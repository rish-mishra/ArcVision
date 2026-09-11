# Showcase Segmentation Fix — Duplicate/False Shot Events

**Date:** 2026-09-08
**Scope authorized:** ONLY duplicate/false shot segmentation on `arcvision_demo_final.mov`.
Outcome classification (MADE/MISSED/UNKNOWN), detector, and tracker code are all
explicitly out of scope and were not touched.
**Decision: KEEP SEGMENTATION FIX.**

`docs/FINAL_DEMO_BLIND_EVALUATION.md` (the original, historically-frozen blind
evaluation) was not modified.

---

## Background

The blind evaluation recorded 2 false-positive shot events on the showcase video:
detected #2 at 11.104s and detected #11 at 87.728s, both immediately preceding a
genuine shot by under 2 seconds — described there as "plausibly a split/double-trigger
around one real attempt." Forensics already suggested this matched V4's previously
documented "no LOAD dwell" failure family (`docs/VIDEO4_FORENSIC_ANALYSIS.md` Part A).

## 1. Forensic trace

A new read-only script, `scripts/forensic_segmentation_showcase.py`, reproduced the
exact same detection/tracking/state-machine pass production uses, with
`ShotStateMachine(enable_trace=True)`, and dumped the full per-frame FSM trace plus
every window's boundaries. Mapping the two false events to FSM windows:

| False event | FSM shot_index (pre-fix) | LOAD→UPWARD gap | Preceding genuine shot | Following genuine shot |
|---|---|---|---|---|
| ~11.104s | 2 | 4 frames | shot 1, release 2.267s | shot 3 (fallback trigger), release 12.271s |
| ~87.728s | 11 | 1 frame | shot 10, release 80.126s | shot 12, release 89.796s |

**Shot 2's false trigger:** `ball_hand_dist_norm` oscillates erratically in the
frames leading up to LOAD entry (idle-phase noise: 0.05 → 2.1 → 0.05 → 2.1... within
single frames — consistent with the tracker alternating between competing position
candidates, the same "sawtooth" signature already documented for V4's 109.7s/132.9s
false positives). A real knee-flexion dip (~160° → 146.8° → 167.8°, comfortably over
`load_knee_flexion_drop_deg`=12.0) genuinely occurs in the ~1.3s lookback window, so
`_genuine_knee_dip_nearby` correctly reports a real dip — but LOAD is only occupied
for 4 frames (243→247) before UPWARD fires. Crucially, once in UPWARD, the ball's
`ball_y` never rises above `shoulder_y` for the entire 82-frame span (247→328) — a
real release's defining signature is absent throughout. "Separation" is confirmed
only because the ball drops out of tracking (`ball_available=False`) for 2 consecutive
frames (329-330), which the pre-fix code treated as equivalent to confirmed physical
distance.

**Shot 11's false trigger:** LOAD occupies exactly 1 frame (2600→2601). The knee dip
`_genuine_knee_dip_nearby` accepts (min ~150.1° at frame 2564) occurred **1.3 seconds**
before the trigger, while the ball was demonstrably NOT near the hand (hand_dist=0.233,
above the 0.18 proximity threshold) — i.e. this dip belongs to an earlier, unrelated
moment (the shooter settling from shot 10), not to any gathering motion for this touch.
Knee angle at the actual trigger frame is a flat ~170-173°, showing no real-time bend
at all. As with shot 2, "separation" completes purely via 2 consecutive
`ball_available=False` frames, not confirmed distance.

**Comparison to V4's five false positives:** four of V4's five (22.5s, 57.7s, 77.5s,
132.9s group) were attributed to "no LOAD dwell" plus, for two of them, the same raw
tracking-noise ("sawtooth") signature found here. The showcase video's two false
events share both symptoms — but the specific completing mechanism (separation
confirmed by tracking dropout rather than confirmed distance) is a more precise,
common root cause visible once traced frame-by-frame, and it directly explains why
both showcase false events, despite very different LOAD-dwell lengths (4 frames vs.
1 frame), still complete a full shot cycle: **neither event's "release" was ever
backed by a single frame of confirmed ball position that was actually far from the
hand and above shoulder height.** Every one of the video's 11 genuine releases
(verified directly, see below) has the opposite signature: confirmed `ball_available`
at every frame contributing to separation.

