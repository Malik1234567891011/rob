--!strict
-- Shared.Config.Ingredients — SPEC §6 "Food is not really food", §69 data shape.
--
-- Adding watermelon must not require engineering. Everything an ingredient needs
-- lives in this table: influence vector, rarity, which biomes spawn it, the eat
-- reaction, and a procedural prop spec (no external assets, so it all works now).
--
-- `model.shape` ∈ Ball | Block | Cylinder | Wedge
-- `model.topper` is an optional second part (apple stems, bottle caps, antennae).

local Ingredients = {}

local function ing(t)
	return t
end

Ingredients.all = {
	-- ══ MEADOW ══════════════════════════════════════════════════════════════
	Apple = ing{
		display = "Apple", emoji = "🍎", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 3, Sweet = 2, Round = 1, Energy = 1 },
		reaction = { animation = "BigBite", sfx = "JuicyCrunch" },
		model = { shape = "Ball", size = {1.5,1.6,1.5}, color = 0xE03A3A,
		          topper = { shape = "Cylinder", size = {0.18,0.6,0.18}, color = 0x6B4A2A, offset = {0,0.9,0} } },
	},
	Strawberry = ing{
		display = "Strawberry", emoji = "🍓", rarity = "Common", biomes = { "Meadow" },
		influences = { Sweet = 4, Nature = 2, Round = 1 },
		reaction = { animation = "Nibble", sfx = "JuicyCrunch" },
		model = { shape = "Ball", size = {1.1,1.4,1.1}, color = 0xFF3355,
		          topper = { shape = "Block", size = {0.9,0.15,0.9}, color = 0x4FA83D, offset = {0,0.75,0} } },
	},
	Watermelon = ing{
		display = "Watermelon", emoji = "🍉", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Water = 3, Sweet = 2, Nature = 1, Round = 2 },
		reaction = { animation = "BigBite", sfx = "JuicyCrunch" },
		model = { shape = "Ball", size = {2.6,2.0,2.6}, color = 0x2F7D32 },
	},
	Blueberry = ing{
		display = "Blueberry", emoji = "🫐", rarity = "Common", biomes = { "Meadow" },
		influences = { Sweet = 2, Nature = 2, Round = 2, Night = 1 },
		reaction = { animation = "Nibble", sfx = "Pop" },
		model = { shape = "Ball", size = {0.8,0.8,0.8}, color = 0x4653B0 },
	},
	Carrot = ing{
		display = "Carrot", emoji = "🥕", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 3, Energy = 2, Sweet = 1 },
		reaction = { animation = "Crunch", sfx = "HardCrunch" },
		model = { shape = "Cylinder", size = {0.7,2.2,0.7}, color = 0xE8761F,
		          topper = { shape = "Block", size = {0.5,0.7,0.5}, color = 0x4FA83D, offset = {0,1.3,0} } },
	},
	Pumpkin = ing{
		display = "Pumpkin", emoji = "🎃", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Nature = 3, Round = 3, Heavy = 2, Night = 1 },
		reaction = { animation = "BigBite", sfx = "SoftSquish" },
		model = { shape = "Ball", size = {2.4,2.0,2.4}, color = 0xE07B1F },
	},
	Daisy = ing{
		display = "Daisy", emoji = "🌼", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 3, Sweet = 1, Air = 1 },
		reaction = { animation = "Nibble", sfx = "SoftSquish" },
		model = { shape = "Cylinder", size = {1.0,0.2,1.0}, color = 0xFFF3C4,
		          topper = { shape = "Ball", size = {0.4,0.4,0.4}, color = 0xFFD52E, offset = {0,0.15,0} } },
	},
	Sunflower = ing{
		display = "Sunflower", emoji = "🌻", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Nature = 4, Celestial = 1, Energy = 1, Round = 1 },
		reaction = { animation = "Nibble", sfx = "SoftSquish" },
		model = { shape = "Cylinder", size = {1.6,0.25,1.6}, color = 0xFFC93D,
		          topper = { shape = "Cylinder", size = {0.8,0.3,0.8}, color = 0x6B4A2A, offset = {0,0.2,0} } },
	},
	Clover = ing{
		display = "Four-Leaf Clover", emoji = "🍀", rarity = "Rare", biomes = { "Meadow" },
		influences = { Nature = 4, Mystic = 2, Sweet = 1 },
		reaction = { animation = "Nibble", sfx = "Sparkle" },
		model = { shape = "Ball", size = {1.0,0.3,1.0}, color = 0x35C24A },
	},
	Beetle = ing{
		display = "Shiny Beetle", emoji = "🪲", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Nature = 2, Shiny = 3, Energy = 2 },
		reaction = { animation = "Crunch", sfx = "HardCrunch" },
		model = { shape = "Ball", size = {1.0,0.7,1.4}, color = 0x2E7D6B, material = "Glass" },
	},
	Butterfly = ing{
		display = "Butterfly", emoji = "🦋", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Air = 4, Nature = 2, Sweet = 1, Shiny = 1 },
		reaction = { animation = "Snap", sfx = "Whoosh" },
		model = { shape = "Block", size = {1.6,0.1,1.0}, color = 0x6FA8FF },
	},
	Worm = ing{
		display = "Wiggly Worm", emoji = "🪱", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 2, Flexible = 4, Slimy = 2 },
		reaction = { animation = "Slurp", sfx = "Slurp" },
		model = { shape = "Cylinder", size = {0.4,1.8,0.4}, color = 0xE08A9B },
	},
	Stick = ing{
		display = "Stick", emoji = "🪵", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 2, Heavy = 1 },
		reaction = { animation = "Crunch", sfx = "WoodSnap" },
		model = { shape = "Cylinder", size = {0.35,2.6,0.35}, color = 0x7A5230 },
	},
	Acorn = ing{
		display = "Acorn", emoji = "🌰", rarity = "Common", biomes = { "Meadow" },
		influences = { Nature = 3, Round = 2, Ancient = 1 },
		reaction = { animation = "Crunch", sfx = "HardCrunch" },
		model = { shape = "Ball", size = {0.9,1.1,0.9}, color = 0x8C6239 },
	},
	MudClump = ing{
		display = "Mud Clump", emoji = "🟤", rarity = "Common", biomes = { "Meadow" },
		influences = { Stone = 2, Slimy = 3, Heavy = 2 },
		reaction = { animation = "Slurp", sfx = "SoftSquish" },
		model = { shape = "Ball", size = {1.4,1.0,1.4}, color = 0x5C4433 },
	},
	Pebble = ing{
		display = "Pebble", emoji = "🪨", rarity = "Common", biomes = { "Meadow", "Junkyard" },
		influences = { Stone = 4, Heavy = 3 },
		reaction = { animation = "Crunch", sfx = "RockCrack" },
		model = { shape = "Ball", size = {1.1,0.9,1.2}, color = 0x8C8478 },
	},
	RubberDuck = ing{
		display = "Rubber Duck", emoji = "🦆", rarity = "Rare", biomes = { "Meadow", "Junkyard" },
		influences = { Toy = 5, Water = 1, Silly = 4, Shiny = 2 },
		reaction = { animation = "Squeak", sfx = "Squeak" },
		model = { shape = "Ball", size = {1.3,1.2,1.7}, color = 0xFFD52E,
		          topper = { shape = "Ball", size = {0.8,0.8,0.8}, color = 0xFFD52E, offset = {0,0.7,0.4} } },
	},
	BouncyBall = ing{
		display = "Bouncy Ball", emoji = "🔴", rarity = "Common", biomes = { "Meadow" },
		influences = { Toy = 3, Round = 4, Energy = 2 },
		reaction = { animation = "Snap", sfx = "Boing" },
		model = { shape = "Ball", size = {1.2,1.2,1.2}, color = 0xFF4D4D },
	},
	ToyBlock = ing{
		display = "Toy Block", emoji = "🧱", rarity = "Common", biomes = { "Meadow" },
		influences = { Toy = 4, Artificial = 2, Heavy = 1 },
		reaction = { animation = "Crunch", sfx = "PlasticClack" },
		model = { shape = "Block", size = {1.2,1.2,1.2}, color = 0x3D7BE0 },
	},
	Honeycomb = ing{
		display = "Honeycomb", emoji = "🍯", rarity = "Uncommon", biomes = { "Meadow" },
		influences = { Sweet = 5, Nature = 2, Slimy = 2, Shiny = 1 },
		reaction = { animation = "Slurp", sfx = "Slurp" },
		model = { shape = "Block", size = {1.5,0.8,1.5}, color = 0xE8A81F, material = "Glass" },
	},
	Mushroom = ing{
		display = "Mushroom", emoji = "🍄", rarity = "Common", biomes = { "Meadow", "CrystalCaves" },
		influences = { Fungal = 5, Mystic = 1, Night = 1 },
		reaction = { animation = "Nibble", sfx = "SoftSquish" },
		model = { shape = "Cylinder", size = {0.5,1.0,0.5}, color = 0xF0E6D2,
		          topper = { shape = "Ball", size = {1.6,0.9,1.6}, color = 0xD1443F, offset = {0,0.55,0} } },
	},
	Feather = ing{
		display = "Feather", emoji = "🪶", rarity = "Common", biomes = { "Meadow", "SkyIslands" },
		influences = { Air = 4, Flexible = 2, Shiny = 1 },
		reaction = { animation = "Snap", sfx = "Whoosh" },
		model = { shape = "Block", size = {0.35,1.8,0.12}, color = 0xF2F2F2 },
	},

	-- ══ JUNKYARD ════════════════════════════════════════════════════════════
	Battery = ing{
		display = "Battery", emoji = "🔋", rarity = "Common", biomes = { "Junkyard" },
		influences = { Electric = 5, Metal = 2, Artificial = 2, Toxic = 1 },
		reaction = { animation = "Zap", sfx = "ElectricFizz", color = 0xFFD52E },
		model = { shape = "Cylinder", size = {0.9,1.8,0.9}, color = 0x2E2E2E, material = "Metal",
		          topper = { shape = "Cylinder", size = {0.4,0.25,0.4}, color = 0xC9A227, offset = {0,1.0,0} } },
	},
	Gear = ing{
		display = "Rusty Gear", emoji = "⚙️", rarity = "Common", biomes = { "Junkyard" },
		influences = { Metal = 4, Artificial = 3, Heavy = 2 },
		reaction = { animation = "Crunch", sfx = "MetalClang" },
		model = { shape = "Cylinder", size = {1.8,0.35,1.8}, color = 0x8A7358, material = "Metal" },
	},
	ScrapMetal = ing{
		display = "Scrap Metal", emoji = "🔩", rarity = "Common", biomes = { "Junkyard" },
		influences = { Metal = 5, Heavy = 3, Artificial = 1 },
		reaction = { animation = "Crunch", sfx = "MetalClang" },
		model = { shape = "Wedge", size = {1.6,1.0,1.4}, color = 0x9AA0A6, material = "Metal" },
	},
	Magnet = ing{
		display = "Magnet", emoji = "🧲", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Metal = 4, Electric = 2, Mystic = 1, Heavy = 1 },
		reaction = { animation = "Snap", sfx = "MetalClang" },
		model = { shape = "Block", size = {1.4,1.4,0.6}, color = 0xD02F2F, material = "Metal" },
	},
	OilCan = ing{
		display = "Oil Can", emoji = "🛢️", rarity = "Common", biomes = { "Junkyard" },
		influences = { Artificial = 3, Toxic = 4, Slimy = 3, Dark = 1 },
		reaction = { animation = "Slurp", sfx = "Glug" },
		model = { shape = "Cylinder", size = {1.3,1.9,1.3}, color = 0x1F2A33, material = "Metal" },
	},
	BrokenTV = ing{
		display = "Broken Television", emoji = "📺", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Artificial = 5, Electric = 3, Metal = 2, Heavy = 2 },
		reaction = { animation = "BigBite", sfx = "StaticBurst", color = 0x9BE8FF },
		model = { shape = "Block", size = {2.2,1.8,1.8}, color = 0x4A4A4A,
		          topper = { shape = "Block", size = {1.6,1.2,0.1}, color = 0x8FD6FF, offset = {0,0,-0.95} } },
	},
	Spring = ing{
		display = "Spring", emoji = "🌀", rarity = "Common", biomes = { "Junkyard" },
		influences = { Metal = 3, Energy = 3, Flexible = 3 },
		reaction = { animation = "Snap", sfx = "Boing" },
		model = { shape = "Cylinder", size = {0.9,1.6,0.9}, color = 0xB0B7BD, material = "Metal" },
	},
	Bolt = ing{
		display = "Bolt", emoji = "🔧", rarity = "Common", biomes = { "Junkyard" },
		influences = { Metal = 4, Heavy = 1, Artificial = 1 },
		reaction = { animation = "Crunch", sfx = "MetalClang" },
		model = { shape = "Cylinder", size = {0.5,1.3,0.5}, color = 0x8E959B, material = "Metal" },
	},
	Wire = ing{
		display = "Tangled Wire", emoji = "🔌", rarity = "Common", biomes = { "Junkyard" },
		influences = { Electric = 3, Artificial = 3, Flexible = 3 },
		reaction = { animation = "Slurp", sfx = "ElectricFizz" },
		model = { shape = "Cylinder", size = {0.3,2.2,0.3}, color = 0xD03A3A },
	},
	Tire = ing{
		display = "Old Tire", emoji = "🛞", rarity = "Common", biomes = { "Junkyard" },
		influences = { Artificial = 3, Heavy = 4, Round = 3, Toy = 1 },
		reaction = { animation = "BigBite", sfx = "RubberThud" },
		model = { shape = "Cylinder", size = {2.6,0.9,2.6}, color = 0x232323 },
	},
	SodaCan = ing{
		display = "Soda Can", emoji = "🥤", rarity = "Common", biomes = { "Junkyard" },
		influences = { Artificial = 3, Sweet = 3, Metal = 2, Energy = 2 },
		reaction = { animation = "Crunch", sfx = "MetalCrunch" },
		model = { shape = "Cylinder", size = {0.9,1.5,0.9}, color = 0xD8322F, material = "Metal" },
	},
	Lightbulb = ing{
		display = "Lightbulb", emoji = "💡", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Electric = 4, Shiny = 3, Artificial = 2, Celestial = 1 },
		reaction = { animation = "Snap", sfx = "GlassTink", color = 0xFFF0A8 },
		model = { shape = "Ball", size = {1.2,1.4,1.2}, color = 0xFFF6D6, material = "Glass",
		          topper = { shape = "Cylinder", size = {0.6,0.5,0.6}, color = 0xB0B7BD, offset = {0,-0.8,0} } },
	},
	CircuitBoard = ing{
		display = "Circuit Board", emoji = "🖥️", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Artificial = 5, Electric = 4, Metal = 2, Mystic = 1 },
		reaction = { animation = "Crunch", sfx = "StaticBurst" },
		model = { shape = "Block", size = {2.0,0.15,1.4}, color = 0x1E6E42 },
	},
	Clock = ing{
		display = "Broken Clock", emoji = "🕰️", rarity = "Rare", biomes = { "Junkyard" },
		influences = { Artificial = 3, Ancient = 4, Metal = 2, Mystic = 2 },
		reaction = { animation = "Crunch", sfx = "GlassTink" },
		model = { shape = "Cylinder", size = {1.8,0.4,1.8}, color = 0xE8DCC0,
		          topper = { shape = "Block", size = {0.12,0.7,0.06}, color = 0x2E2E2E, offset = {0,0.25,0} } },
	},
	Toaster = ing{
		display = "Toaster", emoji = "🍞", rarity = "Rare", biomes = { "Junkyard" },
		influences = { Artificial = 4, Metal = 4, Electric = 3, Silly = 3, Heavy = 1 },
		reaction = { animation = "BigBite", sfx = "MetalClang" },
		model = { shape = "Block", size = {2.0,1.4,1.2}, color = 0xC9CDD1, material = "Metal" },
	},
	TrafficCone = ing{
		display = "Traffic Cone", emoji = "🚧", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Artificial = 4, Silly = 3, Toy = 2 },
		reaction = { animation = "BigBite", sfx = "PlasticClack" },
		model = { shape = "Cylinder", size = {1.6,2.2,1.6}, color = 0xF25C1F },
	},
	Fan = ing{
		display = "Desk Fan", emoji = "🌬️", rarity = "Uncommon", biomes = { "Junkyard" },
		influences = { Air = 5, Artificial = 3, Electric = 2, Metal = 1 },
		reaction = { animation = "Snap", sfx = "Whoosh" },
		model = { shape = "Cylinder", size = {2.0,0.5,2.0}, color = 0x6E7A85, material = "Metal" },
	},

	-- ══ CROSS-BIOME / SPECIAL ═══════════════════════════════════════════════
	IceCube = ing{
		display = "Ice Cube", emoji = "🧊", rarity = "Common", biomes = { "Meadow", "Junkyard" },
		influences = { Cold = 4, Water = 1, Crystal = 1 },
		reaction = { animation = "Crunch", sfx = "IceCrack", color = 0xBFE9FF },
		model = { shape = "Block", size = {1.1,1.1,1.1}, color = 0xCCEEFF, material = "Glass" },
	},
	Bone = ing{
		display = "Old Bone", emoji = "🦴", rarity = "Uncommon", biomes = { "Junkyard", "CrystalCaves" },
		influences = { Ancient = 4, Stone = 2, Dark = 1, Heavy = 1 },
		reaction = { animation = "Crunch", sfx = "BoneCrack" },
		model = { shape = "Cylinder", size = {0.5,2.2,0.5}, color = 0xEDE4CE,
		          topper = { shape = "Ball", size = {0.9,0.9,0.9}, color = 0xEDE4CE, offset = {0,1.1,0} } },
	},
	CrystalShard = ing{
		display = "Crystal Shard", emoji = "💎", rarity = "Rare", biomes = { "CrystalCaves" },
		influences = { Crystal = 5, Shiny = 3, Mystic = 2 },
		reaction = { animation = "Crunch", sfx = "CrystalChime", color = 0x9BE8FF },
		model = { shape = "Wedge", size = {0.9,2.0,0.9}, color = 0x8FE3FF, material = "Glass" },
	},
	Fish = ing{
		display = "Fish", emoji = "🐟", rarity = "Common", biomes = { "Ocean", "Meadow" },
		influences = { Water = 5, Flexible = 2, Shiny = 1, Slimy = 1 },
		reaction = { animation = "Slurp", sfx = "WetSlap", color = 0x3FA9F5 },
		model = { shape = "Ball", size = {1.0,0.8,2.2}, color = 0x5AA9D6,
		          topper = { shape = "Wedge", size = {0.15,0.9,0.9}, color = 0x4A93BD, offset = {0,0.2,-1.2} } },
	},
	Coal = ing{
		display = "Coal", emoji = "⚫", rarity = "Common", biomes = { "Volcano", "Junkyard" },
		influences = { Fire = 3, Stone = 3, Dark = 2, Heavy = 2 },
		reaction = { animation = "Crunch", sfx = "RockCrack" },
		model = { shape = "Ball", size = {1.2,1.0,1.2}, color = 0x1A1A1A },
	},
	LavaFruit = ing{
		display = "Lava Fruit", emoji = "🌶️", rarity = "Rare", biomes = { "Volcano" },
		influences = { Fire = 5, Sweet = 2, Energy = 3, Round = 1 },
		reaction = { animation = "BigBite", sfx = "FireWhoosh", color = 0xFF5A1F },
		model = { shape = "Ball", size = {1.4,1.6,1.4}, color = 0xFF4A17, material = "Neon" },
	},
	StarFragment = ing{
		display = "Star Fragment", emoji = "⭐", rarity = "Exotic", biomes = { "SkyIslands" },
		influences = { Celestial = 6, Shiny = 3, Mystic = 2, Air = 1 },
		reaction = { animation = "Snap", sfx = "Sparkle", color = 0xFFF0A8 },
		model = { shape = "Ball", size = {1.2,1.2,1.2}, color = 0xFFF3B0, material = "Neon" },
	},
	MoonMushroom = ing{
		display = "Moon Mushroom", emoji = "🌙", rarity = "Exotic", biomes = { "CrystalCaves" },
		influences = { Fungal = 4, Celestial = 4, Night = 5, Mystic = 3 },
		reaction = { animation = "Nibble", sfx = "Sparkle", color = 0xC7C2FF },
		model = { shape = "Cylinder", size = {0.5,1.2,0.5}, color = 0xE4E0FF,
		          topper = { shape = "Ball", size = {1.7,1.0,1.7}, color = 0x8E86E0, offset = {0,0.65,0}, material = "Neon" } },
	},
	Meteorite = ing{
		display = "Meteorite", emoji = "☄️", rarity = "Exotic", biomes = { "Event" },
		influences = { Celestial = 5, Stone = 4, Fire = 3, Ancient = 3, Heavy = 3 },
		reaction = { animation = "BigBite", sfx = "Impact", color = 0xFFA63D },
		model = { shape = "Ball", size = {2.2,2.0,2.2}, color = 0x3A332E },
	},
	CursedSandwich = ing{
		display = "Cursed Sandwich", emoji = "🥪", rarity = "Rare", biomes = { "Junkyard" },
		influences = { Toxic = 5, Dark = 4, Silly = 4, Fungal = 2, Mystic = 2 },
		reaction = { animation = "Slurp", sfx = "WrongNoise", color = 0x4A4260 },
		model = { shape = "Block", size = {1.6,0.9,1.6}, color = 0xC9A86A },
	},
	Slime = ing{
		display = "Wild Slime", emoji = "🟢", rarity = "Uncommon", biomes = { "Meadow", "Junkyard" },
		influences = { Slimy = 5, Flexible = 3, Toxic = 2, Silly = 1 },
		reaction = { animation = "Slurp", sfx = "SoftSquish", color = 0x7FE3A8 },
		model = { shape = "Ball", size = {1.6,1.2,1.6}, color = 0x5FD98C, material = "Glass" },
	},
}

