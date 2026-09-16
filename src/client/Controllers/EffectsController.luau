--!strict
-- EffectsController — SPEC §43. Eating needs an ASMR-ish tactile quality, and "players should
-- recognise the rare mutation sound from across the server". Also music, ambience and
-- particle bursts. Everything respects the player's Music / Sounds settings.

local TweenService = game:GetService("TweenService")
local SoundService = game:GetService("SoundService")
local Debris = game:GetService("Debris")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Audio = require(Shared.Config:WaitForChild("Audio"))

local EffectsController = {}

local enabled = { music = true, sfx = true }
local sfxGroup: SoundGroup
local musicGroup: SoundGroup
local currentMusic: Sound? = nil
local currentMusicKey: string? = nil
local ambience: Sound? = nil
local ambienceKey: string? = nil

local function soundId(entry): string
	if entry.id and entry.id > 0 then
		return "rbxassetid://" .. entry.id
	end
	return entry.fallback or ""
end

function EffectsController.play(name: string, pitchJitter: number?)
	if not enabled.sfx then
		return
	end
	local entry = Audio.sfx[name]
	if not entry then
		return
	end
	local s = Instance.new("Sound")
	s.SoundId = soundId(entry)
	s.PlaybackSpeed = (entry.id and entry.id > 0 and 1 or (entry.pitch or 1)) + (pitchJitter and (math.random() - 0.5) * pitchJitter or 0)
	s.Volume = entry.volume or 0.5
	s.SoundGroup = sfxGroup
	s.Parent = SoundService
	s:Play()
	Debris:AddItem(s, 8)
end

-- A sound positioned in the world (other players' creatures eating, meteor impacts).
function EffectsController.playAt(name: string, position: Vector3)
	if not enabled.sfx then
		return
	end
	local entry = Audio.sfx[name]
	if not entry then
		return
	end
	local a = Instance.new("Part")
	a.Anchored = true
	a.CanCollide = false
	a.CanQuery = false
	a.Transparency = 1
	a.Size = Vector3.one
	a.Position = position
	a.Parent = workspace
	local s = Instance.new("Sound")
	s.SoundId = soundId(entry)
	s.Volume = (entry.volume or 0.5) * 1.3
	s.RollOffMaxDistance = 140
	s.SoundGroup = sfxGroup
	s.Parent = a
	s:Play()
	Debris:AddItem(a, 8)
end

local function fadeOut(sound: Sound?)
	if not sound then
		return
	end
	local tw = TweenService:Create(sound, TweenInfo.new(1.5), { Volume = 0 })
	tw:Play()
	tw.Completed:Connect(function()
		sound:Destroy()
	end)
end

function EffectsController.music(key: string?)
	if key == currentMusicKey then
		return
	end
	currentMusicKey = key
	fadeOut(currentMusic)
	currentMusic = nil
	local entry = key and Audio.music[key]
	if not entry or not entry.id or entry.id <= 0 or not enabled.music then
		return
	end
	local s = Instance.new("Sound")
	s.SoundId = "rbxassetid://" .. entry.id
	s.Looped = true
	s.Volume = 0
	s.SoundGroup = musicGroup
	s.Parent = SoundService
	s:Play()
	TweenService:Create(s, TweenInfo.new(2), { Volume = entry.volume or 0.25 }):Play()
	currentMusic = s
end

function EffectsController.ambience(key: string?)
	if key == ambienceKey then
		return
	end
	ambienceKey = key
	fadeOut(ambience)
	ambience = nil
	local entry = key and Audio.ambience[key]
	if not entry or not entry.id or entry.id <= 0 or not enabled.sfx then
		return
	end
	local s = Instance.new("Sound")
	s.SoundId = "rbxassetid://" .. entry.id
	s.Looped = true
	s.Volume = 0
	s.SoundGroup = sfxGroup
	s.Parent = SoundService
	s:Play()
	TweenService:Create(s, TweenInfo.new(2), { Volume = entry.volume or 0.35 }):Play()
	ambience = s
end

function EffectsController.setEnabled(kind: string, on: boolean)
	enabled[kind] = on
	if kind == "music" then
		local key = currentMusicKey
		currentMusicKey = nil
		if on then
			EffectsController.music(key)
		else
			fadeOut(currentMusic)
			currentMusic = nil
			currentMusicKey = key
		end
	elseif kind == "sfx" then
		sfxGroup.Volume = on and 1 or 0
	end
end

function EffectsController.applySettings(settings)
	if type(settings) ~= "table" then
		return
	end
	if settings.music ~= nil and settings.music ~= enabled.music then
		EffectsController.setEnabled("music", settings.music)
	end
	if settings.sfx ~= nil and settings.sfx ~= enabled.sfx then
		EffectsController.setEnabled("sfx", settings.sfx)
	end
end

-- SPEC §5: feed a battery -> BZZT. The particle burst IS the feedback.
function EffectsController.burstAt(position: Vector3, color: Color3, intensity: number?)
	local anchor = Instance.new("Part")
	anchor.Anchored = true
	anchor.CanCollide = false
	anchor.CanQuery = false
	anchor.Transparency = 1
	anchor.Size = Vector3.one
	anchor.Position = position
	anchor.Parent = workspace

	local emitter = Instance.new("ParticleEmitter")
	emitter.Color = ColorSequence.new(color, color:Lerp(Color3.new(1, 1, 1), 0.5))
	emitter.LightEmission = 0.5
	emitter.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.7), NumberSequenceKeypoint.new(1, 0) })
	emitter.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.05), NumberSequenceKeypoint.new(1, 1) })
	emitter.Lifetime = NumberRange.new(0.35, 0.75)
	emitter.Speed = NumberRange.new(5, 13)
	emitter.SpreadAngle = Vector2.new(180, 180)
	emitter.Acceleration = Vector3.new(0, -26, 0)
	emitter.Rate = 0
	emitter.Parent = anchor
	emitter:Emit(math.floor(20 * (intensity or 1)))

	local sparkle = Instance.new("ParticleEmitter")
	sparkle.Color = ColorSequence.new(Color3.new(1, 1, 1))
	sparkle.LightEmission = 1
	sparkle.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.25), NumberSequenceKeypoint.new(1, 0) })
	sparkle.Lifetime = NumberRange.new(0.3, 0.6)
	sparkle.Speed = NumberRange.new(2, 6)
	sparkle.SpreadAngle = Vector2.new(180, 180)
	sparkle.Rate = 0
	sparkle.Parent = anchor
	sparkle:Emit(math.floor(8 * (intensity or 1)))

	Debris:AddItem(anchor, 2)
