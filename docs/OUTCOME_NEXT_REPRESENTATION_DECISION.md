# Outcome Next-Representation Decision — Postmortem + Forward Path

**Date:** 2026-09-09
**Scope:** Synthesis and decision only. No code was written or modified this
pass. Draws on everything established in `docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md`
(Pass #1), `docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md` (Pass #2), and
`docs/POST_CONTACT_REVERSAL_SHADOW.md` (Passes #3/#3B/#3C, now closed).

**Zero production files changed. Tests: 209 passed (197 production + 12
shadow), 0 failed — unchanged, since nothing was modified this pass.**

---

## 1. Failure taxonomy

| Category | Definition | Showcase cases | V4 cases |
|---|---|---|---|
| **A. Clean swish / obvious downward pass-through** | Continuous, monotonic descent through the net, no reversal, no lateral escape | 2, 4, 6, 7, 10 (10 correctly MADE; 2/4/6/7 visually confirmed clean but currently UNKNOWN/MISSED) | 15, 19 (correct); 11, 12, 3 (visually/structurally clean makes, currently MISSED via MISS-logic preemption — see `docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md` Section 3) |
| **B. Rim-assisted make / roll-in / bank-in** | Genuine make, but the ball's path shows real lateral movement or a bank/roll before dropping in | 1, 3 (visually ambiguous, lean MADE — see `OUTCOME_VISUAL_INFORMATION_AUDIT.md` Section 5) | None clearly identified this session |
| **C. Rattle-out with upward reversal** | Ball enters the rim's interaction zone, then genuinely reverses vertical direction and exits | 9 (confirmed: clean, contact-local reversal+escape at 0.23s — `POST_CONTACT_REVERSAL_SHADOW.md` Part 2/3) | 21 (confirmed: large, clean vertical reversal, correctly flagged by the shadow prototype); 17 (a smaller vertical wobble is present in the raw data but was not caught — unresolved, `POST_CONTACT_REVERSAL_SHADOW.md` Part 4) |
| **D. Rim interaction followed by diagonal/downward escape, no reversal** | Ball touches/nears the rim then continues away on a smooth diagonal path — no vertical bounce-back at all | Not clearly identified as distinct from A/E this session | **9, the known false-MADE** — re-inspected directly this session (`POST_CONTACT_REVERSAL_SHADOW.md` Part 4, Section 2): smooth monotonic diagonal descent, no reversal anywhere in the sampled trajectory |
| **E. Clean miss / clear deflection** | Ball never plausibly reaches the rim's vicinity, or deflects away with no rim-adjacent ambiguity | 5, 8 (both correct, airballs) | 4, 5, 6, 8, 13, 14 (all correct) |
| **F. Visually ambiguous or insufficiently observed** | Neither a human nor the current geometry can confidently resolve it from available evidence | 1, 3, 11 (visual audit: genuinely ambiguous from still frames) | 2, 20 (truth MADE, occlusion gate rejects a visibly clean pass-through — same mechanism as showcase 1/2/3/6) |

**V1/V2/V3 were not re-examined against this taxonomy this session** — they
were not part of the physical-evidence/visual-audit/reversal forensic chain
this pass draws on, and are not included here rather than guessed at.

No label was invented where the evidence was insufficient: category D was
only assigned to V4 shot 9 after direct re-inspection of its raw trajectory
and contact-sheet image confirmed the absence of a reversal — it was not
assumed from the taxonomy alone.

## 2. Information audit

| Information | Availability | Basis |
|---|---|---|
| Ball center trajectory | **AVAILABLE AND RELIABLE** | The one signal the whole architecture is already built on; well-tracked away from rim contact |
| Rim geometry (center, radius) | **AVAILABLE AND RELIABLE** | Hoop calibration is high-confidence and stable across both videos (0.96+ confidence, thousands of votes) |
| Temporal ordering / timestamps | **AVAILABLE AND RELIABLE** | Exact per-frame timestamps used throughout |
| Ball bbox / apparent size | **AVAILABLE BUT UNINVESTIGATED** | Present in the detector output but never extracted into the trajectory representation; flagged in `OUTCOME_VISUAL_INFORMATION_AUDIT.md` as plausibly too small/noisy at this resolution (~15-30px) to carry a reliable depth signal, but not conclusively tested |
| Local velocity | **AVAILABLE BUT NOISY** | Directly computed, but raw per-frame velocity spikes wildly near rim contact in both videos' raw signal (see below) |
| Trajectory curvature | **AVAILABLE BUT NOISY** | Same contamination as velocity — repeatedly observed alternating dual-position artifact in the raw ball-tracker output right around rim interaction, in both showcase (`POST_CONTACT_REVERSAL_SHADOW.md` Parts 1-3) and structurally similar noise patterns flagged in V4's own forensic work |
| Entry/exit side (above/below/beside rim) | **AVAILABLE BUT NOT RELIABLY DISCRIMINATING** | Directly computable, but Pass #3C found the same geometric region (above the rim's computed top edge) contains both genuine contact and mere approach — a camera-perspective effect, not a data-availability gap |
| Disappearance / reappearance (occlusion) | **AVAILABLE BUT PROVEN UNRELIABLE** | Directly tracked (`DataSource`/confidence dip), but Pass #1 found it anti-correlated in this data — the known rattle showed *more* apparent occlusion than several genuine clean makes |
| Net deformation / net motion | **NOT AVAILABLE — never computed** | Visually present and informative in multiple inspected clips (net visibly wrapping the ball in genuine makes), but nothing in the current pipeline extracts it |
| Backboard interaction | **NOT OBSERVED IN THIS DATASET** | No inspected shot this session showed backboard involvement — inconclusive either way, not a confirmed gap |
| Short rim-centered raw pixel sequence | **AVAILABLE, AND CONFIRMED INFORMATIVE** | `OUTCOME_VISUAL_INFORMATION_AUDIT.md`: 8 of 11 showcase shots were unambiguously classifiable by direct human inspection of exactly this — and it is entirely unused by the current architecture |

## 3. Critical question: is trajectory-only viable?

**NO, for the core rattle-vs-clean-make discrimination — with one important,
narrower exception that remains YES.**

Justification from the actual failures, not in the abstract:

- **NO for categories A/C/D discrimination.** Pass #3C directly falsified a
  trajectory-only geometric rule for this: showcase's rattle (C) and V4's
  actual false-MADE (D) require contact anchors that move in *opposite*
  directions relative to each other, and no non-fitted structural
  redefinition satisfies both. This is not merely "no threshold has been
  found yet" — the underlying camera-perspective effect (the same position
  band contains both "just approaching" and "already touching") makes this
  a structural, not a tuning, limitation of position-only geometry.
- **NO, independently, because of raw signal quality.** The alternating
  dual-object contamination found repeatedly in the raw ball-tracker output
  right at rim interaction (both videos) means even a perfectly-designed
  geometric rule would be reasoning over partially corrupted input in
  exactly the window that matters most.
- **YES, narrowly, for one already-identified sub-problem.** The
  false-negative-MADE preemption pattern (showcase 4/7/11, V4 11/12/3 — all
  category A shots wrongly reaching a confident MISS) has an existing,
  already-forensically-validated, zero-new-constant deterministic fix: gate
  Case 1/2/3's MISS evidence on `n_candidate_pairs > 0` (`docs/OUTCOME_PHYSICAL_EVIDENCE_FORENSIC.md`
  Section 7). This is a different, more tractable problem than rattle
  discrimination — it doesn't require telling a rattle apart from a swish,
  only recognizing that a plausible crossing candidate existed at all — and
  it remains unimplemented. It is called out here because it is the one
  clear trajectory-only win still on the table, orthogonal to everything
  else in this document.

