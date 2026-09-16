--!strict
-- QuestsPanel — SPEC §46 quests, §47 "something different is happening today", §48 meteor,
-- §78 Community Research Board. One place that answers "what should I try next?"

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Quests = require(Shared.Config:WaitForChild("Quests"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))

local QuestsPanel = {}
QuestsPanel.title = "Quests & Today"
QuestsPanel.emoji = "📜"
QuestsPanel.height = 0.72

function QuestsPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 10)
	Theme.pad(scroll, 2, 4)

	local function header(text, order)
		Theme.text({ text = text, font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = order })
	end

	local function refresh()
		Theme.clear(scroll)
		local profile = ctx.profile
		local ws = ctx.world
		if not profile then
			return
		end

		header("YOUR QUESTS", 1)
		for i, q in ipairs(profile.quests and profile.quests.active or {}) do
			local def = Quests.get(q.id)
			if def then
				local card = Theme.card(scroll, Theme.PAPER2, 18)
				card.Size = UDim2.new(1, -8, 0, 84)
				card.LayoutOrder = 1 + i
				Theme.pad(card, 14, 10)
				Theme.text({ text = def.emoji .. "  " .. def.display, font = Theme.DISPLAY, textSize = 20, parent = card, size = UDim2.new(0.7, 0, 0, 26) })
				Theme.text({ text = def.desc, textSize = 14, color = Theme.MUTED, pos = UDim2.fromOffset(0, 26), size = UDim2.new(0.7, 0, 0, 20), parent = card })
				local bar, set = Theme.progress(card, Theme.accent.quest, 12)
				bar.Position = UDim2.fromOffset(0, 52)
				bar.Size = UDim2.new(0.7, 0, 0, 12)
				set((q.progress or 0) / def.goal)
				local reward = {}
				if def.reward.Coins then
					table.insert(reward, "💰 " .. def.reward.Coins)
				end
				if def.reward.Essence then
					table.insert(reward, "🔮 " .. def.reward.Essence)
				end
				Theme.text({ text = string.format("<b>%d / %d</b>\n%s", q.progress or 0, def.goal, table.concat(reward, "  ")), textSize = 15,
					align = Enum.TextXAlignment.Right, pos = UDim2.new(0.72, 0, 0, 0), size = UDim2.new(0.28, 0, 1, 0), parent = card })
			end
		end

		if not ws then
			return
		end
		header("TODAY IN THE WORLD", 20)
		local todayCard = Theme.card(scroll, Theme.lighter(Theme.accent.quest, 0.78), 18)
		todayCard.Size = UDim2.new(1, -8, 0, 0)
		todayCard.AutomaticSize = Enum.AutomaticSize.Y
		todayCard.LayoutOrder = 21
		Theme.pad(todayCard, 14, 12)
		Theme.list(todayCard, Enum.FillDirection.Vertical, 6)
		local ing = Ingredients.get(ws:GetAttribute("IngredientOfDay") or "")
		local trait = Traits.get(ws:GetAttribute("TraitOfDay") or "")
		local weather = ws:GetAttribute("Weather") or "Sunny"
		local weatherLine = {
			Sunny = "☀️ Sunny — a nice day to explore.",
			Rain = "🌧️ Rain — watery and leafy foods are stronger, and more water things appear.",
			Windy = "🌬️ Windy — airy foods are stronger.",
			Storm = "⛈️ Storm — electric foods are MUCH stronger. Electric monsters are going wild.",
			Fog = "🌫️ Fog — mysterious and dark foods are stronger.",
		}
		local lines = {
			ing and string.format("🌟 <b>Ingredient of the day:</b> %s %s — it's everywhere today.", ing.emoji, ing.display) or nil,
			trait and string.format("📈 <b>%s %s</b> foods are 25%% stronger today.", trait.emoji, trait.display) or nil,
			weatherLine[weather],
		}
		local event = ws:GetAttribute("Event")
		if event then
			table.insert(lines, string.format("🎉 <b>Happening now:</b> %s", (string.gsub(event, "(%l)(%u)", "%1 %2"))))
		end
		local meteor = ws:GetAttribute("NextMeteorAt")
		if meteor then
			table.insert(lines, string.format("☄️ <b>Something falls from the sky</b> in %s.", Theme.countdown(meteor - os.time())))
		end
		local paradeAt = ws:GetAttribute("ParadeNextAt")
		local phase = ws:GetAttribute("ParadePhase")
		if phase == "signup" then
			table.insert(lines, "🎭 <b>The Creature Parade is signing up right now!</b>")
		elseif paradeAt then
			table.insert(lines, string.format("🎭 Next Creature Parade in %s.", Theme.countdown(paradeAt - workspace:GetServerTimeNow())))
		end
		for i, l in ipairs(lines) do
			if l then
				Theme.text({ text = l, textSize = 15, parent = todayCard, order = i, auto = true })
			end
		end
		if phase == "signup" then
			Theme.button({ emoji = "🎭", label = "WALK THE RUNWAY", size = UDim2.new(1, 0, 0, 52), color = Theme.accent.parade, textColor = Theme.WHITE,
				parent = todayCard, order = 50, onClick = function()
					local r = ctx.Net.func("ParadeJoin"):InvokeServer()
					ctx.toast({ title = r and r.ok and "YOU'RE IN" or "NOT THIS TIME", label = r and r.ok and "🎭 Get ready for the runway!" or tostring(r and r.reason),
						color = r and r.ok and 0xF46CC4 or 0xEC6060 })
				end })
		end

		-- merchant (SPEC §47 deterministic rotating inventory)
		header("WANDERING MERCHANT", 30)
		local shelf = Instance.new("Frame")
		shelf.BackgroundTransparency = 1
		shelf.Size = UDim2.new(1, -8, 0, 0)
		shelf.AutomaticSize = Enum.AutomaticSize.Y
		shelf.LayoutOrder = 31
		shelf.Parent = scroll
		Theme.grid(shelf, Vector2.new(112, 112), 8)
		local stock = ws:GetAttribute("MerchantStock") or ""
		local i = 0
		for entry in string.gmatch(stock, "[^,]+") do
			local id, price = string.match(entry, "^(%w+):(%d+)$")
			local def = id and Ingredients.get(id)
			if def then
				i += 1
				Theme.button({ emoji = def.emoji, sub = def.display .. " · 💰" .. price, size = UDim2.fromOffset(112, 112), textSize = 36,
					order = i, parent = shelf, onClick = function()
						local r = ctx.Net.func("MerchantBuy"):InvokeServer(id)
						ctx.toast({ title = r and r.ok and "BOUGHT" or "CAN'T BUY", label = r and r.ok and (def.emoji .. " " .. def.display) or tostring(r and r.reason),
							color = r and r.ok and 0xFFD52E or 0xEC6060 })
					end })
			end
		end

		-- research board (SPEC §78)
		local raw = ws:GetAttribute("Board")
		if type(raw) == "string" then
			local ok, board = pcall(HttpService.JSONDecode, HttpService, raw)
			if ok and board then
				header("COMMUNITY RESEARCH BOARD", 40)
				local bc = Theme.card(scroll, Theme.lighter(Theme.accent.book, 0.8), 18)
				bc.Size = UDim2.new(1, -8, 0, 0)
				bc.AutomaticSize = Enum.AutomaticSize.Y
				bc.LayoutOrder = 41
				Theme.pad(bc, 14, 12)
				Theme.list(bc, Enum.FillDirection.Vertical, 5)
				local most = board.mostEatenToday and Ingredients.get(board.mostEatenToday)
				Theme.text({ text = string.format("🍽️ <b>%s</b> items eaten", Theme.fmt(board.itemsEaten or 0)), textSize = 16, parent = bc, order = 1, auto = true })
				if most then
					Theme.text({ text = string.format("🔥 Most eaten today: %s %s", most.emoji, most.display), textSize = 15, parent = bc, order = 2, auto = true })
				end
				Theme.text({ text = string.format("❓ Undiscovered secrets: <b>%d</b>", board.undiscoveredSecrets or 0), textSize = 15, parent = bc, order = 3, auto = true })
				if type(board.unsolved) == "table" then
					local bits = {}
					for _, id in ipairs(board.unsolved) do
						local ing = id ~= "???" and Ingredients.get(id)
						table.insert(bits, ing and (ing.emoji .. " " .. ing.display) or "<b>???</b>")
					end
					Theme.text({ text = "🧪 Unsolved: " .. table.concat(bits, " + "), textSize = 15, parent = bc, order = 3, auto = true })
				end
				if board.largest then
					Theme.text({ text = string.format("🦖 Largest monster: %s — Gen %d (%s)", board.largest.name or "???", board.largest.gen or 1, board.largest.owner or ""),
						textSize = 15, parent = bc, order = 4, auto = true })
				end
				for k, f in ipairs(board.firsts or {}) do
					local def = Mutations.get(f.mutation)
					Theme.text({ text = string.format("🏆 WORLD FIRST — <b>%s</b> discovered %s", f.name, def and (def.emoji .. " " .. def.display) or "???"),
						textSize = 14, parent = bc, order = 10 + k, auto = true })
				end
			end
		end
	end

	return { refresh = refresh }
end

return QuestsPanel
