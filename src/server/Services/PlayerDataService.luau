--!strict
-- PlayerDataService — the profile is the single source of truth. SPEC §70.
--
-- SPEC §52: "Do not delete someone's six-month digital pet." So saves are defensive:
--   * SESSION LOCK in the record itself (jobId + heartbeat). A second server that loads
--     while the lock is fresh waits and retries, and only steals a STALE lock. Two servers
--     can never both write the same player.
--   * UpdateAsync everywhere, never SetAsync: every write re-reads, checks the lock is
--     still ours, then writes.
--   * Retries with backoff on every DataStore call; failures are loud.
--   * Schema versioning + `reconcile` so an old profile always loads into the new shape.
--
-- Unpublished Studio places have no DataStore; we fall back to memory and say so loudly.

local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = {}

local STORE_NAME = "FeedAMonster_Profiles_v1"
local SCHEMA = 2
local AUTOSAVE_SECONDS = 90
local LOCK_STALE_SECONDS = 300
local LOAD_ATTEMPTS = 6

local JOB_ID = (game.JobId ~= "" and game.JobId) or ("studio-" .. HttpService:GenerateGUID(false))

local store: DataStore? = nil
local memoryOnly = false
do
	local ok, result = pcall(function()
		return DataStoreService:GetDataStore(STORE_NAME)
	end)
	if ok then
		store = result
		-- GetDataStore succeeds in an unpublished place; the first request fails. Probe once.
		local probeOk = pcall(function()
			(store :: DataStore):GetAsync("__probe")
		end)
		if not probeOk then
			store = nil
			memoryOnly = true
		end
	else
		memoryOnly = true
	end
	if memoryOnly then
		warn("[PlayerData] DataStore unavailable, running MEMORY-ONLY (progress will not persist). Publish the place to enable saving.")
	end
end

local profiles: { [number]: any } = {}
local memoryStore: { [string]: any } = {}
local dirty: { [number]: boolean } = {}

-- ═══ SCHEMA ══════════════════════════════════════════════════════════════════

local function defaultProfile()
	return {
		schema = SCHEMA,
		coins = 0,
		essence = 0,
		inventory = {},
		discovered = { ingredients = {}, traits = {}, mutations = {}, combos = {} },
		creatures = {},
		activeCreature = 0,
		lineage = 1,
		ftueStep = 0,
		firstSeen = os.time(),
		lastSeen = os.time(),
		detailMode = false,
		gatesOpened = {},
		sanctuary = { tier = 1, decor = {}, garden = {} },
		quests = { active = {}, completedTotal = 0, refreshedDay = 0 },
		daily = { day = 0, streak = 0 },
		trials = { best = {}, played = 0, wins = 0 },
		parade = { entered = 0, votes = {} },
		cosmetics = { owned = {}, equipped = {}, style = {} },
		passes = {},
		settings = { music = true, sfx = true },
		stats = { feeds = 0, sessions = 0, gatesOpened = 0, trials = 0, pets = 0, evolutions = 0, eventsJoined = 0 },
		pickedFirst = false,
	}
end

-- Deep-merge `loaded` over defaults, keeping unknown-but-valid old data safe.
local function mergeInto(target, source)
	for k, v in pairs(source) do
		if type(v) == "table" and type(target[k]) == "table" and next(target[k]) ~= nil and #target[k] == 0 then
			mergeInto(target[k], v)
		else
			target[k] = v
		end
	end
end

local function reconcile(loaded)
	local profile = defaultProfile()
	if type(loaded) ~= "table" then
		return profile
	end
	loaded.__lock = nil
	mergeInto(profile, loaded)
	profile.schema = SCHEMA
	-- v1 kept gatesOpened as a stat number only
	if type(profile.gatesOpened) ~= "table" then
		profile.gatesOpened = {}
	end
	profile.cosmetics.style = profile.cosmetics.style or {}
	profile.cosmetics.equipped = profile.cosmetics.equipped or {}
	for _, c in ipairs(profile.creatures) do
		c.abilities = c.abilities or {}
		c.mutations = c.mutations or {}
		c.traits = c.traits or {}
		c.genes = c.genes or {}
		c.recent = c.recent or {}
	end
	if profile.activeCreature > #profile.creatures then
		profile.activeCreature = #profile.creatures
	end
	return profile
