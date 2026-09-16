--!strict
-- PlayerDataService — the profile is the single source of truth. SPEC §70.
--
-- DataStore is unavailable in a Studio playtest without API access enabled, so we
-- fall back to an in-memory store rather than erroring. The fallback is loud in the
-- log: silently losing saves is how you ship a game that eats people's creatures.

local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local PlayerDataService = {}

local STORE_NAME = "FeedAMonster_Profiles_v1"
local AUTOSAVE_SECONDS = 120

local store: DataStore? = nil
local memoryOnly = false
do
	local ok, result = pcall(function()
		return DataStoreService:GetDataStore(STORE_NAME)
	end)
	if ok then
		store = result
	else
		memoryOnly = true
		warn("[PlayerData] DataStore unavailable, running MEMORY-ONLY (progress will not persist):", result)
	end
end

local profiles: { [number]: any } = {}
local memoryStore: { [string]: any } = {}

local function defaultProfile()
	return {
		coins = 0,
		essence = 0,
		inventory = {},
		discovered = { ingredients = {}, traits = {}, mutations = {} },
		creatures = {},
		activeCreature = 0,
		lineage = 1,
		ftueStep = 0,
		lastSeen = os.time(),
		sanctuaryTier = 1,
		detailMode = false,
		stats = { feeds = 0, sessions = 0, gatesOpened = 0, trials = 0 },
	}
end

local function key(player: Player): string
	return "p_" .. tostring(player.UserId)
end

local function load(player: Player)
	local k = key(player)
	if memoryOnly or not store then
		return memoryStore[k]
	end
	local ok, data = pcall(function()
		return (store :: DataStore):GetAsync(k)
	end)
	if not ok then
		warn("[PlayerData] load failed for", player.Name, data)
		return nil
	end
	return data
end

local function persist(player: Player, profile)
	local k = key(player)
	if memoryOnly or not store then
		memoryStore[k] = TableUtil.deepCopy(profile)
		return true
	end
	local ok, err = pcall(function()
		(store :: DataStore):SetAsync(k, profile)
	end)
	if not ok then
		warn("[PlayerData] save failed for", player.Name, err)
	end
	return ok
end

-- Migrate/repair a loaded profile so a schema change never bricks an account.
local function reconcile(loaded)
	local profile = defaultProfile()
	if type(loaded) ~= "table" then
		return profile
	end
	for k, v in pairs(loaded) do
		if profile[k] ~= nil then
			profile[k] = v
		end
	end
	profile.discovered = profile.discovered or {}
	profile.discovered.ingredients = profile.discovered.ingredients or {}
	profile.discovered.traits = profile.discovered.traits or {}
	profile.discovered.mutations = profile.discovered.mutations or {}
	profile.inventory = profile.inventory or {}
	profile.creatures = profile.creatures or {}
	profile.stats = profile.stats or { feeds = 0, sessions = 0, gatesOpened = 0, trials = 0 }
	return profile
end

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

function PlayerDataService.sync(player: Player)
	local profile = profiles[player.UserId]
	if profile then
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
	return true
end

function PlayerDataService.save(player: Player)
	local profile = profiles[player.UserId]
	if profile then
		profile.lastSeen = os.time()
		persist(player, profile)
	end
end

local onLoadedCallbacks: { (Player, any) -> () } = {}
function PlayerDataService.onLoaded(fn)
	table.insert(onLoadedCallbacks, fn)
end

local function playerAdded(player: Player)
	local profile = reconcile(load(player))
	profile.stats.sessions += 1
	profiles[player.UserId] = profile

	for _, fn in ipairs(onLoadedCallbacks) do
		task.spawn(fn, player, profile)
	end
	PlayerDataService.sync(player)
end

local function playerRemoving(player: Player)
	PlayerDataService.save(player)
	profiles[player.UserId] = nil
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
				PlayerDataService.save(player)
			end
		end
	end)

	game:BindToClose(function()
		for _, player in ipairs(Players:GetPlayers()) do
			PlayerDataService.save(player)
		end
		if not RunService:IsStudio() then
			task.wait(2)
		end
	end)

	print("[PlayerData] ready. memoryOnly =", memoryOnly)
end

PlayerDataService.memoryOnly = memoryOnly
return PlayerDataService
