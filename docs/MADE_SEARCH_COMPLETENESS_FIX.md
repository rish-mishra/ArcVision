# MADE Search-Completeness Fix — Attempted, Tested, and Reverted

**Date:** 2026-09-08
**Scope authorized:** the single search-completeness bug documented in
`docs/FINAL_DEMO_RELIABILITY_FORENSIC.md` — nothing else.
**Outcome: REVERT FIX.** The fix is fully reverted. Production code and the
test suite are back to their exact pre-turn state (190 tests passing, same as
before this turn began).

This document exists so the investigation is not lost even though the change
was not kept: the bug is real, the fix was implemented correctly and did what
it was supposed to do, and it was rejected for a specific, measured reason.

---

## 1. The bug

In `app/events/outcome_detector.py`'s `detect_outcome()`, the MADE-candidate
loop iterated over above-rim points `a` and, for each `a`, computed only the
chronologically **earliest** eligible below-rim point `b`:

```python
b = min(later_below, key=lambda x: x.frame_index)
```

If that single `(a, b)` pair failed any gate (drift, deflection, occlusion),
the code did `continue` on the **outer** loop — abandoning `a` entirely and
moving to the next candidate `a`, even when a *later* `b` for the *same* `a`
existed in the already-collected `descent_below_tight` set and would have
passed every gate unchanged.

Forensic tracing on the new demo footage (`scripts/forensic_arcvision_demo_final.py`,
see `docs/FINAL_DEMO_RELIABILITY_FORENSIC.md`) showed this was the dominant
root cause of wrong/unresolved outcomes: 6 of 11 truth shots in that footage
were affected by this exact code path.

## 2. The fix (as implemented and tested)

Restructured the loop so the inner search is exhaustive over all
chronologically-valid `b` candidates for a given `a`, trying each in
ascending frame order until one fully passes every existing gate:

```python
later_below = sorted(
    (b for b in descent_below_tight
     if b.frame_index > a.frame_index
     and (b.timestamp_sec - a.timestamp_sec) <= cfg.max_seconds_through_rim),
    key=lambda x: x.frame_index,
)
for b in later_below:
    drift = abs(b.center_x - a.center_x)
    if drift > max_drift:
        continue          # now advances b, not a
    ...
```

**Zero constants or thresholds changed.** Every gate (drift, deflection,
occlusion dip, all `OutcomeConfig` values), every part of the confidence
formula, and the MISS/UNKNOWN logic were byte-identical to the pre-fix code.
The only semantic change: a valid later pair that used to be silently skipped
could now be found and evaluated. Confirmed by direct code diff before this
change was reverted.

## 3. Regression tests written first (Step 1)

Five synthetic, pipeline-free tests were added in a new file,
`tests/test_outcome_detector.py`, calling `detect_outcome()` directly with
constructed `BallObservation`/`HoopLocation` fixtures (no real video, no
timestamps/filenames/ground truth from any recording). This file has since
been **removed** as part of the revert (Section 5); its content is preserved
here for the record.

| Test | Purpose | Pre-fix result (measured) | Post-fix result (measured) |
|---|---|---|---|
| A — later pair fully passes, earliest pair fails drift | Core fix target | **FAIL** — `UNKNOWN` / `rim_crossing_observed_but_low_confidence`→ actually `insufficient`/`no phase sequence met the positive-evidence bar` reason, confidence never reached MADE | **PASS** — `MADE`, confidence ≥ 0.45 |
| B — no pair anywhere passes every gate | Exhaustive search must not manufacture false positives | PASS (`!= MADE`) | PASS (`!= MADE`) |
| C — clean small-drift crossing but no confidence dip | Occlusion gate must still reject a plausible same-depth-plane airball | PASS (`!= MADE`) | PASS (`!= MADE`) |
| D — earliest pair already passes | No behavior change in the common case | PASS (`MADE`, same evidence) | PASS (`MADE`, same evidence, unchanged) |
| E — only 2 trajectory points | Earlier abstention path untouched | PASS (`UNKNOWN` / `insufficient_ball_trajectory_data`) | PASS (unchanged) |

Test A was verified to fail against the *unmodified* production code for
exactly the documented reason (the later, fully-passing `b` was never
evaluated) before the fix was written — confirming the bug is real, not a
test artifact.

**Post-fix full suite:** 195 passed, 0 failed (190 pre-existing + 5 new).
Zero pre-existing tests regressed.

(Note: earlier turns in this session had cited a baseline of "218 passing"
tests; a fresh `--collect-only` and per-file count this turn established the
actual pre-existing total as 190, not 218. That discrepancy predates this
turn's work — no test files were modified or deleted by this fix — and is
flagged here as unresolved and worth checking independently. It did not
affect this turn's pass/fail comparisons, which were always measured
directly, not assumed.)

## 4. V1–V4 regression run (Step 4)

Full pipeline re-run via `scripts/overnight_v1v2v3v4_regression.py`
(`run_pipeline()` directly, no HTTP layer) under the fixed code, compared
against a preserved pre-fix run
(`data/diagnostics/overnight_regression_prefix_fix/`).

**V1 — no change.** Outcomes, confidences, session summary, and coaching
output all identical before and after.

**V2 — no change.** Same as V1.

**V3 — changed, no frozen ground truth exists for V3** (per this session's
standing rule not to invent ground truth for videos that were never frozen
with one). Outcome sequence before: `unknown, unknown, unknown, missed, made`
(1 made / 1 missed / 3 unknown, 50.0% coverage). After:
`made, unknown, made, missed, made` (3 made / 1 missed / 1 unknown, 75.0%
coverage). Two UNKNOWNs became MADE; nothing became MISSED. Coaching
strength/priority unchanged. This can only be reported as "behavior changed,"
not scored for correctness.

