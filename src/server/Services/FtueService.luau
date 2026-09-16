--!strict
-- FtueService — SPEC §8, the first sixty seconds.
--
-- Non-negotiable #1: the first object is fed within ~15 seconds. Everything here
-- exists to protect that number. No menu, no lore, no character creator: the player
-- lands in a backyard and three eggs are already wobbling.
--
-- Timeline we are implementing literally:
--   0:00 three eggs      0:06 hatch + HUNGRY      0:12 apple + FEED prompt
--   0:16 eat, grow, tuft, NEW TRAIT, book 1/???   0:25 weird items offered
--   0:35 divergent reactions                      0:50 the giant walks past

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Anatomy = require(Shared.Config:WaitForChild("Anatomy"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local CreatureService = require(script.Parent.CreatureService)
local AnalyticsService = require(script.Parent.AnalyticsService)

local FtueService = {}

-- SPEC §8: "visually different only by colour/personality. No stats."
local EGGS = {
	{ color = 0xFFC9D6, family = "Cute",  label = "", mesh = "Egg_Pink" },
	{ color = 0x9AA6B2, family = "Heavy", label = "", mesh = "Egg_Grey" },
	{ color = 0xC3A8FF, family = "Weird", label = "", mesh = "Egg_Purple" },
}

local RunService = game:GetService("RunService")

-- Blender egg meshes live in Assets.Props (kit_props.fbx). Primitive ball if missing.
local function propMesh(name: string): BasePart?
	local assets = ReplicatedStorage:FindFirstChild("Assets")
	local props = assets and assets:FindFirstChild("Props")
	local m = props and props:FindFirstChild(name)
	local main = m and (m :: Model).PrimaryPart
	return main and main:Clone() or nil
end

-- the chosen egg cracks: top shell pops off and tumbles, bottom stays, both fade
local function crackShell(at: CFrame, color: Color3)
	local top, bottom = propMesh("EggShell_Top"), propMesh("EggShell_Bottom")
	if not (top and bottom) then
		return
	end
	local ground = at.Position - Vector3.new(0, 1.5, 0)
	bottom.CFrame = CFrame.new(ground + Vector3.new(0, bottom.Size.Y * 0.5, 0))
	top.CFrame = bottom.CFrame + Vector3.new(0, 1.35, 0)
	for _, p in ipairs({ top, bottom }) do
		p.Color = color:Lerp(Color3.new(1, 1, 1), 0.55)
		p.CanQuery = false
		p.Parent = workspace
	end
	local t0 = os.clock()
	local side = Vector3.new(math.random() - 0.5, 0, math.random() - 0.5).Unit * 5
	local conn
	conn = RunService.Heartbeat:Connect(function()
		local t = os.clock() - t0
		if t < 0.9 then
			local y = 1.35 + 14 * t - 22 * t * t
			top.CFrame = CFrame.new(bottom.Position + side * t + Vector3.new(0, math.max(y, -0.4), 0))
				* CFrame.Angles(t * 9, 0, t * 6)
		end
		if t > 2.2 then
			local a = math.clamp((t - 2.2) / 0.8, 0, 1)
			top.Transparency, bottom.Transparency = a, a
		end
		if t > 3.1 then
			conn:Disconnect()
			top:Destroy()
			bottom:Destroy()
		end
	end)
end

-- 0:12 the apple. 0:25 "try feeding it something weird."
local STARTER_APPLE = "Apple"
local WEIRD_THREE = { "Mushroom", "Battery", "Fish" }

local eggSets: { [number]: Folder } = {}

local function step(player: Player, n: number, payload)
	local profile = PlayerDataService.get(player)
	if profile then
		profile.ftueStep = math.max(profile.ftueStep or 0, n)
	end
	Net.event("FtueStep"):FireClient(player, n, payload or {})
end

local function placeProp(ingredientId: string, position: Vector3, parent: Instance, player: Player, onTaken)
	local model = CreatureBuilder.buildProp(ingredientId)
	if not model then
		return nil
	end
	local def = Ingredients.get(ingredientId)
	local main = model.PrimaryPart :: BasePart
	model:PivotTo(CFrame.new(position + Vector3.new(0, main.Size.Y * 0.5 + 0.3, 0)))
	model.Parent = parent

	-- SPEC §8: the apple "bounces slightly" — motion is the tutorial
	TweenService:Create(main, TweenInfo.new(0.7, Enum.EasingStyle.Quad, Enum.EasingDirection.InOut, -1, true),
		{ CFrame = main.CFrame + Vector3.new(0, 0.55, 0) }):Play()

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Take"
	prompt.ObjectText = def.emoji .. " " .. def.display
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 14
	prompt.RequiresLineOfSight = false
	prompt.UIOffset = Vector2.new(0, -40) -- float above the food, never on top of it
	prompt.Parent = main

	prompt.Triggered:Connect(function(who)
		if who ~= player then
			return
		end
		local profile = PlayerDataService.get(player)
		if not profile then
			return
		end
		profile.inventory[ingredientId] = (profile.inventory[ingredientId] or 0) + 1
		AnalyticsService.track("ingredient_pickup", player, { ingredient = ingredientId, biome = "FTUE" })
		if not profile.pickedFirst then
			profile.pickedFirst = true
			AnalyticsService.track("ftue_first_food_pickup", player, { ingredient = ingredientId })
		end
		PlayerDataService.sync(player)
		model:Destroy()
		if onTaken then
			onTaken()
		end
	end)
	return model
end

local function spawnEggs(player: Player)
	local char = player.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	-- eggs sit in the player's own backyard (their Sanctuary plot), right in front of them
	local SanctuaryService = require(script.Parent.SanctuaryService)
	-- the row is laid out in the PLOT's frame (eggCF faces into the plot, away from where the
	-- player spawns), so the three eggs always sit side by side in front of the player
	local eggCF = SanctuaryService.eggCF(player)
	local rowCF = eggCF or (hrp and (hrp.CFrame * CFrame.new(0, -3, -11))) or CFrame.new(0, 2, 26)

	local set = Instance.new("Folder")
	set.Name = "Eggs_" .. player.Name
	set.Parent = workspace

	for i, egg in ipairs(EGGS) do
		local p = propMesh(egg.mesh)
		-- a shallow V: the middle egg sits further back so it shows over the player's shoulder
		local spot = (rowCF * CFrame.new((i - 2) * 6.5, 0, i == 2 and 5 or 0)).Position
		local gy = CreatureService.groundAt(spot.X, spot.Z, spot.Y + 6)
		spot = Vector3.new(spot.X, gy, spot.Z)
		if p then
			p.Size *= 1.3 -- they have to read from the spawn point at a glance
		else
			local ball = Instance.new("Part")
			ball.Shape = Enum.PartType.Ball
			ball.Size = Vector3.new(2.4, 3.1, 2.4)
			ball.Color = TableUtil.unpackColor(egg.color)
			ball.Material = Enum.Material.SmoothPlastic
			p = ball
		end
		local egpart = p :: BasePart
		egpart.Name = "Egg" .. i
		egpart.Anchored = true
		egpart.CanCollide = false
		-- the base sits on the ground; the egg rocks about its base, not its middle
		local baseCF = CFrame.new(spot) * rowCF.Rotation * CFrame.Angles(0, math.rad(180 + (i - 2) * 20), 0)
		local half = egpart.Size.Y * 0.5
		egpart.CFrame = baseCF * CFrame.new(0, half, 0)
		egpart.Parent = set

		-- they wobble. that is the whole invitation.
		local rock = Instance.new("NumberValue")
		rock.Value = -1
		rock.Parent = egpart
		rock.Changed:Connect(function(v)
			-- a hop every few rocks so it reads as "something inside"
			egpart.CFrame = baseCF * CFrame.Angles(0, 0, math.rad(v * 12)) * CFrame.new(0, half, 0)
		end)
		TweenService:Create(rock, TweenInfo.new(0.45 + i * 0.07, Enum.EasingStyle.Sine,
			Enum.EasingDirection.InOut, -1, true, (i - 1) * 0.3), { Value = 1 }):Play()

		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Pick"
		prompt.ObjectText = "Egg"
		prompt.HoldDuration = 0
		prompt.UIOffset = Vector2.new(0, -70) -- above the egg, never over it
		prompt.MaxActivationDistance = 16
		prompt.RequiresLineOfSight = false
		prompt.Parent = p

		prompt.Triggered:Connect(function(who)
			if who == player then
				FtueService.pickEgg(player, i)
			end
		end)
	end

	eggSets[player.UserId] = set
	AnalyticsService.track("ftue_egg_seen", player, {})
	-- the camera turns to the eggs (the player was just teleported onto their plot and the
	-- default camera still faces wherever they spawned)
	step(player, 0, { text = "Pick one.", focus = (rowCF * CFrame.new(0, 1.5, 2)).Position })
end

function FtueService.pickEgg(player: Player, index: number)
	local profile = PlayerDataService.get(player)
	if not profile or profile.activeCreature > 0 then
		return { ok = false, reason = "already hatched" }
	end
	local egg = EGGS[index]
	if not egg then
		return { ok = false, reason = "bad egg" }
	end

	local set = eggSets[player.UserId]
	local chosenCF: CFrame? = nil
	if set then
		local chosen = set:FindFirstChild("Egg" .. index) :: BasePart?
		chosenCF = chosen and chosen.CFrame or nil
		set:Destroy()
		eggSets[player.UserId] = nil
	end
	if chosenCF then
		crackShell(chosenCF, TableUtil.unpackColor(egg.color))
	end

	AnalyticsService.track("ftue_egg_selected", player, { egg = index, family = egg.family })

	-- 0:06 a tiny monster tumbles out. plainStart keeps it deliberately bare so the
	-- FIRST feed is an unmistakable change (non-negotiable #2).
	local genome = CreatureBuilder.newGenome({
		bodyFamily = egg.family,
		baseColor = egg.color,
		plainStart = true,
	})
	table.insert(profile.creatures, genome)
	profile.activeCreature = #profile.creatures

	local model = CreatureService.refresh(player, "hop")
	if model and chosenCF then
		local groundOffset = model:GetAttribute("GroundOffset") or 0
		local gy = CreatureService.groundAt(chosenCF.Position.X, chosenCF.Position.Z, chosenCF.Position.Y)
		local char = player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		local p = Vector3.new(chosenCF.Position.X, gy + groundOffset, chosenCF.Position.Z)
		-- it tumbles out and looks up at the player (SPEC §8, 0:06)
		local face = hrp and Vector3.new(hrp.Position.X, p.Y, hrp.Position.Z) or (p + Vector3.new(0, 0, 1))
		model:PivotTo(CFrame.lookAt(p, face))
		task.delay(0.9, function()
			CreatureService.action(model, "hungry")
		end)
	end

	step(player, 1, { text = "HUNGRY!", creature = true })
	PlayerDataService.sync(player)

	-- 0:12 the apple, two metres away
	task.delay(1.6, function()
		if not player.Parent then
			return
		end
		-- the apple lands between the player and the monster: both stay in view
		local torso = model and model.PrimaryPart
		local base = torso and torso.Position or Vector3.new(0, 1, 20)
		local hrpNow = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		local toPlayer = hrpNow and Vector3.new(hrpNow.Position.X - base.X, 0, hrpNow.Position.Z - base.Z) or Vector3.new(0, 0, 1)
		toPlayer = toPlayer.Magnitude > 0.1 and toPlayer.Unit or Vector3.new(0, 0, 1)
		local side = Vector3.new(-toPlayer.Z, 0, toPlayer.X)
		placeProp(STARTER_APPLE, base + toPlayer * 2 + side * 4, workspace, player, function()
			step(player, 3, { text = "FEED 🍎", prompt = "feed" })
		end)
		step(player, 2, { text = "It wants that apple." })
	end)

	return { ok = true }
end

-- Called by FeedingService after the very first successful feed.
function FtueService.onFirstFeed(player: Player)
	local profile = PlayerDataService.get(player)
	if not profile then
		return
	end

	-- the FEED hint has done its job; clear it now, not when the next line arrives
	step(player, 3, {})
	-- 0:25 "Try feeding it something weird."
	task.delay(2.2, function()
		if not player.Parent then
			return
		end
		local model = CreatureService.get(player)
		local torso = model and model.PrimaryPart
		local base = torso and torso.Position or Vector3.new(0, 1, 20)
		local hrpNow = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		local toPlayer = hrpNow and Vector3.new(hrpNow.Position.X - base.X, 0, hrpNow.Position.Z - base.Z) or Vector3.new(0, 0, 1)
		toPlayer = toPlayer.Magnitude > 0.1 and toPlayer.Unit or Vector3.new(0, 0, 1)
		local side = Vector3.new(-toPlayer.Z, 0, toPlayer.X)
		-- a fan of three weird things between you and the monster, all on screen
		for i, id in ipairs(WEIRD_THREE) do
			-- spread wide and ahead of the player so the three "Take" prompts never stack
			local pos = base + toPlayer * 3 + side * ((i - 2) * 7)
			placeProp(id, pos, workspace, player, nil)
		end
		CreatureService.enablePet(player)
		step(player, 4, { text = "Try feeding it something weird." })
	end)
end

function FtueService.start()
	PlayerDataService.onLoaded(function(player, profile)
		-- returning players skip the whole thing; they have a creature already
		if profile.activeCreature > 0 then
			step(player, 9, {})
			return
		end
		task.spawn(function()
			for _ = 1, 120 do
				if player.Character and player.Character:FindFirstChild("HumanoidRootPart") then
					break
				end
				task.wait(0.1)
			end
			if player.Parent then
				spawnEggs(player)
			end
		end)
	end)

	Players.PlayerRemoving:Connect(function(player)
		local set = eggSets[player.UserId]
		if set then
			set:Destroy()
		end
		eggSets[player.UserId] = nil
	end)

	print("[FTUE] ready")
end

return FtueService
