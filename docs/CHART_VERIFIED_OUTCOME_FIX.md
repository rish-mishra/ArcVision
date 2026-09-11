# ArcVision — Remove UNKNOWN From Verified Demo Charts

Fixes a real presentation bug found by manual inspection: the Details/
Mechanics charts colored and legended shots by the raw **automatic**
outcome instead of the same verified-outcome-aware display logic already
used everywhere else in the verified demo. No CV/backend/data change; no
`automatic_outcome`/`verified_outcome`/ground-truth value was touched
anywhere. **Nothing was published or committed.**

## A. Root cause

Confirmed by reading the code, not assumed. `frontend/static/js/app.js`
already has a small central helper for exactly this purpose, added during
an earlier pass and already used correctly in two places:

```js
function displayOutcome(s) { return s.verified_outcome || s.outcome; }
```

- `renderShots()`'s shot chips and `renderReplay()`'s "Jump to shot" chips
  both call `outcomeClass(displayOutcome(s))` — correct.
- `renderMechanics()` (the five per-shot bar charts on the Details/
  Mechanics sub-tab — Knee angle, Elbow angle, Torso lean, Release height,
  Prep duration) built its color array as `shots.map((s) => s.outcome)` —
  the **raw automatic outcome**, bypassing `displayOutcome()` entirely.
  Every shot the automatic classifier called `unknown` (1, 2, 3, 6 in the
  frozen demo) rendered as a gray bar, even though all four have a
  resolved `verified_outcome`.
- The chart legend was a second, independent bug: a hardcoded three-item
  Made/Missed/Unknown block, unconditionally rendered regardless of which
  categories were actually present in what was being plotted.

Two other places reference `.outcome` and were deliberately **not**
changed — see section C.

## B. Files changed

| File | Change |
|---|---|
| `frontend/static/js/app.js` | `renderMechanics()` now colors bars via `displayOutcome(s)` instead of raw `s.outcome`. New `outcomeLegendRow(outcomes)` helper builds the legend from the outcome categories actually present (made/missed/unknown, in that order, each conditional on `Set.has(...)`) instead of a fixed three-item block. Chart subtitle copy becomes "Per shot, colored by verified outcome." when any shot in the session has a `verified_outcome`, otherwise stays "Per shot, colored by outcome." (normal sessions unchanged). |
| `tests/test_frontend_regressions.py` | +6 tests, detailed in section I. |
| `README.md` | Test count 253 → 259. |
| `docs/CHART_VERIFIED_OUTCOME_FIX.md` | This report — new. |

`app/analytics/`, `app/events/outcome_detector.py`,
`scripts/export_demo.py`'s `apply_verified_outcomes()`, and every backend
module were **not touched** — this is a pure frontend rendering fix.

## C. Charts/visualizations audited

Every place in the frontend that colors, groups, filters, or legends
shots by outcome, found by grepping every `.outcome` reference in
`app.js`:

| Location | Uses | Status |
|---|---|---|
| `renderShots()` shot-chip dots | `displayOutcome(s)` | Already correct |
| `renderReplay()` "Jump to shot" chip dots | `displayOutcome(s)` | Already correct |
| `renderShotDetail()` primary Outcome row | `verified_outcome` (own branch) vs `shot.outcome` (non-verified branch) | Already correct — this is the pre-existing verified/automatic split from an earlier pass |
| `renderShotDetail()` "Automatic analysis details" | `shot.automatic_outcome \|\| shot.outcome` | Correct as-is — intentionally the automatic value, that's its whole purpose |
| **`renderMechanics()` bar-chart coloring** | was raw `s.outcome` | **Fixed** — now `displayOutcome(s)` |
| **`renderMechanics()` legend** | was a hardcoded 3-item block | **Fixed** — now generated from displayed categories |
| `renderMvm()` (Makes vs Misses: ranked differentiators, metric table, per-metric strip-chart dot grouping) | raw `s.outcome` in the strip-chart's `madeValues`/`missedValues` split | **Deliberately left unchanged** — see below |
| `renderConsistency()` (coefficient-of-variation ranking) | not outcome-colored at all (ranks metrics, not shots) | N/A, no change needed |
| `renderTrends()` (early-vs-late session) | not outcome-colored (splits by time, not outcome) | N/A, no change needed |
| Coach headline stats (`11 / 8 / 3 / 72.7%`) | reads `session_summary.made/missed/shooting_percentage`, already overwritten with verified totals at export time (`apply_verified_outcomes()`, an earlier pass) | Already correct, not a frontend concern |

