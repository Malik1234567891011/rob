--!strict
-- WorldBuilder — builds the whole static world ONCE, in edit mode, and it is saved in the
-- place. Never runs during play. Re-running rebuilds deterministically (seeded RNG).
--
-- Run from the MCP edit thread with the require shim (tools/studio/shim.luau):
--   local WB = req(game.ServerScriptService.WorldBuilder)
--   WB.clear(); WB.terrain(); WB.hub(); WB.plots(); WB.meadow(); ...
-- (split into steps so no single call runs too long)
--
-- SPEC §13 hub + biome islands; §8 the backyard; §40 "beautiful lighting, saturated natural
-- world, not neon vomit"; §42 "a tree can look mediocre" — ours don't, but trees stay cheap:
-- instanced kit meshes, box collision.
--
-- Everything runtime needs is a MARKER (invisible part) with a stable name:
--   World.Markers.Travel_<Place> · Gate_<id> · EventSpot_<Area>_n · QuakeSeal
--   World.Hub.Markers.ParadeStart / ParadeEnd · World.Plots.Plot_n.Center
--   World.Biomes.<Biome>.SpawnAreas.* · World.Trials.<Trial>.Markers.*

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Kit = require(Shared:WaitForChild("Kit"))
local Biomes = require(Shared.Config:WaitForChild("Biomes"))
local Sanctuary = require(Shared.Config:WaitForChild("Sanctuary"))
local WorldTerrain = require(script.Parent:WaitForChild("WorldTerrain"))

local WorldBuilder = {}

local T = workspace.Terrain
local rng = Random.new(20260916)
local world: Folder

local M = Enum.Material

-- ═══ HELPERS ═════════════════════════════════════════════════════════════════

local function folder(name: string, parent: Instance): Folder
	local f = parent:FindFirstChild(name)
	if f then
		return f :: Folder
	end
	local nf = Instance.new("Folder")
	nf.Name = name
	nf.Parent = parent
	return nf
end

local function getWorld(): Folder
	world = workspace:FindFirstChild("World") :: Folder
	if not world then
		world = Instance.new("Folder")
		world.Name = "World"
		world.Parent = workspace
	end
	return world
end

local function marker(name: string, cf: CFrame, parent: Instance, size: Vector3?): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Transparency = 1
	p.Size = size or Vector3.new(2, 2, 2)
	p.CFrame = cf
	p.Parent = parent
	return p
end

local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Include

-- Rays start at `rayFrom`. Inside the cave it is set BELOW the cavern ceiling, otherwise
-- every crystal lands on top of the mountain instead of on the cavern floor.
local rayFrom = 320

-- height of TERRAIN only at (x, z)
local function ground(x: number, z: number, fromY: number?): number
	params.FilterDescendantsInstances = { T }
	local hit = workspace:Raycast(Vector3.new(x, (fromY or rayFrom), z), Vector3.new(0, -600, 0), params)
	return hit and hit.Position.Y or 0
end

local function groundHit(x: number, z: number, fromY: number?): RaycastResult?
	params.FilterDescendantsInstances = { T }
	return workspace:Raycast(Vector3.new(x, (fromY or rayFrom), z), Vector3.new(0, -600, 0), params)
end

-- tiny decor is pure dressing: no shadows (hundreds of them), never hit by rays or touches
local SMALL_DECOR = { "GrassTuft", "FlowerPatch", "Reeds", "LilyPad", "GlowMushroom", "Rock_Small", "Pebble", "Tire_Single", "Crate_B" }
local function isSmallDecor(name: string): boolean
	for _, k in ipairs(SMALL_DECOR) do
		if string.find(name, k, 1, true) then
			return true
		end
	end
	return false
end

local function place(name: string, x: number, z: number, yaw: number?, parent: Instance, scale: number?, y: number?, opts: any?)
	local gy = y or ground(x, z)
	local o = opts or {}
	o.scale = scale
	if isSmallDecor(name) then
		o.castShadow = false
		o.query = false
	end
	return Kit.place(name, CFrame.new(x, gy, z) * CFrame.Angles(0, math.rad(yaw or rng:NextNumber(0, 360)), 0), parent, o)
end

local function faceCF(pos: Vector3, lookAt: Vector3): CFrame
	local flat = Vector3.new(lookAt.X, pos.Y, lookAt.Z)
	if (flat - pos).Magnitude < 0.01 then
		return CFrame.new(pos)
	end
	return CFrame.lookAt(pos, flat)
end

-- keep-out circles so scatter never lands on roads, plots, gates or ponds
local keepOut: { { x: number, z: number, r: number } } = {}
local function reserve(x: number, z: number, r: number)
	table.insert(keepOut, { x = x, z = z, r = r })
end
local function free(x: number, z: number, r: number): boolean
	for _, k in ipairs(keepOut) do
		local dx, dz = x - k.x, z - k.z
		if dx * dx + dz * dz < (k.r + r) ^ 2 then
			return false
		end
	end
	return true
end

local function onRoad(x: number, z: number): boolean
	return WorldTerrain.isPaved(x, z, 3)
end

-- scatter kit meshes in a disc or box, on grass, away from reserved spots
-- why scatter attempts fail, so an empty area can be diagnosed instead of guessed at
WorldBuilder.rejects = { taken = 0, paved = 0, noHit = 0, steep = 0, water = 0, material = 0, noAsset = 0, placed = 0 }

