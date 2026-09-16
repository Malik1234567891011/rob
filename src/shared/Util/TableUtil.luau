--!strict
-- Shared.Util.TableUtil — small helpers, no dependencies.
local TableUtil = {}

function TableUtil.deepCopy(t: any): any
	if type(t) ~= "table" then
		return t
	end
	local out = {}
	for k, v in pairs(t) do
		out[k] = TableUtil.deepCopy(v)
	end
	return out
end

function TableUtil.count(t: { [any]: any }): number
	local n = 0
	for _ in pairs(t) do
		n += 1
	end
	return n
end

function TableUtil.keys(t: { [any]: any }): { any }
	local out = {}
	for k in pairs(t) do
		table.insert(out, k)
	end
	return out
end

-- Sorted top-N of a {[string]: number} map. Used wherever we need
-- "what is this creature mostly made of" (SPEC §24 inspection, §5 visible change).
function TableUtil.topN(map: { [string]: number }, n: number): { { key: string, value: number } }
	local list = {}
	for k, v in pairs(map) do
		table.insert(list, { key = k, value = v })
	end
	table.sort(list, function(a, b)
		if a.value == b.value then
			return a.key < b.key
		end
		return a.value > b.value
	end)
	local out = {}
	for i = 1, math.min(n, #list) do
		table.insert(out, list[i])
	end
	return out
end

function TableUtil.addInto(target: { [string]: number }, source: { [string]: number }, scale: number?)
	local s = scale or 1
	for k, v in pairs(source) do
		target[k] = (target[k] or 0) + v * s
	end
end

-- Pack/unpack Color3 <-> 24-bit int. Keeps genomes small in DataStore (SPEC §71).
function TableUtil.packColor(c: Color3): number
	return math.floor(c.R * 255) * 65536 + math.floor(c.G * 255) * 256 + math.floor(c.B * 255)
end

function TableUtil.unpackColor(n: number): Color3
	local r = math.floor(n / 65536) % 256
	local g = math.floor(n / 256) % 256
	local b = n % 256
	return Color3.fromRGB(r, g, b)
end

return TableUtil
