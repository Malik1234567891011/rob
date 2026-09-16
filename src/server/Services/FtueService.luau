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
	{ color = 0xFFC9D6, family = "Cute",  label = "" },
	{ color = 0x9AA6B2, family = "Heavy", label = "" },
	{ color = 0xC3A8FF, family = "Weird", label = "" },
}

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
	local base = hrp and hrp.Position or Vector3.new(0, 3, 26)

	local set = Instance.new("Folder")
	set.Name = "Eggs_" .. player.Name
	set.Parent = workspace

	for i, egg in ipairs(EGGS) do
		local p = Instance.new("Part")
		p.Name = "Egg" .. i
		p.Shape = Enum.PartType.Ball
		p.Size = Vector3.new(2.4, 3.1, 2.4)
		p.Color = TableUtil.unpackColor(egg.color)
		p.Material = Enum.Material.SmoothPlastic
		p.Anchored = true
		p.CanCollide = false
		p.CFrame = CFrame.new(base + Vector3.new((i - 2) * 4.5, -1.2, -9))
		p.Parent = set

		-- they wobble. that is the whole invitation.
		TweenService:Create(p, TweenInfo.new(0.9 + i * 0.13, Enum.EasingStyle.Sine,
			Enum.EasingDirection.InOut, -1, true),
			{ CFrame = p.CFrame * CFrame.Angles(0, 0, math.rad(i % 2 == 0 and 11 or -11)) }):Play()

		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Pick"
		prompt.ObjectText = "Egg"
		prompt.HoldDuration = 0
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
	step(player, 0, { text = "Pick one." })
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
		local torso = model and model.PrimaryPart
		local base = torso and torso.Position or Vector3.new(0, 1, 20)
		placeProp(STARTER_APPLE, base + Vector3.new(3.5, 0, 3.0), workspace, player, function()
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

	-- 0:25 "Try feeding it something weird."
	task.delay(2.2, function()
		if not player.Parent then
			return
		end
		local model = CreatureService.get(player)
		local torso = model and model.PrimaryPart
		local base = torso and torso.Position or Vector3.new(0, 1, 20)
		for i, id in ipairs(WEIRD_THREE) do
			local angle = math.rad(-40 + (i - 1) * 40)
			local offset = Vector3.new(math.sin(angle) * 8, 0, math.cos(angle) * 8)
			placeProp(id, base + offset, workspace, player, nil)
		end
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
