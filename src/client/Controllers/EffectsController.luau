--!strict
-- EffectsController — SPEC §43. Eating needs an almost ASMR-ish tactile quality,
-- and "players should recognise the rare mutation sound from across the server."
--
-- Audio uses engine-bundled rbxasset sounds (they ship with every client, so there
-- is nothing to upload and nothing to break). Each logical sfx is a bundled file
-- plus a pitch/volume treatment, which is enough to make a metal clang read
-- differently from a juicy crunch.

local TweenService = game:GetService("TweenService")
local SoundService = game:GetService("SoundService")
local Debris = game:GetService("Debris")

local EffectsController = {}

-- bundled with the engine; no asset uploads required
-- Verified present by probing the live client (see docs/DECISIONS.md). Two paths
-- that LOOK plausible are NOT shipped and fail with "Temp read failed":
--   sounds/pop_mid_up.wav, sounds/pageturn.wav  -- do not reintroduce these.
local BUNDLED = {
	pop    = "rbxasset://sounds/button.wav",
	splat  = "rbxasset://sounds/splat.wav",
	hit    = "rbxasset://sounds/hit.wav",
	click  = "rbxasset://sounds/clickfast.wav",
	ping   = "rbxasset://sounds/electronicpingshort.wav",
	switch = "rbxasset://sounds/switch3.wav",
	metal  = "rbxasset://sounds/metal.ogg",
	water  = "rbxasset://sounds/impact_water.mp3",
	bass   = "rbxasset://sounds/bass.wav",
	snap   = "rbxasset://sounds/snap.mp3",
}

-- SPEC §6 reaction names -> treatment
local SFX = {
	JuicyCrunch  = { BUNDLED.splat, 1.15, 0.55 },
	HardCrunch   = { BUNDLED.snap,  0.85, 0.5 },
	SoftSquish   = { BUNDLED.splat, 0.8,  0.45 },
	Slurp        = { BUNDLED.water, 0.8,  0.5 },
	Pop          = { BUNDLED.pop,   1.5,  0.45 },
	WoodSnap     = { BUNDLED.snap,  1.1,  0.5 },
	RockCrack    = { BUNDLED.bass,  1.3,  0.45 },
	MetalClang   = { BUNDLED.metal, 1.0,  0.55 },
	MetalCrunch  = { BUNDLED.metal, 1.35, 0.5 },
	ElectricFizz = { BUNDLED.ping,  1.5,  0.5 },
	StaticBurst  = { BUNDLED.ping,  0.75, 0.55 },
	GlassTink    = { BUNDLED.ping,  1.9,  0.4 },
	CrystalChime = { BUNDLED.ping,  2.2,  0.5 },
	IceCrack     = { BUNDLED.snap,  1.6,  0.45 },
	BoneCrack    = { BUNDLED.snap,  0.7,  0.5 },
	Boing        = { BUNDLED.pop,   1.9,  0.5 },
	Squeak       = { BUNDLED.pop,   2.4,  0.5 },
	PlasticClack = { BUNDLED.click, 1.2,  0.5 },
	RubberThud   = { BUNDLED.hit,   0.8,  0.5 },
	Whoosh       = { BUNDLED.water, 1.6,  0.35 },
	Glug         = { BUNDLED.water, 0.6,  0.5 },
	WetSlap      = { BUNDLED.splat, 1.0,  0.55 },
	FireWhoosh   = { BUNDLED.bass,  1.6,  0.5 },
	Sparkle      = { BUNDLED.ping,  2.0,  0.45 },
	Impact       = { BUNDLED.hit,   0.5,  0.75 },
	WrongNoise   = { BUNDLED.switch,0.45, 0.6 },
	-- status signalling: these two must be recognisable instantly (SPEC §43)
	MutationSting= { BUNDLED.ping,  1.25, 0.8 },
	SecretSting  = { BUNDLED.ping,  0.55, 0.9 },
	Evolution    = { BUNDLED.bass,  1.2,  0.8 },
}

function EffectsController.play(name: string, pitchJitter: number?)
	local entry = SFX[name]
	if not entry then
		return
	end
	local sound = Instance.new("Sound")
	sound.SoundId = entry[1]
	sound.PlaybackSpeed = entry[2] + (pitchJitter and (math.random() - 0.5) * pitchJitter or 0)
	sound.Volume = entry[3]
	sound.Parent = SoundService
	sound:Play()
	Debris:AddItem(sound, 5)
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
	emitter.Color = ColorSequence.new(color)
	emitter.LightEmission = 0.6
	emitter.Size = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.9),
		NumberSequenceKeypoint.new(1, 0),
	})
	emitter.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.1),
		NumberSequenceKeypoint.new(1, 1),
	})
	emitter.Lifetime = NumberRange.new(0.4, 0.8)
	emitter.Speed = NumberRange.new(6, 14)
	emitter.SpreadAngle = Vector2.new(180, 180)
	emitter.Rate = 0
	emitter.Parent = anchor
	emitter:Emit(math.floor(18 * (intensity or 1)))

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

return EffectsController
