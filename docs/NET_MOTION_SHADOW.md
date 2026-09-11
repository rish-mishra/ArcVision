# Net-Motion / Rim-Crop Shadow Resolver — Diagnostic Evaluation

**Date:** 2026-09-09
**Scope:** SHADOW-ONLY, DIAGNOSTIC-ONLY throughout both parts. No production
file was modified in either pass. No MADE/MISSED verdict was ever computed.

**FINAL STATUS (after Part 2, the last allowed experiment on this concept):
STOP HANDCRAFTED VISUAL-MOTION ENGINEERING.** Part 2 controlled for the two
confounds Part 1 identified (shooter contamination, incomplete ball
masking) using ArcVision's own already-computed person and ball detections,
and found the measurements barely changed — the representation was not
primarily explained by those confounds after all, and still does not
separate genuine makes from the known dangerous rattle/false-MADE cases.
See Part 2 below for the full account; Part 1 (below, unmodified) is
preserved as the historical record of the first experiment.

---

# Part 1 — Original experiment (uncontrolled, FAILED)

**Test baseline at the time: 217 passed (197 production + 12
reversal-shadow + 8 net-motion-shadow tests), 0 failed.**

**Recommendation at the time: STOP HANDCRAFTED NET-MOTION APPROACH** (this
specific representation) — see Section 12 below for the full justification.
**Superseded by Part 2** (further down this document) — preserved here
unmodified as the historical record.

---

## A. Implementation files

- `app/research/net_motion_resolver.py` — core module (dataclasses +
  `analyze_net_motion_from_frames`, pure/video-I/O-free).
- `tests/research/test_net_motion_resolver.py` — 8 synthetic tests (A–H).
- `scripts/net_motion_shadow_eval.py` — read-only real-video diagnostic
  evaluation (bounded frame decode only, no RF-DETR/pose re-run).
- `data/diagnostics/net_motion_shadow/` — output: `showcase_net_motion.json`,
  `v4_net_motion.json`, and one PNG diagnostic panel per evaluated shot.

## B. Production untouched

**YES.** `git status` shows no changes under `app/events`, `app/pipeline`,
`app/vision`, `app/tracking`. Only `app/research/`, `tests/research/`, and
one new script were added.

## C. Tests

197 production + 12 reversal-shadow + **8 new net-motion tests** = **217
passed, 0 failed.**

## D. Exact visual representation

Per consecutive grayscale frame pair: mean **absolute pixel difference**
within a rim-relative **net ROI** (a region below the rim), compared
against the same measure in two **control ROIs** of identical size placed
immediately adjacent to the net ROI at the same vertical band. Output is a
**relative ratio** (net motion ÷ control motion) plus the raw components —
deliberately the simplest deterministic representation available (plain
frame-differencing, not optical flow, per instruction).

## E. Normalization method

Everything is sized from the existing, already-validated rim geometry:
net ROI half-width = `rim_radius_px * horizontal_margin_frac_of_rim_radius`
(existing production config, 1.6×); net ROI vertical span =
`rim_bottom_y` to `rim_bottom_y + 2.0 * rim_radius_px` (one of exactly two
new constants in this module — see Section O); control ROIs are the same
size, placed immediately adjacent (non-overlapping) left and right of the
net ROI — a structural placement rule, not a chosen pixel offset. The
"elevated" comparison itself (ratio > 1.0) is a zero-parameter structural
baseline (no differential motion between net and control = ratio of
exactly 1), not a fitted cutoff.

## F. Ball masking method

A circular mask is excluded from the net ROI's mean-difference computation,
centered at the ball's tracked position for that frame pair. Where a real
per-frame `radius_px` is available it is used directly; otherwise the
module falls back to a physically-reasoned proportion (regulation
basketball radius ≈ half a regulation rim radius — the second of the two
new constants, Section O). **Synthetic test E confirms the mechanism works**
(masking measurably suppresses a synthetic ball-only motion spike). **The
real-video evaluation exposes a real limitation** — see Sections I/L/N/Q.

## G. Background/global-motion control

