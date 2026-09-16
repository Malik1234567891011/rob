--!strict
-- ShopPanel — SPEC §31–36. It does not scream. No countdowns, no fake discounts, no random
-- boxes, nothing that sells creatures, genes or luck. The HUD button only exists after the
-- first evolution, and the server refuses prompts before then too.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Monetization = require(Shared.Config:WaitForChild("Monetization"))

local ShopPanel = {}
ShopPanel.title = "Shop"
ShopPanel.emoji = "🛍️"
ShopPanel.height = 0.66

function ShopPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 8)
	Theme.pad(scroll, 2, 4)

	local function row(order, def, owned: boolean, kind: string, key: string)
		local card = Theme.card(scroll, Theme.PAPER2, 16)
		card.Size = UDim2.new(1, -8, 0, 84)
		card.LayoutOrder = order
		Theme.text({ text = def.emoji, textSize = 38, align = Enum.TextXAlignment.Center, size = UDim2.fromOffset(64, 84), parent = card })
		Theme.text({ text = def.display, font = Theme.DISPLAY, textSize = 20, pos = UDim2.fromOffset(66, 10), size = UDim2.new(1, -200, 0, 26), parent = card })
		Theme.text({ text = def.blurb, textSize = 13, color = Theme.MUTED, pos = UDim2.fromOffset(66, 36), size = UDim2.new(1, -200, 0, 40), parent = card })
		local soon = not def.id or def.id <= 0
		Theme.button({ label = owned and "Owned" or (soon and "Soon" or ("R$ " .. def.price)), size = UDim2.fromOffset(110, 52),
			pos = UDim2.new(1, -122, 0.5, -26), textSize = 18, parent = card,
			color = (owned or soon) and Theme.PAPER or Theme.accent.shop, onClick = function()
				if owned or soon then
					return
				end
				local r = Net.func("ShopPrompt"):InvokeServer(kind, key)
				if r and not r.ok then
					ctx.toast({ title = "SHOP", label = tostring(r.reason), color = 0xFFC440 })
				end
			end })
	end

	local function refresh()
		Theme.clear(scroll)
		local profile = ctx.profile
		Theme.text({ text = "Everything important in this game is earned by playing. These are conveniences and looks.",
			textSize = 15, color = Theme.MUTED, parent = scroll, order = 0, auto = true })
		Theme.text({ text = "PASSES", font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = 1 })
		for i, key in ipairs(Monetization.passOrder) do
			row(1 + i, Monetization.passes[key], profile and profile.passes[key] == true, "pass", key)
		end
		Theme.text({ text = "EXTRAS", font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = 20 })
		for i, key in ipairs(Monetization.productOrder) do
			local def = Monetization.products[key]
			local owned = def.cosmetic and profile and profile.cosmetics.owned[def.cosmetic] == true or false
			row(20 + i, def, owned, "product", key)
		end
	end

	return { refresh = refresh }
end

return ShopPanel