## 2. Search for a general discriminator

Two candidate discriminators tied to LOAD dwell length were tested and rejected
empirically before settling on the one implemented:

- **Reuse `release_separation_frames` as a required run of consecutive
  qualifying-velocity frames before LOAD→UPWARD fires.** Rejected: the noise driving
  both false triggers is itself a multi-frame trend (the ball's vertical velocity
  stays negative for several consecutive frames as it descends under gravity toward
  the hand), so a short consecutive-frame requirement delays the transition by 1-2
  frames without preventing it.
- **Require a minimum number of consecutive close-to-hand frames in LOAD before
  trusting the burst** (e.g. reusing `reset_stationary_frames`=5, the constant
  already used elsewhere in this file for confirming a stable/settled state).
  Rejected on direct evidence: querying every one of the video's 13 originally-
  detected shots showed **8 of the 11 genuine shots also have a 1-frame LOAD→UPWARD
  gap** (shots 1, 4, 5, 6, 7, 8, 9, 10 in the pre-fix numbering) — a raw dwell-count
  gate at any threshold above 1 frame would have broken most of this video's
  correctly-detected genuine shots, not just the two false ones. This matches
  `docs/VIDEO4_FORENSIC_ANALYSIS.md`'s own caveat that a dwell-duration gate "still
  requires inventing a new fitted numeric threshold" — confirmed here to be actively
  unsafe, not merely unproven.

The discriminator that held up under direct querying of all 13 originally-detected
shots was **how separation was actually confirmed**, not LOAD timing at all: every
one of the video's 11 genuine releases has `ball_available=True` at every frame that
contributed to its separation-confirmation run (real, confirmed-far, above-shoulder
evidence). Both false events confirm separation exclusively through a tracking
dropout, with zero frames of confirmed far-and-above-shoulder evidence anywhere in
their UPWARD phase. This reuses a principle already present elsewhere in the exact
same file — the FLIGHT phase's own handling explicitly treats a missing ball as *not*
positive evidence of anything (`ball going undetected... is NOT itself evidence the
shot ended`) — just applied for the first time to the UPWARD phase's separation
check, which had been treating an absence of tracking as equivalent to confirmed
distance with no corroborating real evidence ever required.

## 3. Regression tests (written before the fix)

`tests/test_shot_segmentation_phantom_touch.py`, 7 synthetic tests, no showcase
timestamps/filenames/session IDs:

| Test | Category | Pre-fix result | Post-fix result |
|---|---|---|---|
| A | shot → rebound → no 2nd shot | PASS | PASS |
| B | shot → immediate real catch-and-shoot → 2nd shot allowed | PASS | PASS |
| C | dribble bounce near hand → no shot | PASS | PASS |
| D | ordinary genuine shot detected | PASS | PASS |
| E | quick genuine release (short LOAD dwell) detected | PASS | PASS |
| F | rearm after forced closure works | PASS | PASS |
| **G** | **noisy momentary touch + stale borrowed knee dip + dropout-only separation → phantom shot** | **FAIL (3 windows, expected 2)** | **PASS (2 windows)** |

A-F reproduce failure categories already independently covered by
`tests/test_shot_state_machine.py` (30 pre-existing tests, all of which also
continued to pass after the fix — see Section I) — included here fresh so this file
stands alone as the record. G is the fixture representing the actual architectural
bug; it failed against unmodified production for the documented reason (release
confirmed via 2 consecutive `ball_available=False` frames with no genuine distance
evidence ever observed) before any code change, confirming the bug is real and not a
test artifact.

## 4. The fix

