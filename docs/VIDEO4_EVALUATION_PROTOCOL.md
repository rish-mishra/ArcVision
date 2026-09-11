# Video 4 Evaluation Protocol — Recording + Pre-Committed Ground Truth

**Purpose:** the first test of the now-frozen architecture (see
`docs/FINAL_ARCHITECTURE_DECISION.md`) against footage that had zero influence on any development
decision. This document has two parts that must happen **in order**, both **before** FormAI ever
sees Video 4:

1. **Part A** — how to record it, so it's a fair test and not accidentally adversarial or
   accidentally easy.
2. **Part B** — the ground-truth log you fill in by hand, watching the raw footage only, with no
   FormAI output visible anywhere.

Only after both are complete and locked in does Part C (the evaluation checklist) get applied to
FormAI's actual output. This ordering is the entire point — it's what makes the test honest.

---

## Part A — Recording protocol

**Goal:** ordinary basketball-shooting footage, the exact use case FormAI is built for. Not a
stress test, not a deliberately easy clip.

### Shot count
**15-25 shot attempts.** Enough to make the session-analytics minimums meaningful (the app itself
requires ≥4 samples for consistency stats, ≥2 makes and ≥2 misses for makes-vs-misses comparison,
≥6 shots for trend splits) without turning this into a marathon. Include a **genuine mix of makes
and misses** — don't stop early because you're on a hot streak, and don't reshoot a miss. Whatever
actually happens is the correct footage.

### Duration
One continuous session, roughly **5-15 minutes**, uninterrupted (single video file, no editing
cuts). Natural pace: however long it actually takes you to take 15-25 shots with normal rest
between them.

### Camera placement
- **Stationary** for the whole session — tripod or propped against something solid. No panning,
  no zooming, no handheld follow. (The pipeline assumes a near-stationary camera; this isn't a
  workaround, it's the documented scope.)
- **Side or ~45° angle to the hoop**, similar in spirit to how V1-V3 were framed — not directly
  under the backboard, not from directly behind the shooter.
- Frame the shooter **fully in view, including feet**, for the whole shooting motion (load through
  follow-through). Cropping off the top of a jump shot or the shooter's legs breaks knee-angle and
  hip-translation signals the state machine depends on.
- **Hoop clearly visible** in the same frame as the shooter for the whole session — outcome
  detection needs it in view continuously, not just when the ball is near it.

### Lighting
Whatever is realistic and convenient for you — **do not engineer the lighting to help or hurt
FormAI.** If it's indoor gym lighting or a heavily overcast/bright outdoor sky, that's fine and
actually useful: the documented limitation is that RF-DETR was trained mostly on outdoor courts,
so an indoor session is a genuine, honest test of that gap rather than something to avoid.

### What to DO during recording
- Shoot **naturally** — your normal shooting rhythm, footwork, and form.
- **Retrieve the ball normally** between shots (walk to it, dribble it back, whatever you'd
  actually do), including any dribbling, passing to yourself off a wall, or brief idle standing
  that naturally happens. This is what actually stress-tests the false-positive gates (rebound vs.
  shot, dribble vs. shot) — under real conditions, not staged ones.
- Keep the **whole session in one take**, one file.
- If a shot is genuinely ambiguous even to your own eye (e.g. you look away, or the ball's outcome
  is unclear from this camera angle), that's fine — record it as ambiguous in Part B rather than
  guessing.

### What to NOT do during recording
- Don't move or re-aim the camera mid-session.
- Don't have a second person shooting, rebounding for you in-frame, or walking through the shot
  — the pipeline assumes a single shooter/single ball.
- Don't deliberately try to trigger or avoid the known roofline-type false-positive artifact (no
  aiming the camera at rooflines/sky on purpose, and no going out of your way to avoid them
  either) — just record wherever you'd naturally record.
- Don't watch or run FormAI on any part of this footage before Part B (the ground-truth log) is
  completely filled in.
- Don't trim, crop, re-encode, or otherwise edit the file after recording it — use the raw output
  from the camera.

---

## Part B — Ground-truth log (fill in BEFORE running FormAI)

Watch the raw video once, start to finish, and fill this in from your own observation only.
Timestamps are approximate (mm:ss, to the nearest second is fine) — precision isn't the point,
having an independent, pre-committed record is.

### Session metadata