-- Stable order for the Discovery Book (SPEC §25).
Ingredients.order = {
	"Apple","Strawberry","Watermelon","Blueberry","Carrot","Pumpkin","Daisy","Sunflower",
	"Clover","Beetle","Butterfly","Worm","Stick","Acorn","MudClump","Pebble","RubberDuck",
	"BouncyBall","ToyBlock","Honeycomb","Mushroom","Feather",
	"Battery","Gear","ScrapMetal","Magnet","OilCan","BrokenTV","Spring","Bolt","Wire","Tire",
	"SodaCan","Lightbulb","CircuitBoard","Clock","Toaster","TrafficCone","Fan",
	"IceCube","Bone","CrystalShard","Fish","Coal","LavaFruit","StarFragment","MoonMushroom",
	"Meteorite","CursedSandwich","Slime",
}

Ingredients.rarityColor = {
	Common = 0xC8D0D8, Uncommon = 0x5FD98C, Rare = 0x6FA8FF, Exotic = 0xC77BFF, Secret = 0xFFD52E,
}

-- How much a single feeding moves the STABLE trait layer, by rarity (SPEC §12).
Ingredients.rarityPotency = {
	Common = 1.0, Uncommon = 1.35, Rare = 1.8, Exotic = 2.6, Secret = 3.2,
}

function Ingredients.get(id: string)
	return Ingredients.all[id]
end

function Ingredients.byBiome(biome: string)
	local out = {}
	for _, id in ipairs(Ingredients.order) do
		local def = Ingredients.all[id]
		if def then
			for _, b in ipairs(def.biomes) do
				if b == biome then
					table.insert(out, id)
					break
				end
			end
		end
	end
	return out
end

function Ingredients.count(): number
	return #Ingredients.order
end

return Ingredients
