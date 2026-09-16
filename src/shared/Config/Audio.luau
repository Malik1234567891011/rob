--!strict
-- Shared.Config.Audio — SPEC §43 "Sound as status signalling". Every sound has a curated
-- Creator Store asset (licensed libraries: ProSoundEffects / Roblox / APM / Monstercat) and an
-- engine-bundled fallback, so the game is never silent even if an asset is moderated away.
--
-- `pitch`/`volume` shape one file into several distinct sounds.

local Audio = {}

local B = {
	pop = "rbxasset://sounds/button.wav",
	splat = "rbxasset://sounds/splat.wav",
	hit = "rbxasset://sounds/hit.wav",
	click = "rbxasset://sounds/clickfast.wav",
	ping = "rbxasset://sounds/electronicpingshort.wav",
	switch = "rbxasset://sounds/switch3.wav",
	metal = "rbxasset://sounds/metal.ogg",
	water = "rbxasset://sounds/impact_water.mp3",
	bass = "rbxasset://sounds/bass.wav",
	snap = "rbxasset://sounds/snap.mp3",
}

-- key = { id = assetId (0 = use fallback), fallback = bundled file, pitch, volume }
Audio.sfx = {
	JuicyCrunch   = { id = 9113660664, fallback = B.splat, pitch = 1.15, volume = 0.6 },
	HardCrunch    = { id = 9113734831, fallback = B.snap, pitch = 0.85, volume = 0.55 },
	SoftSquish    = { id = 9126209045, fallback = B.splat, pitch = 0.8, volume = 0.5 },
	Slurp         = { id = 9113861348, fallback = B.water, pitch = 0.8, volume = 0.55 },
	Gulp          = { id = 9114687054, fallback = B.water, pitch = 0.55, volume = 0.45 },
	Burp          = { id = 9113414870, fallback = B.bass, pitch = 0.7, volume = 0.5 },
	Pop           = { id = 9119669295, fallback = B.pop, pitch = 1.5, volume = 0.5 },
	WoodSnap      = { id = 9120826936, fallback = B.snap, pitch = 1.1, volume = 0.55 },
	RockCrack     = { id = 9118588165, fallback = B.bass, pitch = 1.3, volume = 0.5 },
	MetalClang    = { id = 9119072660, fallback = B.metal, pitch = 1.0, volume = 0.55 },
	MetalCrunch   = { id = 9119072660, fallback = B.metal, pitch = 1.35, volume = 0.5 },
	ElectricFizz  = { id = 9116279560, fallback = B.ping, pitch = 1.5, volume = 0.5 },
	StaticBurst   = { id = 9118027586, fallback = B.ping, pitch = 0.75, volume = 0.55 },
	GlassTink     = { id = 9114618924, fallback = B.ping, pitch = 1.9, volume = 0.45 },
	CrystalChime  = { id = 9116394545, fallback = B.ping, pitch = 2.2, volume = 0.5 },
	IceCrack      = { id = 9114618924, fallback = B.snap, pitch = 1.6, volume = 0.45 },
	BoneCrack     = { id = 9120826936, fallback = B.snap, pitch = 0.7, volume = 0.5 },
	Boing         = { id = 6075441854, fallback = B.pop, pitch = 1.9, volume = 0.5 },
	Squeak        = { id = 9125994778, fallback = B.pop, pitch = 2.4, volume = 0.5 },
	PlasticClack  = { id = 9126110341, fallback = B.click, pitch = 1.2, volume = 0.45 },
	RubberThud    = { id = 9114036511, fallback = B.hit, pitch = 0.8, volume = 0.5 },
	Whoosh        = { id = 9126283592, fallback = B.water, pitch = 1.6, volume = 0.35 },
	Glug          = { id = 9114687054, fallback = B.water, pitch = 0.6, volume = 0.5 },
	WetSlap       = { id = 9126209045, fallback = B.splat, pitch = 1.0, volume = 0.55 },
	FireWhoosh    = { id = 9114446852, fallback = B.bass, pitch = 1.6, volume = 0.5 },
	Sparkle       = { id = 9126073001, fallback = B.ping, pitch = 2.0, volume = 0.45 },
	Impact        = { id = 9114036511, fallback = B.hit, pitch = 0.5, volume = 0.75 },
	MutationSting = { id = 9048764562, fallback = B.ping, pitch = 1.25, volume = 0.8 },
	SecretSting   = { id = 9041915227, fallback = B.ping, pitch = 0.55, volume = 0.9 },
	Evolution     = { id = 1839997938, fallback = B.bass, pitch = 1.2, volume = 0.8 },
	UIClick       = { id = 9126110341, fallback = B.click, pitch = 1.3, volume = 0.35 },
	UIOpen        = { id = 9120733724, fallback = B.click, pitch = 0.9, volume = 0.3 },
	Coins         = { id = 5995351511, fallback = B.ping, pitch = 2.4, volume = 0.4 },
	QuestComplete = { id = 9045808250, fallback = B.ping, pitch = 1.6, volume = 0.6 },
	Pickup        = { id = 9125397272, fallback = B.pop, pitch = 1.7, volume = 0.4 },
	Hatch         = { id = 9113959343, fallback = B.snap, pitch = 1.2, volume = 0.6 },
	Footstep      = { id = 4656838861, fallback = B.hit, pitch = 1.8, volume = 0.15 },
	Thunder       = { id = 9120016021, fallback = B.bass, pitch = 0.5, volume = 0.9 },
	WrongNoise    = { id = 0, fallback = B.switch, pitch = 0.45, volume = 0.6 },
}

Audio.ambience = {
	Meadow = { id = 9112831327, volume = 0.3 },
	Rain = { id = 9112851846, volume = 0.45 },
	Cave = { id = 273398061, volume = 0.35 },
}

Audio.music = {
	Home = { id = 9048776223, volume = 0.26 },
	Explore = { id = 9048733042, volume = 0.24 },
	Event = { id = 9045800945, volume = 0.28 },
	Night = { id = 9047796475, volume = 0.22 },
}

return Audio
