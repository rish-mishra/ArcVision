# Video 4 Forensic Failure Analysis (read-only — no fixes applied)

Video 4 failed its pre-committed evaluation (`docs/VIDEO4_EVALUATION_PROTOCOL.md`, Part D). This
is a read-only, frame-by-frame causal investigation of *why*, requested before any decision to
change the frozen architecture. Nothing in this document was implemented: no thresholds, code,
config, or model weights were touched, and Video 4's evaluation result stands as recorded and
preserved. Two additional diagnostic artifacts were produced, both new read-only tooling that only
calls existing production code with its existing settings — no existing file was edited:
`scripts/eval_coverage_v4.py` and a `scripts/shot_timeline_debug.py` run
(`data/diagnostics/real_test_04_shot_timeline/`, full per-frame FSM trace).

---

## Part A — The five false-positive shot detections

### Summary

| Detected release | FSM trigger | LOAD→UPWARD gap | Raw ball-trace signature |
|---|---|---|---|
| 22.5s | primary (ball-hand proximity) | 1 frame (0.033s) | smooth dribble arc, ~40-70px translation per bounce |
| 57.7s | primary (ball-hand proximity) | 1 frame (0.033s) | smooth dribble arc |
| 77.5s | primary (ball-hand proximity) | 3 frames (0.1s) | ball translates ~330px in x over 4.7s while bouncing 3-4× — walking-while-dribbling |
| 109.7s | primary (ball-hand proximity) | 1 frame (0.033s) | ball-hand distance and vertical velocity oscillate in a rapid sawtooth immediately before the trigger — raw tracking instability, not smooth motion |
| 132.9s | fallback (upward-flight-only) | 2 frames (0.067s) | ball 2.0-2.5 torso-lengths from the hand at the moment the fallback trigger actually fires; same sawtooth instability as above beforehand |

### The shared mechanism (shots at 22.5s, 57.7s, 77.5s)

Pulling `app/events/shot_state_machine.py`'s own per-frame trace (`ball_hand_dist_norm`,
`ball_vertical_velocity_norm`, `knee_angle_deg`) around each LOAD entry:

- In all three, `ball_hand_dist_norm` decreases smoothly toward the `hand_proximity_threshold_norm`
  crossing, and the LOAD→UPWARD transition fires **1-3 analysis frames (0.03-0.1s) later** — i.e.
  the ball does not dwell near the hand at all; it is caught by the proximity check in the same
  instant it is already carrying upward velocity from a bounce. A real shot's LOAD phase (per
  `docs/METHODOLOGY.md`'s own description: "the shooter gathers, sets, dips knees") should show a
  real hold before the release burst; these three show none.
- `_genuine_knee_dip_nearby` (the knee-flexion gate) still passes, because the check only requires
  *some* monotonic dip of at least `load_knee_flexion_drop_deg` somewhere in the lookback window —
  it does not require the dip to be large. The actual dips measured here were 11-24°, consistent
  with ordinary rhythmic knee flex during dribbling, not a real shooting load.
- `_shooter_was_stationary_nearby` (the hip-translation gate, added specifically for the "dribble
  while walking" failure documented in `docs/METHODOLOGY.md`) could not be directly re-verified
  frame-by-frame here — `hip_x_norm` is not one of the fields `ShotStateMachine`'s `TraceEvent`
  records, and adding it would mean editing a production file, which this investigation does not
  do. The raw ball-position data (already gathered for the Part D evaluation) does show one of
  these three (77.5s) translating ~330px horizontally over 4.7s while bouncing — consistent with
  walking — but the other two (22.5s, 57.7s) show a shorter, more localized dribble arc where a
  walking interpretation is less certain from ball position alone.

**Conclusion for this group: one shared architectural gap.** The LOAD→UPWARD transition has no
minimum dwell/hold-duration requirement — nothing currently checks that the ball actually stays
near the hand for a nontrivial span before the upward burst is accepted as a release. A dribble
bounce's brief pass through the proximity zone satisfies the exact same instantaneous-crossing
test a real catch-and-hold does.

### The distinct sub-pattern (shots at 109.7s and 132.9s)

Both show a different, additional signature: immediately before the trigger, `ball_hand_dist_norm`
and `ball_vertical_velocity_norm` swing through a rapid sawtooth (e.g. distance alternating
0.39 → 2.28 → 0.59 → 2.02 → 0.50... and velocity alternating -44 → +39 → -46 → +40... frame to
frame) rather than the smooth, continuous change a real ball in flight produces. This matches the
same interleaved, two-candidate-position artifact independently observed in the raw
`frame_level.csv` ball x/y trace for these two windows during the Part D investigation — most
consistent with the ball tracker alternating between two competing position candidates for a
stretch of frames, not a single coherent physical motion. The 132.9s case additionally goes
through the **fallback** trigger, firing while the ball is 2.0-2.5 torso-lengths from the hand —
reproducing the exact "sustained upward flight with no real hand-proximity evidence" failure mode
already named in `docs/METHODOLOGY.md`, just from a different noise source than the rim-rebound
case that motivated it originally.

**Conclusion for this group:** a contributing factor (tracking-quality noise), not a new
architectural gap in the FSM itself — the FSM is behaving exactly as designed given noisy input;
the noise's source (why the tracker's competing-candidate resolution degrades at these two
specific moments) was not further investigated, since that's a tracking/detector-layer question
distinct from FSM-forensic scope requested here.