Implemented via the relative (net ÷ control) ratio, validated synthetically
(tests B and C: uniform brightness change and uniform camera-pan-like
translation both collapse to ratio ≈ 1, i.e. correctly suppressed). **The
real-video evaluation found the chosen control-region PLACEMENT is
insufficient in practice** — every inspected panel shows the shooter (who
remains standing in frame near the hoop after releasing the ball, since
these are fixed-camera clips of one person shooting) frequently overlapping
or passing directly through the control regions, producing large,
outcome-irrelevant "control motion" contamination the ratio was supposed to
cancel out. This is the primary reason for this pass's STOP recommendation
— see Section L.

## H. Showcase evidence table

All values from `data/diagnostics/net_motion_shadow/showcase_net_motion.json`.
`elevated_frac` = fraction of frame pairs with ratio > 1.0 (robust);
`median_rel` = median relative-motion ratio (robust). `max`/`mean` are
reported but **known unreliable** — see Section L's numerical-artifact
finding.

| Shot | Truth | Production | n pairs | elevated_frac | median_rel |
|---|---|---|---|---|---|
| 1 | MADE | unknown | 54 | 0.759 | 2.36 |
| 3 | MADE | unknown | 62 | 0.806 | 2.91 |
| **9** | **MISSED (rattle)** | **made (0.58)** | 63 | **0.905** | 2.58 |
| 10 | MADE (clean, correct) | made (0.70) | 67 | 0.806 | 4.07 |
| 11 | MADE | missed (0.48) | 46 | 0.783 | 7.40 |
| 5 | MISSED (correct) | missed (0.97) | 56 | 0.839 | 2.34 |
| 8 | MISSED (correct) | missed (0.87) | 41 | 0.829 | 1.73 |

## I. V4 evidence table

From `data/diagnostics/net_motion_shadow/v4_net_motion.json`. V4's ball
masking used only the **sparse** candidate-pair ball positions (frames
inside the tight interaction band) — most frame pairs have no ball sample
at all, so masking is applied far less consistently than for showcase; this
is an honest, reported limitation of this pass, not a claim that V4's
underlying ball data is unavailable in general (a dense pass would require
re-running detection, avoided per instruction).

| Shot | Truth | Production | n pairs | elevated_frac | median_rel |
|---|---|---|---|---|---|
| **9** | **MISSED (known false-MADE)** | **made (0.59)** | 57 | **0.912** | 2.07 |
| 17 | MISSED (dangerous case) | unknown | 60 | 0.617 | 1.13 |
| 21 | MISSED (dangerous case) | unknown | 64 | 0.469 | 0.96 |
| 15 | MADE (correct) | made (0.62) | 71 | 0.606 | 1.12 |
| 19 | MADE (correct) | made (0.72) | 62 | 0.790 | 1.81 |
| 4 | MISSED (correct) | missed (0.79) | 64 | 0.469 | 0.95 |
| 5 | MISSED (correct) | missed (0.96) | 52 | 0.558 | 1.06 |

## J. Strongest genuine-MADE example

Showcase shot 10 (clean swish, correctly predicted MADE): `elevated_frac`
0.806, `median_rel` 4.07 — real, non-trivial local motion. **But its panel
image (Section L) shows the "peak" frame is dominated by the shooter's own
post-release movement, not clearly by net deformation** — this is reported
as the strongest quantitative MADE example while being transparent that its
visual justification is not clean.

## K. Strongest genuine-MISS counterexample

Showcase shot 8 (airball, correctly predicted MISSED): lowest `elevated_frac`
(0.829, still high in absolute terms) and lowest `median_rel` (1.73) among
showcase's clean-outcome references — the *most* separated pair in the
whole table, but the gap to shot 10 is not large, and shot 9's own value
(the target rattle) sits *above* shot 10's clean-make value on `elevated_frac`,
undermining any hoped-for MADE > MISSED ordering.

## L. Known false-MADE Shot 9 results (showcase and V4)