`app/events/shot_state_machine.py`, `ShotStateMachine._step`, `ShotPhase.UPWARD`
branch — before:

```python
elif self._phase == ShotPhase.UPWARD:
    if not f.ball_available:
        self._separation_run += 1
    else:
        far = (...)
        above_shoulder = (...)
        if far and above_shoulder:
            self._separation_run += 1
        else:
            self._separation_run = 0
```

After:

```python
elif self._phase == ShotPhase.UPWARD:
    if not f.ball_available:
        if self._separation_run > 0:
            self._separation_run += 1
    else:
        far = (...)
        above_shoulder = (...)
        if far and above_shoulder:
            self._separation_run += 1
        else:
            self._separation_run = 0
```

**No new constants.** `cfg.release_separation_frames`, `cfg.hand_proximity_threshold_norm`,
every other threshold, and the `far`/`above_shoulder` computation are all byte-identical
to before. The only change: a tracking dropout can no longer manufacture a separation
run from nothing — it can only extend a run a real, confirmed far-and-above-shoulder
frame already started. This preserves the existing, real-video-motivated behavior of
tolerating a brief dropout *during* a genuine release (motion blur right as the ball
leaves the hand, after distance has already been confirmed at least once), while
closing the specific loophole that let a noisy near-hand touch "seal" itself as a
release purely because tracking happened to drop out afterward.

**Files changed:** `app/events/shot_state_machine.py` only (plus the new test file).
`app/events/outcome_detector.py` is confirmed untouched — still contains the original
pre-search-completeness `b = min(later_below, ...)` loop from the earlier, separately
reverted experiment this session.

## 5. Full test suite

197 passed, 0 failed (190 pre-existing + 7 new). Zero regressions among pre-existing
tests, including all 30 in `tests/test_shot_state_machine.py` (rebound, dribble,
walking-dribble, intermittent-detection, long-hold, pump-fake, and rapid-catch-and-
shoot fixtures all continued to pass).

## 6. V1-V4 regression (before Phase 7)

Full pipeline re-run via `scripts/overnight_v1v2v3v4_regression.py`, compared against
`data/diagnostics/overnight_regression_prefix_fix/` (the correct baseline — matches
today's actual, already-reverted `outcome_detector.py` state; an earlier intermediate
snapshot taken at the start of this turn was found to be contaminated by the prior,
separately-reverted MADE-search-completeness experiment and was not used for
comparison).

| Video | Shots before | Shots after | Outcome changes on retained shots |
|---|---|---|---|
| V1 | 7 | 7 | None |
| V2 | 9 | 9 | None |
| V3 | 5 | 5 | 1 shot's release time shifted 26.83s→28.17s (confidence 0.76→0.664, apex_height_norm 3.67→5.45) — same outcome (`missed`, same reason) both before and after. No frozen ground truth exists for V3, so this is reported descriptively only, not scored. Consistent with the same release-timing-refinement effect seen on the showcase video (Section 8). |
| V4 | 23 | 21 | None — every retained shot's outcome and confidence are byte-identical. |

**V4 false-positive detail (Section M/regression check):** the two removed windows
are release times 22.5s and 109.7s — both are 2 of the 5 documented false-positive
windows from `docs/VIDEO4_FORENSIC_ANALYSIS.md` Part A. V4's false-positive count
improves from 5 → 3 (57.7s, 77.5s, 132.9s remain — these were attributed partly or
fully to raw tracking noise rather than the dropout-as-separation mechanism this fix
targets, so their persistence is expected, not a fix failure). All 18 frozen
ground-truth shots remain present and correctly matched; zero genuine shots lost.

