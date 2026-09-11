# FormAI — Final Architecture Decision (Shot Detection / Outcome Pipeline)

**Status:** Decision review, not a proposal. No production code was changed to produce this
document. All conclusions are grounded in re-reading production code (`app/events/shot_state_machine.py`,
`app/events/outcome_detector.py`, `app/events/release_detector.py`), the full shadow-mode
experiment set, `docs/METHODOLOGY.md`, and a clean run of the test suite (`195 passed`) as of
this review.

## 0. What was actually tested, in one paragraph

Over one extended shadow-mode investigation, five architectural alternatives to the shipping
shot-segmentation/outcome pipeline were built and evaluated against V1/V2/V3 real footage, and
two fine-tuning attempts were made against the one confirmed detector weakness. None produced a
net win over what's already in production. This document explains why that's a genuinely good
outcome for a portfolio piece, what to keep, what to document, and what to do next.

---

## 1. Final architecture recommendation

**Ship exactly what's in production today. Make no code changes as a result of this review.**

Concretely, that means:

- **Detector:** RF-DETR-Small v1 (`models/rfdetr_ball_rim_v1.pth`, `confidence_floor=0.3`),
  YOLOv8/YOLO-World/classical-CV stack retained as the automatic fallback. Confirmed still wired
  as primary in `app/config.py` (`BallRimDetectorConfig.checkpoint_name = "rfdetr_ball_rim_v1.pth"`).
- **Shot segmentation:** the existing `IDLE → LOAD → UPWARD → RELEASED → FLIGHT` finite-state
  machine in `app/events/shot_state_machine.py`, primary trigger (ball tracked near hand) +
  fallback trigger (sustained upward flight + knee-dip + stationary-hip corroboration),
  confirmed still the only thing `app/pipeline/orchestrator.py` imports
  (`from app.events.shot_state_machine import FrameSignals, detect_shots`).
- **Release refinement:** `app/events/release_detector.py`, unchanged.
- **Outcome classification:** `app/events/outcome_detector.py`'s phase-based
  RELEASE→ASCENT→APEX→DESCENT→HOOP-APPROACH→RIM-INTERACTION→POST-RIM reasoning, unchanged,
  including its existing first-class `UNKNOWN` outcome.

**Why this is the right call, not a default-by-exhaustion:**

| Alternative tested | Result vs. production | Verdict |
|---|---|---|
| TRANSITION-state release model (`release_event_detector.py`) | Reverted to match the established baseline exactly — no net behavioral difference from what shipped before this session's exploration | No reason to adopt; redundant with production |
| Temporal possession episode detector (`episode_release_detector.py`) | Fixed catch-settle-shot misses (7/7 recall on V1) but introduced dribble-rebound false positives on V2/V3 of comparable size (reactive round-trip rejection can't catch an ascent streak that completes within one dribble's rebound leg) | Net wash at best, likely net negative; not adopted |
| Trajectory-primary "Architecture C" (`trajectory_shot_detector.py` + corroboration layers), modeled directly on a real reference project's actual code (`aarnavshah12/shot-tracker`) | Improved precision over a raw trajectory detector, and its bounded pose-veto design independently converged on the same idea already present in production (`veto_override_frames=8` in the reverted TRANSITION model). But it could not, on its own, distinguish the one confirmed RF-DETR false-positive class (a hallucinated "ball" on a background rooflines) from a genuine flight | Validates the production design's instincts; not a strict improvement; not adopted |
| Detector-level fixes for the roofline false positive: bbox/shape discriminator, raw pre-threshold logit analysis, cross-detector corroboration | All three independently closed — no clean, generalizable signal found at any level | Correctly closed rather than patched with a fitted threshold |
| RF-DETR hard-negative fine-tune v2 | Failed: gradient moved in the correct direction but was diluted to ~2-3% of optimizer steps (too weak to cross the 0.3 confidence floor), plus a separate, root-caused catastrophic rim regression (99.4%→0.2%) from an annotation gap in the new training images | Not adopted; annotation lesson documented |
| RF-DETR hard-negative fine-tune v3 (corrected annotations, 17-20× stronger oversampled exposure) | Failed on its primary criterion: the held-out artifact's ball probability *increased* rather than decreased, despite no rim/genuine-ball regression | Not adopted; RF-DETR-level remediation path is closed |