| Field | Value |
|---|---|
| Recording date | August 29, 2026 |
| Video file name | real_test_04.mov |
| Total duration | approximately 3:12 |
| Indoor / outdoor | Outdoor |
| Lighting conditions (brief description) | Daylight, partly cloudy/bright outdoor conditions |
| Camera angle/placement (brief description) | Stationary camera, elevated approximately 45° side/front view, with full shooter and hoop visible |
| Any second person visible in frame at any point? | YES — one person far in the background mowing the lawn; not interacting with the shooter or basketball |
| Total shot attempts (your count) | 18 |
| Total makes | 7 |
| Total misses | 11 |
| Total ambiguous-to-you outcomes | 0 |

### Per-shot log

Fill one row per shot attempt, in chronological order. "Outcome" is your honest call — use
`AMBIGUOUS` rather than guessing if you genuinely couldn't tell from the recording.

| # | Approx. release time (mm:ss) | Outcome (MADE / MISSED / AMBIGUOUS) | Notes (e.g. airball, rim-out, immediate rebound, awkward footwork, anything unusual) |
|---|---|---|---|
| 1 | 0:03 | MISSED | |
| 2 | 0:15 | MADE | |
| 3 | 0:27 | MADE | |
| 4 | 0:38 | MISSED | |
| 5 | 0:44 | MISSED | |
| 6 | 0:49 | MISSED | |
| 7 | 1:01 | MISSED | |
| 8 | 1:09 | MISSED | |
| 9 | 1:21 | MADE | |
| 10 | 1:31 | MADE | |
| 11 | 1:40 | MISSED | |
| 12 | 1:52 | MISSED | |
| 13 | 2:04 | MADE | |
| 14 | 2:19 | MISSED | |
| 15 | 2:29 | MISSED | |
| 16 | 2:43 | MADE | |
| 17 | 2:56 | MADE | |
| 18 | 3:06 | MISSED | |

Detailed per-shot notes were not recorded beyond the outcome above (user's explicit choice —
"I don't have detailed notes for individual shots unless they are necessary").

### Non-shot event log

Anything in the video that is **not** a shot attempt but involves the ball moving upward or the
shooter's knees bending — dribbling, a pass, a rebound recovery, picking the ball up off the
ground, walking with the ball. This is the ground truth against which false positives get judged.
Doesn't need to be exhaustive of every dribble — just anything that plausibly *could* look like a
shot to an automated system (a bounce, a rebound catch, a retrieval after a miss).

**Not individually timestamped.** Per the user: "There are natural dribbles, rebounds, ball
retrievals, and walking between attempts throughout the video. I did not manually timestamp every
non-shot event." No timestamps were generated for this section by any automated means — FormAI
was explicitly not run to fill this gap, and none were invented. This is a known, accepted
limitation of this ground-truth log: the false-positive check in Part C will be judged only
qualitatively (does a detected shot window fall in a gap between two consecutive logged shots,
consistent with one of these known-present event types) rather than against exact matched
timestamps. A background presence — one person visible mowing the lawn far in the background,
not interacting with the shooter or ball — is also noted here as context for false-positive
diagnosis, since it is the only other moving element in frame besides the shooter.

| # | Approx. time (mm:ss) | What happened |
|---|---|---|
| — | not timestamped | Natural dribbles, rebounds, and ball retrievals occur between shot attempts throughout the session (exact times not logged — see note above) |

### Lock-in step

Once both tables above are complete, treat this file as final. Recommended: commit it to git
(`git add docs/VIDEO4_EVALUATION_PROTOCOL.md && git commit`) **before** running FormAI on Video 4
at all — that gives you an immutable, timestamped record that can't be edited after the fact, even
by accident. Only after that commit should FormAI be run on the video.

---

## Part C — Evaluation checklist (apply only after Part B is locked in and FormAI has run)

This restates `docs/FINAL_ARCHITECTURE_DECISION.md` §4/§5 as a literal checklist. Go through it in
order; do not skip to a metric that looks favorable.

- [ ] **Shot count.** FormAI's detected shot count vs. Part B's total shot attempts. Record the
      raw numbers, not just "close" or "far."
- [ ] **False positives.** For every FormAI-detected shot window, check it against Part B's
      per-shot log AND non-shot event log. Any detected "shot" that doesn't correspond to a real
      shot attempt in Part B is a false positive — note which non-shot event (if any) it lines up
      with.
- [ ] **False negatives.** For every row in Part B's per-shot log, check whether a corresponding
      FormAI shot window exists. Any real shot attempt with no matching detection is a false
      negative.
