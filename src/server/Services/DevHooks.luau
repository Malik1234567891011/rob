--!strict
-- DevHooks — a Studio-only remote control for the RUNNING server, so tests and the MCP can
-- drive real game state (the MCP's own Luau thread cannot require the live modules, and a
-- loadstring copy of a module would not share state with the running game).
--
-- From an MCP execute_luau on the Server datamodel:
--   game.ServerStorage.DevHooks:Invoke("give", "Apple", 3)
--
-- Every hook returns a plain table so results can be read back as text.
-- Never active outside Studio.

local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local Players = game:GetService("Players")

local DevHooks = {}

function DevHooks.start(services)
	if not RunService:IsStudio() then
		return
	end
	local fn = Instance.new("BindableFunction")
	fn.Name = "DevHooks"
	fn.Parent = ServerStorage

	local function me(): Player?
		return Players:GetPlayers()[1]
	end

	local hooks = {}

	hooks.state = function()
		local p = me()
		if not p then
			return { ok = false, reason = "no player" }
		end
		local profile = services.PlayerDataService.get(p)
		local genome = services.PlayerDataService.activeCreature(p)
		local model = services.CreatureService.get(p)
		local muts = {}
		for id in pairs(genome and genome.mutations or {}) do
			table.insert(muts, id)
		end
		return {
			ok = true,
			coins = profile and profile.coins,
			essence = profile and profile.essence,
			ftueStep = profile and profile.ftueStep,
			stage = genome and genome.stage,
			fed = genome and genome.fedCount,
			family = genome and genome.bodyFamily,
			parts = genome and genome.parts,
			mutations = muts,
			model = model and model:GetFullName(),
			modelPos = model and model.PrimaryPart and tostring(model.PrimaryPart.Position),
			playerPos = p.Character and p.Character.PrimaryPart and tostring(p.Character.PrimaryPart.Position),
			mood = model and model:GetAttribute("Mood"),
		}
	end

	hooks.pickEgg = function(i)
		return services.FtueService.pickEgg(me(), i or 1)
	end

	hooks.give = function(id, n)
		local profile = services.PlayerDataService.get(me())
		profile.inventory[id] = (profile.inventory[id] or 0) + (n or 1)
		services.PlayerDataService.sync(me())
		return { ok = true, have = profile.inventory[id] }
	end

	hooks.feed = function(id)
		local p = me()
		local profile = services.PlayerDataService.get(p)
		if (profile.inventory[id] or 0) <= 0 then
			profile.inventory[id] = 1
		end
		return services.FeedingService.feed(p, id)
	end

	hooks.evolve = function()
		local g = services.PlayerDataService.activeCreature(me())
		if g then
			local Progression = require(game.ReplicatedStorage.Shared.Config.Progression)
			local need = Progression.stage(g.stage).feedsToNext
			if need then
				g.fedCount = math.max(g.fedCount, need)
			end
		end
		return services.FeedingService.evolve(me())
	end

	hooks.setTraits = function(traits)
		local g = services.PlayerDataService.activeCreature(me())
		for k, v in pairs(traits) do
			g.traits[k] = v
		end
		return { ok = true }
	end

	hooks.action = function(action)
		services.CreatureService.actionFor(me(), action)
		return { ok = true }
	end

	hooks.mood = function(mood, seconds)
		services.CreatureService.setMood(me(), mood, seconds)
		return { ok = true }
	end

	hooks.refresh = function(reveal)
		services.CreatureService.refresh(me(), reveal)
		return { ok = true }
	end

	hooks.teleport = function(x, y, z)
		local char = me().Character
		if char then
			char:PivotTo(CFrame.new(x, y, z))
		end
		return { ok = true }
	end

	hooks.run = function(name, ...)
		-- escape hatch: call any service function by "Service.fn"
		local svc, f = string.match(name, "^(%w+)%.(%w+)$")
		local s = svc and services[svc]
		if not s or type(s[f]) ~= "function" then
			return { ok = false, reason = "no such function " .. tostring(name) }
		end
		-- "$me" in the args becomes the playtest Player (JSON can't carry an Instance)
		local args = table.pack(...)
		for i = 1, args.n do
			if args[i] == "$me" then
				args[i] = me()
			end
		end
		return { ok = true, result = s[f](table.unpack(args, 1, args.n)) }
	end

	local function dispatch(name, ...)
		local h = hooks[name]
		if not h then
			return { ok = false, reason = "unknown hook " .. tostring(name) }
		end
		local ok, result = pcall(h, ...)
		if not ok then
			return { ok = false, reason = tostring(result) }
		end
		return result
	end
	fn.OnInvoke = dispatch

	-- The MCP thread is not allowed to Invoke a BindableFunction, but it may set an
	-- attribute. So: ServerStorage.DevCmd = '{"id":1,"hook":"give","args":["Apple",3]}'
	-- and the answer appears in ServerStorage.DevResult as '{"id":1,"result":...}'.
	local HttpService = game:GetService("HttpService")
	ServerStorage:GetAttributeChangedSignal("DevCmd"):Connect(function()
		local raw = ServerStorage:GetAttribute("DevCmd")
		if type(raw) ~= "string" or raw == "" then
			return
		end
		local ok, cmd = pcall(HttpService.JSONDecode, HttpService, raw)
		if not ok or type(cmd) ~= "table" then
			ServerStorage:SetAttribute("DevResult", HttpService:JSONEncode({ id = -1, result = { ok = false, reason = "bad json" } }))
			return
		end
		task.spawn(function()
			local result = dispatch(cmd.hook, table.unpack(cmd.args or {}))
			local encoded
			local okEnc = pcall(function()
				encoded = HttpService:JSONEncode({ id = cmd.id, result = result })
			end)
			if not okEnc then
				encoded = HttpService:JSONEncode({ id = cmd.id, result = { ok = false, reason = "unencodable result" } })
			end
			ServerStorage:SetAttribute("DevResult", encoded)
		end)
	end)
	print("[DevHooks] ready (Studio only)")
end

return DevHooks
