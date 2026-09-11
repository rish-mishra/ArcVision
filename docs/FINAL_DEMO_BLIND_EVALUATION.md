# Final Demo — One-Shot Blind Production Evaluation

Frozen ground-truth commit: `b08c2fe56d956108fce23c635f1f70bc5919db3a`
Video SHA-256 (reverified before inference, exact match): `e85b6eac08de5073b364be4dfbed27bcf3c8b6b186daa79973521541964ba1fc`
Production session ID: `29c7e751775e4f20`
Run exactly once, through the current frozen production pipeline (real `/api/sessions/upload` path, no shadow scorer, no modified settings). No fix was made after seeing this result.

## Per-shot matching (greedy nearest-release-time, one-to-one, all gaps reported honestly)

| Truth # | Truth t | Truth outcome | Detected # | Detected t | Timing error | Predicted outcome | Confidence | Match status |
|---|---|---|---|---|---|---|---|---|
| 1 | 0:02 | MADE | 1 | 2.234 | 0.234s | unknown | 0.0 | matched |
| 2 | 0:12 | MADE | 3 | 12.104 | 0.104s | unknown | 0.0 | matched |
| 3 | 0:27 | MADE | 4 | 26.675 | 0.325s | unknown | 0.0 | matched |
| 4 | 0:36 | MADE | 5 | 35.945 | 0.055s | **missed** | 0.474 | matched — **wrong** |
| 5 | 0:46 | MISSED | 6 | 46.148 | 0.148s | missed | 0.972 | matched — correct |
| 6 | 0:51 | MADE | 7 | 51.483 | 0.483s | unknown | 0.0 | matched |
| 7 | 1:00 | MADE | 8 | 60.486 | 0.486s | **missed** | 0.964 | matched — **wrong (high confidence)** |
| 8 | 1:11 | MISSED | 9 | 71.923 | 0.923s | missed | 0.869 | matched — correct |
| 9 | 1:19 | MISSED | 10 | 80.059 | 1.059s | **made** | 0.582 | matched — **wrong** |
| 10 | 1:29 | MADE | 12 | 89.729 | 0.729s | made | 0.697 | matched — correct |
| 11 | 1:36 | MADE | 13 | 96.098 | 0.098s | **missed** | 0.485 | matched — **wrong** |

## False positives (detected, no matching genuine attempt)

| Detected # | Time | Outcome | Notes |
|---|---|---|---|
| 2 | 11.104 | unknown (0.0) | ~0.9s before the true match for Shot 2 (12.104) — plausibly a split/double-trigger around one real attempt, but counts as an extra detected event under strict one-to-one matching. |
| 11 | 87.728 | unknown (0.0) | ~1.9s before the true match for Shot 10 (89.729) — same pattern. |

Neither false positive is near the pre-Shot-11 edit boundary (~1:29–1:36) — the splice itself did not appear to produce a spurious event.

## False negatives

None. All 11 genuine shots were matched to a detected event.

## Aggregate metrics

**Shot detection**
- True shots: 11
- Detected events: 13
- TP: 11, FP: 2, FN: 0
- Precision: 11/13 = 84.6%
- Recall: 11/11 = 100%

**Outcome confusion matrix** (rows = truth, only the 11 matched shots)

| Truth \\ Predicted | MADE | MISSED | UNKNOWN |
|---|---|---|---|
| **MADE (8)** | 1 | 3 | 4 |
| **MISSED (3)** | 1 | 2 | 0 |

- Predicted MADE: 2, predicted MISSED: 5, predicted UNKNOWN: 4
- Coverage (non-unknown / true shots): 7/11 = 63.6%
- Accuracy among classified: 3/7 = 42.9%
- Overall resolved-correct rate (UNKNOWN = unresolved): 3/11 = 27.3%
- UNKNOWN rate: 4/11 = 36.4%
- False MADE: 1 (Shot 9, MISSED called made at 0.582 confidence)
- False MISSED: 3 (Shots 4, 7, 11 — MADE called missed; Shot 7's wrong call carries **0.964 confidence**, the single most concerning result in this run)

**Timing**
- Mean absolute release-time error: 0.422s
- Max absolute release-time error: 1.059s (Shot 9)

## Shot 11 analysis (post-edit, far showcase shot)

Matched to detected shot 13 (release 96.098s, error 0.098s — the tightest timing match in the
whole session).
- **Detected**: yes, cleanly.
- **Outcome**: `missed`, 0.485 confidence, reason `ball_descended_well_clear_of_hoop` — **wrong**
  against the frozen MADE truth.
- **Ball tracking quality**: 1.0 (perfect track-quality score for this shot).
- **Rim/hoop tracking**: 0.97 confidence (video-level, same hoop location used throughout).
- **Pose quality**: 0.829.
- **Warnings**: `video_ended_during_flight` — this is the last shot in the file (release at
  96.1s of 98.5s total), so the window closed because the recording itself ended, not from a
  natural settle.
- **Did the edit produce a false event?** No — no spurious detection appears at or near the
  pre-Shot-11 cut boundary; the two false positives found elsewhere are both well inside the main
  continuous recording, unrelated to the splice.
- 38 trajectory points were rejected as outliers for this shot (the most of any shot in the
  session) — consistent with a genuinely harder-to-track, farther attempt, not a data error.

## Detector/tracking/quality summary

- Mean pose quality: 0.807. Mean ball-track quality: 0.934. Hoop confidence: 0.97 (video-level).
- 8 of 13 detected shots carry `max_duration_exceeded` (consistent with the same continuous
  -recording pacing pattern already observed and explained on the current demo video).
- 0 shots excluded from analysis.

## Coaching output

- Eligible: yes. Confidence: medium.
- Strength: knee angle at release (CV=0.084, most consistent mechanic).
- Priority: trajectory straightness ratio (CV=2.091, least consistent; source=consistency,
  confidence=medium).
- Makes-vs-misses: explicitly abstained — "No strong measurable difference was found between your
  makes and misses this session" (honest, given how few classified calls exist to compare, and how
  unreliable those classified calls turned out to be against truth).

## Demo decision (against the precommitted checklist in `docs/FINAL_DEMO_RECORDING_PROTOCOL.md`)

| Criterion | Result |
|---|---|
| All/most genuine shots represented | Yes (11/11 matched) |
| Low/no false shot events | **No — 2 false positives** |
| Substantially fewer UNKNOWNs than current demo (3/7 = 42.9%) | **No — 36.4% is only marginally lower, not substantial** |
| No increase in confident incorrect outcomes merely for coverage | **No — 4 of 7 classified calls (57%) are wrong against real frozen truth, including one at 0.964 confidence** |
| Replay visually understandable | Not independently re-verified against truth here (out of scope for this metrics-only pass) |
| Useful coaching/biomechanics output | Yes, structurally (eligible, medium confidence, honest makes-vs-misses abstention) |

**The new recording does not clearly satisfy the precommitted acceptance criteria** — it fails on
false positives and, most seriously, on confident-wrong-call rate. Per the precommitted rule, this
means **stop, do not adopt**, regardless of its marginally lower raw UNKNOWN count.

**Recommendation: KEEP CURRENT DEMO** (`arcvision_demo_01`, session `3809b2b304064f21`), not V1.
Reasoning: nothing here demonstrates V1 is actually *better* than the currently-live demo against
independent truth (V1 has never been checked against frozen ground truth either) — switching to it
would trade the current demo's clean, already-verified, already-public-facing framing for
"development footage" framing with no proven accuracy benefit. With the new recording failing its
own precommitted bar, there is no evidence-based reason to change anything.
