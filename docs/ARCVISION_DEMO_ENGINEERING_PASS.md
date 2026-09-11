# ArcVision Demo Session — Post-Investigation Engineering Pass

## Status of the UNKNOWN-rate investigation

The investigation into arcvision_demo_01's 42.9% UNKNOWN rate (session `08b2d16fa1404b90`) is
**closed, intentionally, without any threshold or outcome-detector change.** All 3 UNKNOWNs were
traced to exact mechanisms already documented in `docs/VIDEO4_FORENSIC_ANALYSIS.md` (the
`min_occlusion_dip_frac`/`max_crossing_drift_frac_of_rim_radius` gates, and the missing LOAD
dwell-duration gate) — classified as a THRESHOLD/CALIBRATION issue, with the same documented,
unverified regression risk against V1-V3 Video 4's own analysis already established. Per that
investigation's explicit stop condition, nothing there was implemented. **Do not reopen that
investigation or tune those thresholds based on this document.**

This document covers a separate, later engineering pass on two *implementation* inconsistencies
noted (but explicitly not fixed) during that investigation.

## Issue 1 — post-window enrichment evidence discarded

**Confirmed and fixed.** `app/vision/detection/near_hoop_enrichment.py`'s `enrich_near_hoop()`
deliberately re-reads up to `margin_sec` (0.5s) of ball evidence past a shot window's
`end_frame` — its own code comments and the shape of its returned per-shot trajectory make this
unambiguous, not a guess: the range explicitly used to build the returned list is `[win.start_frame,
win.end_frame + margin_frames]`, capped only by the next shot's own start. `app/pipeline/
orchestrator.py`'s `build_shot_from_window()` was then reclamping that returned trajectory to `<=
window.end_frame` before handing it to `detect_outcome()`, silently discarding exactly the margin
`enrich_near_hoop()` existed to fetch. No existing test exercised this path (`tests/
test_integration_synthetic.py`'s calls to `build_shot_from_window()` never passed
`enriched_flight_points`), so nothing was pinned to the old, wrong behavior.

**Fix**: removed the redundant upper-bound reclamp; the enriched branch now trusts
`enrich_near_hoop()`'s own already-correct upper bound instead of re-imposing `window.end_frame`.
No numeric threshold changed — `margin_sec` is untouched.

**Regression test** (`tests/test_integration_synthetic.py::
test_enriched_flight_points_beyond_window_end_frame_reach_outcome_detection`): written first,
confirmed failing against the pre-fix code, confirmed passing after.

**Effect on real footage**: none observed. Re-verified empirically (both before this fix, during
the original investigation, and again after) against arcvision_demo_01 — all 7 outcomes and
confidences are unaffected. This is expected: the fix can only make additional, legitimately-fetched
evidence available; it never removes evidence an already-successful early match relied on.

## Issue 2 — apex_height_norm torso-length computation

**Confirmed and fixed, but does not explain the demo's ~4.4–5.6 values (see below).**
`app/pipeline/orchestrator.py`'s `torso_px_at_release` (used only by `apex_height_norm`) picked a
single side's shoulder/hip landmarks (left, if present) via `_lm_px`, with no visibility check —
independently of `app/biomechanics/metrics.py`'s `torso_points()` (now public; was `_torso_points`),
which bilaterally averages both shoulders/hips and abstains below a visibility floor, already used
for `release_height_norm`. Two different torso-length computations from the same pose frame, one
fragile.

**Fix**: `orchestrator.py` now calls the canonical `torso_points()` and converts its normalized
result to pixel space locally (the only reason it wasn't reused as-is: `apex_px` is pixel-scale,
`torso_points()` returns normalized 0-1 coordinates). No new fitted constant was introduced — the
existing `_VIS_MIN` visibility floor in `metrics.py` is reused, not duplicated. Low-visibility pose
now correctly makes `apex_height_norm` abstain (`None` + `apex_height_unavailable` warning) instead
of computing from an untrustworthy landmark; the pre-existing `torso_length_px_at_release > 1e-6`
guard in `app/analytics/shot_record.py` still protects against divide-by-zero/NaN/inf.

**Regression tests** (`tests/test_integration_synthetic.py`):
- `test_apex_height_norm_uses_bilateral_visibility_gated_torso_not_single_side` — a degenerate,
  near-zero-length single-side landmark pair no longer distorts `apex_height_norm` once the
  bilateral average is used.
- `test_apex_height_norm_abstains_when_torso_visibility_is_too_low` — low visibility on all
  torso landmarks now correctly abstains instead of fabricating a number.

Both written first, confirmed failing pre-fix, confirmed passing post-fix.

**Were the previous ~4.4–5.6 values actually erroneous? No — this was the key finding of this
pass.** Re-running arcvision_demo_01 and real_test_01 through the fixed code changed apex_height_norm
by only ~1-3% (small, expected, from the bilateral-vs-single-side denominator actually differing
slightly) — not the order-of-magnitude correction the original hypothesis predicted. real_test_01
independently shows the same ~2-4x-torso-length pattern for most of its own shots (with one
consistently low outlier, shot 3, both before and after). A systematic pattern recurring similarly
across two different real videos is better explained by genuine physical scale — a real shot's ball
apex height *above the release point* legitimately spans several torso-lengths for footage with a
real arc — than by landmark noise, which would show up as scattered, not systematic. The
single-side/no-visibility-gate fragility this pass fixed is real and independently worth having
fixed (proven via the synthetic degenerate-landmark tests above), but it was not the cause of the
demo's observed apex values.
