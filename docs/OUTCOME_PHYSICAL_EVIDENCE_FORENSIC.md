# Outcome Physical Evidence Forensic — Cross-Video Analysis

**Date:** 2026-09-09
**Scope:** FORENSICS ONLY. No production file was modified this turn.
**Zero production files changed. Test baseline unchanged: 197/197.**

This is a read-only investigation into whether a general, physically meaningful
signal — already available in the tracked trajectory, not a new fitted threshold —
can separate genuine MADE shots the pipeline currently misses/abstains on from
genuine MISSED shots that geometrically resemble a make in monocular 2D. Nothing here
was implemented. Two new read-only diagnostic scripts were added
(`scripts/forensic_video4_outcome_evidence.py`, mirroring the pre-existing
`scripts/forensic_arcvision_demo_final.py`) and the showcase forensic report was
regenerated under the current (segmentation-fixed) code, since it previously
reflected the old, now-superseded 13-window segmentation.

---

## 1. Cross-video forensic table

Built from `data/diagnostics/arcvision_demo_final_forensic/shot_forensic_report.json`
(regenerated this turn) and `data/diagnostics/video4_outcome_forensic/shot_forensic_report.json`
(new this turn) — both dump every candidate `(a, b)` MADE-crossing pair actually
evaluated (drift, occlusion dip ratio, deflection status) and all "far descent"
points (below rim, outside the wide zone, within 2s of apex) for every shot, using
the real, unmodified `outcome_detector.py` internals.

### Showcase (11 genuine shots, ground truth: 8 MADE / 3 MISSED)

| Shot | Truth | Pred | Conf | Reason | n_candidate_pairs | far_descent_n |
|---|---|---|---|---|---|---|
| 1 | MADE | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 59 | 0 |
| 2 | MADE | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 117 | 0 |
| 3 | MADE | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 123 | 0 |
| 4 | MADE | **missed** | 0.453 | ball_descended_well_clear_of_hoop | 37 | 2 |
| 5 | MISSED | missed | 0.971 | ball_approached_rim_then_deflected_away | 0 | 0 |
| 6 | MADE | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 39 | 0 |
| 7 | MADE | **missed** | 0.973 | ball_descended_well_clear_of_hoop | 12 | 12 |
| 8 | MISSED | missed | 0.868 | ball_approached_rim_then_deflected_away | 0 | 0 |
| 9 | MISSED | **made** | 0.582 | ball_crossed_rim_band_top_to_bottom | 89 | 0 |
| 10 | MADE | made | 0.701 | ball_crossed_rim_band_top_to_bottom | 57 | 1 |
| 11 | MADE | **missed** | 0.485 | ball_descended_well_clear_of_hoop | 7 | 2 |

### Video 4 (frozen 18-shot ground truth, 5 documented segmentation false-positive
windows excluded)

| Shot (t≈s) | Truth | Pred | Conf | Reason | n_candidate_pairs |
|---|---|---|---|---|---|
| 3 (t=21.4) | MADE (t=15 window) | **missed** | 0.539 | ball_passed_beside_hoop_at_rim_height | 13 |
| 4 (t=33.5) | MISSED | missed | 0.792 | ball_approached_rim_then_deflected_away | 0 |
| 5 (t=43.8) | MISSED | missed | 0.960 | ball_approached_rim_then_deflected_away | 0 |
| 6 (t=48.4) | MISSED | missed | 0.756 | ball_approached_rim_then_deflected_away | 0 |
| 9 (t=66.6) | MISSED | **made** | 0.588 | ball_crossed_rim_band_top_to_bottom | 93 |
| 11 (t=80.9) | MADE | **missed** | 0.973 | ball_descended_well_clear_of_hoop | 18 |
| 12 (t=89.4) | MADE | **missed** | 0.937 | ball_descended_well_clear_of_hoop | 17 |
| 13 (t=97.6) | MISSED | missed | 0.805 | ball_approached_rim_then_deflected_away | 0 |
| 14 (t=108.2) | MISSED | missed | 0.889 | ball_approached_rim_then_deflected_away | 0 |
| 15 (t=121.5) | MADE | made | 0.620 | ball_crossed_rim_band_top_to_bottom | 37 |
| 17 (t=138.2) | MISSED | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 98 (9 pairs would pass under exhaustive search — the already-rejected experiment's false MADE) |
| 19 (t=156.5) | MADE | made | 0.718 | ball_crossed_rim_band_top_to_bottom | 123 |
| 21 (t=186.2) | MISSED | unknown | 0.0 | rim_interaction_not_sufficiently_observed | 93 (21 pairs would pass under exhaustive search — the other already-rejected false MADE) |

(Shots omitted above either match ground truth trivially as correct MISSED/UNKNOWN
with `n_candidate_pairs=0`, matched a documented segmentation false-positive window,
or are not central to the comparisons below.)

## 2. Label by frozen truth

Applied throughout Section 1 (analysis-only; never used as a runtime feature —
confirmed no `outcome_detector.py` line references ground truth, timestamps, or
filenames).

## 3. Search for physical separation

### Hypothesis tested: occlusion confidence-dip ratio (`dip_ratio`, lower = stronger
occlusion evidence, gate requires `dip_ratio <= 0.75`)

