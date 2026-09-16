--!strict
-- WorldTerrain — the island as ONE height function, written to voxels in chunks.
--
-- Why a height function instead of FillBlock/FillBall: the first world was stacked blocks and
-- balls, and read as a flat green rectangle with a grey dome on it. One function gives an
-- organic coastline, hills that blend into roads, a ridged mountain, a dirt junkyard basin,
-- beaches, a pond and a stream, and materials that follow the shapes. It is also the single
-- source of truth for "is this a road" when WorldBuilder places props.
--
-- Coordinates: +X east (Meadow), -X west (Junkyard), -Z north (mountain + caves),
-- +Z south (beach + Ocean). Sea level 0, land 2.

local WorldTerrain = {}

local M = Enum.Material
local T = workspace.Terrain

local LAND = 2
local RES = 4
local CHUNK = 64 -- columns per chunk side (256 studs)
WorldTerrain.EXTENT = 1280 -- heightfield covers [-EXTENT, EXTENT) on X and Z
WorldTerrain.LAND = LAND

-- ═══ SHAPES ══════════════════════════════════════════════════════════════════

local function smoothstep(a: number, b: number, x: number): number
	local t = math.clamp((x - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end

local function lerp(a: number, b: number, t: number): number
	return a + (b - a) * t
end

local function fbm(x: number, z: number, octaves: number, seed: number): number
	local s, amp, f, norm = 0, 1, 1, 0
	for _ = 1, octaves do
		s += math.noise(x * f, z * f, seed) * amp
		norm += amp
		amp *= 0.5
		f *= 2.03
	end
	return s / norm
end

local function segDist(px: number, pz: number, ax: number, az: number, bx: number, bz: number): number
	local dx, dz = bx - ax, bz - az
	local len2 = dx * dx + dz * dz
	local t = len2 > 0 and math.clamp(((px - ax) * dx + (pz - az) * dz) / len2, 0, 1) or 0
	local qx, qz = ax + dx * t - px, az + dz * t - pz
	return math.sqrt(qx * qx + qz * qz)
end

local function polyDist(pts: { { number } }, x: number, z: number): number
	local best = math.huge
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local d = segDist(x, z, a[1], a[2], b[1], b[2])
		if d < best then
			best = d
		end
	end
	return best
end

-- roads: half-width in studs, and a polyline. WorldBuilder reads these too.
WorldTerrain.roads = {
	{ name = "East", half = 6, pts = { { 60, 0 }, { 150, 0 }, { 230, 8 }, { 300, -6 }, { 365, 4 }, { 440, 0 } } },
	{ name = "West", half = 6, pts = { { -60, 0 }, { -150, 0 }, { -230, -6 }, { -300, 5 }, { -390, 0 } } },
	{ name = "North", half = 6, pts = { { 0, -60 }, { 0, -150 }, { 7, -225 }, { 0, -290 }, { 0, -345 } } },
	{ name = "South", half = 6, pts = { { 0, 60 }, { 0, 150 }, { -7, 240 }, { 0, 330 }, { 0, 395 } } },
	{ name = "MeadowPath", half = 5, pts = { { 440, 0 }, { 472, 58 }, { 500, 116 }, { 528, 146 } } },
	{ name = "FarmLane", half = 5, pts = { { 104, 104 }, { 190, 190 }, { 262, 238 } } },
	{ name = "OrchardLane", half = 5, pts = { { -104, -104 }, { -185, -190 }, { -262, -250 } } },
}
WorldTerrain.RING_R = 140
WorldTerrain.PLOT_R = 205

WorldTerrain.pond = { x = 420, z = 82, r = 26, water = 1.2 }
WorldTerrain.stream = { { 444, 90 }, { 474, 104 }, { 505, 118 }, { 540, 112 }, { 580, 128 }, { 625, 146 }, { 680, 160 } }

WorldTerrain.zones = {
	meadow = { x = 450, z = 0 },
	junk = { x = -450, z = 0, r = 190 },
	mountain = { x = 0, z = -510, r = 310 },
	caves = { x = 0, z = -470 },
	woods = { x = 370, z = -300, r = 170 },
	orchard = { x = -330, z = -300, r = 150 },
	farm = { x0 = 200, z0 = 200, x1 = 390, z1 = 350 },
	dunes = { x = -300, z = 270, r = 150 },
}

-- junk heaps: { x, z, radius, height }
WorldTerrain.heaps = {
	{ -520, 70, 30, 20 }, { -560, -30, 26, 16 }, { -470, -120, 34, 22 }, { -380, 110, 22, 12 },
	{ -600, 120, 28, 18 }, { -350, -80, 20, 11 }, { -500, 150, 24, 14 }, { -610, -110, 32, 24 },
}

local plotAngles = {}
for i = 1, 12 do
	local a = math.rad(15 + (i - 1) * 30)
	plotAngles[i] = { cos = math.cos(a), sin = math.sin(a) }
end

-- distance-to-road (nearest), with the road's half width
function WorldTerrain.roadDistance(x: number, z: number): (number, number)
	local best, half = math.huge, 6
	for _, road in ipairs(WorldTerrain.roads) do
		local d = polyDist(road.pts, x, z)
		if d - road.half < best - half then
			best, half = d, road.half
		end
	end
	-- ring road
	local r = math.sqrt(x * x + z * z)
	local ringD = math.abs(r - WorldTerrain.RING_R)
	if ringD - 7 < best - half then
		best, half = ringD, 7
	end
	return best, half
end

-- is (x, z) on a road / plot / path, with `pad` studs of clearance?
function WorldTerrain.isPaved(x: number, z: number, pad: number): boolean
	local d, half = WorldTerrain.roadDistance(x, z)
	if d < half + pad then
		return true
	end
	local r = math.sqrt(x * x + z * z)
	if r < 64 + pad then
		return true
	end
	return WorldTerrain.plotAt(x, z, pad) ~= nil
end

-- plot index whose lawn (or front path) contains (x, z)
function WorldTerrain.plotAt(x: number, z: number, pad: number): number?
	local r = math.sqrt(x * x + z * z)
	if r < 150 - pad or r > 250 + pad then
		return nil
	end
	for i, p in ipairs(plotAngles) do
		local px, pz = p.cos * WorldTerrain.PLOT_R, p.sin * WorldTerrain.PLOT_R
		local rx, rz = x - px, z - pz
		-- u points from the plot towards the hub, v across it
		local u = -(rx * p.cos + rz * p.sin)
		local v = -rx * p.sin + rz * p.cos
		if math.abs(u) < 33 + pad and math.abs(v) < 33 + pad then
			return i
		end
		if u > 30 and u < 60 + pad and math.abs(v) < 4 + pad then
			return i
		end
	end
	return nil
end

-- normalised coast distance: < 0.9 is land, 1.0 is the waterline, > 1.2 open sea
function WorldTerrain.coastD(x: number, z: number): number
	local ang = math.atan2(z, x)
	local rz = z < 0 and 820 or 470
	local d = math.sqrt((x / 730) ^ 2 + (z / rz) ^ 2)
	return d * (1 + math.noise(math.cos(ang) * 1.6, math.sin(ang) * 1.6, 3.3) * 0.16 + math.noise(math.cos(ang) * 5, math.sin(ang) * 5, 4.1) * 0.03)
end

-- (height, surface material, water level or nil, deep material)
function WorldTerrain.sample(x: number, z: number): (number, Enum.Material, number?, Enum.Material)
	local d = WorldTerrain.coastD(x, z)
	if d > 1.3 then
		return -30, M.Sand, 0, M.Sand
	end
	local r = math.sqrt(x * x + z * z)
	local Z = WorldTerrain.zones

	-- ── natural shape ─────────────────────────────────────────────────────────
	local roll = (fbm(x / 240, z / 240, 3, 1.7) + 0.3) * 8

	local mdx, mdz = x - Z.meadow.x, z - Z.meadow.z
	local mr = math.sqrt(mdx * mdx + mdz * mdz)
	local hills = smoothstep(95, 150, mr) * (1 - smoothstep(235, 300, mr)) * math.max(0, 0.42 + fbm(x / 85, z / 85, 3, 5.1) * 1.7) * 30

	local wdx, wdz = x - Z.woods.x, z - Z.woods.z
	local woodsMask = 1 - smoothstep(Z.woods.r * 0.6, Z.woods.r, math.sqrt(wdx * wdx + wdz * wdz))
	local woods = woodsMask * math.max(0, fbm(x / 70, z / 70, 2, 7.7) + 0.25) * 12

	local ddx, ddz = x - Z.dunes.x, z - Z.dunes.z
	local duneMask = 1 - smoothstep(Z.dunes.r * 0.5, Z.dunes.r, math.sqrt(ddx * ddx + ddz * ddz))
	local dunes = duneMask * (0.5 + 0.5 * math.sin(x / 16 + z / 40 + math.noise(x / 60, z / 60, 9.2) * 4)) * 5

	local odx, odz = x - Z.orchard.x, z - Z.orchard.z
	local orchardMask = 1 - smoothstep(Z.orchard.r * 0.7, Z.orchard.r, math.sqrt(odx * odx + odz * odz))

	local mx, mz = x - Z.mountain.x, z - Z.mountain.z
	local md = math.sqrt(mx * mx + mz * mz)
	local m = math.clamp(1 - md / Z.mountain.r, 0, 1)
	local ridge = (1 - math.abs(math.noise(x / 62, z / 62, 11.3))) ^ 2
	local mount = 190 * m ^ 1.8 + ridge * 38 * m ^ 0.9 + fbm(x / 36, z / 36, 2, 13.1) * 10 * m

	-- ── what must be flat ─────────────────────────────────────────────────────
	local flat = 1 - smoothstep(78, 118, r) -- the town square
	local roadD, roadHalf = WorldTerrain.roadDistance(x, z)
	flat = math.max(flat, 1 - smoothstep(roadHalf + 3, roadHalf + 30, roadD))
	if r > 112 and r < 262 then
		flat = math.max(flat, 0.9) -- the plot ring stays calm
	end
	local plot = WorldTerrain.plotAt(x, z, 6)
	if plot then
		flat = 1
	end
	local jdx, jdz = x - Z.junk.x, z - Z.junk.z
	local jr = math.sqrt(jdx * jdx + jdz * jdz)
	flat = math.max(flat, 1 - smoothstep(Z.junk.r - 10, Z.junk.r + 30, jr))
	local F = Z.farm
	local inFarm = x > F.x0 and x < F.x1 and z > F.z0 and z < F.z1
	if inFarm then
		flat = math.max(flat, 0.95)
	end
	orchardMask *= 1 - flat
	local orchard = orchardMask * math.max(0, fbm(x / 110, z / 110, 2, 21.5) + 0.2) * 6

	local h = LAND + (roll + hills + woods + dunes + orchard + mount) * (1 - flat)
	-- heaps sit ON the flattened junkyard
	for _, hp in ipairs(WorldTerrain.heaps) do
		local hx, hz = x - hp[1], z - hp[2]
		local t = 1 - (hx * hx + hz * hz) / (hp[3] * hp[3])
		if t > 0 then
			h += hp[4] * t * t * (0.85 + math.noise(x / 9, z / 9, 31) * 0.3)
		end
	end
	h = math.max(h, LAND - 1.5 + roll * 0.15)

	-- ── water ─────────────────────────────────────────────────────────────────
	local water: number? = nil
	local P = WorldTerrain.pond
	local pdx, pdz = x - P.x, z - P.z
	local pd = math.sqrt(pdx * pdx + pdz * pdz)
	if pd < P.r + 8 then
		local bowl = 1 - smoothstep(P.r - 10, P.r + 6, pd)
		h = lerp(h, -2.5, bowl)
		if pd < P.r then
			water = P.water
		end
	end
	local sd = polyDist(WorldTerrain.stream, x, z)
	if sd < 9 then
		local cut = 1 - smoothstep(3, 9, sd)
		h = lerp(h, -0.6, cut)
		if sd < 5 then
			water = water or 1.0
		end
	end

	-- ── coast ─────────────────────────────────────────────────────────────────
	local coast = smoothstep(0.9, 1.0, d)
	h = lerp(h, -3, coast)
	if d > 1.0 then
		h = lerp(-3, -30, smoothstep(1.0, 1.2, d))
	end
	if h < 0 then
		water = math.max(water or 0, 0)
	end

	-- ── materials ─────────────────────────────────────────────────────────────
	local mat = M.Grass
	local deep = M.Ground
	if woodsMask > 0.35 or (hills > 14 and math.noise(x / 40, z / 40, 17) > -0.1) then
		mat = M.LeafyGrass
	end
	if orchardMask > 0.3 then
		mat = M.LeafyGrass
	end
	local mountainH = mount * (1 - flat)
	if mountainH > 16 + math.noise(x / 30, z / 30, 19) * 10 then
		mat = mountainH > 95 and M.Slate or M.Rock
		deep = M.Rock
	end
	if duneMask > 0.35 and (dunes > 1.5 or math.noise(x / 25, z / 25, 23) > 0) then
		mat = M.Sand
	end
	if jr < Z.junk.r + 6 then
		-- a few broad oily patches, not camouflage
		mat = math.noise(x / 55, z / 55, 27) > 0.3 and M.Mud or M.Ground
	end
	if inFarm then
		-- crop fields: dirt rows inside three fenced fields
		local fx = (x - F.x0) % 64
		local fz = (z - F.z0) % 50
		if fx > 8 and fx < 56 and fz > 8 and fz < 42 then
			mat = M.Ground
		end
	end
	-- sand: the southern beach, the rim of every coast, and anything low right by the sea
	local beach = z > 338 + math.noise(x / 90, 0.5, 5.5) * 24
	if beach or d > 0.9 or (h < 1.2 and d > 0.8) then
		mat = M.Sand
		deep = M.Sand
	end
	if pd < P.r + 3 and h < 2 then
		mat = M.Sand
	end
	if sd < 5 then
		mat = M.Mud
	end
	if plot then
		mat = M.Grass
		if WorldTerrain.plotAt(x, z, 0) and math.abs(math.sqrt(x * x + z * z) - WorldTerrain.PLOT_R) > 33 then
			mat = M.Ground -- the little path out to the ring road
		end
	end
	if roadD < roadHalf then
		mat = r < 80 and M.Cobblestone or M.Ground
		if h < 1.2 then
			mat = M.Sand
		end
	end
	if r < 62 then
		mat = M.Cobblestone
	end
	return h, mat, water, deep
end

-- ═══ WRITING ═════════════════════════════════════════════════════════════════

local Y0 = -40

-- Writes one row (`band` 0..N-1) of chunks. Returns the number of voxels written.
function WorldTerrain.writeBand(band: number): number
	local count = 0
	local nChunks = math.floor(2 * WorldTerrain.EXTENT / (CHUNK * RES))
	local cz0 = -WorldTerrain.EXTENT + band * CHUNK * RES
	for ci = 0, nChunks - 1 do
		local cx0 = -WorldTerrain.EXTENT + ci * CHUNK * RES
		local hs = table.create(CHUNK * CHUNK)
		local ms = table.create(CHUNK * CHUNK)
		local ws = table.create(CHUNK * CHUNK)
		local ds = table.create(CHUNK * CHUNK)
		local top = Y0 + 8
		for i = 0, CHUNK - 1 do
			for k = 0, CHUNK - 1 do
				local h, mat, water, deep = WorldTerrain.sample(cx0 + i * RES + RES / 2, cz0 + k * RES + RES / 2)
				local idx = i * CHUNK + k + 1
				hs[idx], ms[idx], ws[idx], ds[idx] = h, mat, water or false, deep
				top = math.max(top, h, water or -math.huge)
			end
		end
		local yTop = math.ceil((top + 6 - Y0) / RES) * RES + Y0
		local ny = (yTop - Y0) // RES
		local mats = table.create(CHUNK)
		local occ = table.create(CHUNK)
		for i = 1, CHUNK do
			local mi = table.create(ny)
			local oi = table.create(ny)
			for j = 1, ny do
				mi[j] = table.create(CHUNK, M.Air)
				oi[j] = table.create(CHUNK, 0)
			end
			mats[i], occ[i] = mi, oi
		end
		for i = 1, CHUNK do
			for k = 1, CHUNK do
				local idx = (i - 1) * CHUNK + k
				local h, mat, water, deep = hs[idx], ms[idx], ws[idx], ds[idx]
				for j = 1, ny do
					local yb = Y0 + (j - 1) * RES
					local yt = yb + RES
					if yt <= h then
						mats[i][j][k] = (h - yt) < 6 and mat or deep
						occ[i][j][k] = 1
					elseif yb < h then
						mats[i][j][k] = mat
						occ[i][j][k] = math.max(0.12, (h - yb) / RES)
					elseif water and yb < water - 0.5 then
						mats[i][j][k] = M.Water
						occ[i][j][k] = 1
					end
				end
			end
		end
		local region = Region3.new(Vector3.new(cx0, Y0, cz0), Vector3.new(cx0 + CHUNK * RES, yTop, cz0 + CHUNK * RES))
		T:WriteVoxels(region, RES, mats, occ)
		count += CHUNK * CHUNK * ny
	end
	return count
end

function WorldTerrain.bands(): number
	return math.floor(2 * WorldTerrain.EXTENT / (CHUNK * RES))
end

-- the open sea beyond the heightfield, so the horizon is water in every direction
function WorldTerrain.sea()
	local E = WorldTerrain.EXTENT
	local S = 3000
	for _, rect in ipairs({
		{ -S, -S, S, -E }, { -S, E, S, S }, { -S, -E, -E, E }, { E, -E, S, E },
	}) do
		local x0, z0, x1, z1 = rect[1], rect[2], rect[3], rect[4]
		T:FillBlock(CFrame.new((x0 + x1) / 2, -16, (z0 + z1) / 2), Vector3.new(x1 - x0, 32, z1 - z0), M.Water)
		T:FillBlock(CFrame.new((x0 + x1) / 2, -34, (z0 + z1) / 2), Vector3.new(x1 - x0, 4, z1 - z0), M.Sand)
	end
end

return WorldTerrain