**Both show the HIGHEST `elevated_frac` of every shot checked in their
respective video** (showcase 9: 0.905, highest of 7; V4 9: 0.912, highest
of 7) — **higher than every genuine clean make inspected, in both videos.**
This is the opposite of the hoped-for direction (more net/structure
evidence for a genuine make). Direct visual inspection of both panels
(`data/diagnostics/net_motion_shadow/showcase_shot09.png`,
`.../v4_shot09.png`) shows why: showcase shot 9's peak-motion frame is
dominated by the shooter walking through/near the control region; V4 shot
9's peak-motion frame shows the **ball itself** clearly visible as the
dominant bright blob at the net ROI, with the shooter also large and
un-masked in the wider scene — i.e. **in both cases, the elevated ratio is
plausibly explained by uncontrolled confounds (shooter motion, incomplete
ball masking), not by net/structure deformation specific to a rattle.**
This is the clearest single piece of evidence against this representation:
it does not separate the known dangerous case from ordinary makes, and its
own diagnostic imagery shows why.

## M. Cross-video consistency

The *direction* of the finding is consistent across both videos: in both,
the known false-MADE/rattle case shows the highest `elevated_frac`, not the
lowest, and genuine makes don't cluster distinctly apart from misses on
either metric. This consistency is itself informative — but it is
consistency in a **problem** (both videos share the same confound
mechanisms: a shooter remaining in frame, and, for V4, sparse ball masking)
rather than consistency in a **useful signal**.

## N. New fitted constants introduced

**Exactly two, both fixed by physical reasoning before any real-video
evaluation and never adjusted afterward:**

1. `NET_ROI_VERTICAL_SPAN_RIM_RADII = 2.0` — net ROI extends 2 rim radii
   below the rim (a net's visible drop is commonly on the order of the
   rim's own diameter).
2. `BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS = 0.5` — regulation basketball
   radius is roughly half a regulation rim's radius (real equipment
   proportions), used only as a fallback when a real per-frame ball radius
   isn't available.

Neither was chosen, tested, or adjusted by checking which value makes any
labeled showcase or V4 shot separate correctly — both were fixed in the
module's docstring before the real-video evaluation script was even run.
The "elevated" ratio-> 1.0 comparison used throughout is a zero-parameter
structural baseline, not a third fitted constant.

## O. (see N — duplicate letter in task template, answered together)

## P. Representation useful?

**NO, not as currently constructed.** The core intended signal (net/structure
motion, isolated from the ball and from other movers) is not reliably
isolated by this pass's ROI-and-frame-differencing approach: control regions
are contaminated by the shooter's own body in every inspected panel, and
V4's sparse ball data leaves the ball itself visibly unmasked in at least
one inspected "peak" frame. The measured signal, whatever it currently
reflects, points in the wrong direction on the one case it most needed to
get right (Section L).

## Q. Recommendation

**STOP HANDCRAFTED NET-MOTION APPROACH**, as implemented this pass. This is
not a rejection of "temporal visual change around the rim" as a concept —
Section M's cross-video consistency shows the *measurement apparatus*
behaves the same way on both videos, which is a meaningful, if
disappointing, result — it is a rejection of *this specific,
frame-differencing-with-adjacent-controls* implementation, for two concrete,
fixable-in-principle reasons neither of which was addressed this pass (per
instruction: report, don't fix):

1. **Shooter contamination of control regions** — the control ROIs need to
   actively account for the shooter's own position (e.g. by reusing the
   pipeline's already-computed person/pose bounding box to mask the shooter
   the same way the ball is masked), not just be placed at a fixed offset
   from the net ROI.
2. **Ball-masking completeness** — reliable masking needs a real per-frame
   ball radius, which requires re-running detection (explicitly out of
   scope this pass) or a denser cached trajectory than currently exists for
   V4.

## R. If STOP — what would be required next

