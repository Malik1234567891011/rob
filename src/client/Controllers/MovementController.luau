--!strict
-- MovementController — SPEC §11: "The creature you create changes your exploration route."
--
-- The server stamps the player's character with what their active creature can do
-- (CanGlide, CanClimb, CanGhost, CanTiny, CanSwim, CanHeat — see CreatureService) and trial
-- attributes (TrialGlide...). The world marks special geometry with CollectionService tags:
--   GhostBarrier — solid unless you are a Ghost        (local CanCollide)
--   TinyGap      — solid unless you are Tiny           (local CanCollide)
--   ClimbWall    — Sticky monsters climb it
--   DeepWater    — you get pushed back up unless Aquatic
--   HotGround    — you hop back to safety unless Heatproof
-- Character physics are owned by the client, so this feels instant and costs nothing.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local CollectionService = game:GetService("CollectionService")

local MovementController = {}
local player = Players.LocalPlayer

local jumpHeld = false
local lastSafe: CFrame? = nil

local function can(char: Model, attr: string, trialAttr: string?): boolean
	return char:GetAttribute(attr) == true or (trialAttr ~= nil and char:GetAttribute(trialAttr) == true)
end

local function applyPassThrough()
	local char = player.Character
	if not char then
		return
	end
	local ghost = can(char, "CanGhost")
	local tiny = can(char, "CanTiny", "TrialTiny")
	for _, p in ipairs(CollectionService:GetTagged("GhostBarrier")) do
		if p:IsA("BasePart") then
			p.CanCollide = not ghost
			p.LocalTransparencyModifier = ghost and 0.35 or 0
		end
	end
	for _, p in ipairs(CollectionService:GetTagged("TinyGap")) do
		if p:IsA("BasePart") then
			p.CanCollide = not tiny
		end
	end
end

local function inside(part: BasePart, pos: Vector3): boolean
	local rel = part.CFrame:PointToObjectSpace(pos)
	local h = part.Size * 0.5
	return math.abs(rel.X) <= h.X and math.abs(rel.Y) <= h.Y and math.abs(rel.Z) <= h.Z
end

local function step(dt: number)
	local char = player.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if not char or not hrp or not hum then
		return
	end
	local state = hum:GetState()
	local v = hrp.AssemblyLinearVelocity

	-- remember where we last stood on normal ground
	if hum.FloorMaterial ~= Enum.Material.Air and state ~= Enum.HumanoidStateType.Freefall then
		local onHot = false
		for _, p in ipairs(CollectionService:GetTagged("HotGround")) do
			if p:IsA("BasePart") and inside(p, hrp.Position - Vector3.new(0, 3, 0)) then
				onHot = true
			end
		end
		if not onHot then
			lastSafe = hrp.CFrame
		elseif not can(char, "CanHeat") and lastSafe then
			hrp.CFrame = lastSafe
			hrp.AssemblyLinearVelocity = Vector3.new(0, 30, 0)
		end
	end

	-- GLIDE: hold jump while falling
	if jumpHeld and state == Enum.HumanoidStateType.Freefall and can(char, "CanGlide", "TrialGlide") and v.Y < -6 then
		local look = hrp.CFrame.LookVector
		local horizontal = Vector3.new(v.X, 0, v.Z)
		local forward = Vector3.new(look.X, 0, look.Z).Unit * math.max(horizontal.Magnitude, 22)
		hrp.AssemblyLinearVelocity = Vector3.new(forward.X, -6, forward.Z)
		char:SetAttribute("Gliding", true)
	elseif char:GetAttribute("Gliding") then
		char:SetAttribute("Gliding", nil)
	end

	-- CLIMB: Sticky monsters walk up ClimbWall surfaces
	if can(char, "CanClimb", "TrialSticky") and hum.MoveDirection.Magnitude > 0.1 then
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Include
		params.FilterDescendantsInstances = CollectionService:GetTagged("ClimbWall")
		local hit = workspace:Raycast(hrp.Position, hum.MoveDirection.Unit * 2.6, params)
		if hit then
			hrp.AssemblyLinearVelocity = Vector3.new(v.X * 0.2, 18, v.Z * 0.2)
		end
	end

	-- DEEP WATER: only Aquatic monsters let you dive
	if not can(char, "CanSwim") then
		for _, p in ipairs(CollectionService:GetTagged("DeepWater")) do
			if p:IsA("BasePart") and inside(p, hrp.Position) then
				hrp.AssemblyLinearVelocity = Vector3.new(v.X, math.max(v.Y, 26), v.Z)
			end
		end
	elseif state == Enum.HumanoidStateType.Swimming then
		local swim = char:GetAttribute("TrialSwim") or 30
		hum.WalkSpeed = math.max(hum.WalkSpeed, swim)
	end
end

function MovementController.start()
	UserInputService.JumpRequest:Connect(function()
		jumpHeld = true
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.KeyCode == Enum.KeyCode.Space or input.KeyCode == Enum.KeyCode.ButtonA or input.UserInputType == Enum.UserInputType.Touch then
			jumpHeld = false
		end
	end)
	RunService.Heartbeat:Connect(step)
	task.spawn(function()
		while true do
			applyPassThrough()
			task.wait(0.5)
		end
	end)
	CollectionService:GetInstanceAddedSignal("GhostBarrier"):Connect(applyPassThrough)
	CollectionService:GetInstanceAddedSignal("TinyGap"):Connect(applyPassThrough)
end

return MovementController
