# Tests

`DevIntegration.server.luau` lives in `ServerScriptService` during development and
drives the **real server API** end to end on playtest: egg → first feed → mutation →
evolution → ability → lineage → offline report → discovery board.

It asserts on **state, not screenshots** — it queries the profile, never the pixels.

Run it: open the place in Studio and press Play. Results print as `[ITEST] PASS/FAIL`
plus the SPEC §65 funnel. Delete the script before publishing.

Two failures it has already caught that nothing else would have:
- an assertion passing for the *wrong reason* (rate-limit fired before the ownership
  check, so "cannot feed unowned item" was never actually testing ownership)
- the empty-bag case masking the rate limiter entirely
