# Outcome Visual Information Audit — Is MADE/MISSED Visually Resolvable?

**Date:** 2026-09-09
**Scope:** ARCHITECTURE FEASIBILITY RESEARCH ONLY. No production file was modified.
**Zero production files changed. Test baseline unchanged: 197/197.**

This audit asks a question the previous forensic pass (`docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md`)
could not: is MADE vs. MISSED actually visible in the raw video frames around rim
interaction, even where the current trajectory-derived signals (drift, occlusion
dip, candidate-pair existence) cannot resolve it? If so, the limitation is in what
our feature representation keeps, not in monocular projection itself.

Two new read-only diagnostic scripts were added and run:
`scripts/extract_rim_interaction_clips.py`, which crops a fixed region around the
already-known hoop center (from the existing forensic reports) for every candidate/
far-descent frame of a shot and tiles them into a labeled contact-sheet PNG. 20
contact sheets were generated under `data/diagnostics/rim_interaction_clips/`: all
11 showcase shots, and 9 Video 4 shots covering genuine MADE, genuine MISSED, the
known false MADE, the dangerous false-MISSED-on-true-MADE cases, and the two shots
that would become false MADE under the already-rejected exhaustive-search
experiment. Every sheet was inspected directly (not inferred from metadata) before
comparing against ground truth.

---

## 1-2. Rim-interaction clips + human-visibility audit

| Shot | Truth | Current pred | Visual call (made BEFORE checking truth) | Match? |
|---|---|---|---|---|
| Showcase 1 | MADE | unknown | AMBIGUOUS — ball swings right then left across the rim before dropping; plausible rim-assisted make, not crisp | leans correct |
| Showcase 2 | MADE | unknown | **CLEARLY MADE** — clean, continuous, single-direction fall through the net | correct |
| Showcase 3 | MADE | unknown | AMBIGUOUS — ball circles/oscillates near the rim (right→left→in→up-right→down) before dropping; a plausible "rim roll," not crisp | leans correct |
| Showcase 4 | MADE | missed (0.45) | **CLEARLY MADE** — clean top-to-bottom pass through the net, no reversal | correct |
| Showcase 5 | MISSED | missed (0.97) | **CLEARLY MISSED** — airball, travels across the top of frame, never approaches the rim | correct |
| Showcase 6 | MADE | unknown | **CLEARLY MADE** — clean pass-through, net visibly engaged | correct |
| Showcase 7 | MADE | missed (0.97) | **CLEARLY MADE** — clean, continuous pass through the net, no reversal | correct |
| Showcase 8 | MISSED | missed (0.87) | **CLEARLY MISSED** — airball, never approaches the rim | correct |
| Showcase 9 | MISSED | **made (0.58)** | **CLEARLY MISSED** — ball dips into the rim opening, then visibly bounces back UP and sideways, exits away from the hoop | correct |
| Showcase 10 | MADE | made (0.70) | **CLEARLY MADE** — clean swish (already correctly predicted) | correct |
| Showcase 11 | MADE | missed (0.49) | AMBIGUOUS — small/far ball, passes along the rim's right edge; plausibly through, not crisp | leans correct |

**8 of 11 (73%) are unambiguous to a human eye**, and in every one of those 8 cases
the human call matches frozen ground truth — including all three of the highest-
confidence WRONG production calls (shots 4, 7 at 0.45/0.97, and 9 at 0.58) and the
two correctly-abstaining airballs (5, 8). Only 3 of 11 (1, 3, 11) are genuinely
ambiguous even to a human working from still frames, and even those visually lean
toward the correct (MADE) answer rather than looking like clean misses.

Video 4 cross-check (5 shots inspected in detail): shot 9 (truth MISSED, pred MADE
0.59) shows the same touch-then-bounce-out signature as showcase shot 9. Shots 11
and 15 (truth MADE) both show the same clean, continuous, net-engaged pass-through
as showcase shots 2/4/6/7/10 — shot 11 is production's 0.97-confidence wrong MISS,
visually unambiguous as a make. Shot 17 (one of the two dangerous exhaustive-search
false-MADE cases, truth MISSED) shows the identical touch-then-reverse-direction
signature as both shot 9s. Shot 21 (the other dangerous case) shows a distinct but
equally clear miss signature: the ball glances off the rim's near edge and
deflects away to the side without ever dipping into the opening.

