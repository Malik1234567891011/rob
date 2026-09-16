-- devbus.luau — paste into an MCP execute_luau on the SERVER datamodel during Play to drive
-- the running game through src/server/Services/DevHooks.luau.
-- (The MCP thread can't Invoke a BindableFunction, but it can set an attribute.)
local SS = game:GetService("ServerStorage")
local HttpService = game:GetService("HttpService")
local __seq = 0
local function call(hook, ...)
	__seq += 1
	local id = os.clock() * 1000 // 1 + __seq
	SS:SetAttribute("DevCmd", HttpService:JSONEncode({ id = id, hook = hook, args = { ... } }))
	for _ = 1, 200 do
		local raw = SS:GetAttribute("DevResult")
		if raw then
			local r = HttpService:JSONDecode(raw)
			if r.id == id then
				return r.result
			end
		end
		task.wait(0.05)
	end
	return { ok = false, reason = "timeout" }
end
local function J(x)
	return HttpService:JSONEncode(x)
end
-- hooks: state pickEgg(i) give(id,n) feed(id) evolve() setTraits({...}) action(name)
--        mood(name,secs) refresh(reveal) teleport(x,y,z) run("Service.fn", ...)
