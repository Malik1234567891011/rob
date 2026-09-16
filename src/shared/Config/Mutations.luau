--!strict
-- Shared.Config.Mutations — SPEC §69 data shape, §26 secret recipes, §11 abilities.
--
-- SPEC §11 is the rule that keeps this from being a dress-up simulator:
-- a mutation that grants an ability MUST change where the player can go.
--
-- Trait scale: one Common feed adds its influence x1.0 to the stable layer.
-- An apple is Nature+3, so `Sprout` at Nature>=3 fires on the VERY FIRST FEED.
-- That is SPEC §8 (0:16 "a tiny green tuft pops out of its head") and
-- non-negotiable §99 #2, encoded as data rather than a special case.

local Mutations = {}

Mutations.all = {
	-- ── Tier 0: fire on the first few feeds. Teaches cause and effect. ───────
	Sprout = {
		display = "Sprout", emoji = "🌿", rarity = "Common", stage = 1,
		requirements = { Nature = 3 },
		parts = { Horn = "Nub" }, tintSecondary = 0x5FBF52,
		hint = "Something green.",
	},
	Spark = {
		display = "Spark", emoji = "⚡", rarity = "Common", stage = 1,
		requirements = { Electric = 5 },
		parts = { Eyes = "Glow" }, tintSecondary = 0xFFD52E, glow = 0.4,
		hint = "Its pupils flicker.",
	},
	Spore = {
		display = "Spore", emoji = "🍄", rarity = "Common", stage = 1,
		requirements = { Fungal = 5 },
		parts = { Back = "Mushroom" }, tintSecondary = 0xC96FA8,
		hint = "Something is growing on its back.",
	},
	Squeaky = {
		display = "Squeaky", emoji = "🦆", rarity = "Common", stage = 1,
		requirements = { Toy = 5 },
		parts = { Mouth = "Beak" }, tintPrimary = 0xFFD52E,
		hint = "It squeaks now. You did this.",
	},
	Pebbled = {
		display = "Pebbled", emoji = "🪨", rarity = "Common", stage = 1,
		requirements = { Stone = 6 },
		parts = { Back = "Spikes" }, tintPrimary = 0x8C8478,
		hint = "Its skin has gone rough.",
	},
	Damp = {
		display = "Damp", emoji = "💧", rarity = "Common", stage = 1,
		requirements = { Water = 5 },
		parts = { Tail = "FishTail" }, tintSecondary = 0x3FA9F5,
		hint = "It is inexplicably wet.",
	},

	-- ── Tier 1: stage 2, first ABILITIES. These change where you can go. ────
	Gigantism = {
		display = "Gigantism", emoji = "🏋️", rarity = "Uncommon", stage = 2,
		requirements = { Heavy = 22 }, blockers = { Flexible = 30 },
		parts = { Legs = "Chunky" }, sizeMul = 1.55, ability = "Giant",
		hint = "Heavy things, over and over.",
	},
	Miniature = {
		display = "Miniature", emoji = "🐜", rarity = "Uncommon", stage = 2,
		requirements = { Flexible = 20 }, blockers = { Heavy = 25 },
		parts = { Legs = "Noodle" }, sizeMul = 0.55, ability = "Tiny",
		hint = "Bendy things. Nothing heavy.",
	},
	LiveWire = {
		display = "Live Wire", emoji = "🔌", rarity = "Uncommon", stage = 2,
		requirements = { Electric = 26 },
		parts = { Tail = "Bolt", Eyes = "Glow" }, ability = "Electric",
		tintSecondary = 0xFFD52E, glow = 0.7,
		hint = "Keep feeding it batteries.",
	},
	Glowworm = {
		display = "Glowworm", emoji = "🔦", rarity = "Uncommon", stage = 2,
		requirements = { Crystal = 18, Shiny = 10 },
		parts = { Horn = "Crystal" }, ability = "Light", glow = 0.9,
		hint = "Crystal and shine.",
	},
	Featherlight = {
		display = "Featherlight", emoji = "🪶", rarity = "Uncommon", stage = 2,
		requirements = { Air = 24 }, blockers = { Heavy = 30 },
		parts = { Back = "Fins" }, ability = "Glide", sizeMul = 0.92,
		hint = "Airy things, and stay light.",
	},
	Burrower = {
		display = "Burrower", emoji = "⛏️", rarity = "Uncommon", stage = 2,
		requirements = { Stone = 24, Heavy = 14 },
		parts = { Legs = "Chunky", Mouth = "Fangs" }, ability = "Burrow",
		hint = "Stone. Lots of stone.",
	},

	-- ── Tier 2: stage 3, the shareable ones. ────────────────────────────────
	Stormwing = {
		display = "Stormwing", emoji = "🪽", rarity = "Rare", stage = 3,
		requirements = { Electric = 70, Air = 55 }, blockers = { Heavy = 80 },
		parts = { Back = "Wings", Tail = "Bolt", Eyes = "Glow" },
		ability = "Glide", tintSecondary = 0xFFD52E, glow = 0.8,
		secret = true, hint = "Electric + Air, and never let it get heavy.",
	},
	LavaSnail = {
		display = "Lava Snail", emoji = "🐌", rarity = "Rare", stage = 3,
		requirements = { Fire = 55, Stone = 30 }, blockers = { Energy = 60 },
		parts = { Back = "Shell", Legs = "Stubby" },
		ability = "Heatproof", tintPrimary = 0xFF5A1F, sizeMul = 1.1, glow = 0.5,
		secret = true, hint = "Fire and shell, but keep it slow.",
	},
	TVHead = {
		display = "TV Head", emoji = "📺", rarity = "Rare", stage = 3,
		requirements = { Artificial = 60, Electric = 40 },
		parts = { Eyes = "Screen", Head = "Blocky", Back = "Screen" },
		ability = "Electric", tintPrimary = 0xC9CDD1, glow = 0.6,
		secret = true, hint = "Televisions. Repeatedly. Yes, really.",
	},
	MoonBeast = {
		display = "Moon Beast", emoji = "🌙", rarity = "Exotic", stage = 3,
		requirements = { Celestial = 55, Night = 45 },
		parts = { Horn = "Single", Eyes = "Glow", Back = "Wings" },
		ability = "Ghost", tintPrimary = 0x8E86E0, tintSecondary = 0xE4E0FF, glow = 1.0,
		secret = true, hint = "Celestial + Night. Something lunar.",
	},
	StaticBloom = {
		display = "Static Bloom", emoji = "🌸", rarity = "Rare", stage = 3,
		requirements = { Nature = 45, Electric = 45 },
		parts = { Back = "Mushroom", Ears = "Antenna" },
		ability = "Plant", tintSecondary = 0xA6E22E, glow = 0.55,
		secret = true, hint = "Nature and Electric, in equal measure.",
	},
	Scrapheart = {
		display = "Scrapheart", emoji = "🔩", rarity = "Rare", stage = 3,
		requirements = { Metal = 65, Heavy = 35 },
		parts = { Head = "Blocky", Legs = "Chunky", Back = "Spikes" },
		ability = "Giant", tintPrimary = 0xA8B0BA, sizeMul = 1.35,
		hint = "Metal until it stops being organic.",
	},
	Cursed = {
		display = "Cursed", emoji = "☣️", rarity = "Rare", stage = 3,
		requirements = { Toxic = 50, Dark = 35 },
		parts = { Eyes = "Many", Mouth = "Gaping" },
		tintPrimary = 0x4A4260, glow = 0.3,
		secret = true, hint = "Feed it things you probably should not.",
	},
	Deepling = {
		display = "Deepling", emoji = "🐟", rarity = "Rare", stage = 3,
		requirements = { Water = 60, Flexible = 30 },
		parts = { Tail = "FishTail", Back = "Fins", Eyes = "Big" },
		ability = "Aquatic", tintPrimary = 0x3FA9F5,
		hint = "Nothing but fish.",
	},
	Fossilised = {
		display = "Fossilised", emoji = "🦴", rarity = "Rare", stage = 3,
		requirements = { Ancient = 50, Stone = 30 },
		parts = { Horn = "Curved", Head = "Snouted", Legs = "Chunky" },
		ability = "Burrow", tintPrimary = 0xD6C9A8,
		hint = "Old things. Older than they should be.",
	},
	Gummy = {
		display = "Gummy", emoji = "🍬", rarity = "Uncommon", stage = 3,
		requirements = { Sweet = 55, Slimy = 25 },
		parts = { Head = "Bulb", Eyes = "Big", Ears = "Floppy" },
		tintPrimary = 0xFF8FB0, sizeMul = 0.95,
		hint = "Sweet, and a bit sticky.",
	},
	Frostbitten = {
		display = "Frostbitten", emoji = "❄️", rarity = "Rare", stage = 3,
		requirements = { Cold = 50 },
		parts = { Horn = "Crystal", Back = "Spikes" },
		tintPrimary = 0xBFE9FF, ability = "Light", glow = 0.4,
		hint = "Keep it cold.",
	},

	-- ── Tier 3: stage 4+, spectacle. SPEC §14 Giant / Mythic. ───────────────
	Monarch = {
		display = "Monarch", emoji = "👑", rarity = "Exotic", stage = 4,
		requirements = { Shiny = 60, Celestial = 40, Sweet = 30 },
		parts = { Horn = "Crown", Back = "Wings", Eyes = "Big" },
		tintSecondary = 0xFFD52E, sizeMul = 1.25, glow = 0.7,
		secret = true, hint = "Shiny, celestial, and sweet. It wants to be adored.",
	},
	VoidMoth = {
		display = "Void Moth", emoji = "🌑", rarity = "Exotic", stage = 4,
		requirements = { Dark = 65, Mystic = 50, Air = 35 },
		parts = { Back = "Wings", Eyes = "Many", Ears = "Antenna" },
		ability = "Ghost", tintPrimary = 0x4A4260, glow = 0.85,
		secret = true, hint = "Nobody has written this one down yet.",
	},
	Everything = {
		display = "Everything", emoji = "🤯", rarity = "Exotic", stage = 5,
		-- SPEC §41: funny before cool. This is the thumbnail creature.
		requirements = { Crystal = 40, Fire = 40, Electric = 40, Artificial = 40, Celestial = 40 },
		parts = { Horn = "Crystal", Back = "Wings", Eyes = "Screen", Legs = "Chunky", Tail = "Bolt" },
		ability = "Glide", sizeMul = 1.6, glow = 1.0,
		secret = true, hint = "Feed it a bit of absolutely everything.",
	},
}

