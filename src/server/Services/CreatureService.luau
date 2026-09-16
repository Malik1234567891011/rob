--!strict
-- CreatureService — the creature as a CHARACTER, not a walking multiplier.
-- SPEC §99 non-negotiable #4, and SPEC §18 (temperament drives behaviour, not stats).
--
-- Split of responsibilities (so animation costs no network):
--   SERVER  moves the anchored RootPart along the ground, decides MOOD (sit / sleep /
--           hide) and broadcasts one-shot ACTIONS (eat, hop, sniff, pet, celebrate...).
--   CLIENT  CreatureController + Shared.CreatureAnimator turn that into bones: gait,
--           look-at, blinking, chewing. Bone.Transform never replicates.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local Anatomy = require(Shared.Config:WaitForChild("Anatomy"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)

local CreatureService = {}

CreatureService.TAG = "FAMCreature"

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

-- ═══ GROUND ══════════════════════════════════════════════════════════════════

local groundParams = RaycastParams.new()
groundParams.FilterType = Enum.RaycastFilterType.Exclude
groundParams.RespectCanCollide = true

local function refreshGroundFilter()
	local exclude: { Instance } = { ensureContainer() }
	for _, p in ipairs(Players:GetPlayers()) do
		if p.Character then
			table.insert(exclude, p.Character)
		end
	end
	groundParams.FilterDescendantsInstances = exclude
end

-- Height of walkable ground under (x, z), searching down from `fromY`.
function CreatureService.groundAt(x: number, z: number, fromY: number?): number
	local origin = Vector3.new(x, (fromY or 60) + 40, z)
	local hit = workspace:Raycast(origin, Vector3.new(0, -400, 0), groundParams)
	return hit and hit.Position.Y or 0
end

-- ═══ NAMEPLATE (SPEC §24) ════════════════════════════════════════════════════

local function nameplate(model: Model, genome)
	local root = model.PrimaryPart
	if not root then
		return
	end
	local height = model:GetAttribute("Height") or 2
	local gui = Instance.new("BillboardGui")
	gui.Name = "Nameplate"
	gui.Size = UDim2.fromOffset(180, 46)
	gui.StudsOffsetWorldSpace = Vector3.new(0, height + 0.9, 0)
	gui.AlwaysOnTop = false
	gui.MaxDistance = 70
	gui.LightInfluence = 0
	gui.Adornee = root
	gui.Parent = root

	local label = Instance.new("TextLabel")
	label.Size = UDim2.new(1, 0, 0.58, 0)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.FredokaOne
	label.TextScaled = true
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.TextStrokeTransparency = 0.45
	label.Text = genome.name or ""
	label.Parent = gui

	local sub = Instance.new("TextLabel")
	sub.Name = "Sub"
	sub.Position = UDim2.fromScale(0, 0.58)
	sub.Size = UDim2.new(1, 0, 0.42, 0)
	sub.BackgroundTransparency = 1
	sub.Font = Enum.Font.GothamBold
	sub.TextScaled = true
	sub.TextColor3 = Color3.fromRGB(236, 240, 246)
	sub.TextStrokeTransparency = 0.6
	local dom = CreatureBuilder.dominantTrait(genome)
	local stage = Progression.stage(genome.stage or 1)
	sub.Text = string.format("%s Gen %d  %s", stage.emoji, genome.generation or 1, dom and Traits.display(dom) or "")
	sub.Parent = gui
end

-- ═══ TEMPERAMENT (SPEC §18) ══════════════════════════════════════════════════

local function dominantTemperament(genome): string
	local top = TableUtil.topN(genome.temperament or {}, 1)
	return #top > 0 and top[1].key or "curious"
end

-- how each temperament follows, in multiples of the creature's own length
local FOLLOW = {
	affectionate = { dist = 0.8, speed = 15, idleAction = "hop", idleEvery = 9 },
	curious      = { dist = 1.3, speed = 12, idleAction = "sniff", idleEvery = 7 },
	greedy       = { dist = 1.0, speed = 14, idleAction = "hungry", idleEvery = 10 },
	brave        = { dist = 1.4, speed = 13, idleAction = "sniff", idleEvery = 12 },
	mischievous  = { dist = 1.2, speed = 14, idleAction = "hop", idleEvery = 6 },
	silly        = { dist = 1.2, speed = 13, idleAction = "stumble", idleEvery = 11 },
	nervous      = { dist = 0.7, speed = 13, idleAction = "sniff", idleEvery = 14 },
	lazy         = { dist = 1.8, speed = 8, idleAction = "hop", idleEvery = 30 },
}

-- ═══ ACTIONS ═════════════════════════════════════════════════════════════════

-- One-shot animation for everyone nearby. The client decides whether it is close enough
-- to bother playing it.
function CreatureService.action(model: Model?, action: string, extra: any?)
	if not model then
		return
	end
	local id = model:GetAttribute("CreatureId")
	if id then
		Net.event("CreatureAction"):FireAllClients(id, action, extra)
	end
end

function CreatureService.actionFor(player: Player, action: string, extra: any?)
	local state = active[player.UserId]
	if state then
		state.lastActionAt = os.clock()
		CreatureService.action(state.model, action, extra)
	end
end

-- ═══ SPAWN / REBUILD ═════════════════════════════════════════════════════════

local function petPrompt(model: Model, owner: Player)
	local root = model.PrimaryPart
	if not root then
		return
	end
	local attach = Instance.new("Attachment")
	attach.Name = "PromptAnchor"
	attach.Position = Vector3.new(0, (model:GetAttribute("Height") or 2) * 0.6, 0)
	attach.Parent = root
	local prompt = Instance.new("ProximityPrompt")
	prompt.Name = "PetPrompt"
	prompt.ActionText = "Pet"
	prompt.ObjectText = ""
	prompt.HoldDuration = 0.25
	prompt.MaxActivationDistance = 9
	prompt.RequiresLineOfSight = false
	prompt.Style = Enum.ProximityPromptStyle.Default
	prompt.KeyboardKeyCode = Enum.KeyCode.F
	prompt.Parent = attach
	prompt.Triggered:Connect(function(who)
		local state = active[owner.UserId]
		if not state or state.model ~= model then
			return
		end
		if os.clock() - (state.lastPetAt or 0) < 1.2 then
			return
		end
		state.lastPetAt = os.clock()
		state.mood = nil
		state.moodUntil = os.clock() + 6
		CreatureService.action(model, "pet")
		local ok, Analytics = pcall(require, script.Parent.AnalyticsService)
		if ok then
			Analytics.track("monster_petted", who, { own = who == owner })
		end
		if who == owner then
			PlayerDataService.stat(owner, "pets")
			require(script.Parent.GameEvents).fire(owner, "pet", {})
		end
	end)
end

--[[
	Build (or rebuild) the model for a player's active creature.
	`reveal` names a one-shot the client plays on the NEW model (eg. "celebrate" after a
	mutation, "evolve" after a stage change), so a morph is felt, not just seen.
]]
function CreatureService.refresh(player: Player, reveal: any?)
	local genome = PlayerDataService.activeCreature(player)
	if not genome then
		return nil
	end
	refreshGroundFilter()

	local state = active[player.UserId]
	local keepCF = state and state.model and state.model.PrimaryPart and state.model.PrimaryPart.CFrame or nil
	if state and state.model then
		state.model:Destroy()
	end

	local model = CreatureBuilder.build(genome, 1)
	model.Name = (genome.name or "Creature") .. "_" .. player.Name
	model:SetAttribute("Owner", player.UserId)
	model:SetAttribute("OwnerName", player.Name)
	local temperament = dominantTemperament(genome)
	model:SetAttribute("Temperament", temperament)
	if reveal == true then
		reveal = "celebrate"
	end
	if type(reveal) == "string" then
		model:SetAttribute("Reveal", reveal)
		model:SetAttribute("RevealAt", workspace:GetServerTimeNow())
	end

	local groundOffset = model:GetAttribute("GroundOffset") or 0
	local cf: CFrame
	if keepCF then
		local y = CreatureService.groundAt(keepCF.Position.X, keepCF.Position.Z, keepCF.Position.Y) + groundOffset
		cf = CFrame.new(keepCF.Position.X, y, keepCF.Position.Z) * keepCF.Rotation
	else
		local char = player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		local base = hrp and hrp.Position or Vector3.new(0, 0, 0)
		local p = base + (hrp and hrp.CFrame.LookVector * 5 or Vector3.new(0, 0, -5))
		cf = CFrame.lookAt(Vector3.new(p.X, CreatureService.groundAt(p.X, p.Z, base.Y) + groundOffset, p.Z),
			Vector3.new(base.X, CreatureService.groundAt(p.X, p.Z, base.Y) + groundOffset, base.Z))
	end
	model:PivotTo(cf)
	model.Parent = ensureContainer()
	CollectionService:AddTag(model, CreatureService.TAG)

	nameplate(model, genome)
	petPrompt(model, player)
	CreatureService.stampAbilities(player)

	local body = Anatomy.bodies[genome.bodyFamily] or Anatomy.bodies.Cute
	active[player.UserId] = {
		model = model,
		genome = genome,
		temperament = temperament,
		follow = FOLLOW[temperament] or FOLLOW.curious,
		groundOffset = groundOffset,
		length = math.max(1.5, (model:GetAttribute("Height") or 2) * 1.2) * (body.followScale or 1),
		mood = nil :: string?,
		moodUntil = os.clock() + 5,
		lastActionAt = os.clock(),
		lastMoveAt = os.clock(),
		ownerStillSince = os.clock(),
		lastOwnerPos = nil :: Vector3?,
		-- stable per-creature lateral offset so two creatures never stack up
		sideOffset = (player.UserId % 2 == 0) and 1 or -1,
		heading = cf.LookVector,
	}
	return model
end

-- What the active creature lets the player DO (read by the client MovementController and
-- AmbienceController). SPEC §11: abilities change the route, not a stat screen.
local ABILITY_ATTR = {
	Glide = "CanGlide", Sticky = "CanClimb", Ghost = "CanGhost", Tiny = "CanTiny",
	Aquatic = "CanSwim", Heatproof = "CanHeat", Light = "CanLight",
}
function CreatureService.stampAbilities(player: Player)
	local char = player.Character
	if not char then
		return
	end
	local genome = PlayerDataService.activeCreature(player)
	local abilities = genome and genome.abilities or {}
	for ability, attr in pairs(ABILITY_ATTR) do
		char:SetAttribute(attr, abilities[ability] == true or nil)
	end
end

function CreatureService.get(player: Player): Model?
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

-- Take over movement for a scripted walk (parade runway, cutscenes). nil gives it back.
--   { from = Vector3, to = Vector3, duration = s, startedAt = os.clock(),
--     pauseAt = 0..1?, pauseFor = s?, action = "celebrate"? }
function CreatureService.setOverride(player: Player, override)
	local state = active[player.UserId]
	if state then
		state.override = override
		if override then
			state.overridePosed = false
			state.mood = nil
			state.model:SetAttribute("Mood", nil)
		end
	end
end

function CreatureService.setMood(player: Player, mood: string?, seconds: number?)
	local state = active[player.UserId]
	if state then
		state.mood = mood
		state.moodUntil = os.clock() + (seconds or 8)
		state.model:SetAttribute("Mood", mood)
	end
end

-- ═══ STEP ════════════════════════════════════════════════════════════════════

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

local groundTick = 0

local function step(dt: number)
	groundTick += dt
	local now = os.clock()
	for userId, state in pairs(active) do
		local model = state.model
		local root = model and model.PrimaryPart
		if not root or not model.Parent then
			active[userId] = nil
			continue
		end
		local player = Players:GetPlayerByUserId(userId)
		local char = player and player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		local F = state.follow
		local pos = root.Position
		local target = pos

		-- ── scripted walk (parade) ──────────────────────────────────────────
		local ov = state.override
		if ov then
			local elapsed = now - ov.startedAt
			local walkTime = ov.duration - (ov.pauseFor or 0)
			local t
			if ov.pauseAt and elapsed > ov.pauseAt * walkTime and elapsed < ov.pauseAt * walkTime + (ov.pauseFor or 0) then
				t = ov.pauseAt
				if not state.overridePosed and ov.action then
					state.overridePosed = true
					CreatureService.action(model, ov.action)
				end
			else
				local walked = elapsed
				if ov.pauseAt and elapsed >= ov.pauseAt * walkTime + (ov.pauseFor or 0) then
					walked -= (ov.pauseFor or 0)
				end
				t = math.clamp(walked / walkTime, 0, 1)
			end
			local p = ov.from:Lerp(ov.to, t)
			local dir = flat(ov.to - ov.from)
			state.heading = dir.Magnitude > 0.01 and dir.Unit or state.heading
			local gy = CreatureService.groundAt(p.X, p.Z, p.Y + 5)
			local y = gy + state.groundOffset
			root.CFrame = CFrame.lookAt(Vector3.new(p.X, y, p.Z), Vector3.new(p.X, y, p.Z) + state.heading)
			continue
		end

		-- owner stillness drives lazy/sleep behaviour
		if hrp then
			if state.lastOwnerPos and (hrp.Position - state.lastOwnerPos).Magnitude > 0.6 then
				state.ownerStillSince = now
			end
			state.lastOwnerPos = hrp.Position
		end
		local ownerIdle = now - state.ownerStillSince

		-- ── choose a mood ───────────────────────────────────────────────────
		local mood: string? = state.mood
		if now > state.moodUntil then
			mood = nil
			if state.temperament == "lazy" and ownerIdle > 6 then
				mood = math.random() < 0.5 and "sleep" or "sit"
			elseif ownerIdle > 25 then
				mood = (state.temperament == "nervous") and "hide" or "sleep"
			elseif state.temperament == "nervous" and math.random() < 0.15 then
				mood = "hide"
			end
			state.mood = mood
			state.moodUntil = now + math.random(5, 10)
		end
		if ownerIdle < 0.5 and state.mood == "sleep" then
			-- owner moved: wake up (the client plays a little hop as it wakes)
			state.mood = nil
			mood = nil
			CreatureService.action(model, "hop")
		end
		if model:GetAttribute("Mood") ~= mood then
			model:SetAttribute("Mood", mood)
		end

		-- ── follow ──────────────────────────────────────────────────────────
		local lookDir = state.heading
		if hrp and mood ~= "sleep" and mood ~= "sit" then
			local look = flat(hrp.CFrame.LookVector)
			if look.Magnitude < 0.01 then
				look = Vector3.new(0, 0, -1)
			end
			look = look.Unit
			local right = Vector3.new(-look.Z, 0, look.X)
			-- The whole game is watching your creature change, so it stays ON SCREEN:
			-- anchored in front of the owner, distance proportional to its own size.
			local reach = math.clamp(2.5 + state.length * F.dist * 1.6, 4, 16)
			local anchor
			if state.temperament == "nervous" and mood == "hide" then
				anchor = hrp.Position - look * math.max(3, reach * 0.45)
			else
				anchor = hrp.Position + look * reach + right * state.sideOffset * math.min(3, state.length * 0.9)
			end
			local toAnchor = flat(anchor - pos)
			local gap = toAnchor.Magnitude
			if gap > 60 then
				-- fell far behind (teleport, respawn): catch up instantly
				target = Vector3.new(anchor.X, pos.Y, anchor.Z)
			elseif gap > 1.0 then
				local speed = F.speed * (gap > 14 and 1.8 or 1)
				target = pos + toAnchor.Unit * math.min(speed * dt, gap)
				state.lastMoveAt = now
			end
			-- face movement while moving, face the owner when settled
			local moved = flat(target - pos)
			if moved.Magnitude > 0.02 then
				lookDir = moved.Unit
			else
				local toOwner = flat(hrp.Position - pos)
				if toOwner.Magnitude > 0.5 then
					lookDir = toOwner.Unit
				end
			end
		end
		state.heading = state.heading:Lerp(lookDir, math.clamp(dt * 7, 0, 1))
		if state.heading.Magnitude < 0.01 then
			state.heading = lookDir
		end

		-- ── idle flourishes (temperament-flavoured) ─────────────────────────
		if not mood and now - state.lastMoveAt > 1.5 and now - state.lastActionAt > F.idleEvery then
			state.lastActionAt = now + math.random() * 3
			CreatureService.action(model, F.idleAction)
		end

		-- ── ground + write ──────────────────────────────────────────────────
		local groundY = state.groundY
		if not groundY or groundTick > 0.2 or (target - pos).Magnitude > 0.01 then
			groundY = CreatureService.groundAt(target.X, target.Z, pos.Y)
			state.groundY = groundY
		end
		local y = groundY + state.groundOffset
		local p = Vector3.new(target.X, y, target.Z)
		local h = flat(state.heading)
		if h.Magnitude < 0.01 then
			h = Vector3.new(0, 0, -1)
		end
		root.CFrame = CFrame.lookAt(p, p + h.Unit)
	end
	if groundTick > 0.2 then
		groundTick = 0
	end
end

function CreatureService.start()
	ensureContainer()
	RunService.Heartbeat:Connect(step)

	Players.PlayerRemoving:Connect(function(player)
		CreatureService.despawn(player)
	end)
	Players.PlayerAdded:Connect(function(player)
		player.CharacterAdded:Connect(function()
			task.defer(CreatureService.stampAbilities, player)
		end)
	end)
	for _, player in ipairs(Players:GetPlayers()) do
		player.CharacterAdded:Connect(function()
			task.defer(CreatureService.stampAbilities, player)
		end)
	end

	PlayerDataService.onLoaded(function(player, profile)
		if profile.activeCreature > 0 and profile.creatures[profile.activeCreature] then
			task.spawn(function()
				for _ = 1, 100 do
					if player.Character and player.Character:FindFirstChild("HumanoidRootPart") then
						break
					end
					task.wait(0.1)
				end
				CreatureService.refresh(player, nil)
			end)
		end
	end)

	print("[Creature] ready")
end

return CreatureService