**Result: NOT separable — actively counter-correlated in this data.**

| Shot | Class | dip_ratio range on its best candidates |
|---|---|---|
| Showcase 9 | **dangerous false MADE** (truth MISSED) | 0.49 – 0.56 |
| Showcase 2, 3 | genuine MADE (currently UNKNOWN — occlusion gate rejects them) | 0.78 – 0.90 |
| Showcase 10 | genuine MADE (correctly predicted) | 0.63 – 0.72 |
| V4 9 | **dangerous false MADE** (truth MISSED) | 0.50 – 0.52 |
| V4 15, 19 | genuine MADE (correctly predicted) | 0.35 – 0.41 |

The dangerous false-MADE cases in **both** independent videos show a dip_ratio
comfortably inside the passing range, and V4's correctly-classified genuine makes
(15, 19) show an even *lower* dip_ratio (more apparent occlusion) than V4's dangerous
false MADE (9). A rim rattle — the ball genuinely bouncing against/behind the front
rim before popping back out — produces the same or stronger occlusion signature as
a clean swish. This is not just insufficiently discriminating; it is directionally
useless on this evidence. **Rejected as a candidate signal.**

### Hypothesis tested: crossing drift (lateral pixel offset between the above/below
pair, gate requires `drift <= rim_radius_px * 1.6`)

**Result: NOT separable in isolation.** Showcase 9's passing candidates show drift
7.7–21.4px; genuine makes span the same range (showcase 10: 1.7–14.6px; showcase 2:
1.2–14.2px; but showcase 1: 33–49px, entirely outside the gate despite being a
genuine make). Drift alone overlaps heavily between classes.

### Hypothesis tested: height-oscillation / rim-rattle signature (vertical
direction reversals among the above-tight-band candidate points)

**Result: NOT cleanly separable, rejected as a standalone signal.** Showcase 9's
above-band points do show a genuine, sustained ~20px bounce (y drops from 130→108px
then rises back to 128px over 13 points/0.57s) — a real, physically visible rattle.
But showcase shots 2 and 3 (both genuine makes) show comparable or greater
oscillation (up to 3–4 direction reversals, comparable total span) in the same
above-band data, most likely reflecting the trajectory's own apex sitting inside the
tight band rather than a rim bounce. The longest sustained single-direction "rise"
run is 4 frames for shot 9 vs. 3 frames for shot 2 — a 1-frame difference on a
13-frame and 15-frame sample respectively, not a qualitative, structural separation.
**Rejected** per the task's own instruction not to force a threshold onto data that
doesn't show qualitative separation.

### Hypothesis tested: existence of ANY temporally-plausible above→below crossing
candidate (`n_candidate_pairs > 0`) as a gate on Case 1/2/3's independent MISS
evidence (deflection / beside / far-descent)

**Result: a clean, 100% separator across both videos, on every MISSED-classified
shot with known or inferable ground truth:**

| n_candidate_pairs | Video | Shot | Truth | Current pred | Correct? |
|---|---|---|---|---|---|
| **> 0** | Showcase | 4, 7, 11 | MADE | missed | **WRONG**, all 3 |
| **> 0** | V4 | 11, 12 | MADE | missed | **WRONG**, both |
| **> 0** | V4 | 3 | MADE (window truth) | missed | very likely **WRONG** |
| **0** | Showcase | 5, 8 | MISSED | missed | correct, both |
| **0** | V4 | 4, 5, 6, 13 | MISSED | missed | correct, all 4 |