Mutations.order = {
	"Sprout","Spark","Spore","Squeaky","Pebbled","Damp",
	"Gigantism","Miniature","LiveWire","Glowworm","Featherlight","Burrower",
	"Stormwing","LavaSnail","TVHead","MoonBeast","StaticBloom","Scrapheart",
	"Cursed","Deepling","Fossilised","Gummy","Frostbitten",
	"Monarch","VoidMoth","Everything",
}

-- ═══ ABILITIES (SPEC §11 — must materially change gameplay) ══════════════════
Mutations.abilities = {
	Giant     = { display = "Giant",     emoji = "🏋️", desc = "Move heavy rocks that block paths." },
	Tiny      = { display = "Tiny",      emoji = "🐜", desc = "Fit through small passages." },
	Electric  = { display = "Electric",  emoji = "⚡", desc = "Power dead machinery." },
	Glide     = { display = "Glide",     emoji = "🪽", desc = "Glide across gaps." },
	Light     = { display = "Light",     emoji = "🔦", desc = "See inside dark caves." },
	Burrow    = { display = "Burrow",    emoji = "⛏️", desc = "Dig through cracked earth." },
	Aquatic   = { display = "Aquatic",   emoji = "🌊", desc = "Breathe underwater." },
	Heatproof = { display = "Heatproof", emoji = "🔥", desc = "Survive volcanic ground." },
	Ghost     = { display = "Ghost",     emoji = "👻", desc = "Pass through certain barriers." },
	Plant     = { display = "Plant",     emoji = "🌱", desc = "Grow climbable vines." },
	Sticky    = { display = "Sticky",    emoji = "🕷️", desc = "Climb sheer walls." },
}

