--!strict
-- GameEvents — one tiny server-side bus so systems stay decoupled.
--
-- Feeding does not know quests exist; it just says "fed". Quests, analytics, the research
-- board and events all listen. Adding a new system never means editing FeedingService.
--
--   GameEvents.fire(player, "fed", { ingredient = "Apple", firstTime = true })
--   GameEvents.on("fed", function(player, data) ... end)
--
-- Event names in use: fed, pickup, trait_new, mutation_new, evolved, gate_opened, pet,
-- biome_enter, trial_done, parade_entered, parade_vote, lineage, named, sanctuary_upgrade,
-- merchant_buy, event_joined, party_gate

local GameEvents = {}

local listeners: { [string]: { (Player, any) -> () } } = {}

function GameEvents.on(name: string, fn: (Player, any) -> ())
	listeners[name] = listeners[name] or {}
	table.insert(listeners[name], fn)
end

function GameEvents.fire(player: Player, name: string, data: any?)
	for _, fn in ipairs(listeners[name] or {}) do
		task.spawn(function()
			local ok, err = pcall(fn, player, data or {})
			if not ok then
				warn("[GameEvents] listener for " .. name .. " failed: " .. tostring(err))
			end
		end)
	end
end

return GameEvents
