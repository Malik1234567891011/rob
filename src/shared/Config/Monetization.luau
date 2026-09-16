--!strict
-- Shared.Config.Monetization — SPEC §31–36. Restrained on purpose.
--
-- "We make money because players value what they created. We do not undermine that for a
--  $10 sale."
--
-- WHAT WE WILL NOT SELL (SPEC §34): mutation luck, Robux-exclusive genes, revives, random
-- Robux eggs, "buy the rare monster". Nothing in this file may ever do those things.
--
-- IDs are 0 until the passes/products are created on the Creator Dashboard after the place
-- is published. With id 0 the item shows as "coming soon" and can never be prompted.

local Monetization = {}

-- SPEC §36: "No purchase prompt before first evolution."
Monetization.requireEvolutions = 1

Monetization.passes = {
	ExtraSlots = {
		id = 0, price = 249, display = "+2 Creature Slots", emoji = "🥚",
		blurb = "Keep two more monsters ready to swap to. Not required. Ever.",
	},
	BigBackpack = {
		id = 0, price = 149, display = "Bigger Backpack", emoji = "🎒",
		blurb = "Carry far more ingredients on an expedition.",
	},
	SanctuaryPlus = {
		id = 0, price = 199, display = "Sanctuary Builder+", emoji = "🏡",
		blurb = "Six extra decoration spots and the fancy architecture set.",
	},
	Stylist = {
		id = 0, price = 99, display = "Creature Stylist", emoji = "🎨",
		blurb = "Purely cosmetic: eye colours, name effects, harmless markings.",
	},
	Researcher = {
		id = 0, price = 399, display = "VIP Researcher", emoji = "🔬",
		blurb = "Researcher nameplate, detailed journal stats, photo tools. No power.",
	},
}
Monetization.passOrder = { "ExtraSlots", "BigBackpack", "SanctuaryPlus", "Stylist", "Researcher" }

-- Developer products: deterministic, never random (SPEC §27, §33).
Monetization.products = {
	TraitCleanser = {
		id = 0, price = 49, display = "Trait Cleanser", emoji = "🧼",
		blurb = "Wash out the recent foods pushing your monster somewhere you didn't want.",
	},
	SnackPack = {
		id = 0, price = 39, display = "Expedition Snack Pack", emoji = "🧺",
		blurb = "Ten common ingredients from every biome. Also found in the world for free.",
		grants = { Apple = 2, Carrot = 1, Battery = 2, Gear = 1, Mushroom = 2, Pebble = 1, Feather = 1 },
	},
	TrailStars = {
		id = 0, price = 79, display = "Star Footprints", emoji = "✨",
		blurb = "Your monster leaves little stars when it walks. Cosmetic.",
		cosmetic = "TrailStars",
	},
	TrailBubbles = {
		id = 0, price = 79, display = "Bubble Trail", emoji = "🫧",
		blurb = "Bubbles follow your monster everywhere. Cosmetic.",
		cosmetic = "TrailBubbles",
	},
	TrailLeaves = {
		id = 0, price = 79, display = "Leaf Trail", emoji = "🍃",
		blurb = "Little leaves drift behind it. Cosmetic.",
		cosmetic = "TrailLeaves",
	},
}
Monetization.productOrder = { "TraitCleanser", "SnackPack", "TrailStars", "TrailBubbles", "TrailLeaves" }

-- Free baselines the passes extend (never below what a free player needs).
Monetization.backpackBase = 120
Monetization.backpackPass = 400
Monetization.slotsBase = 2
Monetization.slotsPass = 4
Monetization.decorSlotsPass = 6

return Monetization