**Conclusion: monocular projection is NOT the fundamental limitation for the
majority of this problem.** The information needed to call 8 of 11 showcase shots
correctly — including every high-confidence wrong call — is visibly present in the
raw frames. The current ball-center/rim-center trajectory abstraction is discarding
it.

## 3. What visual information is being lost

Directly inspected (not assumed) against the checklist:

- **Ball bounding-box size / aspect changes:** not separately inspected pixel-by-
  pixel this pass; the crops show the ball is small (≈15-20px raw, upscaled 10x
  here) and roughly circular throughout — unlikely to carry a strong depth signal
  at this resolution, but not conclusively ruled out.
- **Ball/rim overlap shape, ball appearing inside the rim opening:** **clearly
  visible and informative.** Every genuine make shows the ball unambiguously
  positioned inside the rim's visual opening for 2-4 consecutive frames (showcase
  2, 4, 6, 7, 10; V4 11, 15). The false-MADE rattle (showcase/V4 shot 9) shows the
  ball touching/entering that same region only briefly before visibly re-emerging
  above/beside it.
- **Ball partially disappearing behind front/back rim, ball visibility through
  net:** **clearly visible.** V4 shot 15 shows the net visibly draped over/wrapped
  around the ball mid-frame — strong, directly observable physical contact
  evidence current tracking never records (only the ball's center point is kept;
  the net's appearance is discarded entirely).
- **Net motion:** visibly present in multiple genuine-make sequences (net moving/
  deforming as the ball passes) and not investigated frame-differenced quantitatively
  this pass, but qualitatively a strong candidate signal.
- **Rim occlusion ordering (front rim vs. ball vs. back rim vs. net):** visible in
  the crops (e.g., showcase shot 9's ball is briefly hidden behind the front rim
  edge around the moment of contact) but not extracted as a separate signal.
- **Ball appearing below rim while horizontally contained (a genuine make's
  natural signature) vs. reappearing ABOVE rim height after initial contact (the
  rattle signature):** **the single most important, most clearly and consistently
  visible discriminator found in this audit.** Every miss inspected (showcase 9,
  V4 9, V4 17, V4 21) shows the ball's height/position reversing back toward or
  above the rim, or deflecting sharply sideways, within a few frames of first
  touching the rim region. Every make inspected shows a single, continuous,
  monotonic descent with no such reversal.
- **Backboard interaction, rebound direction:** not present in any of the inspected
  clips (this hoop/backboard combination didn't produce a backboard-assisted shot
  in the sampled set).
- **Several-frame appearance pattern vs. center coordinates:** this is exactly
  the gap. The current MADE/MISS logic reduces each frame to one (x, y, confidence)
  triple and evaluates isolated `(a, b)` pairs; a human instead reads the whole
  short sequence as a single continuous or discontinuous motion. The "does the
  ball's path reverse direction after first touching the rim" question requires
  looking at the SEQUENCE, not any one pair — this is presently unrepresented.
- **Local optical flow around ball/net, detector confidence pattern, bbox width/
  height/aspect:** not directly inspected pixel-level this pass (would require
  additional instrumentation); flagged as unverified, not ruled in or out.

## 4. Shot 9 — the key negative, examined directly

Showcase shot 9 (truth MISSED, current pred MADE at 0.58 confidence,
`ball_crossed_rim_band_top_to_bottom`) — frames f2430-2493, `data/diagnostics/rim_interaction_clips/showcase_shot09.png`:

The ball approaches from the upper right and descends toward the rim (f2430-2442).
By f2445-2457 it has visibly entered the rim's opening — genuinely indistinguishable
from a make at this point, matching the makes examined in Section 1-2. Then, at
f2460 (only 0.1s / 3 frames later), the ball reappears clearly **above and to the
right of the rim** — a direct visual reversal no genuine make in this dataset ever
shows. By f2463-2466 it has moved further right and down, away from the hoop
entirely, and the rim sits empty for the remainder of the window. **This is a
textbook, unambiguous rim rattle to a human viewer: the ball engaged the rim, was
briefly inside its opening, and then bounced back out.**

V4 shot 9 and V4 shot 17 (both truth MISSED, both dangerous false-MADE risks) show
the same touch-then-reverse pattern, though V4's thinner/sparser-looking net and
different camera angle made the critical 2-3 frames somewhat harder to read with
full confidence than the showcase footage's clearer, denser net — a genuine,
video-dependent difference in how legible this signal is, not just a labeling
artifact.

**Answer: yes, Shot 9's miss is visually distinguishable from a make — but only by
looking at what happens in the 2-4 frames immediately AFTER the ball first appears
to enter the rim opening, which the current single-pair evaluation never examines.**

## 5. Shots 1/2/3/4/6/7/11 — individually

| Shot | Make visually obvious? | Ball visible entering rim? | Net interaction visible? | Ball visible below rim after? | Tracking loses discriminating frames? | Tracker switches objects? |
|---|---|---|---|---|---|---|
| 1 | No — ambiguous, plausible bank/rim-assist | Yes, briefly | Not clearly | Only a brief, small reappearance at frame edge | Not obviously — more a genuinely complex real trajectory (real lateral bank motion) than a tracking failure | No signs observed |
| 2 | **Yes** | Yes, clearly | Yes | Yes, clean exit below | No | No |
| 3 | No — ambiguous, "rim roll" pattern | Yes, appears to enter then re-emerge briefly | Not clearly | Yes, small, exits lower-center | Not obviously | No signs observed |
| 4 | **Yes** | Yes, clearly | Yes | Yes, clean exit below-right | No | No |
| 6 | **Yes** | Yes, clearly | Yes | Yes, clean exit | No | No |
| 7 | **Yes** | Yes, clearly | Yes | Yes, clean exit | No | No |
| 11 | No — ambiguous, small/far | Passes along rim's right edge | Not clearly resolvable at this size | Yes, small, continues down-right | Ball is genuinely small at this shooting distance — a real resolution/scale limitation, not a tracking bug | No signs observed |

**Far Shot 11, specifically:** the ball is visibly smaller than in every other
inspected shot (consistent with "intentionally much farther away"), and the crop
shows it tracking along the rim's near-right edge rather than clearly through the
opening center. This looks like a genuine resolution limit — at this scale, even a
human is not fully certain from a still-frame contact sheet whether the ball
clipped the front rim and continued through, or grazed past it. Full-motion video
(not stills) would very likely resolve this more confidently than the sampled
frames do, since human motion perception integrates continuity that discrete frames
lose — this is a real caveat on this whole audit's methodology, not specific to
Shot 11.

## 6. Architecture options

| Option | Input | Existing data sufficient? | Training required? | Expected generalization | Implementation complexity | Runtime cost | Overfitting risk |
|---|---|---|---|---|---|---|---|
| **A. Improved deterministic multi-frame geometry** (e.g., detect a height/position reversal in the frames immediately following first rim contact, using the existing tracked ball-center sequence, not a new visual signal) | Existing ball trajectory only | Likely yes — the reversal is visible in existing tracked points (Section 4), though a first attempt at operationalizing it via the current above/below-tight-band classification did NOT cleanly capture it (the reversal frame in showcase shot 9 fell outside the existing "above-tight" classification) — a genuinely redesigned per-frame classification would be needed, not a one-line change | No | High if it works — same normalization properties as existing geometry, no learned weights to transfer | Medium — needs real design/iteration, not proven complete by this pass | Negligible, same as current | Low — still a hand-designed, physically-motivated rule |
| **B. Optical-flow / motion evidence around rim/net** | New: dense/sparse flow in the rim-crop region | No — not currently computed anywhere in the pipeline | No (classical CV, not learned) | Plausible, physically motivated (net deformation is a real, camera-angle-somewhat-robust cue) | Medium-high — new per-frame processing stage, tuning flow parameters | New cost, real-time-feasible at this crop size | Low-medium — flow itself isn't learned, but thresholds on it could be if handled carelessly |
| **C. Tiny temporal image classifier on the rim-interaction crop** | New: raw pixels, ~15-25 frame clip | No — needs labeled clips | **Yes** | Unknown without data (Section 7) | Medium (a small 3D-CNN/video-transformer head is not exotic) but full ML pipeline (labeling, training, eval, versioning) is new | Small if the crop and clip length stay bounded | **High** with only this project's footage (see Section 7) |
| **D. Object detector extension for additional visual state** (ball bbox aspect/size as an occlusion-depth proxy) | New: bbox width/height/aspect from the existing detector, not currently retained per-frame in the trajectory | Partially — RF-DETR already outputs boxes, but the pipeline currently keeps only the center point | Possibly (if the raw box signal alone isn't discriminating enough, would need a learned combiner) | Uncertain — ball is small (≈15-20px) at this resolution, aspect/size changes may be dominated by noise | Low-medium to plumb the box through; unknown value until tried | Negligible | Low if kept as raw geometry, higher if a learned combiner is added |
| **E. Explicit net-motion / ball-through-net detection** | New: appearance/motion specifically in the net region below the rim | No — not currently computed | Possibly not (could be handcrafted: net-region pixel change / deformation magnitude) or could be learned | Plausible but net appearance (color, density, motion against background) varies more across courts/videos than ball/rim geometry — the V4-vs-showcase net-legibility difference noted in Section 4 is a real generalization risk | Medium-high — a new, physically-motivated but nontrivial CV component | New cost | Medium — more video-appearance-dependent than A |

## 7. Training data reality check (NOT executed — analysis only)

- **Labels required:** per-shot MADE/MISSED ground truth, already exists for V1-V4
  and the showcase video combined — roughly **15-20 labeled shots total** across
  every video this project has ever evaluated.
- **Approximate clips needed for a viable learned classifier:** typically hundreds
  to low thousands of labeled examples for a *small* temporal classifier to
  generalize past memorizing its training set, even fine-tuning a pretrained
  backbone; considerably more without one. **This project's entire labeled corpus
  (≈15-20 shots) is roughly one to two orders of magnitude short of that**, even
  before considering that several of those shots share the same camera/hoop
  (V1-V4 are the same setup; the showcase is a second setup) — true diversity
  (different courts, hoops, lighting, camera angles/distances) is far smaller
  still.
- **Public basketball make/miss video datasets in this project's data sources:**
  **none found.** `data/datasets/` contains only ball/rim *object-detection*
  datasets (bounding boxes for ball and rim: `basketball_ball_rim*`,
  `basketball_shooting_robot_raw` — a Roboflow ball/rim detection set) — no
  shot-outcome-labeled video clips of any kind. `scripts/download_basketball_dataset.py`
  confirms the only integrated external source is that same ball/rim detection
  dataset.
- **Synthetic augmentation:** could stretch existing clips (temporal jitter, crop
  jitter, flips, brightness/color augmentation) but cannot manufacture new
  *outcomes* — augmentation multiplies existing labeled examples, it doesn't
  address the fundamental shortage of distinct real makes/misses.
- **Whether a pretrained video/image backbone could help:** plausibly, and this is
  the most realistic path IF a learned approach is pursued later — fine-tuning a
  small pretrained video backbone (e.g., action-recognition-style) on the
  rim-crop clips needs far fewer labeled examples than training from scratch, but
  still meaningfully more than ~15-20 shots to avoid simply memorizing this
  project's own hoops.

**Conclusion: current V1-V4 + showcase footage is far too small to train any
learned classifier responsibly this session** — the risk isn't just weak
generalization, it's that a model trained on ≈15-20 examples spanning 2 camera
setups would almost certainly just be memorizing those 2 setups' idiosyncratic
appearance, which is a much more dangerous failure mode for a showcase demo than
today's honest UNKNOWN.

## 8. Product goal, restated

The requirement is trustworthy MADE/MISSED without UNKNOWN spam, without
hardcoding, timestamp special-casing, manual overrides, hiding UNKNOWN behind fake
predictions, or arbitrary constant-tuning. Section 6/7 together point toward: the
visual information needed genuinely exists (Sections 1-4), a **deterministic**
geometric refinement (Option A) is the only path that doesn't require new training
data or a new CV subsystem, and it is *not yet proven complete* — a first
attempt at expressing "does the ball reverse direction / reappear above rim height
shortly after first rim contact" using the currently-tracked points did not fall
directly out of the existing above/below-tight-band classification and would need
real design work to get right, tested the same rigorous way the segmentation and
prior outcome forensic passes were.

## 9. Decision

Confirmed: no production file was modified this turn. No production constant was
added. Two new read-only diagnostic scripts were added under `scripts/`, and 20
diagnostic PNG contact sheets were generated under `data/diagnostics/rim_interaction_clips/`
— no other files were touched.

---

## Final report

**A. How many of the 11 showcase outcomes are visually obvious from rim crops:**
8 of 11 (shots 2, 4, 5, 6, 7, 8, 9, 10) — and in all 8, the human visual call
matches frozen ground truth, including the three highest-confidence wrong
production calls.

**B. Which are visually ambiguous:** shots 1, 3, and 11 — all three genuine
MADE shots where the visual sequence shows real ambiguity (a rim-assisted bank,
a rim roll, and a small/far ball respectively), though all three lean toward the
correct MADE answer rather than looking like clean misses.

**C. Whether Shot 9's miss is visually distinguishable from a make:** yes, clearly
— the ball enters the rim opening (indistinguishable from a make at that instant)
then visibly reappears above/beside the rim 2-4 frames later and exits away from
the hoop. This exact touch-then-reverse pattern also appears in V4's shot 9 (the
known false MADE) and V4's shot 17 (one of the two dangerous exhaustive-search
false-MADE cases).

