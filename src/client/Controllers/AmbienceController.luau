--!strict
-- AmbienceController — SPEC §40 "beautiful lighting", §47 creature weather you can SEE.
--   * rain/storm particles around the camera, fog thickening, storm darkening
--   * day/night grading on top of the server's ClockTime
--   * anything tagged "Spin" slowly rotates (windmill sails, portal discs)
--   * "DarkZone" volumes (caves) get dark unless your monster has the Light ability

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Lighting = game:GetService("Lighting")
local TweenService = game:GetService("TweenService")
local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local AmbienceController = {}
local player = Players.LocalPlayer

local rainPart: Part
local rainEmitter: ParticleEmitter
local grade: ColorCorrectionEffect
local bloom: BloomEffect

local function ensureLighting()
	grade = Lighting:FindFirstChild("FAMGrade") :: ColorCorrectionEffect
	if not grade then
		grade = Instance.new("ColorCorrectionEffect")
		grade.Name = "FAMGrade"
		grade.Parent = Lighting
	end
	bloom = Lighting:FindFirstChildOfClass("BloomEffect") :: BloomEffect
	if not bloom then
		bloom = Instance.new("BloomEffect")
		bloom.Intensity = 0.35
		bloom.Size = 22
		bloom.Threshold = 1.6
		bloom.Parent = Lighting
	end
end

local function buildRain()
	rainPart = Instance.new("Part")
	rainPart.Name = "RainEmitter"
	rainPart.Anchored = true
	rainPart.CanCollide = false
	rainPart.CanQuery = false
	rainPart.Transparency = 1
	rainPart.Size = Vector3.new(90, 1, 90)
	rainPart.Parent = workspace.CurrentCamera
	rainEmitter = Instance.new("ParticleEmitter")
	rainEmitter.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	rainEmitter.Color = ColorSequence.new(Color3.fromRGB(200, 220, 255))
	rainEmitter.LightEmission = 0.2
	rainEmitter.Size = NumberSequence.new(0.12)
	rainEmitter.Transparency = NumberSequence.new(0.35)
	rainEmitter.Lifetime = NumberRange.new(1.1, 1.4)
	rainEmitter.Speed = NumberRange.new(70, 90)
	rainEmitter.EmissionDirection = Enum.NormalId.Bottom
	rainEmitter.Squash = NumberSequence.new(-3)
	rainEmitter.Rate = 0
	rainEmitter.Parent = rainPart
end

local function inside(part: BasePart, pos: Vector3): boolean
	local rel = part.CFrame:PointToObjectSpace(pos)
	local h = part.Size * 0.5
	return math.abs(rel.X) <= h.X and math.abs(rel.Y) <= h.Y and math.abs(rel.Z) <= h.Z
end

local currentWeather = ""
local function applyWeather(weather: string)
	if weather == currentWeather then
		return
	end
	currentWeather = weather
	local atmos = Lighting:FindFirstChildOfClass("Atmosphere")
	local rate = (weather == "Rain" and 600) or (weather == "Storm" and 1100) or 0
	rainEmitter.Rate = rate
	if atmos then
		local density = (weather == "Fog" and 0.62) or (weather == "Storm" and 0.45) or (weather == "Rain" and 0.4) or 0.3
		TweenService:Create(atmos, TweenInfo.new(4), { Density = density }):Play()
	end
	local sat = (weather == "Storm" and -0.18) or (weather == "Rain" and -0.08) or 0.06
	local bright = (weather == "Storm" and -0.08) or 0
	TweenService:Create(grade, TweenInfo.new(4), { Saturation = sat, Brightness = bright }):Play()
end

function AmbienceController.start()
	ensureLighting()
	buildRain()
	local ws = ReplicatedStorage:WaitForChild("WorldState", 20)
	local spinners = {}
	local function addSpin(m: Instance)
		if not (m:IsA("Model") or m:IsA("BasePart")) then
			return
		end
		task.spawn(function()
			-- the model can replicate before its mesh does (streaming): wait for the part
			local part: BasePart? = if m:IsA("BasePart") then m else nil
			for _ = 1, 100 do
				if part then
					break
				end
				part = (m :: Model).PrimaryPart or m:FindFirstChildWhichIsA("BasePart")
				task.wait(0.1)
			end
			if not part or not m.Parent then
				return
			end
			-- spin about the part's CENTRE, not its pivot (a portal disc's pivot is the arch base)
			local base = (m :: any):GetPivot()
			spinners[m] = { base = base, centre = base:ToObjectSpace(CFrame.new(part.Position)) }
		end)
	end
	for _, m in ipairs(CollectionService:GetTagged("Spin")) do
		addSpin(m)
	end
	CollectionService:GetInstanceAddedSignal("Spin"):Connect(addSpin)
	CollectionService:GetInstanceRemovedSignal("Spin"):Connect(function(m)
		spinners[m] = nil
	end)

	local darkBlend = 0
	RunService.RenderStepped:Connect(function(dt)
		local cam = workspace.CurrentCamera
		if cam and rainPart then
			rainPart.CFrame = CFrame.new(cam.CFrame.Position + Vector3.new(0, 45, 0))
		end
		local t = os.clock()
		for m, s in pairs(spinners) do
			if m.Parent then
				local c = CFrame.new(s.centre.Position)
				m:PivotTo(s.base * c * CFrame.Angles(0, 0, t * 0.6) * c:Inverse())
			else
				spinners[m] = nil
			end
		end
		-- caves: dark unless your monster carries light
		local char = player.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		local inDark = false
		if hrp then
			for _, z in ipairs(CollectionService:GetTagged("DarkZone")) do
				if z:IsA("BasePart") and inside(z, hrp.Position) then
					inDark = true
				end
			end
		end
		local lit = char and char:GetAttribute("CanLight") == true
		darkBlend += ((inDark and 1 or 0) - darkBlend) * math.min(1, dt * 2)
		grade.Contrast = 0.04 + darkBlend * 0.1
		Lighting.ExposureCompensation = 0.1 - darkBlend * (lit and 0.6 or 2.4)
	end)

	task.spawn(function()
		while true do
			if ws then
				applyWeather(ws:GetAttribute("Weather") or "Sunny")
			end
			-- warm evenings, cool nights
			local ct = Lighting.ClockTime
			local warm = math.clamp(1 - math.abs(ct - 18.2) / 2.5, 0, 1)
			local night = (ct < 5.5 or ct > 19.5) and 1 or 0
			TweenService:Create(grade, TweenInfo.new(3), {
				TintColor = Color3.new(1, 1, 1):Lerp(Color3.fromRGB(255, 214, 180), warm * 0.6):Lerp(Color3.fromRGB(180, 196, 255), night * 0.5),
			}):Play()
			task.wait(3)
		end
	end)
end

return AmbienceController
