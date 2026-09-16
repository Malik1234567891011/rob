--!strict
-- Shared.Config.Quests — SPEC §46: no "walk 5,000 studs". Quests TEACH DISCOVERY.
--
-- Each quest listens to one GameEvents name and counts matching events up to `goal`.
-- `filter` keys are checked against the event data:
--   new = true            only first-time things (never eaten before, new trait...)
--   influence = "Metal"   ingredient must push this trait
--   rarity = "Rare"       ingredient rarity at least this
--   distinct = true       each different ingredient counts once
--   biome = "Junkyard"    where it happened
--   withFriend = true     a friend was in the same activity
--
-- `weight` biases how often a quest is rolled; `minStage` keeps late quests out of FTUE.

local Quests = {}

Quests.all = {
	TrySomethingNew = {
		display = "Try Something New", emoji = "🍽️",
		desc = "Feed your monster something it has never eaten.",
		event = "fed", goal = 1, filter = { new = true },
		reward = { Coins = 60 }, weight = 3,
	},
	WeirdDiet = {
		display = "Weird Diet", emoji = "🤖",
		desc = "Feed it three different artificial objects.",
		event = "fed", goal = 3, filter = { influence = "Artificial", distinct = true },
		reward = { Coins = 120 }, weight = 2,
	},
	Scientist = {
		display = "Scientist", emoji = "🧪",
		desc = "Trigger a trait your monster doesn't have yet.",
		event = "trait_new", goal = 1,
		reward = { Coins = 90 }, weight = 2,
	},
	Adventure = {
		display = "Adventure", emoji = "🗺️",
		desc = "Use an ability to open something hidden.",
		event = "gate_opened", goal = 1,
		reward = { Coins = 150, Essence = 1 }, weight = 1, minStage = 2,
	},
	SocialCreature = {
		display = "Social Creature", emoji = "🤝",
		desc = "Finish a Trial with a friend.",
		event = "trial_done", goal = 1, filter = { withFriend = true },
		reward = { Coins = 200, Essence = 1 }, weight = 1, minStage = 3,
	},
	TrialRunner = {
		display = "Trial Runner", emoji = "🏁",
		desc = "Complete any Creature Trial.",
		event = "trial_done", goal = 1,
		reward = { Coins = 150 }, weight = 2, minStage = 2,
	},
	Mutant = {
		display = "It's Changing", emoji = "🧬",
		desc = "Unlock a new mutation.",
		event = "mutation_new", goal = 1,
		reward = { Coins = 140 }, weight = 2,
	},
	Sparky = {
		display = "Sparky", emoji = "⚡",
		desc = "Feed it four things with Electric influence.",
		event = "fed", goal = 4, filter = { influence = "Electric" },
		reward = { Coins = 100 }, weight = 1,
	},
	GreenThumb = {
		display = "Green Thumb", emoji = "🌿",
		desc = "Feed it five plants.",
		event = "fed", goal = 5, filter = { influence = "Nature" },
		reward = { Coins = 100 }, weight = 1,
	},
	Rare = {
		display = "Something Rare", emoji = "💎",
		desc = "Feed it a Rare (or rarer) ingredient.",
		event = "fed", goal = 1, filter = { rarity = "Rare" },
		reward = { Coins = 160, Essence = 1 }, weight = 1, minStage = 2,
	},
	PetLover = {
		display = "Good Monster", emoji = "💕",
		desc = "Pet your monster three times.",
		event = "pet", goal = 3,
		reward = { Coins = 50 }, weight = 2,
	},
	Forager = {
		display = "Forager", emoji = "🧺",
		desc = "Pick up eight ingredients.",
		event = "pickup", goal = 8,
		reward = { Coins = 80 }, weight = 2,
	},
	JunkDiver = {
		display = "Junk Diver", emoji = "🔩",
		desc = "Pick up five things in the Junkyard.",
		event = "pickup", goal = 5, filter = { biome = "Junkyard" },
		reward = { Coins = 110 }, weight = 1,
	},
	CaveCrawler = {
		display = "Cave Crawler", emoji = "💎",
		desc = "Pick up four things in the Crystal Caves.",
		event = "pickup", goal = 4, filter = { biome = "CrystalCaves" },
		reward = { Coins = 130 }, weight = 1, minStage = 2,
	},
	StarOfTheShow = {
		display = "Star of the Show", emoji = "🎭",
		desc = "Walk your monster in the Creature Parade.",
		event = "parade_entered", goal = 1,
		reward = { Coins = 120, Essence = 1 }, weight = 1, minStage = 2,
	},
	BigBite = {
		display = "Big Appetite", emoji = "😋",
		desc = "Feed your monster ten times.",
		event = "fed", goal = 10,
		reward = { Coins = 120 }, weight = 1,
	},
}

Quests.ACTIVE = 3

Quests.rarityRank = { Common = 1, Uncommon = 2, Rare = 3, Exotic = 4, Secret = 5 }

function Quests.get(id: string)
	return Quests.all[id]
end

return Quests