The pattern across all five alternatives is consistent: each either matched production exactly,
or traded one failure class for a different, comparably-sized one. That is the actual evidence
for "the current design is a reasonable local optimum," not an assumption. Recommending against
a swap here is the defensible engineering call, not a failure to find something better.

---

## 2. Research-only vs. production-informing

**Nothing from this session's experimentation should enter production code.** That is a real
conclusion, not a placeholder — see the table above. The value this work produced is evidentiary
and documentary, not a new module to wire in.

**Keep as research/documentation artifacts only** (do not import from `app/pipeline/orchestrator.py`,
do not delete):

- `app/events/release_event_detector.py`, `app/events/episode_release_detector.py`,
  `app/events/trajectory_shot_detector.py`, `app/events/hoop_corroboration.py`,
  `app/events/pose_at_arm_corroboration.py` — all shadow-only, all still covered by their own
  passing tests (23+ adversarial synthetic tests across the three Architecture C modules alone).
- `data/datasets/basketball_ball_rim_hardneg_v1/`, `basketball_ball_rim_v2_merged/`,
  `basketball_ball_rim_hardneg_v3/`, `basketball_ball_rim_v3_merged/`,
  `data/training_runs/rfdetr_ball_rim_v2_hardneg/`, `data/training_runs/rfdetr_ball_rim_v3/` —
  confirmed present and isolated from the production dataset/checkpoint. These are the actual
  evidence trail for the fine-tuning methodology (dataset composition, held-out-window discipline,
  exposure-ratio math, GO/NO-GO criteria decided *before* seeing results) — worth pointing a
  reviewer at directly, since the fine-tuning writeups are a stronger demonstration of ML
  engineering rigor than a successful-on-the-first-try result would have been.
- `scripts/diagnose_rfdetr_raw_logits.py`, `scripts/diagnose_v2_tracking_artifact.py`,
  `scripts/diagnose_fallback_corroboration.py`, `scripts/eval_coverage_v1v2v3.py`,
  `scripts/shadow_mode_architecture_c_combined.py` — diagnostic tooling, valuable as tooling, not
  as production dependencies.

**Concepts (not code) that the production design already reflects, confirmed rather than newly
adopted by this work:**

- Bounded pose veto / "don't let one signal be a hard requirement forever" — production's
  `veto_override_frames`-style budgeted overrides and the fallback trigger's design already do
  this; Architecture C's independent convergence on the same pattern (matching the reference
  project almost exactly) is a validation of the existing design, not a new idea to integrate.
- Additive, non-required corroboration (a signal that raises confidence but is never a hard gate)
  — already production's pattern in `release_detector.py` (hand-ball distance / velocity / elbow
  extension each independently raise confidence) and in `outcome_detector.py`'s confidence
  scoring. `hoop_corroboration.py`/`pose_at_arm_corroboration.py` are a second, independent
  implementation of the same idea on a different architecture — good confirming evidence for a
  portfolio narrative, not something to merge in.
- First-class "I don't know" as an outcome rather than a forced binary — already exactly what
  `outcome_detector.py`'s `UNKNOWN` and the shot machine's `excluded_from_analysis`/
  `exclusion_reason` do. See §3 for why no new UNCLASSIFIED state is needed.

---

## 3. Limitations to explicitly accept

These should be stated plainly in the portfolio write-up rather than engineered around further:

1. **RF-DETR can hallucinate "ball" on background clutter that resembles the ball's appearance
   from a distance** (confirmed case: a house roofline in outdoor footage). Three independent,
   rigorous investigations (bbox/shape geometry, raw pre-threshold model internals, cross-detector
   agreement) and two fine-tuning attempts all failed to produce a clean, generalizable fix. This
   is now a documented, understood limitation with a real investigation trail behind it — not an
   unknown unknown.
