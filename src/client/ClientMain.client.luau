--!strict
-- ClientMain — wires server pushes to feedback. SPEC §44: the creature is the UI.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

local Controllers = script.Parent:WaitForChild("Controllers")
local EffectsController = require(Controllers:WaitForChild("EffectsController"))
local CreatureController = require(Controllers:WaitForChild("CreatureController"))
local UIController = require(Controllers:WaitForChild("UIController"))
local MovementController = require(Controllers:WaitForChild("MovementController"))
local AmbienceController = require(Controllers:WaitForChild("AmbienceController"))

EffectsController.start()
UIController.build()
CreatureController.start()
MovementController.start()
AmbienceController.start()

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
	prop:ScaleTo(math.clamp(0.9 / math.max(extents.X, extents.Y, extents.Z), 0.15, 1))
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
	conn = RunService.RenderStepped:Connect(function()
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
	EffectsController.applySettings(profile.settings)
end)

Net.event("CreatureSync").OnClientEvent:Connect(function(genome)
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

Net.event("WorldNotice").OnClientEvent:Connect(function(payload)
	UIController.notice(payload)
end)

-- SPEC §5: the eat reaction must land as a physical event, not a number.
Net.event("Reaction").OnClientEvent:Connect(function(payload)
	local model = CreatureController.myCreature()
	local color = TableUtil.unpackColor(payload.color or 0xFFD52E)
	if model then
		task.delay(0.1, flyFoodIntoMouth, payload.ingredient, model, color)
	end
	task.delay(0.46, EffectsController.play, payload.sfx, 0.08)
	task.delay(1.6, EffectsController.play, "Gulp", 0.1)
end)

Net.event("TrialFx").OnClientEvent:Connect(function(p)
	if p.at then
		local colors = { hit = Color3.fromRGB(255, 220, 140), ["break"] = Color3.fromRGB(255, 170, 90), chest = Color3.fromRGB(255, 215, 80), finish = Color3.fromRGB(120, 255, 170) }
		EffectsController.burstAt(p.at, colors[p.kind] or Color3.new(1, 1, 1), p.kind == "hit" and 0.5 or 1.4)
	end
	local sfx = { hit = "RockCrack", ["break"] = "Impact", chest = "Sparkle", finish = "MutationSting" }
	if sfx[p.kind] then
		EffectsController.play(sfx[p.kind], 0.15)
	end
end)

-- ═══ INSPECTION (SPEC §24) ═══════════════════════════════════════════════════
-- Tap any creature: owner, what it is, and the part of the recipe YOU have discovered.

local function tryInspect(screenPos: Vector2)
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	local ray = cam:ScreenPointToRay(screenPos.X, screenPos.Y)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { player.Character }
	local hit = workspace:Raycast(ray.Origin, ray.Direction * 300, params)
	if not hit then
		return
	end
	local model = hit.Instance:FindFirstAncestorOfClass("Model")
	local creatureId = model and model:GetAttribute("CreatureId")
	if not creatureId or model:GetAttribute("Owner") == player.UserId then
		return
	end
	local info = Net.func("Inspect"):InvokeServer(creatureId)
	if info then
		UIController.inspect(info, model:GetAttribute("Owner"))
		EffectsController.play("PlasticClack")
	end
end

UserInputService.InputEnded:Connect(function(input, processed)
	if processed then
		return
	end
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		tryInspect(Vector2.new(input.Position.X, input.Position.Y))
	end
end)

print("[Client] ready")
