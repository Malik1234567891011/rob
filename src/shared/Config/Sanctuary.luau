--!strict
-- Shared.Config.Sanctuary — SPEC §16 "The Sanctuary is autobiography."
--
-- Every player owns one plot (64 x 64 studs) for the session. It starts as a patch of grass
-- and a shack, and each tier in Config/Economy.sanctuaryTiers BUILDS something visible.
-- A 200-hour player's plot should tell their story at a glance.
--
-- Plot-local coordinates: origin at the plot centre on the ground, -Z faces the hub path
-- (the entrance), +Z is the back. Asset names are Blender kit meshes in Assets.Kits.

local Sanctuary = {}

Sanctuary.PLOT_SIZE = 64
Sanctuary.MAX_PLOTS = 12

-- Where the player stands when they arrive / respawn, facing into the plot.
Sanctuary.spawn = { 0, 3, -22 }
-- The three FTUE eggs wobble here (SPEC §8 0:00).
Sanctuary.eggSpot = { 0, 0, -10 }

-- item name -> list of placements { x, y, z, yawDegrees, scale? }
Sanctuary.builds = {
	Shack           = { { -16, 0, 16, 180 } },
	Food_Bowl       = { { -9, 0, 6, 160 } },
	Sanctuary_Sign  = { { 7, 0, -31, 180 } },
	Fence           = "perimeter",
	Pet_Bed         = { { -6, 0, 12, 200 } },
	Lantern_Post    = { { -26, 0, 4, 0 }, { 26, 0, 4, 0 } },
	Pond_Small      = { { 14, 0, 16, 20 } },
	LilyPad         = { { 12, 0.55, 15, 0 }, { 16.5, 0.55, 18, 70 } },
	StonePath       = "path",
	Garden_Bed      = { { 16, 0, -10, 90 }, { 16, 0, -21, 90 } },
	Nest            = { { -18, 0, -10, 0 } },
	Statue_Pedestal = { { -26, 0, -24, 0 }, { -18, 0, -25, 0 }, { -10, 0, -24, 0 } },
	Greenhouse      = { { 25, 0, -3, 270 } },
	Windmill        = { { -27, 0, 27, 225 } },
	Treehouse       = { { 2, 0, 26, 180 } },
	Observatory     = { { 25, 0, 24, 200 } },
	Lantern_String  = { { 0, 9, -26, 0 } },
	Trophy_Shelf    = { { -5, 0, 20, 180 } },
	Fountain_Small  = { { 0, 0, 2, 0, 0.45 } },
}

-- Asset substitutions (a build name that re-uses another mesh).
Sanctuary.assetFor = {
	Fence = "Fence_Straight",
	StonePath = "StonePath_Tile",
	Fountain_Small = "Fountain",
}

-- Where retired parents wander (SPEC §15 "the parent stays forever").
Sanctuary.wanderRadius = 20

-- Decor: bought with coins, placed into fixed slots (mobile-friendly, no fiddly placement).
Sanctuary.decorSlots = {
	{ -8, 0, -16 }, { 8, 0, -16 }, { -27, 0, -12 }, { 27, 0, -14 },
	{ -28, 0, 14 }, { 28, 0, 12 }, { 6, 0, 8 }, { -2, 0, -4 },
	{ 10, 0, 28 }, { -12, 0, 28 }, { 20, 0, 6 }, { -20, 0, 0 },
}
-- slots unlocked per tier (tier 1 -> 2 slots ... tier 12 -> all 12)
Sanctuary.slotsAtTier = { 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12 }

Sanctuary.decor = {
	FlowerPatch_Yellow = { display = "Sunny Flowers", emoji = "🌼", price = 150 },
	FlowerPatch_Pink   = { display = "Pink Flowers", emoji = "🌸", price = 150 },
	FlowerPatch_Blue   = { display = "Blue Flowers", emoji = "💠", price = 150 },
	Bush_A             = { display = "Round Bush", emoji = "🌳", price = 220 },
	Mushroom_Red       = { display = "Big Toadstool", emoji = "🍄", price = 300 },
	Hay_Bale           = { display = "Hay Bale", emoji = "🌾", price = 260 },
	Bench_Wood         = { display = "Bench", emoji = "🪑", price = 400 },
	Birdhouse_Post     = { display = "Birdhouse", emoji = "🐦", price = 520 },
	Mailbox            = { display = "Mailbox", emoji = "📫", price = 480 },
	Planter_Box        = { display = "Planter", emoji = "🪴", price = 600 },
	Balloon_Cluster    = { display = "Balloons", emoji = "🎈", price = 750 },
	Well               = { display = "Wishing Well", emoji = "🪣", price = 1800 },
	Tent_Striped       = { display = "Striped Tent", emoji = "⛺", price = 2400 },
	Crystal_Cluster_Purple = { display = "Crystal Cluster", emoji = "💜", price = 3500, essence = 1 },
	Tree_Fruit         = { display = "Apple Tree", emoji = "🍎", price = 5000, essence = 2 },
}
Sanctuary.decorOrder = {
	"FlowerPatch_Yellow", "FlowerPatch_Pink", "FlowerPatch_Blue", "Bush_A", "Mushroom_Red",
	"Hay_Bale", "Bench_Wood", "Mailbox", "Birdhouse_Post", "Planter_Box", "Balloon_Cluster",
	"Well", "Tent_Striped", "Crystal_Cluster_Purple", "Tree_Fruit",
}

function Sanctuary.slotsFor(tier: number): number
	return Sanctuary.slotsAtTier[math.clamp(tier, 1, #Sanctuary.slotsAtTier)]
end

return Sanctuary