Every currently-"missed" shot with at least one temporally-plausible above/below
crossing candidate is a wrong call in this data (6 of 6 checkable cases, across two
independent videos, two different hoop calibrations, two different camera setups).
Every currently-"missed" shot with **zero** such candidates is a correct call
(6 of 6 checkable cases). `n_candidate_pairs` is not a new signal — it is already
computed by the existing MADE-evaluation loop before Case 1/2/3 ever runs; this
hypothesis only asks whether its existing value (already in scope, unused by the
MISS logic today) predicts anything. It does, cleanly.

**Physical rationale, not mere correlation:** Case 3 (`ball_descended_well_clear_of_hoop`)
fires whenever the ball is found outside the wide zone, below rim height, within
2 seconds of apex — treating this as "the ball clearly missed and continued past the
hoop." But a genuine make's ball does exactly this too: after passing through the
net it keeps falling, hits the floor, bounces, and can end up meters from the hoop
well inside that 2-second window. Case 3 has no way to tell "airball that never got
near the rim" apart from "clean make whose ball kept moving after scoring" — except
that when a temporally-plausible above→below crossing pair *also* exists
(`n_candidate_pairs > 0`), the ball demonstrably *did* pass near the rim in a
physically consistent way, which an airball by definition cannot show. Case 2
(`ball_passed_beside_hoop_at_rim_height`, V4 shot 3) is architecturally the same
kind of check and shows the same failure pattern.

## 4. Most important comparison

**Showcase true makes that currently fail vs. V4 true misses that would become
false MADE under exhaustive search** (the already-rejected experiment,
`docs/MADE_SEARCH_COMPLETENESS_FIX.md`; not re-run — the historical result and this
turn's forensic dump of the *same* candidate pairs are used together):

| Signal | Physical rationale | Showcase makes (4,7,9-rattle,11) | V4 dangerous misses (17,21 under exhaustive search) | Separation quality | Generalization risk | New constant? |
|---|---|---|---|---|---|---|
| dip_ratio | occlusion = passed through rim opening | 0.45–0.97 (wide, overlapping) | 0.59–0.72 | **None** — ranges overlap heavily, and the genuine rattle (showcase/V4 shot 9) sits in the *low* (strong-occlusion) part of both ranges, same as the V4 exhaustive-search false MADEs | High (already unreliable in-sample) | No, but doesn't work |
| drift | clean vertical pass-through | 1–72px (wide) | 22–30px, hugging the max allowed (29.9px) | **None** | High | No, but doesn't work |
| n_candidate_pairs > 0 (as a MISS-evidence gate, not a MADE-evidence search) | a plausible above→below transition existed at all | Present for 4/7/9/11 (7–37 pairs) | **Not applicable — these are correctly abstaining as UNKNOWN today, not being converted to MISSED**; the proposed change does not touch MADE's search behavior at all | **Clean (100% in-sample)** for its actual target (Case 1/2/3 false MISSED), genuinely orthogonal to the exhaustive-search danger | Low — reuses existing, already-normalized computation | **No** |

The critical distinction: the exhaustive-search experiment's danger was about
**MADE's own search finding a passing pair it shouldn't have trusted** (V4 17/21 have
9 and 21 candidate pairs that pass drift+occlusion, and exhaustive search would
report them as confident MADE). The `n_candidate_pairs > 0` gate proposed here
**never touches MADE's search or gates at all** — it only prevents the separate,
independent MISS logic (Case 1/2/3) from overriding a genuinely ambiguous crossing
with unwarranted confidence. V4 shots 17 and 21 are untouched by this proposal:
they correctly remain UNKNOWN before and after, for an unrelated reason (no
candidate pair reaches MADE's gates under the current, non-exhaustive search, which
this proposal does not change).

## 5. Normalization check

`n_candidate_pairs > 0` requires no new pixel threshold: it reuses the existing
`_interaction_band`/`_wide_zone` computation (already expressed as a fraction of
`hoop.rim_radius_px`) and the existing `max_seconds_through_rim` time window (already
in seconds, not frames) — both already scale-independent. Verified working
consistently across two different hoop-radius calibrations in this data
(showcase: `rim_radius_px=28.2`; V4: `rim_radius_px≈29.9`), though both happen to be
similar in absolute magnitude; no video with a substantially different camera
distance was available this pass to test the extreme end of this claim. Shot 11
(the intentionally farther showcase shot) shows the SAME behavior as the others
under this signal: `n_candidate_pairs=7 > 0`, so it too would move from a confident
wrong MISS to an honest UNKNOWN — no special-casing needed for its distance.

## 6. Dominant architectural weakness

Primarily **B (incomplete temporal reasoning)** and **D (insufficient post-rim
evidence usage)**: Case 1/2/3's "positive MISS evidence" is evaluated in a temporal
vacuum, without checking whether the *same* trajectory also contains a
temporally-plausible rim-crossing candidate that the far/beside/deflection points
might just be the natural continuation of. This is a genuine implementation gap
(A), not fundamentally unresolvable monocular ambiguity (E) — the existing
`n_candidate_pairs` computation already contains the disambiguating information;
Case 1/2/3 simply never consults it.

A secondary, separate, **not** addressed by anything proposed here:
**E (fundamentally ambiguous monocular projection)** does dominate the *other* half
of the outcome problem — separating a genuine rattle (showcase/V4 shot 9) from a
genuine make using only drift and occlusion-dip. Every signal tried in Section 3
failed to separate these with the current trajectory data. This looks like a real
information-availability limit of 2D monocular tracking at the resolution/frame
rate available here, not an implementation bug — though it was not exhaustively
ruled out (e.g., a genuinely different signal entirely, not tried here, might exist).

## 7. Proposed next architecture (ONE, evidence-supported, NOT implemented)

**Gate Case 1/2/3's MISS evidence (`ball_approached_rim_then_deflected_away`,
`ball_passed_beside_hoop_at_rim_height`, `ball_descended_well_clear_of_hoop`) on the
absence of any temporally-plausible above→below crossing candidate.** Concretely:
before evaluating Cases 1–3, check whether the same `(descent_above_tight,
descent_below_tight)` computation the MADE loop already performs found at least one
`(a, b)` pair with `b` chronologically after `a` within `max_seconds_through_rim`
(regardless of whether that pair passed drift/occlusion). If it did, Cases 1–3 must
not return a confident MISS — the shot falls through to the existing UNKNOWN
fallback (`rim_interaction_not_sufficiently_observed`) instead. If MADE's own
existing gates already found a passing pair, MADE already wins by evaluation order
and is entirely unaffected.

