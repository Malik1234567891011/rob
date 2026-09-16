--!strict
-- Shared.Config.Economy — SPEC §28. EXACTLY TWO CURRENCIES.
-- Not Coins/Gems/Crystals/Stars/Tokens/Raid Coins/Diamonds/Event Flowers.
-- That destroys cognitive simplicity.

local Economy = {}

Economy.currencies = {
	Coins   = { display = "Coins",   emoji = "🪙", color = 0xFFD52E,
	            blurb = "Discoveries, activities, expeditions, competitions, quests." },
	Essence = { display = "Essence", emoji = "🔮", color = 0xA77BFF,
	            blurb = "Evolutions, discoveries, major achievements, lineage milestones." },
}

Economy.rewards = {
	firstFeedOfIngredient = { Coins = 25 },   -- SPEC §30: discovery value, not just economic value
	traitUnlocked         = { Coins = 40 },
	mutationUnlocked      = { Coins = 120, Essence = 1 },
	secretMutation        = { Coins = 400,  Essence = 5 },
	stageEvolution        = { Coins = 250,  Essence = 2 },
	gateOpened            = { Coins = 150 },
	lineageCreated        = { Essence = 10 },
	trialCompleted        = { Coins = 120 },
	trialWin              = { Coins = 200, Essence = 1 },
	paradeEntered         = { Coins = 60 },
	paradeCategoryWin     = { Coins = 250, Essence = 1 },
	eventJoined           = { Coins = 80 },
	meteorCrack           = { Coins = 300, Essence = 2 },
	partyGate             = { Coins = 250, Essence = 1 },
	worldFirst            = { Coins = 1000, Essence = 10 },
}

-- SPEC §29: permanent sinks. Inflation destroys persistent-game economies.
-- SPEC §75: "~12 meaningful Sanctuary upgrade tiers". Each tier builds something you can see.
Economy.sanctuaryTiers = {
	{ tier = 1,  cost = { Coins = 0 },                     name = "Patch of Grass",   builds = { "Shack", "Food_Bowl" } },
	{ tier = 2,  cost = { Coins = 400 },                   name = "Fenced Yard",      builds = { "Fence" } },
	{ tier = 3,  cost = { Coins = 1200 },                  name = "Cosy Corner",      builds = { "Pet_Bed", "Lantern_Post" } },
	{ tier = 4,  cost = { Coins = 2500 },                  name = "Little Pond",      builds = { "Pond_Small", "LilyPad" } },
	{ tier = 5,  cost = { Coins = 4500 },                  name = "Stone Path",       builds = { "StonePath" } },
	{ tier = 6,  cost = { Coins = 7500, Essence = 2 },     name = "Garden Beds",      builds = { "Garden_Bed" } },
	{ tier = 7,  cost = { Coins = 12000, Essence = 4 },    name = "The Nest",         builds = { "Nest", "Statue_Pedestal" } },
	{ tier = 8,  cost = { Coins = 20000, Essence = 6 },    name = "Greenhouse",       builds = { "Greenhouse" } },
	{ tier = 9,  cost = { Coins = 32000, Essence = 10 },   name = "Windmill",         builds = { "Windmill" } },
	{ tier = 10, cost = { Coins = 50000, Essence = 15 },   name = "Treehouse",        builds = { "Treehouse" } },
	{ tier = 11, cost = { Coins = 80000, Essence = 25 },   name = "Observatory",      builds = { "Observatory" } },
	{ tier = 12, cost = { Coins = 130000, Essence = 40 },  name = "Grand Sanctuary",  builds = { "Lantern_String", "Trophy_Shelf", "Fountain_Small" } },
}

-- Wandering merchant prices by rarity (SPEC §47, deterministic stock, §29 coin sink).
Economy.merchantPrice = { Common = 40, Uncommon = 110, Rare = 320, Exotic = 900 }

-- Garden (SPEC §29 "food cultivation"): plant a picked-up ingredient, it grows more.
Economy.garden = {
	plotsPerBed = 3,
	growSeconds = { Common = 180, Uncommon = 420, Rare = 900, Exotic = 1800 },
	yield = { Common = 3, Uncommon = 2, Rare = 2, Exotic = 1 },
}

-- SPEC §12 + §33: a controlled way to shift direction, so nobody is bricked.
Economy.traitCleanseCost = { Essence = 3 }

-- Extra active-companion slots come from the game pass; base is one.
Economy.baseActiveSlots = 1

return Economy
