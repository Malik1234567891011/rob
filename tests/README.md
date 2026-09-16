# Tests

`DevIntegration.server.luau` lives in `ServerScriptService` during development and
drives the **real server API** end to end on playtest: egg → first feed → mutation →
evolution → ability → lineage → offline report → discovery board.

It asserts on **state, not screenshots** — it queries the profile, never the pixels.

`DevSystems.server.luau` covers everything beyond the core loop: world markers, quests,
daily + merchant, gates (solo / co-op / Update-1-locked), sanctuary tiers + garden +
decor, extra eggs + switching, the no-prompt-before-evolution guard, parade signup,
world events, and trials (queue → arena teleport → leave returns you home).
Last run: 43 passed, 0 failed (2026-09-16).

`DevTrials.server.luau` plays Race, Obstacle (every checkpoint, both laps), Smash (breaks
real targets) and Treasure with short timers: queue → arena → score → results → home.
Last run: 22 passed, 0 failed.

`DevEvents.server.luau` runs all eight world events with 8-second durations: each starts,
puts things in the world, ends, cleans up, and logs no errors. Last run: 51 passed, 0 failed.

`DevTiming.server.luau` measures non-negotiable #1 (first feed ≤ 15 s).

All of these are Scripts with `Disabled = true`; enable ONE at a time (they share the
playtest player) and press Play.

Run it: open the place in Studio and press Play. Results print as `[ITEST] PASS/FAIL`
plus the SPEC §65 funnel. Delete the script before publishing.

Two failures it has already caught that nothing else would have:
- an assertion passing for the *wrong reason* (rate-limit fired before the ownership
  check, so "cannot feed unowned item" was never actually testing ownership)
- the empty-bag case masking the rate limiter entirely
