--!strict
-- ClientMain — wires server pushes to feedback. SPEC §44: the creature is the UI.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
-- how many meals this player had when they joined (set by the first ProfileSync)
local feedsAtJoin: number? = nil
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
local WorldFxController = require(Controllers:WaitForChild("WorldFxController"))

-- one broken controller must never take the rest of the client down with it
local function boot(name: string, fn: () -> ())
	local ok, err = pcall(fn)
	if not ok then
		warn("[Client] " .. name .. " failed to start: " .. tostring(err))
	end
end
boot("Effects", EffectsController.start)
boot("UI", UIController.build)
boot("Creature", CreatureController.start)
boot("Movement", MovementController.start)
boot("Ambience", AmbienceController.start)
boot("WorldFx", function()
	WorldFxController.start(EffectsController, UIController)
end)

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
	if feedsAtJoin == nil then
		feedsAtJoin = profile.stats and profile.stats.feeds or 0
	end
	UIController.setProfile(profile)
	EffectsController.applySettings(profile.settings)
	WorldFxController.syncProfile(profile)
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
	if typeof(payload) == "table" and typeof(payload.focus) == "Vector3" then
		-- stand behind the player, looking over their shoulder at what matters
		task.spawn(function()
			local char = player.Character or player.CharacterAdded:Wait()
			local hrp = char:WaitForChild("HumanoidRootPart", 5) :: BasePart?
			local cam = workspace.CurrentCamera
			if hrp and cam then
				task.wait(0.15)
				local flat = Vector3.new(payload.focus.X - hrp.Position.X, 0, payload.focus.Z - hrp.Position.Z)
				local dir = flat.Magnitude > 0.1 and flat.Unit or hrp.CFrame.LookVector
				hrp.CFrame = CFrame.lookAt(hrp.Position, hrp.Position + dir)
				local eye = hrp.Position - dir * 11 + Vector3.new(0, 6, 0)
				cam.CFrame = CFrame.lookAt(eye, payload.focus)
			end
		end)
	end
	UIController.ftue(index, payload)
end)

Net.event("WorldNotice").OnClientEvent:Connect(function(payload)
	if payload.kind == "gate_open" and payload.gate then
		WorldFxController.openGate(payload.gate, payload.instant)
	end
	UIController.notice(payload)
end)

-- SPEC §5: the eat reaction must land as a physical event, not a number.
-- SPEC §99 #2 "the monster changes visibly, almost immediately": the first meals get a
-- short over-the-shoulder push-in on the monster so a baby's first sprout can't be missed.
local shotsLeft = 2
local function focusShot(model: Model, seconds: number)
	local cam = workspace.CurrentCamera
	local root = model.PrimaryPart
	local char = player.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not cam or not root or not hrp then
		return
	end
	local height = model:GetAttribute("Height") or 2
	local target = root.Position + Vector3.new(0, height * 0.55, 0)
	local toPlayer = Vector3.new(hrp.Position.X - target.X, 0, hrp.Position.Z - target.Z)
	toPlayer = toPlayer.Magnitude > 0.1 and toPlayer.Unit or Vector3.new(0, 0, 1)
	local side = Vector3.new(-toPlayer.Z, 0, toPlayer.X)
	local eye = target + toPlayer * (4 + height * 1.6) + side * 1.5 + Vector3.new(0, 1 + height * 0.5, 0)
	local before = cam.CFrame
	cam.CameraType = Enum.CameraType.Scriptable
	local TweenService = game:GetService("TweenService")
	TweenService:Create(cam, TweenInfo.new(0.45, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { CFrame = CFrame.lookAt(eye, target) }):Play()
	task.delay(seconds, function()
		local back = TweenService:Create(cam, TweenInfo.new(0.4, Enum.EasingStyle.Quad, Enum.EasingDirection.InOut), { CFrame = before })
		back:Play()
		back.Completed:Wait()
		cam.CameraType = Enum.CameraType.Custom
	end)
end

Net.event("Reaction").OnClientEvent:Connect(function(payload)
	local model = CreatureController.myCreature()
	local color = TableUtil.unpackColor(payload.color or 0xFFD52E)
	if model then
		task.delay(0.1, flyFoodIntoMouth, payload.ingredient, model, color)
		-- judged from the profile as it was when you joined: the sync for THIS meal can land
		-- before the reaction does
		if shotsLeft > 0 and feedsAtJoin == 0 then
			shotsLeft -= 1
			task.delay(0.35, function()
				-- the model is rebuilt when it mutates: frame the fresh one
				focusShot(CreatureController.myCreature() or model, 2.2)
			end)
		end
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