## 4. Option comparison

| | **A. Richer deterministic trajectory episode** | **B. Net-motion/deformation from rim crop** | **C. Small learned temporal classifier** | **D. Hybrid (deterministic gate + visual resolver on ambiguous cases only)** |
|---|---|---|---|---|
| New information captured | None — already attempted and closed (Pass #3) | Net deformation/motion, currently unused entirely | Full raw appearance + motion, richest possible | Same as B/C, but only invoked where A already fails |
| Training required | No | Not necessarily (can be handcrafted via frame-differencing/optical flow) | **Yes** | Only if the resolver chosen is C-style; not if B-style |
| Data requirement | None | None for a handcrafted version | Hundreds-to-thousands of labeled clips (per Pass #2) | None if resolver = B; same as C if resolver = C |
| Expected generalization | **Disproven this session** (Pass #3C) | Uncertain — V4's net was visibly harder to read than showcase's own footage (`OUTCOME_VISUAL_INFORMATION_AUDIT.md`) | Poor, given the data shortfall — high risk of memorizing the 2 known camera setups | Better than B/C alone — bounded scope reduces exposure to both B's appearance-variance risk and C's data shortfall |
| Implementation complexity | Low-medium | Medium-high (new CV stage, no existing scaffolding) | Medium (model) / high (full ML pipeline: labeling, training, eval, versioning) | Medium — reuses existing episode/gate logic unchanged, adds one new bounded-scope module |
| Runtime impact | Negligible | New but bounded (per-shot crop + motion computation) | New, plus a model dependency | Bounded — only runs on the minority of already-ambiguous shots |
| Explainability | High | Medium (a computed motion-magnitude signal is interpretable) | **Low** — black box, a real concern given this project's whole-session preference for defensible logic | High for the majority (unchanged path); medium only for the minority the resolver touches |
| Overfitting risk | High in practice (three separate attempts this session each "worked" on some cases without generalizing) | Medium | **Very high**, given the data shortfall | Lower than B/C alone — the resolver's mistakes are bounded to already-uncertain cases, not the whole classification |
| Enough data NOW | Yes (moot — closed) | Yes, for a first handcrafted prototype | **No** | Yes, if the resolver starts as B-style (handcrafted, no training) |

## 5. Data reality check

Approximate inventory across the videos with real forensic labeling this
session (showcase + V4; V1/V2/V3 have their own historical ground truth but
were not re-categorized into this taxonomy):

| Bucket | Approximate count |
|---|---|
| Clean makes (category A) | ~10 (5 showcase + 5 V4, including 3 V4 shots currently misclassified but structurally clean) |
| Rim-assisted / bank-in makes (category B) | ~2 (both showcase, ambiguous) |
| Clean misses (category E) | ~8 (2 showcase + 6 V4) |
| Rattle-outs (category C) | **~2 confirmed** (showcase 9, V4 21) + 1 weak/unresolved (V4 17) |
| Diagonal-escape misses (category D) | **1 confirmed** (V4 9) |
| Difficult/ambiguous (category F) | ~5 (3 showcase + 2 V4) |
| Distinct camera setups | **2** |

**This is sufficient for continued deterministic development and
validation** (the same small corpus this entire session's forensic work has
already been using productively) **but is not remotely sufficient for
training anything** — 2 camera setups and roughly 2-3 confirmed examples of
the rarest, most decision-relevant category (rattle-outs) is one to two
orders of magnitude short of what Pass #2 already estimated is needed
(hundreds to low thousands, across meaningfully varied setups) for a
learned classifier to generalize rather than memorize. This has not changed
since Pass #2 and is not re-litigated here.

## 6. Public dataset possibility

**NONE KNOWN**, re-confirmed against current project sources without a new
web search (per instruction): `data/datasets/` contains only ball/rim
*object-detection* datasets (`basketball_ball_rim*`, `basketball_shooting_robot_raw`
— a Roboflow ball/rim bounding-box set), and `scripts/download_basketball_dataset.py`
is the only integrated external-dataset script, targeting that same
detection dataset. No shot-outcome-labeled (MADE/MISSED) video corpus is
referenced anywhere in the project's docs or scripts. This matches Pass #2's
own finding (`OUTCOME_VISUAL_INFORMATION_AUDIT.md` Section 7) exactly — not
re-derived, re-confirmed.

## 7. Weighing against the showcase goal

The product goal is trustworthy outcomes on the 11-shot showcase **and**
cross-video reliability on V4, without hardcoding, timestamp special-casing,
manual overrides, hidden UNKNOWNs, or constants fitted to one video.

- Option A is closed — it cannot help either video further without becoming
  exactly the kind of fitted special-casing the project has repeatedly and
  deliberately avoided (three attempts this session, each one initially
  promising on a subset, each one failing to generalize to the other video).
- Option C cannot be responsibly started — Section 5 is unambiguous.
- Option B alone risks the same single-video-appearance dependency problem
  already observed (V4's net being harder to read than showcase's) if
  applied broadly across every shot.
- **Option D, scoped to a handcrafted (non-learned) resolver, is the only
  option that plausibly helps both videos while staying technically
  defensible right now**: the deterministic majority path (already
  validated safe on both videos throughout this session) is untouched, and
  the new, riskier component is deliberately bounded to only the shots
  where trajectory evidence is already known to be insufficient — which is
  exactly where net-motion or other rim-crop evidence would add genuinely
  new information rather than compete with or override reliable existing
  signal.
- Separately, and not competing with Option D for attention: the
  `n_candidate_pairs > 0` MISS-evidence gate (Section 3) remains an
  independent, ready, low-risk, already-justified fix that was never
  implemented — it is not a "next representation" and doesn't require this
  decision to move forward, but it should not be lost sight of.

## 8. Stop conditions checked

- "Remaining ambiguity requires substantial new labeled data we do not
  have" — **true for Option C**, not for Option D scoped to a handcrafted
  resolver (no training data required to prototype it).
- "Proposed deterministic fixes become fitted special cases" — **true for
  Option A**, which is why it stays closed; not proposed again here.
- "Available monocular evidence is genuinely insufficient" — **not
  supported**: the visual audit found real, human-visible evidence in 8 of
  11 showcase shots that the current architecture simply doesn't capture
  (net deformation, post-contact motion shape). The evidence exists; it is
  the representation that is missing it.

None of the stop conditions apply cleanly to the narrower Option D path.
**A next architecture is recommended, not a stop.**

---

## Final report

**A. Failure taxonomy:** six categories (A–F) defined and mapped in Section 1
— clean swish, rim-assisted make, rattle-out (vertical reversal), diagonal
escape without reversal (newly distinguished from rattle-out this pass),
clean miss, and visually/evidentially ambiguous.

**B. Trajectory-only architecture viable:** **NO** for the core rattle/
clean-make/diagonal-escape discrimination (directly disproven, Pass #3C).
**Narrow YES** for the separate false-negative-MADE preemption problem (the
still-unimplemented `n_candidate_pairs > 0` gate).

**C. Missing information:** net deformation/motion (never computed, visually
confirmed informative) is the clearest concrete gap; ball bbox/apparent
size is available but unexploited and untested.

**D. Option comparison:** see Section 4 table. A is closed; C is blocked by
data; B carries cross-video appearance risk if applied broadly; D bounds
that risk by only engaging new evidence on already-ambiguous shots.

**E. Current labeled-data inventory:** ~10 clean makes, ~2 rim-assisted
makes, ~8 clean misses, ~2-3 rattle/diagonal-escape examples, ~5 ambiguous
cases, across only 2 distinct camera setups (Section 5).

**F. Training-data sufficiency:** **NO** — one to two orders of magnitude
short of what a learned classifier would need to generalize rather than
memorize.

**G. Public temporal MADE/MISSED dataset currently known:** **NO — NONE
KNOWN** in current project sources.

**H. Recommended architecture: Option D — deterministic episode/gate
(reusing existing, already-validated geometry) that hands off ONLY
genuinely ambiguous shots to a new, initially handcrafted (non-learned)
net-motion/rim-crop evidence resolver.**

**I. Why it is better than the reversal architecture:** the reversal
prototype (Option A) tried to replace/override the existing trajectory
logic's verdict using more trajectory geometry — repeatedly finding
threshold/anchor configurations that worked on one video's failure mode and
broke on the other's. Option D never overrides a confident existing
verdict; it only adds a new source of evidence for the cases the existing,
validated logic has *already* honestly flagged as uncertain (`UNKNOWN`,
low-confidence) — a fundamentally different, additive risk profile.

**J. Expected effect on showcase:** plausible improvement on shots 1, 3, 9,
11 — exactly the shots visual inspection already showed carry real,
human-visible discriminating evidence (net wrap, reversal shape) the
trajectory representation discards; no effect (by design) on already-correct
shots 5, 8, 10.

**K. Expected effect on V4:** plausible improvement on shots 9, 17 (and the
21-type case would already be resolvable by the closed reversal logic if
that were ever revisited narrowly for confirmed vertical-reversal cases
only — not proposed here); no effect on the 7 genuine MADE shots or 6
clean-miss shots, which the existing deterministic path already handles
correctly.

**L. Biggest unresolved risk:** cross-video appearance variance — V4's net
was independently observed to be harder to read than showcase's in this
session's own visual audit; a net-motion signal validated only on showcase
could fail to transfer, echoing this session's repeated cross-video
generalization failures with trajectory-based signals. Must be validated on
V4 before any showcase-only claim of success is trusted, exactly as this
session's discipline around the reversal prototype already enforced.

**M. Training required:** **NO**, for the recommended first prototype
(handcrafted net-motion/rim-crop resolver, not a learned classifier).

**N. Estimated implementation effort:** medium — a new, bounded-scope CV
component (per-shot rim-crop extraction + a motion/deformation measure,
already informally exercised via the contact-sheet extraction tooling built
in Pass #2) plus a small amount of glue logic to invoke it only when the
existing deterministic path already returns UNKNOWN or low confidence; no
training pipeline, no new model dependency, no labeling infrastructure.

**O. Recommendation: BUILD ONE NEXT PROTOTYPE** — Option D, scoped
specifically to a handcrafted (non-learned) net-motion/rim-crop resolver,
gated by existing UNKNOWN/low-confidence cases only. Not implemented this
turn, per instruction.

**P. Production untouched:** confirmed — `git status` shows no changes
under `app/events`, `app/pipeline`, `app/vision`, `app/tracking`, or
`app/research` this pass (nothing was modified).

**Q. Tests:** 209 passed (197 production + 12 shadow), 0 failed — unchanged,
re-run this pass to confirm, since no code was touched.