**Not necessarily more labeled data or a learned model** — the two
confounds identified above are addressable with the SAME existing detection
outputs already computed elsewhere in the pipeline (person/pose bounding
boxes for shooter-masking; a full, non-sparse per-frame ball trajectory
with real radius for complete ball-masking), not new labels or training. A
next attempt would need: (a) person-region masking reusing existing
pose/person-detection output, (b) a dense, real (not sparse-sampled or
proportion-estimated) ball radius per frame for both videos, and (c) a
re-evaluation of whether, with those two confounds controlled, net/structure
motion separates the known cases — before considering whether a learned
approach (Option C from `docs/OUTCOME_NEXT_REPRESENTATION_DECISION.md`) is
ever warranted. This is a scoped engineering correction, not a data
shortfall, and is explicitly not being implemented this turn.

## S. Production unchanged confirmation

Confirmed — `git status` shows no changes under `app/events`, `app/pipeline`,
`app/vision`, `app/tracking` this pass.

## T. Final test count

**217 passed, 0 failed** (197 production + 12 reversal-shadow + 8 new
net-motion-shadow tests), re-run this pass to confirm.

---

# Part 2 — Controlled measurement (final allowed experiment)

Isolates whether Part 1's two identified confounds (shooter motion in the
control ROIs, incomplete ball masking) were the actual cause of Part 1's
failure to separate outcomes, by reusing ArcVision's own already-computed
person detection and RF-DETR ball detection — run only over the same
bounded shot windows as Part 1, never the full video — to mask both
properly this time. The core representation (frame-differencing, net ROI
vs. adjacent controls) is unchanged; no ROI geometry, no cutoff, no new
constant. Per instruction, this is the last experiment on the handcrafted
net-motion concept.

## A. Files changed

- `app/research/net_motion_resolver.py` — extended (not rewritten):
  `PersonSample` dataclass; `BallSample.source` field
  (`"detected"`/`"interpolated"`); `_person_mask`; `analyze_net_motion_from_frames`
  gained an optional `person_by_frame` parameter and now masks person+ball
  from **all three** regions (net + both controls, previously only the net
  ROI was ball-masked and controls were unmasked); new completeness fields
  (`person_mask_available_series`, `ball_mask_source_series`,
  `n_fully_clean_pairs`). Part 1's public function signature and all Part 1
  tests remain valid unmodified (new parameters default to `None`/off).
- `tests/research/test_net_motion_resolver.py` — 8 new Part 2 tests appended.
- `scripts/net_motion_shadow_eval_v2.py` — new controlled real-video
  evaluation script.
- `data/diagnostics/net_motion_shadow/*_part2.json`, `*_part2.png` — new
  diagnostic outputs, alongside (not replacing) Part 1's originals.

## B. Production untouched

**YES** — confirmed via `git status`: no changes under `app/events`,
`app/pipeline`, `app/vision`, `app/tracking`.

## C. Tests

197 production + 12 reversal-shadow + 8 Part 1 net-motion + **8 new Part 2
net-motion tests = 225 passed, 0 failed.**

## D. Person masking source/method

Reuses the pipeline's existing `YoloMultiDetector` person detections and
`PrimaryShooterSelector` (the same classes `run_pipeline()` itself uses) to
obtain a real per-frame shooter bounding box — a fresh selector instance
per shot (shot windows are chronologically disjoint, so no shared state is
needed or used across shots). No added margin around the reported box; no
new constant.

## E. Dense ball masking source/method

Reuses the pipeline's existing `RFDETRBallRimDetector` + `BallTracker` (the
same classes `run_pipeline()` uses) to obtain a real per-frame ball
center/radius with true `DataSource` provenance (`DETECTED`/`INTERPOLATED`/
`PREDICTED`/`UNAVAILABLE`), run fresh per shot. Unlike Part 1's V4
evaluation (sparse, tight-band-only samples with an estimated radius),
every target frame in every shot's window was run through the real
detector this time.

## F. Inference actually rerun

**YES, RF-DETR ball/rim + YOLO person**, exactly as authorized — but bounded
strictly to the same 14 shots' windows as Part 1 (a single sequential decode
pass per video, skipping inference on every frame outside those windows;
frame-index *seeking* was deliberately avoided as unreliable on compressed
video — the same reasoning already applied earlier this session). No pose
estimation, no hoop re-aggregation, no full-video run.

