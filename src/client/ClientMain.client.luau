--!strict
-- Main (client) — wires server pushes to feedback. SPEC §44: the creature is the UI.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local TweenService = game:GetService("TweenService")

local player = Players.LocalPlayer
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))
local Traits = require(Shared.Config:WaitForChild("Traits"))

local Controllers = script.Parent:WaitForChild("Controllers")
local UIController = require(Controllers:WaitForChild("UIController"))
local EffectsController = require(Controllers:WaitForChild("EffectsController"))
local CreatureController = require(Controllers:WaitForChild("CreatureController"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

UIController.build()
CreatureController.start()

local function myCreature(): Model?
	return CreatureController.myCreature()
end

-- The food leaves the player's hand and arcs into the open mouth, timed to the lunge of
-- the eat animation (Shared.CreatureAnimator ACTIONS.eat opens the jaw at ~0.3 s).
local function flyFoodIntoMouth(ingredientId: string, model: Model, color: Color3)
	local char = player.Character
	local hand = char and (char:FindFirstChild("RightHand") or char:FindFirstChild("Right Arm") or char:FindFirstChild("HumanoidRootPart")) :: BasePart?
	local prop = PropBuilder.build(ingredientId)
	if not prop or not hand then
		return
	end
	local extents = prop:GetExtentsSize()
	local s = math.clamp(0.9 / math.max(extents.X, extents.Y, extents.Z), 0.15, 1)
	prop:ScaleTo(s)
	for _, d in ipairs(prop:GetDescendants()) do
		if d:IsA("BasePart") then
			d.Anchored = true
			d.CanCollide = false
			d.CanQuery = false
		end
	end
	prop.Parent = workspace
	local start = hand.Position
	local t0 = os.clock()
	local conn
	conn = game:GetService("RunService").RenderStepped:Connect(function()
		local t = (os.clock() - t0) / 0.34
		local mouth = CreatureController.mouthOf(model) or start
		if t >= 1 or not model.Parent then
			conn:Disconnect()
			prop:Destroy()
			EffectsController.burstAt(mouth, color, 0.9)
			return
		end
		local p = start:Lerp(mouth, t) + Vector3.new(0, math.sin(t * math.pi) * 2.2, 0)
		prop:PivotTo(CFrame.new(p) * CFrame.Angles(t * 7, t * 5, 0))
	end)
end

-- ═══ SERVER PUSHES ═══════════════════════════════════════════════════════════

Net.event("ProfileSync").OnClientEvent:Connect(function(profile)
	UIController.setProfile(profile)
end)

Net.event("CreatureSync").OnClientEvent:Connect(function(genome, report)
	UIController.setGenome(genome)
end)

Net.event("Toast").OnClientEvent:Connect(function(payload)
	UIController.toast(payload)
end)

Net.event("Evolution").OnClientEvent:Connect(function(payload)
	UIController.evolution(payload)
end)

Net.event("OfflineReport").OnClientEvent:Connect(function(report)
	UIController.offlineReport(report)
end)

Net.event("FtueStep").OnClientEvent:Connect(function(index, payload)
	UIController.ftue(index, payload)
end)

-- SPEC §5: the eat reaction must land as a physical event, not a number.
Net.event("Reaction").OnClientEvent:Connect(function(payload)
	local model = myCreature()
	local color = TableUtil.unpackColor(payload.color or 0xFFD52E)
	if model then
		task.delay(0.1, flyFoodIntoMouth, payload.ingredient, model, color)
	end
	task.delay(0.46, EffectsController.play, payload.sfx, 0.08)
end)

-- ═══ INSPECTION (SPEC §24) ═══════════════════════════════════════════════════
-- Click any creature: who owns it, what it is, and the part of the recipe you have
-- personally discovered. Everything else stays "???" — envy becomes curiosity.

local function showInspect(info)
	local gui = player:WaitForChild("PlayerGui"):FindFirstChild("FeedAMonster")
	if not gui then
		return
	end
	local old = gui:FindFirstChild("InspectCard")
	if old then
		old:Destroy()
	end

	local card = Instance.new("Frame")
	card.Name = "InspectCard"
	card.AnchorPoint = Vector2.new(0.5, 0)
	card.Position = UDim2.new(0.5, 0, 0.12, 0)
	card.Size = UDim2.fromOffset(300, 150)
	card.BackgroundColor3 = Color3.fromRGB(252, 250, 246)
	card.ZIndex = 15
	card.Parent = gui

	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 18)
	c.Parent = card
	local s = Instance.new("UIStroke")
	s.Thickness = 3
	s.Color = Color3.fromRGB(167, 123, 255)
	s.Parent = card

	local function line(txt, y, font, size, color)
		local l = Instance.new("TextLabel")
		l.BackgroundTransparency = 1
		l.Position = UDim2.fromOffset(14, y)
		l.Size = UDim2.new(1, -28, 0, size + 6)
		l.Font = font
		l.TextSize = size
		l.TextXAlignment = Enum.TextXAlignment.Left
		l.TextColor3 = color
		l.Text = txt
		l.ZIndex = 16
		l.Parent = card
		return l
	end

	line(info.name, 12, Enum.Font.FredokaOne, 24, Color3.fromRGB(28, 26, 34))
	line(string.format("Gen %d  ·  %s", info.generation, info.stage), 42,
		Enum.Font.GothamBold, 15, Color3.fromRGB(120, 118, 130))
	line(info.dominant or "", 64, Enum.Font.GothamBold, 16, Color3.fromRGB(28, 26, 34))
	line("Owner: " .. info.owner, 86, Enum.Font.Gotham, 14, Color3.fromRGB(120, 118, 130))
	line(info.recipe ~= "" and info.recipe or "???", 110, Enum.Font.GothamBold, 14,
		Color3.fromRGB(167, 123, 255))

	task.delay(5, function()
		if card.Parent then
			TweenService:Create(card, TweenInfo.new(0.25), { BackgroundTransparency = 1 }):Play()
			task.wait(0.3)
			card:Destroy()
		end
	end)
end

local function tryInspect()
	local mouse = player:GetMouse()
	local target = mouse.Target
	if not target then
		return
	end
	local model = target:FindFirstAncestorOfClass("Model")
	if not model then
		return
	end
	local creatureId = model:GetAttribute("CreatureId")
	if not creatureId then
		return
	end
	local info = Net.func("Inspect"):InvokeServer(creatureId)
	if info then
		showInspect(info)
		EffectsController.play("click")
	end
end

UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.UserInputType == Enum.UserInputType.MouseButton1
		or input.UserInputType == Enum.UserInputType.Touch then
		tryInspect()
	end
end)

print("[Client] ready")
