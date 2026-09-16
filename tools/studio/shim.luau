-- shim.luau — run the REAL runtime ModuleScripts inside the MCP edit-mode thread.
-- The MCP sandbox cannot require(), but loadstring works, so each module's Source is
-- compiled with an environment whose `script` and `require` point at the live instances.
-- Paste this at the top of an execute_luau call, then use `req(path.to.Module)`.
local __cache = {}
local function req(mod)
	if __cache[mod] ~= nil then
		return __cache[mod]
	end
	local fn, err = loadstring(mod.Source, "=" .. mod:GetFullName())
	if not fn then
		error(err)
	end
	local env = setmetatable({ script = mod, require = req }, { __index = getfenv(0) })
	setfenv(fn, env)
	local result = fn()
	__cache[mod] = result
	return result
end