## G. Masking completeness

Dramatically better than Part 1, on both videos:

| | Person available | Ball DETECTED (not interpolated/predicted/missing) |
|---|---|---|
| Showcase (7 shots) | 55/55 to 68/68 — **effectively 100%** every shot | 53/64 to 59/68 — **83–97%** per shot |
| V4 (7 shots) | 58/58 to 72/72 — **100%** every shot | 58/58 to 72/72 (**100%**) for 4 of 7 shots; 59/61–61/65 (**93–97%**) for the other 3 |

This is a genuine, large improvement over Part 1 (which had zero person
masking and only sparse, tight-band-only ball samples for V4) — the
confounds Part 1 flagged were, this time, actually controlled for.

## H. Showcase before/after

| Shot | Truth | elevated_frac before | elevated_frac after | median_rel before | median_rel after |
|---|---|---|---|---|---|
| 1 | MADE | 0.759 | 0.759 | 2.36 | 2.07 |
| 3 | MADE | 0.806 | 0.806 | 2.91 | 2.91 |
| **9** | **MISSED (rattle)** | **0.905** | **0.905** | 2.58 | 2.58 |
| 10 | MADE (correct) | 0.806 | 0.806 | 4.07 | 3.98 |
| 11 | MADE | 0.783 | 0.783 | 7.40 | 5.15 |
| 5 | MISSED (correct) | 0.839 | 0.875 | 2.34 | 2.38 |
| 8 | MISSED (correct) | 0.829 | 0.829 | 1.73 | 1.73 |

## I. V4 before/after

| Shot | Truth | elevated_frac before | elevated_frac after | median_rel before | median_rel after |
|---|---|---|---|---|---|
| **9** | **MISSED (known false-MADE)** | **0.912** | **0.912** | 2.07 | 2.07 |
| 17 | MISSED (dangerous) | 0.617 | 0.617 | 1.13 | 1.13 |
| 21 | MISSED (dangerous) | 0.469 | 0.469 | 0.96 | 0.96 |
| 15 | MADE (correct) | 0.606 | 0.606 | 1.12 | 1.15 |
| 19 | MADE (correct) | 0.790 | 0.790 | 1.81 | 1.82 |
| 4 | MISSED (correct) | 0.469 | 0.500 | 0.95 | 0.99 |
| 5 | MISSED (correct) | 0.558 | 0.558 | 1.06 | 1.06 |

**The central finding of Part 2: these numbers are, shot for shot, nearly
identical before and after masking** — several are exactly unchanged
(showcase 3/8/9; V4 9/17/21/5), the rest shift by hundredths. This is the
opposite of what Part 1's confound hypothesis predicted (a large shift once
the shooter and ball were properly excluded).

## J. Showcase Shot 9 finding

`elevated_frac` unchanged at 0.905 — still the highest of the 7 showcase
shots evaluated, still above genuine clean make shot 10 (0.806). Its
diagnostic panel (`showcase_shot09_part2.png`) shows the control ROIs
correctly empty at the peak frame (the shooter is visibly well clear of
them there) — masking wasn't even substantially engaged for this specific
peak moment, which is itself part of why the number didn't move.

## K. V4 false-MADE finding

`elevated_frac` unchanged at 0.912 — still the highest of the 7 V4 shots
evaluated, still above both genuine correct makes (15: 0.606, 19: 0.790).
Its diagnostic panel (`v4_shot09_part2.png`) shows the ball **still clearly
visible** as a bright blob at the net ROI in the peak-motion diff, despite
100% ball-detected coverage (58/58) for this shot. Investigated why: this
module's ball mask is a single circle centered on one frame's detected
position; a fast-moving ball's frame-to-frame difference footprint spans
its full displacement between the two frames, not just a static disc at one
endpoint — a real, previously-unidentified limitation of this simple
masking approach, distinct from "no detection available" (Part 1's
diagnosis). This is reported as a new, specific finding, not fixed.

## L. Strongest clean genuine-MADE evidence

