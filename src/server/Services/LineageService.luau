--!strict
-- LineageService — SPEC §15 "The Nest". Deliberately NOT called rebirth.
--
-- "Rebirth" tells the player: throw away the thing you became attached to so your
-- multiplier gets bigger. Here the PARENT STAYS FOREVER. The offspring inherits
-- one body gene, one trait affinity, one potential mutation, and the lineage level.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local CreatureService = require(script.Parent.CreatureService)
local AnalyticsService = require(script.Parent.AnalyticsService)

local LineageService = {}

function LineageService.canNest(genome): boolean
	return genome ~= nil and (genome.stage or 1) >= Progression.maxStage()
end

function LineageService.create(player: Player)
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false, reason = "no profile" }
	end
	local parent = profile.creatures[profile.activeCreature]
	if not LineageService.canNest(parent) then
		return { ok = false, reason = "creature must reach Mythic first" }
	end

	-- one trait affinity: the parent's strongest line carries forward
	local eff = CreatureBuilder.effectiveTraits(parent)
	local top = TableUtil.topN(eff, 1)
	local affinity = #top > 0 and top[1].key or nil

	-- one potential mutation: the rarest the parent actually expressed
	local best, bestScore = nil, -1
	for id in pairs(parent.mutations or {}) do
		local def = Mutations.get(id)
		if def then
			local score = 0
			for _, v in pairs(def.requirements) do
				score += v
			end
			if score > bestScore then
				best, bestScore = id, score
			end
		end
	end

	local genes = {}
	if affinity then
		-- inherited genes punch above stable traits (Progression.GENE_WEIGHT)
		genes[affinity] = math.floor((eff[affinity] or 0) * 0.22)
	end

	local child = CreatureBuilder.newGenome({
		bodyFamily = parent.bodyFamily, -- one body gene
		genes = genes,
		generation = (parent.generation or 1) + 1,
		parentId = parent.id,
		plainStart = true,
	})
	child.inheritedMutation = best

	-- THE PARENT IS NOT CONSUMED. It stays in the Sanctuary, forever.
	parent.retired = true
	parent.retiredAt = os.time()

	table.insert(profile.creatures, child)
	profile.activeCreature = #profile.creatures
	profile.lineage = math.max(profile.lineage or 1, child.generation)

	PlayerDataService.addCurrency(player, Economy.rewards.lineageCreated)
	AnalyticsService.track("lineage_created", player, {
		generation = child.generation,
		affinity = affinity or "none",
		inherited_mutation = best or "none",
	})

	CreatureService.refresh(player, true)
	PlayerDataService.sync(player)

	Net.event("Toast"):FireClient(player, {
		kind = "lineage",
		title = "THE NEST",
		label = string.format("Generation %d", child.generation),
		sub = string.format("%s stays in your Sanctuary. %s%s",
			parent.name or "Your monster",
			affinity and ("Inherited " .. Traits.display(affinity)) or "",
			best and (" + " .. (Mutations.get(best) or {}).display .. " potential") or ""),
		color = 0xA77BFF,
	})

	return { ok = true, generation = child.generation, affinity = affinity, inherited = best }
end

return LineageService