### Do these five share ONE mechanism, or need separate special cases?

**Mostly one.** Four of five (all but 109.7s) are explained by the same missing dwell-duration
gate; the fifth (109.7s) and part of the fourth's precondition (132.9s) additionally involve raw
tracking noise the FSM has no way to filter on its own. A single new gate (a minimum number of
consecutive near-hand frames before the upward transition is accepted) is conceptually one fix,
not five special cases — but note it would still need a **new fitted numeric threshold** (how many
frames counts as "dwelled"), which is a real caveat for the final verdict below.

### Regression risk against V1-V3

`docs/METHODOLOGY.md`'s own account of the coherent-evidence gates' validation says they were
added and confirmed against a real video achieving 7/7 correct shots with the two previously-known
false positives (a rim rebound, a walking dribble) resolved — which by construction means V1's own
real shots' LOAD phases were NOT single-frame passthroughs (otherwise the existing knee-dip/
stationary gates could never have told them apart from the false positives they were built to
reject). This is reasonable, if indirect, evidence that a dwell-duration requirement would likely
be safe for V1-V3's own genuine shots. It is **not proof** — this investigation did not re-run the
timeline trace against V1/V2/V3 to directly measure their real shots' own LOAD→UPWARD gaps (doing
so was out of scope for a Video-4-focused forensic pass, and would mean picking a threshold value
empirically from exactly the kind of multi-video threshold-fitting this project has deliberately
avoided). The honest position: plausible low regression risk, not verified.

---

## Part B — Outcome-detector failures (10 shots: 4 wrong calls + 6 UNKNOWN)

