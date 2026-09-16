--!strict
-- FeedingService — the core loop, server-authoritative. SPEC §70.
--
-- The client asks "I want to feed item X". The server confirms ownership, that a
-- creature exists, that the state is valid and that this is not spam, and only then
-- mutates state. Nothing here trusts a single client-supplied number.
--
-- SPEC §12 three layers are applied here:
--   recent  <- always (temporary push, decays)
--   traits  <- always, scaled by rarity potency AND stage malleability
--   genes   <- only at LOCK_AT_STAGE and above (permanent lineage)

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")

local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local Economy = require(Shared.Config:WaitForChild("Economy"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local DiscoveryService = require(script.Parent.DiscoveryService)
local AnalyticsService = require(script.Parent.AnalyticsService)

local FeedingService = {}

local MIN_FEED_INTERVAL = 0.35 -- anti-spam; generous enough to never feel gated
local REVEAL_DELAY = 2.05 -- seconds: the eat animation's swallow lands here
local lastFeed: { [number]: number } = {}
local pendingRebuild: { [number]: number } = {}
local pendingReveal: { [number]: boolean } = {}

local CreatureService -- resolved lazily to avoid a require cycle

local function visibleTraits(genome)
	local out = {}
	local eff = CreatureBuilder.effectiveTraits(genome)
	for id, value in pairs(eff) do
		if value >= Traits.VISIBLE_AT then
			out[id] = value
		end
	end
	return out
end

--[[
	Apply one ingredient to a genome. Pure state mutation; no networking.
	Returns a report the caller turns into feedback.
]]
function FeedingService.applyInfluence(genome, ingredientId: string)
	local def = Ingredients.get(ingredientId)
	if not def then
		return nil
	end

	local potency = Ingredients.rarityPotency[def.rarity] or 1
	local stage = Progression.stage(genome.stage or 1)
	-- Babies change fast, Mythics barely budge (SPEC §14 malleability).
	local gain = potency * stage.malleability

	local before = visibleTraits(genome)

	genome.traits = genome.traits or {}
	for trait, amount in pairs(def.influences) do
		genome.traits[trait] = (genome.traits[trait] or 0) + amount * gain
	end

	-- layer 1: recent window
	genome.recent = genome.recent or {}
	table.insert(genome.recent, { ingredient = ingredientId, at = os.time() })
	local cutoff = os.time() - Progression.RECENT_WINDOW
	for i = #genome.recent, 1, -1 do
		if genome.recent[i].at < cutoff then
			table.remove(genome.recent, i)
		end
	end

	-- layer 3: at high stages, stable traits begin crystallising into lineage genes
	if (genome.stage or 1) >= Progression.LOCK_AT_STAGE then
		genome.genes = genome.genes or {}
		for trait, amount in pairs(def.influences) do
			genome.genes[trait] = (genome.genes[trait] or 0) + amount * gain * 0.08
		end
	end

	genome.fedCount = (genome.fedCount or 0) + 1

	local after = visibleTraits(genome)
	local newTraits = {}
	for id in pairs(after) do
		if not before[id] then
			table.insert(newTraits, id)
		end
	end

	-- evaluate mutations against the FULL effective vector (SPEC §69)
	local eff = CreatureBuilder.effectiveTraits(genome)
	genome.mutations = genome.mutations or {}
	local found = Mutations.evaluate(eff, genome.stage or 1, genome.mutations)
	local newMutations = {}
	for _, m in ipairs(found) do
		genome.mutations[m.id] = true
		table.insert(newMutations, m.id)
		if m.def.ability then
			genome.abilities = genome.abilities or {}
			genome.abilities[m.def.ability] = true
		end
	end

	return {
		ingredient = ingredientId,
		newTraits = newTraits,
		newMutations = newMutations,
		readyToEvolve = Progression.readyToEvolve(genome.stage or 1, genome.fedCount),
		reaction = def.reaction,
	}
end

function FeedingService.feed(player: Player, ingredientId: string)
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false, reason = "no profile" }
	end

	local now = os.clock()
	if now - (lastFeed[player.UserId] or 0) < MIN_FEED_INTERVAL then
		return { ok = false, reason = "too fast" }
	end

	local held = profile.inventory[ingredientId] or 0
	if held <= 0 then
		return { ok = false, reason = "not owned" }
	end

	local genome = PlayerDataService.activeCreature(player)
	if not genome then
		return { ok = false, reason = "no creature" }
	end

	local def = Ingredients.get(ingredientId)
	if not def then
		return { ok = false, reason = "unknown ingredient" }
	end

	-- commit
	lastFeed[player.UserId] = now
	profile.inventory[ingredientId] = held - 1
	if profile.inventory[ingredientId] <= 0 then
		profile.inventory[ingredientId] = nil
	end
	profile.stats.feeds += 1

	local report = FeedingService.applyInfluence(genome, ingredientId)
	if not report then
		return { ok = false, reason = "apply failed" }
	end

	DiscoveryService.recordEaten(ingredientId)
	DiscoveryService.ingredient(player, ingredientId)

	AnalyticsService.track("ingredient_feed", player, {
		ingredient = ingredientId, rarity = def.rarity, fed_count = genome.fedCount,
	})
	if profile.stats.feeds == 1 then
		AnalyticsService.track("ftue_first_feed", player, { ingredient = ingredientId })
		-- lazy require: FtueService reaches back into CreatureService
		require(script.Parent.FtueService).onFirstFeed(player)
	end

	-- eat reaction first, so the mouthfeel lands before any banner. Everyone nearby sees
	-- the chomp; only the feeder gets the food flying from their hand.
	CreatureService = CreatureService or require(script.Parent.CreatureService)
	CreatureService.actionFor(player, "eat")
	Net.event("Reaction"):FireClient(player, {
		ingredient = ingredientId,
		animation = def.reaction.animation,
		sfx = def.reaction.sfx,
		color = def.reaction.color or def.model.color,
		mutated = #report.newMutations > 0,
	})

	for _, traitId in ipairs(report.newTraits) do
		if DiscoveryService.trait(player, traitId) and profile.stats.feeds <= 3 then
			AnalyticsService.track("ftue_first_trait", player, { trait = traitId })
		end
	end
	for _, mutationId in ipairs(report.newMutations) do
		DiscoveryService.mutation(player, mutationId)
	end

	-- The body change lands AFTER the swallow (ART_DIRECTION feeding beat: chomp -> cheeks
	-- -> swallow -> wobble -> THEN mutation). Rapid feeds coalesce into one rebuild.
	local token = (pendingRebuild[player.UserId] or 0) + 1
	pendingRebuild[player.UserId] = token
	local mutated = #report.newMutations > 0
	pendingReveal[player.UserId] = pendingReveal[player.UserId] or mutated
	task.delay(REVEAL_DELAY, function()
		if pendingRebuild[player.UserId] ~= token or not player.Parent then
			return
		end
		local reveal = pendingReveal[player.UserId]
		pendingReveal[player.UserId] = nil
		CreatureService.refresh(player, reveal and "celebrate" or nil)
	end)

	PlayerDataService.sync(player)
	Net.event("CreatureSync"):FireClient(player, genome, report)

	return { ok = true, report = report }
end

--[[
	Stage advance. SPEC §9: the first evolution gets an exaggerated cinematic, and
	SPEC §17: evolutions NEVER complete offline — the reveal waits for the player.
]]
function FeedingService.evolve(player: Player)
	local profile = PlayerDataService.get(player)
	local genome = PlayerDataService.activeCreature(player)
	if not profile or not genome then
		return { ok = false, reason = "no creature" }
	end
	if not Progression.readyToEvolve(genome.stage or 1, genome.fedCount or 0) then
		return { ok = false, reason = "not ready" }
	end
	if (genome.stage or 1) >= Progression.maxStage() then
		return { ok = false, reason = "already mythic" }
	end

	genome.stage += 1
	local stage = Progression.stage(genome.stage)

	-- newly reachable mutations at this stage
	local eff = CreatureBuilder.effectiveTraits(genome)
	local found = Mutations.evaluate(eff, genome.stage, genome.mutations)
	local gained = {}
	for _, m in ipairs(found) do
		genome.mutations[m.id] = true
		table.insert(gained, m.id)
		if m.def.ability then
			genome.abilities = genome.abilities or {}
			genome.abilities[m.def.ability] = true
		end
	end

	PlayerDataService.addCurrency(player, Economy.rewards.stageEvolution)
	AnalyticsService.track("trait_progress", player, { stage = genome.stage })
	if genome.stage == 2 then
		AnalyticsService.track("ftue_first_evolution", player, {})
	end

	CreatureService = CreatureService or require(script.Parent.CreatureService)
	CreatureService.refresh(player, "evolve")

	Net.event("Evolution"):FireClient(player, {
		stage = genome.stage,
		name = stage.name,
		emoji = stage.emoji,
		blurb = stage.blurb,
		gained = gained,
		needsName = genome.name == nil, -- SPEC §19: name it after first evolution
	})
	for _, mutationId in ipairs(gained) do
		DiscoveryService.mutation(player, mutationId)
	end

	PlayerDataService.sync(player)
	return { ok = true, stage = genome.stage, gained = gained }
end

return FeedingService