-- Wired to real world gates in this build (SPEC §60 asks for 5).
Mutations.activeAbilities = { "Giant", "Tiny", "Electric", "Glide", "Light" }

function Mutations.get(id: string)
	return Mutations.all[id]
end

-- Does `traits` satisfy this mutation at `stage`?
function Mutations.satisfied(def, traits: { [string]: number }, stage: number): boolean
	if stage < (def.stage or 1) then
		return false
	end
	for trait, need in pairs(def.requirements) do
		if (traits[trait] or 0) < need then
			return false
		end
	end
	if def.blockers then
		for trait, limit in pairs(def.blockers) do
			if (traits[trait] or 0) >= limit then
				return false
			end
		end
	end
	return true
end

-- All mutations newly satisfied, most specific first so the biggest one wins
-- the announcement (SPEC §43: rare mutation sting is status signalling).
function Mutations.evaluate(traits: { [string]: number }, stage: number, already: { [string]: boolean })
	local found = {}
	for _, id in ipairs(Mutations.order) do
		local def = Mutations.all[id]
		if def and not already[id] and Mutations.satisfied(def, traits, stage) then
			local specificity = 0
			for _, need in pairs(def.requirements) do
				specificity += need
			end
			table.insert(found, { id = id, def = def, specificity = specificity })
		end
	end
	table.sort(found, function(a, b)
		return a.specificity > b.specificity
	end)
	return found
end

function Mutations.secretCount(): number
	local n = 0
	for _, def in pairs(Mutations.all) do
		if def.secret then
			n += 1
		end
	end
	return n
end

return Mutations
