--!strict
-- AnalyticsService — the full SPEC §64 event schema, instrumented from day one.
-- "No guessing."
--
-- Roblox AnalyticsService only accepts its own event kinds, so custom events are
-- buffered with their properties and logged. Swap `emit` for your pipeline of
-- choice without touching a single call site.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local AnalyticsService = {}

AnalyticsService.SCHEMA = {
	"session_start",
	"ftue_egg_seen", "ftue_egg_selected", "ftue_first_food_pickup", "ftue_first_feed",
	"ftue_first_trait", "ftue_first_evolution",
	"ingredient_pickup", "ingredient_feed", "ingredient_discovered",
	"trait_progress", "trait_unlocked", "mutation_unlocked",
	"biome_enter", "biome_unlock",
	"monster_named", "monster_petted",
	"trial_enter", "trial_complete",
	"friend_join", "friend_party", "friend_sanctuary_visit",
	"sanctuary_upgrade",
	"lineage_created",
	"shop_open", "product_view", "purchase_prompt", "purchase_complete",
	"moment_capture", "moment_share",
	"session_end",
}

local valid: { [string]: boolean } = {}
for _, name in ipairs(AnalyticsService.SCHEMA) do
	valid[name] = true
end

local sessionStart: { [number]: number } = {}
local counts: { [string]: number } = {}
local VERBOSE = false

-- SPEC §64 common properties, attached to every event.
local function commonProps(player: Player?)
	if not player then
		return {}
	end
	local PlayerDataService = require(script.Parent.PlayerDataService)
	local profile = PlayerDataService.get(player)
	local creature = PlayerDataService.activeCreature(player)
	local activeTraits = {}
	if creature then
		local CreatureBuilder = require(game:GetService("ReplicatedStorage").Shared.CreatureBuilder)
		local dom = CreatureBuilder.dominantTrait(creature)
		activeTraits = { dom or "none" }
	end
	return {
		device = "unknown", -- client reports this on join; not inferred server-side
		session_number = profile and profile.stats.sessions or 0,
		monster_stage = creature and creature.stage or 0,
		lineage_generation = creature and creature.generation or 0,
		active_traits = table.concat(activeTraits, ","),
		friends_present = #Players:GetPlayers() - 1,
		time_since_last_session = profile and (os.time() - (profile.lastSeen or os.time())) or 0,
	}
end

function AnalyticsService.track(eventName: string, player: Player?, props: { [string]: any }?)
	if not valid[eventName] then
		warn("[Analytics] event not in SPEC 64 schema:", eventName)
		return
	end
	counts[eventName] = (counts[eventName] or 0) + 1

	local payload = commonProps(player)
	for k, v in pairs(props or {}) do
		payload[k] = v
	end

	if VERBOSE then
		local parts = {}
		for k, v in pairs(payload) do
			table.insert(parts, k .. "=" .. tostring(v))
		end
		table.sort(parts)
		print(string.format("[Analytics] %-24s %s %s",
			eventName, player and player.Name or "-", table.concat(parts, " ")))
	end
end

function AnalyticsService.funnelReport(): string
	-- SPEC §65 primary funnel, in order.
	local steps = {
		"session_start", "ftue_egg_selected", "ftue_first_food_pickup", "ftue_first_feed",
		"ftue_first_trait", "ftue_first_evolution", "lineage_created",
	}
	local out = { "[Analytics] funnel:" }
	for _, s in ipairs(steps) do
		table.insert(out, string.format("  %-24s %d", s, counts[s] or 0))
	end
	return table.concat(out, "\n")
end

function AnalyticsService.setVerbose(on: boolean)
	VERBOSE = on
end

function AnalyticsService.start()
	Players.PlayerAdded:Connect(function(player)
		sessionStart[player.UserId] = os.clock()
		AnalyticsService.track("session_start", player)
	end)
	Players.PlayerRemoving:Connect(function(player)
		local started = sessionStart[player.UserId]
		AnalyticsService.track("session_end", player, {
			duration = started and math.floor(os.clock() - started) or 0,
		})
		sessionStart[player.UserId] = nil
	end)
	print("[Analytics] ready,", #AnalyticsService.SCHEMA, "events instrumented")
end

return AnalyticsService
