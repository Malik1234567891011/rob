--!strict
-- Shared.Config.Biomes — SPEC §13 hub + biome islands (NOT a seamless continent; mobile
-- performance matters). Each biome declares its palette, spawn table and gates, so adding
-- a biome is configuration. Geometry is laid out by src/server/WorldBuilder.luau, which
-- places named markers; runtime systems only ever read markers.
--
-- Layout (studs): hub at the origin, 12 player plots on a ring (r = 200), biomes beyond:
--   Meadow east · Junkyard west · Crystal Caves north · Ocean south (Update 1)
--   Strange Zone floats high above the north horizon, visible from every plot.

local Biomes = {}

Biomes.all = {
	Hub = {
		display = "Town Square", emoji = "⛲", order = 0,
		center = { 0, 0, 0 }, radius = 75,
		spawnTable = { "Apple", "Cookie", "Daisy", "Pebble", "Stick", "Sock", "Crayon", "Cheese" },
		maxProps = 10,
		blurb = "Where everyone meets. The Parade happens here.",
	},
	Meadow = {
		display = "Meadow", emoji = "🌼", order = 1,
		center = { 450, 0, 0 }, radius = 180,
		spawnTable = {
			"Apple", "Apple", "Strawberry", "Blueberry", "Carrot", "Daisy", "Daisy", "Sunflower",
			"Clover", "Beetle", "Butterfly", "Worm", "Stick", "Acorn", "MudClump", "Pebble",
			"BouncyBall", "ToyBlock", "Honeycomb", "Mushroom", "Feather", "Watermelon", "Pumpkin",
			"RubberDuck", "IceCube", "Fish", "Slime", "Cookie", "Cupcake", "Balloon", "Cheese",
		},
		maxProps = 48,
		traits = { "Nature", "Sweet", "Energy", "Round" },
		blurb = "Fruit, flowers, insects, wood, mud, toys.",
	},
	Junkyard = {
		display = "Junkyard", emoji = "🔩", order = 2,
		center = { -450, 0, 0 }, radius = 180,
		spawnTable = {
			"Battery", "Battery", "Gear", "ScrapMetal", "ScrapMetal", "Magnet", "OilCan", "BrokenTV",
			"Spring", "Bolt", "Wire", "Tire", "SodaCan", "Lightbulb", "CircuitBoard", "Clock",
			"Toaster", "TrafficCone", "Fan", "Pebble", "Coal", "Bone", "CursedSandwich", "RubberDuck",
			"Slime", "Sock", "Crayon", "Bell", "RubberBoot",
		},
		maxProps = 44,
		traits = { "Metal", "Electric", "Artificial", "Heavy" },
		blurb = "Scrap, gears, batteries, magnets, oil, televisions.",
	},
	CrystalCaves = {
		display = "Crystal Caves", emoji = "💎", order = 3,
		center = { 0, 0, -470 }, radius = 150,
		spawnTable = {
			"CrystalShard", "CrystalShard", "Mushroom", "Amethyst", "Glowworm", "Geode", "Fossil",
			"CaveMoss", "Glowcap", "Bone", "Coal", "Obsidian", "IceCube", "MoonMushroom",
		},
		maxProps = 34,
		traits = { "Crystal", "Dark", "Mystic", "Ancient" },
		blurb = "Crystals, mushrooms, ancient fossils, glowworms, minerals.",
	},
	Ocean = {
		display = "The Ocean", emoji = "🌊", order = 4, update = 1,
		center = { 0, 0, 470 }, radius = 170,
		spawnTable = { "Fish", "Fish", "Seashell", "Kelp", "Starfish", "Crab", "Coral", "Jellyfish", "Pearl", "SunkenCoin", "RubberDuck", "IceCube" },
		maxProps = 36,
		traits = { "Water", "Flexible", "Shiny" },
		blurb = "SOMETHING IS IN THE OCEAN.",
	},
	-- config-ready, held back as later seasons (SPEC §49, §76)
	Volcano = {
		display = "Volcano", emoji = "🌋", order = 5, locked = true,
		center = { 0, 0, 0 }, radius = 0,
		spawnTable = { "Coal", "Obsidian", "LavaFruit" }, maxProps = 0,
		traits = { "Fire", "Stone", "Heavy" },
		blurb = "Coal, obsidian, lava fruit, fire beetles.",
	},
	SkyIslands = {
		display = "Sky Islands", emoji = "☁️", order = 6, locked = true,
		center = { 0, 0, 0 }, radius = 0,
		spawnTable = { "CloudBerry", "Feather", "StarFragment" }, maxProps = 0,
		traits = { "Air", "Celestial" },
		blurb = "Cloud berries, feathers, star fragments, wind flowers.",
	},
	-- SPEC §13: players glimpse the Strange Zone very early.
	StrangeZone = {
		display = "The Strange Zone", emoji = "🌀", order = 99, locked = true, glimpseOnly = true,
		center = { 0, 240, -820 }, radius = 60,
		spawnTable = { "MoonMushroom", "StarFragment", "Meteorite" }, maxProps = 0,
		traits = { "Mystic", "Dark", "Celestial" },
		blurb = "Reality behaves improperly here.",
	},
}

Biomes.order = { "Hub", "Meadow", "Junkyard", "CrystalCaves", "Ocean", "Volcano", "SkyIslands", "StrangeZone" }

