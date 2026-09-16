--!strict
-- Shared.Config.Biomes — SPEC §13 hub + biome islands (NOT a seamless continent;
-- mobile performance matters). Each biome declares its own palette, spawn table
-- and ability gates, so adding a biome is configuration.

local Biomes = {}

Biomes.all = {
	Habitat = {
		display = "Home Habitat", emoji = "🏡", order = 0,
		origin = { 0, 0, 0 }, size = { 120, 120 },
		ground = 0x6FBF5A, ambient = 0xFFF4E0, fog = 900,
		spawnTable = { "Apple", "Daisy", "Stick", "Pebble", "Blueberry" },
		maxProps = 10,
		blurb = "Your creature lives here. Visitors can walk in.",
	},
	Meadow = {
		display = "Meadow", emoji = "🌼", order = 1,
		origin = { 260, 0, 0 }, size = { 220, 220 },
		ground = 0x7ACB5E, ambient = 0xFFF0D0, fog = 1100,
		spawnTable = {
			"Apple","Apple","Strawberry","Blueberry","Carrot","Daisy","Daisy","Sunflower",
			"Clover","Beetle","Butterfly","Worm","Stick","Acorn","MudClump","Pebble",
			"BouncyBall","ToyBlock","Honeycomb","Mushroom","Feather","Watermelon","Pumpkin",
			"RubberDuck","IceCube","Fish","Slime",
		},
		maxProps = 42,
		traits = { "Nature", "Sweet", "Energy", "Round" },
		blurb = "Fruit, flowers, insects, wood, mud, toys.",
	},
	Junkyard = {
		display = "Junkyard", emoji = "🔩", order = 2,
		origin = { -260, 0, 120 }, size = { 200, 200 },
		ground = 0x6E6459, ambient = 0xD8CDBC, fog = 800,
		spawnTable = {
			"Battery","Battery","Gear","ScrapMetal","ScrapMetal","Magnet","OilCan","BrokenTV",
			"Spring","Bolt","Wire","Tire","SodaCan","Lightbulb","CircuitBoard","Clock",
			"Toaster","TrafficCone","Fan","Pebble","Coal","Bone","CursedSandwich","RubberDuck","Slime",
		},
		maxProps = 40,
		traits = { "Metal", "Electric", "Artificial", "Heavy" },
		blurb = "Scrap, gears, batteries, magnets, oil, televisions.",
	},
	-- SPEC §13: players should glimpse the Strange Zone very early. It is visible
	-- from the Habitat but not enterable in this build.
	StrangeZone = {
		display = "The Strange Zone", emoji = "🌀", order = 99,
		origin = { 0, 180, -520 }, size = { 90, 90 },
		ground = 0x4A4260, ambient = 0xC7B8FF, fog = 400,
		spawnTable = { "MoonMushroom", "StarFragment", "Meteorite" },
		maxProps = 6, locked = true, glimpseOnly = true,
		traits = { "Mystic", "Dark", "Celestial" },
		blurb = "Reality behaves improperly here.",
	},
}

Biomes.order = { "Habitat", "Meadow", "Junkyard", "StrangeZone" }

-- ═══ ABILITY GATES (SPEC §11 — the creature you build changes your route) ════
-- Each gate sits in a biome and only opens for a creature with that ability.
Biomes.gates = {
	{ id = "MeadowBoulder", biome = "Meadow",   ability = "Giant",
	  position = { 320, 0, -60 }, reward = { "Watermelon", "Pumpkin", "Clover" },
	  prompt = "A boulder. Far too heavy to move.", success = "Your creature shoves it aside." },
	{ id = "MeadowBurrow",  biome = "Meadow",   ability = "Tiny",
	  position = { 200, 0, 70 }, reward = { "Honeycomb", "Beetle", "Clover" },
	  prompt = "A gap in the roots. Something small could fit.", success = "It squeezes through." },
	{ id = "JunkGenerator", biome = "Junkyard", ability = "Electric",
	  position = { -320, 0, 60 }, reward = { "BrokenTV", "CircuitBoard", "Toaster" },
	  prompt = "A dead generator.", success = "It sparks to life." },
	{ id = "JunkGap",       biome = "Junkyard", ability = "Glide",
	  position = { -200, 0, 190 }, reward = { "Lightbulb", "Fan", "Magnet" },
	  prompt = "A wide gap between scrap towers.", success = "It glides across." },
	{ id = "MeadowCave",    biome = "Meadow",   ability = "Light",
	  position = { 340, 0, 90 }, reward = { "Mushroom", "CrystalShard", "Bone" },
	  prompt = "A dark hollow. You cannot see in.", success = "Its glow fills the hollow." },
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
