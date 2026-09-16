--!strict
-- Shared.Types — central type vocabulary.
-- SPEC §71: we store a COMPACT GENOME. We never serialize assembled models.

export type TraitVector = { [string]: number }

export type RecentInfluence = { ingredient: string, at: number }

export type PartSet = {
	Head: string,
	Eyes: string,
	Mouth: string,
	Ears: string,
	Horn: string,
	Back: string,
	Tail: string,
	Legs: string,
}

export type MaterialGenes = {
	Skin: string,
	Pattern: string,
	Primary: number,   -- packed 24-bit RGB, compact for DataStore
	Secondary: number,
	Glow: number,      -- 0..1
}

-- SPEC §12: three influence layers so a kid who feeds only rocks is never bricked.
--   recent -> temporary push (decays)
--   traits -> stable, earned through repetition
--   genes  -> permanent, only locked at major milestones
export type Genome = {
	id: string,
	bodyFamily: string,
	size: number,
	parts: PartSet,
	material: MaterialGenes,
	traits: TraitVector,
	genes: TraitVector,
	recent: { RecentInfluence },
	mutations: { [string]: boolean },
	temperament: { [string]: number },
	stage: number,
	generation: number,
	parentId: string?,
	birth: number,
	name: string?,
	fedCount: number,
	abilities: { [string]: boolean },
}

export type Ingredient = {
	id: string,
	display: string,
	emoji: string,
	rarity: string,
	influences: TraitVector,
	biomes: { string },
	reaction: { animation: string, sfx: string, color: number? },
	model: { shape: string, size: { number }, color: number, material: string? },
}

export type Mutation = {
	id: string,
	display: string,
	emoji: string,
	rarity: string,
	requirements: { [string]: number },
	blockers: { [string]: number }?,
	stage: number,
	parts: { [string]: string }?,
	ability: string?,
	sizeMul: number?,
	tint: number?,
	secret: boolean?,
	hint: string?,
}

export type Profile = {
	coins: number,
	essence: number,
	inventory: { [string]: number },
	discovered: {
		ingredients: { [string]: boolean },
		traits: { [string]: boolean },
		mutations: { [string]: boolean },
	},
	creatures: { Genome },
	activeCreature: number,
	lineage: number,
	ftueStep: number,
	lastSeen: number,
	sanctuaryTier: number,
	stats: { [string]: number },
}

return {}