**Why Makes vs Misses was left on the automatic grouping, explicitly:**
the effect size, p-value, and made/missed means shown in that sub-tab's
ranked list, comparison table, and per-metric strip charts are a
**backend-computed statistic** (`app/analytics/makes_vs_misses.py`,
`MakesVsMissesReport`) derived from the automatic outcome grouping —
`verified_outcome` doesn't exist anywhere in the backend, only as a
frontend/export-time overlay. Re-grouping just the strip-chart's dots by
`displayOutcome()` without recomputing the statistic they illustrate would
make the chart visually contradict its own effect-size/p-value caption
sitting next to it (e.g. dots regrouped into "made n=8 / missed n=3" next
to a caption still saying "Made n=2, Missed n=5, effect size —"). Doing
that would also mean presenting a made/missed comparison that was never
actually computed — squarely inside "do not estimate anything, do not
create new predictions." This sub-tab stays fully self-consistent by
staying fully automatic, matching the "mechanics/coaching remain
automatic" boundary already established in earlier passes. Visually
confirmed unchanged and internally consistent (`Made n=2, Missed n=5`
throughout) — see the screenshot check in section K.

## D. Shot 1/2/3/6 colors

**Green (MADE)** in every Mechanics chart where each has a plotted value —
confirmed programmatically by reading each bar's `fill` attribute directly
from the live DOM (not eyeballed), not just from a screenshot. These four
shots were exactly the ones the automatic classifier called `unknown`
(the automatic totals are made=2/missed=5/unknown=4), so this is the
direct before/after of the fix: previously gray, now green, matching their
real `verified_outcome`.

## E. Shot 9 color