-- ═══ ABILITY GATES (SPEC §11 — the creature you build changes your route) ════
-- Each gate is a marker `Gate_<id>` placed by the WorldBuilder. `abilities` must ALL be
-- present — from you or, for co-op gates, from party members standing nearby (SPEC §20).
-- `kind` decides what opening looks like: prompt gates vanish; zone gates (Ghost, Tiny,
-- Plant, Sticky, Aquatic, Light) are geometry the client lets you pass, and the reward
-- chest sits beyond them.
Biomes.gates = {
	{ id = "MeadowBoulder", biome = "Meadow", abilities = { "Giant" }, asset = "Boulder_Big",
	  reward = { "Watermelon", "Pumpkin", "Clover", "CloudBerry" },
	  prompt = "A boulder. Far too heavy to move.", success = "Your monster shoves it aside!" },
	{ id = "MeadowRoots", biome = "Meadow", abilities = { "Tiny" }, asset = "RootTunnel", zone = true,
	  reward = { "Honeycomb", "Beetle", "Clover", "Acorn" },
	  prompt = "A gap in the roots. Something small could fit.", success = "It squeezes through." },
	{ id = "MeadowHollow", biome = "Meadow", abilities = { "Light" }, asset = "DarkHollow", zone = true,
	  reward = { "Mushroom", "CrystalShard", "Glowworm", "MoonMushroom" },
	  prompt = "A dark hollow. You cannot see in.", success = "Its glow fills the hollow." },
	{ id = "MeadowVines", biome = "Meadow", abilities = { "Plant" }, asset = "VineWall",
	  reward = { "Sunflower", "Butterfly", "Clover", "CloudBerry" },
	  prompt = "Bare rock. If only something would grow here.", success = "Vines burst up the rock!" },
	{ id = "JunkGenerator", biome = "Junkyard", abilities = { "Electric" }, asset = "Generator_Dead",
	  reward = { "BrokenTV", "CircuitBoard", "Toaster", "Lightbulb" },
	  prompt = "A dead generator.", success = "It sparks to life. The vault door opens!" },
	{ id = "JunkTowers", biome = "Junkyard", abilities = { "Glide" }, asset = "ScrapTower_B", zone = true,
	  reward = { "Lightbulb", "Fan", "Magnet", "Bell" },
	  prompt = "The far tower. Too far to jump.", success = "It glides across." },
	{ id = "JunkCracks", biome = "Junkyard", abilities = { "Burrow" }, asset = "CrackedGround",
	  reward = { "Bone", "Coal", "Fossil", "SunkenCoin" },
	  prompt = "Cracked earth. Something is buried here.", success = "It digs straight down!" },
	{ id = "JunkWall", biome = "Junkyard", abilities = { "Sticky" }, asset = "Container_Shipping", zone = true,
	  reward = { "Spring", "Wire", "Gear", "Magnet" },
	  prompt = "A tall stack of containers.", success = "It climbs right up." },
	-- CO-OP (SPEC §20: "Giant moves the broken generator, Electric activates it")
	{ id = "JunkBigMachine", biome = "Junkyard", abilities = { "Giant", "Electric" }, asset = "Magnet_Crane", coop = true,
	  reward = { "BrokenTV", "StarFragment", "CircuitBoard", "Meteorite", "Magnet" },
	  prompt = "A jammed crane. It needs lifting AND power.", success = "Together you got it running!" },
	{ id = "CaveGhost", biome = "CrystalCaves", abilities = { "Ghost" }, asset = "GhostBarrier", zone = true,
	  reward = { "MoonMushroom", "Amethyst", "Glowcap", "Obsidian" },
	  prompt = "A shimmering barrier. Solid to anything alive.", success = "It drifts through." },
	{ id = "CaveDeep", biome = "CrystalCaves", abilities = { "Light" }, asset = "Crystal_Big", zone = true,
	  reward = { "Geode", "Amethyst", "CrystalShard", "Fossil" },
	  prompt = "Pitch dark. Something glitters deeper in.", success = "Its light shows the way." },
	{ id = "CaveHeat", biome = "CrystalCaves", abilities = { "Heatproof" }, asset = "Crystal_Cluster_Pink", zone = true,
	  reward = { "Obsidian", "Coal", "LavaFruit", "Geode" },
	  prompt = "The floor here is scalding hot.", success = "It strolls over the heat." },
	{ id = "CaveCoop", biome = "CrystalCaves", abilities = { "Burrow", "Light" }, asset = "CaveRock_C", coop = true,
	  reward = { "StarFragment", "Meteorite", "Amethyst", "MoonMushroom", "Geode" },
	  prompt = "A rockfall over a glowing hole. Dig AND light.", success = "Together you uncovered it!" },
	{ id = "OceanReef", biome = "Ocean", abilities = { "Aquatic" }, asset = "Coral", zone = true, update = 1,
	  reward = { "Pearl", "SunkenCoin", "Jellyfish", "Coral" },
	  prompt = "The reef drops away into deep water.", success = "It dives right in." },
}

function Biomes.get(id: string)
	return Biomes.all[id]
end

function Biomes.gatesFor(biome: string)
	local out = {}
	for _, g in ipairs(Biomes.gates) do
		if g.biome == biome then
			table.insert(out, g)
		end
	end
	return out
end

return Biomes
