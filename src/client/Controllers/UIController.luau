--!strict
-- UIController — SPEC §44. Mobile first. "The creature is the UI."
--
-- Main screen carries almost nothing: currencies top-left, three buttons bottom,
-- one book button on the side. No spin wheels, no gifts, no battle pass, no codes,
-- no daily reward popup. SPEC §36: nothing here screams, and there is no shop.

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local EffectsController = require(script.Parent:WaitForChild("EffectsController"))

local player = Players.LocalPlayer
local UIController = {}

local INK   = Color3.fromRGB(28, 26, 34)
local PAPER = Color3.fromRGB(252, 250, 246)
local MUTED = Color3.fromRGB(120, 118, 130)

local profile: any = nil
local genome: any = nil
local gui: ScreenGui
local refs: { [string]: any } = {}
local openPanel: string? = nil

-- ═══ SMALL BUILDERS ══════════════════════════════════════════════════════════

local function corner(parent: Instance, radius: number)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius)
	c.Parent = parent
	return c
end

local function stroke(parent: Instance, thickness: number, color: Color3, transparency: number?)
	local s = Instance.new("UIStroke")
	s.Thickness = thickness
	s.Color = color
	s.Transparency = transparency or 0
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Parent = parent
	return s
end

local function text(props): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Font = props.font or Enum.Font.GothamMedium
	t.TextColor3 = props.color or INK
	t.TextScaled = props.scaled ~= false
	t.Text = props.text or ""
	t.Size = props.size or UDim2.fromScale(1, 1)
	t.Position = props.position or UDim2.fromScale(0, 0)
	t.TextXAlignment = props.align or Enum.TextXAlignment.Center
	t.Name = props.name or "Label"
	if props.parent then
		t.Parent = props.parent
	end
	return t
end

local function button(props): TextButton
	local b = Instance.new("TextButton")
	b.Size = props.size
	b.Position = props.position or UDim2.new()
	b.AnchorPoint = props.anchor or Vector2.new(0, 0)
	b.BackgroundColor3 = props.bg or PAPER
	b.AutoButtonColor = false
	b.Text = ""
	b.Name = props.name or "Button"
	corner(b, props.radius or 16)
	if props.stroke then
		stroke(b, 2, props.stroke)
	end

	local label = text({
		text = props.label, font = Enum.Font.FredokaOne,
		color = props.fg or INK, parent = b,
		size = UDim2.fromScale(1, 0.62), position = UDim2.fromScale(0, 0.19),
	})
	label.Name = "Label"

	-- chunky tap feedback; every target is finger-sized (SPEC §44 mobile first)
	b.MouseButton1Down:Connect(function()
		TweenService:Create(b, TweenInfo.new(0.08), { Size = props.size - UDim2.fromOffset(0, 4) }):Play()
	end)
	local function release()
		TweenService:Create(b, TweenInfo.new(0.12), { Size = props.size }):Play()
	end
	b.MouseButton1Up:Connect(release)
	b.MouseLeave:Connect(release)
	if props.parent then
		b.Parent = props.parent
	end
	return b
end

local function panelFrame(name: string, heightScale: number): Frame
	local f = Instance.new("Frame")
	f.Name = name
	f.AnchorPoint = Vector2.new(0.5, 1)
	f.Position = UDim2.new(0.5, 0, 1.4, 0) -- offscreen until opened
	f.Size = UDim2.new(0.92, 0, heightScale, 0)
	f.BackgroundColor3 = PAPER
	f.Visible = false
	f.Parent = gui
	corner(f, 22)
	stroke(f, 2, Color3.fromRGB(226, 222, 214))

	local pad = Instance.new("UIPadding")
	pad.PaddingTop = UDim.new(0, 14)
	pad.PaddingBottom = UDim.new(0, 14)
	pad.PaddingLeft = UDim.new(0, 14)
	pad.PaddingRight = UDim.new(0, 14)
	pad.Parent = f

	local close = button({
		label = "✕", size = UDim2.fromOffset(40, 40),
		position = UDim2.new(1, 0, 0, 0), anchor = Vector2.new(1, 0),
		bg = Color3.fromRGB(240, 236, 230), parent = f, radius = 12,
	})
	close.ZIndex = 5
	close.MouseButton1Click:Connect(function()
		UIController.closePanels()
	end)
	return f
