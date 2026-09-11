# Post-Contact Reversal Shadow Prototype

**Date:** 2026-09-09
**Status: STOPPED.** The contact-anchor forensic (Part 4) found that no
single, non-fitted structural anchor redefinition can fix both the
showcase false-positive and the V4 false-negative simultaneously, and that
V4's actual target case (the known false-MADE) most likely reflects a
different physical miss mechanism (lateral deflection) than the vertical-
reversal concept this prototype is built around. V1/V2/V3 were never run.

**Zero production files changed. Test baseline: 209 passed (197 production +
12 shadow tests), 0 failed.**

---

## Part 1 — The original 2.0s-from-apex experiment (FAILED, preserved for record)

The first version of `app/research/post_contact_reversal.py` bounded its
reversal/escape episode using `cfg.max_seconds_from_apex_for_descent_evidence`
(2.0s, measured from the trajectory's global apex) — an existing production
constant, reused because the module's design rule was "no new fitted
constants," but reused for the wrong purpose. On the showcase video, this
produced `reversal_detected=True` on **all 11 of 11 shots**, with 6 genuine
MADE shots (4, 7, 10 plus 5, 8, 11) flagged at "strong" escape confidence and
the actual target case (shot 9, the rattle) landing at only "weak" confidence
— backwards from what the visual audit predicted.

**Root cause:** measuring 2.0s from *apex* reaches far past the actual rim
interaction into each shot's post-decision aftermath — the ball already on
the floor, rolling, or retrieved. Every shot's flagged "reversal" points
landed 1.0–1.6 seconds after the ball's actual rim contact, not a few frames
after it. Shot 10's own flagged "escape" point (frame 2764) was independently
already on record in `docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md` as a
`far_descent_detail` point — i.e., the same kind of stale, post-decision
evidence that motivated Outcome Reliability Pass #1's (still unimplemented)
`n_candidate_pairs` MISS gate in the first place. The module was answering a
different, unintended question ("did the ball's height ever rise, anywhere
within 2 seconds") instead of the intended one ("did the ball reverse and
escape within a plausible rim-contact timescale"). Full detail preserved in
git history / this document's earlier revision; the finding above is the
complete account of why it failed.

This was diagnosed as primarily an implementation/scoping bug, not
disqualifying evidence against the underlying physical hypothesis (shot 9's
own visually-confirmed rattle, `docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`,
was never in doubt) — which is what motivated attempting the correction
below rather than stopping outright.

## Part 2 — The contact-relative scoping correction (this turn)

### A. Exact shadow change

In `app/research/post_contact_reversal.py`, the `post_contact` point list
(the set the reversal/escape scan runs over) is now bounded to
`cfg.max_seconds_through_rim` (0.75s — the existing constant production
already uses to define how long a single rim-crossing event may plausibly
span) measured from the **contact frame**, not `cfg.max_seconds_from_apex_for_descent_evidence`
(2.0s) measured from apex:

```python
post_contact = [p for p in episode_pts
                 if contact.frame_index <= p.frame_index
                 and (p.timestamp_sec - contact.timestamp_sec) <= cfg.max_seconds_through_rim]
```

Nothing else changed: geometric bands (tight/wide), the minimum
confirmation-point count (`cfg.min_points_below`), observed/interpolated
policy, trajectory filtering (`_reliable`/`_reject_trajectory_outliers`),
escape semantics (leaves wide band and/or rises above rim), and production
`outcome_detector.py` are all untouched.

### B. New constants introduced

**NO.** `max_seconds_through_rim` already exists in `OutcomeConfig` and is
already used by production for a directly analogous purpose (bounding a
single rim-crossing event in time).

### C. Tests

Two new synthetic tests added to `tests/research/test_post_contact_reversal.py`,
both proving the window boundary itself: `test_i_motion_more_than_0_75s_after_contact_cannot_create_reversal`
and `test_j_ordinary_post_make_floor_bounce_outside_window_does_not_count`.
All 10 previously-existing shadow tests were re-run unmodified and still
pass (their fixtures use frame gaps of a few frames at 30fps, well inside
the new 0.75s bound, so the correction doesn't change their outcomes).

**Production tests: 197. Shadow tests: 12. Total: 209/209, 0 failed.**

### D/E. Showcase shots flagged, before → after

| | Before (2.0s-from-apex) | After (0.75s-from-contact) |
|---|---|---|
| Any reversal detected | 11 / 11 | **2 / 11** |
| Strong reversal+escape | 6 / 11 (4, 5, 7, 8, 10, 11) | **2 / 11 (2, 9)** |
| Reversal on genuine MADE shots | 5 of 8 truth-MADE shots (4, 7, 10, 11, plus weak on 1/2/3/6) | **1 of 8** (shot 2 only) |
| Reversal on the truth-MISSED target (shot 9) | weak, no escape | **strong, escape=True** |

Full per-shot result (0.75s-from-contact, this turn):

| Shot | Truth | Production | Reversal | Escape | Quality | Time after contact | Observed support | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | MADE | unknown | False | False | strong | — | — | no_reversal_clean_continuation |
| 2 | MADE | unknown | **True** | **True** | **strong** | 0.30s | 12 detected, 0 interp | post_contact_reversal_with_escape |
| 3 | MADE | unknown | False | False | strong | — | — | no_reversal_clean_continuation |
| 4 | MADE | missed (0.45) | False | False | strong | — | — | no_reversal_clean_continuation |
| 5 | MISSED | missed (0.97) | False | False | strong | — | — | no_reversal_clean_continuation |
| 6 | MADE | unknown | False | False | strong | — | — | no_reversal_clean_continuation |
| 7 | MADE | missed (0.97) | False | False | strong | — | — | no_reversal_clean_continuation |
| 8 | MISSED | missed (0.87) | False | False | strong | — | — | no_reversal_clean_continuation |
| **9** | **MISSED** | **made (0.58)** | **True** | **True** | **strong** | **0.23s** | **12 detected, 0 interp** | post_contact_reversal_with_escape |
| 10 | MADE | made (0.70) | False | False | strong | — | — | no_reversal_clean_continuation |
| 11 | MADE | missed (0.48) | False | False | strong | — | — | no_reversal_clean_continuation |

### F. Shot 9 result

**Strong, contact-local reversal+escape evidence — the target result.**
Reversal confirmed 0.23s after contact (frame 2444 onward, contact at frame
2437), by 12 genuinely-DETECTED points (zero interpolated), with an
`upward` escape direction. This lines up closely with the visual audit's
own frame-by-frame account (`docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`
Section 4): the ball was seen entering the rim opening then reappearing
above/beside the rim within 2–4 raw video frames (~0.1s) of first contact —
this module's independently-derived 0.23s figure is the same fast timescale,
not the 1.47s the uncorrected version reported.

### G. Shot 9 evidence: clean or contaminated?

**CLEAN.** Cross-referenced against the raw per-frame ball-tracker cache
(`data/diagnostics/arcvision_demo_final_segmentation_forensic/frame_signals.json`):
frames 2437–2451 do show the same alternating dual-cluster artifact flagged
as a risk in Part 1 (one cluster near x≈260–310, a second near x≈400–600
appearing on interleaved frames) — but **none of those interleaved-cluster
frames appear in the module's actual confirming evidence.** The 12
confirming points (frames 2444, 2446, 2448, 2450, 2452–2459) all come from
the x≈260–310 cluster, form an internally smooth, physically coherent
sub-sequence (y: 121.4 → 113.1 → 110.9 → 107.7 → 110.9 → 115.5 → 117.2 →
118.4 → 119.2 → 120.5 → 123.1 → 128.5 — a genuine dip then sustained rise),
and are reported by the module itself as 100% `DETECTED`-sourced with zero
interpolated support. The alternating-cluster frames between them (2438,
2439, 2441, 2443, 2445, 2447, 2449, 2451) are simply absent from the
confirming set entirely, not merely down-weighted — whatever their true
nature (not independently re-verified this turn, per the instruction not to
fix or further investigate the tracker), they did not end up polluting
shot 9's specific reversal evidence.

### H. Genuine MADE false-flag count

**1 of 8** truth-MADE shots (shot 2) — down from 5 of 8 under the
uncorrected 2.0s window. All other 7 genuine makes (1, 3, 4, 6, 7, 10, 11)
now show clean, confident `no_reversal_clean_continuation`.

### I. Strongest genuine-MADE counterexample

**Shot 2.** Investigated the same way as shot 9 (Section G): its 12
confirming points (frames 406–415, all `DETECTED`, zero interpolated — this
is NOT a contamination case either) come from a real, physically coherent
wobble — but critically, that wobble's y-range (≈106–120) sits entirely
**above** `hoop.rim_top_y` (≈136 for this video) — i.e., the ball never
actually descends into the rim's own vertical span during this specific
0.75s-from-contact window. Cross-referenced against
`docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`'s direct visual inspection of
shot 2 (frames spanning its full flight, not just the first 0.75s after
contact): the ball is confirmed there to pass cleanly through the net
*later* in its trajectory, after this window has already closed. This
reveals a second, distinct issue from the one just fixed: `contact` is
detected too early for this shot — `near_rim_height`'s existing tolerance
(2.5× rim radius, quite generous) is satisfied while the ball is still well
above the rim's true vertical span, so the tightened 0.75s window can end up
anchored to, and fully consumed by, an early high-altitude approach wobble
rather than the shot's real, decisive rim interaction. This is a plausible
next thing to investigate, but is a different correction from the one made
this turn and was not attempted.

### J. Whether contact-relative scoping fixed the original failure

**Yes, substantially.** Reversal went from ubiquitous (11/11, uninformative)
to rare and structurally meaningful (2/11). The target case (shot 9) now
shows exactly the fast, clean, contact-local evidence the visual audit
predicted. One genuine make (shot 2) is still falsely flagged, but for a
clearly different, separately-diagnosable reason (early contact anchoring,
not the episode-length bug) — not a sign that the correction failed, but a
sign of where the *next* correction would need to look.

### K. Recommendation

**RUN V4 NEXT.** All four of the decision criteria from this turn's
instructions are met: (1) reversal is no longer ubiquitous — 2/11, not
11/11; (2) shot 9 has strong, meaningful, contact-local reversal evidence —
0.23s after contact, strong quality, escape confirmed; (3) genuine makes are
substantially cleaner — 7/8 clean, down from 3/8; (4) shot 9's evidence is
confirmed clean, not tracking contamination (Section G). The one remaining
false positive (shot 2) is understood well enough to describe precisely
(Section I) without blocking a V4 generalization check. **Not launched this
turn** — this is a recommendation for the next explicitly-authorized turn,
consistent with the instruction to validate on showcase only before
resuming the more expensive V4/V1/V2/V3 runs that caused resource concerns
previously.

### L. Production unchanged confirmation

Confirmed — `git status` shows no changes under `app/events`, `app/pipeline`,
`app/vision`, or `app/tracking` this turn. Only `app/research/`
(shadow-only, not imported by production), `scripts/`, and `tests/research/`
were modified/added.

---

## Part 3 — V4 validation (Outcome Reliability Pass #3B), mixed result

### A. Frozen shadow implementation

`app/research/post_contact_reversal.py` SHA-256:
`b87d33778af76ddcf0d1ae0cc859bf9a483d9b37d2b11c8c8d9aafbbbf5ad846`
(`app/research/__init__.py`: `1997069356a1fd4554374afd3d771ea24de769695b7d57885f7adfd8ec02b1c8`).
Recorded reused config values at freeze time: `max_seconds_through_rim=0.75`,
`min_points_below=2`, `min_points_above=2`, `min_reliable_points_to_attempt=3`,
`min_descent_points_to_attempt=3`, `min_hoop_confidence_to_attempt=0.3`,
`near_rim_height_frac_of_rim_radius=2.5`, `horizontal_margin_frac_of_rim_radius=1.6`,
`wide_zone_frac_of_rim_radius=3.0`. Hash re-verified identical immediately
after the V4 run completed — **the module was not touched between freezing
and running V4.**

### B. V4 run completed

**YES.** V4 only (real_test_04.mov, 5761 frames); no other heavy job ran
concurrently. Output: `data/diagnostics/shadow_reversal_v4/shadow_reversal_report.json`,
21 shots.

### C. V4 genuine shots analyzed

21 detected windows total. 3 of them (shot_index 7, 10, 16 — release times
≈57.71s/77.78s/133.02s) match 3 of the 5 documented segmentation
false-positive windows and were excluded from truth scoring. **The
remaining 18 detected windows match all 18 frozen ground-truth shots
one-to-one** (release times within ~1s of each frozen truth entry). Of
those 18: **7 genuine MADE, 11 genuine MISSED.**

### D. V4 known false-MADE reversal result

**Shot_index 9** (release t≈69.76s, matching the frozen ground-truth MISSED
at ~69s; production predicts `made`, confidence 0.588 —
`ball_crossed_rim_band_top_to_bottom`): shadow result is
**`reversal_detected=False`, quality `strong` (confident clean-continuation),
reason `no_reversal_clean_continuation`.**

**The shadow module does NOT flag V4's known false-MADE case.** This is the
opposite of the desired result and does not replicate showcase shot 9's
outcome.

Investigated why: contact is detected at frame 2122 (t=70.832s); the
trajectory's max depth within the post-contact window is reached at frame
2144 — only ~0.73s after contact, i.e. right at the edge of the 0.75s
window. There is essentially no window time left after reaching that depth
for the `cfg.min_points_below`(2) confirming "came back up" points to
accumulate before the window closes. This is consistent with a real bounce
that, on this video's footage, takes slightly longer to fully develop into
confirmable evidence than showcase's did (which confirmed in 0.23s, well
inside the window) — not obviously consistent with "no bounce exists at
all." This was not further investigated (extending the window would be a
second, unauthorized change this turn).

### E. Comparison with showcase Shot 9

| | Showcase Shot 9 | V4 Shot 9 (known false-MADE) |
|---|---|---|
| Truth | MISSED | MISSED |
| Production | made (0.58) | made (0.588) |
| Reversal detected | **True** | **False** |
| Time from contact to max depth | — (reversal confirmed at 0.23s) | ~0.73s (right at the 0.75s window edge) |
| Structurally same event (contact → local reversal → escape)? | **Yes, directly confirmed** | **Not confirmed within the current window** — the descent-to-max-depth half of the pattern is present, but the window closes before the reversal/escape half can be confirmed |

**The physical event is plausibly the same in kind (rim interaction followed
by an eventual reversal), but the two videos' timing relative to the fixed
0.75s window is NOT the same** — showcase's resolves comfortably inside it,
V4's does not. This is the primary, most important negative finding of this
validation pass.

### F. V4 genuine MADE strong false-flag count

**0 of 7.** Every genuine MADE shot (shot_index 2, 3, 11, 12, 15, 19, 20 —
ground-truth release times 15s, 27s, 81s, 91s, 124s, 163s, 176s) shows
`reversal_detected=False`, `no_reversal_clean_continuation`, quality
`strong`. This is a stronger safety result than showcase (which had 1 of 8
false-flagged, shot 2).

### G. Explanations for each false flag

**None to explain — there are zero genuine-MADE false flags on V4.** (Two
genuine-MISSED shots, 1 and 21, DID get strong reversal+escape flags — see
Section H; these are not false flags, since their truth is MISSED.)

### H. V4 dangerous exhaustive-search misses result

- **Shot_index 17** (t≈139.06s, matches frozen truth MISSED at 139s — one of
  the two shots that would become false MADE under the already-rejected
  exhaustive crossing-search experiment): `reversal_detected=False`,
  `no_reversal_clean_continuation`, strong. No reversal evidence for this one.
- **Shot_index 21** (t≈187.16s, matches frozen truth MISSED at 186s — the
  other exhaustive-search danger case): `reversal_detected=True`,
  `escape_detected=True`, quality **strong**, reversal confirmed 0.2s after
  contact, 14 detected / 0 interpolated support.

**Mixed: one of the two dangerous cases (21) gets real, clean reversal
evidence; the other (17) does not.** Reversal evidence would have provided
zero benefit against MADE-search changes for shot 17, and a genuine,
independent safety signal for shot 21.

A third genuine-MISSED shot, shot_index 1 (t≈3.30s, matches frozen truth
MISSED at 3s; production currently abstains, `unknown`), also shows a clean
`reversal_detected=True, escape=True, strong` result (0.234s after contact,
16 detected / 0 interpolated) — an uncontroversial correct-direction result
on an already-correctly-abstaining shot, included here for completeness
since MADE search was never involved for it either.

### I. Evidence contamination assessment

No raw per-frame ball-tracker cache was generated for V4 this session (doing
so would require re-running V4's detection pass again, which this turn's
instructions explicitly asked to avoid) — so the same direct raw-signal
cross-reference used for showcase (Part 2, Section G) was **not possible**
for V4. This is a genuine methodological limitation, reported rather than
papered over.

What IS available, from the shadow module's own accounting:

| Shot | Confirm frames | Support | Contiguity | Assessment |
|---|---|---|---|---|
| 1 | [136–151], 16 consecutive frame numbers, zero gaps | 16 detected, 0 interpolated | Perfectly contiguous | **CLEAN** (strong internal evidence; no raw cross-check available) |
| 21 | [5642, 5644, 5646, 5648, 5649...5658] | 14 detected, 0 interpolated | Mostly contiguous; a few 2-frame steps early in the run | **CLEAN, with lower confidence than shot 1** — the 2-frame steps are consistent with intervening frames simply not qualifying as new reversal candidates (expected, benign) rather than dropped/alternating data, but this was not independently verified against raw per-frame output the way showcase's was |

Neither shows the every-other-frame alternation pattern that flagged
contamination risk in Part 1/2. **Assessment: CLEAN for both, at reduced
confidence relative to the showcase cross-check due to the missing raw
cache.**

### J. New constants introduced

**NO** — module was frozen (Section A) and re-verified byte-identical after
the run.

### K. Tuning after V4

**NO** — no changes were made to the module, config, or anything else based
on this run's results; this document is the only artifact produced.

### L. Cross-video generalization

**FAIL, on the specific acceptance bar set for this pass.** The primary
target (identifying V4's known false-MADE case) was not met — Section D.
Genuine-MADE safety generalizes excellently (actually improves on
showcase — Section F). One of the two exhaustive-search danger cases
generalizes (shot 21); the other does not (shot 17). The pattern of
failures (Section E, and Part 2 Section I's showcase shot 2 finding) points
at the same underlying weakness in both directions: **contact-frame timing
precision**, not a refuted physical hypothesis.

### M. Recommended eventual production role

**NONE — too early to assign one.** Given the mixed cross-video result, no
production role (veto/abstain/episode) should be considered until the
contact-timing question is resolved and re-validated. If pursued further
and it eventually generalizes reliably, **ABSTAIN** (converting a confident
wrong MADE to UNKNOWN) remains the most defensible role given this
prototype's demonstrated strength (zero false MADE-suppressions across both
videos so far) — never VETO-to-MISSED, and never participation in a larger
episode architecture, until the core detection reliability question is
settled.

### N. Recommendation

**PROCEED TO CONTACT-TIMING INVESTIGATION — not STOP, and not a claim of
success.** Rationale: (1) the underlying physical hypothesis is not refuted
— V4 shot 9's trajectory does descend to a genuine post-contact depth
within the window, it simply runs out of window time before confirming the
reversal, which is a timing/boundary issue, not evidence no reversal
exists; (2) safety remains excellent and actually improved on V4 (0/7
genuine-MADE false flags, vs. 1/8 on showcase); (3) both observed failure
modes — showcase's premature-contact false positive (Part 2, Section I) and
V4's just-too-late-for-the-window false negative (Section D here) — are
naturally explained by the same single, specific, describable weakness
(contact-frame anchoring precision), not by two unrelated problems, which
makes a targeted follow-up investigation plausible rather than speculative.
This is explicitly **not** a claim that the prototype currently works on
V4 — Section L's FAIL stands as reported, and no further correction was
attempted this turn per instructions.

### O. Production unchanged confirmation

Confirmed — `git status` shows no changes under `app/events`, `app/pipeline`,
`app/vision`, `app/tracking` this turn (Part 3). Only the diagnostics output
directory `data/diagnostics/shadow_reversal_v4/` and this document were
added/changed, plus `scripts/shadow_post_contact_reversal_eval.py`'s `main()`
was pointed at V4 instead of showcase (a script, not production or the
shadow module itself).

### P. Tests remain 209/209

Confirmed, re-run after the V4 pass: 209 passed (197 production + 12
shadow), 0 failed.

---

## Part 4 — Contact-anchor forensic (Outcome Reliability Pass #3C), FORENSICS ONLY

No code was changed this pass. `app/research/post_contact_reversal.py`
hash re-verified identical to Part 2/3's frozen value
(`b87d33778af76ddcf0d1ae0cc859bf9a483d9b37d2b11c8c8d9aafbbbf5ad846`)
throughout. All data below comes from existing cached diagnostics: showcase
uses the dense per-frame cache `data/diagnostics/arcvision_demo_final_segmentation_forensic/frame_signals.json`
(every frame, exact positions); V4 uses the sparser `data/diagnostics/video4_outcome_forensic/shot_forensic_report.json`
candidate-pair samples (only frames already inside the tight interaction
band) plus one contact-sheet image re-inspection — **no video was
re-rendered or re-processed this pass.**

### 1. Current contact definition, exactly

From `app/research/post_contact_reversal.py`:

```python
contact_pts = [p for p in wide_band_pts
                if od._in_band(p, hoop, tight_band) and od._near_rim_height(p, hoop, cfg)]
contact = contact_pts[0]   # first, chronologically
```

- **Triggering band:** horizontal — existing `tight_band` (`rim_radius * 1.6 + ball_radius`).
  Vertical — existing `near_rim_height` (`|y - rim_center_y| <= rim_radius * 2.5`,
  a **symmetric** tolerance around the rim's center, not tied to the rim's
  actual structural top/bottom edges).
- **Descending required?** Not checked directly at the contact point itself
  — implied only by scanning `near_apex_descent` (already apex-onward), not
  enforced frame-by-frame.
- **Horizontal rim-opening overlap required?** No — `tight_band` is far
  wider than the rim's own radius (1.6× radius plus the ball's own radius
  margin, so effectively covers roughly ±2 rim-radii of horizontal
  tolerance for a typical ball size).
- **Observed points required?** Contact points come from `reliable`
  (`DETECTED`/`INTERPOLATED` only, `_reject_trajectory_outliers` applied) —
  but the single contact point itself is not required to be `DETECTED`
  specifically; `INTERPOLATED` qualifies too.
- **How early can contact occur relative to the actual rim?** Very early —
  `near_rim_height`'s 2.5× radius tolerance is large relative to the rim's
  own structural half-height (`rim_radius * 0.35`, i.e. ~7× larger), so
  contact can fire while the ball is still comfortably above the rim's
  actual top edge, simply because it's "in the neighborhood."
- **Can contact occur while the ball is visibly above the rim?** **Yes,
  routinely** — confirmed directly in every case inspected below.

### 2. Forensic tables

**Legend:** `dx/r`, `dy/r` = horizontal/vertical offset from rim center, in
rim radii (positive dy = below rim center, image-y convention). `above` =
existing `_above_rim` (y < rim_top_y = rim_center_y − 0.35·radius).

#### SHOWCASE Shot 2 — genuine MADE, false reversal flag

| | |
|---|---|
| A. Current contact | frame 393, t=13.10s |
| B/C/D. At contact | dx/r=+0.43, dy/r=−2.23 (ball ~2.2 rim-radii ABOVE center) |
| E. State | descending overall (part of `near_apex_descent`) |
| F. Observed | DETECTED |
| G. First wide-band frame | 390 |
| H. First tight+near-height frame (=contact) | 393 |
| I. First frame with strict horizontal rim-radius overlap (`|dx|<=r`) | **393 — already true at contact** (not the problem) |
| J. Likely true interaction frame (visual/trajectory) | **~418** (first frame with `above=False`, i.e. `dy/r` crosses from −0.27 to +0.09 — the ball genuinely reaches rim height here for the first time; a later clean pass-through continues from there, confirmed separately in `docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md`) |
| K. Difference | **+25 frames (~0.83s) later than current contact** |
| L. Would moving the anchor help? | **Yes, clearly** — it would exclude the entire early high-altitude approach wobble (frames 393–415) that is the source of the false reversal flag. |

#### SHOWCASE Shot 9 — true rattle MISS, correctly strong-flagged

| | |
|---|---|
| A. Current contact | frame 2437, t=81.26s |
| B/C/D. At contact | dx/r=−0.63, dy/r=−1.78 (ball ~1.8 rim-radii above center) |
| E. State | descending |
| F. Observed | DETECTED |
| G. First wide-band frame | 2431 |
| H. First tight+near-height frame (=contact) | 2437 |
| I. First frame with strict horizontal rim-radius overlap | 2434 (dx/r=+0.48) — 3 frames *before* current contact |
| J. Likely true interaction frame (visual/trajectory) | The confirmed reversal itself (max depth at frame 2442, confirmed bounce-back by frame 2459) **occurs entirely while `dy/r` stays between −0.6 and −1.8 — i.e. the whole rattle happens above `rim_top_y`.** The first frame with `above=False` doesn't occur until **frame 2461** — after the bounce is already fully complete. |
| K. Difference (current → "not above_rim" anchor) | **+24 frames (~0.8s) later — landing AFTER the reversal already happened** |
| L. Would moving the anchor (in Shot 2's direction) help or hurt? | **Hurts, decisively.** The same "require not-above-rim" tightening that fixes Shot 2 would destroy Shot 9's detection entirely — its whole bounce is already over by the time that stricter gate would open. |

#### SHOWCASE Shot 10 — genuine MADE, clean no reversal (control)

| | |
|---|---|
| A. Current contact | frame 2724, t=90.83s |
| J. Likely true interaction frame | ~2730 (first `above=False`) — a 6-frame shift |
| L. Would moving the anchor help or hurt? | **Neutral** — trajectory from 2730 onward is still a clean, monotonic descent (already verified in Part 2); a later anchor doesn't introduce or remove any reversal here. |

#### V4 known false-MADE/rattle (shot_index 9, t≈70s)

Using the sparser candidate-pair sample (only tight-band frames; a genuine
excursion outside the tight band, if any, would not appear here — see
caveat in Section 6):

| | |
|---|---|
| A. Current contact | frame 2122, t=70.83s |
| B/C/D. At contact | dx/r=+0.41, dy/r=−1.49 |
| I. First strict rim-radius horizontal overlap | 2133 (dx/r=+0.08) |
| **Observed trajectory shape, contact → tight-band exit (frame 2122 → 2155)** | **Smooth, monotonic, single-direction diagonal descent** — y rises steadily from 109.9 to 190.7+ while x drifts steadily rightward (dx/r from −0.82 to +2.01) the entire time. **No vertical reversal (y decreasing then increasing) appears anywhere in this sampled range.** |
| Re-inspected contact-sheet (`data/diagnostics/rim_interaction_clips/v4_shot09.png`, frames 2110–2167) | Ball touches the rim area (~frame 2138–2142, net visible), then continues moving **down and to the right** continuously through frame 2150 before leaving the crop — **no visible bounce back up**, unlike showcase Shot 9's contact sheet. (An earlier session turn mischaracterized this clip as showing a clear bounce-out; direct re-inspection this pass does not support that — see Section 6.) |
| L. Would moving the anchor help? | **No evidence that it would** — there is no reversal anywhere in the observed data for any anchor choice to reveal. This is not an anchor-timing problem. |

#### V4 dangerous miss ~139s (shot_index 17)

| | |
|---|---|
| Observed shape (tight-band samples) | y: 127→135→140 (descending) → **124 at frame 4209** (a real ~16px / 0.5-radius rise) → 138 at frame 4214 (descending again) → continues down past 175+ | 
| Assessment | A genuine, if modest, vertical wobble **is present** in the raw data — yet the shadow module (Part 3) reported no reversal for this shot. The exact reason could not be fully resolved without V4's dense per-frame trace (not available without a full rerun, avoided per instruction) — plausibly a contact-frame/pre-window exclusion detail, or the wobble's frames being classified as pre-contact rather than post-contact. Reported as unresolved, not guessed at. |

#### V4 dangerous miss ~187s (shot_index 21)

| | |
|---|---|
| Observed shape (tight-band samples) | y: 127.6 → **80.7 at frame 5650** (a large ~47px / 1.6-radius rise, ball moving well further above the rim) → back down through 132.8 (frame 5659) → continues down past 177+ |
| Assessment | A large, clean, unambiguous vertical reversal, entirely consistent with the shadow module's own strong reversal+escape finding (Part 3). **This is the concept's clearest working example on V4.** |

#### V4 genuine MADE (shot_index 15, t≈124s)

| | |
|---|---|
| Observed shape | y: 115.4 → 136.7 → 140.0 → (gap) → 167.9 → 171.1 → ... → 294.0, monotonically increasing throughout, `above` flips to `False` at frame 3778 and never reverses. |
| Assessment | Clean, no reversal anywhere — consistent with Part 3's 0/7 genuine-MADE false-flag finding. |

(Shots 11, 12, 19, 20 not individually re-tabulated this pass; Part 3
already established all 7 genuine-MADE V4 shots show `reversal_detected=False`,
and nothing in this pass's spot checks contradicts that.)

### 3/4. Structural contact definition and the critical question

**Candidate structural definition tested:** "first descending, tight-band
point that is no longer above the rim's own structural top edge" —
`not od._above_rim(p, hoop)` combined with the existing `tight_band` check.
Uses only existing helpers/config (`_above_rim`, `_in_band`, `tight_band`);
introduces no new numeric fraction.

**Result: this definition helps Shot 2 (shifts contact from 393 → ~418,
correctly past the early wobble) but destroys Shot 9 (shifts contact from
2437 → ~2461, landing after the rattle it exists to detect is already
over).** Both shots' problematic/target evidence sits in the exact same
geometric regime (well above `rim_top_y`, within the existing generous
`near_rim_height` tolerance) — there is no position-only boundary between
"still approaching, not yet touching" (Shot 2's early wobble) and "already
touching and rattling" (Shot 9's real bounce) using the rim's existing,
symmetric, center-based geometric model. This is very likely a camera-angle/
perspective effect: the front rim edge nearest the camera projects visually
higher (smaller y) than the simple circular rim model's `rim_top_y` implies,
so a real touch near the front rim can occur well before the ball's y
coordinate ever crosses that computed threshold.

**No other candidate anchor tried in this pass (closest-approach-distance,
strict-radius horizontal overlap) resolves this** — each shares the same
fundamental issue, since they are all variations on "how close, by this
same rim-centered model, is the ball to the rim" and Shot 9's real contact
happens at a "not very close by that model" position.

**Answer to the critical question (Section 4 of the task): NO.** A single
structural, non-fitted contact-anchor redefinition does not fix both
directions simultaneously.

### 5. No new constants

N/A beyond the analysis above — no anchor change is being proposed for
implementation (see Section 8's decision).

### 6. Raw tracking limitation vs. anchor vs. real physical interaction

For V4's known false-MADE case specifically: the observed, reliable
(tight-band-sampled) trajectory is **smooth and physically coherent** (no
sudden jumps, no alternating-cluster artifact of the kind found in
showcase's raw signal in Parts 1–3) — this argues against tracker lag or
object-switching as the explanation. It shows **no reversal at all**, not a
reversal that's merely mistimed — which argues against "wrong anchor" as a
sufficient explanation too, and against "genuinely slow rattle exceeding
0.75s" (there's no wobble to be too slow *for*, anywhere in the sampled
range). The most consistent explanation given the available evidence is
that **this specific shot's true miss mechanism is a lateral deflection
while continuously descending, not a vertical bounce-back** — a physically
different event from showcase Shot 9's and V4 Shot 21's vertical rattles,
which the current concept (built specifically around vertical y-reversal)
was never designed to detect. **Caveat:** this is based on tight-band-
restricted samples, not V4's dense per-frame trace (unavailable without a
full rerun, avoided this pass) — a brief excursion outside the tight band
that would reveal a real reversal cannot be fully ruled out, though the
re-inspected contact-sheet image (Section 2 above) is consistent with this
finding, not contradicting it.

### 7. Proposed anchor

**None proposed for implementation.** The one candidate tested (Section 3/4)
was falsified by Shot 9 before reaching the point of drafting a
current→proposed table for all cases; per the task's own instruction, no
second candidate anchor was invented to chase past that result, and no
threshold-fitting was attempted.

### 8. Decision

**STOP REVERSAL ARCHITECTURE**, on the current vertical-reversal concept,
without a further contact-anchor correction attempt. The evidence answers
the task's own stated gate directly: Section 4's critical question is NO
(Shot 2 and Shot 9 require anchors that move in incompatible directions
given the existing geometry), and Section 6's distinction lands on "a
different physical event, not an anchor or tracking problem" for at least
one dangerous case (V4's actual known false-MADE — the specific case this
whole prototype exists to catch). No further threshold experiment is
proposed, per instruction.

---

## Final report — Part 4

**A. Current contact definition:** first (chronologically) reliable point
that is within the existing `tight_band` horizontally AND within the
existing `near_rim_height` (2.5× rim radius) tolerance vertically — a
generous, symmetric, center-based tolerance untethered from the rim's own
structural top/bottom edges; can fire while the ball is still visibly well
above the rim.

**B. Why Shot 2 anchors too early:** `near_rim_height`'s tolerance is wide
enough that contact fires at frame 393 while the ball is still ~2.2 rim-
radii above the rim center (comfortably above `rim_top_y`) — 25 frames
(~0.83s) before the ball genuinely reaches rim height.

**C. Why Shot 9 works:** its real, visually-confirmed rattle (touching the
rim, bouncing back up) happens to occur within 0.23s of the *current*
(early) contact anchor — coincidentally well-timed relative to the loose
anchor, not because the anchor is correct in any deeper sense.

**D. Why V4's false-MADE misses the reversal:** the observed trajectory
shows a smooth, monotonic diagonal descent with no vertical reversal
anywhere in the sampled data — most consistent with a genuinely different
miss mechanism (lateral deflection, not vertical bounce), not explained by
anchor timing alone.

**E. Tracker/data-quality contribution:** minimal for this specific case —
the sampled trajectory is smooth and coherent, unlike the alternating-
cluster contamination pattern seen elsewhere in this investigation. Caveat:
based on tight-band-restricted samples only, not a dense per-frame trace.

**F. Best structural contact definition found:** "first non-above-rim,
tight-band point" (`not _above_rim` + existing `tight_band`) — tested and
**rejected**, because it fixes Shot 2 but destroys Shot 9.

**G. New constants required:** N/A — no anchor is being proposed.

**H. Shot 2 current → proposed contact:** frame 393 → ~418 (+25 frames, ~0.83s).

**I. Shot 9 current → proposed contact:** frame 2437 → ~2461 (+24 frames,
~0.8s) — **lands after the target reversal is already complete.**

**J. V4 false-MADE current → proposed contact:** not applicable — no anchor
placement reveals a reversal, since none is present in the observed data.

**K. Effect on V4 genuine makes:** not separately re-tested this pass (no
anchor change is being proposed to implement); the one spot-checked genuine
MADE (shot 15) shows a clean monotonic trajectory with no reversal
regardless of anchor placement.

**L. Whether 0.75s remains sufficient:** moot given F's rejection — no
anchor change is being carried forward to test window sufficiency against.

**M. Expected regression risk:** N/A — nothing is being implemented.

**N. Decision: STOP REVERSAL ARCHITECTURE.**

**O. Production unchanged:** confirmed — `git status` shows no changes
under `app/events`, `app/pipeline`, `app/vision`, `app/tracking`.

**P. Shadow prototype unchanged:** confirmed — `app/research/post_contact_reversal.py`
SHA-256 `b87d33778af76ddcf0d1ae0cc859bf9a483d9b37d2b11c8c8d9aafbbbf5ad846`,
identical to the frozen value from Parts 2/3, verified before and after
this forensic pass.

**Q. Tests remain 209/209:** confirmed, re-run this pass (197 production +
12 shadow, 0 failed).