end

-- ═══ STORE ACCESS ════════════════════════════════════════════════════════════

local function key(userId: number): string
	return "p_" .. tostring(userId)
end

local function retry<T>(label: string, fn: () -> T): (boolean, T | string)
	local lastErr = ""
	for attempt = 1, 4 do
		local ok, result = pcall(fn)
		if ok then
			return true, result
		end
		lastErr = tostring(result)
		task.wait(attempt * attempt * 0.5)
	end
	warn("[PlayerData] " .. label .. " failed after retries: " .. lastErr)
	return false, lastErr
end

-- Load and take the session lock. Returns (profile, reason)
local function loadLocked(player: Player)
	local k = key(player.UserId)
	if memoryOnly or not store then
		return reconcile(memoryStore[k] and TableUtil.deepCopy(memoryStore[k]) or nil), nil
	end
	for attempt = 1, LOAD_ATTEMPTS do
		local blockedBy: string? = nil
		local ok, data = retry("load " .. player.Name, function()
			return (store :: DataStore):UpdateAsync(k, function(old)
				old = old or {}
				local lock = old.__lock
				if lock and lock.job ~= JOB_ID and (os.time() - (lock.at or 0)) < LOCK_STALE_SECONDS then
					blockedBy = lock.job
					return nil -- cancel the write; someone else holds it
				end
				old.__lock = { job = JOB_ID, at = os.time() }
				return old
			end)
		end)
		if not ok then
			return nil, "load failed"
		end
		if not blockedBy then
			return reconcile(data), nil
		end
		warn(string.format("[PlayerData] %s is locked by another server (%s), waiting (%d/%d)", player.Name, tostring(blockedBy), attempt, LOAD_ATTEMPTS))
		task.wait(6)
	end
	return nil, "locked"
end

local function persist(userId: number, profile, release: boolean)
	local k = key(userId)
	if memoryOnly or not store then
		memoryStore[k] = TableUtil.deepCopy(profile)
		return true
	end
	local lostLock = false
	local ok = retry("save " .. userId, function()
		return (store :: DataStore):UpdateAsync(k, function(old)
			old = old or {}
			local lock = old.__lock
			if lock and lock.job ~= JOB_ID then
				lostLock = true
				return nil -- another server owns this player now; never overwrite it
			end
			local out = TableUtil.deepCopy(profile)
			out.__lock = (not release) and { job = JOB_ID, at = os.time() } or nil
			return out
		end)
	end)
	if lostLock then
		warn("[PlayerData] save skipped for " .. userId .. ": session lock held elsewhere")
		return false
	end
	return ok
end

-- ═══ API ═════════════════════════════════════════════════════════════════════

function PlayerDataService.get(player: Player)
	return profiles[player.UserId]
end

function PlayerDataService.activeCreature(player: Player)
	local profile = profiles[player.UserId]
	if not profile then
		return nil
	end
	return profile.creatures[profile.activeCreature]
end

function PlayerDataService.markDirty(player: Player)
	dirty[player.UserId] = true
end

-- Client only ever sees a sanitised copy.
function PlayerDataService.sync(player: Player)
	local profile = profiles[player.UserId]
	if profile then
		dirty[player.UserId] = true
		Net.event("ProfileSync"):FireClient(player, profile)
	end
end

function PlayerDataService.addCurrency(player: Player, rewards)
	local profile = profiles[player.UserId]
	if not profile or not rewards then
		return
	end
	for currency, amount in pairs(rewards) do
		if currency == "Coins" then
			profile.coins += amount
		elseif currency == "Essence" then
			profile.essence += amount
		end
	end
	dirty[player.UserId] = true
end

