--!strict
-- DailyService — SPEC §47: dailies create fresh POSSIBILITY, not attendance.
--
-- Nothing here says "claim Day 37". Instead the world itself is different today:
--   * Ingredient of the Day  — one unusual ingredient spawns far more often
--   * Trait of the Day       — foods pushing this trait are 25% stronger
--   * Creature weather       — rolls every few minutes; rain boosts water foods, storms
--                              supercharge electric ones, wind lifts air
--   * Day / night            — a 20-minute cycle; Night foods are stronger after dark
--   * Wandering merchant     — deterministic rotating stock (same for everyone today)
--
-- Deterministic per UTC day, so every server agrees and players can share tips.
-- Clients read it from ReplicatedStorage.WorldState attributes.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Economy = require(Shared.Config:WaitForChild("Economy"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local GameEvents = require(script.Parent.GameEvents)

local DailyService = {}

local DAY_LENGTH = 20 * 60 -- real seconds per in-game day
local WEATHERS = {
	{ id = "Sunny", weight = 50, minutes = { 6, 9 } },
	{ id = "Rain", weight = 20, minutes = { 4, 6 }, boost = { Water = 1.5, Nature = 1.25 } },
	{ id = "Windy", weight = 15, minutes = { 3, 5 }, boost = { Air = 1.5 } },
	{ id = "Storm", weight = 10, minutes = { 3, 4 }, boost = { Electric = 1.6 } },
	{ id = "Fog", weight = 5, minutes = { 3, 4 }, boost = { Mystic = 1.4, Dark = 1.3 } },
}

local state: Folder
local current = {
	day = 0,
	ingredientOfDay = "Apple",
	traitOfDay = "Nature",
	weather = WEATHERS[1],
	weatherEndsAt = 0,
	merchant = {},
}

local function dayNumber(): number
	return math.floor(os.time() / 86400)
end

local function seededRandom(day: number, salt: number): Random
	return Random.new(day * 7919 + salt)
end

function DailyService.isNight(): boolean
	local t = Lighting.ClockTime
	return t < 6 or t > 19
end

-- Multiplier applied to one trait's influence when feeding right now.
function DailyService.influenceMultiplier(trait: string): number
	local m = 1
	if trait == current.traitOfDay then
		m *= 1.25
	end
	local boost = current.weather.boost
	if boost and boost[trait] then
		m *= boost[trait]
	end
	if (trait == "Night" or trait == "Dark") and DailyService.isNight() then
		m *= 1.35
	end
	return m
end

function DailyService.spawnWeight(ingredientId: string): number
	if ingredientId == current.ingredientOfDay then
		return 4
	end
	if current.weather.id == "Rain" then
		local def = Ingredients.get(ingredientId)
		if def and (def.influences.Water or 0) > 0 then
			return 2
		end
	end
	return 1
end

function DailyService.weather(): string
	return current.weather.id
end

local function publish()
	state:SetAttribute("Day", current.day)
	state:SetAttribute("IngredientOfDay", current.ingredientOfDay)
	state:SetAttribute("TraitOfDay", current.traitOfDay)
	state:SetAttribute("Weather", current.weather.id)
	state:SetAttribute("WeatherEndsAt", current.weatherEndsAt)
	local stock = {}
	for _, item in ipairs(current.merchant) do
		table.insert(stock, item.id .. ":" .. item.price)
	end
	state:SetAttribute("MerchantStock", table.concat(stock, ","))
end

local function rollDay(day: number)
	current.day = day
	-- ingredient of the day: an Uncommon or Rare from a biome that exists today
	local rng = seededRandom(day, 1)
	local candidates = {}
	for _, id in ipairs(Ingredients.order) do
		local def = Ingredients.get(id)
		if def and (def.rarity == "Uncommon" or def.rarity == "Rare") then
			local event = false
			for _, b in ipairs(def.biomes) do
				if b == "Event" then
					event = true
				end
			end
			if not event then
				table.insert(candidates, id)
			end
		end
	end
	current.ingredientOfDay = candidates[rng:NextInteger(1, #candidates)]
	local trng = seededRandom(day, 2)
	current.traitOfDay = Traits.order[trng:NextInteger(1, #Traits.order)]

	-- merchant: 6 distinct items, deterministic, priced by rarity (SPEC §29 coin sink)
	local mrng = seededRandom(day, 3)
	local pool = table.clone(Ingredients.order)
	current.merchant = {}
	for _ = 1, 6 do
		if #pool == 0 then
			break
		end
		local id = table.remove(pool, mrng:NextInteger(1, #pool))
		local def = Ingredients.get(id)
		local skip = false
		for _, b in ipairs(def.biomes) do
			if b == "Event" then
				skip = true
			end
		end
		if not skip then
			table.insert(current.merchant, { id = id, price = (Economy.merchantPrice or {})[def.rarity] or 50 })
		end
	end
	publish()
	print(string.format("[Daily] day %d: ingredient=%s trait=%s merchant=%d items", day, current.ingredientOfDay, current.traitOfDay, #current.merchant))
end

local function rollWeather()
	local total = 0
	for _, w in ipairs(WEATHERS) do
		total += w.weight
	end
	local r = math.random() * total
	local pick = WEATHERS[1]
	for _, w in ipairs(WEATHERS) do
		r -= w.weight
		if r <= 0 then
			pick = w
			break
		end
	end
	current.weather = pick
	current.weatherEndsAt = workspace:GetServerTimeNow() + math.random(pick.minutes[1], pick.minutes[2]) * 60
	publish()
	Net.event("WorldNotice"):FireAllClients({ kind = "weather", weather = pick.id })
end

-- Merchant purchase (server-authoritative). SPEC §27: deterministic, never random.
function DailyService.buy(player: Player, ingredientId: string)
	local profile = PlayerDataService.get(player)
	if not profile then
		return { ok = false, reason = "no profile" }
	end
	local item
	for _, it in ipairs(current.merchant) do
		if it.id == ingredientId then
			item = it
		end
	end
	if not item then
		return { ok = false, reason = "not sold today" }
	end
	profile.daily.bought = profile.daily.bought or {}
	if profile.daily.day ~= current.day then
		profile.daily.day = current.day
		profile.daily.bought = {}
	end
	if (profile.daily.bought[ingredientId] or 0) >= 3 then
		return { ok = false, reason = "sold out for you today" }
	end
	if not PlayerDataService.spend(player, { Coins = item.price }) then
		return { ok = false, reason = "not enough coins" }
	end
	profile.daily.bought[ingredientId] = (profile.daily.bought[ingredientId] or 0) + 1
	PlayerDataService.give(player, ingredientId, 1)
	GameEvents.fire(player, "merchant_buy", { ingredient = ingredientId })
	PlayerDataService.sync(player)
	return { ok = true }
end

function DailyService.current()
	return current
end

function DailyService.start()
	state = ReplicatedStorage:FindFirstChild("WorldState") :: Folder
	if not state then
		state = Instance.new("Folder")
		state.Name = "WorldState"
		state.Parent = ReplicatedStorage
	end
	rollDay(dayNumber())
	rollWeather()

	-- day/night cycle, continuous
	Lighting.ClockTime = 9.5
	task.spawn(function()
		while true do
			local dt = task.wait(1)
			Lighting.ClockTime = (Lighting.ClockTime + dt * 24 / DAY_LENGTH) % 24
		end
	end)

	task.spawn(function()
		while true do
			task.wait(5)
			if dayNumber() ~= current.day then
				rollDay(dayNumber())
			end
			if workspace:GetServerTimeNow() > current.weatherEndsAt then
				rollWeather()
			end
		end
	end)
	print("[Daily] ready")
end

return DailyService
