--!strict
-- HomePanel — SPEC §16 Sanctuary, §29 sinks. Upgrade tiers you can SEE, decorations in
-- fixed slots (no fiddly placement on a phone), garden status, and quick travel.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Sanctuary = require(Shared.Config:WaitForChild("Sanctuary"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))

local HomePanel = {}
HomePanel.title = "Home & Travel"
HomePanel.emoji = "🏡"
HomePanel.height = 0.72

local DESTINATIONS = {
	{ id = "Home", emoji = "🏡", label = "My Sanctuary" },
	{ id = "Hub", emoji = "⛲", label = "Town Square" },
	{ id = "Meadow", emoji = "🌼", label = "Meadow" },
	{ id = "Junkyard", emoji = "🔩", label = "Junkyard" },
	{ id = "CrystalCaves", emoji = "💎", label = "Crystal Caves" },
	{ id = "Ocean", emoji = "🌊", label = "The Ocean" },
}

function HomePanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 10)
	Theme.pad(scroll, 2, 4)

	local function header(text, order)
		Theme.text({ text = text, font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = order })
	end

	local function costText(cost): string
		local parts = {}
		if cost.Coins and cost.Coins > 0 then
			table.insert(parts, "🪙 " .. Theme.fmt(cost.Coins))
		end
		if cost.Essence and cost.Essence > 0 then
			table.insert(parts, "🔮 " .. cost.Essence)
		end
		return #parts > 0 and table.concat(parts, "  ") or "Free"
	end

	local function refresh()
		Theme.clear(scroll)
		local profile = ctx.profile
		if not profile then
			return
		end

		-- travel (mobile: nobody should have to walk 400 studs to their plot)
		header("GO TO", 1)
		local travel = Instance.new("Frame")
		travel.BackgroundTransparency = 1
		travel.Size = UDim2.new(1, -8, 0, 0)
		travel.AutomaticSize = Enum.AutomaticSize.Y
		travel.LayoutOrder = 2
		travel.Parent = scroll
		Theme.grid(travel, Vector2.new(150, 56), 8)
		local ws = ctx.world
		for i, d in ipairs(DESTINATIONS) do
			local locked = d.id == "Ocean" and ((ws and ws:GetAttribute("UpdateLevel") or 0) < 1)
			Theme.button({ emoji = locked and "🔒" or d.emoji, label = d.label, size = UDim2.fromOffset(150, 56), textSize = 16, order = i,
				parent = travel, color = locked and Theme.PAPER2 or Theme.lighter(Theme.accent.home, 0.55), onClick = function()
					if locked then
						ctx.toast({ title = "SOMETHING IS IN THE OCEAN", label = "🌊 Coming soon...", color = 0x3FA9F5 })
						return
					end
					local r = ctx.Net.func("Travel"):InvokeServer(d.id)
					if r and r.ok then
						ctx.close()
					elseif r then
						ctx.toast({ title = "CAN'T GO YET", label = tostring(r.reason), color = 0xEC6060 })
					end
				end })
		end

		-- tier
		local tier = profile.sanctuary and profile.sanctuary.tier or 1
		local current = Economy.sanctuaryTiers[tier]
		local nextTier = Economy.sanctuaryTiers[tier + 1]
		header("YOUR SANCTUARY", 10)
		local card = Theme.card(scroll, Theme.lighter(Theme.accent.home, 0.75), 20)
		card.Size = UDim2.new(1, -8, 0, 0)
		card.AutomaticSize = Enum.AutomaticSize.Y
		card.LayoutOrder = 11
		Theme.pad(card, 14, 12)
		Theme.list(card, Enum.FillDirection.Vertical, 8)
		Theme.text({ text = string.format("🏡 <b>%s</b>  ·  Tier %d / %d", current and current.name or "?", tier, #Economy.sanctuaryTiers),
			font = Theme.DISPLAY, textSize = 22, parent = card, order = 1, auto = true })
		local bar, set = Theme.progress(card, Theme.accent.home, 12)
		bar.LayoutOrder = 2
		set(tier / #Economy.sanctuaryTiers)
		if nextTier then
			Theme.text({ text = string.format("Next: <b>%s</b> — builds %s", nextTier.name, table.concat(nextTier.builds, ", "):gsub("_", " ")),
				textSize = 15, parent = card, order = 3, auto = true })
			local afford = profile.coins >= (nextTier.cost.Coins or 0) and profile.essence >= (nextTier.cost.Essence or 0)
			Theme.button({ emoji = "🔨", label = "BUILD  " .. costText(nextTier.cost), size = UDim2.new(1, 0, 0, 56), textSize = 20,
				color = afford and Theme.accent.home or Theme.PAPER2, parent = card, order = 4, onClick = function()
					local r = ctx.Net.func("SanctuaryUpgrade"):InvokeServer()
					if r and not r.ok then
						ctx.toast({ title = "NOT YET", label = tostring(r.reason), color = 0xEC6060 })
					end
				end })
		else
			Theme.text({ text = "Fully built. It tells your whole story. ✨", textSize = 15, parent = card, order = 3, auto = true })
		end

		-- decor shop
		local slots = Sanctuary.slotsFor(tier)
		local used = #(profile.sanctuary and profile.sanctuary.decor or {})
		header(string.format("DECORATE  (%d / %d spots used)", used, slots), 20)
		local shop = Instance.new("Frame")
		shop.BackgroundTransparency = 1
		shop.Size = UDim2.new(1, -8, 0, 0)
		shop.AutomaticSize = Enum.AutomaticSize.Y
		shop.LayoutOrder = 21
		shop.Parent = scroll
		Theme.grid(shop, Vector2.new(120, 116), 8)
		for i, id in ipairs(Sanctuary.decorOrder) do
			local def = Sanctuary.decor[id]
			local cost = "🪙 " .. Theme.fmt(def.price) .. (def.essence and (" 🔮" .. def.essence) or "")
			Theme.button({ emoji = def.emoji, sub = def.display .. "\n" .. cost, size = UDim2.fromOffset(120, 116), textSize = 34, order = i,
				parent = shop, color = profile.coins >= def.price and Theme.PAPER or Theme.PAPER2, onClick = function()
					local r = ctx.Net.func("SanctuaryDecor"):InvokeServer("buy", id)
					ctx.toast({ title = r and r.ok and "PLACED" or "CAN'T PLACE", label = r and r.ok and (def.emoji .. " " .. def.display) or tostring(r and r.reason),
						color = r and r.ok and 0x58C4C4 or 0xEC6060 })
				end })
		end

		-- garden
		if tier >= 6 then
			header("GARDEN", 30)
			local g = Theme.card(scroll, Theme.PAPER2, 18)
			g.Size = UDim2.new(1, -8, 0, 0)
			g.AutomaticSize = Enum.AutomaticSize.Y
			g.LayoutOrder = 31
			Theme.pad(g, 14, 10)
			Theme.list(g, Enum.FillDirection.Vertical, 4)
			local any = false
			for key, plant in pairs(profile.sanctuary.garden or {}) do
				local def = Ingredients.get(plant.id)
				if def then
					any = true
					local grow = Economy.garden.growSeconds[def.rarity] or 300
					local left = grow - (os.time() - plant.at)
					Theme.text({ text = string.format("%s %s — %s", def.emoji, def.display, left <= 0 and "<b>ready to harvest!</b>" or ("ready in " .. Theme.countdown(left))),
						textSize = 15, parent = g, order = 1, auto = true })
				end
			end
			if not any then
				Theme.text({ text = "Plant ingredients from your Bag (tap an item → PLANT). They grow more of themselves.", textSize = 14, color = Theme.MUTED, parent = g, auto = true })
			end
			local _ = key
		end
	end

	return { refresh = refresh }
end

return HomePanel