function PlayerDataService.give(player: Player, ingredientId: string, n: number?)
	local profile = profiles[player.UserId]
	if not profile then
		return
	end
	profile.inventory[ingredientId] = (profile.inventory[ingredientId] or 0) + (n or 1)
	dirty[player.UserId] = true
end

function PlayerDataService.spend(player: Player, cost): boolean
	local profile = profiles[player.UserId]
	if not profile then
		return false
	end
	if (cost.Coins or 0) > profile.coins or (cost.Essence or 0) > profile.essence then
		return false
	end
	profile.coins -= (cost.Coins or 0)
	profile.essence -= (cost.Essence or 0)
	dirty[player.UserId] = true
	return true
end

function PlayerDataService.stat(player: Player, name: string, delta: number?)
	local profile = profiles[player.UserId]
	if profile then
		profile.stats[name] = (profile.stats[name] or 0) + (delta or 1)
		dirty[player.UserId] = true
	end
end

function PlayerDataService.save(player: Player, release: boolean?)
	local profile = profiles[player.UserId]
	if profile then
		profile.lastSeen = os.time()
		persist(player.UserId, profile, release == true)
		dirty[player.UserId] = nil
	end
end

local onLoadedCallbacks: { (Player, any) -> () } = {}
function PlayerDataService.onLoaded(fn)
	table.insert(onLoadedCallbacks, fn)
	-- late subscribers still hear about players already loaded
	for userId, profile in pairs(profiles) do
		local p = Players:GetPlayerByUserId(userId)
		if p then
			task.spawn(fn, p, profile)
		end
	end
end

local onLeavingCallbacks: { (Player, any) -> () } = {}
function PlayerDataService.onLeaving(fn)
	table.insert(onLeavingCallbacks, fn)
end

local function playerAdded(player: Player)
	local profile, reason = loadLocked(player)
	if not player.Parent then
		if profile then
			persist(player.UserId, profile, true)
		end
		return
	end
	if not profile then
		player:Kick(reason == "locked"
			and "Your monster is still settling in on another server. Please rejoin in a minute!"
			or "We couldn't load your monster right now. Please rejoin in a moment!")
		return
	end
	profile.stats.sessions += 1
	profiles[player.UserId] = profile
	player:SetAttribute("ProfileLoaded", true)

	for _, fn in ipairs(onLoadedCallbacks) do
		task.spawn(fn, player, profile)
	end
	PlayerDataService.sync(player)
end

local function playerRemoving(player: Player)
	local profile = profiles[player.UserId]
	if not profile then
		return
	end
	for _, fn in ipairs(onLeavingCallbacks) do
		pcall(fn, player, profile)
	end
	PlayerDataService.save(player, true)
	profiles[player.UserId] = nil
	dirty[player.UserId] = nil
end

function PlayerDataService.start()
	Players.PlayerAdded:Connect(playerAdded)
	Players.PlayerRemoving:Connect(playerRemoving)
	for _, player in ipairs(Players:GetPlayers()) do
		task.spawn(playerAdded, player)
	end

	task.spawn(function()
		while true do
			task.wait(AUTOSAVE_SECONDS)
			for _, player in ipairs(Players:GetPlayers()) do
				-- always refresh the lock heartbeat, even if nothing changed
				if profiles[player.UserId] then
					task.spawn(PlayerDataService.save, player, false)
				end
			end
		end
	end)

	game:BindToClose(function()
		local pending = 0
		for _, player in ipairs(Players:GetPlayers()) do
			if profiles[player.UserId] then
				pending += 1
				task.spawn(function()
					PlayerDataService.save(player, true)
					pending -= 1
				end)
			end
		end
		local deadline = os.clock() + 25
		while pending > 0 and os.clock() < deadline do
			task.wait(0.2)
		end
	end)

	print("[PlayerData] ready. memoryOnly =", memoryOnly, "job =", JOB_ID)
end

PlayerDataService.memoryOnly = memoryOnly
PlayerDataService.SCHEMA = SCHEMA
return PlayerDataService