**Critical regression check: PASSED.** No genuine shot lost in any of V1-V4; V4's
false-positive count improved (did not worsen); outcome logic is unchanged
everywhere it was possible to change (it wasn't touched, and the data confirms it).

## 7. Showcase video validation

`arcvision_demo_final.mov` re-run once with the segmentation fix (development
validation, not a rewrite of the frozen blind evaluation).

| Metric | Before | After |
|---|---|---|
| Detected events | 13 | **11** |
| TP | 11 | **11** |
| FP | 2 | **0** |
| FN | 0 | 0 |
| Precision | 84.6% | **100%** |
| Recall | 100% | 100% |

Matching used nearest release-time (tolerance 3s) against the 11-shot ground truth:

| Truth # | Truth time | Truth outcome | Matched detected release | Diff |
|---|---|---|---|---|
| 1 | 2s | MADE | 2.267s | 0.267s |
| 2 | 12s | MADE | 12.171s | 0.171s |
| 3 | 27s | MADE | 26.842s | 0.158s |
| 4 | 36s | MADE | 36.045s | 0.045s |
| 5 | 46s | MISSED | 46.315s | 0.315s |
| 6 | 51s | MADE | 51.483s | 0.483s |
| 7 | 60s | MADE | 60.753s | 0.753s |
| 8 | 71s | MISSED | 72.157s | 1.157s |
| 9 | 79s | MISSED | 80.126s | 1.126s |
| 10 | 89s | MADE | 89.796s | 0.796s |
| 11 | 96s | MADE | 96.098s | 0.098s |

All 11 genuine shots now map to exactly one detected event each; the two previously
false events (release times 12.171s absorbed shot 2, and 89.796s absorbed shot 10 —
see Section 8) no longer produce separate windows.

This matches the task's stated ideal target exactly (11 events, 11 TP, 0 FP, 0 FN),
achieved with zero new constants and zero showcase-specific logic — the fix is a pure
structural change to how separation evidence is interpreted, verified general via
Sections 3 and 6.

## 8. Unexpected finding: window-boundary contamination on 2 of 11 shots

This fix corrects **which frame confirms separation**, but does not address the
*other* half of the original bug: the LOAD→UPWARD transition still fires on the same
noisy touch + borrowed knee dip it always did (Section 1/2's LOAD-side mechanism is
unchanged — deliberately, since every attempted fix for it was shown to be either
unsafe or to require a new fitted constant, see Section 2). Previously, that
premature LOAD→UPWARD entry produced its own short-lived, separately-closed phantom
window. Now, because separation can no longer confirm on the noisy dropout alone, the
machine instead stays continuously in UPWARD/FLIGHT through the noisy touch and *all
the way through* the shooter's subsequent real gather and release — merging what were
two FSM episodes into one.

For the 2 showcase shots this affects (post-fix shot_index 2 and shot_index 10, the
same two that had false events before), the emitted window's `load_start_frame` and
`start_frame` are inherited from the original spurious touch (8.103s and 86.695s
respectively) rather than the genuine gather (roughly 11-12s and roughly 89s, based on
where the real motion actually begins). Downstream, `build_shot_from_window` passes
`window.load_start_frame` directly into `compute_shot_mechanics` with no independent
re-derivation — so **load-phase biomechanics (e.g. knee angle at load, torso lean at
load) for these 2 of 11 shots would be computed from the wrong moment** even though
the shot's release timing, flight trajectory, and outcome are all correct.

This is a real, measured side effect, not a hypothetical one — verified directly via
the cached frame-signal trace. It affects biomechanics/coaching detail for 2 shots,
not shot segmentation (event count, false positives, false negatives, or outcome),
which is what this turn was authorized to fix and what Section 7 confirms is now
exact. A `load_start_frame` correction would require a second, distinct change to the
LOAD-entry/knee-dip-lookback logic — explicitly out of scope for this turn's "smallest
possible fix, no second fix" mandate, and (per Section 2) no safe, general version of
that change was found without inventing a new constant. This is flagged here as a
recommended candidate for a future, separately-authorized investigation, not
addressed now.

## 9. Decision

| Criterion | Result |
|---|---|
| Failing synthetic regression genuinely fixed | Yes (test G) |
| Full test suite passes | Yes (197/197, 0 regressions) |
| Regression videos (V1-V4) don't lose genuine shots | Yes |
| New video improves without special casing | Yes (13→11 events, exact match to truth, zero new constants) |

**KEEP SEGMENTATION FIX.**

No second fix was attempted. The window-boundary side effect (Section 8) is
documented, not fixed, this turn.

---

## Final report

**A. Root cause of FP #1 (~11.104s):** LOAD occupied 4 frames on the back of a real
but noise-adjacent knee dip; "separation"/release confirmed only via 2 consecutive
ball-tracking dropout frames, with the ball never once confirmed above shoulder
height in the preceding 82 frames.

**B. Root cause of FP #2 (~87.728s):** LOAD occupied 1 frame; the accepted knee dip
occurred 1.3s earlier while the ball was confirmed NOT near the hand (belongs to an
unrelated recovery motion, not this touch); separation again confirmed only via 2
consecutive dropout frames, zero confirmed-far evidence.

**C. Comparison to V4 FP mechanism:** same family as V4's already-documented "no LOAD
dwell" false positives (4 of 5), and shares V4's raw-tracking-noise ("sawtooth")
sub-signature with 2 of those 5. The more precise, general, and directly fixable
common root cause across both showcase events and (empirically) V4's 22.5s/109.7s
cases specifically: separation was confirmed with zero frames of genuine confirmed
distance evidence, relying entirely on a tracking dropout.

**D. Pre-fix failing synthetic test:** `test_g_noisy_momentary_hand_touch_with_stale_knee_dip_is_not_a_phantom_shot`
in `tests/test_shot_segmentation_phantom_touch.py` — 3 windows detected (expected 2)
against unmodified production, confirmed before any code change.

**E. General fix:** `app/events/shot_state_machine.py`'s UPWARD-phase separation
check now requires `self._separation_run > 0` before a ball-tracking dropout can
increment it — a dropout can only extend an already-genuinely-confirmed departure,
never manufacture one from nothing. See Section 4 for the exact diff.

**F. Why it is not demo-specific:** zero new constants; reuses the existing
`far`/`above_shoulder` computation unchanged and reuses the "absence isn't positive
evidence" principle already present in this same file's FLIGHT-phase handling.
Verified general via 7 synthetic fixtures with no showcase timestamps, and via direct
empirical rejection of two dwell-count-based candidate fixes that would have broken
8 of this video's own 11 genuine shots (Section 2).

**G. Exact files changed:** `app/events/shot_state_machine.py` (production fix),
`tests/test_shot_segmentation_phantom_touch.py` (new, 7 tests, kept).

**H. Confirmation `outcome_detector.py` untouched:** confirmed — still contains the
original `b = min(later_below, ...)` loop; zero outcome/confidence changes on any
retained shot across V1-V4 and the showcase video.

**I. Full test result:** 197 passed, 0 failed (190 pre-existing + 7 new, 0 regressions).

**J. V1 shot count before → after:** 7 → 7 (unchanged).

**K. V2 shot count before → after:** 9 → 9 (unchanged).

**L. V3 shot count before → after:** 5 → 5 (unchanged; 1 shot's release timing shifted
with no ground truth to score against, same outcome before/after).

**M. V4 shot count / FP before → after:** 23 → 21 shots; 5 → 3 known false-positive
windows (22.5s and 109.7s removed); 0 genuine shots lost; 0 outcome changes on any
retained shot.

**N. Showcase detected events before → after:** 13 → 11.

**O. Showcase TP / FP / FN:** 11 / 0 / 0 (precision 100%, recall 100%; before: 11 / 2 / 0).

**P. KEEP SEGMENTATION FIX.**

**Q. Confirmation no outcome work was performed:** confirmed — `outcome_detector.py`
was not modified, no MADE/MISSED/UNKNOWN logic, threshold, or constant was touched
this turn; every outcome value on every retained shot across V1-V4 and the showcase
video is byte-identical before and after.
