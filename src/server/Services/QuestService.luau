--!strict
-- QuestService — SPEC §46. Three discovery quests at a time, always something to try next.
--
-- Pure listener: it never reaches into feeding or trials, it hears GameEvents and counts.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Quests = require(Shared.Config:WaitForChild("Quests"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local GameEvents = require(script.Parent.GameEvents)

local QuestService = {}

local function stageOf(player: Player): number
	local g = PlayerDataService.activeCreature(player)
	return g and g.stage or 1
end

local function roll(player: Player, profile, exclude: { [string]: boolean })
	local pool = {}
	local total = 0
	local stage = stageOf(player)
	for id, def in pairs(Quests.all) do
		if not exclude[id] and stage >= (def.minStage or 1) then
			table.insert(pool, { id = id, w = def.weight or 1 })
			total += def.weight or 1
		end
	end
	if total == 0 then
		return nil
	end
	local r = math.random() * total
	for _, e in ipairs(pool) do
		r -= e.w
		if r <= 0 then
			return { id = e.id, progress = 0, seen = {} }
		end
	end
	return { id = pool[#pool].id, progress = 0, seen = {} }
end

function QuestService.fill(player: Player)
	local profile = PlayerDataService.get(player)
	if not profile then
		return
	end
	local active = profile.quests.active
	local have = {}
	for _, q in ipairs(active) do
		have[q.id] = true
	end
	while #active < Quests.ACTIVE do
		local q = roll(player, profile, have)
		if not q then
			break
		end
		have[q.id] = true
		table.insert(active, q)
	end
end

local function matches(def, data): boolean
	local f = def.filter
	if not f then
		return true
	end
	if f.new and not data.new then
		return false
	end
	if f.withFriend and not data.withFriend then
		return false
	end
	if f.biome and data.biome ~= f.biome then
		return false
	end
	if f.influence or f.rarity then
		local ing = data.ingredient and Ingredients.get(data.ingredient)
		if not ing then
			return false
		end
		if f.influence and not (ing.influences[f.influence] and ing.influences[f.influence] > 0) then
			return false
		end
		if f.rarity and (Quests.rarityRank[ing.rarity] or 1) < (Quests.rarityRank[f.rarity] or 1) then
			return false
		end
	end
	return true
end

local function onEvent(eventName: string)
	return function(player: Player, data)
		local profile = PlayerDataService.get(player)
		if not profile then
			return
		end
		local changed = false
		for i = #profile.quests.active, 1, -1 do
			local q = profile.quests.active[i]
			local def = Quests.get(q.id)
			if not def then
				table.remove(profile.quests.active, i)
				changed = true
			elseif def.event == eventName and matches(def, data) then
				local counts = true
				if def.filter and def.filter.distinct and data.ingredient then
					q.seen = q.seen or {}
					if q.seen[data.ingredient] then
						counts = false
					else
						q.seen[data.ingredient] = true
					end
				end
				if counts then
					q.progress = math.min(def.goal, (q.progress or 0) + 1)
					changed = true
					if q.progress >= def.goal then
						table.remove(profile.quests.active, i)
						profile.quests.completedTotal += 1
						PlayerDataService.addCurrency(player, def.reward)
						local rewardText = {}
						if def.reward.Coins then
							table.insert(rewardText, "💰 " .. def.reward.Coins)
						end
						if def.reward.Essence then
							table.insert(rewardText, "🔮 " .. def.reward.Essence)
						end
						Net.event("Toast"):FireClient(player, {
							kind = "quest", title = "QUEST COMPLETE",
							label = def.emoji .. " " .. def.display,
							sub = table.concat(rewardText, "   "),
							color = 0x5FD98C,
						})
						GameEvents.fire(player, "quest_done", { quest = q.id })
					end
				end
			end
		end
		if changed then
			QuestService.fill(player)
			PlayerDataService.sync(player)
		end
	end
end

function QuestService.start()
	for _, def in pairs(Quests.all) do
		-- one listener per distinct event name
		local name = def.event
		if not QuestService["_listening_" .. name] then
			QuestService["_listening_" .. name] = true
			GameEvents.on(name, onEvent(name))
		end
	end
	PlayerDataService.onLoaded(function(player)
		QuestService.fill(player)
		PlayerDataService.sync(player)
	end)
	print("[Quests] ready")
end

return QuestService