Showcase shot 10 (67 pairs, 58 fully clean) and V4 shot 19 (62 pairs, 62
fully clean) are the best-supported genuine-MADE references. Both panels
show a real, non-trivial motion signature at their peak frame, concentrated
around the rim/backboard/pole structure — but **visually similar in
character** to the rattle/false-MADE panels (Sections J/K), not distinctly
"net-like" in a way a human could reliably tell apart from the dangerous
cases without already knowing the answer.

## M. Strongest clean genuine-MISS/rattle evidence

V4 shot 21 (64 pairs, 60 fully clean, `elevated_frac` 0.469 — the lowest
of any V4 shot checked) is the cleanest correctly-behaving MISS reference
this pass. Showcase shot 9 and V4 shot 9 (Sections J/K) are the
best-supported rattle/false-MADE evidence, and both remain the *highest*,
not lowest, `elevated_frac` in their video even under full masking.

## N. Visual attribution results

Across every peak-frame panel inspected this pass (showcase 9, 10; V4 9,
15), the dominant bright region in the amplified diff visualization sits
around the pole/backboard/rim structure area at the top of each wide-FOV
frame — plausibly **NET/STRUCTURE** motion in general character, but not
cleanly distinguishable from **AMBIGUOUS** (fine structural vibration,
video compression artifacts amplified 4x for visibility, or residual
ball-motion-blur per Section K) without an unjustifiable amount of
case-by-case visual judgment calls. No panel this pass showed a clean,
unambiguous **PERSON**-attributable spike (masking is working as intended
there) — the remaining ambiguity is between NET/STRUCTURE and
BALL/compression-noise, not primarily person contamination anymore.

## O. Cross-video consistency

**Consistent, again, in the same direction as Part 1**: on both showcase
and V4, the known dangerous case shows the highest `elevated_frac` of the
shots checked, and masking (now genuinely thorough, per Section G) did not
change this. This consistency now carries more weight than Part 1's did,
specifically because the two suspected confounds have been controlled for
and the result didn't move — it is no longer plausible to attribute the
non-separation to those two specific contamination sources.

## P. New fitted constants introduced

**NO.** The two Part 1 constants (`NET_ROI_VERTICAL_SPAN_RIM_RADII`,
`BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS`) are unchanged. No new constant was
added for person masking (uses the detector's own reported box directly)
or for ball-source handling (a categorical label, not a numeric threshold).

## Q. Representation useful?

**NO.** Controlling for both previously-identified confounds did not
materially change the measurements or unlock separation — the
representation itself, not measurement contamination, is the limiting
factor.

## R. Recommendation

**STOP HANDCRAFTED VISUAL-MOTION ENGINEERING.** Per instruction, this was
the final allowed experiment on this concept; no Pass #5C is proposed.

## S. If STOP — what would actually be required next

Reliable automatic resolution of this ambiguity most likely requires a
**learned temporal representation** (Option C from
`docs/OUTCOME_NEXT_REPRESENTATION_DECISION.md`), not further handcrafted
feature engineering — two independent handcrafted attempts (trajectory
reversal, Sept. earlier this session; net-motion, this document) have each
looked promising in isolation and failed to generalize or separate outcomes
once properly controlled. That option remains blocked on data: this
project has on the order of dozens of labeled shots across only 2 camera
setups, one to two orders of magnitude short of what a learned classifier
would need (already established in `docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`
Section 7 and reconfirmed in `docs/OUTCOME_NEXT_REPRESENTATION_DECISION.md`
Sections 5–6 — no public MADE/MISS-labeled dataset is known to exist in
current project sources either). **Substantially more labeled temporal
data would need to be collected before a learned approach could be
responsibly attempted** — this is a data-collection problem now, not an
engineering one.

## T. Production unchanged confirmation

Confirmed — `git status` shows no changes under `app/events`,
`app/pipeline`, `app/vision`, `app/tracking` this pass.

## U. Final test count

**225 passed, 0 failed** (197 production + 12 reversal-shadow + 16
net-motion-shadow tests [8 Part 1 + 8 Part 2]), re-run this pass to confirm.
