--!strict
-- CreatureService — the creature as a CHARACTER, not a walking multiplier.
-- SPEC §99 non-negotiable #4, and SPEC §18 (temperament drives animation, not stats).
--
-- The torso is anchored and driven directly; every other part is welded to it, so
-- moving the root moves the whole creature with no physics cost and no pushing
-- players around.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)

local CreatureService = {}

local active: { [number]: any } = {}
local container: Folder

local function ensureContainer(): Folder
	if container and container.Parent then
		return container
	end
	local existing = workspace:FindFirstChild("Creatures")
	if existing then
		container = existing :: Folder
	else
		container = Instance.new("Folder")
		container.Name = "Creatures"
		container.Parent = workspace
	end
	return container
end

-- SPEC §24: a stranger's monster must be inspectable at a glance.
local function nameplate(model: Model, genome, ownerName: string)
	local torso = model.PrimaryPart
	if not torso then
		return
	end
	local gui = Instance.new("BillboardGui")
	gui.Name = "Nameplate"
	gui.Size = UDim2.fromScale(7, 2)
	gui.StudsOffsetWorldSpace = Vector3.new(0, torso.Size.Y * 0.95 + 1.6, 0)
	gui.AlwaysOnTop = false
	gui.MaxDistance = 90
	gui.Adornee = torso
	gui.Parent = torso

	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 0.55)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.FredokaOne
	label.TextScaled = true
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.TextStrokeTransparency = 0.35
	label.Text = genome.name or "???"
	label.Parent = gui

	local sub = Instance.new("TextLabel")
	sub.Name = "Sub"
	sub.Position = UDim2.fromScale(0, 0.55)
	sub.Size = UDim2.fromScale(1, 0.45)
	sub.BackgroundTransparency = 1
	sub.Font = Enum.Font.Gotham
	sub.TextScaled = true
	sub.TextColor3 = Color3.fromRGB(226, 232, 240)
	sub.TextStrokeTransparency = 0.5

	local dom = CreatureBuilder.dominantTrait(genome)
	local stage = Progression.stage(genome.stage or 1)
	sub.Text = string.format("Gen %d  %s  %s",
		genome.generation or 1, stage.emoji,
		dom and Traits.display(dom) or "")
	sub.Parent = gui
end

local function dominantTemperament(genome): string
	local top = TableUtil.topN(genome.temperament or {}, 1)
	return #top > 0 and top[1].key or "curious"
end

--[[
	Build (or rebuild) the model for a player's active creature.
	`dramatic` plays a pop so a mutation/evolution is felt, not just seen.
]]
function CreatureService.refresh(player: Player, dramatic: boolean?)
	local genome = PlayerDataService.activeCreature(player)
	if not genome then
		return
	end

	local state = active[player.UserId]
	local keepCF = state and state.model and state.model.PrimaryPart
		and state.model.PrimaryPart.CFrame or nil

	if state and state.model then
		state.model:Destroy()
	end

	local model = CreatureBuilder.build(genome, 1)
	model.Name = (genome.name or "Creature") .. "_" .. player.Name
	model:SetAttribute("Owner", player.UserId)
	model:SetAttribute("OwnerName", player.Name)
	model.Parent = ensureContainer()

	local groundOffset = model:GetAttribute("GroundOffset") or 2
	if keepCF then
		model:PivotTo(CFrame.new(keepCF.Position.X, groundOffset, keepCF.Position.Z)
			* (keepCF - keepCF.Position))
	else
		local char = player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart")
		local base = hrp and (hrp :: BasePart).Position or Vector3.new(0, 0, 0)
		model:PivotTo(CFrame.new(base.X + 4, groundOffset, base.Z + 4))
	end

	nameplate(model, genome, player.Name)

	active[player.UserId] = {
		model = model,
		genome = genome,
		temperament = dominantTemperament(genome),
		phase = math.random() * 10,
		groundOffset = groundOffset,
		popUntil = dramatic and (os.clock() + 0.5) or 0,
		mood = "follow",
		moodUntil = 0,
	}
	return model
end

function CreatureService.get(player: Player)
	local state = active[player.UserId]
	return state and state.model or nil
end

function CreatureService.despawn(player: Player)
	local state = active[player.UserId]
	if state and state.model then
		state.model:Destroy()
	end
	active[player.UserId] = nil
end