end

-- ═══ TOASTS (SPEC §8 "NEW TRAIT DISCOVERED") ═════════════════════════════════

local toastQueue = {}
local toasting = false

local function showToast(payload)
	local card = Instance.new("Frame")
	card.AnchorPoint = Vector2.new(0.5, 0)
	card.Position = UDim2.new(0.5, 0, 0, -120)
	card.Size = UDim2.new(0.62, 0, 0, payload.sub and 96 or 72)
	card.BackgroundColor3 = PAPER
	card.Parent = gui
	corner(card, 18)
	stroke(card, 3, TableUtil.unpackColor(payload.color or 0xFFD52E))

	text({
		text = payload.title, font = Enum.Font.FredokaOne,
		color = TableUtil.unpackColor(payload.color or 0xFFD52E),
		size = UDim2.new(1, -16, 0, 22), position = UDim2.fromOffset(8, 8), parent = card,
	})
	text({
		text = payload.label, font = Enum.Font.GothamBold, color = INK,
		size = UDim2.new(1, -16, 0, 28), position = UDim2.fromOffset(8, 32), parent = card,
	})
	if payload.sub then
		text({
			text = payload.sub, font = Enum.Font.Gotham, color = MUTED,
			size = UDim2.new(1, -16, 0, 22), position = UDim2.fromOffset(8, 62), parent = card,
		})
	end
	if payload.progress then
		text({
			text = payload.progress, font = Enum.Font.GothamBold, color = MUTED,
			size = UDim2.fromOffset(70, 20), position = UDim2.new(1, -78, 0, 8), parent = card,
		})
	end

	if payload.kind == "mutation" then
		EffectsController.play(payload.secret and "SecretSting" or "MutationSting")
		local char = player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart")
		if hrp then
			EffectsController.ringAt((hrp :: BasePart).Position,
				TableUtil.unpackColor(payload.color or 0xFFD52E))
		end
	else
		EffectsController.play("Sparkle")
	end

	TweenService:Create(card, TweenInfo.new(0.35, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
		{ Position = UDim2.new(0.5, 0, 0, 16) }):Play()
	task.wait(payload.kind == "mutation" and 3.2 or 2.0)
	TweenService:Create(card, TweenInfo.new(0.25), { Position = UDim2.new(0.5, 0, 0, -140) }):Play()
	task.wait(0.3)
	card:Destroy()
end

local function pumpToasts()
	if toasting then
		return
	end
	toasting = true
	task.spawn(function()
		while #toastQueue > 0 do
			local next = table.remove(toastQueue, 1)
			showToast(next)
		end
		toasting = false
	end)
end

function UIController.toast(payload)
	table.insert(toastQueue, payload)
	pumpToasts()
end

-- ═══ PANELS ══════════════════════════════════════════════════════════════════

local function clearList(scroll: ScrollingFrame)
	for _, c in ipairs(scroll:GetChildren()) do
		if c:IsA("GuiObject") then
			c:Destroy()
		end
	end
end

local function makeScroll(parent: Instance): ScrollingFrame
	local s = Instance.new("ScrollingFrame")
	s.Size = UDim2.new(1, 0, 1, -44)
	s.Position = UDim2.fromOffset(0, 40)
	s.BackgroundTransparency = 1
	s.BorderSizePixel = 0
	s.ScrollBarThickness = 5
	s.CanvasSize = UDim2.new()
	s.AutomaticCanvasSize = Enum.AutomaticSize.Y
	s.Parent = parent

	local layout = Instance.new("UIGridLayout")
	layout.CellSize = UDim2.fromOffset(104, 104)
	layout.CellPadding = UDim2.fromOffset(8, 8)
	layout.SortOrder = Enum.SortOrder.LayoutOrder
	layout.Parent = s
	return s
end

local function tile(parent, emoji, label, sub, color, onClick)
	local b = Instance.new("TextButton")
	b.Size = UDim2.fromOffset(104, 104)
	b.BackgroundColor3 = Color3.fromRGB(246, 243, 238)
	b.AutoButtonColor = false
	b.Text = ""
	b.Parent = parent
	corner(b, 14)
	stroke(b, 2, color or Color3.fromRGB(226, 222, 214))

	text({ text = emoji, size = UDim2.new(1, 0, 0, 40), position = UDim2.fromOffset(0, 8), parent = b })
	text({
		text = label, font = Enum.Font.GothamBold, color = INK,
		size = UDim2.new(1, -8, 0, 20), position = UDim2.fromOffset(4, 50), parent = b,
	})
	if sub then
		text({
			text = sub, font = Enum.Font.Gotham, color = MUTED,
			size = UDim2.new(1, -8, 0, 18), position = UDim2.fromOffset(4, 72), parent = b,
		})
	end
	if onClick then
		b.MouseButton1Click:Connect(onClick)
	end
	return b
end

-- FEED: tap an item, it gets eaten. This is the shortest path in the whole UI.
local function refreshFeed()
	local scroll = refs.feedScroll
	clearList(scroll)
	local any = false
	for _, id in ipairs(Ingredients.order) do
		local n = (profile and profile.inventory[id]) or 0
		if n > 0 then
			any = true
			local def = Ingredients.get(id)
			tile(scroll, def.emoji, def.display, "x" .. n,
				TableUtil.unpackColor(Ingredients.rarityColor[def.rarity]), function()
					local result = Net.func("Feed"):InvokeServer(id)
					if result and result.ok then
						UIController.closePanels()
					end
				end)
		end
	end
	if not any then
		text({
			text = "Your bag is empty.\nGo find something.",
			font = Enum.Font.Gotham, color = MUTED, scaled = false,
			size = UDim2.new(1, 0, 0, 60), parent = scroll,
		}).TextSize = 18
	end
end

-- MONSTER: what it is, what it can do, and the evolve / nest actions.
local function refreshMonster()
	local scroll = refs.monsterScroll
	clearList(scroll)
	if not genome then
		text({ text = "No creature yet.", font = Enum.Font.Gotham, color = MUTED,
			size = UDim2.new(1, 0, 0, 40), parent = scroll })
		return
	end

	local stage = Progression.stage(genome.stage or 1)
	local eff = CreatureBuilder.effectiveTraits(genome)
	for _, entry in ipairs(TableUtil.topN(eff, 6)) do
		local t = Traits.get(entry.key)
		if t and entry.value >= Traits.VISIBLE_AT then
			tile(scroll, t.emoji, t.display, tostring(math.floor(entry.value)),
				TableUtil.unpackColor(t.color), nil)
		end
	end
	for id in pairs(genome.mutations or {}) do
		local def = Mutations.get(id)
		if def then
			tile(scroll, def.emoji, def.display, def.ability or "",
				TableUtil.unpackColor(0xA77BFF), nil)
		end
	end

	refs.monsterHeader.Text = string.format("%s %s  ·  Gen %d  ·  %d fed",
		stage.emoji, genome.name or "Unnamed", genome.generation or 1, genome.fedCount or 0)

	local ready = Progression.readyToEvolve(genome.stage or 1, genome.fedCount or 0)
	local mythic = (genome.stage or 1) >= Progression.maxStage()
	refs.evolveBtn.Visible = ready and not mythic
	refs.nestBtn.Visible = mythic
end

-- BOOK: SPEC §25. Counts, never totals.
local function refreshBook()
	local scroll = refs.bookScroll
	clearList(scroll)
	if not profile then
		return
	end

	local function section(items, kindLabel, getDef, discovered)
		local found = 0
		for _, id in ipairs(items) do
			local def = getDef(id)
			if def then
				local known = discovered[id]
				tile(scroll,
					known and def.emoji or "❔",
					known and def.display or "???",
					nil,
					known and TableUtil.unpackColor(def.color or 0xC8D0D8) or Color3.fromRGB(226, 222, 214),
					nil)
				if known then
					found += 1
				end
			end
		end
		return found
	end

	local ing = section(Ingredients.order, "food", Ingredients.get, profile.discovered.ingredients)
	local tr = 0
	for _ in pairs(profile.discovered.traits) do
		tr += 1
	end
	local mu = 0
	for _ in pairs(profile.discovered.mutations) do
		mu += 1
	end

	-- SPEC §8: we never tell them the denominator.
	refs.bookHeader.Text = string.format(
		"🍎 %d / ???     🌿 %d / ???     🤯 %d / ???", ing, tr, mu)
end

function UIController.closePanels()
	for _, name in ipairs({ "feedPanel", "bagPanel", "monsterPanel", "bookPanel" }) do
		local p = refs[name]
		if p and p.Visible then
			TweenService:Create(p, TweenInfo.new(0.18), { Position = UDim2.new(0.5, 0, 1.4, 0) }):Play()
			task.delay(0.2, function()
				p.Visible = false
			end)
		end
	end
	openPanel = nil
end

local function openPanelNamed(name: string)
	if openPanel == name then
		UIController.closePanels()
		return
	end
	UIController.closePanels()
	task.wait(0.05)
	local p = refs[name]
	if not p then
		return
	end
	if name == "feedPanel" then
		refreshFeed()
	elseif name == "bagPanel" then
		refreshFeed() -- same inventory, feed panel doubles as bag
	elseif name == "monsterPanel" then
		refreshMonster()
	elseif name == "bookPanel" then
		refreshBook()
	end
	p.Visible = true
	p.Position = UDim2.new(0.5, 0, 1.4, 0)
	TweenService:Create(p, TweenInfo.new(0.26, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
		{ Position = UDim2.new(0.5, 0, 0.98, 0) }):Play()
	openPanel = name
	EffectsController.play("click")
end

-- ═══ BIG MOMENTS ═════════════════════════════════════════════════════════════

-- SPEC §9: the first evolution receives an exaggerated cinematic.
function UIController.evolution(payload)
	EffectsController.play("Evolution")
	local overlay = Instance.new("Frame")
	overlay.Size = UDim2.fromScale(1, 1)
	overlay.BackgroundColor3 = Color3.fromRGB(12, 10, 18)
	overlay.BackgroundTransparency = 1
	overlay.ZIndex = 20
	overlay.Parent = gui
	TweenService:Create(overlay, TweenInfo.new(0.3), { BackgroundTransparency = 0.35 }):Play()

	local big = text({
		text = payload.emoji .. "  IT EVOLVED!", font = Enum.Font.FredokaOne,
		color = Color3.fromRGB(255, 255, 255), parent = overlay,
		size = UDim2.new(0.9, 0, 0, 72), position = UDim2.new(0.05, 0, 0.32, 0),
	})
	big.ZIndex = 21
	local sub = text({
		text = payload.name .. " — " .. payload.blurb, font = Enum.Font.GothamBold,
		color = Color3.fromRGB(226, 232, 240), parent = overlay,
		size = UDim2.new(0.9, 0, 0, 30), position = UDim2.new(0.05, 0, 0.45, 0),
	})
	sub.ZIndex = 21

	-- SPEC §9: "📸 SHOW WHAT YOU MADE" — architected around shareable moments
	local share = button({
		label = "📸  SHOW WHAT YOU MADE",
		size = UDim2.fromOffset(300, 56),
		position = UDim2.new(0.5, 0, 0.58, 0), anchor = Vector2.new(0.5, 0),
		bg = Color3.fromRGB(255, 213, 46), parent = overlay,
	})
	share.ZIndex = 21
	local shareLabel = share:FindFirstChild("Label")
	if shareLabel then shareLabel.ZIndex = 22 end
	share.MouseButton1Click:Connect(function()
		UIController.toast({
			kind = "moment", title = "MOMENT CAPTURED",
			label = "Use Roblox's record button to share it",
			color = 0xFFD52E,
		})
	end)

	task.delay(4.5, function()
		TweenService:Create(overlay, TweenInfo.new(0.3), { BackgroundTransparency = 1 }):Play()
		task.wait(0.35)
		overlay:Destroy()
		-- SPEC §19: name it after the first evolution, not before
		if payload.needsName then
			UIController.askName()
		end
	end)
end

function UIController.askName()
	local box = Instance.new("Frame")
	box.AnchorPoint = Vector2.new(0.5, 0.5)
	box.Position = UDim2.fromScale(0.5, 0.45)
	box.Size = UDim2.fromOffset(330, 190)
	box.BackgroundColor3 = PAPER
	box.ZIndex = 30
	box.Parent = gui
	corner(box, 20)
	stroke(box, 3, Color3.fromRGB(255, 213, 46))

	local q = text({
		text = "What is its name?", font = Enum.Font.FredokaOne, color = INK,
		size = UDim2.new(1, -20, 0, 36), position = UDim2.fromOffset(10, 16), parent = box,
	})
	q.ZIndex = 31

	local input = Instance.new("TextBox")
	input.Size = UDim2.new(1, -40, 0, 48)
	input.Position = UDim2.fromOffset(20, 62)
	input.BackgroundColor3 = Color3.fromRGB(244, 241, 236)
	input.Font = Enum.Font.GothamBold
	input.TextSize = 22
	input.TextColor3 = INK
	input.PlaceholderText = "Mochi"
	input.Text = ""
	input.ClearTextOnFocus = false
	input.ZIndex = 31
	input.Parent = box
	corner(input, 12)

	local confirm = button({
		label = "THAT'S THE ONE", size = UDim2.fromOffset(290, 48),
		position = UDim2.fromOffset(20, 124), bg = Color3.fromRGB(255, 213, 46), parent = box,
	})
	confirm.ZIndex = 31
	local confirmLabel = confirm:FindFirstChild("Label")
	if confirmLabel then confirmLabel.ZIndex = 32 end
	confirm.MouseButton1Click:Connect(function()
		local wanted = input.Text ~= "" and input.Text or "Mochi"
		local result = Net.func("NameCreature"):InvokeServer(wanted)
		box:Destroy()
		if result and result.ok then
			UIController.toast({ kind = "name", title = "NAMED", label = result.name, color = 0xFFD52E })
		end
	end)
end

-- SPEC §17: what they come back to is curiosity, not a number.
function UIController.offlineReport(report)
	local box = Instance.new("Frame")
	box.AnchorPoint = Vector2.new(0.5, 0.5)
	box.Position = UDim2.fromScale(0.5, 0.42)
	box.Size = UDim2.fromOffset(360, 240)
	box.BackgroundColor3 = PAPER
	box.ZIndex = 25
	box.Parent = gui
	corner(box, 20)
	stroke(box, 3, Color3.fromRGB(167, 123, 255))

	text({
		text = "WHILE YOU WERE GONE…", font = Enum.Font.FredokaOne,
		color = Color3.fromRGB(167, 123, 255),
		size = UDim2.new(1, -24, 0, 26), position = UDim2.fromOffset(12, 14), parent = box,
	}).ZIndex = 26
	local head = text({
		text = report.headline, font = Enum.Font.GothamBold, color = INK, scaled = false,
		size = UDim2.new(1, -24, 0, 56), position = UDim2.fromOffset(12, 44), parent = box,
	})
	head.TextSize = 17
	head.TextWrapped = true
	head.ZIndex = 26

	local found = text({
		text = table.concat(report.gathered, "   "), font = Enum.Font.Gotham,
		color = MUTED, scaled = false,
		size = UDim2.new(1, -24, 0, 54), position = UDim2.fromOffset(12, 106), parent = box,
	})
	found.TextSize = 15
	found.TextWrapped = true
	found.ZIndex = 26

	local ok = button({
		label = "GO LOOK", size = UDim2.fromOffset(320, 48),
		position = UDim2.fromOffset(20, 174), bg = Color3.fromRGB(167, 123, 255),
		fg = Color3.fromRGB(255, 255, 255), parent = box,
	})
	ok.ZIndex = 26
	local okLabel = ok:FindFirstChild("Label")
	if okLabel then okLabel.ZIndex = 27 end
	ok.MouseButton1Click:Connect(function()
		box:Destroy()
	end)
end

-- SPEC §8: contextual, wordless-where-possible guidance. No tutorial wall.
function UIController.ftue(stepIndex: number, payload)
	local hint = refs.ftueHint
	if not payload.text or stepIndex >= 9 then
		hint.Visible = false
		return
	end
	hint.Visible = true
	hint.Text = payload.text
	hint.TextTransparency = 1
	TweenService:Create(hint, TweenInfo.new(0.3), { TextTransparency = 0 }):Play()

	if stepIndex == 3 then
		-- "FEED 🍎" — make the button impossible to miss
		local btn = refs.feedBtn
		TweenService:Create(btn, TweenInfo.new(0.4, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
			{ BackgroundColor3 = Color3.fromRGB(255, 213, 46) }):Play()
	end
end

-- ═══ BUILD ═══════════════════════════════════════════════════════════════════

function UIController.build()
	gui = Instance.new("ScreenGui")
	gui.Name = "FeedAMonster"
	gui.ResetOnSpawn = false
	gui.IgnoreGuiInset = false
	gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	gui.Parent = player:WaitForChild("PlayerGui")

	-- top-left currency pill (SPEC §44: "Top: Coins")
	local pill = Instance.new("Frame")
	pill.Size = UDim2.fromOffset(196, 44)
	pill.Position = UDim2.fromOffset(12, 12)
	pill.BackgroundColor3 = PAPER
	pill.BackgroundTransparency = 0.08
	pill.Parent = gui
	corner(pill, 22)
	refs.currency = text({
		text = "🪙 0    🔮 0", font = Enum.Font.GothamBold, color = INK,
		size = UDim2.fromScale(1, 1), parent = pill,
	})

	-- bottom row: Feed / Bag / Monster
	local bar = Instance.new("Frame")
	bar.AnchorPoint = Vector2.new(0.5, 1)
	bar.Position = UDim2.new(0.5, 0, 1, -14)
	bar.Size = UDim2.fromOffset(330, 60)
	bar.BackgroundTransparency = 1
	bar.Parent = gui

	local row = Instance.new("UIListLayout")
	row.FillDirection = Enum.FillDirection.Horizontal
	row.Padding = UDim.new(0, 8)
	row.HorizontalAlignment = Enum.HorizontalAlignment.Center
	row.Parent = bar

	refs.feedBtn = button({
		label = "FEED", size = UDim2.fromOffset(104, 60),
		bg = Color3.fromRGB(255, 228, 120), parent = bar,
	})
	refs.bagBtn = button({
		label = "BAG", size = UDim2.fromOffset(104, 60), bg = PAPER, parent = bar,
	})
	refs.monsterBtn = button({
		label = "MONSTER", size = UDim2.fromOffset(104, 60), bg = PAPER, parent = bar,
	})

	-- side: the Discovery Book (SPEC §25)
	refs.bookBtn = button({
		label = "📖", size = UDim2.fromOffset(56, 56),
		position = UDim2.new(1, -14, 0.5, 0), anchor = Vector2.new(1, 0.5),
		bg = PAPER, parent = gui,
	})

	-- contextual FTUE line, centred, no box, no OK button
	refs.ftueHint = text({
		text = "", font = Enum.Font.FredokaOne, color = Color3.fromRGB(255, 255, 255),
		size = UDim2.new(0.8, 0, 0, 44), position = UDim2.new(0.1, 0, 0.17, 0), parent = gui,
	})
	refs.ftueHint.TextStrokeTransparency = 0.3
	refs.ftueHint.Visible = false

	-- panels
	refs.feedPanel = panelFrame("FeedPanel", 0.46)
	text({ text = "FEED IT SOMETHING", font = Enum.Font.FredokaOne, color = INK,
		size = UDim2.new(1, -50, 0, 28), position = UDim2.fromOffset(0, 0),
		align = Enum.TextXAlignment.Left, parent = refs.feedPanel })
	refs.feedScroll = makeScroll(refs.feedPanel)

	refs.bagPanel = refs.feedPanel -- same surface; SPEC §44 says keep it small

	refs.monsterPanel = panelFrame("MonsterPanel", 0.52)
	refs.monsterHeader = text({
		text = "", font = Enum.Font.GothamBold, color = INK,
		size = UDim2.new(1, -50, 0, 28), position = UDim2.fromOffset(0, 0),
		align = Enum.TextXAlignment.Left, parent = refs.monsterPanel,
	})
	refs.monsterScroll = makeScroll(refs.monsterPanel)
	refs.evolveBtn = button({
		label = "IT'S READY TO EVOLVE", size = UDim2.new(1, 0, 0, 52),
		position = UDim2.new(0, 0, 1, -52), bg = Color3.fromRGB(255, 213, 46),
		parent = refs.monsterPanel,
	})
	refs.evolveBtn.Visible = false
	refs.evolveBtn.MouseButton1Click:Connect(function()
		local result = Net.func("Evolve"):InvokeServer()
		if result and result.ok then
			UIController.closePanels()
		end
	end)
	refs.nestBtn = button({
		label = "🥚 THE NEST — RAISE THE NEXT ONE", size = UDim2.new(1, 0, 0, 52),
		position = UDim2.new(0, 0, 1, -52), bg = Color3.fromRGB(167, 123, 255),
		fg = Color3.fromRGB(255, 255, 255), parent = refs.monsterPanel,
	})
	refs.nestBtn.Visible = false
	refs.nestBtn.MouseButton1Click:Connect(function()
		Net.func("CreateLineage"):InvokeServer()
		UIController.closePanels()
	end)

	refs.bookPanel = panelFrame("BookPanel", 0.62)
	refs.bookHeader = text({
		text = "", font = Enum.Font.GothamBold, color = INK,
		size = UDim2.new(1, -50, 0, 28), position = UDim2.fromOffset(0, 0),
		align = Enum.TextXAlignment.Left, parent = refs.bookPanel,
	})
	refs.bookScroll = makeScroll(refs.bookPanel)

	refs.feedBtn.MouseButton1Click:Connect(function() openPanelNamed("feedPanel") end)
	refs.bagBtn.MouseButton1Click:Connect(function() openPanelNamed("feedPanel") end)
	refs.monsterBtn.MouseButton1Click:Connect(function() openPanelNamed("monsterPanel") end)
	refs.bookBtn.MouseButton1Click:Connect(function() openPanelNamed("bookPanel") end)
end

function UIController.setProfile(p)
	profile = p
	if refs.currency then
		refs.currency.Text = string.format("🪙 %d    🔮 %d", p.coins or 0, p.essence or 0)
	end
	genome = p.creatures and p.creatures[p.activeCreature] or nil
	if openPanel == "feedPanel" then
		refreshFeed()
	elseif openPanel == "monsterPanel" then
		refreshMonster()
	elseif openPanel == "bookPanel" then
		refreshBook()
	end
end

function UIController.setGenome(g)
	genome = g
end

return UIController