- **No ground truth at runtime:** uses only the trajectory's own existing candidate-pair computation.
- **No video-specific logic, no filename/timestamp special cases:** verified against two independent videos with different footage, hoop calibration, and camera setup.
- **No fitted stack of constants:** the gate is a pure existence check (`len(candidates) > 0`) on data the MADE loop already computes; zero new numeric thresholds.
- **Rejects V4's dangerous misses (17, 21) exactly as before — untouched:** this proposal does not modify MADE's search or gates in any way; those two shots' correct UNKNOWN status is unaffected because they were never reaching Case 1/2/3 to begin with (they already reach the final UNKNOWN fallback for an unrelated reason).
- **Recovers showcase genuine makes (4, 7, 11) and V4's (11, 12, and likely 3) from confident wrong MISSED to honest UNKNOWN** — not to confident MADE. This is a coverage/safety trade, not a full fix: it removes six confident wrong answers (three of them above 0.9 confidence) at the cost of returning them to UNKNOWN, exactly the "preserve UNKNOWN when physical evidence is actually insufficient" principle the task requires.
- **Does NOT address:** the false-MADE rattle problem (showcase/V4 shot 9 — Section 3/6 found no safe signal for this); the "true MADE currently UNKNOWN" shots that never reach Case 1/2/3 at all (showcase 1, 2, 3, 6; several V4 shots); or MADE's own search-completeness limitation (deliberately, per this session's standing prohibition).

## 8. Do not implement

Confirmed: no change was made to `outcome_detector.py`, `shot_state_machine.py`, any
detector, tracker, UI, or the demo exporter this turn. No production constant was
added. Two new read-only diagnostic scripts were added under `scripts/`, and two
diagnostic JSON reports were (re)generated under `data/diagnostics/` — no other
files were touched.

---

## Final report

**A. Current showcase outcome confusion:** 8 MADE truth / 3 MISSED truth. Predictions:
1 MADE correct (shot 10), 4 MADE truth misclassified UNKNOWN (1, 2, 3, 6), 3 MADE
truth misclassified confident MISSED (4, 7, 11 — one at 0.973 confidence), 2 MISSED
truth correctly MISSED (5, 8), 1 MISSED truth misclassified confident MADE (9, a rim
rattle, 0.582 confidence).