**V4 — changed, and this is where the fix fails the acceptance bar.**
V4 has a frozen 18-shot ground truth (`docs/VIDEO4_EVALUATION_PROTOCOL.md`)
and 5 documented false-positive shot-window release times to exclude
(`docs/VIDEO4_FORENSIC_ANALYSIS.md`).

| Metric | Before (pre-fix) | After (fix applied) |
|---|---|---|
| Total detected shot windows | 23 | 23 |
| made | 3 | 5 |
| missed | 9 | 9 |
| unknown | 11 | 9 |
| Matched to ground truth (of 18) | 18 | 18 |
| False MADE (truth MISSED, called made) | **1** | **3** |
| False MISSED (truth MADE, called missed) | 3 | 3 |
| Classified coverage | 66.7% | 77.8% |

Per-shot detail for the exact 3 shots that changed outcome (matched to
ground truth by release time, ±2s exclusion around the 5 known false-positive
windows):

| shot_index | release_time_sec | ground truth | before | after | after confidence |
|---|---|---|---|---|---|
| 17 | 124.54 | MADE | made | made | 0.621 (unchanged, listed for context) |
| 19 | 138.99 | **MISSED** | unknown | **made** | 0.468 |
| 23 | 187.19 | **MISSED** | unknown | **made** | 0.516 |

(shot_index 17 did not change — included only to show the full changed-outcome
context was checked; the two genuinely new outcome flips are shot_index 19
and 23.)

The pre-existing, already-known ~70s false-MADE case (shot_index 10,
release_time_sec ≈ 69.7, truth MISSED) is **confirmed unchanged** — still
called `made` at confidence 0.588 both before and after. That specific
case did not get worse.

**However, two entirely new false-MADE calls were introduced** — shots that
were correctly abstaining (`unknown`) before the fix and became confident,
reportable `made` calls (both above the 0.45 reporting threshold) after it,
on shots whose frozen ground truth is MISSED. This is precisely the failure
mode the fix's own design reasoning (Section 2, `docs/FINAL_DEMO_RELIABILITY_FORENSIC.md`)
argued it would not cause, because it does not weaken any individual gate —
it only searches more pairs, each of which must still pass the exact same
gates as before. In practice, on this footage, a second/third-choice
`(a, b)` pair can happen to fully satisfy drift + deflection + occlusion
gates by coincidence on a shot that was genuinely a miss, and the exhaustive
search now reaches and reports it instead of correctly stopping at UNKNOWN.

## 5. Critical regression check and decision (Steps 4/6)

The task's explicit instruction: *"CRITICAL REGRESSION CHECK: V4's known
~70s false-MADE must NOT become worse because of this change. If V4 gains
new confident incorrect MADE calls: STOP. Do not proceed to final demo."*

V4's false-MADE count went from **1 → 3**. This is a direct violation of the
stop condition. Per instruction, **the final demo was NOT re-run** — Step 5
was skipped entirely.

Decision criteria (Step 6):
1. Synthetic regression test proves old implementation incomplete — **met** (Test A).
2. All existing tests pass — **met** (0 regressions among the 190 pre-existing tests).
3. No unacceptable V1–V4 regression — **NOT met** (V4 false-MADE count tripled).
4. V4 does not gain new false-confident MADE behavior — **NOT met** (2 new cases).
5. Final-demo behavior changes in the predicted direction — **not evaluated**, gated out by criterion 4's failure.

Criteria 3 and 4 fail. Per the task's own decision rule, this is conclusive.

**Decision: REVERT FIX.**

## 6. What was reverted

- `app/events/outcome_detector.py` — the MADE-candidate loop restored
  exactly to its pre-turn form (earliest-`b`-only search, outer-loop
  `continue` on any gate failure). Verified byte-for-byte against the
  pre-fix version captured at the start of this turn.
- `tests/test_outcome_detector.py` — removed. It tested behavior (the
  exhaustive search) that is no longer present in production; keeping a
  test that asserts reverted behavior would leave a permanently-failing
  test in the suite. Its fixtures and pre/post-fix results are preserved
  verbatim in Section 3 above.
- Full suite re-run after revert: **190 passed, 0 failed** — identical to
  this turn's starting state.
- `docs/FINAL_DEMO_BLIND_EVALUATION.md` — not touched at any point this
  turn; confirmed still present and untouched.
- `arcvision_demo_final.mov` — never re-processed under the fixed code.
  Step 5 was correctly never reached.

## 7. Why this differs from "the fix was wrong"

The fix was not buggy — it did exactly what it was designed to do: search
exhaustively among candidates that must each still pass the same unchanged
gates. The forensic diagnosis (a search-completeness gap) was also correct
and explained real UNKNOWN/wrong outcomes on the new demo footage. What this
experiment shows is that on V4 specifically, the *existing* gates (drift,
deflection, occlusion dip) are not tight enough to guarantee that a
second-or-later valid-looking `(a, b)` pair on a genuine miss won't
coincidentally satisfy all of them. Searching harder amplified that
pre-existing gate-precision limitation rather than only fixing the intended
problem. Any future attempt at this class of fix would need to either
tighten the gates themselves (out of scope for this turn) or add a
different, principled way to prefer the "most convincing" passing pair
rather than the first one found — neither of which was attempted here, per
the "no second fix in this turn" constraint.
