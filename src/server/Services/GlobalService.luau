--!strict
-- GlobalService — SPEC §77 world firsts + §78 Community Research Board, across ALL servers.
--
--   "WORLD FIRST — StaticFrog22 discovered VOID MOTH" + timestamp.
--   "72.8B items eaten · Most eaten today: 🍎 Apple · Largest creature alive: Chunk — Gen 19"
--   "Discovery creates permanent status that is not purchasable."
--
-- Writes are batched (one UpdateAsync per minute per key) so a busy server never hammers
-- the DataStore. World firsts use set-if-absent so two servers can never both claim one.
-- The merged board is published to ReplicatedStorage.WorldState as JSON for clients.

local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local GameEvents = require(script.Parent.GameEvents)

local GlobalService = {}

local store: DataStore? = nil
local pendingEaten = 0
local pendingToday: { [string]: number } = {}
local board = {
	itemsEaten = 0,
	eatenToday = {} :: { [string]: number },
	day = 0,
	firsts = {} :: { [string]: { name: string, userId: number, at: number } },
	largest = nil :: any,
}

local function today(): number
	return math.floor(os.time() / 86400)
end

-- SPEC §78 "Unsolved: ??? + Battery + Star Fragment". Each day one undiscovered secret
-- gets a partial recipe: the strongest ingredient for each of its required traits, with
-- the most important one hidden. Enough to start a rumour, never enough to solve it.
local function unsolvedHint(): { string }?
	local open = {}
	for _, id in ipairs(Mutations.order or {}) do
		local def = Mutations.get(id)
		if def and def.secret and not board.firsts[id] and def.requirements then
			table.insert(open, id)
		end
	end
	if #open == 0 then
		return nil
	end
	local def = Mutations.get(open[(today() % #open) + 1])
	local reqs = {}
	for trait, need in pairs(def.requirements) do
		table.insert(reqs, { trait = trait, need = need })
	end
	table.sort(reqs, function(a, b)
		return a.need > b.need
	end)
	local out = {}
	for i, r in ipairs(reqs) do
		if i > 3 then
			break
		end
		if i == 1 then
			table.insert(out, "???")
		else
			local best, bestV = nil, 0
			for id, ing in pairs(Ingredients.all) do
				local v = ing.influences and ing.influences[r.trait] or 0
				if v > bestV or (v == bestV and best and id < best) then
					best, bestV = id, v
				end
			end
			if best then
				table.insert(out, best)
			end
		end
	end
	return #out >= 2 and out or nil
end

local function publish()
	local ws = ReplicatedStorage:FindFirstChild("WorldState")
	if not ws then
		return
	end
	local top, topN = nil, 0
	for id, n in pairs(board.eatenToday) do
		if n > topN then
			top, topN = id, n
		end
	end
	local firsts = {}
	for id, f in pairs(board.firsts) do
		table.insert(firsts, { mutation = id, name = f.name, at = f.at })
	end
	table.sort(firsts, function(a, b)
		return a.at > b.at
	end)
	local secretsFound = 0
	for id in pairs(board.firsts) do
		if (Mutations.get(id) or {}).secret then
			secretsFound += 1
		end
	end
	ws:SetAttribute("Board", HttpService:JSONEncode({
		itemsEaten = board.itemsEaten + pendingEaten,
		mostEatenToday = top, mostEatenCount = topN,
		firsts = { table.unpack(firsts, 1, math.min(#firsts, 8)) },
		undiscoveredSecrets = Mutations.secretCount() - secretsFound,
		unsolved = unsolvedHint(),
		largest = board.largest,
	}))
end

function GlobalService.recordEaten(ingredientId: string)
	pendingEaten += 1
	pendingToday[ingredientId] = (pendingToday[ingredientId] or 0) + 1
	board.eatenToday[ingredientId] = (board.eatenToday[ingredientId] or 0) + 1
end

-- Returns true if THIS player is the first in the whole game.
function GlobalService.claimFirst(player: Player, mutationId: string): boolean
	if board.firsts[mutationId] then
		return false
	end
	local entry = { name = player.DisplayName, userId = player.UserId, at = os.time() }
	if not store then
		board.firsts[mutationId] = entry
		publish()
		return true
	end
	local won = false
	local ok = pcall(function()
		(store :: DataStore):UpdateAsync("firsts", function(old)
			old = old or {}
			if old[mutationId] then
				board.firsts[mutationId] = old[mutationId]
				return nil
			end
			old[mutationId] = entry
			won = true
			return old
		end)
	end)
	if ok and won then
		board.firsts[mutationId] = entry
		publish()
	end
	return ok and won
end

function GlobalService.considerLargest(player: Player, model: Model)
	local scale = model:GetAttribute("Scale") or 1
	if board.largest and board.largest.scale >= scale then
		return
	end
	local genome = PlayerDataService.activeCreature(player)
	board.largest = { name = genome and genome.name or "???", owner = player.DisplayName, scale = scale, gen = genome and genome.generation or 1 }
	publish()
end

local function flush()
	if not store then
		board.itemsEaten += pendingEaten
		pendingEaten = 0
		pendingToday = {}
		publish()
		return
	end
	local eaten = pendingEaten
	local todayCounts = pendingToday
	pendingEaten = 0
	pendingToday = {}
	pcall(function()
		(store :: DataStore):UpdateAsync("totals", function(old)
			old = old or { itemsEaten = 0 }
			old.itemsEaten = (old.itemsEaten or 0) + eaten
			board.itemsEaten = old.itemsEaten
			if (old.largest == nil) or (board.largest and board.largest.scale > (old.largest.scale or 0)) then
				old.largest = board.largest
			else
				board.largest = old.largest
			end
			return old
		end)
	end)
	local d = today()
	pcall(function()
		(store :: DataStore):UpdateAsync("day_" .. d, function(old)
			old = old or {}
			for id, n in pairs(todayCounts) do
				old[id] = (old[id] or 0) + n
			end
			board.eatenToday = old
			return old
		end)
	end)
	pcall(function()
		local firsts = (store :: DataStore):GetAsync("firsts")
		if type(firsts) == "table" then
			board.firsts = firsts
		end
	end)
	publish()
end

function GlobalService.start()
	if not PlayerDataService.memoryOnly then
		local ok, s = pcall(function()
			return DataStoreService:GetDataStore("FeedAMonster_Global_v1")
		end)
		store = ok and s or nil
	end
	board.day = today()

	GameEvents.on("fed", function(_player, data)
		GlobalService.recordEaten(data.ingredient)
	end)
	GameEvents.on("mutation_new", function(player, data)
		if GlobalService.claimFirst(player, data.mutation) then
			PlayerDataService.addCurrency(player, Economy.rewards.worldFirst)
			local def = Mutations.get(data.mutation)
			Net.event("WorldNotice"):FireAllClients({
				kind = "world_first", owner = player.DisplayName,
				mutation = def and (def.emoji .. " " .. string.upper(def.display)) or data.mutation,
			})
			PlayerDataService.sync(player)
		end
	end)

	task.spawn(function()
		flush()
		while true do
			task.wait(60)
			flush()
		end
	end)
	game:BindToClose(function()
		flush()
	end)
	print("[Global] ready. persistent =", store ~= nil)
end

return GlobalService