**B. Most important physical difference between true makes and dangerous misses:**
none was found that reliably separates a genuine rim-rattle miss (shot 9, both
videos) from a genuine make using drift or occlusion-dip — both signals overlap or
actively invert between these classes. The one clean, general, structural difference
found operates on a *different* pair of classes: whether *any* temporally-plausible
rim-crossing candidate exists at all cleanly separates "confidently, wrongly called
MISSED" true-MADE shots from correctly-called true-MISSED shots (100% across 12
checkable cases in 2 videos).

**C. Best candidate signal:** `n_candidate_pairs > 0`, used as a gate preventing
Case 1/2/3's independent MISS evidence from overriding a shot whose trajectory also
shows a plausible rim crossing. Clean, general, zero new constants.

**D. Second-best candidate signal, if any:** none found that meets the bar. Drift
and occlusion-dip were both tried and rejected (Section 3) — not "second-best," but
explored and found non-separating.

**E. Counterexamples to each:** for C, none found in this data (6/6 and 6/6 clean
in both directions); the caveat is sample size (12 shots total, one video pair) and
that it only ever *removes* false confidence, never *adds* correct MADE calls. For
drift/occlusion-dip, showcase shots 2/3/9/10 and V4 shots 9/15/19 are themselves the
counterexamples (documented in Section 3).

**F. Whether post-rim evidence materially helps:** yes, but currently in the *wrong
direction* — it is used as standalone MISS evidence (Case 3) without checking
whether it's actually the natural continuation of a make. Used correctly (as a gate
suppressing false MISS confidence, not as new positive evidence), it is the single
most useful thing found this pass.

**G. Whether rim-rattle behavior is separable:** no. Every signal tried (dip_ratio,
drift, height-oscillation reversal count/magnitude) failed to separate showcase/V4
shot 9's genuine rattle from genuine clean makes.

**H. Whether Shot 11 is solvable with existing evidence:** not as a confident MADE —
no candidate pair passes both gates for it in either video's data. It IS solvable as
"stop being confidently wrong": under the proposed architecture it would correctly
fall back to UNKNOWN instead of a wrong 0.485-confidence MISSED.

**I. Whether normalization across camera distance is feasible:** the proposed
signal itself needs no new normalization (reuses existing rim-radius- and
time-based scales). Verified consistent across two different hoop-radius
calibrations; not verified against a substantially different camera distance in
this pass.

**J. Dominant architectural weakness:** B (incomplete temporal reasoning) / D
(insufficient post-rim evidence usage) for the false-MISSED problem; E
(fundamentally ambiguous monocular projection), not yet ruled out as solvable with a
different signal, for the false-MADE rattle problem.

**K. Proposed ONE next architecture:** gate Case 1/2/3's MISS evidence on
`n_candidate_pairs > 0` (fall through to UNKNOWN instead of a confident MISS when a
plausible crossing candidate exists). See Section 7.

**L. Why it should recover showcase makes:** shots 4, 7, 11 (currently confident
wrong MISSED, one at 0.973 confidence) would correctly fall back to UNKNOWN, since
each has 7–37 temporally-plausible crossing candidates the current MISS logic
ignores.

**M. Why it should reject V4's dangerous misses:** it doesn't interact with them at
all — V4 shots 17 and 21 (the ones that would become false MADE under the
already-rejected exhaustive search) never reach Case 1/2/3 today and are entirely
unaffected by this proposal, which only touches the independent MISS-evidence code
path.

**N. Whether it requires new fitted constants:** no.

**O. Expected regression risk:** **LOW.** In this data it never changes a currently-
correct MISSED call (both videos' 6 correctly-classified MISSED shots all have
`n_candidate_pairs=0` and are untouched) and never manufactures a new confident
MADE (it can only convert MISSED→UNKNOWN, never MISSED→MADE). Caveat: sample size is
12 checkable shots across 2 videos; not verified against V1/V2/V3 or a broader
corpus this pass.

**P. Recommendation: IMPLEMENT PROTOTYPE** (in a future, separately-authorized turn
— not this one) for the `n_candidate_pairs > 0` MISS-evidence gate specifically.
This is a narrow, well-evidenced, low-risk fix for one clearly-identified slice of
the outcome problem (confident wrong MISSED on genuine makes) — not a fix for
outcome classification as a whole. The rim-rattle false-MADE problem and the
"true MADE currently UNKNOWN" shots remain open, unsolved by this proposal, and no
safe signal for either was found this pass.

**Q. Confirmation zero production files changed:** confirmed — `outcome_detector.py`,
`shot_state_machine.py`, detector, tracker, UI, and demo exporter are all untouched
this turn.

**R. Test baseline remains 197/197:** confirmed, re-run this turn.
