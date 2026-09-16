--!strict
-- Shared.Config.Release — which content updates are live (SPEC §76).
--
-- "Have Update 1 ready before launch. A week after momentum: SOMETHING IS IN THE OCEAN."
-- Update 1 ships dark inside the launch build. Flip it on either by raising `updateLevel`
-- (needs a server restart) or by setting `unlockAt[1]` to a UTC unix time: every running
-- server checks once a minute and opens the Ocean live, with no restart and no deploy.

local Release = {}

Release.updateLevel = 0

-- [level] = unix seconds (UTC) at which that update opens itself. nil = manual only.
Release.unlockAt = {
	[1] = nil :: number?,
}

function Release.levelAt(now: number): number
	local level = Release.updateLevel
	for n, at in pairs(Release.unlockAt) do
		if at and now >= at and n > level then
			level = n
		end
	end
	return level
end

return Release
