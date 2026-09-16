--!strict
-- Shared.Util.Rng — deterministic, seedable randomness.
-- Genome generation must be reproducible from a seed so a creature renders
-- identically on every client without replicating the assembled model (SPEC §71).

local Rng = {}
Rng.__index = Rng

export type Rng = typeof(setmetatable({} :: { _r: Random }, Rng))

function Rng.new(seed: number?): Rng
	return setmetatable({ _r = Random.new(seed or math.floor(os.clock() * 1e6)) }, Rng)
end

-- FNV-1a, so a creature id maps to a stable seed on every machine.
function Rng.fromString(s: string): Rng
	local hash = 2166136261
	for i = 1, #s do
		hash = bit32.bxor(hash, string.byte(s, i))
		hash = (hash * 16777619) % 4294967296
	end
	return Rng.new(hash)
end

function Rng.int(self: Rng, min: number, max: number): number
	return self._r:NextInteger(min, max)
end

function Rng.num(self: Rng, min: number?, max: number?): number
	return self._r:NextNumber(min or 0, max or 1)
end

function Rng.pick<T>(self: Rng, list: { T }): T
	return list[self._r:NextInteger(1, #list)]
end

function Rng.chance(self: Rng, p: number): boolean
	return self._r:NextNumber() < p
end

-- Weighted pick; entries may carry `weight` (defaults to 1).
function Rng.weighted(self: Rng, list: { any }): any
	local total = 0
	for _, item in ipairs(list) do
		total += (item.weight or 1)
	end
	local roll = self._r:NextNumber(0, total)
	local acc = 0
	for _, item in ipairs(list) do
		acc += (item.weight or 1)
		if roll <= acc then
			return item
		end
	end
	return list[#list]
end

return Rng
