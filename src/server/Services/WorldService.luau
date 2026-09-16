--!strict
-- WorldService — hub + biome islands, built procedurally. SPEC §13.
--
-- SPEC §7: the world is one giant ingredient cabinet. Anything spawned here with an
-- `Ingredient` attribute is edible, and the prompt says so, so "can I feed that to
-- him?" is answerable at a glance.
--
-- SPEC §42: "a tree can look mediocre, the creature cannot." Scenery is deliberately
-- cheap; the part budget goes to creatures.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Biomes = require(Shared.Config:WaitForChild("Biomes"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Rng = require(Shared.Util:WaitForChild("Rng"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local AnalyticsService = require(script.Parent.AnalyticsService)

local WorldService = {}

local RESPAWN_SECONDS = 22
local world: Folder
local propCounts: { [string]: number } = {}

local function folder(name: string, parent: Instance): Folder
	local existing = parent:FindFirstChild(name)
	if existing then
		return existing :: Folder
	end
	local f = Instance.new("Folder")
	f.Name = name
	f.Parent = parent
	return f
end

local function slab(name, size: Vector3, cf: CFrame, color: number, material: Enum.Material, parent)
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.CFrame = cf
	p.Anchored = true
	p.Color = TableUtil.unpackColor(color)
	p.Material = material
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

-- ═══ INGREDIENT PICKUPS ══════════════════════════════════════════════════════

local function spawnProp(biomeId: string, ingredientId: string, position: Vector3, parent: Folder)
	local model = CreatureBuilder.buildProp(ingredientId)
	if not model then
		return nil
	end
	local def = Ingredients.get(ingredientId)
	local main = model.PrimaryPart :: BasePart
	local lift = main.Size.Y * 0.5 + 0.25
	model:PivotTo(CFrame.new(position + Vector3.new(0, lift, 0))
		* CFrame.Angles(0, math.random() * 6.28, 0))
	model:SetAttribute("Biome", biomeId)
	model.Parent = parent

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Take"
	prompt.ObjectText = def.emoji .. " " .. def.display
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 11
	prompt.RequiresLineOfSight = false
	prompt.Parent = main

	prompt.Triggered:Connect(function(player)
		local profile = PlayerDataService.get(player)
		if not profile then
			return
		end
		profile.inventory[ingredientId] = (profile.inventory[ingredientId] or 0) + 1

		AnalyticsService.track("ingredient_pickup", player, { ingredient = ingredientId, biome = biomeId })
		if not profile.pickedFirst then
			profile.pickedFirst = true
			AnalyticsService.track("ftue_first_food_pickup", player, { ingredient = ingredientId })
		end

		Net.event("Toast"):FireClient(player, {
			kind = "pickup",
			title = "PICKED UP",
			label = def.emoji .. " " .. def.display,
			-- SPEC §45: simple by default, detail only for players who asked for it
			sub = WorldService.describeInfluence(def, profile.detailMode),
			color = Ingredients.rarityColor[def.rarity],
		})
		PlayerDataService.sync(player)

		model:Destroy()
		propCounts[biomeId] = (propCounts[biomeId] or 1) - 1

		task.delay(RESPAWN_SECONDS, function()
			WorldService.topUp(biomeId)
		end)
	end)

	propCounts[biomeId] = (propCounts[biomeId] or 0) + 1
	return model
end

-- SPEC §45: "⚡ Strong Electric influence" for everyone; numbers only on request.
function WorldService.describeInfluence(def, detailed: boolean): string
	local Traits = require(Shared.Config.Traits)
	local ranked = TableUtil.topN(def.influences, detailed and 6 or 2)
	local parts = {}
	for _, entry in ipairs(ranked) do
		local t = Traits.get(entry.key)
		if t then
			if detailed then
				table.insert(parts, string.format("%s %s +%d", t.emoji, t.display, entry.value))
			else
				local strength = entry.value >= 4 and "Strong" or (entry.value >= 2 and "Some" or "Small")
				table.insert(parts, string.format("%s %s %s", t.emoji, strength, t.display))
			end
		end
	end
	return table.concat(parts, "   ")
end

local function randomPointIn(biome, rng): Vector3
	local ox, _, oz = biome.origin[1], biome.origin[2], biome.origin[3]
	local halfX, halfZ = biome.size[1] * 0.5 - 12, biome.size[2] * 0.5 - 12
	return Vector3.new(ox + rng:num(-halfX, halfX), 0, oz + rng:num(-halfZ, halfZ))
end

function WorldService.topUp(biomeId: string)
	local biome = Biomes.get(biomeId)
	if not biome or not world then
		return
	end
	local parent = world:FindFirstChild(biomeId)
	if not parent then
		return
	end
	local props = parent:FindFirstChild("Props") :: Folder
	if not props then
		return
	end

	local rng = Rng.new()
	local have = propCounts[biomeId] or 0
	for _ = 1, math.max(0, biome.maxProps - have) do
		local id = rng:pick(biome.spawnTable)
		spawnProp(biomeId, id, randomPointIn(biome, rng), props)
	end
end

-- ═══ SCENERY ═════════════════════════════════════════════════════════════════

local function decorate(biomeId: string, biome, parent: Folder, rng)
	local deco = folder("Scenery", parent)
	if biomeId == "Meadow" or biomeId == "Habitat" then
		for _ = 1, (biomeId == "Habitat" and 6 or 22) do
			local p = randomPointIn(biome, rng)
			local h = rng:num(6, 12)
			slab("Trunk", Vector3.new(1.4, h, 1.4), CFrame.new(p + Vector3.new(0, h * 0.5, 0)),
				0x6B4A2A, Enum.Material.Wood, deco)
			local crown = slab("Leaves", Vector3.new(7, 6, 7),
				CFrame.new(p + Vector3.new(0, h + 1.6, 0)), 0x4E9B42, Enum.Material.Grass, deco)
			crown.Shape = Enum.PartType.Ball
		end
	elseif biomeId == "Junkyard" then
		for _ = 1, 26 do
			local p = randomPointIn(biome, rng)
			local h = rng:num(3, 9)
			slab("ScrapPile", Vector3.new(rng:num(3, 7), h, rng:num(3, 7)),
				CFrame.new(p + Vector3.new(0, h * 0.5, 0)) * CFrame.Angles(0, rng:num(0, 6.28), 0),
				rng:chance(0.5) and 0x7A6A5A or 0x59636B, Enum.Material.CorrodedMetal, deco)
		end
	end
end

-- ═══ ABILITY GATES (SPEC §11) ════════════════════════════════════════════════

local function buildGate(gate, parent: Folder)
	local ability = Mutations.abilities[gate.ability]
	local anchor = slab("Gate_" .. gate.id, Vector3.new(9, 7, 9),
		CFrame.new(gate.position[1], 3.5, gate.position[3]),
		0x5A5148, Enum.Material.Rock, parent)
	anchor:SetAttribute("Gate", gate.id)

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = ability.display .. " needed"
	prompt.ObjectText = gate.prompt
	prompt.HoldDuration = 0.4
	prompt.MaxActivationDistance = 14
	prompt.RequiresLineOfSight = false
	prompt.Parent = anchor

	prompt.Triggered:Connect(function(player)
		local genome = PlayerDataService.activeCreature(player)
		local profile = PlayerDataService.get(player)
		if not genome or not profile then
			return
		end
		if not (genome.abilities or {})[gate.ability] then
			Net.event("Toast"):FireClient(player, {
				kind = "gate_locked",
				title = "NOT YET",
				label = ability.emoji .. " " .. ability.display .. " required",
				sub = ability.desc,
				color = 0x8C8478,
			})
			return
		end

		profile.gatesOpened = profile.gatesOpened or {}
		if profile.gatesOpened[gate.id] then
			Net.event("Toast"):FireClient(player, {
				kind = "gate", title = "ALREADY OPEN", label = gate.success, color = 0x5FD98C,
			})
			return
		end
		profile.gatesOpened[gate.id] = true
		profile.stats.gatesOpened += 1

		for _, ingredientId in ipairs(gate.reward) do
			profile.inventory[ingredientId] = (profile.inventory[ingredientId] or 0) + 1
		end
		PlayerDataService.addCurrency(player, Economy.rewards.gateOpened)
		AnalyticsService.track("biome_unlock", player, { gate = gate.id, ability = gate.ability })

		Net.event("Toast"):FireClient(player, {
			kind = "gate",
			title = ability.emoji .. " " .. string.upper(ability.display),
			label = gate.success,
			sub = "You found something inside.",
			color = 0xFFD52E,
		})
		PlayerDataService.sync(player)

		anchor.CanCollide = false
		anchor.Transparency = 0.75
		prompt.Enabled = false
	end)
end

-- ═══ ASPIRATION (SPEC §8, 0:50) ══════════════════════════════════════════════
-- "A massive player monster walks past the edge of their plot... The player
-- understands without words: I can make THAT." On an empty server there is no such
-- player, so we stage one. No popup, no text — it simply exists, and it is huge.

local function spawnAspirationCreature(parent: Folder)
	local genome = CreatureBuilder.newGenome({ id = "aspiration-showcase", bodyFamily = "Weird" })
	genome.stage = 5
	genome.fedCount = 60
	genome.name = "???"
	genome.traits = {
		Crystal = 55, Celestial = 50, Electric = 45, Artificial = 45,
		Fire = 42, Shiny = 62, Sweet = 32, Air = 40,
	}
	local eff = CreatureBuilder.effectiveTraits(genome)
	for _, m in ipairs(Mutations.evaluate(eff, 5, {})) do
		genome.mutations[m.id] = true
	end

	local model = CreatureBuilder.build(genome, 1)
	model.Name = "AspirationCreature"
	local groundOffset = model:GetAttribute("GroundOffset") or 6
	model:PivotTo(CFrame.new(64, groundOffset, -70))
	model.Parent = parent

	-- slow patrol across the horizon of the starting plot
	task.spawn(function()
		local t = 0
		while model.Parent do
			t += 0.03
			local torso = model.PrimaryPart
			if not torso then
				break
			end
			local x = 64 + math.sin(t * 0.18) * 46
			local z = -74 + math.cos(t * 0.18) * 14
			local nextX = 64 + math.sin((t + 0.05) * 0.18) * 46
			local nextZ = -74 + math.cos((t + 0.05) * 0.18) * 14
			-- Both points MUST share a Y. Feeding lookAt a target at a different
			-- height pitches the whole creature over onto its face.
			local bobY = groundOffset + math.abs(math.sin(t * 2)) * 0.5
			torso.CFrame = CFrame.lookAt(
				Vector3.new(x, bobY, z),
				Vector3.new(nextX, bobY, nextZ))
			task.wait(0.03)
		end
	end)
	return model
end

-- ═══ BUILD ═══════════════════════════════════════════════════════════════════

function WorldService.build()
	local existing = workspace:FindFirstChild("World")
	if existing then
		existing:Destroy()
	end
	world = Instance.new("Folder")
	world.Name = "World"
	world.Parent = workspace

	local baseplate = workspace:FindFirstChild("Baseplate")
	if baseplate then
		baseplate:Destroy()
	end

	local rng = Rng.new(20260916)

	for _, biomeId in ipairs(Biomes.order) do
		local biome = Biomes.get(biomeId)
		local parent = folder(biomeId, world)

		local groundY = biome.origin[2]
		slab("Ground", Vector3.new(biome.size[1], 4, biome.size[2]),
			CFrame.new(biome.origin[1], groundY - 2, biome.origin[3]),
			biome.ground, Enum.Material.Grass, parent)

		folder("Props", parent)
		decorate(biomeId, biome, parent, rng)

		if not biome.locked then
			WorldService.topUp(biomeId)
			for _, gate in ipairs(Biomes.gatesFor(biomeId)) do
				buildGate(gate, parent)
			end
		end
	end

	-- SPEC §13: the player should glimpse the Strange Zone very early. It floats in
	-- the sky above the habitat, visible from spawn, and is not enterable yet.
	local strange = world:FindFirstChild("StrangeZone")
	if strange then
		for _, d in ipairs(strange:GetDescendants()) do
			if d:IsA("BasePart") then
				d.Material = Enum.Material.Neon
				d.Transparency = 0.25
				d.CanCollide = false
			end
		end
	end

	spawnAspirationCreature(world)

	-- SPEC §40: saturated natural world, not neon vomit.
	Lighting.ClockTime = 14.2
	Lighting.Brightness = 2.4
	Lighting.OutdoorAmbient = Color3.fromRGB(122, 130, 145)
	Lighting.ExposureCompensation = 0.12
	Lighting.GlobalShadows = true
	local atmos = Lighting:FindFirstChildOfClass("Atmosphere")
	if atmos then
		atmos.Density = 0.32
		atmos.Haze = 1.1
	end

	local spawnPoint = workspace:FindFirstChildOfClass("SpawnLocation")
	if not spawnPoint then
		spawnPoint = Instance.new("SpawnLocation")
		spawnPoint.Parent = workspace
	end
	spawnPoint.Size = Vector3.new(12, 1, 12)
	spawnPoint.CFrame = CFrame.new(0, 0.5, 26)
	spawnPoint.Anchored = true
	spawnPoint.Transparency = 1
	spawnPoint.CanCollide = false
	spawnPoint.Neutral = true

	local total = 0
	for _, n in pairs(propCounts) do
		total += n
	end
	print(string.format("[World] built %d biomes, %d ingredient props, %d gates",
		#Biomes.order, total, #Biomes.gates))
end

function WorldService.start()
	WorldService.build()
	task.spawn(function()
		while true do
			task.wait(30)
			for _, biomeId in ipairs(Biomes.order) do
				local b = Biomes.get(biomeId)
				if b and not b.locked then
					WorldService.topUp(biomeId)
				end
			end
		end
	end)
end

return WorldService
