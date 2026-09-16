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

	require(script.Parent.GameEvents).fire(player, "lineage", { generation = child.generation })
	return { ok = true, generation = child.generation, affinity = affinity, inherited = best }
end

-- Non-retired creatures the player can swap between. Base 2, +2 with the game pass
-- (SPEC §32: "Not required. Huge enthusiast value."). Retired parents never count.
local function roster(profile)
	local list = {}
	for i, c in ipairs(profile.creatures) do
		if not c.retired then
			table.insert(list, i)
		end
	end
	return list
end

local function slotsFor(player: Player): number
	local ok, Monetization = pcall(require, script.Parent.MonetizationService)
	if ok and Monetization.creatureSlots then
		return Monetization.creatureSlots(player)
	end
	return 2
end

function LineageService.switch(player: Player, index: number)
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false }
	end
	local c = profile.creatures[index]
	if not c or c.retired then
		return { ok = false, reason = "that monster lives in your Sanctuary now" }
	end
	if index == profile.activeCreature then
		return { ok = true }
	end
	profile.activeCreature = index
	CreatureService.refresh(player, "hop")
	PlayerDataService.sync(player)
	return { ok = true }
end

-- A brand-new egg alongside your current monster, paid in Essence (earned by playing).
LineageService.NEW_EGG_COST = { Essence = 25 }
function LineageService.newEgg(player: Player, family: string?)
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false }
	end
	if #roster(profile) >= slotsFor(player) then
		return { ok = false, reason = "no free creature slot" }
	end
	local Anatomy = require(Shared.Config.Anatomy)
	if family and not Anatomy.bodies[family] then
		family = nil
	end
	if not PlayerDataService.spend(player, LineageService.NEW_EGG_COST) then
		return { ok = false, reason = "needs 25 Essence" }
	end
	local g = CreatureBuilder.newGenome({ bodyFamily = family, plainStart = true })
	table.insert(profile.creatures, g)
	profile.activeCreature = #profile.creatures
	CreatureService.refresh(player, "hop")
	PlayerDataService.sync(player)
	return { ok = true }
end

function LineageService.start()
	Net.func("SwitchCreature").OnServerInvoke = function(player, index)
		if type(index) ~= "number" then
			return { ok = false }
		end
		return LineageService.switch(player, math.floor(index))
	end
	Net.func("NewEgg").OnServerInvoke = function(player, family)
		return LineageService.newEgg(player, type(family) == "string" and family or nil)
	end
end

return LineageService
