--!strict
-- BookPanel — SPEC §25 The Discovery Book. Not a Pokédex of 300 creatures:
--   Foods ✓ / ???  ·  Traits ✓ / ???  ·  Mutations (secrets stay hidden)  ·  Weird combos
-- SPEC §8: never reveal the denominator. We show "12 / ???".
-- SPEC §90: players must form hypotheses, so ordinary undiscovered mutations show their HINT.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))

local BookPanel = {}
BookPanel.title = "Discovery Book"
BookPanel.emoji = "📖"
BookPanel.height = 0.72

function BookPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local tab = "Foods"
	local tabs = Instance.new("Frame")
	tabs.BackgroundTransparency = 1
	tabs.Size = UDim2.new(1, 0, 0, 48)
	tabs.Parent = body
	Theme.list(tabs, Enum.FillDirection.Horizontal, 8)

	local counter = Theme.text({ text = "", font = Theme.BOLD, textSize = 15, color = Theme.MUTED, pos = UDim2.fromOffset(0, 52),
		size = UDim2.new(1, 0, 0, 20), parent = body })

	local scroll = Theme.scroll(body, UDim2.new(1, 0, 1, -80), UDim2.fromOffset(0, 78))
	local refresh

	local tabButtons = {}
	for i, name in ipairs({ "Foods", "Traits", "Mutations", "Combos" }) do
		tabButtons[name] = Theme.button({ label = name, size = UDim2.fromOffset(120, 44), textSize = 17, order = i, parent = tabs,
			color = Theme.PAPER2, onClick = function()
				tab = name
				refresh()
			end })
	end

	local function tile(parent, order, emoji, label, sub, known, color)
		local card = Theme.card(parent, known and Theme.PAPER or Theme.PAPER2, 16)
		card.LayoutOrder = order
		Theme.stroke(card, 2, known and (color or Theme.LINE) or Theme.LINE, known and 0 or 0.4)
		Theme.text({ text = known and emoji or "❔", textSize = 30, align = Enum.TextXAlignment.Center, size = UDim2.new(1, 0, 0, 40),
			pos = UDim2.fromOffset(0, 6), parent = card })
		Theme.text({ text = known and label or "???", font = Theme.BOLD, textSize = 14, align = Enum.TextXAlignment.Center,
			size = UDim2.new(1, -8, 0, 34), pos = UDim2.fromOffset(4, 46), parent = card, scaled = true })
		if sub then
			Theme.text({ text = sub, textSize = 12, color = Theme.MUTED, align = Enum.TextXAlignment.Center,
				size = UDim2.new(1, -8, 0, 34), pos = UDim2.fromOffset(4, 80), parent = card, scaled = true })
		end
		return card
	end

	refresh = function()
		Theme.clear(scroll)
		for name, b in pairs(tabButtons) do
			Theme.setButton(b, nil, name == tab and Theme.accent.book or Theme.PAPER2)
		end
		local profile = ctx.profile
		if not profile then
			return
		end
		local d = profile.discovered
		local grid = Theme.grid(scroll, Vector2.new(tab == "Foods" and 104 or 150, tab == "Foods" and 92 or 120), 8)
		local _ = grid
		Theme.pad(scroll, 4, 6)

		if tab == "Foods" then
			local n = 0
			for i, id in ipairs(Ingredients.order) do
				local def = Ingredients.get(id)
				local known = d.ingredients[id] == true
				if known then
					n += 1
				end
				-- event-only foods stay invisible until found: mystery matters
				local eventOnly = def.biomes[1] == "Event"
				if known or not eventOnly then
					tile(scroll, i, def.emoji, def.display, nil, known, Theme.hex(Ingredients.rarityColor[def.rarity] or 0xCCCCCC))
				end
			end
			counter.Text = string.format("Foods eaten: <b>%d / ???</b>", n)
		elseif tab == "Traits" then
			local n = 0
			for i, id in ipairs(Traits.order) do
				local def = Traits.get(id)
				local known = d.traits[id] == true
				if known then
					n += 1
				end
				tile(scroll, i, def.emoji, def.display, known and def.blurb or nil, known, Theme.hex(def.color))
			end
			counter.Text = string.format("Traits discovered: <b>%d / ???</b>", n)
		elseif tab == "Mutations" then
			local n, hidden = 0, 0
			for i, id in ipairs(Mutations.order) do
				local def = Mutations.get(id)
				local known = d.mutations[id] == true
				if known then
					n += 1
					tile(scroll, i, def.emoji, def.display, def.hint, true, def.secret and Theme.accent.book or Theme.accent.quest)
				elseif def.secret then
					hidden += 1
				else
					-- a hint lets players form a hypothesis (SPEC §90) without spoiling it
					tile(scroll, i, def.emoji, def.display, def.hint, false)
				end
			end
			counter.Text = string.format("Mutations discovered: <b>%d</b>   ·   <b>???</b> hidden", n)
		else
			local n = 0
			for i, id in ipairs(Mutations.order) do
				local def = Mutations.get(id)
				local keys = {}
				for trait in pairs(def.requirements) do
					table.insert(keys, trait)
				end
				if #keys >= 2 and d.mutations[id] then
					n += 1
					table.sort(keys)
					local parts = {}
					for _, k in ipairs(keys) do
						local t = Traits.get(k)
						table.insert(parts, t and t.emoji or k)
					end
					tile(scroll, i, def.emoji, def.display, table.concat(parts, " + "), true, Theme.accent.book)
				end
			end
			if n == 0 then
				Theme.text({ text = "Weird combinations appear here when two different kinds of food make something new.",
					textSize = 16, color = Theme.MUTED, parent = scroll, auto = true }).Size = UDim2.new(1, 0, 0, 60)
			end
			counter.Text = string.format("Weird combinations: <b>%d</b>", n)
		end
	end

	return { refresh = refresh }
end

return BookPanel
