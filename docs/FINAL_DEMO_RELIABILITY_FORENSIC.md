# Final Demo Reliability — Forensic Root-Cause Analysis (Phase 1–4, no fix implemented)

Read-only. `app/events/outcome_detector.py` and every other production file are unmodified. This
document traces the blind evaluation's 4 UNKNOWN, 3 false-MISSED, 1 false-MADE, and 2 false
-positive results from `docs/FINAL_DEMO_BLIND_EVALUATION.md` (session `29c7e751775e4f20`, which is
**not re-run or altered here**) down to their exact mechanisms, using a new read-only forensic
script (`scripts/forensic_arcvision_demo_final.py`) that reproduces production's real detection
pass and calls the real, unmodified `app.events.outcome_detector` helper functions directly —
never a reimplementation, never the rejected shadow scorer.

---

## Phase 1 — Per-shot forensic trace

### The 4 genuine UNKNOWN shots (truth 1, 2, 3, 6 — all truth MADE)

All four share an identical signature, confirmed at the frame level:

| Truth | Session shot | Reliable pts | Candidates evaluated | Fully-passing candidates exist? | Production found one? |
|---|---|---|---|---|---|
| 1 (0:02) | 1 | 120 (120 detected, 0 interpolated) | 59 | **Yes (6)** | No |
| 2 (0:12) | 3 | 87 | 117 | **Yes (30)** | No |
| 3 (0:27) | 4 | 115 | 123 | **Yes (9)** | No |
| 6 (0:51) | 7 | 121 (121 detected, 0 interpolated) | 39 | **Yes (7)** | No |

For every one of these four, a candidate crossing pair exists — same rim, same tight/wide bands,
same `max_crossing_drift_frac_of_rim_radius`, same `min_occlusion_dip_frac`, same
`max_seconds_through_rim`, all currently-frozen and unchanged — that satisfies drift, occlusion,
and no-deflection simultaneously. Example, shot 1 (truth 1): frame 94→108 (drift 7.1px against a
28.2px allowance, dip 0.744 against a 0.75 cutoff, no deflection) fully qualifies. Production never
tries it.

**Exact mechanism** (`app/events/outcome_detector.py`, MADE loop): for each `a` in
`descent_above_tight`, production computes `b = min(later_below, key=lambda x: x.frame_index)` —
**only the chronologically-earliest qualifying `b`** — and if that single pair fails *any* check
(drift, deflection, or occlusion), it `continue`s to the **next `a`**, never trying a later `b` for
the *same* `a`. Reproducing this exact selection rule against the full candidate set confirms it:
for all four shots, the earliest-`b` pair for the earliest `a` fails (usually on occlusion, by a
narrow margin — e.g. shot 1's actual first-tried pair has dip 0.815 against the 0.75 cutoff), and
production gives up before ever reaching the passing pair that exists a few frames later in the
exact same `descent_below_tight` set it already computed.

### The 3 false-MISSED shots (truth 4, 7, 11)

| Truth | Session shot | Wrong outcome | Confidence | Fully-passing candidate exists? |
|---|---|---|---|---|
| 4 (0:36) | 5 | missed (Case 3, far-descent) | 0.474 | **Yes** — frame 1115→1137, drift 1.0px, dip 0.673 |
| 7 (1:00) | 8 | missed (Case 3, far-descent) | **0.964** | **Yes** — frame 1855→1877, drift 20.5px, dip 0.698 |
| 11 (1:36) | 13 | missed (Case 3, far-descent) | 0.485 | **No** — 0 of 7 candidates pass both checks |

**Shots 4 and 7 share the exact same mechanism as the 4 UNKNOWNs above** — a passing pair exists,
the earliest-`b`-per-`a` search misses it, and *because* the MADE loop then finds nothing, the shot
falls through to MISS Case 3 ("descended well clear of the hoop"), which fires on the ball's real
post-rim motion (rolling/bouncing after landing) and produces a **confident, wrong** MISSED call.
This is precisely the mechanism `docs/VIDEO4_FORENSIC_ANALYSIS.md` Part B already documented for
V4's own ≈81s case, in that document's own words: *"after the MADE check rejects the crossing...
the ball's continued, real post-rim motion... falls into MISS Case 3... converting what should at
worst have been UNKNOWN into a confidently wrong MISSED call."* Shot 7's 0.964-confidence wrong
call is the same failure, just with more far-descent points (12) feeding Case 3's confidence
formula (`0.4 + 0.05 * len(far_descent)`) than V4's case had.

**Shot 11 (Shot 11 in the ground truth, the far showcase shot) is different.** No fully-passing
candidate exists even under exhaustive search — the single `a` tried (frame 2919) shows drift
*monotonically increasing* with each later candidate `b` (16.5px → 72.1px as `b` moves later),
and occlusion only appears once drift has already grown too large to matter. This looks like a
genuinely harder case tied to the shot's own greater distance/angle (a farther, more oblique shot
plausibly produces more true apparent horizontal drift per unit of real accuracy than the closer
shots this video and its thresholds were otherwise implicitly exercised against) — not something
the search-completeness fix below would resolve. It still falls to the same Case 3 mechanism as
shots 4 and 7, converting a genuine make into a wrong, lower-confidence MISSED call. `warnings`
also shows `video_ended_during_flight` (release at 96.1s of a 98.5s file) — the window closed
because the recording ended, not from a natural resolution, though this by itself did not prevent
data collection here (33 detected points, 1.0 ball-track quality).

