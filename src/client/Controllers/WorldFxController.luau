--!strict
-- WorldFxController — the world reacting to YOU (SPEC §11 "a gate you finally open is a
-- moment", §20 co-op gates). Gates are per-player: the boulder only rolls away on the
-- screen of someone who has opened it, so this is all client-local.
--
--   * gate_open notices animate the gate's model (roll, grow, power up, sink, fade)
--   * ProfileSync re-applies opened gates instantly after a respawn/rejoin
--   * ProximityPrompts carrying an OpenPanel attribute open that UI panel (trials portal)

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local ProximityPromptService = game:GetService("ProximityPromptService")

local WorldFxController = {}

local player = Players.LocalPlayer
local effects: any
local ui: any

-- gate id -> the mesh instance the reveal was applied to. Streaming can drop a mesh and
-- send a fresh server copy later; a different instance means "apply again".
local applied: { [string]: Instance } = {}

local GOLD = Color3.fromRGB(255, 213, 46)

local modelCache: { [string]: Model } = {}
local function gateModel(id: string): Model?
	local cached = modelCache[id]
	if cached and cached.Parent then
		return cached
	end
	local w = workspace:FindFirstChild("World")
	if not w then
		return nil
	end
	for _, d in ipairs(w:GetDescendants()) do
		if d.Name == "Gate_" .. id .. "_Model" and d:IsA("Model") then
			modelCache[id] = d
			return d
		end
	end
	return nil
end

local function gateMarker(id: string): BasePart?
	local w = workspace:FindFirstChild("World")
	local m = w and w:FindFirstChild("Markers")
	return m and m:FindFirstChild("Gate_" .. id) :: BasePart?
end

local function parts(m: Instance): { BasePart }
	local out = {}
	if m:IsA("BasePart") then
		table.insert(out, m)
	end
	for _, d in ipairs(m:GetDescendants()) do
		if d:IsA("BasePart") then
			table.insert(out, d)
		end
	end
	return out
end

local function tweenPivot(m: Model, to: CFrame, seconds: number, style: Enum.EasingStyle?)
	local v = Instance.new("CFrameValue")
	v.Value = m:GetPivot()
	v.Changed:Connect(function(cf)
		if m.Parent then
			m:PivotTo(cf)
		end
	end)
	local t = TweenService:Create(v, TweenInfo.new(seconds, style or Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { Value = to })
	t.Completed:Connect(function()
		v:Destroy()
	end)
	t:Play()
end

local function tweenScale(m: Model, from: number, to: number, seconds: number)
	local base = m:GetScale()
	local v = Instance.new("NumberValue")
	v.Value = from
	m:ScaleTo(base * from)
	v.Changed:Connect(function(s)
		if m.Parent then
			m:ScaleTo(math.max(0.01, base * s))
		end
	end)
	local t = TweenService:Create(v, TweenInfo.new(seconds, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Value = to })
	t.Completed:Connect(function()
		v:Destroy()
	end)
	t:Play()
end

local function noCollide(m: Instance)
	for _, p in ipairs(parts(m)) do
		p.CanCollide = false
	end
end

-- colliders tagged for the gate's ability (ghost barrier) live next to the model
local function barrierNear(pos: Vector3, tag: string): BasePart?
	local CollectionService = game:GetService("CollectionService")
	for _, p in ipairs(CollectionService:GetTagged(tag)) do
		if p:IsA("BasePart") and (p.Position - pos).Magnitude < 20 then
			return p
		end
	end
	return nil
end

-- per-asset reveal. `instant` = already opened earlier (no fanfare)
local REVEAL: { [string]: (Model, BasePart?, boolean) -> () } = {
	Boulder_Big = function(m, _, instant)
		-- roll about its middle, not its base, so it ends up resting on the ground
		local h = m:GetExtentsSize().Y * 0.5
		local to = m:GetPivot() * CFrame.new(14, h, 0) * CFrame.Angles(0, 0, math.rad(-200)) * CFrame.new(0, -h, 0)
		noCollide(m)
		if instant then
			m:PivotTo(to)
		else
			tweenPivot(m, to, 1.6, Enum.EasingStyle.Bounce)
		end
	end,
	VineWall = function(m, _, instant)
		for _, p in ipairs(parts(m)) do
			p.Transparency = 0
		end
		if not instant then
			tweenScale(m, 0.05, 1, 1.4)
		end
	end,
	Generator_Dead = function(m, _, instant)
		for _, p in ipairs(parts(m)) do
			if not p:FindFirstChildOfClass("PointLight") then
				local l = Instance.new("PointLight")
				l.Color = Color3.fromRGB(255, 230, 120)
				l.Range = 18
				l.Brightness = instant and 2 or 0
				l.Parent = p
				if not instant then
					TweenService:Create(l, TweenInfo.new(0.12, Enum.EasingStyle.Linear, Enum.EasingDirection.InOut, 8, true), { Brightness = 4 }):Play()
					task.delay(2, function()
						l.Brightness = 2
					end)
				end
			end
			break
		end
	end,
	CrackedGround = function(m, _, instant)
		local to = m:GetPivot() * CFrame.new(0, -3, 0)
		noCollide(m)
		if instant then
			m:PivotTo(to)
		else
			tweenPivot(m, to, 1.2)
		end
	end,
	CaveRock_C = function(m, _, instant)
		local to = m:GetPivot() * CFrame.new(0, -8, 0)
		noCollide(m)
		if instant then
			m:PivotTo(to)
		else
			tweenPivot(m, to, 2.0, Enum.EasingStyle.Sine)
		end
	end,
	GhostBarrier = function(m, _, instant)
		local b = barrierNear(m:GetPivot().Position, "GhostBarrier")
		for _, p in ipairs(parts(m)) do
			if instant then
				p.Transparency = 0.85
			else
				TweenService:Create(p, TweenInfo.new(1.5), { Transparency = 0.85 }):Play()
			end
			p.CanCollide = false
		end
		if b then
			b.CanCollide = false
			b.Transparency = 0.9
		end
	end,
	Magnet_Crane = function(m, _, instant)
		if instant then
			return
		end
		local base = m:GetPivot()
		tweenPivot(m, base * CFrame.Angles(0, math.rad(40), 0), 2.5, Enum.EasingStyle.Elastic)
	end,
}

-- with StreamingEnabled a far-away gate model can exist with no parts yet: park the
-- reveal and apply it (without fanfare) the moment the mesh streams in
local pending: { [string]: boolean } = {}

function WorldFxController.openGate(id: string, instant: boolean?)
	local streamed = gateModel(id)
	if not streamed or not streamed.PrimaryPart then
		pending[id] = true
		return
	end
	if applied[id] then
		if not instant then
			local marker = gateMarker(id)
			if marker then
				effects.ringAt(marker.Position, GOLD)
			end
		end
		return
	end
	applied[id] = streamed.PrimaryPart :: Instance
	local m = streamed
	local marker = gateMarker(id)
	local name = m and string.gsub((m.PrimaryPart and m.PrimaryPart.Name) or "", "%.%d+$", "") or ""
	local fx = REVEAL[name]
	if m and fx then
		local ok, err = pcall(fx, m, marker, instant == true)
		if not ok then
			warn("[WorldFx] gate " .. id .. ": " .. tostring(err))
		end
	end
	if marker then
		local prompt = marker:FindFirstChild("GatePrompt") :: ProximityPrompt?
		if prompt then
			prompt.ActionText = "Visit"
		end
		if not instant then
			effects.burstAt(marker.Position, GOLD, 1.4)
			effects.ringAt(marker.Position, GOLD)
			effects.playAt("MutationSting", marker.Position)
		end
	end
end

-- VineWall starts hidden: "bare rock" until something grows it
local function hideUnopenedVines()
	local m = gateModel("MeadowVines")
	if m and m.PrimaryPart and not applied.MeadowVines and not pending.MeadowVines and m.PrimaryPart.Transparency < 1 then
		for _, p in ipairs(parts(m)) do
			p.Transparency = 1
		end
	end
end

function WorldFxController.syncProfile(profile)
	for id, on in pairs(profile.gatesOpened or {}) do
		if on and not applied[id] then
			WorldFxController.openGate(id, true)
		end
	end
end

function WorldFxController.start(effectsController, uiController)
	effects = effectsController
	ui = uiController
	task.spawn(function()
		local w = workspace:WaitForChild("World", 30)
		if not w then
			return
		end
		-- gate meshes stream in and out as you move: keep unopened vines hidden and
		-- apply parked reveals whenever their mesh arrives
		while true do
			hideUnopenedVines()
			for id in pairs(pending) do
				local m = gateModel(id)
				if m and m.PrimaryPart then
					pending[id] = nil
					applied[id] = nil
					WorldFxController.openGate(id, true)
				end
			end
			for id, part in pairs(applied) do
				local m = gateModel(id)
				if m and m.PrimaryPart and m.PrimaryPart ~= part then
					applied[id] = nil
					WorldFxController.openGate(id, true)
				elseif m and not m.PrimaryPart then
					applied[id] = nil
					pending[id] = true
				end
			end
			task.wait(1)
		end
	end)

	ProximityPromptService.PromptTriggered:Connect(function(prompt, who)
		if who ~= player then
			return
		end
		local panel = prompt:GetAttribute("OpenPanel")
		if typeof(panel) == "string" and ui and ui.open then
			ui.open(panel)
		end
	end)
end

return WorldFxController
