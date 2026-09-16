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
local rayFrom = 200

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
	-- straight roads along axes (width 16) and the ring road (r 132..148)
	local d = math.sqrt(x * x + z * z)
	if d > 50 and ((math.abs(z) < 9 and math.abs(x) < 340) or (math.abs(x) < 9 and z < 0 and z > -330) or (math.abs(x) < 9 and z > 0 and z < 340)) then
		return true
	end
	if d > 128 and d < 152 then
		return true
	end
	return false
end

-- scatter kit meshes in a disc or box, on grass, away from reserved spots
local function scatter(names: { string }, count: number, cx: number, cz: number, radius: number, parent: Instance, minGap: number, scaleRange: { number }?, materials: { Enum.Material }?)
	local placed = 0
	local tries = 0
	while placed < count and tries < count * 12 do
		tries += 1
		local a = rng:NextNumber(0, math.pi * 2)
		local r = math.sqrt(rng:NextNumber()) * radius
		local x, z = cx + math.cos(a) * r, cz + math.sin(a) * r
		if free(x, z, minGap) and not onRoad(x, z) then
			local hit = groundHit(x, z)
			if hit and hit.Normal.Y > 0.82 and (not materials or table.find(materials, hit.Material)) then
				local s = scaleRange and rng:NextNumber(scaleRange[1], scaleRange[2]) or 1
				local m = place(names[rng:NextInteger(1, #names)], x, z, nil, parent, s, hit.Position.Y - 0.15)
				if m then
					placed += 1
					if minGap > 2 then
						reserve(x, z, minGap * 0.6)
					end
				end
			end
		end
	end
	return placed
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
	rayFrom = 200
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

-- ═══ TERRAIN + LIGHTING ══════════════════════════════════════════════════════

local function fillBlock(x0: number, z0: number, x1: number, z1: number, yTop: number, depth: number, mat: Enum.Material)
	local cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
	T:FillBlock(CFrame.new(cx, yTop - depth / 2, cz), Vector3.new(math.abs(x1 - x0), depth, math.abs(z1 - z0)), mat)
end

function WorldBuilder.terrain()
	getWorld()
	-- saturated but natural (SPEC §40)
	T:SetMaterialColor(M.Grass, Color3.fromRGB(104, 176, 72))
	T:SetMaterialColor(M.LeafyGrass, Color3.fromRGB(96, 164, 70))
	T:SetMaterialColor(M.Ground, Color3.fromRGB(176, 142, 100))
	T:SetMaterialColor(M.Sand, Color3.fromRGB(236, 214, 160))
	T:SetMaterialColor(M.Rock, Color3.fromRGB(122, 130, 150))
	T:SetMaterialColor(M.Slate, Color3.fromRGB(88, 94, 118))
	T:SetMaterialColor(M.Cobblestone, Color3.fromRGB(196, 186, 170))
	T:SetMaterialColor(M.Mud, Color3.fromRGB(122, 98, 76))
	T:SetMaterialColor(M.Asphalt, Color3.fromRGB(96, 94, 100))
	T:SetMaterialColor(M.Basalt, Color3.fromRGB(70, 64, 86))
	T:SetMaterialColor(M.CrackedLava, Color3.fromRGB(255, 120, 40))
	T.WaterColor = Color3.fromRGB(60, 170, 210)
	T.WaterTransparency = 0.55
	T.WaterWaveSize = 0.12
	T.WaterWaveSpeed = 8
	T.WaterReflectance = 0.6
	pcall(function()
		(T :: any).Decoration = true -- grass decoration; not scriptable in every context
	end)

	-- the sea around everything
	fillBlock(-1100, -1150, 1100, 1100, -1.5, 30, M.Water)
	fillBlock(-1100, -1150, 1100, 1100, -31.5, 6, M.Sand)
	-- the island
	fillBlock(-660, -700, 660, 330, 0, 12, M.Grass)
	-- beach
	fillBlock(-420, 330, 420, 430, 0, 12, M.Sand)
	fillBlock(-420, 430, 420, 470, -1, 12, M.Sand)
	-- rounded coast: soften the corners with grass balls under the edge
	for i = 0, 40 do
		local x = -660 + i * 33
		T:FillBall(Vector3.new(x, -8, -700), 20, M.Grass)
		T:FillBall(Vector3.new(x, -8, 330), 20, M.Grass)
	end
	for i = 0, 31 do
		local z = -700 + i * 33
		T:FillBall(Vector3.new(-660, -8, z), 20, M.Grass)
		T:FillBall(Vector3.new(660, -8, z), 20, M.Grass)
	end

	-- town square: cobblestone disc
	T:FillCylinder(CFrame.new(0, -1, 0), 2, 62, M.Cobblestone)
	-- straight roads to each biome
	fillBlock(56, -8, 340, 8, 0, 1.6, M.Ground)
	fillBlock(-340, -8, -56, 8, 0, 1.6, M.Ground)
	fillBlock(-8, -330, 8, -56, 0, 1.6, M.Ground)
	fillBlock(-8, 56, 8, 340, 0, 1.6, M.Ground)
	-- the ring road between the square and the plots (aspiration creature walks it)
	for i = 0, 120 do
		local a = i / 120 * math.pi * 2
		local x, z = math.cos(a) * 140, math.sin(a) * 140
		T:FillBlock(CFrame.new(x, -0.8, z) * CFrame.Angles(0, -a, 0), Vector3.new(14, 1.6, 9), M.Ground)
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
	marker("ParadeStart", CFrame.new(0, 1.8, -42), hm)
	marker("ParadeEnd", CFrame.new(0, 1.8, -77), hm)
	reserve(0, -60, 26)
	for i = 0, 3 do
		place("Bench_Park", i % 2 == 0 and -12 or 12, -48 - i * 9, i % 2 == 0 and 90 or 270, hub)
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
	marker("Travel_Hub", CFrame.new(0, 2, 34), markers)
	marker("TrialReturn", CFrame.new(-36, 2, 22), markers)

	-- lamp ring, bunting between lamps, benches, planters, balloons
	local lamps = {}
	for i = 0, 7 do
		local a = (i + 0.5) / 8 * math.pi * 2
		local x, z = math.cos(a) * 56, math.sin(a) * 56
		place("Lamp_Post", x, z, -math.deg(a), hub)
		table.insert(lamps, Vector3.new(x, 0, z))
	end
	for i = 1, #lamps do
		local a, b = lamps[i], lamps[(i % #lamps) + 1]
		local mid = (a + b) / 2
		Kit.place("Bunting_Span", CFrame.lookAt(Vector3.new(mid.X, 0, mid.Z), Vector3.new(b.X, 0, b.Z)) * CFrame.Angles(0, math.rad(90), 0), hub, { collide = false })
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
		marker("EventSpot_Hub_" .. i, CFrame.new(math.cos(i * 1.57) * 34, 1, math.sin(i * 1.57) * 34), markers)
	end
	-- flowers around the edge of the square
	scatter({ "FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "FlowerPatch_White", "GrassTuft_A", "GrassTuft_B", "Bush_A" }, 60, 0, 0, 90, hub, 2.5)
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
		local facingHub = CFrame.lookAt(pos, Vector3.new(0, 0, 0))
		-- lawn and a little path out to the ring road
		T:FillBlock(facingHub * CFrame.new(0, -0.9, 0), Vector3.new(66, 1.8, 66), M.LeafyGrass)
		T:FillBlock(facingHub * CFrame.new(0, -0.8, -44), Vector3.new(8, 1.6, 24), M.Ground)
		local plot = folder("Plot_" .. i, plots)
		local c = marker("Center", CFrame.new(pos.X, 0.5, pos.Z) * facingHub.Rotation, plot, Vector3.new(4, 1, 4))
		c:SetAttribute("Plot", i)
		reserve(pos.X, pos.Z, 48)
		-- trees framing the back corners (outside the fence line) so every plot feels cosy
		for _, off in ipairs({ { -40, 38 }, { 40, 36 }, { -44, 0 }, { 44, -6 } }) do
			local wp = facingHub * CFrame.new(off[1], 0, off[2])
			local name = ({ "Tree_Puffy_A", "Tree_Puffy_B", "Tree_Puffy_C", "Tree_Fruit" })[rng:NextInteger(1, 4)]
			place(name, wp.X, wp.Z, nil, plot, rng:NextNumber(0.85, 1.1))
		end
		for _, off in ipairs({ { -36, -30 }, { 36, -30 } }) do
			local wp = facingHub * CFrame.new(off[1], 0, off[2])
			place("Bush_B", wp.X, wp.Z, nil, plot)
			place("FlowerPatch_Pink", wp.X + 3, wp.Z + 2, nil, plot)
		end
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

	-- rolling hills around the edges, flat fields in the middle
	for _ = 1, 22 do
		local a = rng:NextNumber(0, math.pi * 2)
		local r = rng:NextNumber(130, 210)
		local x, z = cx + math.cos(a) * r, cz + math.sin(a) * r
		T:FillBall(Vector3.new(x, rng:NextNumber(-34, -24), z), rng:NextNumber(34, 50), M.Grass)
	end
	-- the pond and a stream
	local px, pz = cx - 30, cz + 80
	T:FillCylinder(CFrame.new(px, -3, pz), 7, 26, M.Air)
	T:FillCylinder(CFrame.new(px, -6, pz), 2, 26, M.Mud)
	T:FillCylinder(CFrame.new(px, -2.8, pz), 4.6, 24, M.Water)
	T:FillCylinder(CFrame.new(px, -0.5, pz), 1.2, 29, M.Sand)
	T:FillCylinder(CFrame.new(px, -3, pz), 7, 24, M.Air)
	T:FillCylinder(CFrame.new(px, -3.3, pz), 4.6, 24, M.Water)
	reserve(px, pz, 32)
	for i = 0, 12 do
		local x = px + 26 + i * 8
		local z = pz + 30 + math.sin(i * 0.6) * 10
		T:FillBlock(CFrame.new(x, -2, z), Vector3.new(10, 4, 10), M.Air)
		T:FillBlock(CFrame.new(x, -3, z), Vector3.new(10, 2.2, 9), M.Water)
		reserve(x, z, 8)
	end
	place("Bridge_Wood", px + 66, pz + 34 + math.sin(5 * 0.6) * 10, 0, deco)
	for i = 1, 8 do
		local a = i / 8 * math.pi * 2
		place(i % 2 == 0 and "Reeds" or "PondRim_Stone", px + math.cos(a) * 25, pz + math.sin(a) * 25, nil, deco)
	end
	for i = 1, 5 do
		local a = rng:NextNumber(0, 6.28)
		Kit.place("LilyPad", CFrame.new(px + math.cos(a) * rng:NextNumber(4, 18), -0.4, pz + math.sin(a) * rng:NextNumber(4, 18)), deco)
	end

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
	-- the hollow is a dark zone; the roots are a tiny gap
	tagCollider("DarkZone", CFrame.new(cx + 154, 4, cz + 20), Vector3.new(14, 10, 12), mf)
	tagCollider("TinyGap", CFrame.new(cx + 80, 2, cz + 150), Vector3.new(3, 4, 8), mf)

	-- farm corner
	for i = 0, 4 do
		place("Hay_Bale", cx - 120 + i * 4, cz - 90 + (i % 2) * 3, rng:NextNumber(0, 40), deco)
	end
	place("Well", cx - 100, cz - 70, 30, deco)
	for i = 0, 5 do
		place("Fence_Straight", cx - 140 + i * 8, cz - 100, 0, deco)
	end
	reserve(cx - 115, cz - 85, 24)
	place("Signpost", cx - 150, cz + 12, 270, deco)
	marker("Travel_Meadow", CFrame.new(cx - 130, ground(cx - 130, cz) + 3, cz), markers)

	-- vegetation
	scatter({ "Tree_Puffy_A", "Tree_Puffy_B", "Tree_Puffy_C", "Tree_Fruit", "Tree_Pine_A", "Tree_Pine_B" }, 90, cx, cz, 210, deco, 9, { 0.85, 1.25 })
	scatter({ "Bush_A", "Bush_B", "Bush_C" }, 70, cx, cz, 200, deco, 4, { 0.8, 1.3 })
	scatter({ "Rock_Small_A", "Rock_Small_B", "Rock_Medium_A", "Rock_Medium_B", "Log_A", "Stump_A" }, 45, cx, cz, 200, deco, 4)
	scatter({ "FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "FlowerPatch_White", "Mushroom_Red" }, 180, cx, cz, 200, deco, 1.5, { 0.9, 1.4 })
	scatter({ "GrassTuft_A", "GrassTuft_B" }, 240, cx, cz, 210, deco, 1)

	for i = 1, 4 do
		spawnArea("Meadow", CFrame.new(cx + (i <= 2 and -60 or 60), 5, cz + (i % 2 == 0 and -60 or 60)), Vector3.new(90, 8, 90))
		marker("EventSpot_Meadow_" .. i, CFrame.new(cx + (i <= 2 and -50 or 50), ground(cx, cz) + 2, cz + (i % 2 == 0 and -50 or 50)), markers)
	end
	marker("EventSpot_Meteor_1", CFrame.new(cx + 40, 2, cz - 40), markers)
	return "meadow ok"
end

-- ═══ JUNKYARD ════════════════════════════════════════════════════════════════

function WorldBuilder.junkyard()
	getWorld()
	local b = Biomes.get("Junkyard")
	local cx, cz = b.center[1], b.center[3]
	local jf = folder("Junkyard", folder("Biomes", world))
	local deco = folder("Decor", jf)
	local markers = folder("Markers", world)

	T:FillCylinder(CFrame.new(cx, -1, cz), 2.2, 190, M.Ground)
	for _ = 1, 26 do
		local a = rng:NextNumber(0, 6.28)
		local r = math.sqrt(rng:NextNumber()) * 170
		T:FillCylinder(CFrame.new(cx + math.cos(a) * r, -0.9, cz + math.sin(a) * r), 2, rng:NextNumber(8, 22), rng:NextNumber() < 0.5 and M.Mud or M.Asphalt)
	end
	-- perimeter fence with a gap facing the road
	for i = 0, 43 do
		local a = i / 44 * math.pi * 2
		if math.abs(math.cos(a) - 1) > 0.02 then
			local x, z = cx + math.cos(a) * 182, cz + math.sin(a) * 182
			if not (x > cx + 170 and math.abs(z - cz) < 14) then
				Kit.place("ChainFence", CFrame.new(x, ground(x, z), z) * CFrame.Angles(0, -a + math.pi / 2, 0), deco)
			end
		end
	end
	place("Sign_Danger", cx + 176, cz - 16, 90, deco)
	marker("Travel_Junkyard", CFrame.new(cx + 150, 3, cz), markers)

	-- landmark + gates
	local crane = place("Magnet_Crane", cx - 110, cz + 100, 30, jf)
	if crane then
		crane.Name = "Gate_JunkBigMachine_Model"
	end
	marker("Gate_JunkBigMachine", CFrame.new(cx - 104, 3, cz + 96), markers)
	reserve(cx - 110, cz + 100, 22)

	place("Generator_Dead", cx - 110, cz - 60, 90, jf)
	marker("Gate_JunkGenerator", CFrame.new(cx - 104, 3, cz - 60), markers)
	-- the vault: containers around a yard with the reward inside
	for i, spec in ipairs({ { -135, -40, 0 }, { -135, -80, 0 }, { -155, -60, 90 } }) do
		place("Container_Shipping", cx + spec[1], cz + spec[2], spec[3], deco)
		local _ = i
	end
	reserve(cx - 130, cz - 60, 34)

	-- glide towers: climb A by the crate stairs, glide down onto B
	place("ScrapTower_A", cx - 20, cz + 140, 0, jf)
	place("ScrapTower_B", cx + 14, cz + 140, 180, jf, 0.72)
	for i = 0, 6 do
		place("Crate_A", cx - 20 - 8 - i * 3.2, cz + 132 + i * 0.3, i * 13, deco, 1, ground(cx - 28, cz + 132) + i * 2.8)
	end
	marker("Gate_JunkTowers", CFrame.new(cx + 14, ground(cx + 14, cz + 140) + 15.5, cz + 140), markers)
	reserve(cx, cz + 140, 30)

	place("CrackedGround", cx + 70, cz - 150, 0, jf)
	marker("Gate_JunkCracks", CFrame.new(cx + 70, 2, cz - 150), markers)
	reserve(cx + 70, cz - 150, 12)

	-- sticky climb: a stack of containers; the reward sits on top
	local wx, wz = cx - 150, cz - 150
	place("Container_Shipping", wx, wz, 0, jf)
	place("Container_Shipping", wx, wz, 0, jf, 1, ground(wx, wz) + 8.6)
	tagCollider("ClimbWall", CFrame.new(wx, ground(wx, wz) + 8.5, wz - 4.4), Vector3.new(20, 17, 1), jf)
	marker("Gate_JunkWall", CFrame.new(wx, ground(wx, wz) + 19, wz), markers)
	reserve(wx, wz, 16)

	-- junk everywhere
	scatter({ "ScrapPile_A", "ScrapPile_B", "ScrapPile_C" }, 30, cx, cz, 165, deco, 8, { 0.9, 1.5 })
	scatter({ "Tire_Single", "Tire_Stack", "Crate_A", "Crate_B", "OilDrum" }, 60, cx, cz, 165, deco, 3)
	scatter({ "CarWreck", "Fridge_Old", "WashingMachine", "TV_Pile", "Pipe_Segment" }, 26, cx, cz, 160, deco, 7)
	scatter({ "GrassTuft_A", "GrassTuft_B", "Rock_Small_A" }, 60, cx, cz, 180, deco, 1)
	for i = 1, 4 do
		spawnArea("Junkyard", CFrame.new(cx + (i <= 2 and -55 or 55), 5, cz + (i % 2 == 0 and -55 or 55)), Vector3.new(80, 8, 80))
	end
	marker("EventSpot_Meteor_2", CFrame.new(cx + 30, 2, cz + 20), markers)
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

	-- the mountain, then the cavern carved out of it, then a flat floor
	T:FillBall(Vector3.new(cx, -40, cz), 170, M.Rock)
	T:FillBall(Vector3.new(cx + 90, -30, cz - 60), 110, M.Slate)
	T:FillBall(Vector3.new(cx - 100, -30, cz - 30), 100, M.Rock)
	-- snow-ish grass cap on the peak so it reads from the plots
	T:FillBall(Vector3.new(cx, 118, cz), 30, M.Grass)
	T:FillBall(Vector3.new(cx, 22, cz), 96, M.Air)
	T:FillBlock(CFrame.new(cx, -6, cz), Vector3.new(220, 12, 220), M.Slate)
	T:FillBall(Vector3.new(cx, 22, cz), 92, M.Air)
	T:FillBlock(CFrame.new(cx, -3, cz), Vector3.new(170, 6, 170), M.Slate)
	-- entrance tunnel from the road
	for i = 0, 10 do
		T:FillBall(Vector3.new(cx, 9, cz + 150 - i * 8), 13, M.Air)
	end
	T:FillBlock(CFrame.new(cx, -2, cz + 110), Vector3.new(22, 4, 90), M.Slate)
	place("Cave_Arch", cx, cz + 158, 0, cf, 1, ground(cx, cz + 158, 12))
	rayFrom = 60 -- everything below is inside the cavern
	marker("Travel_CrystalCaves", CFrame.new(cx, 3, cz + 175), markers)

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
		reserve(x, z, 12)
	end
	gate("CaveGhost", "GhostBarrier", cx - 70, cz - 50, 60)
	tagCollider("GhostBarrier", CFrame.new(cx - 70, 5, cz - 50) * CFrame.Angles(0, math.rad(60), 0), Vector3.new(8, 9, 1), cf, true, Color3.fromRGB(200, 170, 255), M.ForceField)
	gate("CaveDeep", "Crystal_Big", cx + 10, cz - 80, 0, 1.3)
	tagCollider("DarkZone", CFrame.new(cx + 10, 10, cz - 80), Vector3.new(30, 20, 20), cf)
	gate("CaveHeat", "Crystal_Cluster_Pink", cx + 60, cz + 40, 0, 1.5)
	T:FillCylinder(CFrame.new(cx + 50, -0.8, cz + 30), 1.6, 12, M.CrackedLava)
	tagCollider("HotGround", CFrame.new(cx + 50, 1, cz + 30), Vector3.new(24, 4, 24), cf)
	gate("CaveCoop", "CaveRock_C", cx - 40, cz + 50, 0, 1.4)
	-- the earthquake pocket: sealed by a rock wall that the Earthquake event opens
	local seal = tagCollider("QuakeSealPart", CFrame.new(cx + 76, 8, cz - 20), Vector3.new(2, 16, 20), cf, true, Color3.fromRGB(88, 94, 118), M.Slate)
	seal.Name = "QuakeSeal"
	seal.Transparency = 0
	marker("EventSpot_Quake_1", CFrame.new(cx + 86, 2, cz - 20), markers)
	marker("EventSpot_Caves_1", CFrame.new(cx, 2, cz), markers)

	scatter({ "Stalagmite_A", "Stalagmite_B", "CaveRock_A", "CaveRock_B" }, 40, cx, cz, 82, deco, 5, { 0.8, 1.5 })
	scatter({ "GlowMushroom_A", "GlowMushroom_B" }, 30, cx, cz, 80, deco, 3)
	scatter({ "Fossil_Ribs" }, 4, cx, cz, 70, deco, 10)
	-- outside the mountain
	rayFrom = 200
	scatter({ "Tree_Pine_A", "Tree_Pine_B", "Rock_Medium_A", "CaveRock_B" }, 40, cx, cz + 175, 70, deco, 8)
	spawnArea("CrystalCaves", CFrame.new(cx, 4, cz), Vector3.new(150, 6, 150))
	return "caves ok"
end

-- ═══ OCEAN (Update 1) + STRANGE ZONE ═════════════════════════════════════════

function WorldBuilder.ocean()
	getWorld()
	local of = folder("Ocean", folder("Biomes", world))
	local deco = folder("Decor", of)
	local markers = folder("Markers", world)
	-- deeper water with a reef shelf
	T:FillBlock(CFrame.new(0, -20, 540), Vector3.new(300, 36, 160), M.Water)
	T:FillBlock(CFrame.new(0, -40, 540), Vector3.new(300, 6, 160), M.Sand)
	for _ = 1, 30 do
		T:FillBall(Vector3.new(rng:NextNumber(-130, 130), rng:NextNumber(-40, -26), rng:NextNumber(480, 600)), rng:NextNumber(5, 12), M.Rock)
	end
	tagCollider("DeepWater", CFrame.new(0, -20, 540), Vector3.new(300, 34, 160), of)
	marker("Gate_OceanReef", CFrame.new(0, -30, 540), markers)
	marker("Travel_Ocean", CFrame.new(0, 3, 380), markers)
	spawnArea("Ocean", CFrame.new(0, 4, 380), Vector3.new(500, 6, 70))
	-- beach dressing
	scatter({ "Rock_Small_A", "Rock_Medium_B", "PondRim_Stone" }, 20, 0, 380, 200, deco, 4, nil, { M.Sand })
	-- locked until Update 1 ships (WorldState.UpdateLevel)
	local lock = Instance.new("Part")
	lock.Name = "OceanLock"
	lock.Anchored = true
	lock.Transparency = 1
	lock.Size = Vector3.new(860, 60, 2)
	lock.CFrame = CFrame.new(0, 30, 336)
	lock.Parent = of
	local sign = place("Signpost", 12, 326, 0, of)
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
	local c = Vector3.new(0, 240, -820)
	T:FillBall(c - Vector3.new(0, 30, 0), 50, M.Basalt)
	T:FillBall(c - Vector3.new(0, 6, 0), 44, M.LeafyGrass)
	T:FillBlock(CFrame.new(c + Vector3.new(0, 30, 0)), Vector3.new(120, 60, 120), M.Air)
	for i = 1, 10 do
		local a = i / 10 * math.pi * 2
		local p = c + Vector3.new(math.cos(a) * 28, 0, math.sin(a) * 28)
		local m = Kit.place(i % 2 == 0 and "Crystal_Big" or "Tree_Puffy_B", CFrame.new(p.X, ground(p.X, p.Z, 320), p.Z) * CFrame.Angles(0, a, 0.2), sf, { scale = 1.5 })
		if m and m.PrimaryPart then
			m.PrimaryPart.Color = i % 2 == 0 and Color3.fromRGB(255, 120, 255) or Color3.fromRGB(170, 120, 255)
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
	local ox = 2200

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
		T:FillBlock(CFrame.new(ox, 2, cz), Vector3.new(180, 8, 110), M.Air)
		T:FillBlock(CFrame.new(ox, -30, cz), Vector3.new(180, 50, 110), M.Air)
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
		Kit.place("Race_StartGate", CFrame.new(ox - 118, 0, cz - 20), r)
		for i = 1, 6 do
			Kit.place("Obstacle_Bumper", CFrame.new(ox + rng:NextNumber(-100, 100), 0, cz + (i % 2 == 0 and -80 or 80) + rng:NextNumber(-6, 6)), r)
		end
		-- glide shortcut ramp across the middle gap
		T:FillWedge(CFrame.new(ox - 60, 6, cz - 60) * CFrame.Angles(0, math.rad(90), 0), Vector3.new(14, 12, 30), M.Grass)
		marker("Return", CFrame.new(-36, 2, 22), mk)
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
		marker("Return", CFrame.new(-36, 2, 22), mk)
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
		marker("Return", CFrame.new(-36, 2, 22), mk)
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
			table.insert(islands, p)
			marker("Checkpoint_" .. (i + 1), CFrame.new(p + Vector3.new(0, 4, 0)), mk, Vector3.new(24, 10, 24))
			if i > 0 then
				local prev = islands[i]
				local mid = (prev + p) / 2
				Kit.place("Balance_Beam", CFrame.lookAt(Vector3.new(mid.X, mid.Y - 0.5, mid.Z), Vector3.new(p.X, mid.Y - 0.5, p.Z)), o)
				Kit.place(i % 2 == 0 and "Obstacle_Hurdle" or "Obstacle_Bumper", CFrame.new(p.X + 4, p.Y, p.Z - 6), o)
			end
		end
		-- secret routes: a Tiny gap and a Sticky wall shortcut
		tagCollider("TinyGap", CFrame.new(ox + 18, 7, z0 + 110), Vector3.new(2, 4, 6), o)
		tagCollider("ClimbWall", CFrame.new(ox - 22, 10, z0 + 200), Vector3.new(10, 20, 2), o, true, Color3.fromRGB(160, 140, 120), M.Rock)
		for i = 1, 8 do
			marker("Spawn_" .. i, CFrame.new(islands[1] + Vector3.new((i - 4.5) * 2.5, 4, -4)), mk)
		end
		marker("Return", CFrame.new(-36, 2, 22), mk)
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
		marker("Return", CFrame.new(-36, 2, 22), mk)
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
	s.CFrame = CFrame.new(0, 1, 36)
	s.Parent = workspace
	return "spawn ok"
end

function WorldBuilder.all()
	local out = {}
	for _, step in ipairs({ "clear", "terrain", "hub", "plots", "meadow", "junkyard", "caves", "ocean", "strange", "trials", "spawn" }) do
		table.insert(out, (WorldBuilder :: any)[step]())
	end
	return table.concat(out, ", ")
end

return WorldBuilder