local function scatter(names: { string }, count: number, cx: number, cz: number, radius: number, parent: Instance, minGap: number, scaleRange: { number }?, materials: { Enum.Material }?)
	local R = WorldBuilder.rejects
	local placed = 0
	local tries = 0
	while placed < count and tries < count * 12 do
		tries += 1
		local a = rng:NextNumber(0, math.pi * 2)
		local r = math.sqrt(rng:NextNumber()) * radius
		local x, z = cx + math.cos(a) * r, cz + math.sin(a) * r
		if not free(x, z, minGap) then
			R.taken += 1
		elseif WorldTerrain.isPaved(x, z, math.max(2, minGap * 0.5)) then
			R.paved += 1
		else
			local hit = groundHit(x, z)
			if not hit then
				R.noHit += 1
			elseif hit.Normal.Y <= 0.82 then
				R.steep += 1
			elseif hit.Material == M.Water then
				R.water += 1
			elseif materials and not table.find(materials, hit.Material) then
				R.material += 1
			else
				local s = scaleRange and rng:NextNumber(scaleRange[1], scaleRange[2]) or 1
				local m = place(names[rng:NextInteger(1, #names)], x, z, nil, parent, s, hit.Position.Y - 0.15)
				if m then
					placed += 1
					R.placed += 1
					if minGap > 2 then
						reserve(x, z, minGap * 0.6)
					end
				else
					R.noAsset += 1
				end
			end
		end
	end
	return placed
end

-- groves and clearings instead of an even polka-dot: pick cluster centres, fill around them
local function grove(names: { string }, clusters: number, perCluster: number, cx: number, cz: number, radius: number, spread: number, parent: Instance, minGap: number, scaleRange: { number }?, materials: { Enum.Material }?)
	local placed = 0
	for _ = 1, clusters do
		local a = rng:NextNumber(0, math.pi * 2)
		local r = math.sqrt(rng:NextNumber()) * radius
		local gx, gz = cx + math.cos(a) * r, cz + math.sin(a) * r
		if not WorldTerrain.isPaved(gx, gz, spread * 0.4) then
			placed += scatter(names, rng:NextInteger(math.max(1, perCluster - 2), perCluster + 2), gx, gz, spread, parent, minGap, scaleRange, materials)
		end
	end
	return placed
end

-- walk a polyline, calling fn(x, z, dirX, dirZ) every `step` studs
local function alongRoad(pts: { { number } }, step: number, startAt: number, fn: (number, number, number, number, number) -> ())
	local travelled, nextAt, n = 0, startAt, 0
	for i = 1, #pts - 1 do
		local ax, az, bx, bz = pts[i][1], pts[i][2], pts[i + 1][1], pts[i + 1][2]
		local len = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
		local dx, dz = (bx - ax) / len, (bz - az) / len
		while nextAt <= travelled + len do
			local t = nextAt - travelled
			n += 1
			fn(ax + dx * t, az + dz * t, dx, dz, n)
			nextAt += step
		end
		travelled += len
	end
end

local function spawnArea(biome: string, cf: CFrame, size: Vector3)
	local b = folder(biome, folder("Biomes", world))
	marker("Area", cf, folder("SpawnAreas", b), size)
end

local function tagCollider(tag: string, cf: CFrame, size: Vector3, parent: Instance, visible: boolean?, color: Color3?, material: Enum.Material?): Part
	local p = Instance.new("Part")
	p.Name = tag
	p.Anchored = true
	p.CanCollide = tag ~= "DarkZone" and tag ~= "DeepWater" and tag ~= "HotGround"
	p.CanQuery = false
	p.Transparency = visible and 0.35 or 1
	p.Size = size
	p.CFrame = cf
	if color then
		p.Color = color
	end
	p.Material = material or M.SmoothPlastic
	p.Parent = parent
	CollectionService:AddTag(p, tag)
	return p
end

-- ═══ CLEAR ═══════════════════════════════════════════════════════════════════

function WorldBuilder.clear()
	local w = workspace:FindFirstChild("World")
	if w then
		w:Destroy()
	end
	T:Clear()
	keepOut = {}
	rayFrom = 320
	rng = Random.new(20260916)
	for _, n in ipairs({ "Baseplate", "PreviewStage", "LookTest" }) do
		local x = workspace:FindFirstChild(n)
		if x then
			x:Destroy()
		end
	end
	getWorld()
	return "cleared"
end

-- props only: keeps the (slow to write) terrain, rebuilds everything placed on it
function WorldBuilder.clearProps()
	local w = workspace:FindFirstChild("World")
	if w then
		w:Destroy()
	end
	keepOut = {}
	rayFrom = 320
	rng = Random.new(20260916)
	for k in pairs(WorldBuilder.rejects) do
		WorldBuilder.rejects[k] = 0
	end
	getWorld()
	return "props cleared"
end

-- ═══ TERRAIN + LIGHTING ══════════════════════════════════════════════════════

function WorldBuilder.terrain(bandFrom: number?, bandTo: number?)
	getWorld()
	-- saturated but natural (SPEC §40)
	T:SetMaterialColor(M.Grass, Color3.fromRGB(104, 176, 72))
	T:SetMaterialColor(M.LeafyGrass, Color3.fromRGB(96, 164, 70))
	T:SetMaterialColor(M.Ground, Color3.fromRGB(160, 124, 88))
	T:SetMaterialColor(M.Sand, Color3.fromRGB(206, 176, 124))
	T:SetMaterialColor(M.Rock, Color3.fromRGB(122, 130, 150))
	T:SetMaterialColor(M.Slate, Color3.fromRGB(88, 94, 118))
	T:SetMaterialColor(M.Cobblestone, Color3.fromRGB(168, 156, 142))
	T:SetMaterialColor(M.Mud, Color3.fromRGB(96, 76, 60))
	T:SetMaterialColor(M.Asphalt, Color3.fromRGB(96, 94, 100))
	T:SetMaterialColor(M.Basalt, Color3.fromRGB(70, 64, 86))
	T:SetMaterialColor(M.CrackedLava, Color3.fromRGB(255, 120, 40))
	T.WaterColor = Color3.fromRGB(38, 128, 150)
	T.WaterTransparency = 0.4
	T.WaterWaveSize = 0.15
	T.WaterWaveSpeed = 9
	T.WaterReflectance = 0.45
	pcall(function()
		(T :: any).Decoration = true -- grass decoration; not scriptable in every context
	end)

	-- the island is one height function (WorldTerrain), written in bands so no single call
	-- runs too long. `terrain(from, to)` writes a subset; `terrain()` writes all of it.
	if not bandFrom or bandFrom == 0 then
		WorldTerrain.sea()
	end
	local nb = WorldTerrain.bands()
	for band = bandFrom or 0, math.min(bandTo or (nb - 1), nb - 1) do
		WorldTerrain.writeBand(band)
	end
	reserve(0, 0, 66)

	-- lighting (SPEC §40 "beautiful lighting")
	-- some Lighting properties are not writable from every script context (Technology needs
	-- to be set by hand in Studio: Lighting > Technology = Future)
	local function set(obj: Instance, prop: string, value: any)
		pcall(function()
			(obj :: any)[prop] = value
		end)
	end
	set(Lighting, "Technology", Enum.Technology.Future)
	set(Lighting, "Brightness", 2.6)
	set(Lighting, "EnvironmentDiffuseScale", 1)
	set(Lighting, "EnvironmentSpecularScale", 1)
	set(Lighting, "OutdoorAmbient", Color3.fromRGB(128, 132, 150))
	set(Lighting, "Ambient", Color3.fromRGB(60, 60, 72))
	set(Lighting, "ShadowSoftness", 0.25)
	set(Lighting, "GeographicLatitude", 30)
	set(Lighting, "ExposureCompensation", 0.1)
	local atmos = Lighting:FindFirstChildOfClass("Atmosphere") or Instance.new("Atmosphere")
	atmos.Density = 0.3
	atmos.Offset = 0.12
	atmos.Color = Color3.fromRGB(206, 224, 240)
	atmos.Decay = Color3.fromRGB(120, 150, 190)
	atmos.Glare = 0.2
	atmos.Haze = 1.2
	atmos.Parent = Lighting
	local rays = Lighting:FindFirstChildOfClass("SunRaysEffect") or Instance.new("SunRaysEffect")
	rays.Intensity = 0.06
	rays.Spread = 0.8
	rays.Parent = Lighting
	local clouds = T:FindFirstChildOfClass("Clouds") or Instance.new("Clouds")
	clouds.Cover = 0.55
	clouds.Density = 0.6
	clouds.Color = Color3.fromRGB(255, 255, 255)
	clouds.Parent = T
	return "terrain ok"
end

-- ═══ HUB ═════════════════════════════════════════════════════════════════════

function WorldBuilder.hub()
	getWorld()
	local hub = folder("Hub", world)
	local hm = folder("Markers", hub)
	local markers = folder("Markers", world)
	local center = Vector3.new(0, 0, 0)

	place("Fountain", 0, 0, 0, hub)
	-- parade runway runs north from the square
	place("Parade_Runway", 0, -60, 0, hub)
	place("Parade_Arch", 0, -38, 0, hub)
	marker("ParadeStart", CFrame.new(0, ground(0, -42) + 1.8, -42), hm)
	marker("ParadeEnd", CFrame.new(0, ground(0, -77) + 1.8, -77), hm)
	reserve(0, -60, 26)
	for i = 0, 3 do
		place("Bench_Park", i % 2 == 0 and -12 or 12, -48 - i * 9, i % 2 == 0 and 270 or 90, hub)
	end

	local function facing(name: string, x: number, z: number, parent: Instance, scale: number?)
		local gy = ground(x, z)
		return Kit.place(name, faceCF(Vector3.new(x, gy, z), center), parent, { scale = scale })
	end
	facing("Research_Board", 40, -20, hub)
	facing("Quest_Board", -40, -20, hub)
	local stall = facing("Market_Stall", 42, 26, hub)
	if stall then
		stall.Name = "Merchant"
	end
	local portal = facing("Portal_Arch", -44, 28, hub)
	local disc = facing("Portal_Disc", -44, 28, hub)
	if disc then
		disc.Name = "TrialsPortal"
		CollectionService:AddTag(disc, "Spin")
		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Creature Trials"
		prompt.ObjectText = "🏁"
		prompt.HoldDuration = 0
		prompt.MaxActivationDistance = 14
		prompt.RequiresLineOfSight = false
		prompt:SetAttribute("OpenPanel", "Trials")
		prompt.Parent = disc.PrimaryPart
	end
	local _p = portal
	for _, spot in ipairs({ { 40, -20 }, { -40, -20 }, { 42, 26 }, { -44, 28 } }) do
		reserve(spot[1], spot[2], 12)
	end
	marker("Travel_Hub", CFrame.new(0, ground(0, 34) + 1, 34), markers)
	marker("TrialReturn", CFrame.new(-36, ground(-36, 22) + 2, 22), markers)

	-- lamp ring, bunting between lamps, benches, planters, balloons
	local lamps = {}
	for i = 0, 7 do
		local a = (i + 0.5) / 8 * math.pi * 2
		local x, z = math.cos(a) * 56, math.sin(a) * 56
		place("Lamp_Post", x, z, -math.deg(a), hub)
		table.insert(lamps, Vector3.new(x, 0, z))
		reserve(x, z, 3)
	end
	for i = 1, #lamps do
		local a, b = lamps[i], lamps[(i % #lamps) + 1]
		local mid = (a + b) / 2
		local gy = ground(mid.X, mid.Z) + 6.4
		Kit.place("Bunting_Span", CFrame.lookAt(Vector3.new(mid.X, gy, mid.Z), Vector3.new(b.X, gy, b.Z)) * CFrame.Angles(0, math.rad(90), 0), hub, { collide = false })
	end
	for i = 0, 5 do
		local a = i / 6 * math.pi * 2 + 0.3
		place("Planter_Box", math.cos(a) * 30, math.sin(a) * 30, -math.deg(a), hub)
	end
	place("Balloon_Cluster", 18, 20, nil, hub)
	place("Balloon_Cluster", -20, 16, nil, hub)
	place("Tent_Striped", 58, -44, 225, hub)
	place("Tent_Striped", -58, -46, 135, hub)
	-- three pedestals: the research board's "largest creature" and friends pose here
	for i = -1, 1 do
		place("Statue_Pedestal", i * 9, 22, 180, hub)
	end
	for i = 1, 4 do
		local ex, ez = math.cos(i * 1.57) * 34, math.sin(i * 1.57) * 34
		marker("EventSpot_Hub_" .. i, CFrame.new(ex, ground(ex, ez) + 1, ez), markers)
	end
	-- the park between the square and the ring road: four quarter-gardens between the roads,
	-- each a little grove with flower beds, so the walk to your plot is never bare lawn
	for q = 0, 3 do
		local a = math.rad(45 + q * 90)
		local gx, gz = math.cos(a) * 100, math.sin(a) * 100
		scatter({ "Tree_Puffy_A", "Tree_Puffy_B", "Tree_Fruit" }, 5, gx, gz, 26, hub, 9, { 0.9, 1.15 })
		scatter({ "Bush_A", "Bush_B", "Bush_C" }, 8, gx, gz, 34, hub, 4, { 0.8, 1.2 })
		for k = 0, 2 do
			local fa = a + (k - 1) * 0.28
			scatter({ "FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "FlowerPatch_White" }, 7, math.cos(fa) * 76, math.sin(fa) * 76, 7, hub, 1.2, { 1.0, 1.4 })
		end
		place("Bench_Wood", math.cos(a) * 72, math.sin(a) * 72, -math.deg(a) + 90, hub)
	end
	scatter({ "GrassTuft_A", "GrassTuft_B" }, 70, 0, 0, 130, hub, 1.5)
	-- lamps and signposts along the four main roads, out to each biome
	for _, road in ipairs(WorldTerrain.roads) do
		if road.half >= 6 then
			alongRoad(road.pts, 36, 30, function(x, z, dx, dz, n)
				local side = (n % 2 == 0) and 1 or -1
				local lx, lz = x - dz * 10 * side, z + dx * 10 * side
				if not WorldTerrain.plotAt(lx, lz, 3) and math.sqrt(lx * lx + lz * lz) > 70 then
					place("Lamp_Post", lx, lz, math.deg(math.atan2(dx, dz)), hub)
					reserve(lx, lz, 3)
				end
			end)
		end
	end
	spawnArea("Hub", CFrame.new(0, 4, 40), Vector3.new(60, 6, 20))
	return "hub ok"
end

-- ═══ PLOTS (SPEC §16) ════════════════════════════════════════════════════════

function WorldBuilder.plots()
	getWorld()
	local plots = folder("Plots", world)
	for i = 1, Sanctuary.MAX_PLOTS do
		local a = math.rad(15 + (i - 1) * 30)
		local pos = Vector3.new(math.cos(a) * 205, 0, math.sin(a) * 205)
		local gy = ground(pos.X, pos.Z)
		local facingHub = CFrame.lookAt(Vector3.new(pos.X, gy, pos.Z), Vector3.new(0, gy, 0))
		local plot = folder("Plot_" .. i, plots)
		-- the Center's BASE is the plot's ground level (SanctuaryService builds from it)
		local c = marker("Center", CFrame.new(pos.X, gy + 0.5, pos.Z) * facingHub.Rotation, plot, Vector3.new(4, 1, 4))
		c:SetAttribute("Plot", i)
		reserve(pos.X, pos.Z, 48)
		-- a lot you can read as "a place" even before anyone moves in: lanterns at the gate,
		-- a flower border along the front, round bushes on the back corners, trees behind
		for _, off in ipairs({ { -9, -33 }, { 9, -33 } }) do
			local wp = facingHub * CFrame.new(off[1], 0, off[2])
			Kit.place("Lantern_Post", CFrame.new(wp.X, ground(wp.X, wp.Z), wp.Z) * facingHub.Rotation, plot)
		end
		for k = -3, 3 do
			if math.abs(k) > 0 then
				local wp = facingHub * CFrame.new(k * 8 + (k > 0 and 2 or -2), 0, -34)
				place(({ "FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "FlowerPatch_White" })[(k + 4) % 4 + 1], wp.X, wp.Z, nil, plot, 1.3, nil, { query = false })
			end
		end
		for _, off in ipairs({ { -31, 31 }, { 31, 31 }, { -31, -2 }, { 31, -2 } }) do
			local wp = facingHub * CFrame.new(off[1], 0, off[2])
			place(math.abs(off[2]) > 10 and "Bush_B" or "Bush_A", wp.X, wp.Z, nil, plot, 1.15)
		end
		for _, off in ipairs({ { -24, 44 }, { 0, 48 }, { 24, 44 } }) do
			local wp = facingHub * CFrame.new(off[1] + rng:NextNumber(-4, 4), 0, off[2])
			if not WorldTerrain.isPaved(wp.X, wp.Z, 4) then
				local name = ({ "Tree_Puffy_A", "Tree_Puffy_B", "Tree_Puffy_C", "Tree_Fruit" })[rng:NextInteger(1, 4)]
				place(name, wp.X, wp.Z, nil, plot, rng:NextNumber(0.85, 1.1))
			end
		end
		local mail = facingHub * CFrame.new(-6, 0, -36)
		place("Mailbox", mail.X, mail.Z, math.deg(a) + 90, plot)
	end
	return "plots ok"
end

-- ═══ MEADOW ══════════════════════════════════════════════════════════════════

function WorldBuilder.meadow()
	getWorld()
	local b = Biomes.get("Meadow")
	local cx, cz = b.center[1], b.center[3]
	local mf = folder("Meadow", folder("Biomes", world))
	local deco = folder("Decor", mf)
	local markers = folder("Markers", world)

	-- the pond (terrain carves it; we dress it)
	local P = WorldTerrain.pond
	reserve(P.x, P.z, P.r + 4)
	for i = 1, 14 do
		local a = i / 14 * math.pi * 2 + rng:NextNumber(-0.1, 0.1)
		local rr = P.r + rng:NextNumber(1, 4)
		place(i % 3 == 0 and "PondRim_Stone" or "Reeds", P.x + math.cos(a) * rr, P.z + math.sin(a) * rr, nil, deco, rng:NextNumber(0.8, 1.2), nil, { query = false })
	end
	for _ = 1, 7 do
		local a = rng:NextNumber(0, 6.28)
		local rr = rng:NextNumber(4, P.r - 6)
		Kit.place("LilyPad", CFrame.new(P.x + math.cos(a) * rr, P.water - 0.05, P.z + math.sin(a) * rr) * CFrame.Angles(0, a, 0), deco, { collide = false, query = false })
	end
	-- the stream, and a bridge where the meadow path crosses it
	for i, pt in ipairs(WorldTerrain.stream) do
		reserve(pt[1], pt[2], 8)
		if i % 2 == 0 then
			place("Reeds", pt[1] + rng:NextNumber(-7, 7), pt[2] + 7, nil, deco)
		end
	end
	local crossX, crossZ = 503, 117
	local bridgeY = ground(crossX + 12, crossZ - 8)
	Kit.place("Bridge_Wood", faceCF(Vector3.new(crossX, bridgeY - 0.4, crossZ), Vector3.new(528, bridgeY, 146)), deco)
	reserve(crossX, crossZ, 12)

	-- gates (SPEC §11). Each gets a marker at its prompt position.
	local gates = {
		MeadowBoulder = { cx + 120, cz - 120, "Boulder_Big", 225 },
		MeadowRoots = { cx + 80, cz + 150, "RootTunnel", 20 },
		MeadowHollow = { cx + 150, cz + 20, "DarkHollow", 270 },
		MeadowVines = { cx + 20, cz - 165, "VineWall", 180 },
	}
	for id, g in pairs(gates) do
		local m = place(g[3], g[1], g[2], g[4], mf)
		if m then
			m.Name = "Gate_" .. id .. "_Model"
		end
		marker("Gate_" .. id, CFrame.new(g[1], ground(g[1], g[2]) + 3, g[2]), markers)
		reserve(g[1], g[2], 16)
	end
	tagCollider("DarkZone", CFrame.new(cx + 154, ground(cx + 154, cz + 20) + 4, cz + 20), Vector3.new(14, 10, 12), mf)
	tagCollider("TinyGap", CFrame.new(cx + 80, ground(cx + 80, cz + 150) + 2, cz + 150), Vector3.new(3, 4, 8), mf)

	place("Signpost", cx - 118, cz + 14, 270, deco)
	marker("Travel_Meadow", CFrame.new(cx - 130, ground(cx - 130, cz) + 3, cz), markers)

	-- vegetation in groves on the hills, open flower fields in the middle
	grove({ "Tree_Puffy_A", "Tree_Puffy_B", "Tree_Puffy_C", "Tree_Fruit" }, 16, 7, cx, cz, 230, 30, deco, 8, { 0.85, 1.3 })
	grove({ "Tree_Pine_A", "Tree_Pine_B" }, 6, 6, cx + 60, cz - 120, 90, 26, deco, 7, { 0.9, 1.3 })
	grove({ "Bush_A", "Bush_B", "Bush_C" }, 18, 5, cx, cz, 230, 16, deco, 3.5, { 0.8, 1.3 })
	grove({ "Rock_Small_A", "Rock_Small_B", "Rock_Medium_A", "Rock_Medium_B", "Log_A", "Stump_A" }, 12, 4, cx, cz, 220, 14, deco, 4)
	grove({ "FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "FlowerPatch_White", "Mushroom_Red" }, 22, 9, cx, cz, 150, 14, deco, 1.4, { 0.9, 1.5 })
	grove({ "GrassTuft_A", "GrassTuft_B" }, 30, 10, cx, cz, 230, 16, deco, 1)

	for i = 1, 4 do
		spawnArea("Meadow", CFrame.new(cx + (i <= 2 and -60 or 60), 5, cz + (i % 2 == 0 and -60 or 60)), Vector3.new(90, 8, 90))
		local ex, ez = cx + (i <= 2 and -50 or 50), cz + (i % 2 == 0 and -50 or 50)
		marker("EventSpot_Meadow_" .. i, CFrame.new(ex, ground(ex, ez) + 2, ez), markers)
	end
	marker("EventSpot_Meteor_1", CFrame.new(cx + 40, ground(cx + 40, cz - 40) + 2, cz - 40), markers)
	return "meadow ok"
end

-- ═══ THE COUNTRYSIDE: four corners between the biomes ════════════════════════
-- Nothing here is a gate or a spawn area. It exists so every direction you look from the
-- plots has a place in it: pine woods, an orchard, a farm, and dunes by the sea.

function WorldBuilder.countryside()
	getWorld()
	local cs = folder("Countryside", world)
	local Z = WorldTerrain.zones

	-- NE pine woods: dense, dark, with clearings, logs and mushrooms
	local woods = folder("Woods", cs)
	grove({ "Tree_Pine_A", "Tree_Pine_B" }, 16, 9, Z.woods.x, Z.woods.z, Z.woods.r - 20, 34, woods, 7, { 0.9, 1.5 }, { M.Grass, M.LeafyGrass })
	grove({ "Log_A", "Stump_A", "Rock_Medium_A", "Mushroom_Red", "Bush_C" }, 12, 4, Z.woods.x, Z.woods.z, Z.woods.r, 20, woods, 4, { 0.8, 1.3 })
	grove({ "GrassTuft_A", "GrassTuft_B", "FlowerPatch_White" }, 14, 8, Z.woods.x, Z.woods.z, Z.woods.r, 18, woods, 1.2)

	-- NW orchard: rows of fruit trees along the lane, a windmill watching over them
	local orchard = folder("Orchard", cs)
	for row = -3, 3 do
		for col = -3, 3 do
			local x = Z.orchard.x + col * 22 + (row % 2) * 11
			local z = Z.orchard.z + row * 20
			local _, _, _, _ = x, z, row, col
			if rng:NextNumber() < 0.85 and not WorldTerrain.isPaved(x, z, 5) then
				place("Tree_Fruit", x + rng:NextNumber(-2, 2), z + rng:NextNumber(-2, 2), nil, orchard, rng:NextNumber(0.9, 1.15))
				reserve(x, z, 6)
			end
		end
	end
	if Kit.has("Windmill") then
		local wx, wz = Z.orchard.x - 110, Z.orchard.z + 40
		local mill = place("Windmill", wx, wz, 135, orchard, 1.1)
		if mill then
			local sails = Kit.place("Windmill_Sails", mill:GetPivot() * CFrame.new(0, 11 * 1.1, -3.6 * 1.1), orchard, { collide = false, scale = 1.1 })
			if sails then
				CollectionService:AddTag(sails, "Spin")
			end
		end
		reserve(wx, wz, 16)
	end
	for i = 0, 5 do
		place("Hay_Bale", Z.orchard.x + 90 + (i % 3) * 5, Z.orchard.z + 70 + (i // 3) * 5, rng:NextNumber(0, 40), orchard)
	end
	scatter({ "FlowerPatch_Yellow", "GrassTuft_A", "Bush_B" }, 40, Z.orchard.x, Z.orchard.z, Z.orchard.r, orchard, 2)

	-- SE farm: three rows of fields with a fence, a barn-shack, hay, a well and a scarecrow post
	local farm = folder("Farm", cs)
	local F = Z.farm
	local fx, fz = F.x0, F.z0
	local w, d = F.x1 - F.x0, F.z1 - F.z0
	local function fenceLine(ax: number, az: number, bx: number, bz: number, gapAt: number?)
		local len = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
		local n = math.floor(len / 8)
		for k = 0, n - 1 do
			if not gapAt or k ~= gapAt then
				local t = (k + 0.5) / n
				local x, z = ax + (bx - ax) * t, az + (bz - az) * t
				place("Fence_Straight", x, z, math.deg(math.atan2(bx - ax, bz - az)) + 90, farm)
			end
		end
	end
	fenceLine(fx, fz + 14, fx, fz + d)
	fenceLine(fx, fz + d, fx + w, fz + d)
	fenceLine(fx + w, fz + d, fx + w, fz)
	fenceLine(fx + w, fz, fx + 14, fz)
	place("Shack", fx + w - 26, fz + d - 26, 225, farm, 1.8)
	reserve(fx + w - 26, fz + d - 26, 20)
	place("Well", fx + 30, fz + d - 20, 30, farm)
	for i = 0, 7 do
		place("Hay_Bale", fx + w - 60 + (i % 4) * 5, fz + 16 + (i // 4) * 5, rng:NextNumber(-15, 15), farm)
	end
	-- crops: rows of the real ingredient props growing in the dirt fields
	local ReplicatedStorage = game:GetService("ReplicatedStorage")
	local props = ReplicatedStorage:FindFirstChild("Assets") and ReplicatedStorage.Assets:FindFirstChild("Props")
	local crops = { "Carrot", "Pumpkin", "Watermelon", "Strawberry", "Sunflower", "Pumpkin" }
	local fieldN = 0
	for cxI = 0, 2 do
		for czI = 0, 2 do
			if (cxI + czI) % 2 == 0 then
				fieldN += 1
				local crop = crops[(fieldN - 1) % #crops + 1]
				local src = props and props:FindFirstChild(crop)
				for row = 0, 4 do
					for col = 0, 6 do
						local x = F.x0 + cxI * 64 + 14 + col * 6.5
						local z = F.z0 + czI * 50 + 13 + row * 6
						if src and not WorldTerrain.isPaved(x, z, 1) then
							local m = (src :: Model):Clone()
							m:ScaleTo(crop == "Sunflower" and 2 or 1.5)
							local ext = m:GetExtentsSize()
							m:PivotTo(CFrame.new(x + rng:NextNumber(-0.6, 0.6), ground(x, z) + ext.Y * 0.5 - 0.3, z) * CFrame.Angles(0, rng:NextNumber(0, 6.28), 0))
							for _, d in ipairs(m:GetDescendants()) do
								if d:IsA("BasePart") then
									d.Anchored = true
									d.CanCollide = false
									d.CanQuery = false
									d.CastShadow = false
								end
							end
							m.Parent = farm
						end
					end
				end
			end
		end
	end

	-- SW dunes: sand, driftwood, washed-up junk from the yard, rocks
	local dunes = folder("Dunes", cs)
	grove({ "Log_A", "Rock_Medium_A", "Rock_Medium_B", "Rock_Small_A", "Tire_Single", "Crate_B" }, 12, 4, Z.dunes.x, Z.dunes.z, Z.dunes.r, 22, dunes, 5, { 0.8, 1.3 })
	grove({ "Reeds", "Bush_C", "GrassTuft_B" }, 14, 5, Z.dunes.x, Z.dunes.z, Z.dunes.r, 16, dunes, 2)

	-- the whole coastline: rocks where the land meets the sea
	for i = 1, 90 do
		local a = i / 90 * math.pi * 2 + rng:NextNumber(-0.02, 0.02)
		for rr = 300, 1000, 6 do
			local x, z = math.cos(a) * rr, math.sin(a) * rr
			if WorldTerrain.coastD(x, z) > 0.94 then
				if rng:NextNumber() < 0.55 and z < 300 then
					place(({ "Rock_Medium_A", "Rock_Medium_B", "Rock_Small_B" })[rng:NextInteger(1, 3)], x, z, nil, dunes, rng:NextNumber(1, 2.2))
				end
				break
			end
		end
	end
	return "countryside ok"
end

-- ═══ JUNKYARD ════════════════════════════════════════════════════════════════

function WorldBuilder.junkyard()
	getWorld()
	local b = Biomes.get("Junkyard")
	local cx, cz = b.center[1], b.center[3]
	local jf = folder("Junkyard", folder("Biomes", world))
	local deco = folder("Decor", jf)
	local markers = folder("Markers", world)

	-- the dirt basin and junk heaps are terrain (WorldTerrain); a continuous chain fence
	-- rings the yard with one gate facing the road
	local fenceR = 180
	local segs = math.ceil(2 * math.pi * fenceR / 8.4)
	for i = 0, segs - 1 do
		local a = (i + 0.5) / segs * math.pi * 2
		local x, z = cx + math.cos(a) * fenceR, cz + math.sin(a) * fenceR
		if math.abs(math.atan2(math.sin(a), math.cos(a))) > 0.06 then
			Kit.place("ChainFence", CFrame.new(x, ground(x, z), z) * CFrame.Angles(0, -a + math.pi / 2, 0), deco)
		end
	end
	place("Sign_Danger", cx + 176, cz - 16, 90, deco)
	marker("Travel_Junkyard", CFrame.new(cx + 150, ground(cx + 150, cz) + 3, cz), markers)

	-- landmark + gates
	local crane = place("Magnet_Crane", cx - 110, cz + 100, 30, jf)
	if crane then
		crane.Name = "Gate_JunkBigMachine_Model"
	end
	marker("Gate_JunkBigMachine", CFrame.new(cx - 104, ground(cx - 104, cz + 96) + 3, cz + 96), markers)
	reserve(cx - 110, cz + 100, 22)

	place("Generator_Dead", cx - 110, cz - 60, 90, jf)
	marker("Gate_JunkGenerator", CFrame.new(cx - 104, ground(cx - 104, cz - 60) + 3, cz - 60), markers)
	-- the vault: containers around a yard with the reward inside
	for i, spec in ipairs({ { -135, -40, 0 }, { -135, -80, 0 }, { -155, -60, 90 } }) do
		place("Container_Shipping", cx + spec[1], cz + spec[2], spec[3], deco)
		local _ = i
	end
	reserve(cx - 130, cz - 60, 34)

	-- glide towers: climb A by the crate stairs, glide down onto B
	place("ScrapTower_A", cx - 20, cz + 140, 0, jf)
	place("ScrapTower_B", cx + 14, cz + 140, 180, jf, 0.72)
	-- crate stairs climb from the south straight up to tower A's platform
	for i = 0, 6 do
		local sx, sz = cx - 20 + (i % 2) * 0.6, cz + 114 + i * 3.2
		place("Crate_A", sx, sz, i * 13, deco, 1, ground(cx - 20, cz + 114) + i * 2.8)
	end
	marker("Gate_JunkTowers", CFrame.new(cx + 14, ground(cx + 14, cz + 140) + 15.5, cz + 140), markers)
	reserve(cx, cz + 140, 30)

	place("CrackedGround", cx + 70, cz - 150, 0, jf)
	marker("Gate_JunkCracks", CFrame.new(cx + 70, ground(cx + 70, cz - 150) + 3, cz - 150), markers)
	reserve(cx + 70, cz - 150, 12)

	-- sticky climb: a stack of containers; the reward sits on top
	local wx, wz = cx - 150, cz - 150
	place("Container_Shipping", wx, wz, 0, jf)
	place("Container_Shipping", wx, wz, 0, jf, 1, ground(wx, wz) + 8.6)
	tagCollider("ClimbWall", CFrame.new(wx, ground(wx, wz) + 8.5, wz - 4.4), Vector3.new(20, 17, 1), jf)
	marker("Gate_JunkWall", CFrame.new(wx, ground(wx, wz) + 19, wz), markers)
	reserve(wx, wz, 16)

	-- junk HEAPS, not confetti: piles crown each terrain heap, loose junk drifts around it,
	-- and bare dirt lanes run between them
	for _, hp in ipairs(WorldTerrain.heaps) do
		local hx, hz = hp[1], hp[2]
		place(({ "ScrapPile_A", "ScrapPile_B", "ScrapPile_C" })[rng:NextInteger(1, 3)], hx, hz, nil, deco, 2 + hp[4] / 12)
		reserve(hx, hz, hp[3] * 0.3)
		scatter({ "ScrapPile_A", "ScrapPile_B", "ScrapPile_C", "TV_Pile", "Tire_Stack", "CarWreck" }, 5, hx, hz, hp[3] * 0.75, deco, 7, { 1.2, 2.0 })
		scatter({ "Tire_Single", "Crate_B", "OilDrum", "Pipe_Segment", "Fridge_Old", "WashingMachine" }, 7, hx, hz, hp[3] * 1.3, deco, 3)
	end
	grove({ "CarWreck", "Fridge_Old", "WashingMachine", "OilDrum", "Tire_Stack" }, 8, 3, cx, cz, 150, 14, deco, 6)
	grove({ "GrassTuft_A", "GrassTuft_B", "Rock_Small_A" }, 10, 6, cx, cz, 170, 18, deco, 1)
	for i = 1, 4 do
		spawnArea("Junkyard", CFrame.new(cx + (i <= 2 and -55 or 55), 5, cz + (i % 2 == 0 and -55 or 55)), Vector3.new(80, 8, 80))
	end
	marker("EventSpot_Meteor_2", CFrame.new(cx + 30, ground(cx + 30, cz + 20) + 2, cz + 20), markers)
	return "junkyard ok"
end

-- ═══ CRYSTAL CAVES ═══════════════════════════════════════════════════════════

function WorldBuilder.caves()
	getWorld()
	local b = Biomes.get("CrystalCaves")
	local cx, cz = b.center[1], b.center[3]
	local cf = folder("CrystalCaves", folder("Biomes", world))
	local deco = folder("Decor", cf)
	local markers = folder("Markers", world)

	-- the mountain is part of the island height function; carve the cavern and the tunnel
	T:FillBall(Vector3.new(cx, 22, cz), 96, M.Air)
	T:FillBlock(CFrame.new(cx, -2, cz), Vector3.new(220, 8, 220), M.Slate)
	T:FillBall(Vector3.new(cx, 22, cz), 92, M.Air)
	T:FillBlock(CFrame.new(cx, -1, cz), Vector3.new(176, 6, 176), M.Slate)
	-- the tunnel runs from the end of the north road's canyon into the cavern
	for i = 0, 13 do
		T:FillBall(Vector3.new(cx + math.sin(i * 0.5) * 3, 10, cz + 145 - i * 7), 13, M.Air)
	end
	T:FillBlock(CFrame.new(cx, 0, cz + 110), Vector3.new(24, 4, 84), M.Slate)
	task.wait(0.5) -- let the carve reach collision before anything raycasts the cave floor
	place("Cave_Arch", cx, cz + 142, 0, cf, 1.15, ground(cx, cz + 142, 14))
	rayFrom = 60 -- everything below is inside the cavern
	marker("Travel_CrystalCaves", CFrame.new(cx, ground(cx, cz + 160, 40) + 3, cz + 160), markers)

	-- darkness inside (Light ability matters) + crystals that glow
	tagCollider("DarkZone", CFrame.new(cx, 25, cz), Vector3.new(180, 60, 180), cf)
	local function glowing(name: string, x: number, z: number, color: Color3, range: number, scale: number?)
		local m = place(name, x, z, nil, deco, scale)
		if m and m.PrimaryPart then
			local l = Instance.new("PointLight")
			l.Color = color
			l.Range = range
			l.Brightness = 1.6
			l.Parent = m.PrimaryPart
		end
		return m
	end
	local palette = {
		{ "Crystal_Cluster_Cyan", Color3.fromRGB(90, 220, 255) },
		{ "Crystal_Cluster_Purple", Color3.fromRGB(190, 120, 255) },
		{ "Crystal_Cluster_Pink", Color3.fromRGB(255, 120, 200) },
	}
	for i = 1, 34 do
		local a = rng:NextNumber(0, 6.28)
		local r = math.sqrt(rng:NextNumber()) * 78
		local x, z = cx + math.cos(a) * r, cz + math.sin(a) * r
		if free(x, z, 3) then
			local p = palette[(i % 3) + 1]
			glowing(p[1], x, z, p[2], 14, rng:NextNumber(0.8, 1.6))
			reserve(x, z, 2)
		end
	end
	for _, spot in ipairs({ { 50, -40 }, { -55, 30 }, { 10, -70 } }) do
		glowing("Crystal_Big", cx + spot[1], cz + spot[2], Color3.fromRGB(120, 230, 255), 36)
		reserve(cx + spot[1], cz + spot[2], 10)
	end
	-- gates
	local function gate(id: string, asset: string, x: number, z: number, yaw: number, scale: number?)
		local m = place(asset, x, z, yaw, cf, scale)
		if m then
			m.Name = "Gate_" .. id .. "_Model"
		end
		marker("Gate_" .. id, CFrame.new(x, ground(x, z, 60) + 3, z), markers)
		local _ = rayFrom
		reserve(x, z, 12)
	end
	gate("CaveGhost", "GhostBarrier", cx - 70, cz - 50, 60)
	tagCollider("GhostBarrier", CFrame.new(cx - 70, 7, cz - 50) * CFrame.Angles(0, math.rad(60), 0), Vector3.new(8, 9, 1), cf, true, Color3.fromRGB(200, 170, 255), M.ForceField)
	gate("CaveDeep", "Crystal_Big", cx + 10, cz - 80, 0, 1.3)
	tagCollider("DarkZone", CFrame.new(cx + 10, 10, cz - 80), Vector3.new(30, 20, 20), cf)
	gate("CaveHeat", "Crystal_Cluster_Pink", cx + 60, cz + 40, 0, 1.5)
	T:FillCylinder(CFrame.new(cx + 50, -0.8, cz + 30), 1.6, 12, M.CrackedLava)
	tagCollider("HotGround", CFrame.new(cx + 50, 1, cz + 30), Vector3.new(24, 4, 24), cf)
	gate("CaveCoop", "CaveRock_C", cx - 40, cz + 50, 0, 1.4)
	-- the earthquake pocket: sealed by a rock wall that the Earthquake event opens
	local seal = tagCollider("QuakeSealPart", CFrame.new(cx + 76, 10, cz - 20), Vector3.new(2, 16, 20), cf, true, Color3.fromRGB(88, 94, 118), M.Slate)
	seal.Name = "QuakeSeal"
	seal.Transparency = 0
	if Kit.has("Rock_Seal") then
		-- the seal reads as a rockfall: the mesh sits in front of the (then invisible) collider
		seal.Transparency = 1
		local rock = Kit.place("Rock_Seal", CFrame.new(cx + 76, ground(cx + 76, cz - 20, 60), cz - 20) * CFrame.Angles(0, math.rad(90), 0), seal, { collide = false })
		if rock then
			rock.Name = "SealRocks"
		end
	end
	marker("EventSpot_Quake_1", CFrame.new(cx + 86, ground(cx + 86, cz - 20, 60) + 2, cz - 20), markers)
	marker("EventSpot_Caves_1", CFrame.new(cx, ground(cx, cz, 60) + 2, cz), markers)

	scatter({ "Stalagmite_A", "Stalagmite_B", "CaveRock_A", "CaveRock_B" }, 40, cx, cz, 82, deco, 5, { 0.8, 1.5 })
	scatter({ "GlowMushroom_A", "GlowMushroom_B" }, 30, cx, cz, 80, deco, 3)
	scatter({ "Fossil_Ribs" }, 4, cx, cz, 70, deco, 10)
	-- outside: pines on the green lower slopes, boulders where the rock starts
	rayFrom = 320
	local mz = WorldTerrain.zones.mountain
	grove({ "Tree_Pine_A", "Tree_Pine_B" }, 20, 6, mz.x, mz.z, mz.r, 30, deco, 7, { 0.9, 1.4 }, { M.Grass, M.LeafyGrass })
	grove({ "Rock_Medium_A", "Rock_Medium_B", "CaveRock_A", "CaveRock_B" }, 14, 3, mz.x, mz.z, mz.r, 24, deco, 6, { 1.2, 2.2 }, { M.Rock, M.Grass })
	spawnArea("CrystalCaves", CFrame.new(cx, 6, cz), Vector3.new(150, 6, 150))
	return "caves ok"
end

-- ═══ OCEAN (Update 1) + STRANGE ZONE ═════════════════════════════════════════

function WorldBuilder.ocean()
	getWorld()
	local of = folder("Ocean", folder("Biomes", world))
	local deco = folder("Decor", of)
	local markers = folder("Markers", world)
	-- the sea floor is terrain; the reef is coral-coloured rock outcrops rising from it
	for _ = 1, 38 do
		local x, z = rng:NextNumber(-150, 150), rng:NextNumber(470, 610)
		T:FillBall(Vector3.new(x, rng:NextNumber(-26, -16), z), rng:NextNumber(5, 11), rng:NextNumber() < 0.6 and M.Rock or M.Sandstone)
	end
	T:SetMaterialColor(M.Sandstone, Color3.fromRGB(240, 140, 150))
	tagCollider("DeepWater", CFrame.new(0, -20, 540), Vector3.new(300, 34, 160), of)
	marker("Gate_OceanReef", CFrame.new(0, -30, 540), markers)
	marker("Travel_Ocean", CFrame.new(0, ground(0, 380) + 3, 380), markers)
	spawnArea("Ocean", CFrame.new(0, 4, 380), Vector3.new(500, 6, 60))
	-- striped cabanas along the sand
	for _, spot in ipairs({ { -70, 372, 160 }, { -46, 386, 195 }, { 58, 378, 210 }, { 84, 366, 150 } }) do
		place("Tent_Striped", spot[1], spot[2], spot[3], deco, 0.8)
		reserve(spot[1], spot[2], 8)
	end
	scatter({ "Log_A", "Crate_B", "OilDrum", "Tire_Single" }, 10, 0, 400, 260, deco, 10, { 0.9, 1.3 }, { M.Sand })
	-- beach dressing: rock groups, driftwood, reeds at the back of the sand
	grove({ "Rock_Small_A", "Rock_Medium_B", "PondRim_Stone", "Log_A" }, 12, 4, 0, 380, 220, 18, deco, 4, { 0.9, 1.6 }, { M.Sand })
	grove({ "Reeds", "GrassTuft_B", "Bush_C" }, 10, 5, 0, 350, 240, 14, deco, 2, nil, { M.Sand, M.Grass })
	-- locked until Update 1 ships (WorldState.UpdateLevel)
	local lock = Instance.new("Part")
	lock.Name = "OceanLock"
	lock.Anchored = true
	lock.Transparency = 1
	lock.Size = Vector3.new(1100, 80, 2)
	lock.CFrame = CFrame.new(0, 30, 428)
	lock.Parent = of
	local sign = place("Signpost", 12, 404, 0, of)
	if sign and sign.PrimaryPart then
		local gui = Instance.new("SurfaceGui")
		gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
		gui.PixelsPerStud = 50
		gui.Parent = sign.PrimaryPart
		local t = Instance.new("TextLabel")
		t.BackgroundTransparency = 1
		t.Size = UDim2.fromScale(1, 0.4)
		t.Position = UDim2.fromScale(0, 0.1)
		t.TextScaled = true
		t.Font = Enum.Font.FredokaOne
		t.TextColor3 = Color3.fromRGB(80, 50, 30)
		t.Text = "SOMETHING IS IN THE OCEAN"
		t.Parent = gui
	end
	return "ocean ok"
end

function WorldBuilder.strange()
	getWorld()
	local sf = folder("StrangeZone", folder("Biomes", world))
	local c = Vector3.new(-560, 230, -640)
	T:FillBall(c - Vector3.new(0, 30, 0), 50, M.Basalt)
	T:FillBall(c - Vector3.new(0, 6, 0), 44, M.LeafyGrass)
	T:FillBlock(CFrame.new(c + Vector3.new(0, 30, 0)), Vector3.new(120, 60, 120), M.Air)
	for i = 1, 10 do
		local a = i / 10 * math.pi * 2
		local p = c + Vector3.new(math.cos(a) * 28, 0, math.sin(a) * 28)
		local m = Kit.place(i % 2 == 0 and "Crystal_Big" or "Tree_Puffy_B", CFrame.new(p.X, ground(p.X, p.Z, 320), p.Z) * CFrame.Angles(0, a, 0.2), sf, { scale = 1.5 })
		if m and m.PrimaryPart then
			m.PrimaryPart.Color = i % 2 == 0 and Color3.fromRGB(255, 170, 255) or Color3.fromRGB(215, 190, 255)
			local l = Instance.new("PointLight")
			l.Color = Color3.fromRGB(200, 120, 255)
			l.Range = 40
			l.Brightness = 3
			l.Parent = m.PrimaryPart
		end
	end
	-- floating rocks orbiting the island (static, but they sell "reality misbehaves")
	for i = 1, 8 do
		local a = i / 8 * math.pi * 2
		T:FillBall(c + Vector3.new(math.cos(a) * 80, rng:NextNumber(-20, 40), math.sin(a) * 80), rng:NextNumber(6, 12), M.Basalt)
	end
	return "strange ok"
end

-- ═══ TRIALS (SPEC §21) ═══════════════════════════════════════════════════════

function WorldBuilder.trials()
	getWorld()
	local tf = folder("Trials", world)
	local ox = 6000

	local function platform(cf: CFrame, size: Vector3, mat: Enum.Material)
		T:FillBlock(cf * CFrame.new(0, -size.Y / 2, 0), size, mat)
	end

	-- RACE: a rounded rectangle loop, 8 checkpoints, a glide shortcut over a gap
	do
		local r = folder("Race", tf)
		r:SetAttribute("VoidY", -30)
		local mk = folder("Markers", r)
		local cz = 0
		platform(CFrame.new(ox, 0, cz), Vector3.new(260, 8, 200), M.Grass)
		T:FillBlock(CFrame.new(ox, -30, cz), Vector3.new(182, 76, 112), M.Air)
		task.wait(0.5)
		local pts = {
			Vector3.new(ox - 110, 0, cz - 80), Vector3.new(ox, 0, cz - 82), Vector3.new(ox + 110, 0, cz - 80), Vector3.new(ox + 118, 0, cz),
			Vector3.new(ox + 110, 0, cz + 80), Vector3.new(ox, 0, cz + 82), Vector3.new(ox - 110, 0, cz + 80), Vector3.new(ox - 118, 0, cz - 10),
		}
		for i, p in ipairs(pts) do
			local nxt = pts[(i % #pts) + 1]
			local cfm = CFrame.lookAt(p + Vector3.new(0, 5, 0), nxt + Vector3.new(0, 5, 0))
			local cp = marker("Checkpoint_" .. i, cfm, mk, Vector3.new(16, 12, 4))
			Kit.place("Race_Ring", cfm * CFrame.new(0, -5, 0), r, { collide = false })
			local _ = cp
		end
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(ox - 118 + (i - 4.5) * 4, 3, cz - 30) * CFrame.Angles(0, math.rad(180), 0), mk)
		end
		Kit.place("Race_StartGate", CFrame.new(ox - 118, ground(ox - 118, cz - 20, 40), cz - 20), r)
		for i = 1, 6 do
			local bx, bz = ox + rng:NextNumber(-100, 100), cz + (i % 2 == 0 and -80 or 80) + rng:NextNumber(-6, 6)
			Kit.place("Obstacle_Bumper", CFrame.new(bx, ground(bx, bz, 40), bz), r)
		end
		-- glide shortcut ramp across the middle gap
		T:FillWedge(CFrame.new(ox - 60, 6, cz - 60) * CFrame.Angles(0, math.rad(90), 0), Vector3.new(14, 12, 30), M.Grass)
		marker("Return", CFrame.new(-36, 6, 22), mk)
	end

	-- SMASH: a round arena with 24 smash spots
	do
		local s = folder("Smash", tf)
		local mk = folder("Markers", s)
		local c = Vector3.new(ox, 0, 500)
		T:FillCylinder(CFrame.new(c.X, -4, c.Z), 8, 80, M.Ground)
		T:FillCylinder(CFrame.new(c.X, -0.5, c.Z), 1, 76, M.Sand)
		for i = 1, 24 do
			local a = i / 24 * math.pi * 2
			local r = (i % 3 + 1) * 20
			marker("SmashSpot_" .. i, CFrame.new(c.X + math.cos(a) * r, 1, c.Z + math.sin(a) * r), mk)
		end
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(c.X + (i - 4.5) * 5, 3, c.Z), mk)
		end
		marker("Return", CFrame.new(-36, 6, 22), mk)
	end

	-- TREASURE: rolling dunes with 40 buried spots
	do
		local t = folder("Treasure", tf)
		local mk = folder("Markers", t)
		local c = Vector3.new(ox, 0, 1000)
		platform(CFrame.new(c.X, 0, c.Z), Vector3.new(240, 8, 240), M.Sand)
		for _ = 1, 20 do
			T:FillBall(c + Vector3.new(rng:NextNumber(-100, 100), rng:NextNumber(-14, -8), rng:NextNumber(-100, 100)), rng:NextNumber(12, 22), M.Sand)
		end
		for i = 1, 40 do
			local x, z = c.X + rng:NextNumber(-105, 105), c.Z + rng:NextNumber(-105, 105)
			marker("ChestSpot_" .. i, CFrame.new(x, ground(x, z, 80) + 1, z), mk)
		end
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(c.X + (i - 4.5) * 5, 8, c.Z), mk)
		end
		scatter({ "Rock_Medium_A", "Tree_Pine_A", "Bush_C" }, 24, c.X, c.Z, 115, t, 8)
		marker("Return", CFrame.new(-36, 6, 22), mk)
	end

	-- OBSTACLE CHAOS: floating islands over a void; hurdles, bumpers, beams; secret routes
	do
		local o = folder("Obstacle", tf)
		o:SetAttribute("VoidY", -20)
		local mk = folder("Markers", o)
		local z0 = 1500
		local islands = {}
		for i = 0, 7 do
			local p = Vector3.new(ox + (i % 2 == 0 and -10 or 10), i * 2, z0 + i * 44)
			T:FillCylinder(CFrame.new(p.X, p.Y - 3, p.Z), 6, 16, M.Grass)
			task.wait(0.1)
			table.insert(islands, p)
			marker("Checkpoint_" .. (i + 1), CFrame.new(p + Vector3.new(0, 4, 0)), mk, Vector3.new(24, 10, 24))
			if i > 0 then
				local prev = islands[i]
				local mid = (prev + p) / 2
				Kit.place("Balance_Beam", CFrame.lookAt(Vector3.new(mid.X, mid.Y - 0.5, mid.Z), Vector3.new(p.X, mid.Y - 0.5, p.Z)), o)
				Kit.place(i % 2 == 0 and "Obstacle_Hurdle" or "Obstacle_Bumper", CFrame.new(p.X + 4, ground(p.X + 4, p.Z - 6, p.Y + 20), p.Z - 6), o)
			end
		end
		-- secret routes: a Tiny gap and a Sticky wall shortcut
		tagCollider("TinyGap", CFrame.new(ox + 18, 7, z0 + 110), Vector3.new(2, 4, 6), o)
		tagCollider("ClimbWall", CFrame.new(ox - 22, 10, z0 + 200), Vector3.new(10, 20, 2), o, true, Color3.fromRGB(160, 140, 120), M.Rock)
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(islands[1] + Vector3.new((i - 4.5) * 2.5, 4, -4)), mk)
		end
		marker("Return", CFrame.new(-36, 6, 22), mk)
	end

	-- SWIM (Update 1): a ring course in open water near the reef
	do
		local s = folder("Swim", tf)
		local mk = folder("Markers", s)
		local c = Vector3.new(ox, 0, 2200)
		T:FillBlock(CFrame.new(c.X, -12, c.Z), Vector3.new(200, 24, 200), M.Water)
		T:FillBlock(CFrame.new(c.X, -26, c.Z), Vector3.new(200, 4, 200), M.Sand)
		for i = 1, 8 do
			local a = i / 8 * math.pi * 2
			local p = c + Vector3.new(math.cos(a) * 70, -6, math.sin(a) * 70)
			marker("Checkpoint_" .. i, CFrame.new(p), mk, Vector3.new(14, 14, 14))
			Kit.place("Race_Ring", CFrame.new(p - Vector3.new(0, 5, 0)), s, { collide = false })
		end
		platform(CFrame.new(c.X + 90, 0, c.Z), Vector3.new(20, 4, 40), M.Sand)
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(c.X + 90, 3, c.Z + (i - 4.5) * 4), mk)
		end
		marker("Return", CFrame.new(-36, 6, 22), mk)
	end
	return "trials ok"
end

-- ═══ SPAWN ═══════════════════════════════════════════════════════════════════

function WorldBuilder.spawn()
	getWorld()
	local s = workspace:FindFirstChildOfClass("SpawnLocation") or Instance.new("SpawnLocation")
	s.Anchored = true
	s.Transparency = 1
	s.CanCollide = false
	s.Neutral = true
	s.Size = Vector3.new(8, 1, 8)
	s.CFrame = CFrame.new(0, ground(0, 36) + 0.5, 36)
	s.Parent = workspace
	return "spawn ok"
end

function WorldBuilder.all()
	local out = {}
	for _, step in ipairs({ "clear", "terrain", "hub", "plots", "meadow", "countryside", "junkyard", "caves", "ocean", "strange", "trials", "spawn" }) do
		table.insert(out, (WorldBuilder :: any)[step]())
		if step == "terrain" then
			-- freshly written voxels are not raycastable until the engine steps; every
			-- placement below raycasts the ground
			task.wait(1)
		end
	end
	return table.concat(out, ", ")
end

return WorldBuilder
