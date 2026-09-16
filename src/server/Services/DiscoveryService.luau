--!strict
-- DiscoveryService — SPEC §25 The Discovery Book.
-- Not a Pokedex of 300 predefined creatures. Foods / traits / mutations, and we
-- never tell the player the total. "1 / ???" — mystery matters (SPEC §8).

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Economy = require(Shared.Config:WaitForChild("Economy"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local AnalyticsService = require(script.Parent.AnalyticsService)

local DiscoveryService = {}

-- Server-wide firsts, for the Community Research Board (SPEC §77, §78).
DiscoveryService.worldFirsts = {}
DiscoveryService.globalStats = { itemsEaten = 0, eatenToday = {} }

local function toast(player: Player, payload)
	Net.event("Toast"):FireClient(player, payload)
end

function DiscoveryService.ingredient(player: Player, id: string): boolean
	local profile = PlayerDataService.get(player)
	if not profile or profile.discovered.ingredients[id] then
		return false
	end
	local def = Ingredients.get(id)
	if not def then
		return false
	end
	profile.discovered.ingredients[id] = true
	PlayerDataService.addCurrency(player, Economy.rewards.firstFeedOfIngredient)
	AnalyticsService.track("ingredient_discovered", player, { ingredient = id, rarity = def.rarity })
	toast(player, {
		kind = "ingredient",
		title = "NEW INGREDIENT",
		label = def.emoji .. " " .. def.display,
		color = Ingredients.rarityColor[def.rarity],
	})
	return true
end

function DiscoveryService.trait(player: Player, id: string): boolean
	local profile = PlayerDataService.get(player)
	if not profile or profile.discovered.traits[id] then
		return false
	end
	local def = Traits.get(id)
	if not def then
		return false
	end
	profile.discovered.traits[id] = true
	PlayerDataService.addCurrency(player, Economy.rewards.traitUnlocked)
	AnalyticsService.track("trait_unlocked", player, { trait = id })

	local count = 0
	for _ in pairs(profile.discovered.traits) do
		count += 1
	end
	toast(player, {
		kind = "trait",
		title = "NEW TRAIT DISCOVERED",
		label = def.emoji .. " " .. def.display,
		sub = def.blurb,
		-- SPEC §8: never reveal the denominator
		progress = count .. " / ???",
		color = def.color,
	})
	return true
end

function DiscoveryService.mutation(player: Player, id: string): boolean
	local profile = PlayerDataService.get(player)
	if not profile then
		return false
	end
	local def = Mutations.get(id)
	if not def then
		return false
	end
	local firstForPlayer = not profile.discovered.mutations[id]
	profile.discovered.mutations[id] = true

	if firstForPlayer then
		PlayerDataService.addCurrency(player,
			def.secret and Economy.rewards.secretMutation or Economy.rewards.mutationUnlocked)
		AnalyticsService.track("mutation_unlocked", player, {
			mutation = id, rarity = def.rarity, secret = def.secret == true,
		})
	end

	-- SPEC §77: discovery creates permanent status that is not purchasable.
	local worldFirst = false
	if not DiscoveryService.worldFirsts[id] then
		DiscoveryService.worldFirsts[id] = { player = player.Name, at = os.time() }
		worldFirst = true
	end

	toast(player, {
		kind = "mutation",
		title = worldFirst and "WORLD FIRST" or "MUTATION!",
		label = def.emoji .. " " .. def.display,
		sub = def.hint,
		rarity = def.rarity,
		secret = def.secret == true,
		color = Ingredients.rarityColor[def.rarity] or 0xFFD52E,
	})
	return firstForPlayer
end

function DiscoveryService.recordEaten(id: string)
	DiscoveryService.globalStats.itemsEaten += 1
	DiscoveryService.globalStats.eatenToday[id] = (DiscoveryService.globalStats.eatenToday[id] or 0) + 1
end

-- SPEC §78 Community Research Board
function DiscoveryService.boardSummary()
	local topId, topN = nil, 0
	for id, n in pairs(DiscoveryService.globalStats.eatenToday) do
		if n > topN then
			topId, topN = id, n
		end
	end
	local firsts = {}
	for mutationId, info in pairs(DiscoveryService.worldFirsts) do
		table.insert(firsts, { mutation = mutationId, player = info.player, at = info.at })
	end
	table.sort(firsts, function(a, b)
		return a.at > b.at
	end)
	return {
		itemsEaten = DiscoveryService.globalStats.itemsEaten,
		mostEatenToday = topId,
		mostEatenCount = topN,
		worldFirsts = firsts,
		undiscoveredSecrets = Mutations.secretCount() - (function()
			local n = 0
			for id in pairs(DiscoveryService.worldFirsts) do
				if (Mutations.get(id) or {}).secret then
					n += 1
				end
			end
			return n
		end)(),
	}
end

return DiscoveryService