`app/events/outcome_detector.py`'s MADE check requires, in order: an above-rim point inside a
*tight* horizontal band, a later below-rim point also inside the tight band within
`max_seconds_through_rim` (0.75s), a crossing-pair horizontal drift no more than
`max_crossing_drift_frac_of_rim_radius` (1.0 × rim radius ≈ 30px here), nothing observed between
them outside the wider zone, **and** a confidence dip during the crossing of at least
`min_occlusion_dip_frac` (dip to ≤75% of the crossing's bracketing confidence) — the code's own
proxy for "the ball was actually occluded by the rim/net, not just visually near it." Both of the
numeric gates (drift fraction, occlusion-dip fraction) are explicitly calibrated in the code's own
comments from specific percentages observed on other footage ("four confirmed makes... dropping to
36-73%... two false positives... never below 77%").

### The three genuine makes called MISSED

All three (release ≈27s, ≈81s, ≈91s) show, in the raw `frame_level.csv` ball trace, a clean,
high-confidence, physically unambiguous descent through the rim's horizontal center (drift of
0.5-11px between the last above-rim point and first below-rim point — far inside the 30px
allowance) — by eye, an obvious make in every case. Each still failed the MADE check, for **two
different specific gate failures**:

- **≈27s and ≈81s: occlusion-dip failure.** The crossing-span confidence never dips below ~84-87%
  of its bracketing value (dip_ratio 0.839 and 0.872 respectively, both above the 0.75 cutoff) —
  the ball stays confidently, continuously detected the entire time it visually crosses the rim's
  vertical span, with no confidence drop and no tracking gap at all.
- **≈91s: drift failure.** The one qualifying above-rim point drifts 55px to the first below-rim
  point — nearly double the 30px allowance — despite both points and everything between them
  sitting comfortably inside the *wide* zone the whole time (a genuinely centered, if slightly
  angled-looking in 2D, descent).

For ≈81s specifically, the failure compounds: after the MADE check rejects the crossing (for lack
of occlusion), the ball's continued, real post-rim motion (rolling/bouncing away after landing)
falls into MISS Case 3 ("descended well clear of the hoop") within its time window, converting what
should at worst have been UNKNOWN into a **confidently wrong** MISSED call.

A fourth genuine make (≈177s) shows the same drift-based rejection (88.7px drift, roughly 3× the
allowance) but in this instance the ball's post-rim motion happens to fall *outside* the
2-second apex-relative window MISS Case 3 checks, so it correctly falls through to **UNKNOWN**
rather than a wrong call — the same underlying gate failure, just a different, safer landing spot
this time, essentially by timing coincidence.

### The one genuine miss called MADE (contrast case)

The single false MADE call (release ≈70s) is a different kind of case: the ball's trace shows a
real confidence dip during its near-rim crossing (dip to ~50% of bracketing confidence) alongside
small drift (24.6px) — every gate the three makes above failed, this one passes. Ground truth says
it was a miss (a near-rim graze/rattle-out is the most plausible read of the data: partial
occlusion by the rim itself during a shot that came very close but did not go through). This
matches the code's own documented, acknowledged limitation almost exactly — *"a single static
camera cannot tell a ball that passed through the rim's opening from one that sailed past its
depth plane entirely"* — a fundamentally monocular ambiguity, not obviously specific to Video 4's
camera geometry the way the drift/occlusion mismatches above are.

### The six UNKNOWN calls

All six report `"why": "no phase sequence met the positive-evidence bar for MADE or MISSED"`. Spot
checks (including the ≈177s make above) show the same drift/occlusion gates failing to confirm a
crossing, with the ball's subsequent motion this time not qualifying for any MISS case's time
window either — i.e., these are the FSM correctly declining to guess rather than a separate
failure. This is the architecture's designed, intended behavior, not a bug.

### Do these share one mechanism?

**Yes.** Every wrong call and most UNKNOWNs trace back to the same two numeric gates
(`max_crossing_drift_frac_of_rim_radius`, `min_occlusion_dip_frac`) failing to confirm a crossing
that, by direct visual/positional inspection, was clearly a clean make. The one false MADE is the
one case that does *not* share this mechanism — it is the inverse, and arguably irreducible, side
of the same monocular-depth-ambiguity problem the gates exist to manage. Whether the drift/
occlusion mismatch is "caused by" the new camera geometry/angle specifically: **plausibly yes** —
an elevated, more oblique ~45° angle changes both how much apparent lateral drift a truly vertical
drop produces (parallax) and how much the rim/net visually overlaps the ball's path (occlusion),
and this hoop/net's specific structure could independently affect the occlusion signal too. This
investigation did not isolate camera angle from rim/net design as the specific cause (both are
plausible physical mechanisms and both changed between V1-V3's setup and Video 4's), but the
pattern recurring across three separate shots via two different specific gates, both explicitly
threshold-fitted from other footage's numbers, is strong evidence the gates themselves — not the
detector, not the tracker, not the FSM — don't generalize past the footage they were tuned on.

### Regression risk against V1-V3

Unlike Part A, this is not a plausible-but-unverified risk — it is **directly documented in the
code's own rationale**. The drift and occlusion thresholds exist specifically to reject rim/
backboard deflections and same-depth-plane airballs that would otherwise look like clean crossings
in 2D; loosening either to accommodate Video 4's wider-drift, no-dip makes would mechanically
readmit exactly the false-MADE cases those thresholds were fitted to prevent. Any fix here is a
direct trade against the V1-V3 behavior the thresholds currently protect, not a free generalization.

---

## Verdict

**B — failures are understandable but solving them would require additional fitted thresholds/
special cases.**

Both categories are now precisely, causally characterized (this is not a case of insufficient
evidence — the exact failing gate, the exact numeric margin by which it failed, and the exact
downstream consequence are known for essentially every failure). But in neither category is there
a free, generalizable fix available:

- Part A's cleanest candidate fix (a minimum LOAD dwell-duration) still requires inventing a new
  fitted numeric threshold, with regression risk against V1-V3 that is plausible but unverified.
- Part B's failures trace directly to thresholds that were *already* fitted from other footage's
  specific numbers, and any change is a documented, direct trade against the V1-V3 behavior those
  numbers currently protect.

This does not clear the bar for "A" (no general fix was found that doesn't itself require new
fitted constants), and the evidence is far too specific and reproducible to call "C."

## Portfolio-readiness recommendation

**FormAI is already strong enough for a university portfolio if these limitations are reported
honestly — no architecture-level correction is warranted before stopping**, for the same reason
this project has stopped rather than patched at every prior decision point this session: the
available fix in each category is a new or adjusted fitted threshold, evaluated on exactly the kind
of single additional video this project has explicitly refused to fit to all along, with a real,
identified (Part B) or plausible (Part A) risk of quietly regressing the validated V1-V3 behavior
for uncertain gain on a fourth video. The stronger, more technically honest portfolio narrative is
the one already available: a frozen, validated v1 architecture; a genuinely blind fourth-video
test; two specific, rigorously root-caused failure modes, each traced to its exact mechanism rather
than left as an unexplained bug; and a documented decision not to chase either fix under the same
discipline applied throughout. If further engineering time is available later, a **scoped, clearly
labeled experiment** (e.g. a minimum LOAD dwell-duration gate) could be tried under the identical
protocol used all session — adversarial tests, A/B against V1-V3 for regression, a fresh held-out
video for generalization, explicit stop condition — but that is optional future work, not a
prerequisite for calling the current architecture portfolio-ready.