-- SPEC §18: temperament decides HOW it moves, not how strong it is.
local FOLLOW = {
	affectionate = { dist = 4.0,  speed = 15, bob = 1.25 },
	curious      = { dist = 7.0,  speed = 12, bob = 1.0 },
	greedy       = { dist = 5.5,  speed = 14, bob = 1.15 },
	brave        = { dist = 6.5,  speed = 13, bob = 0.9 },
	mischievous  = { dist = 6.0,  speed = 14, bob = 1.3 },
	silly        = { dist = 6.0,  speed = 13, bob = 1.5 },
	nervous      = { dist = 3.2,  speed = 13, bob = 0.8 },
	lazy         = { dist = 9.0,  speed = 7,  bob = 0.5 },
}

local function step(dt: number)
	for userId, state in pairs(active) do
		local model = state.model
		local torso = model and model.PrimaryPart
		if not torso or not model.Parent then
			active[userId] = nil
			continue
		end

		local player = Players:GetPlayerByUserId(userId)
		local char = player and player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?

		local profile = FOLLOW[state.temperament] or FOLLOW.curious
		state.phase += dt * (2.0 * profile.bob)

		local pos = torso.Position
		local target = pos

		if hrp then
			local toOwner = hrp.Position - pos
			local flat = Vector3.new(toOwner.X, 0, toOwner.Z)
			local dist = flat.Magnitude

			if state.temperament == "nervous" and dist < profile.dist then
				-- hides BEHIND the owner rather than in front of them
				local behind = hrp.CFrame.LookVector * -3
				target = hrp.Position + Vector3.new(behind.X, 0, behind.Z)
			elseif dist > profile.dist then
				local move = flat.Unit * math.min(profile.speed * dt, dist - profile.dist * 0.8)
				target = pos + move
			elseif state.temperament == "mischievous" then
				-- circles the owner instead of standing still
				local side = Vector3.new(-flat.Z, 0, flat.X)
				if side.Magnitude > 0.01 then
					target = pos + side.Unit * (profile.speed * 0.45 * dt)
				end
			end
		end

		-- lazy creatures sit down, dramatically, on their own schedule
		if state.temperament == "lazy" and os.clock() > state.moodUntil then
			state.mood = (state.mood == "sit") and "follow" or "sit"
			state.moodUntil = os.clock() + math.random(4, 9)
		end

		local bobAmp = (state.mood == "sit") and 0.04 or 0.16
		local bob = math.abs(math.sin(state.phase)) * bobAmp * torso.Size.Y
		local sink = (state.mood == "sit") and torso.Size.Y * 0.12 or 0
		local y = state.groundOffset + bob - sink

		-- pop on mutation / evolution so the change is FELT (SPEC §5)
		local extra = CFrame.identity
		if os.clock() < state.popUntil then
			local t = (state.popUntil - os.clock()) / 0.5
			extra = CFrame.Angles(0, math.sin(t * 22) * 0.22, 0)
		end

		local look = torso.CFrame.LookVector
		if hrp then
			-- it looks at its owner. SPEC §42 lists this first in the animation budget.
			local toOwner = hrp.Position - Vector3.new(target.X, hrp.Position.Y, target.Z)
			if toOwner.Magnitude > 0.5 then
				look = toOwner.Unit
			end
		end
		local flatLook = Vector3.new(look.X, 0, look.Z)
		if flatLook.Magnitude < 0.01 then
			flatLook = Vector3.new(0, 0, -1)
		end

		local goal = CFrame.lookAt(Vector3.new(target.X, y, target.Z),
			Vector3.new(target.X, y, target.Z) + flatLook.Unit) * extra
		torso.CFrame = torso.CFrame:Lerp(goal, math.clamp(dt * 8, 0, 1))
	end
end

function CreatureService.start()
	ensureContainer()
	RunService.Heartbeat:Connect(step)

	Players.PlayerRemoving:Connect(function(player)
		CreatureService.despawn(player)
	end)

	PlayerDataService.onLoaded(function(player, profile)
		if profile.activeCreature > 0 and profile.creatures[profile.activeCreature] then
			-- wait for a character so it spawns beside them, not at the origin
			task.spawn(function()
				for _ = 1, 100 do
					if player.Character and player.Character:FindFirstChild("HumanoidRootPart") then
						break
					end
					task.wait(0.1)
				end
				CreatureService.refresh(player, false)
			end)
		end
	end)

	print("[Creature] ready")
end

return CreatureService
