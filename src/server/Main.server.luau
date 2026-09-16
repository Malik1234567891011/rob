--!strict
-- Main — server entry point. Starts services and wires every client request.
--
-- SPEC §70: the client never asserts, it asks. Each handler below re-validates from
-- the profile, which is the only thing we trust.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local TextService = game:GetService("TextService")
local Players = game:GetService("Players")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Anatomy = require(Shared.Config:WaitForChild("Anatomy"))

Net.init() -- create every remote before any client can look for one

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services:WaitForChild("PlayerDataService"))
local AnalyticsService = require(Services:WaitForChild("AnalyticsService"))
local DiscoveryService = require(Services:WaitForChild("DiscoveryService"))
local CreatureService = require(Services:WaitForChild("CreatureService"))
local FeedingService = require(Services:WaitForChild("FeedingService"))
local WorldService = require(Services:WaitForChild("WorldService"))
local FtueService = require(Services:WaitForChild("FtueService"))
local OfflineService = require(Services:WaitForChild("OfflineService"))
local LineageService = require(Services:WaitForChild("LineageService"))

-- ═══ REMOTE HANDLERS ═════════════════════════════════════════════════════════

Net.func("PickEgg").OnServerInvoke = function(player, index)
	if type(index) ~= "number" then
		return { ok = false, reason = "bad index" }
	end
	return FtueService.pickEgg(player, math.clamp(math.floor(index), 1, 3))
end

Net.func("Feed").OnServerInvoke = function(player, ingredientId)
	if type(ingredientId) ~= "string" or not Ingredients.get(ingredientId) then
		return { ok = false, reason = "unknown ingredient" }
	end
	return FeedingService.feed(player, ingredientId)
end

Net.func("Evolve").OnServerInvoke = function(player)
	return FeedingService.evolve(player)
end

Net.func("CreateLineage").OnServerInvoke = function(player)
	return LineageService.create(player)
end

Net.func("SetDetailMode").OnServerInvoke = function(player, on)
	local profile = PlayerDataService.get(player)
	if profile then
		profile.detailMode = on == true
	end
	return { ok = true }
end

-- SPEC §19: naming happens after the first evolution, and names are player-authored,
-- so they go through moderation before anyone else can see them.
Net.func("NameCreature").OnServerInvoke = function(player, requested)
	local profile = PlayerDataService.get(player)
	local genome = PlayerDataService.activeCreature(player)
	if not profile or not genome then
		return { ok = false, reason = "no creature" }
	end
	if type(requested) ~= "string" then
		return { ok = false, reason = "bad name" }
	end
	requested = string.sub(string.gsub(requested, "^%s+", ""), 1, 20)
	if #requested < 1 then
		return { ok = false, reason = "empty" }
	end

	local safe = requested
	local ok, filtered = pcall(function()
		local result = TextService:FilterStringAsync(requested, player.UserId)
		return result:GetNonChatStringForBroadcastAsync()
	end)
	if ok and type(filtered) == "string" then
		safe = filtered
	else
		-- Studio has no filtering backend. Fail CLOSED, never ship an unfiltered name.
		warn("[Main] name filter unavailable, using placeholder:", filtered)
		safe = "Monster"
	end

	genome.name = safe
	AnalyticsService.track("monster_named", player, {})
	CreatureService.refresh(player, false)
	PlayerDataService.sync(player)
	return { ok = true, name = safe }
end

-- SPEC §24: click another monster -> who, what, and "HOW DID THEY GET THAT?!"
-- We reveal only the KNOWN portion of the ancestry. Unknowns stay "???".
Net.func("Inspect").OnServerInvoke = function(player, creatureId)
	if type(creatureId) ~= "string" then
		return nil
	end
	for _, other in ipairs(Players:GetPlayers()) do
		local genome = PlayerDataService.activeCreature(other)
		if genome and genome.id == creatureId then
			local viewer = PlayerDataService.get(player)
			local known = viewer and viewer.discovered.mutations or {}

			local shown = {}
			for id in pairs(genome.mutations or {}) do
				local def = Mutations.get(id)
				if def then
					-- you only get to read the recipe for things YOU have found
					table.insert(shown, known[id]
						and (def.emoji .. " " .. def.display)
						or "???")
				end
			end
			table.sort(shown)

			local dom = CreatureBuilder.dominantTrait(genome)
			return {
				name = genome.name or "???",
				owner = other.Name,
				generation = genome.generation or 1,
				stage = Progression.stage(genome.stage or 1).name,
				dominant = dom and Traits.display(dom) or nil,
				mutations = shown,
				recipe = table.concat(shown, "  +  "),
			}
		end
	end
	return nil
end

-- ═══ START ═══════════════════════════════════════════════════════════════════

WorldService.start()
PlayerDataService.start()
AnalyticsService.start()
CreatureService.start()
FtueService.start()
OfflineService.start()

print(string.format(
	"[Main] Feed a Monster! ready — %d ingredients, %d traits, %d mutations (%d secret), %s silhouettes",
	Ingredients.count(), #Traits.order, #Mutations.order, Mutations.secretCount(),
	tostring(Anatomy.combinationCount())))
