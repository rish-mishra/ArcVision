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