end

-- Rare mutations get a ring the whole server can see (SPEC §43 status signalling).
function EffectsController.ringAt(position: Vector3, color: Color3)
	local ring = Instance.new("Part")
	ring.Shape = Enum.PartType.Cylinder
	ring.Anchored = true
	ring.CanCollide = false
	ring.CanQuery = false
	ring.Material = Enum.Material.Neon
	ring.Color = color
	ring.Size = Vector3.new(0.3, 2, 2)
	ring.CFrame = CFrame.new(position) * CFrame.Angles(0, 0, math.rad(90))
	ring.Parent = workspace
	TweenService:Create(ring, TweenInfo.new(0.85, Enum.EasingStyle.Quint, Enum.EasingDirection.Out), {
		Size = Vector3.new(0.3, 42, 42),
		Transparency = 1,
	}):Play()
	Debris:AddItem(ring, 1.2)
end

function EffectsController.start()
	sfxGroup = Instance.new("SoundGroup")
	sfxGroup.Name = "SFX"
	sfxGroup.Volume = 1
	sfxGroup.Parent = SoundService
	musicGroup = Instance.new("SoundGroup")
	musicGroup.Name = "Music"
	musicGroup.Volume = 1
	musicGroup.Parent = SoundService

	-- music follows the time of day and events; ambience follows weather
	task.spawn(function()
		local ws = ReplicatedStorage:WaitForChild("WorldState", 20)
		while true do
			local event = ws and ws:GetAttribute("Event")
			local night = Lighting.ClockTime < 6 or Lighting.ClockTime > 19
			EffectsController.music(event and "Event" or (night and "Night" or "Explore"))
			local weather = ws and ws:GetAttribute("Weather")
			EffectsController.ambience((weather == "Rain" or weather == "Storm") and "Rain" or "Meadow")
			task.wait(4)
		end
	end)
end

return EffectsController