- [ ] **Release timing.** For matched shots, compare FormAI's release frame/timestamp to Part B's
      approximate release time. Rough agreement (within a couple seconds, given Part B's own
      mm:ss precision) is expected; note any large disagreements.
- [ ] **Make/miss/unknown.** Build the confusion table: Part B's outcome vs. FormAI's outcome, for
      every matched shot. Report `UNKNOWN` separately from wrong calls — a shot FormAI correctly
      declines to call is not the same failure as a shot it calls wrong.
- [ ] **Roofline/background-artifact check.** For any false positive from the check above, look at
      what the detector actually locked onto (if diagnosable) — is it the same already-documented
      class of static-background hallucination, or something new?
- [ ] **Biomechanics completeness.** For shots with a confirmed release, check whether knee/elbow/
      torso-lean/release-height metrics are populated or `null`-with-reason.
- [ ] **Verdict against the frozen stop condition** (§5 of the decision doc): do shot
      count/timing/outcome accuracy land within the same error bars as V1-V3, with no *new*
      failure category beyond the documented roofline-type artifact? Answer yes/no plainly, the
      same way the v2/v3 fine-tune verdicts were reported — no threshold changes to make a
      borderline result look better.

Nothing in this checklist should be filled in, and no code should be run, until Part A and Part B
above are both complete.

---

## Part D — Results (one-shot evaluation, run after ground truth was frozen)

Ground truth frozen in commit `fa9ee0d18dfac3c27b10ce613ec34b132fb1fd14` prior to any inference.
Pipeline run once, unmodified, via the existing generic diagnostic entrypoint
(`scripts/diagnose_video.py`, which only calls `app.pipeline.orchestrator.run_pipeline` — no
detector, tracker, shot-event, outcome, biomechanics, or threshold code was touched). Raw outputs
preserved at `data/diagnostics/real_test_04/` (`session_result.json`, `frame_level.csv`,
`ball_trajectory.png`, `pose_confidence.png`, `diagnostic.mp4`) and via a new, read-only measurement
script `scripts/eval_coverage_v4.py` (mirrors the existing `eval_coverage_v1v2v3.py` methodology
exactly, pointed at Video 4 — no existing file edited).

### Shot count
**23 detected vs. 18 true.** All 18 ground-truth shots matched a detection (0 false negatives).
**5 unmatched detections (false positives)**, at release times 22.498s, 57.68s, 77.508s, 109.653s,
132.919s — none within ~4.5s of any logged shot.

### Matched shots / false positives / false negatives
- **Matched: 18/18** (every logged shot found a corresponding detection).
- **False negatives: 0.**
- **False positives: 5** (see below for cause).

### Release timing errors (18 matched shots)
Deltas between detected release time and the ground truth's hand-logged mm:ss: 0.305, 0.012,
0.062, 0.888, 0.105, 0.098, 0.252, 0.697, 0.046, 0.207, 0.707, 0.39, 0.54, 0.006, 0.059, 0.161,
0.947, 1.195 (seconds). Mean ≈0.36s, max 1.195s. **No timing concern** — well within what a
hand-eyeballed, whole-second ground-truth log can resolve.

### MAKE / MISS / UNKNOWN vs. 7 MADE / 11 MISSED ground truth

| Truth \ Prediction | MADE | MISSED | UNKNOWN |
|---|---|---|---|
| **MADE (7)** | 2 | 3 | 2 |
| **MISSED (11)** | 1 | 6 | 4 |

- Correct calls: 8 (6 correct MISSED, 2 correct MADE)
- **Wrong calls: 4** — 3 real makes called MISSED, 1 real miss called MADE
- Abstentions (UNKNOWN): 6

### Outcome accuracy
- **Accuracy among calls FormAI was willing to make (non-UNKNOWN): 8/12 = 66.7%.**
- UNKNOWN rate: 6/18 = 33.3%.
- Made-shot recall (correctly called MADE outright): 2/7 = 28.6%.
- Missed-shot recall (correctly called MISSED outright): 6/11 = 54.5%.
- This is the headline negative finding: 1 in 3 of the calls the system was confident enough to
  make were wrong, with a clear directional bias — 3 of 4 wrong calls were genuine makes reported
  as misses.

