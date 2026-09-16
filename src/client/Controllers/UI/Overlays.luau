--!strict
-- Overlays — the big moments and the social layer on top of the HUD.
--   * Evolution cinematic (SPEC §9): camera orbits, flash, IT EVOLVED!, 📸 SHOW WHAT YOU MADE
--   * Naming (SPEC §19), offline report (SPEC §17)
--   * Parade reaction bar (SPEC §23), inspection card (SPEC §24)
--   * World notices: events, world firsts, weather, meteor, lightning, shakes (SPEC §48, §54, §77)
--   * Moments + capture/share (SPEC §39)

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))

local Overlays = {}
local ctx: any
local Theme: any
local player = Players.LocalPlayer

-- ═══ CAPTURE / SHARE (SPEC §39) ══════════════════════════════════════════════

local function shareMoment(kind: string)
	local ok, CaptureService = pcall(game.GetService, game, "CaptureService")
	if not ok or not CaptureService then
		return
	end
	pcall(function()
		(CaptureService :: any):CaptureScreenshot(function(contentId)
			Net.event("Moment"):FireServer({ kind = kind, step = "capture" })
			pcall(function()
				(CaptureService :: any):PromptShareCapture(contentId, "", function()
					Net.event("Moment"):FireServer({ kind = kind, step = "share" })
				end, function() end)
			end)
		end)
	end)
end

function Overlays.shareButton(label: string, kind: string, parent: Instance, pos: UDim2)
	return Theme.button({ emoji = "📸", label = label, size = UDim2.fromOffset(300, 64), pos = pos, anchor = Vector2.new(0.5, 0),
		color = Theme.accent.shop, textSize = 22, parent = parent, onClick = function()
			shareMoment(kind)
		end })
end

-- ═══ CAMERA ORBIT ════════════════════════════════════════════════════════════

local function orbit(model: Model?, seconds: number)
	local cam = workspace.CurrentCamera
	if not cam or not model or not model.PrimaryPart then
		return
	end
	local prevType = cam.CameraType
	cam.CameraType = Enum.CameraType.Scriptable
	local t0 = os.clock()
	local height = model:GetAttribute("Height") or 3
	local conn
	conn = RunService.RenderStepped:Connect(function()
		local t = os.clock() - t0
		if t > seconds or not model.Parent or not model.PrimaryPart then
			conn:Disconnect()
			cam.CameraType = prevType
			return
		end
		local center = model.PrimaryPart.Position + Vector3.new(0, height * 0.6 + math.min(t, 1.4) * 1.2, 0)
		local a = math.rad(200) + t * 0.9
		local dist = height * 2.4 + 6
		local eye = center + Vector3.new(math.sin(a) * dist, height * 0.35 + 1.5, math.cos(a) * dist)
		cam.CFrame = CFrame.lookAt(eye, center)
	end)
end

local function flash(color: Color3?)
	local f = Instance.new("Frame")
	f.BackgroundColor3 = color or Color3.new(1, 1, 1)
	f.BackgroundTransparency = 0
	f.Size = UDim2.fromScale(1, 1)
	f.ZIndex = 90
	f.Parent = ctx.overlayLayer
	TweenService:Create(f, TweenInfo.new(0.7), { BackgroundTransparency = 1 }):Play()
	task.delay(0.75, function()
		f:Destroy()
	end)
end

-- ═══ EVOLUTION (SPEC §9) ═════════════════════════════════════════════════════