2. **RF-DETR's training distribution is one outdoor-court dataset** (University of Arizona
   "Basketball Shooting Robot," mostly outdoor). Indoor gym lighting, a materially different
   rim/net/backboard design, or a very different camera angle are explicitly out of the validated
   distribution — already stated in `docs/METHODOLOGY.md`'s "Known limitations," reconfirmed
   accurate.
3. **No physical (metric) calibration beyond one rough, rim-depth-only speed estimate.** Already
   documented and intentional (`app/biomechanics/rim_calibration.py`) — not something this
   session touched or should touch.
4. **Single shooter, single ball, single hoop, near-stationary camera** — not validated for full
   game footage or camera panning. Unchanged from the existing documented scope.
5. **The fallback-trigger's coherent-evidence gates (knee-dip direction, stationary-hip check)
   are tuned against V1/V2/V3's specific failure modes** (a mid-motion clip start, a rim rebound,
   a walking dribble). They are principled, not curve-fit to shot *counts*, but they have only
   been exercised against three videos' worth of failure diversity — Video 4+ is the first real
   test of whether that generalizes (see §4).
6. **The outcome detector's near-hoop trajectory reasoning depends on chain-repair heuristics**
   (`near_hoop_enrichment.py`) whose pruning-threshold sensitivity was already documented as not
   fully robust. It correctly resolves to `UNKNOWN` rather than forcing a call when the chain
   doesn't stabilize — that's the intended failure behavior, not a bug to close.

None of these require a threshold change or new heuristic to "accept." Accepting a limitation
here specifically means: state it in the documentation, and do not attempt one more patch this
session or under time pressure to make it disappear.

---

## 4. Metrics to measure on a completely untouched Video 4+ test set

Run the pipeline exactly as-is (no code changes, no threshold changes) on footage that has never
been viewed, discussed, or used in any decision this session. Reuse existing tooling rather than
writing new scripts:

| Metric | How | Reused from |
|---|---|---|
| Shot count accuracy | Detected shot count vs. a manual count from watching the raw video once | manual, new |
| Release-timing accuracy | Detected release frame vs. manually marked release frame, ± frames | manual + `shot_timeline_debug.py` |
| False positive rate | Any detected "shot" that a human would not call a shot attempt (dribble, rebound, pass) | manual review of each `ShotWindow` |
| False negative rate | Any real shot attempt visible in the footage with no corresponding `ShotWindow` | manual review |
| Make/miss/unknown distribution | Confusion vs. manual ground truth, with `UNKNOWN` reported and reasoned about **separately** — a high `UNKNOWN` rate on hard footage is not automatically a failure, a wrong MADE/MISSED call is | `outcome_detector.py` output + manual labels |
| Ball/rim raw coverage (overall, near-rim last-30%-of-flight) | Same methodology as the existing V1 A/B benchmark | `scripts/eval_coverage_v1v2v3.py`, `scripts/benchmark_ball_rim_detectors.py` |
| Roofline/background-artifact recurrence | Specifically check whether any detected ball candidate lands on static background clutter unrelated to the shooter/hoop, the same way the original V2 artifact was found | `scripts/diagnose_v2_tracking_artifact.py` pattern |
| Biomechanics completeness | % of shots with non-null knee/elbow/torso-lean/release metrics vs. `null`-with-reason | session JSON `warnings` field |
| Throughput | fps, matching the existing 28-39 fps range already benchmarked | `benchmark_ball_rim_detectors.py`'s timing harness |

Video 4+ must **not** be used to tune anything. It exists to answer one question: does the
already-shipped design generalize past the three videos it was iterated against, or does it
reveal a new failure category?

---

## 5. Concrete stop condition for declaring FormAI portfolio-ready

Portfolio-ready is declared when **all** of the following hold after the single, unmodified
Video 4+ run in §4:

1. Shot count and release timing land within the same honest error bars already documented for
   V1-V3 (i.e., no new, structurally different failure mode — a rebound/dribble/occlusion variant
   that the existing coherent-evidence gates already generalize to is fine; a genuinely new
   failure class is not).