### Ball / rim detector coverage and confidence (raw RF-DETR, all 5,761 analyzed frames)
- **Ball: 85.5% coverage, mean confidence 0.777.**
- **Rim: 100.0% coverage, mean confidence 0.903.**
- For comparison, the original documented V1 A/B benchmark: ball 80.8% / conf 0.693; rim 99.4% /
  conf 0.963. RF-DETR itself performs at least as well on Video 4 as on its original benchmark
  video — **the detector generalized cleanly; it is not the source of the outcome-accuracy
  problem above.**
- Post-tracking (Kalman) ball availability, from `frame_level.csv`: detected 72.7%, interpolated
  15.5% (detected+interpolated = "reliable" = 88.2%), predicted 1.6%, unavailable 10.2%.

### Biomechanics completeness
275 of 322 possible metric fields populated across the 23 detected shots (14 fields × 23 shots) =
**85.4%**. Zero shots were `excluded_from_analysis`.

### Background person (lawn-mower) check
Inspected the raw per-frame ball trace (`frame_level.csv`) for all 5 false-positive windows.
**No evidence the background person contributed.** All 5 show continuous, high-confidence,
physically coherent ball motion (translating position + oscillating vertical bounce) consistent
with the ball actually being handled by the shooter — not a fixed-position or background-scale
artifact. One (release ≈77.5s) computed a physically impossible `apex_height_norm = 7.846`
(a normal shot is well under 1.0), which is a data-quality flag on the mechanics computation for
that window, not evidence of the background person specifically.

### False positives from dribbles/rebounds/retrievals
**Yes — all 5 false-positive windows.** Each one's raw ball trace shows the same signature: the
ball's x-position translates steadily across a couple hundred pixels while its y-position
oscillates through one or more bounce cycles — the exact "dribble while walking" pattern already
named and (on V1-V3) mitigated in `docs/METHODOLOGY.md`'s coherent-evidence section via the
shooter-stationarity gate (`_shooter_was_stationary_nearby` / `max_load_hip_translation_norm`).
That gate evidently did not fully suppress this pattern on Video 4's specific framing/pace. This
is the ground-truth log's own predicted non-shot-event category ("natural dribbles, rebounds,
ball retrievals, and walking between attempts") showing up exactly where expected — not a new,
unexplained failure mode, but a known mitigation not generalizing as far as hoped.

### Throughput / runtime
- Full `diagnose_video.py` run: 10m44s wall time, but this includes diagnostic-only plot and
  overlay-video rendering (~71s) that is not part of the shipped product.
- **Core pipeline only** (frame analysis through biomechanics/outcome/finalizing, i.e. what
  actually ships): ≈564s (9m24s) for 5,761 analyzed frames of a 192.3s video ≈ **10.2 fps**,
  i.e. ≈2.9× slower than real-time on this hardware. Not directly comparable to the previously
  documented 28-39fps figure, which measured the ball/rim detector stage in isolation — this
  number is the full stack (person detection, pose, ball+rim detection, tracking, hoop
  aggregation, shot segmentation, near-hoop enrichment, biomechanics, outcome reasoning) together.

### Pre-committed stop condition — checked against `docs/FINAL_ARCHITECTURE_DECISION.md` §5

1. Shot count/timing within the same honest error bars as V1-V3, no new failure category —
   **partially fails**: timing is fine, but the false-positive rate (5/18 ≈ 28% extra) reproduces
   the *already-documented* dribble-while-walking category at a magnitude similar to what the
   stationary-hip gate was built to close on V1-V3, indicating that gate does not fully
   generalize to this footage.
2. Any background false positives belong to the already-documented roofline-type class — **moot/
   satisfied**: no background-related false positives were found at all.
3. MADE/MISSED calls that are made are correct against manual review — **fails**: only 66.7%
   (8/12) of non-abstained calls were correct, with a clear bias toward calling real makes as
   misses.
4. No production file needed to change to get here — **satisfied**: nothing was changed.
5. Documentation reflects limitations — **not yet done**; pending as a follow-up per the
   already-written implementation plan.

### VIDEO 4 VERDICT: **FAIL**

**Responsible criterion: #3.** The pre-committed bar was that calls FormAI actually makes (not
abstained as UNKNOWN) must be correct against manual review. 4 of 12 such calls were wrong
(66.7% accuracy), including 3 of 7 genuine makes called MISSED outright — a directional,
non-random error pattern, not noise. That alone is sufficient to fail this evaluation regardless
of the other criteria. Criterion #1 (false-positive rate reproducing the dribble-while-walking
category) is a secondary, contributing concern. Per the pre-committed protocol, no fix is
proposed here and none should be attempted without a separate, explicit request.
