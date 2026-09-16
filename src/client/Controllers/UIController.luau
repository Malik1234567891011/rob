--!strict
-- UIController — SPEC §44–45. Mobile first. "The creature is the UI."
--
-- The HUD carries very little: currencies top-left, a small "today" chip, three big
-- buttons at the bottom (Feed · Bag · Monster), a short column of side buttons, and a quiet
-- quest tracker. Everything else lives in bottom-sheet panels (Controllers/UI/*Panel).
-- SPEC §36: nothing here screams, and the Shop button does not exist until the first
-- evolution.

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local GuiService = game:GetService("GuiService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Quests = require(Shared.Config:WaitForChild("Quests"))
local Progression = require(Shared.Config:WaitForChild("Progression"))

local UI = script.Parent:WaitForChild("UI")
local Theme = require(UI:WaitForChild("Theme"))
local EffectsController = require(script.Parent:WaitForChild("EffectsController"))

local player = Players.LocalPlayer
local UIController = {}

local gui: ScreenGui
local refs: { [string]: any } = {}
local panels: { [string]: any } = {}
local panelOrder = { "Feed", "Monster", "Book", "Quests", "Home", "Trials", "Party", "Shop" }
local openName: string? = nil
local ctx: any = {}

-- ═══ CONTEXT SHARED WITH PANELS ══════════════════════════════════════════════

ctx.Theme = Theme
ctx.Net = Net
ctx.player = player
ctx.profile = nil
ctx.genome = nil
ctx.world = nil :: Folder?
ctx.effects = EffectsController

function ctx.open(name: string)
	UIController.open(name)
end
function ctx.close()
	UIController.closePanels()
end
function ctx.toast(payload)
	UIController.toast(payload)
end
function ctx.creature()
	local ok, CC = pcall(require, script.Parent:WaitForChild("CreatureController"))
	return ok and CC or nil
end

-- ═══ TOASTS ══════════════════════════════════════════════════════════════════

local toastQueue = {}
local toastBusy = false

local function showToast(payload)
	toastBusy = true
	local color = payload.color and Theme.hex(payload.color) or Theme.accent.feed
	local card = Theme.card(refs.toastLayer, Theme.PAPER, 20)
	card.AnchorPoint = Vector2.new(0.5, 0)
	card.Position = UDim2.new(0.5, 0, 0, -120)
	card.Size = UDim2.fromOffset(360, payload.sub and 96 or 74)
	card.ZIndex = 50
	Theme.stroke(card, 3, color)
	local strip = Instance.new("Frame")
	strip.BackgroundColor3 = color
	strip.BorderSizePixel = 0
	strip.Size = UDim2.new(0, 10, 1, -16)
	strip.Position = UDim2.fromOffset(10, 8)
	strip.ZIndex = 51
	strip.Parent = card
	Theme.corner(strip, 5)
	Theme.text({ text = payload.title or "", font = Theme.BOLD, textSize = 13, color = Theme.darker(color, 0.35),
		pos = UDim2.fromOffset(30, 8), size = UDim2.new(1, -40, 0, 16), parent = card }).ZIndex = 51
	Theme.text({ text = payload.label or "", font = Theme.DISPLAY, textSize = 24, pos = UDim2.fromOffset(30, 26),
		size = UDim2.new(1, -40, 0, 30), parent = card, scaled = true }).ZIndex = 51
	if payload.sub then
		Theme.text({ text = payload.sub .. (payload.progress and ("   ·   " .. payload.progress) or ""), textSize = 14,
			color = Theme.MUTED, pos = UDim2.fromOffset(30, 60), size = UDim2.new(1, -40, 0, 30), parent = card }).ZIndex = 51
	end
	TweenService:Create(card, TweenInfo.new(0.42, Enum.EasingStyle.Back), { Position = UDim2.new(0.5, 0, 0, 14) }):Play()
	if payload.kind == "mutation" then
		EffectsController.play(payload.secret and "SecretSting" or "MutationSting")
	elseif payload.kind == "trait" or payload.kind == "quest" then
		EffectsController.play("Sparkle")
	end
	task.delay(payload.kind == "mutation" and 3.4 or 2.4, function()
		TweenService:Create(card, TweenInfo.new(0.3, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Position = UDim2.new(0.5, 0, 0, -130) }):Play()
		task.wait(0.32)
		card:Destroy()
		toastBusy = false
		if #toastQueue > 0 then
			showToast(table.remove(toastQueue, 1))
		end
	end)
end

function UIController.toast(payload)
	if toastBusy then
		table.insert(toastQueue, payload)
		if #toastQueue > 5 then
			table.remove(toastQueue, 1)
		end
	else
		showToast(payload)
	end
end

-- ═══ BANNERS (world notices: events, world firsts, parade) ═══════════════════

function UIController.banner(text: string, color: Color3?, seconds: number?)
	local b = Theme.card(refs.bannerLayer, color or Theme.accent.book, 16)
	b.AnchorPoint = Vector2.new(0.5, 0)
	b.Size = UDim2.fromOffset(460, 50)
	b.Position = UDim2.new(0.5, 0, 0, -60)
	b.ZIndex = 40
	Theme.text({ text = text, font = Theme.DISPLAY, textSize = 22, color = Theme.WHITE, align = Enum.TextXAlignment.Center,
		size = UDim2.new(1, -20, 1, 0), pos = UDim2.fromOffset(10, 0), parent = b, scaled = true, stroke = 0.6 }).ZIndex = 41
	TweenService:Create(b, TweenInfo.new(0.4, Enum.EasingStyle.Back), { Position = UDim2.new(0.5, 0, 0, 118) }):Play()
	task.delay(seconds or 4.5, function()
		TweenService:Create(b, TweenInfo.new(0.3), { Position = UDim2.new(0.5, 0, 0, -70) }):Play()
		task.wait(0.35)
		b:Destroy()
	end)
end

-- ═══ PANELS ══════════════════════════════════════════════════════════════════

local function sheetHeight(p): number
	local cam = workspace.CurrentCamera
	local h = cam and cam.ViewportSize.Y or 800
	return math.floor(math.clamp(h * (p.height or 0.6), 300, 640))
end

function UIController.closePanels()
	if not openName then
		return
	end
	local p = panels[openName]
	openName = nil
	if p.onClose then
		pcall(p.onClose, ctx)
	end
	TweenService:Create(p.sheet, TweenInfo.new(0.22, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Position = UDim2.new(0.5, 0, 1, 40) }):Play()
	task.delay(0.24, function()
		if openName == nil or panels[openName] ~= p then
			p.sheet.Visible = false
		end
	end)
	refs.dim.Visible = false
end

function UIController.open(name: string)
	local p = panels[name]
	if not p then
		return
	end
	if openName == name then
		UIController.closePanels()
		return
	end
	if openName then
		panels[openName].sheet.Visible = false
		if panels[openName].onClose then
			pcall(panels[openName].onClose, ctx)
		end
	end
	openName = name
	p.sheet.Size = UDim2.new(1, -24, 0, sheetHeight(p.module))
	p.sheet.Position = UDim2.new(0.5, 0, 1, 40)
	p.sheet.Visible = true
	refs.dim.Visible = true
	pcall(p.refresh, ctx)
	if p.onOpen then
		pcall(p.onOpen, ctx)
	end
	TweenService:Create(p.sheet, TweenInfo.new(0.32, Enum.EasingStyle.Back), { Position = UDim2.new(0.5, 0, 1, -12) }):Play()
	EffectsController.play("PlasticClack", 0.1)
end

local function buildPanel(name: string)
	local module = require(UI:WaitForChild(name .. "Panel"))
	local sheet = Theme.card(gui, Theme.PAPER, 26)
	sheet.Name = name .. "Sheet"
	sheet.AnchorPoint = Vector2.new(0.5, 1)
	sheet.Position = UDim2.new(0.5, 0, 1, 40)
	sheet.Size = UDim2.new(1, -24, 0, 420)
	sheet.Visible = false
	sheet.ZIndex = 20
	local maxW = Instance.new("UISizeConstraint")
	maxW.MaxSize = Vector2.new(760, 700)
	maxW.Parent = sheet
	Theme.stroke(sheet, 3, Theme.lighter(module.accent or Theme.LINE, 0.3))

	local header = Instance.new("Frame")
	header.Name = "Header"
	header.BackgroundTransparency = 1
	header.Size = UDim2.new(1, 0, 0, 56)
	header.Parent = sheet
	Theme.text({ text = (module.emoji or "") .. "  " .. (module.title or name), font = Theme.DISPLAY, textSize = 26,
		pos = UDim2.fromOffset(20, 10), size = UDim2.new(1, -90, 0, 38), parent = header, name = "Title" })
	Theme.button({ label = "✕", size = UDim2.fromOffset(46, 46), pos = UDim2.new(1, -58, 0, 8), color = Theme.PAPER2,
		parent = header, textSize = 20, onClick = function()
			UIController.closePanels()
		end })

	local body = Instance.new("Frame")
	body.Name = "Body"
	body.BackgroundTransparency = 1
	body.Position = UDim2.fromOffset(16, 58)
	body.Size = UDim2.new(1, -32, 1, -70)
	body.Parent = sheet

	local api = module.build(body, ctx, header)
	panels[name] = {
		module = module, sheet = sheet, body = body, header = header,
		refresh = api.refresh or function() end, onOpen = api.onOpen, onClose = api.onClose, api = api,
	}
end

function UIController.refreshOpen()
	if openName then
		pcall(panels[openName].refresh, ctx)
	end
end

function UIController.panel(name: string)
	return panels[name] and panels[name].api or nil
end

-- ═══ HUD ═════════════════════════════════════════════════════════════════════

local function sideButton(emoji: string, label: string, accent: Color3, order: number, onClick)
	local b = Theme.button({ emoji = emoji, size = UDim2.fromOffset(62, 62), color = Theme.PAPER, textSize = 30,
		order = order, parent = refs.side, onClick = onClick, badge = true, name = label })
	local tag = Theme.text({ text = label, font = Theme.BOLD, textSize = 11, color = Theme.WHITE, stroke = 0.5,
		align = Enum.TextXAlignment.Center, size = UDim2.new(1, 12, 0, 14), pos = UDim2.new(0, -6, 1, -8), parent = b })
	tag.ZIndex = 5
	local _ = accent
	return b
end

local function buildHud()
	-- currencies (SPEC §44 "Top: Coins")
	local pill = Theme.card(gui, Theme.PAPER, 24)
	pill.Name = "Currency"
	pill.Position = UDim2.fromOffset(14, 14)
	pill.Size = UDim2.fromOffset(232, 48)
	Theme.stroke(pill, 2, Theme.LINE)
	refs.coins = Theme.text({ text = "🪙 0", font = Theme.DISPLAY, textSize = 22, pos = UDim2.fromOffset(14, 0),
		size = UDim2.new(0.56, -14, 1, 0), parent = pill, scaled = true })
	refs.essence = Theme.text({ text = "🔮 0", font = Theme.DISPLAY, textSize = 22, pos = UDim2.new(0.56, 4, 0, 0),
		size = UDim2.new(0.44, -14, 1, 0), parent = pill, scaled = true })

	-- today chip (weather / event / parade)
	local chip = Instance.new("TextButton")
	chip.Name = "Today"
	chip.AutoButtonColor = false
	chip.Text = ""
	chip.AnchorPoint = Vector2.new(0.5, 0)
	chip.Position = UDim2.new(0.5, 0, 0, 14)
	chip.Size = UDim2.fromOffset(260, 40)
	chip.BackgroundColor3 = Theme.PAPER
	chip.BackgroundTransparency = 0.08
	chip.Parent = gui
	Theme.corner(chip, 20)
	refs.today = Theme.text({ text = "", font = Theme.BOLD, textSize = 15, align = Enum.TextXAlignment.Center,
		size = UDim2.new(1, -16, 1, 0), pos = UDim2.fromOffset(8, 0), parent = chip, scaled = true })
	chip.MouseButton1Click:Connect(function()
		UIController.open("Quests")
	end)

	-- right column (SPEC §44 "Side")
	local side = Instance.new("Frame")
	side.Name = "Side"
	side.BackgroundTransparency = 1
	side.AnchorPoint = Vector2.new(1, 0.5)
	side.Position = UDim2.new(1, -12, 0.45, 0)
	side.Size = UDim2.fromOffset(62, 460)
	side.Parent = gui
	Theme.list(side, Enum.FillDirection.Vertical, 16, Enum.HorizontalAlignment.Center)
	refs.side = side
	refs.btnQuests = sideButton("📜", "Quests", Theme.accent.quest, 1, function() UIController.open("Quests") end)
	refs.btnBook = sideButton("📖", "Book", Theme.accent.book, 2, function() UIController.open("Book") end)
	refs.btnHome = sideButton("🏡", "Home", Theme.accent.home, 3, function() UIController.open("Home") end)
	refs.btnTrials = sideButton("🏁", "Trials", Theme.accent.trials, 4, function() UIController.open("Trials") end)
	refs.btnParty = sideButton("👥", "Friends", Theme.accent.party, 5, function() UIController.open("Party") end)
	refs.btnShop = sideButton("🛍️", "Shop", Theme.accent.shop, 6, function() UIController.open("Shop") end)
	refs.btnShop.Visible = false

	-- bottom row (SPEC §44 "Bottom: Feed · Bag · Monster")
	local bar = Instance.new("Frame")
	bar.Name = "Bottom"
	bar.BackgroundTransparency = 1
	bar.AnchorPoint = Vector2.new(0.5, 1)
	bar.Position = UDim2.new(0.5, 0, 1, -16)
	bar.Size = UDim2.fromOffset(372, 76)
	bar.Parent = gui
	Theme.list(bar, Enum.FillDirection.Horizontal, 12, Enum.HorizontalAlignment.Center)
	refs.feedBtn = Theme.button({ emoji = "🍎", label = "FEED", size = UDim2.fromOffset(136, 72), color = Theme.accent.feed,
		textSize = 26, parent = bar, order = 1, badge = true, onClick = function() UIController.open("Feed") end })
	refs.bagBtn = Theme.button({ emoji = "🎒", label = "BAG", size = UDim2.fromOffset(104, 72), color = Theme.PAPER,
		textSize = 22, parent = bar, order = 2, onClick = function()
			local p = panels.Feed
			if p and p.api.setMode then
				p.api.setMode("bag")
			end
			UIController.open("Feed")
		end })
	refs.monsterBtn = Theme.button({ emoji = "🐾", label = "", size = UDim2.fromOffset(104, 72), color = Theme.accent.monster,
		textSize = 30, parent = bar, order = 3, badge = true, sub = "MONSTER", onClick = function() UIController.open("Monster") end })

	-- quest tracker (quiet, left)
	local tracker = Instance.new("TextButton")
	tracker.Name = "Tracker"
	tracker.Text = ""
	tracker.AutoButtonColor = false
	tracker.BackgroundColor3 = Theme.PAPER
	tracker.BackgroundTransparency = 0.18
	tracker.Position = UDim2.fromOffset(14, 74)
	tracker.Size = UDim2.fromOffset(232, 0)
	tracker.AutomaticSize = Enum.AutomaticSize.Y
	tracker.Parent = gui
	Theme.corner(tracker, 16)
	Theme.pad(tracker, 10, 8)
	Theme.list(tracker, Enum.FillDirection.Vertical, 4)
	tracker.MouseButton1Click:Connect(function()
		UIController.open("Quests")
	end)
	refs.tracker = tracker

	-- FTUE hint: centred, no box, no OK button (SPEC §8)
	refs.ftueHint = Theme.text({ text = "", font = Theme.DISPLAY, color = Theme.WHITE, textSize = 40, stroke = 0.35,
		align = Enum.TextXAlignment.Center, size = UDim2.new(0.8, 0, 0, 60), pos = UDim2.new(0.1, 0, 0.2, 0), parent = gui, scaled = true })
	refs.ftueHint.Visible = false

	-- dimmer behind open panels (tap to close)
	local dim = Instance.new("TextButton")
	dim.Name = "Dim"
	dim.Text = ""
	dim.AutoButtonColor = false
	dim.BackgroundColor3 = Theme.SHADOW
	dim.BackgroundTransparency = 0.72
	dim.Size = UDim2.fromScale(1, 1)
	dim.ZIndex = 15
	dim.Visible = false
	dim.Parent = gui
	dim.MouseButton1Click:Connect(function()
		UIController.closePanels()
	end)
	refs.dim = dim

	for _, layer in ipairs({ "toastLayer", "bannerLayer", "overlayLayer" }) do
		local f = Instance.new("Frame")
		f.Name = layer
		f.BackgroundTransparency = 1
		f.Size = UDim2.fromScale(1, 1)
		f.ZIndex = 45
		f.Parent = gui
		refs[layer] = f
	end
	ctx.overlayLayer = refs.overlayLayer
	ctx.gui = gui
end

local function refreshTracker()
	local tracker = refs.tracker
	Theme.clear(tracker)
	local profile = ctx.profile
	if not profile or profile.activeCreature == 0 then
		tracker.Visible = false
		return
	end
	tracker.Visible = true
	Theme.text({ text = "QUESTS", font = Theme.BOLD, textSize = 12, color = Theme.MUTED, parent = tracker, order = 0 })
	for i, q in ipairs(profile.quests and profile.quests.active or {}) do
		local def = Quests.get(q.id)
		if def then
			Theme.text({ text = string.format("%s %s  <font color=\"#7E768A\">%d/%d</font>", def.emoji, def.display, q.progress or 0, def.goal),
				textSize = 14, font = Theme.BOLD, parent = tracker, order = i, wrap = false, scaled = true })
		end
	end
end

local function refreshToday()
	local ws = ctx.world
	if not ws then
		return
	end
	local parts = {}
	local weatherEmoji = { Sunny = "☀️", Rain = "🌧️", Windy = "🌬️", Storm = "⛈️", Fog = "🌫️" }
	table.insert(parts, weatherEmoji[ws:GetAttribute("Weather") or "Sunny"] or "☀️")
	local event = ws:GetAttribute("Event")
	local now = workspace:GetServerTimeNow()
	if event then
		local ends = ws:GetAttribute("EventEndsAt") or now
		local pretty = (string.gsub(tostring(event), "(%l)(%u)", "%1 %2"))
		table.insert(parts, string.format("<b>%s</b> %s", pretty, Theme.countdown(ends - now)))
	elseif ws:GetAttribute("ParadePhase") == "signup" then
		table.insert(parts, "<b>🎭 Parade signing up!</b>")
	else
		local meteor = ws:GetAttribute("NextMeteorAt")
		if meteor and meteor - os.time() < 3600 then
			table.insert(parts, string.format("☄️ Meteor in <b>%s</b>", Theme.countdown(meteor - os.time())))
		else
			local trait = ws:GetAttribute("TraitOfDay")
			local Traits = require(Shared.Config.Traits)
			local t = trait and Traits.get(trait)
			if t then
				table.insert(parts, string.format("%s %s day", t.emoji, t.display))
			end
		end
	end
	refs.today.Text = table.concat(parts, "   ")
end

-- ═══ STATE FROM THE SERVER ═══════════════════════════════════════════════════

local shownCoins, shownEssence = 0, 0
local function animateCurrency(profile)
	local targetC, targetE = profile.coins or 0, profile.essence or 0
	local startC, startE = shownCoins, shownEssence
	local t0 = os.clock()
	local conn
	-- Heartbeat, not RenderStepped: state text must update even when frames aren't rendered
	conn = RunService.Heartbeat:Connect(function()
		local t = math.clamp((os.clock() - t0) / 0.6, 0, 1)
		local e = 1 - (1 - t) ^ 3
		shownCoins = math.floor(startC + (targetC - startC) * e)
		shownEssence = math.floor(startE + (targetE - startE) * e)
		refs.coins.Text = "🪙 " .. Theme.fmt(shownCoins)
		refs.essence.Text = "🔮 " .. Theme.fmt(shownEssence)
		if t >= 1 then
			conn:Disconnect()
		end
	end)
end

function UIController.setProfile(profile)
	ctx.profile = profile
	ctx.genome = profile.creatures and profile.creatures[profile.activeCreature] or nil
	animateCurrency(profile)
	refreshTracker()
	-- SPEC §36: no shop surface before the first evolution
	refs.btnShop.Visible = (profile.stats and profile.stats.evolutions or 0) >= 1
	local hasItems = next(profile.inventory or {}) ~= nil
	local feedBadge = refs.feedBtn:FindFirstChild("Badge") :: Frame?
	if feedBadge then
		feedBadge.Visible = hasItems and profile.activeCreature > 0 and (profile.stats.feeds or 0) < 3
	end
	local g = ctx.genome
	local monsterBadge = refs.monsterBtn:FindFirstChild("Badge") :: Frame?
	if monsterBadge then
		monsterBadge.Visible = g ~= nil and Progression.readyToEvolve(g.stage or 1, g.fedCount or 0) and (g.stage or 1) < Progression.maxStage()
	end
	local stage = g and Progression.stage(g.stage or 1)
	if stage then
		(refs.monsterBtn:FindFirstChild("Face"):FindFirstChild("Label") :: TextLabel).Text = stage.emoji
	end
	UIController.refreshOpen()
end

function UIController.setGenome(genome)
	ctx.genome = genome
	UIController.refreshOpen()
end

-- FTUE (SPEC §8): contextual lines only.
function UIController.ftue(stepIndex: number, payload)
	local hint = refs.ftueHint
	if stepIndex >= 9 or not payload or not payload.text then
		hint.Visible = false
		return
	end
	hint.Text = payload.text
	hint.Visible = true
	Theme.pop(hint)
	if payload.prompt == "feed" then
		local badge = refs.feedBtn:FindFirstChild("Badge") :: Frame?
		if badge then
			badge.Visible = true
		end
		-- a gentle bounce on the FEED button so nobody needs an arrow
		task.spawn(function()
			for _ = 1, 6 do
				Theme.pop(refs.feedBtn)
				task.wait(0.7)
			end
		end)
	end
	-- steps that wait on the player (pick an egg, take the apple, press FEED) stay up until
	-- the next step replaces them; the rest are moments and fade on their own
	local waitsOnPlayer = stepIndex == 0 or stepIndex == 2 or stepIndex == 3
	if waitsOnPlayer then
		return
	end
	task.delay(stepIndex == 4 and 6 or 4, function()
		if hint.Text == payload.text then
			hint.Visible = false
		end
	end)
end

-- ═══ BUILD ═══════════════════════════════════════════════════════════════════

function UIController.build()
	gui = Instance.new("ScreenGui")
	gui.Name = "FeedAMonster"
	gui.ResetOnSpawn = false
	-- CoreUISafeInsets keeps the HUD clear of Roblox's own top-bar buttons and phone notches
	gui.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
	gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	gui.Parent = player:WaitForChild("PlayerGui")

	ctx.world = ReplicatedStorage:WaitForChild("WorldState", 10)
	buildHud()
	for _, name in ipairs(panelOrder) do
		local ok, err = pcall(buildPanel, name)
		if not ok then
			warn("[UI] panel " .. name .. " failed to build: " .. tostring(err))
		end
	end
	local Overlays = require(UI:WaitForChild("Overlays"))
	Overlays.init(ctx)
	UIController.overlays = Overlays
	UIController.evolution = Overlays.evolution
	UIController.askName = Overlays.askName
	UIController.offlineReport = Overlays.offlineReport
	UIController.notice = Overlays.notice
	UIController.inspect = Overlays.inspect
	ctx.photoMode = Overlays.photoMode

	task.spawn(function()
		while gui.Parent do
			pcall(refreshToday)
			task.wait(1)
		end
	end)
	local _ = GuiService
end

return UIController