function Overlays.evolution(payload)
	local CC = ctx.creature()
	local model = CC and CC.myCreature()
	ctx.close()
	ctx.effects.play("Evolution")
	orbit(model, 3.6)
	task.delay(2.5, function()
		flash()
		ctx.effects.play("MutationSting")
	end)
	task.delay(2.7, function()
		local card = Instance.new("Frame")
		card.BackgroundTransparency = 1
		card.Size = UDim2.fromScale(1, 1)
		card.ZIndex = 80
		card.Parent = ctx.overlayLayer
		local title = Theme.text({ text = "IT EVOLVED!", font = Theme.DISPLAY, textSize = 88, color = Theme.WHITE, stroke = 0.2,
			align = Enum.TextXAlignment.Center, size = UDim2.new(1, 0, 0, 110), pos = UDim2.new(0, 0, 0.16, 0), parent = card, scaled = true })
		title.ZIndex = 81
		Theme.pop(title)
		local gainedNames = {}
		for _, id in ipairs(payload.gained or {}) do
			local def = Mutations.get(id)
			if def then
				table.insert(gainedNames, def.emoji .. " " .. def.display)
			end
		end
		local sub = Theme.text({ text = string.format("%s  %s", payload.emoji or "", payload.name or "") .. (#gainedNames > 0 and ("\n" .. table.concat(gainedNames, "  ·  ")) or ""),
			font = Theme.DISPLAY, textSize = 34, color = Theme.WHITE, stroke = 0.3, align = Enum.TextXAlignment.Center,
			size = UDim2.new(1, 0, 0, 90), pos = UDim2.new(0, 0, 0.3, 0), parent = card, scaled = true })
		sub.ZIndex = 81
		local share = Overlays.shareButton("SHOW WHAT YOU MADE", "evolution", card, UDim2.new(0.5, 0, 0.72, 0))
		share.ZIndex = 82
		task.delay(6, function()
			card:Destroy()
			if payload.needsName then
				Overlays.askName()
			end
		end)
	end)
end

-- ═══ NAMING (SPEC §19) ═══════════════════════════════════════════════════════

local SUGGESTIONS = { "Mochi", "Noodle", "Pickle", "Bubbles", "Chunk", "Biscuit", "Wobble", "Pudding", "Zappy", "Gloop", "Nugget", "Taco" }

function Overlays.askName()
	local card = Theme.card(ctx.overlayLayer, Theme.PAPER, 26)
	card.AnchorPoint = Vector2.new(0.5, 0.5)
	card.Position = UDim2.fromScale(0.5, 0.45)
	card.Size = UDim2.fromOffset(380, 250)
	card.ZIndex = 85
	Theme.stroke(card, 3, Theme.accent.monster)
	Theme.pop(card)
	Theme.text({ text = "What is its name?", font = Theme.DISPLAY, textSize = 30, align = Enum.TextXAlignment.Center,
		pos = UDim2.fromOffset(0, 18), size = UDim2.new(1, 0, 0, 40), parent = card }).ZIndex = 86
	local box = Instance.new("TextBox")
	box.Size = UDim2.new(1, -48, 0, 56)
	box.Position = UDim2.fromOffset(24, 72)
	box.BackgroundColor3 = Theme.PAPER2
	box.Font = Theme.DISPLAY
	box.TextSize = 26
	box.TextColor3 = Theme.INK
	box.PlaceholderText = SUGGESTIONS[math.random(1, #SUGGESTIONS)]
	box.Text = ""
	box.ClearTextOnFocus = false
	box.ZIndex = 86
	box.Parent = card
	Theme.corner(box, 14)
	local function submit(name: string)
		local r = Net.func("NameCreature"):InvokeServer(name)
		card:Destroy()
		if r and r.ok then
			ctx.toast({ title = "MEET", label = "🐾 " .. r.name, color = 0xFF96BC })
		end
	end
	local ok = Theme.button({ label = "That's its name!", size = UDim2.new(1, -48, 0, 58), pos = UDim2.fromOffset(24, 146), color = Theme.accent.monster,
		textSize = 22, parent = card, onClick = function()
			submit(box.Text ~= "" and box.Text or box.PlaceholderText)
		end })
	ok.ZIndex = 86
	local skip = Instance.new("TextButton")
	skip.BackgroundTransparency = 1
	skip.Text = "Use \"" .. box.PlaceholderText .. "\""
	skip.Font = Theme.BOLD
	skip.TextSize = 14
	skip.TextColor3 = Theme.MUTED
	skip.Size = UDim2.new(1, 0, 0, 24)
	skip.Position = UDim2.fromOffset(0, 214)
	skip.ZIndex = 86
	skip.Parent = card
	skip.MouseButton1Click:Connect(function()
		submit(box.PlaceholderText)
	end)
end

-- ═══ OFFLINE REPORT (SPEC §17) ═══════════════════════════════════════════════

function Overlays.offlineReport(report)
	local card = Theme.card(ctx.overlayLayer, Theme.PAPER, 26)
	card.AnchorPoint = Vector2.new(0.5, 0.5)
	card.Position = UDim2.fromScale(0.5, 0.45)
	card.Size = UDim2.fromOffset(420, 0)
	card.AutomaticSize = Enum.AutomaticSize.Y
	card.ZIndex = 84
	Theme.stroke(card, 3, Theme.accent.book)
	Theme.pad(card, 22, 18)
	Theme.list(card, Enum.FillDirection.Vertical, 10, Enum.HorizontalAlignment.Center)
	Theme.pop(card)
	local function t(text, font, size, color, order)
		local l = Theme.text({ text = text, font = font, textSize = size, color = color, align = Enum.TextXAlignment.Center, parent = card, order = order, auto = true })
		l.ZIndex = 85
		return l
	end
	t("WHILE YOU WERE GONE...", Theme.BOLD, 15, Theme.MUTED, 1)
	t(report.headline or "", Theme.DISPLAY, 26, Theme.INK, 2)
	if report.gathered and #report.gathered > 0 then
		t("It brought back: " .. table.concat(report.gathered, ", "), Theme.BODY, 15, Theme.INK, 3)
	end
	if report.coins and report.coins > 0 then
		t("🪙 " .. report.coins, Theme.DISPLAY, 20, Theme.INK, 4)
	end
	local b = Theme.button({ label = "Go see", size = UDim2.fromOffset(200, 56), color = Theme.accent.book, textColor = Theme.WHITE, textSize = 22,
		parent = card, order = 10, onClick = function()
			card:Destroy()
		end })
	b.ZIndex = 85
end

-- ═══ PARADE BAR (SPEC §23) ═══════════════════════════════════════════════════

local paradeBar: Frame
local paradeLabel: TextLabel
local function buildParadeBar()
	paradeBar = Theme.card(ctx.gui, Theme.PAPER, 22)
	paradeBar.AnchorPoint = Vector2.new(0.5, 1)
	paradeBar.Position = UDim2.new(0.5, 0, 1, -104)
	paradeBar.Size = UDim2.fromOffset(420, 116)
	paradeBar.Visible = false
	paradeBar.ZIndex = 25
	Theme.stroke(paradeBar, 3, Theme.accent.parade)
	paradeLabel = Theme.text({ text = "", font = Theme.DISPLAY, textSize = 20, align = Enum.TextXAlignment.Center, pos = UDim2.fromOffset(10, 6),
		size = UDim2.new(1, -20, 0, 28), parent = paradeBar, scaled = true })
	local row = Instance.new("Frame")
	row.BackgroundTransparency = 1
	row.Position = UDim2.fromOffset(10, 40)
	row.Size = UDim2.new(1, -20, 0, 66)
	row.Parent = paradeBar
	Theme.list(row, Enum.FillDirection.Horizontal, 8, Enum.HorizontalAlignment.Center)
	for i, c in ipairs({ { "Weirdest", "😂" }, { "Cutest", "😍" }, { "Scariest", "😱" }, { "Unexpected", "🤯" } }) do
		Theme.button({ emoji = c[2], sub = c[1], size = UDim2.fromOffset(94, 64), textSize = 30, order = i, parent = row, color = Theme.lighter(Theme.accent.parade, 0.7),
			onClick = function()
				local r = Net.func("ParadeVote"):InvokeServer(c[1])
				if r and r.ok then
					ctx.effects.play("Pop", 0.2)
				end
			end })
	end
end

local function floatingReaction(emoji: string)
	local l = Theme.text({ text = emoji, textSize = 44, align = Enum.TextXAlignment.Center, size = UDim2.fromOffset(60, 60),
		pos = UDim2.new(0.5, math.random(-180, 180), 1, -230), parent = ctx.overlayLayer })
	l.ZIndex = 70
	TweenService:Create(l, TweenInfo.new(1.6, Enum.EasingStyle.Quad), { Position = l.Position - UDim2.fromOffset(0, 220), TextTransparency = 1 }):Play()
	task.delay(1.7, function()
		l:Destroy()
	end)
end

-- ═══ INSPECTION (SPEC §24) ═══════════════════════════════════════════════════

function Overlays.inspect(info, ownerUserId: number?)
	local old = ctx.overlayLayer:FindFirstChild("InspectCard")
	if old then
		old:Destroy()
	end
	local card = Theme.card(ctx.overlayLayer, Theme.PAPER, 22)
	card.Name = "InspectCard"
	card.AnchorPoint = Vector2.new(0.5, 0)
	card.Position = UDim2.new(0.5, 0, 0, 70)
	card.Size = UDim2.fromOffset(330, 0)
	card.AutomaticSize = Enum.AutomaticSize.Y
	card.ZIndex = 60
	Theme.stroke(card, 3, Theme.accent.book)
	Theme.pad(card, 16, 12)
	Theme.list(card, Enum.FillDirection.Vertical, 4)
	Theme.pop(card)
	local function line(text, font, size, color, order)
		local l = Theme.text({ text = text, font = font, textSize = size, color = color, parent = card, order = order, auto = true })
		l.ZIndex = 61
	end
	line(info.name, Theme.DISPLAY, 28, Theme.INK, 1)
	line(string.format("Gen %d  ·  %s", info.generation or 1, info.stage or ""), Theme.BOLD, 15, Theme.MUTED, 2)
	if info.dominant then
		line(info.dominant, Theme.BOLD, 17, Theme.INK, 3)
	end
	line("Owner: " .. tostring(info.owner), Theme.BODY, 14, Theme.MUTED, 4)
	line("HOW DID THEY GET THAT?!", Theme.DISPLAY, 18, Theme.accent.book, 5)
	line(info.recipe ~= "" and info.recipe or "???", Theme.BOLD, 15, Theme.INK, 6)
	if ownerUserId and ownerUserId ~= player.UserId then
		local b = Theme.button({ emoji = "👥", label = "Invite to party", size = UDim2.new(1, 0, 0, 48), color = Theme.accent.party, textSize = 17,
			parent = card, order = 10, onClick = function()
				Net.func("PartyInviteSend"):InvokeServer(ownerUserId)
				card:Destroy()
			end })
		b.ZIndex = 61
	end
	task.delay(7, function()
		if card.Parent then
			card:Destroy()
		end
	end)
end

-- ═══ WORLD NOTICES ═══════════════════════════════════════════════════════════

local function shake(strength: number)
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	local t0 = os.clock()
	local conn
	conn = RunService.RenderStepped:Connect(function()
		local t = os.clock() - t0
		if t > 1.2 then
			conn:Disconnect()
			return
		end
		local k = (1 - t / 1.2) * 0.35 * strength
		cam.CFrame = cam.CFrame * CFrame.new(math.noise(t * 30, 1) * k, math.noise(t * 30, 2) * k, 0)
	end)
end

local function lightning(at: Vector3)
	local bolt = Instance.new("Part")
	bolt.Anchored = true
	bolt.CanCollide = false
	bolt.CanQuery = false
	bolt.Material = Enum.Material.Neon
	bolt.Color = Color3.fromRGB(255, 240, 150)
	bolt.Size = Vector3.new(0.8, 160, 0.8)
	bolt.CFrame = CFrame.new(at + Vector3.new(0, 80, 0))
	bolt.Parent = workspace
	flash(Color3.fromRGB(255, 250, 220))
	ctx.effects.play("StaticBurst")
	task.delay(0.18, function()
		bolt:Destroy()
	end)
end

function Overlays.notice(p)
	local k = p.kind
	if k == "event" then
		ctx.effects.play("MutationSting")
		local sub = {
			IngredientRain = "Food is falling from the sky in the Meadow and Town Square!",
			GiantPicnic = "A giant picnic appeared in the Meadow. Rare treats!",
			Storm = "Electric foods are twice as strong. Lightning leaves batteries behind.",
			FullMoon = "Night foods are awake. Moon Mushrooms are sprouting.",
			UFO = "Something is hovering over Town Square...",
			SlimeInvasion = "Slimes stole the food! Catch them in the Meadow.",
			Earthquake = "A hidden crystal pocket cracked open in the caves!",
			Meteor = "SOMETHING FELL FROM THE SKY. Crack it together!",
		}
		ctx.toast({ kind = "quest", title = "WORLD EVENT", label = (p.emoji or "") .. " " .. (p.display or ""), sub = sub[p.event], color = 0xA780FF })
	elseif k == "world_first" then
		ctx.effects.play("SecretSting")
		task.spawn(function()
			local ui = require(script.Parent.Parent:WaitForChild("UIController"))
			ui.banner("🏆 WORLD FIRST — " .. tostring(p.owner) .. " discovered " .. tostring(p.mutation), Theme.accent.book, 6)
		end)
	elseif k == "weather" then
		local names = { Rain = "🌧️ It's raining — water foods are stronger", Storm = "⛈️ A storm! Electric foods are MUCH stronger", Windy = "🌬️ Windy — airy foods are stronger", Fog = "🌫️ Fog rolls in — mysterious foods are stronger" }
		if names[p.weather] then
			task.spawn(function()
				local ui = require(script.Parent.Parent:WaitForChild("UIController"))
				ui.banner(names[p.weather], Theme.accent.party, 4)
			end)
		end
	elseif k == "lightning" and p.at then
		lightning(p.at)
	elseif k == "shake" then
		shake(p.strength or 1)
	elseif k == "meteor_incoming" then
		ctx.effects.play("FireWhoosh")
		task.spawn(function()
			local ui = require(script.Parent.Parent:WaitForChild("UIController"))
			ui.banner("☄️ SOMETHING IS FALLING FROM THE SKY", Theme.accent.trials, 5)
		end)
	elseif k == "meteor_impact" then
		ctx.effects.play("Impact")
		flash(Color3.fromRGB(220, 180, 255))
	elseif k == "meteor_cracked" then
		ctx.effects.play("SecretSting")
	elseif k == "abducted" then
		task.spawn(function()
			local ui = require(script.Parent.Parent:WaitForChild("UIController"))
			ui.banner("🛸 " .. tostring(p.owner) .. "'s monster was beamed up!", Theme.accent.quest, 3.5)
		end)
	elseif k == "parade_signup" then
		ctx.toast({ kind = "quest", title = "CREATURE PARADE", label = "🎭 Signing up now — open Quests to join!", color = 0xF46CC4 })
	elseif k == "parade_walk" then
		paradeBar.Visible = p.userId ~= player.UserId
		paradeLabel.Text = string.format("🎭 On the runway: <b>%s</b>'s monster", tostring(p.owner))
		if p.userId == player.UserId then
			ctx.toast({ title = "YOUR TURN", label = "🎭 Everyone is watching your monster!", color = 0xF46CC4 })
		end
		task.delay(15, function()
			paradeBar.Visible = false
		end)
	elseif k == "parade_results" then
		paradeBar.Visible = false
		local lines = {}
		for _, w in ipairs(p.winners or {}) do
			table.insert(lines, string.format("%s %s: %s", w.emoji, w.category, w.owner))
		end
		if #lines > 0 then
			ctx.toast({ kind = "quest", title = "PARADE RESULTS", label = lines[1], sub = table.concat(lines, "   "), color = 0xF46CC4 })
		end
	end
end

function Overlays.init(c)
	ctx = c
	Theme = c.Theme
	buildParadeBar()
	Net.event("ParadeReaction").OnClientEvent:Connect(function(p)
		local map = { Weirdest = "😂", Cutest = "😍", Scariest = "😱", Unexpected = "🤯" }
		floatingReaction(map[p.category] or "✨")
	end)
	Net.event("PartyInvite").OnClientEvent:Connect(function(p)
		local card = Theme.card(ctx.overlayLayer, Theme.PAPER, 20)
		card.AnchorPoint = Vector2.new(0.5, 0)
		card.Position = UDim2.new(0.5, 0, 0, 70)
		card.Size = UDim2.fromOffset(340, 120)
		card.ZIndex = 65
		Theme.stroke(card, 3, Theme.accent.party)
		Theme.text({ text = "👥 " .. tostring(p.from) .. " invited you to a party", font = Theme.DISPLAY, textSize = 18,
			align = Enum.TextXAlignment.Center, pos = UDim2.fromOffset(10, 10), size = UDim2.new(1, -20, 0, 40), parent = card }).ZIndex = 66
		local yes = Theme.button({ label = "Join", size = UDim2.fromOffset(140, 50), pos = UDim2.new(0, 16, 1, -62), color = Theme.accent.party, textSize = 20, parent = card,
			onClick = function()
				Net.func("PartyAccept"):InvokeServer()
				card:Destroy()
			end })
		yes.ZIndex = 66
		local no = Theme.button({ label = "Not now", size = UDim2.fromOffset(140, 50), pos = UDim2.new(1, -156, 1, -62), color = Theme.PAPER2, textSize = 18, parent = card,
			onClick = function()
				card:Destroy()
			end })
		no.ZIndex = 66
		task.delay(30, function()
			if card.Parent then
				card:Destroy()
			end
		end)
	end)
	local _ = UserInputService
end

return Overlays
