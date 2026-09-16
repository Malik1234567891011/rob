--!strict
-- FeedPanel — Feed & Bag (SPEC §44 bottom row, §45 contextual information).
--
-- Tap an item: it appears in your hand, your monster's eyes follow it (ART_DIRECTION
-- "eyes TRACK the item"), and a card explains it simply ("⚡ Strong Electric"). The detail
-- toggle shows exact numbers for optimisers (SPEC §45). FEED sends it; PLANT puts it in the
-- garden if you have beds.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

local FeedPanel = {}
FeedPanel.title = "Feed"
FeedPanel.emoji = "🍎"
FeedPanel.height = 0.62

function FeedPanel.build(body: Frame, ctx, header: Frame)
	local Theme = ctx.Theme
	FeedPanel.accent = Theme.accent.feed
	local mode = "feed"
	local selected: string? = nil
	local detail = false
	local held: Model? = nil
	local heldConn: RBXScriptConnection? = nil

	local title = header:FindFirstChild("Title") :: TextLabel

	local detailBtn = Theme.button({ label = "Details", size = UDim2.fromOffset(96, 40), pos = UDim2.new(1, -164, 0, 11),
		color = Theme.PAPER2, textSize = 15, parent = header })

	-- left: grid of items; right: info card
	local grid = Theme.scroll(body, UDim2.new(0.58, -6, 1, 0))
	Theme.grid(grid, Vector2.new(92, 104), 8)
	Theme.pad(grid, 4, 6)

	local info = Theme.card(body, Theme.PAPER2, 20)
	info.Position = UDim2.new(0.58, 6, 0, 0)
	info.Size = UDim2.new(0.42, -6, 1, 0)
	Theme.pad(info, 14, 12)
	Theme.list(info, Enum.FillDirection.Vertical, 6)

	local function dropHeld()
		if heldConn then
			heldConn:Disconnect()
			heldConn = nil
		end
		if held then
			held:Destroy()
			held = nil
		end
		local CC = ctx.creature()
		if CC then
			CC.setHeldFocus(nil)
		end
	end

	-- the item floats in front of the player; the creature watches it
	local function hold(id: string)
		dropHeld()
		local model = PropBuilder.build(id)
		local char = ctx.player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		if not model or not hrp then
			return
		end
		local ext = model:GetExtentsSize()
		model:ScaleTo(math.clamp(1.1 / math.max(ext.X, ext.Y, ext.Z), 0.15, 1.2))
		for _, d in ipairs(model:GetDescendants()) do
			if d:IsA("BasePart") then
				d.Anchored = true
				d.CanCollide = false
				d.CanQuery = false
			end
		end
		model.Parent = workspace
		held = model
		local t0 = os.clock()
		heldConn = RunService.RenderStepped:Connect(function()
			local c = ctx.player.Character
			local root = c and c:FindFirstChild("HumanoidRootPart") :: BasePart?
			if not root or not model.Parent then
				return
			end
			local t = os.clock() - t0
			-- sway left/right so the eye tracking reads
			local cf = root.CFrame * CFrame.new(math.sin(t * 1.6) * 1.2, 1.4 + math.sin(t * 3.1) * 0.15, -2.2)
			model:PivotTo(CFrame.new(cf.Position) * CFrame.Angles(0, t * 1.5, 0))
			local CC = ctx.creature()
			if CC then
				CC.setHeldFocus(cf.Position)
			end
		end)
	end

	local function describe(def): string
		local ranked = {}
		for trait, v in pairs(def.influences) do
			table.insert(ranked, { trait = trait, v = v })
		end
		table.sort(ranked, function(a, b)
			return a.v > b.v
		end)
		local lines = {}
		for i, r in ipairs(ranked) do
			local t = Traits.get(r.trait)
			if t and (detail or i <= 2) then
				if detail then
					table.insert(lines, string.format("%s %s <b>+%d</b>", t.emoji, t.display, r.v))
				else
					local strength = r.v >= 4 and "Strong" or (r.v >= 2 and "Some" or "A little")
					table.insert(lines, string.format("%s <b>%s</b> %s", t.emoji, strength, t.display))
				end
			end
		end
		return table.concat(lines, "\n")
	end

	local refresh

	local function renderInfo()
		Theme.clear(info)
		local profile = ctx.profile
		if not selected or not profile then
			Theme.text({ text = mode == "feed" and "Pick something to feed it." or "Your bag.", font = Theme.DISPLAY,
				textSize = 22, parent = info, order = 1, auto = true })
			Theme.text({ text = mode == "feed"
				and "Everything changes your monster a little. What happens if you feed it <b>that</b>?"
				or "Ingredients you have picked up. Tap one to see what it does.",
				textSize = 15, color = Theme.MUTED, parent = info, order = 2, auto = true })
			return
		end
		local def = Ingredients.get(selected)
		if not def then
			return
		end
		local have = profile.inventory[selected] or 0
		Theme.text({ text = def.emoji .. "  " .. def.display, font = Theme.DISPLAY, textSize = 24, parent = info, order = 1, auto = true })
		local rarity = Theme.chip(info, def.rarity, Theme.hex(Ingredients.rarityColor[def.rarity] or 0xCCCCCC), 2)
		local _ = rarity
		Theme.text({ text = describe(def), textSize = 16, parent = info, order = 3, auto = true })
		Theme.text({ text = "You have " .. have, textSize = 14, color = Theme.MUTED, parent = info, order = 4, auto = true })
		local seen = profile.discovered.ingredients[selected]
		if not seen then
			Theme.text({ text = "✨ Never eaten. Find out.", font = Theme.BOLD, textSize = 14, color = Theme.darker(Theme.accent.book, 0.2), parent = info, order = 5, auto = true })
		end
		local feed = Theme.button({ emoji = "😋", label = "FEED", size = UDim2.new(1, 0, 0, 58), color = Theme.accent.feed, textSize = 24,
			parent = info, order = 10, onClick = function()
				if not ctx.genome then
					ctx.toast({ title = "NO MONSTER YET", label = "🥚 Pick an egg first!", color = 0xFF9EC4 })
					return
				end
				local result = ctx.Net.func("Feed"):InvokeServer(selected)
				if result and result.ok then
					ctx.close()
				elseif result and result.reason == "too fast" then
					-- chewing: ignore
				elseif result then
					ctx.toast({ title = "HMM", label = tostring(result.reason), color = 0xEC6060 })
				end
			end })
		local _f = feed
		if (profile.sanctuary and profile.sanctuary.tier or 1) >= 6 then
			Theme.button({ emoji = "🌱", label = "PLANT", size = UDim2.new(1, 0, 0, 46), color = Theme.accent.quest, textSize = 18,
				parent = info, order = 11, onClick = function()
					local r = ctx.Net.func("GardenPlant"):InvokeServer(selected)
					ctx.toast({ title = r and r.ok and "PLANTED" or "CAN'T PLANT", label = r and r.ok and ("🌱 " .. def.display) or tostring(r and r.reason), color = r and r.ok and 0x5FD98C or 0xEC6060 })
					refresh(ctx)
				end })
		end
	end

	refresh = function(_ctx)
		Theme.clear(grid)
		local profile = ctx.profile
		title.Text = mode == "feed" and "🍎  Feed" or "🎒  Bag"
		if not profile then
			return
		end
		local ids = {}
		for id, n in pairs(profile.inventory) do
			if n > 0 and Ingredients.get(id) then
				table.insert(ids, id)
			end
		end
		local rank = { Common = 1, Uncommon = 2, Rare = 3, Exotic = 4, Secret = 5 }
		table.sort(ids, function(a, b)
			local da, db = Ingredients.get(a), Ingredients.get(b)
			if rank[da.rarity] ~= rank[db.rarity] then
				return rank[da.rarity] > rank[db.rarity]
			end
			return da.display < db.display
		end)
		if selected and not profile.inventory[selected] then
			selected = nil
			dropHeld()
		end
		if #ids == 0 then
			Theme.text({ text = "Nothing yet! Pick things up around the world — almost anything can be eaten.",
				textSize = 16, color = Theme.MUTED, parent = grid, auto = true }).Size = UDim2.new(1, 0, 0, 60)
		end
		for i, id in ipairs(ids) do
			local def = Ingredients.get(id)
			local color = Theme.hex(Ingredients.rarityColor[def.rarity] or 0xCCCCCC)
			local tile = Theme.button({ emoji = def.emoji, size = UDim2.fromOffset(92, 104), order = i, parent = grid,
				color = selected == id and Theme.lighter(Theme.accent.feed, 0.2) or Theme.PAPER, textSize = 34,
				sub = def.display .. "  ×" .. profile.inventory[id],
				onClick = function()
					selected = id
					if mode == "feed" then
						hold(id)
					end
					refresh(ctx)
				end })
			local face = tile:FindFirstChild("Face") :: Frame
			local stripe = Instance.new("Frame")
			stripe.BorderSizePixel = 0
			stripe.BackgroundColor3 = color
			stripe.Size = UDim2.new(1, -20, 0, 4)
			stripe.Position = UDim2.new(0, 10, 1, -8)
			stripe.Parent = face
			Theme.corner(stripe, 2)
			if not profile.discovered.ingredients[id] then
				Theme.text({ text = "✨", textSize = 16, size = UDim2.fromOffset(20, 20), pos = UDim2.fromOffset(6, 4), parent = face })
			end
		end
		renderInfo()
	end

	detailBtn.MouseButton1Click:Connect(function()
		detail = not detail
		Theme.setButton(detailBtn, detail and "Simple" or "Details")
		ctx.Net.func("SetDetailMode"):InvokeServer(detail)
		renderInfo()
	end)

	return {
		refresh = refresh,
		onClose = function()
			dropHeld()
			mode = "feed"
		end,
		setMode = function(m: string)
			mode = m
		end,
	}
end

return FeedPanel