**D. Whether Shot 11's make is visually distinguishable:** not with full
confidence from still frames — genuinely ambiguous due to the ball's small size at
this shooting distance, though it visually leans toward "made" (passes along the
rim's edge, continues down toward/under the hoop, never clearly escapes sideways
and away the way a real miss does in this dataset).

**E. What useful information current trajectory representation loses:** whether
the ball's path reverses direction (or deflects sharply sideways) shortly after
first rim contact — a sequence-level property no single `(a, b)` crossing-pair
check can see. Also loses directly-observable net deformation/wrap (visible in
several genuine makes) and rim-occlusion-ordering cues entirely, since only a
ball center point and confidence value are retained per frame.

**F. Best deterministic architecture, if any:** Option A — extend the existing
geometry to explicitly check for a post-contact direction reversal using the
already-tracked points. Promising and physically well-motivated by this audit, but
**not proven complete**: a first attempt showed the existing above/below-tight-band
point classification does not automatically capture the reversal frame (it fell
outside the tight band in showcase shot 9's data) — genuine follow-up design and
testing would be needed, not a one-line change.

**G. Best learned architecture, if any:** Option C (tiny temporal classifier on
the rim-interaction crop) is the most likely to work given how visually clean the
distinguishing pattern is — but is gated entirely on data availability (Section 7).

**H. Whether training is required:** not for Option A (the recommended next step);
yes for Option C, and this project does not currently have enough labeled data to
pursue it responsibly.

**I. Rough amount/type of training data needed:** hundreds to low thousands of
labeled make/miss clips across multiple hoops/cameras/lighting conditions for a
learned approach to generalize; this project has ≈15-20 across 2 camera setups —
roughly one to two orders of magnitude short. No public dataset of this kind exists
in the project's current data sources; only ball/rim object-detection data does.

**J. Expected ability to classify all 11 showcase shots correctly:** even a
successful Option A implementation would not resolve shots 1, 3, and 11 with full
confidence (they are genuinely ambiguous even to a human from still frames) — a
realistic target is recovering the 6 currently-wrong-or-abstained-but-visually-
obvious shots (2, 3-partially, 4, 6, 7, 9's correct MISS, 11-partially), not all 11.
Full-motion (not still-frame) review would likely do better on 1/3/11 than this
audit could, which is itself informative for where remaining difficulty lives.

**K. Expected cross-video generalization:** reasonable for Option A (same
underlying geometric signal, both videos showed the same touch-then-reverse
pattern for their false-MADE cases). More uncertain for any net-appearance-based
option (B/E) — V4's net was visibly harder to read than the showcase's in this
audit, a real, observed cross-video appearance difference.

**L. Implementation complexity:** Option A is low-to-medium (extends existing
geometry, no new subsystem, but needs real design iteration); Option C is
medium for the model itself but high overall once labeling/training/eval
infrastructure is included; Option B/E are medium-high (new CV processing stage).

**M. Recommended architecture:** Option A (deterministic post-contact reversal
check), as a dedicated follow-up investigation — not implemented this turn.

**N. Recommendation: BUILD** — but only Option A, and only as a next
*investigative* prototype (design + the same test-first, forensic-verified process
used for the segmentation fix), not a training effort. **STOP on Options C/D/E
this session** — insufficient data (C), unproven signal value (D), and higher
appearance-dependence risk (E) all argue against starting them now.

**O. Confirmation zero production files changed:** confirmed — `outcome_detector.py`,
`shot_state_machine.py`, detector, tracker, UI, and demo exporter are all untouched
this turn.

**P. Test baseline remains 197/197:** confirmed (unchanged; no code was modified
this turn, so the suite was not re-run — no change could have affected it).