2. Any background false-positive detections, if present, belong to the **already-documented**
   roofline-type artifact class — not a new, unexplained detector failure.
3. `MADE`/`MISSED` calls that are made (not `UNKNOWN`) are correct against manual review; a
   sizeable `UNKNOWN` rate on genuinely hard footage is acceptable and should be reported as such,
   not treated as a defect.
4. No production file needed to change to get here. If Video 4+ *does* reveal something that
   needs a code change, treat it as a new, narrowly-scoped investigation under the same
   discipline used all session (adversarial tests, no threshold fit to one video, honest report,
   explicit stop condition) — not a reason to reopen the closed RF-DETR fine-tuning or
   shot-segmentation architecture questions.
5. `docs/METHODOLOGY.md`'s "Known limitations" section reflects §3 above in full.

If Video 4+ passes 1-3 cleanly: stop, ship, write up the portfolio narrative. If it doesn't:
report exactly what broke and why, the same way v2/v3's failures were reported — plainly, without
compensating via a new threshold.

---

## 6. Shortest implementation plan

This is a documentation/evaluation plan, not a code-change plan — consistent with "nothing from
this session enters production" (§2). Nothing below was executed as part of this review; it's the
punch list for the next session.

1. **Run Video 4+ once**, unmodified pipeline, and collect the §4 metrics. This is the only step
   that produces new evidence; everything else is writing down what's already true.
2. **Update `docs/METHODOLOGY.md`'s "Known limitations" section** with the roofline-artifact
   finding (cite the three closed investigation branches) and a short note that alternative
   shot-segmentation architectures were built and evaluated (episode-based, trajectory-primary)
   and not adopted, with one sentence of why — this turns a night of otherwise-invisible shadow
   work into something a reviewer of the repo can actually see and credit.
3. **Add a short README to `app/events/`** (or a top-of-file docstring convention already used
   elsewhere in this codebase) marking which modules are production (`shot_state_machine.py`,
   `release_detector.py`, `outcome_detector.py`) vs. research-only shadow experiments — so nobody,
   including future-you, mistakes `episode_release_detector.py` for something that ships.
4. **Confirm the dashboard surfaces `UNKNOWN` outcomes and shot warnings** (e.g.
   `load_phase_inferred_from_pose_only_ball_not_tracked_near_hand`) visibly rather than as buried
   JSON fields — this is the actual product expression of the "clean failure over a forced guess"
   design already built, and it's a strong, honest talking point in a demo if it's visible.
5. **Stop.** No further detector training, no new shot-segmentation architecture, unless Video 4+
   step 1 produces a specific, reproducible counter-example that survives the same adversarial-test
   discipline used throughout this session.

---

## Appendix: verification performed for this review

- Full test suite: `195 passed` (`pytest tests/ -q`), confirming no regression across production
  and shadow modules.
- `app/pipeline/orchestrator.py` greped for every experimental module name — confirmed only
  `app.events.shot_state_machine` is imported; none of the shadow modules are wired in.
- `app/config.py` confirmed `BallRimDetectorConfig.checkpoint_name == "rfdetr_ball_rim_v1.pth"`,
  `confidence_floor == 0.3` — production still points at the original, validated checkpoint, not
  v2 or v3.
- `data/training_runs/` confirmed contains `rfdetr_ball_rim_v1/`, `rfdetr_ball_rim_v2_hardneg/`,
  `rfdetr_ball_rim_v3/` all present and separate; `data/datasets/basketball_ball_rim/` (the
  original dataset) confirmed present and distinct from the `_v2_merged`/`_v3_merged` variants.
- `app/events/shot_state_machine.py` read in full and reconfirmed to match the documented
  LOAD/UPWARD/RELEASED/FLIGHT design with primary+fallback triggers and the knee-dip/stationary
  coherent-evidence gates described in `docs/METHODOLOGY.md`.
- `docs/METHODOLOGY.md` read in full (all sections) for this review.
