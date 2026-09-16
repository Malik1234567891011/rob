--!strict
-- CreatureController — brings every creature on screen to life. SPEC §42, §72.
--
-- The server moves an anchored RootPart and sets a few attributes (Mood, Reveal). This
-- controller owns a Shared.CreatureAnimator per nearby creature and drives it every frame:
-- look-at (owner, held food, other creatures), mood loops, one-shot actions from the
-- CreatureAction remote. Bone.Transform is local-only, so none of this touches the network.
--
-- LOD (SPEC §72 "LOD is mandatory"): full animation within FULL_RANGE, a cheap update every
-- few frames out to LITE_RANGE, frozen beyond.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local CreatureAnimator = require(Shared:WaitForChild("CreatureAnimator"))

local CreatureController = {}

local TAG = "FAMCreature"
local FULL_RANGE = 90
local LITE_RANGE = 220

local player = Players.LocalPlayer
local rigs: { [Model]: any } = {}
local byId: { [string]: Model } = {}
local heldFocus: Vector3? = nil

local function ownerHead(model: Model): Vector3?
	local ownerId = model:GetAttribute("Owner")
	if not ownerId then
		return nil
	end
	local owner = Players:GetPlayerByUserId(ownerId)
	local char = owner and owner.Character
	local head = char and char:FindFirstChild("Head") :: BasePart?
	return head and head.Position or nil
end

local function attach(model: Model)
	if rigs[model] then
		return
	end
	task.spawn(function()
		-- the model replicates as a unit, but give the bone tree a moment to arrive
		local root = model.PrimaryPart or model:WaitForChild("RootPart", 5) :: BasePart?
		if not root then
			return
		end
		for _ = 1, 30 do
			if root:FindFirstChild("Head", true) then
				break
			end
			task.wait()
		end
		if not model.Parent or rigs[model] then
			return
		end
		local ok, rig = pcall(CreatureAnimator.new, model)
		if not ok then
			warn("[CreatureController] rig failed:", rig)
			return
		end
		rig.frame = 0
		rigs[model] = rig
		local id = model:GetAttribute("CreatureId")
		if id then
			byId[id] = model
		end
		-- a freshly rebuilt creature plays its reveal (mutation/evolution) exactly once
		local reveal = model:GetAttribute("Reveal")
		local at = model:GetAttribute("RevealAt")
		if type(reveal) == "string" and type(at) == "number" and workspace:GetServerTimeNow() - at < 4 then
			rig:play(reveal)
		end
	end)
end

local function detach(model: Model)
	local rig = rigs[model]
	rigs[model] = nil
	if rig then
		local id = model:GetAttribute("CreatureId")
		if id and byId[id] == model then
			byId[id] = nil
		end
	end
end

function CreatureController.rigFor(creatureId: string)
	local model = byId[creatureId]
	return model and rigs[model] or nil
end

function CreatureController.myCreature(): Model?
	for model in pairs(rigs) do
		if model:GetAttribute("Owner") == player.UserId then
			return model
		end
	end
	for _, m in ipairs(CollectionService:GetTagged(TAG)) do
		if m:IsA("Model") and m:GetAttribute("Owner") == player.UserId then
			return m
		end
	end
	return nil
end

-- The UI tells us where the food the player is holding is, so eyes track it (ART_DIRECTION:
-- "eyes TRACK the item as the player moves left/right").
function CreatureController.setHeldFocus(worldPos: Vector3?)
	heldFocus = worldPos
end

function CreatureController.play(creatureId: string, action: string)
	local rig = CreatureController.rigFor(creatureId)
	if rig then
		rig:play(action)
	end
end

-- Mouth position (world) for flying food into it.
function CreatureController.mouthOf(model: Model): Vector3?
	local root = model.PrimaryPart
	local jaw = root and root:FindFirstChild("Jaw", true) :: Bone?
	return jaw and jaw.TransformedWorldCFrame.Position or (root and root.Position) or nil
end

local function nearestOtherCreature(model: Model, pos: Vector3): Vector3?
	local best, bestD = nil, 14
	for other in pairs(rigs) do
		if other ~= model and other.PrimaryPart then
			local d = (other.PrimaryPart.Position - pos).Magnitude
			if d < bestD then
				best, bestD = other.PrimaryPart.Position + Vector3.new(0, (other:GetAttribute("Height") or 2) * 0.7, 0), d
			end
		end
	end
	return best
end

local function update(dt: number)
	local cam = workspace.CurrentCamera
	local camPos = cam and cam.CFrame.Position or Vector3.zero
	for model, rig in pairs(rigs) do
		local root = model.PrimaryPart
		if not root or not model.Parent then
			detach(model)
			continue
		end
		local dist = (root.Position - camPos).Magnitude
		if dist > LITE_RANGE then
			continue
		end
		rig.frame += 1
		local lite = dist > FULL_RANGE
		if lite and rig.frame % 4 ~= 0 then
			continue
		end

		rig:setMood(model:GetAttribute("Mood"))

		-- what is it looking at?
		local isMine = model:GetAttribute("Owner") == player.UserId
		local target: Vector3? = nil
		if isMine and heldFocus then
			target = heldFocus
		else
			local head = ownerHead(model)
			if head and (head - root.Position).Magnitude < 40 then
				target = head
			end
			-- occasionally glance at a nearby creature instead (SPEC §42 creature-to-creature)
			local phase = (rig.t + (rig.seed or 0)) % 9
			if phase > 6.5 then
				target = nearestOtherCreature(model, root.Position) or target
			end
		end
		rig:setLookTarget(target)
		rig:step(lite and dt * 4 or dt)
	end
end

function CreatureController.start()
	for _, m in ipairs(CollectionService:GetTagged(TAG)) do
		if m:IsA("Model") then
			attach(m)
		end
	end
	CollectionService:GetInstanceAddedSignal(TAG):Connect(function(m)
		if m:IsA("Model") then
			attach(m)
		end
	end)
	CollectionService:GetInstanceRemovedSignal(TAG):Connect(function(m)
		if m:IsA("Model") then
			detach(m)
		end
	end)

	Net.event("CreatureAction").OnClientEvent:Connect(function(creatureId, action)
		if type(creatureId) == "string" and type(action) == "string" then
			CreatureController.play(creatureId, action)
		end
	end)

	RunService.RenderStepped:Connect(update)
end

return CreatureController
