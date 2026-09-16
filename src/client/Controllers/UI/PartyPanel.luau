--!strict
-- PartyPanel — SPEC §20, §53. Friends change what's POSSIBLE: party members' abilities
-- combine at co-op gates. Invite anyone on the server; friends are listed first.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))

local PartyPanel = {}
PartyPanel.title = "Friends & Party"
PartyPanel.emoji = "👥"
PartyPanel.height = 0.58

function PartyPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local members = {}
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 8)
	Theme.pad(scroll, 2, 4)

	local friendCache: { [number]: boolean } = {}
	local function isFriend(p: Player): boolean
		if friendCache[p.UserId] == nil then
			local ok, v = pcall(ctx.player.IsFriendsWith, ctx.player, p.UserId)
			friendCache[p.UserId] = ok and v or false
		end
		return friendCache[p.UserId]
	end

	local refresh
	refresh = function()
		Theme.clear(scroll)
		Theme.text({ text = "Team up (2–4). Your monsters' abilities COMBINE at special gates — a Giant and an Electric monster can open what neither could alone.",
			textSize = 15, color = Theme.MUTED, parent = scroll, order = 0, auto = true })
		Theme.text({ text = "YOUR PARTY", font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = 1 })
		if #members == 0 then
			Theme.text({ text = "Just you (and your monster).", textSize = 15, parent = scroll, order = 2, auto = true })
		else
			for i, m in ipairs(members) do
				Theme.text({ text = "🐾 " .. m.name, font = Theme.BOLD, textSize = 17, parent = scroll, order = 2 + i, auto = true })
			end
			Theme.button({ label = "Leave party", size = UDim2.fromOffset(160, 46), color = Theme.PAPER2, textSize = 16, parent = scroll, order = 20,
				onClick = function()
					Net.func("PartyLeave"):InvokeServer()
				end })
		end
		Theme.text({ text = "ON THIS SERVER", font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = scroll, order = 30 })
		local others = {}
		for _, p in ipairs(Players:GetPlayers()) do
			if p ~= ctx.player then
				table.insert(others, p)
			end
		end
		table.sort(others, function(a, b)
			local fa, fb = isFriend(a), isFriend(b)
			if fa ~= fb then
				return fa
			end
			return a.DisplayName < b.DisplayName
		end)
		if #others == 0 then
			Theme.text({ text = "Nobody else here yet.", textSize = 15, parent = scroll, order = 31, auto = true })
		end
		for i, p in ipairs(others) do
			local row = Theme.card(scroll, Theme.PAPER2, 14)
			row.Size = UDim2.new(1, -8, 0, 56)
			row.LayoutOrder = 31 + i
			Theme.text({ text = (isFriend(p) and "⭐ " or "") .. p.DisplayName, font = Theme.BOLD, textSize = 17,
				pos = UDim2.fromOffset(14, 0), size = UDim2.new(1, -150, 1, 0), parent = row })
			Theme.button({ label = "Invite", size = UDim2.fromOffset(110, 44), pos = UDim2.new(1, -122, 0, 4), color = Theme.accent.party, textSize = 16, parent = row,
				onClick = function()
					local r = Net.func("PartyInviteSend"):InvokeServer(p.UserId)
					ctx.toast({ title = r and r.ok and "INVITE SENT" or "CAN'T INVITE", label = r and r.ok and ("👋 " .. p.DisplayName) or tostring(r and r.reason), color = 0x6EA8FF })
				end })
		end
	end

	Net.event("PartyState").OnClientEvent:Connect(function(payload)
		members = payload.members or {}
		refresh()
	end)

	return { refresh = refresh }
end

return PartyPanel