### The 1 false-MADE shot (truth 9, 1:19, genuine MISS called MADE at 0.582 confidence)

Different mechanism entirely, and **not explained by the search-completeness bug** — production's
existing (even if incomplete) search correctly reaches a technically-passing pair here (frame
2446→2463, drift 21.4px, dip 0.538), so this is not a "missed evidence" case.

What's notable: **many consecutive `a` frames (2442, 2444, 2446, 2448, 2450, 2452...) all share the
identical `b=2463`** — meaning the ball spent roughly 10+ consecutive frames (~1/3 second at this
video's analysis rate) hovering within the tight band directly above the rim before finally
dropping below it. A clean, genuine pass-through does not typically show the ball lingering this
long directly over the rim before crossing — this pattern (sustained hover, then drop) is much
more consistent with **the ball resting/rattling on the rim itself before ultimately rejecting
out** than with a fluid pass-through. Also notable: this shot's `rim_entry_speed_mps_estimate` is
**0.75 m/s** — the slowest of any crossing in this session (the two genuinely correct MADE calls,
truth 9 and truth 10, show 2.08 m/s and a separate value; a real ball entering/passing a rim under
gravity at typical shot speeds is not usually moving at under 1 m/s). This estimate is already
computed by the pipeline for every MADE candidate but is **not currently used anywhere in the
decision** — it is recorded as informational evidence only.

### The 2 false-positive shot-window events

| Time | Session shot | Trigger | Load→Upward gap |
|---|---|---|---|
| 11.1s | shot 2 | primary (ball-hand proximity) | 4 frames (~0.13s) |
| 87.7s | shot 11 | primary (ball-hand proximity) | 1 frame (~0.03s) |

Both are extremely sparse (0 candidate pairs ever reached — the trajectory never even re-entered
the tight band), both sit roughly 1–2 seconds *before* a genuine, much richer shot (truth 2 and
truth 10 respectively), and both show a near-instantaneous LOAD→UPWARD transition. **This is the
exact same mechanism `docs/VIDEO4_FORENSIC_ANALYSIS.md` Part A already documented and named**:
*"the LOAD→UPWARD transition has no minimum dwell/hold-duration requirement... A dribble bounce's
brief pass through the proximity zone satisfies the exact same instantaneous-crossing test a real
catch-and-hold does."* This is now confirmed recurring on a **second, independent** video —
strong evidence it is a genuine, generalizable gap, not noise specific to one clip. That same V4
document already concluded a fix here needs **a new fitted numeric threshold** (how many frames
counts as "dwelled") — this analysis does not overturn that conclusion, and per this task's rules
against introducing new fitted constants, no fix is proposed for this here.

---

## Phase 2 — Shared root causes, grouped and classified

| Failure | Shots affected | Category | Classification |
|---|---|---|---|
| **MADE-candidate search tries only the earliest `b` per `a`, abandons `a` on any single check failure** | Truth 1, 2, 3, 6 (UNKNOWN) + Truth 4, 7 (false MISSED) — **6 of 11 truth shots** | E. crossing-pair selection | **BUG** — an algorithmic completeness gap, not a threshold or design tradeoff. The same unchanged gates already accept the pairs that exist; the search simply never finds them. |
| MISS Case 3 uses an apex-relative 2.0s window, far looser than the ~0.75s scale everything else in the MADE/deflection logic uses, so it can fire on real post-rim motion after a make | Truth 4, 7, 11 (as a *consequence* of the bug above, plus independently for Truth 11) | H. make/miss evidence aggregation | **ARCHITECTURAL WEAKNESS** — already documented on V4; a real design gap, but distinct from, and secondary to, the search bug above (the search bug alone already explains 2 of these 3 shots). |
| Rim-rattle produces a technically-passing but physically-implausible crossing pair (long hover directly over the rim, unusually slow estimated entry speed) | Truth 9 (false MADE) | E. crossing-pair selection (a different sub-issue: pair *plausibility*, not pair *discovery*) | **ARCHITECTURAL WEAKNESS** — a real gap (an already-computed physical signal, entry speed, goes unused), but independent of the search-completeness bug and not affecting any other shot in this session. |
| No minimum LOAD dwell-duration before the upward transition is accepted | The 2 false-positive windows | B. duplicate/retrigger behavior | **ARCHITECTURAL WEAKNESS, already documented on V4 (Part A), confirmed recurring here.** Known fix requires a new fitted threshold — explicitly out of scope under this task's rules. |
| Shot 11's own inherently larger true drift (farther, more oblique shot) | Truth 11 only | D. rim-relative geometry / possibly threshold scaling with distance | **THRESHOLD SENSITIVITY at best, possibly UNAVOIDABLE MONOCULAR AMBIGUITY** — a fixed-radius-based drift tolerance may not be the right invariant across very different shot distances; not enough evidence from one shot to say more. |
| Video ending during Shot 11's flight | Truth 11 | I. recording ending before resolution | Present but **not the deciding factor** here — this shot still had strong ball-track data (33 detected points, quality 1.0); the wrong outcome traces to the drift/Case-3 issues above, not to running out of frames. |

**Dominant failure, by a wide margin: the MADE-candidate search-completeness bug.** It is the sole
or contributing cause for 6 of the 8 wrong/unresolved matched shots, and it is a genuine
implementation bug — not a fitted threshold, not a redesign, not a monocular-ambiguity tradeoff.

---

## Phase 3 — Proposed fix (not implemented)

**Make the MADE-candidate search exhaustive: for each shot, evaluate every chronologically-valid
`(a, b)` pair (not just the earliest `b` per `a`), and if more than one pair passes all of the
existing, unchanged hard gates (drift, no-deflection, occlusion), select... the earliest-by-`a`
pair among the passing set** (matching today's implicit tie-breaking philosophy — "the first
genuine crossing" — rather than introducing any new scoring/weighting logic).

Concretely, in `app/events/outcome_detector.py`'s MADE loop: instead of computing a single
`b = min(later_below, ...)` per `a` and `continue`-ing to the next `a` on any failure, iterate over
**all** `later_below` candidates for the current `a` (or, equivalently, over all `(a, b)` pairs in
ascending `a` order), and take the first one — across the *entire* candidate set — that passes all
three existing checks. No threshold changes. No new checks. No new constants.

**Why this is the smallest general fix for the dominant failure**: it does not touch what counts
as valid evidence — it only ensures evidence that already qualifies under today's frozen thresholds
is not missed due to an accident of which `b` happens to sort earliest by frame index. It requires
zero new fitted constants and changes no existing one.

**What it does not fix, on purpose** (explicitly out of scope for this proposal, reported
separately per Phase 2): the false-MADE rattle case (truth 9), Shot 11's own far-shot drift/Case-3
issue, and the two false-positive shot windows. Bundling any of those into this same change would
violate the "smallest general fix" instruction — each has a different mechanism and would need its
own separate justification (and, for the false-positive windows, a new fitted constant that this
task's rules do not authorize tonight).

### Why this avoids the rejected shadow scorer's failure mode

The shadow-scorer experiment (`docs/...` shadow-mode task, rejected) failed because it turned
drift and occlusion from **hard vetoes into weighted, combinable scores** — meaning a pair with
*weak* drift and occlusion evidence could still cross the acceptance bar if other factors (approach
count, source quality, gap tightness) compensated. That is what let V4's false-MADE-rate quintuple
(1→5): pairs that never would have passed either individual gate got admitted by summing
partial credit.

This proposal does the opposite: **every candidate pair still must pass the exact same two hard
gates, unweighted, exactly as today.** It changes *only* which pairs get a chance to be checked —
not what "passing" means. A pair that would be rejected today is still rejected under this
proposal; the only behavioral difference is that a pair which already, fully, satisfies today's
bar is no longer skipped because of frame-ordering bad luck. This is a strict subset relationship
in the safe direction: the set of "pairs a shot can be confirmed MADE from" only grows to include
pairs that were always valid, never to include pairs that are currently invalid.

---

## Phase 4 — Regression plan (tests to add *before* implementing, not yet written)

All as synthetic/fixture trajectories (in the style of `tests/test_integration_synthetic.py` /
direct `detect_outcome()` unit calls), **not** derived from this video's own timestamps:

1. **Duplicate event near one genuine shot** (documents the false-positive mechanism; not fixed by
   this proposal — a fixture with a 1–4 frame LOAD→UPWARD gap immediately preceding a normal load
   sequence, asserting today's behavior so a future dwell-duration fix has a documented before/after).
2. **Made shot with a noisy/rattling rim interaction** (documents the false-MADE mechanism; a
   synthetic trajectory with the ball hovering across many consecutive frames in the tight band
   above the rim before a single late drop below — asserting today's MADE call, as a baseline for
   a future plausibility-check fix, not resolved by this proposal).
3. **A miss that passes near/through the projected rim region at a different depth** — the classic
   monocular-ambiguity negative case: a clean, small-drift, occlusion-free crossing that is a *real*
   miss (airball at the rim's own apparent position but a different true depth). Must assert this
   **still correctly returns UNKNOWN/MISS, never MADE**, both before and after the fix — this is
   the key regression guard proving exhaustive search doesn't admit evidence the current gates
   would reject.
4. **High-confidence false-MISSED prevention** (the core fix target): a synthetic trajectory
   reproducing shots 1/3/4/7's exact shape — an early `(a, earliest-b)` pair that fails occlusion by
   a narrow margin, with a *later*, fully-passing `(a, later-b)` pair a few frames after. Assert
   **UNKNOWN or wrong-MISSED today, MADE after the fix.**
5. **High-confidence false-MADE prevention** (regression guard for the fix, not a new capability):
   assert that shots with *no* fully-passing pair anywhere in the exhaustive set still correctly
   return UNKNOWN/MISS after the fix — exhaustiveness must never manufacture a passing pair that
   doesn't already exist under the unchanged gates.
6. **End-of-video genuine shot**: a trajectory that is cut short by the synthetic "video" ending
   shortly after a real crossing exists — assert the shot still resolves correctly if the passing
   evidence is present before the cutoff (this proposal doesn't change end-of-video handling per se,
   but should be verified not to regress it).
7. **UNKNOWN only when evidence is genuinely insufficient**: a trajectory with too few
   descent/reliable points to reason about at all (below `min_descent_points_to_attempt`) — assert
   UNKNOWN both before and after, proving the fix doesn't paper over genuinely thin data.

All 218 existing tests must continue passing unmodified — none of them exercise the multi-candidate
search path differently than today (per the shadow-experiment task's own finding, no existing test
even passes `enriched_flight_points` with more than one viable candidate pair), so no existing test
is expected to change behavior.

---

## Files that would need modification (if implemented — not done this turn)

- `app/events/outcome_detector.py` — the MADE-candidate search loop only. No other function, no
  config default, no other file.
- `tests/test_integration_synthetic.py` (or a new `tests/test_outcome_detector.py`) — the 7
  regression tests above, added first.

## Risk to V1/V2/V3/V4

Structurally lower risk than the rejected shadow scorer (no gate is weakened), but **not zero** —
it has not been tested. The one concrete open question: could exhaustive search surface a
previously-unfound *passing* pair on a shot in V1–V4 that is *currently* correctly UNKNOWN or
MISSED, converting it to a new MADE? This can only happen if such a fully-passing pair already
exists in those videos' own data (exactly as it does here) — plausible, not yet verified. Required
before adoption, exactly as `docs/FINAL_DEMO_RELIABILITY_FORENSIC.md`'s Phase 4 tests are meant to
catch: re-run V1, V2, V3, and frozen V4 under the changed code and confirm zero new false-confident
calls, with special attention to V4's own already-known false-MADE (~70s) case, which must not
newly worsen.

## Estimated implementation complexity: **LOW**

The change is localized to one loop in one function, introduces no new state, no new config
fields, and no new dependencies. The regression-test authoring (7 fixtures) is the larger share of
the work, not the fix itself.

---

# Summary

**A. Root cause of each UNKNOWN** (truth 1, 2, 3, 6): in all four, a fully-passing MADE crossing
pair exists in the already-collected data; production's search only tries the earliest `b` per `a`
and gives up on the first failure, never finding it.

**B. Root cause of each wrong MISSED**: truth 4 and truth 7 — same search-completeness bug as A,
compounded by MISS Case 3 then firing on real post-rim motion (matches V4 Part B's already
-documented ≈81s mechanism exactly). Truth 11 — no passing pair exists even under exhaustive
search; falls to the same Case 3 mechanism, likely related to this shot's greater distance
producing larger true drift.

**C. Root cause of the false MADE** (truth 9): a separate, independent mechanism — a real,
technically-passing crossing pair exists, but the ball's sustained ~10-frame hover directly above
the rim before dropping, plus an unusually low estimated entry speed (0.75 m/s vs ~2 m/s for
genuine makes), is consistent with a rim rattle rather than a clean pass-through. Not caused by,
and not fixed by, the search-completeness bug.

**D. Root cause of each false-positive shot event**: both share a near-instantaneous (1–4 frame)
LOAD→UPWARD transition — the same "no minimum dwell duration" gap already documented on V4 Part A,
now confirmed on a second video.

**E. Shared dominant failure**: the MADE-candidate search-completeness bug — explains or
contributes to 6 of 11 truth shots' wrong/unresolved outcomes.

**F. Is there an actual implementation bug?** **Yes** — the earliest-`b`-per-`a` search with
give-up-on-first-failure is a genuine algorithmic completeness bug, not a threshold or design
tradeoff.

**G. Smallest general fix recommended**: make the MADE-candidate search exhaustive over all
`(a, b)` pairs instead of one `b` per `a`; keep every existing gate and constant unchanged; select
the first pair (in ascending `a` order) that passes all of them.

**H. Why it should generalize**: it adds no new video-specific logic, no new constants, and only
recovers evidence that already, fully satisfies today's frozen criteria — the same criteria
already validated on V1–V4's own correct calls.

**I. Why it avoids the rejected shadow scorer's failure mode**: that experiment weakened the gates
themselves (weighted/combinable evidence); this proposal leaves the gates as hard, unweighted
vetoes and only searches more thoroughly for pairs that already fully clear them — it cannot admit
evidence the current gates would reject.

**J. Tests to add before implementation**: the 7 synthetic-fixture tests in Phase 4 above,
authored first, shown failing under current behavior for the relevant cases.

**K. Files that would need modification**: `app/events/outcome_detector.py` (MADE loop only) plus
new/extended test files. Nothing else.

**L. Risk to V1/V2/V3/V4**: low but unverified — must re-run all four under the changed code before
adoption and confirm zero new false-confident calls, especially checking V4's known ~70s false
-MADE doesn't worsen.

**M. Estimated implementation complexity: LOW.**

**N. Recommendation: IMPLEMENT** — but only after Phase 4's regression tests are written and shown
failing under current behavior, and only with the required V1–V4 re-verification run immediately
after, per this document's own risk section. Not implemented in this turn, per instruction.
