--!strict
-- Shared.Config.Progression — SPEC §14 growth stages.
-- Mythic does NOT end progression; it unlocks lineage (SPEC §15).

local Progression = {}

Progression.stages = {
	{ id = 1, name = "Baby",   emoji = "🥚", feedsToNext = 5,  sizeBase = 0.7, malleability = 1.00,
	  blurb = "Cute. Changes fast. Traits are extremely malleable." },
	{ id = 2, name = "Little", emoji = "🐣", feedsToNext = 14, sizeBase = 0.80, malleability = 0.80,
	  blurb = "Basic anatomy emerges. First environmental ability." },
	{ id = 3, name = "Grown",  emoji = "🦎", feedsToNext = 34, sizeBase = 1.00, malleability = 0.55,
	  blurb = "Your build identity becomes obvious. Competitions unlock." },
	{ id = 4, name = "Giant",  emoji = "🦖", feedsToNext = 70, sizeBase = 1.45, malleability = 0.35,
	  blurb = "Rare combination traits. Harder exploration." },
	{ id = 5, name = "Mythic", emoji = "🐉", feedsToNext = nil, sizeBase = 1.95, malleability = 0.20,
	  blurb = "Spectacular. This is where lineage begins." },
}

-- SPEC §12, three-layer influence model.
Progression.RECENT_WINDOW   = 90    -- seconds a feed counts as "recent"
Progression.RECENT_WEIGHT   = 0.60  -- temporary push, decays out
Progression.GENE_WEIGHT     = 1.35  -- inherited genes punch above stable traits
Progression.LOCK_AT_STAGE   = 4     -- stable traits start locking into genes here

-- Every feed nudges size even without a mutation, so change is ALWAYS visible.
-- SPEC §8 (0:16 "physically grows perhaps 8%"), non-negotiable §99 #2.
Progression.GROWTH_PER_FEED = 0.018
Progression.MAX_SIZE_DRIFT  = 0.45

-- Mutation sizeMul stacks multiplicatively (Gigantism x Monarch x Everything = 3.1x),
-- which ran away to 8.7x base in the first smoke test. Clamp per stage so Mythic is
-- spectacular but bounded: 6.5 x a ~2.5-stud torso lands near the 15-foot creature
-- the thumbnail promises (SPEC thumbnail promise, 14 Giant/Mythic).
Progression.MAX_SCALE = { 1.25, 1.90, 2.80, 4.20, 6.50 }

function Progression.stage(n: number)
	return Progression.stages[math.clamp(n, 1, #Progression.stages)]
end

function Progression.readyToEvolve(stage: number, fedCount: number): boolean
	local s = Progression.stage(stage)
	return s.feedsToNext ~= nil and fedCount >= s.feedsToNext
end

function Progression.maxStage(): number
	return #Progression.stages
end

return Progression
