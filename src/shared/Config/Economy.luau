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
	trialCompleted        = { Coins = 200 },
}

-- SPEC §29: permanent sinks. Inflation destroys persistent-game economies.
Economy.sanctuaryTiers = {
	{ tier = 1, cost = 0,      name = "Patch of Grass" },
	{ tier = 2, cost = 500,    name = "Fenced Yard" },
	{ tier = 3, cost = 2000,   name = "Little Pond" },
	{ tier = 4, cost = 6500,   name = "Stone Path" },
	{ tier = 5, cost = 18000,  name = "Greenhouse" },
	{ tier = 6, cost = 45000,  name = "Observatory" },
	{ tier = 7, cost = 110000, name = "Grand Sanctuary" },
}

-- SPEC §12 + §33: a controlled way to shift direction, so nobody is bricked.
Economy.traitCleanseCost = { Essence = 3 }

return Economy
