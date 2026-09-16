--!strict
-- MonetizationService — SPEC §31–36. Receipts are idempotent and saved before granting is
-- acknowledged, so a purchase is never lost and never granted twice.
--
-- The shop is never pushed: there is no prompt before the first evolution (SPEC §36), no
-- countdowns, no "97% OFF", and nothing that sells creatures, genes or luck (SPEC §34).

local Players = game:GetService("Players")
local MarketplaceService = game:GetService("MarketplaceService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Monetization = require(Shared.Config:WaitForChild("Monetization"))

local PlayerDataService = require(script.Parent.PlayerDataService)

local MonetizationService = {}

local productById: { [number]: string } = {}
for key, def in pairs(Monetization.products) do
	if def.id and def.id > 0 then
		productById[def.id] = key
	end
end

function MonetizationService.hasPass(player: Player, key: string): boolean
	local profile = PlayerDataService.get(player)
	return profile ~= nil and profile.passes[key] == true
end

function MonetizationService.backpackCapacity(player: Player): number
	return MonetizationService.hasPass(player, "BigBackpack") and Monetization.backpackPass or Monetization.backpackBase
end

function MonetizationService.creatureSlots(player: Player): number
	return MonetizationService.hasPass(player, "ExtraSlots") and Monetization.slotsPass or Monetization.slotsBase
end

local function refreshPasses(player: Player)
	local profile = PlayerDataService.get(player)
	if not profile then
		return
	end
	for key, def in pairs(Monetization.passes) do
		if def.id and def.id > 0 then
			local ok, owns = pcall(MarketplaceService.UserOwnsGamePassAsync, MarketplaceService, player.UserId, def.id)
			if ok and owns then
				profile.passes[key] = true
			end
		end
	end
	PlayerDataService.sync(player)
end

local function allowedToPrompt(player: Player): (boolean, string?)
	local profile = PlayerDataService.get(player)
	if not profile then
		return false, "no profile"
	end
	if (profile.stats.evolutions or 0) < Monetization.requireEvolutions then
		return false, "evolve your monster first"
	end
	return true, nil
end

function MonetizationService.prompt(player: Player, kind: string, key: string)
	local ok, reason = allowedToPrompt(player)
	if not ok then
		return { ok = false, reason = reason }
	end
	local def = (kind == "pass" and Monetization.passes or Monetization.products)[key]
	if not def then
		return { ok = false, reason = "unknown item" }
	end
	if not def.id or def.id <= 0 then
		return { ok = false, reason = "coming soon" }
	end
	local okAnalytics, Analytics = pcall(require, script.Parent.AnalyticsService)
	if okAnalytics then
		Analytics.track("purchase_prompt", player, { kind = kind, item = key })
	end
	if kind == "pass" then
		MarketplaceService:PromptGamePassPurchase(player, def.id)
	else
		MarketplaceService:PromptProductPurchase(player, def.id)
	end
	return { ok = true }
end

local function grant(player: Player, key: string): boolean
	local profile = PlayerDataService.get(player)
	local def = Monetization.products[key]
	if not profile or not def then
		return false
	end
	if key == "TraitCleanser" then
		local genome = PlayerDataService.activeCreature(player)
		if genome then
			genome.recent = {}
		end
	elseif def.grants then
		for id, n in pairs(def.grants) do
			PlayerDataService.give(player, id, n)
		end
	elseif def.cosmetic then
		profile.cosmetics.owned[def.cosmetic] = true
		profile.cosmetics.equipped.trail = def.cosmetic
	end
	return true
end

local function processReceipt(info)
	local player = Players:GetPlayerByUserId(info.PlayerId)
	if not player then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	local profile = PlayerDataService.get(player)
	if not profile then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	profile.receipts = profile.receipts or {}
	local rid = tostring(info.PurchaseId)
	if profile.receipts[rid] then
		return Enum.ProductPurchaseDecision.PurchaseGranted
	end
	local key = productById[info.ProductId]
	if not key or not grant(player, key) then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	profile.receipts[rid] = os.time()
	-- save BEFORE acknowledging, so a crash can't lose a paid item
	PlayerDataService.save(player, false)
	local okA, Analytics = pcall(require, script.Parent.AnalyticsService)
	if okA then
		Analytics.track("purchase_complete", player, { item = key, robux = info.CurrencySpent })
	end
	Net.event("Toast"):FireClient(player, { kind = "purchase", title = "THANK YOU", label = (Monetization.products[key].emoji or "") .. " " .. Monetization.products[key].display, color = 0xFFD52E })
	PlayerDataService.sync(player)
	return Enum.ProductPurchaseDecision.PurchaseGranted
end

function MonetizationService.start()
	MarketplaceService.ProcessReceipt = processReceipt
	MarketplaceService.PromptGamePassPurchaseFinished:Connect(function(player, passId, purchased)
		if purchased then
			refreshPasses(player)
		end
	end)
	PlayerDataService.onLoaded(function(player)
		refreshPasses(player)
	end)
	Net.func("ShopPrompt").OnServerInvoke = function(player, kind, key)
		if type(kind) ~= "string" or type(key) ~= "string" then
			return { ok = false }
		end
		return MonetizationService.prompt(player, kind, key)
	end
	print("[Monetization] ready")
end

return MonetizationService
