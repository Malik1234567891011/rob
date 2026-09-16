--!strict
-- WorldService — the living layer on top of the static world. SPEC §7, §11, §13.
--
-- The world GEOMETRY is built once in edit mode by src/server/WorldBuilder.luau and saved
-- in the place (terrain, Blender kit meshes, markers). This service only reads markers:
--   Workspace.World.Biomes.<Biome>.SpawnAreas.*   ingredient pickups appear inside these
--   Workspace.World.Markers.Gate_<id>             ability gates (Config/Biomes.gates)
--   Workspace.World.Markers.Aspiration_*          the giant creature's patrol loop
-- If the world hasn't been built (fresh place, tests) a small fallback ground is made so the
-- game still runs.
--
-- SPEC §7: "the world is one giant ingredient cabinet" — anything with a Take prompt is food.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))
local Kit = require(Shared:WaitForChild("Kit"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Biomes = require(Shared.Config:WaitForChild("Biomes"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Rng = require(Shared.Util:WaitForChild("Rng"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local AnalyticsService = require(script.Parent.AnalyticsService)
local GameEvents = require(script.Parent.GameEvents)

local WorldService = {}

local RESPAWN_SECONDS = 20
local runtime: Folder
local propCounts: { [string]: number } = {}
local worldState: Folder

local function world(): Instance?
	return workspace:FindFirstChild("World")
end

local function updateLevel(): number
	return worldState and worldState:GetAttribute("UpdateLevel") or 0
end

-- ═══ INFLUENCE TEXT (SPEC §45) ═══════════════════════════════════════════════

function WorldService.describeInfluence(def, detailed: boolean): string
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

-- ═══ PICKUPS ═════════════════════════════════════════════════════════════════

local function backpackCount(profile): number
	local n = 0
	for _, c in pairs(profile.inventory) do
		n += c
	end
	return n
end

local function capacity(player: Player): number
	local ok, M = pcall(require, script.Parent.MonetizationService)
	return ok and M.backpackCapacity and M.backpackCapacity(player) or 120
end

function WorldService.take(player: Player, ingredientId: string, biomeId: string): boolean
	local profile = PlayerDataService.get(player)
	local def = Ingredients.get(ingredientId)
	if not profile or not def then
		return false
	end
	if backpackCount(profile) >= capacity(player) then
		Net.event("Toast"):FireClient(player, { kind = "full", title = "BAG IS FULL", label = "🎒 Feed your monster first!", color = 0xEC6060 })
		return false
	end
	PlayerDataService.give(player, ingredientId, 1)
	AnalyticsService.track("ingredient_pickup", player, { ingredient = ingredientId, biome = biomeId })
	if not profile.pickedFirst then
		profile.pickedFirst = true
		AnalyticsService.track("ftue_first_food_pickup", player, { ingredient = ingredientId })
	end
	GameEvents.fire(player, "pickup", { ingredient = ingredientId, biome = biomeId })

	-- SPEC §19/§53: friends help you find things. A party member standing close sometimes
	-- spots another one of the same thing.
	local okP, Party = pcall(require, script.Parent.PartyService)
	if okP and Party.members then
		local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		for _, m in ipairs(Party.members(player)) do
			local mh = m ~= player and m.Character and m.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
			if hrp and mh and (mh.Position - hrp.Position).Magnitude < 30 and math.random() < 0.25 then
				PlayerDataService.give(m, ingredientId, 1)
				Net.event("Toast"):FireClient(m, { kind = "pickup", title = "YOUR FRIEND FOUND ONE", label = def.emoji .. " " .. def.display, color = 0x6EA8FF })
				PlayerDataService.sync(m)
			end
		end
	end

	Net.event("Toast"):FireClient(player, {
		kind = "pickup", title = "PICKED UP", label = def.emoji .. " " .. def.display,
		sub = WorldService.describeInfluence(def, profile.detailMode), color = Ingredients.rarityColor[def.rarity],
	})
	PlayerDataService.sync(player)
	return true
end

local function spawnAreas(biomeId: string): { BasePart }
	local w = world()
	local b = w and w:FindFirstChild("Biomes")
	local folder = b and b:FindFirstChild(biomeId)
	local areas = folder and folder:FindFirstChild("SpawnAreas")
	local out = {}
	for _, p in ipairs(areas and areas:GetChildren() or {}) do
		if p:IsA("BasePart") then
			table.insert(out, p)
		end
	end
	return out
end

local groundParams = RaycastParams.new()
groundParams.FilterType = Enum.RaycastFilterType.Exclude

local function randomGroundPoint(biomeId: string, rng): Vector3?
	local areas = spawnAreas(biomeId)
	local biome = Biomes.get(biomeId)
	for _ = 1, 8 do
		local origin
		if #areas > 0 then
			local a = areas[rng:int(1, #areas)]
			local local_ = Vector3.new(rng:num(-0.5, 0.5) * a.Size.X, a.Size.Y * 0.5, rng:num(-0.5, 0.5) * a.Size.Z)
			origin = a.CFrame:PointToWorldSpace(local_)
		elseif biome then
			local ang = rng:num(0, math.pi * 2)
			local r = math.sqrt(rng:num(0, 1)) * biome.radius * 0.85
			origin = Vector3.new(biome.center[1] + math.cos(ang) * r, 60, biome.center[3] + math.sin(ang) * r)
		else
			return nil
		end
		groundParams.FilterDescendantsInstances = { runtime, workspace:FindFirstChild("Creatures") }
		local hit = workspace:Raycast(origin + Vector3.new(0, 40, 0), Vector3.new(0, -200, 0), groundParams)
		if hit and hit.Material ~= Enum.Material.Water and hit.Normal.Y > 0.7 then
			return hit.Position
		end
	end
	return nil
end

local function spawnProp(biomeId: string, ingredientId: string, position: Vector3)
	local model = PropBuilder.build(ingredientId)
	if not model then
		return nil
	end
	local def = Ingredients.get(ingredientId)
	local extents = model:GetExtentsSize()
	local s = math.clamp(1.8 / math.max(extents.X, extents.Y, extents.Z), 0.4, 1.6)
	if math.abs(s - 1) > 0.05 then
		model:ScaleTo(s)
	end
	extents = model:GetExtentsSize()
	model:PivotTo(CFrame.new(position + Vector3.new(0, extents.Y * 0.5 + 0.05, 0)) * CFrame.Angles(0, math.random() * 6.28, 0))
	model:SetAttribute("Biome", biomeId)
	model.Parent = runtime
	CollectionService:AddTag(model, "Pickup")

	local main = model.PrimaryPart or model:FindFirstChildWhichIsA("BasePart")
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Take"
	prompt.ObjectText = def.emoji .. " " .. def.display
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 11
	prompt.RequiresLineOfSight = false
	prompt.Parent = main
	prompt.Triggered:Connect(function(player)
		if not model.Parent then
			return
		end
		if WorldService.take(player, ingredientId, biomeId) then
			model:Destroy()
			propCounts[biomeId] = math.max(0, (propCounts[biomeId] or 1) - 1)
			task.delay(RESPAWN_SECONDS, WorldService.topUp, biomeId)
		end
	end)
	propCounts[biomeId] = (propCounts[biomeId] or 0) + 1
	return model
end

function WorldService.topUp(biomeId: string)
	local biome = Biomes.get(biomeId)
	if not biome or biome.locked or biome.maxProps <= 0 then
		return
	end
	if biome.update and updateLevel() < biome.update then
		return
	end
	local okD, Daily = pcall(require, script.Parent.DailyService)
	local rng = Rng.new()
	local have = propCounts[biomeId] or 0
	for _ = 1, math.max(0, biome.maxProps - have) do
		-- weighted by today's Ingredient of the Day and weather (SPEC §47)
		local pool = {}
		for _, id in ipairs(biome.spawnTable) do
			local w = okD and Daily.spawnWeight and Daily.spawnWeight(id) or 1
			table.insert(pool, { id = id, weight = w })
		end
		local pick = rng:weighted(pool)
		local pos = randomGroundPoint(biomeId, rng)
		if pos then
			spawnProp(biomeId, pick.id, pos)
		end
	end
end

-- ═══ GATES (SPEC §11, §20) ═══════════════════════════════════════════════════

local function gateMarker(id: string): BasePart?
	local w = world()
	local m = w and w:FindFirstChild("Markers")
	return m and m:FindFirstChild("Gate_" .. id) :: BasePart?
end

local gatesById: { [string]: any } = {}

-- The one gate rule, used by the world prompt AND Net TryGate (and tests).
-- Returns { ok, opened?, already?, missing? }.
function WorldService.tryGate(player: Player, gateId: string)
	local gate = gatesById[gateId]
	local marker = gateMarker(gateId)
	if not gate or not marker then
		return { ok = false, reason = "no such gate" }
	end
	if gate.update and updateLevel() < gate.update then
		return { ok = false, reason = "not yet released" }
	end
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false, reason = "no profile" }
	end
	profile.gatesOpened = profile.gatesOpened or {}
	if profile.gatesOpened[gate.id] then
		Net.event("Toast"):FireClient(player, { kind = "gate", title = "ALREADY FOUND", label = gate.success, color = 0x5FD98C })
		Net.event("WorldNotice"):FireClient(player, { kind = "gate_open", gate = gate.id, instant = true })
		return { ok = true, already = true }
	end
	local have: { [string]: boolean } = {}
	local helpers: { Player } = {}
	if gate.coop then
		local okP, Party = pcall(require, script.Parent.PartyService)
		if okP then
			have, helpers = Party.abilitiesNear(player, marker.Position, 30)
		end
	else
		local g = PlayerDataService.activeCreature(player)
		have = g and g.abilities or {}
	end
	local missing = {}
	for _, a in ipairs(gate.abilities) do
		if not have[a] then
			local def = Mutations.abilities[a]
			table.insert(missing, def and (def.emoji .. " " .. def.display) or a)
		end
	end
	if #missing > 0 then
		Net.event("Toast"):FireClient(player, {
			kind = "gate_locked", title = gate.coop and "NEEDS A TEAM" or "NOT YET",
			label = gate.prompt,
			sub = "Needs " .. table.concat(missing, " + ") .. (gate.coop and " (party members nearby count!)" or ""),
			color = 0x8C8478,
		})
		return { ok = false, reason = "missing", missing = missing }
	end
	local recipients = { player }
	for _, h in ipairs(helpers) do
		table.insert(recipients, h)
	end
	for _, p in ipairs(recipients) do
		local prof = PlayerDataService.get(p)
		if prof and not (prof.gatesOpened or {})[gate.id] then
			prof.gatesOpened = prof.gatesOpened or {}
			prof.gatesOpened[gate.id] = true
			PlayerDataService.stat(p, "gatesOpened")
			for _, ingredientId in ipairs(gate.reward) do
				PlayerDataService.give(p, ingredientId, 1)
			end
			PlayerDataService.addCurrency(p, gate.coop and Economy.rewards.partyGate or Economy.rewards.gateOpened)
			AnalyticsService.track("biome_unlock", p, { gate = gate.id, coop = gate.coop == true })
			GameEvents.fire(p, "gate_opened", { gate = gate.id, coop = gate.coop == true })
			Net.event("Toast"):FireClient(p, {
				kind = "gate", title = gate.coop and "🤝 TEAMWORK" or "OPENED",
				label = gate.success, sub = "You found something inside.", color = 0xFFD52E,
			})
			Net.event("WorldNotice"):FireClient(p, { kind = "gate_open", gate = gate.id })
			PlayerDataService.sync(p)
		end
	end
	return { ok = true, opened = true, helpers = #helpers }
end

local function buildGate(gate)
	gatesById[gate.id] = gate
	local marker = gateMarker(gate.id)
	if not marker then
		return
	end
	if gate.update and updateLevel() < gate.update then
		return
	end
	local abilityNames = {}
	for _, a in ipairs(gate.abilities) do
		local def = Mutations.abilities[a]
		table.insert(abilityNames, def and (def.emoji .. " " .. def.display) or a)
	end
	local prompt = Instance.new("ProximityPrompt")
	prompt.Name = "GatePrompt"
	prompt.ActionText = gate.coop and "Team up" or "Try"
	prompt.ObjectText = table.concat(abilityNames, " + ")
	prompt.HoldDuration = 0.4
	prompt.MaxActivationDistance = 16
	prompt.RequiresLineOfSight = false
	prompt:SetAttribute("Gate", gate.id)
	prompt.Parent = marker

	prompt.Triggered:Connect(function(player)
		WorldService.tryGate(player, gate.id)
	end)
end

-- ═══ BIOME ENTRY (SPEC §64 biome_enter) ══════════════════════════════════════

local lastBiome: { [number]: string } = {}
local function biomeCheck()
	for _, p in ipairs(Players:GetPlayers()) do
		local hrp = p.Character and p.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if hrp then
			local here = nil
			for _, id in ipairs(Biomes.order) do
				local b = Biomes.get(id)
				if b and b.radius > 0 then
					local dx, dz = hrp.Position.X - b.center[1], hrp.Position.Z - b.center[3]
					if dx * dx + dz * dz < b.radius * b.radius and math.abs(hrp.Position.Y - b.center[2]) < 120 then
						here = id
					end
				end
			end
			if here and lastBiome[p.UserId] ~= here then
				lastBiome[p.UserId] = here
				p:SetAttribute("Biome", here)
				AnalyticsService.track("biome_enter", p, { biome = here })
				GameEvents.fire(p, "biome_enter", { biome = here })
			end
		end
	end
end

-- ═══ ASPIRATION (SPEC §8, 0:50) ══════════════════════════════════════════════
-- "A massive player monster walks past the plot edge... No popup." On an empty server
-- there is no such player, so one patrols the road ring every plot can see.

local function spawnAspirationCreature()
	local genome = CreatureBuilder.newGenome({ id = "aspiration-showcase", bodyFamily = "Heavy" })
	genome.stage = 5
	genome.fedCount = 60
	genome.name = "???"
	genome.traits = { Crystal = 55, Celestial = 50, Electric = 45, Artificial = 45, Fire = 42, Shiny = 62, Sweet = 32, Air = 40 }
	local eff = CreatureBuilder.effectiveTraits(genome)
	for _, m in ipairs(Mutations.evaluate(eff, 5, {})) do
		genome.mutations[m.id] = true
	end
	local ok, model = pcall(CreatureBuilder.build, genome, 1)
	if not ok then
		warn("[World] aspiration creature failed: " .. tostring(model))
		return
	end
	model.Name = "AspirationCreature"
	local groundOffset = model:GetAttribute("GroundOffset") or 0
	model.Parent = runtime
	CollectionService:AddTag(model, "FAMCreature")
	task.spawn(function()
		local CreatureService = require(script.Parent.CreatureService)
		local t = 0
		local R = 140 -- the road ring between the hub and the plots
		while model.Parent do
			t += 0.03
			local root = model.PrimaryPart
			if not root then
				break
			end
			local a = t * 0.012
			local x, z = math.cos(a) * R, math.sin(a) * R
			local nx, nz = math.cos(a + 0.01) * R, math.sin(a + 0.01) * R
			local y = CreatureService.groundAt(x, z, 20) + groundOffset
			root.CFrame = CFrame.lookAt(Vector3.new(x, y, z), Vector3.new(nx, y, nz))
			task.wait(0.03)
		end
	end)
end

-- ═══ FALLBACK GROUND (unbuilt place / tests) ═════════════════════════════════

local function ensureGround()
	if world() then
		return
	end
	warn("[World] Workspace.World not built — creating fallback ground. Run tools/studio/build_world.luau in edit mode.")
	local f = Instance.new("Folder")
	f.Name = "World"
	f.Parent = workspace
	local p = Instance.new("Part")
	p.Name = "FallbackGround"
	p.Anchored = true
	p.Size = Vector3.new(1400, 4, 1400)
	p.CFrame = CFrame.new(0, -2, 0)
	p.Color = Color3.fromRGB(110, 178, 88)
	p.Material = Enum.Material.Grass
	p.Parent = f
	local spawn = workspace:FindFirstChildOfClass("SpawnLocation") or Instance.new("SpawnLocation")
	spawn.Anchored = true
	spawn.Transparency = 1
	spawn.CanCollide = false
	spawn.CFrame = CFrame.new(0, 0.5, 30)
	spawn.Parent = workspace
	Lighting.Brightness = 2.4
end

function WorldService.start()
	worldState = ReplicatedStorage:FindFirstChild("WorldState") :: Folder
	if not worldState then
		worldState = Instance.new("Folder")
		worldState.Name = "WorldState"
		worldState.Parent = ReplicatedStorage
	end
	ensureGround()
	local baseplate = workspace:FindFirstChild("Baseplate")
	if baseplate then
		baseplate:Destroy()
	end
	runtime = Instance.new("Folder")
	runtime.Name = "WorldRuntime"
	runtime.Parent = workspace

	for _, gate in ipairs(Biomes.gates) do
		buildGate(gate)
	end
	-- Update 1: the Ocean opens the moment UpdateLevel reaches 1 (no server restart needed)
	local function oceanLock()
		local w = world()
		local lock = w and w:FindFirstChild("OceanLock", true)
		if lock and updateLevel() >= 1 then
			lock:Destroy()
			for _, gate in ipairs(Biomes.gates) do
				if gate.update and not (gateMarker(gate.id) and gateMarker(gate.id):FindFirstChild("GatePrompt")) then
					buildGate(gate)
				end
			end
			WorldService.topUp("Ocean")
		end
	end
	if worldState then
		worldState:GetAttributeChangedSignal("UpdateLevel"):Connect(oceanLock)
	end
	oceanLock()
	Net.func("TryGate").OnServerInvoke = function(player, gateId)
		if typeof(gateId) ~= "string" then
			return { ok = false, reason = "bad gate" }
		end
		return WorldService.tryGate(player, gateId)
	end
	for _, id in ipairs(Biomes.order) do
		WorldService.topUp(id)
	end
	spawnAspirationCreature()

	task.spawn(function()
		while true do
			task.wait(25)
			for _, id in ipairs(Biomes.order) do
				WorldService.topUp(id)
			end
		end
	end)
	task.spawn(function()
		while true do
			task.wait(2)
			biomeCheck()
		end
	end)
	Players.PlayerRemoving:Connect(function(p)
		lastBiome[p.UserId] = nil
	end)

	local total = 0
	for _, n in pairs(propCounts) do
		total += n
	end
	print(string.format("[World] live: %d ingredient props, %d gates, %d kit meshes available", total, #Biomes.gates, #Kit.names()))
end

return WorldService