**Red (MISSED)** — confirmed the same way, at its correct chart position,
in both the Knee-angle chart (10 bars, shot 9 is the 8th) and every other
chart that includes shot 9. Shot 9's `automatic_outcome` is `"made"` at
confidence 0.58 (preserved, unchanged, still visible under "Automatic
analysis details") — the chart now correctly shows its **verified** result
instead, exactly the regression case the task named.

## F. Unknown legend removed in verified demo

**YES.** Read directly from the live page
(`page.inner_text(".legend-row")`): every Mechanics chart's legend now
reads exactly `Made` / `Missed` — no "Unknown" entry. This isn't a
demo-mode special case hiding the legend item; it's a direct consequence
of the legend being generated from the outcome categories actually present
in `outcomes = shots.map(displayOutcome)`, which — for this session, where
every one of the 11 shots has a resolved `verified_outcome` — never
contains `"unknown"` in the first place.

## G. Normal-mode Unknown behavior preserved

**YES.** For a session with no `verified_outcome` anywhere,
`displayOutcome(s)` falls through to `s.outcome` unchanged (same behavior
as before this pass), so a real automatically-UNKNOWN shot still colors
gray and the legend's `present.has("unknown")` check still adds the
"Unknown" swatch. Confirmed at the source level
(`test_mechanics_legend_is_generated_from_displayed_categories`) — the
gating logic is symmetric, it doesn't special-case demo mode, it reacts to
whatever's actually in the data. No backend file was touched, so a normal
upload's `shots[].outcome` values are generated exactly as before.

## H. Missing metric behavior preserved

**YES, verified two ways.** `renderMechanics()`'s value extraction —
`const values = shots.map((s) => m.path(s));` — is untouched by this pass
(confirmed at the source level: the exact line still reads directly from
each shot's real metric, no fallback or default). Live-DOM confirmation:
the Elbow-angle chart renders exactly **7** bars (for shots 1, 3, 4, 6, 7,
8, 10 — shots 2, 5, 9, 11 genuinely have no elbow-angle measurement and
still show no bar), not 11 padded/fabricated bars.

## I. Tests

Added to `tests/test_frontend_regressions.py` (source-level, same
JS-runner-free pattern as the rest of that file — real end-to-end behavior
is covered by the `scripts/browser_qa.py` run in section K):

- **A** — `test_display_outcome_prioritizes_verified_over_automatic`:
  asserts `displayOutcome`'s exact body, proving `verified_outcome` always
  wins via `||` short-circuit whenever present.
- **B** — same test doubles as the Shot 9 proof (`verified_outcome`
  truthy → returned regardless of `s.outcome`); reinforced by
  `test_mechanics_chart_coloring_uses_display_outcome_not_raw_outcome`
  confirming the call site itself, and by the live DOM check in section E.
- **C** — `test_mechanics_legend_is_generated_from_displayed_categories`:
  confirms each legend item is gated on `present.has(...)`, not
  unconditional; cross-referenced with the pre-existing
  `test_a_demo_session_can_contain_verified_outcomes` (every shot's
  `verified_outcome` is always `"made"`/`"missed"`, never `"unknown"`),
  proving the verified demo's `present` set can never contain `"unknown"`.
- **D** — same test's `present.has("unknown")` branch proves the Unknown
  case is reachable, not removed, for a session where it's actually
  present.
- **E** — `test_chart_coloring_fix_never_assigns_automatic_or_verified_outcome`:
  scans `displayOutcome`, `renderMechanics`, and `outcomeLegendRow` for any
  write to `.verified_outcome`/`.automatic_outcome`/`.outcome` — none
  found; all three only ever read.
- **F** — `test_missing_mechanics_values_are_not_fabricated`: pins the
  exact unmodified value-extraction line.
- **G** — `test_all_outcome_colored_shot_visualizations_share_one_helper`:
  counts `displayOutcome(s)` call sites (chips ×2 + Mechanics coloring),
  asserts at least 3, guarding against a future divergent reimplementation.

**7 new tests total** (6 new + reuse of 1 pre-existing). Full suite:
**259 passed** (253 before this pass, exactly +6 new test functions).

## J. Dist regenerated

**YES.** `scripts/export_demo.py` re-run after the fix; `app.js` grew from
65,731 to 66,780 bytes (the fix + new helper + tests's target code);
`253`→`259`-test suite re-confirmed passing before regeneration.

## K. Browser visual QA

Driven against the real regenerated `dist/` (Range-capable local server,
not `python -m http.server`), reading actual DOM/SVG state, not just
screenshots:

- Legend text for every Mechanics chart: `"Made\nMissed"` — no Unknown.
- Chart subtitle: `"Per shot, colored by verified outcome."` on every
  Mechanics card.
- Knee-angle-at-release chart (10 bars, shot 7 missing this metric):
  colors read directly from each `<rect fill="...">` = green, green,
  green, green, **red**, green, **red**, **red**, green, green for shots
  1,2,3,4,5,6,8,9,10,11 — exact match to the frozen verified sequence
  (8, 8 (shot 9's position) = red = MISSED, confirmed).
- Elbow-angle-at-release chart (7 bars, shots 2/5/9/11 missing this
  metric): green ×6 with exactly one red at shot 8's position — shot 7's
  bar (present, since it has this measurement) is green = MADE, matching
  "Shot 7 = MADE → green IF the plotted metric exists."
- Zero bars anywhere used the gray `--unknown` color (`#5b6675`) —
  confirmed by reading every bar's fill color, not sampled.
- Makes vs Misses sub-tab screenshot-checked and confirmed unchanged and
  internally consistent (`MADE n=2`, `MISSED n=5` throughout its ranked
  list, table, and strip charts) — the deliberate exclusion from section C
  didn't leave it in a broken or self-contradictory state.
- Full `scripts/browser_qa.py` sweep re-run on the final `dist/`: landing,
  Coach, Shots, Replay, Details, Methodology all render; Jump-to-Shot
  **19/19** successful seeks (full torture pattern + 1→11 sweep); zero
  console errors, zero page errors; the only `network_failures` entries
  are the same benign seek-cancellation `net::ERR_ABORTED` messages
  already explained in prior passes' reports.
