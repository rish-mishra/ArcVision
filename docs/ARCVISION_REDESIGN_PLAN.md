# ArcVision Redesign Plan (proposal — not implemented)

Rebrand of "FormAI Basketball" → **ArcVision**, plus a product/UX/coaching redesign of the
existing dashboard. This document is a plan for approval, grounded in a full read of the
current frontend (`frontend/`) and the entire analytics/biomechanics layer
(`app/biomechanics/metrics.py`, `app/analytics/*.py`). Nothing has been implemented.

**Hard constraint respected throughout:** every idea below is presentation, information
architecture, or synthesis of *already-computed* numbers. Nothing here proposes a new
measurement, a new threshold, an absolute "ideal" biomechanical value, or any change to
`app/vision/`, `app/tracking/`, `app/events/`, `app/biomechanics/metrics.py`'s actual
computation, or RF-DETR/weights. The one backend addition proposed (a coaching-synthesis
module) only reads existing dataclasses that `app/pipeline/orchestrator.py` already computes.

---

## 1. Visual identity

### Name and rationale
**ArcVision** — "arc" is the shot's own trajectory (already a first-class concept in the data:
`apex_height_norm`, `trajectory.straightness_ratio`), "vision" is computer vision. Reads as a
real product name, not generic "AI-something."

### Color palette
Current palette is a competent but generic warm-grey/blue SaaS look. Proposed direction: move
the neutral base toward a **deep ink-navy** (reads more "premium sports broadcast" than warm
grey) and introduce one confident, sports-native accent instead of the current plain blue.

| Token | Light mode | Dark mode | Use |
|---|---|---|---|
| `--brand` (primary accent) | `#E85D2A` (ember orange) | `#FF7A45` | CTAs, brand mark, primary highlights, "hero" numbers |
| `--accent-2` (secondary) | `#0F9E9E` (teal) | `#2DD4D4` | Links, secondary chart series, "insight/vision" callouts — keeps orange from being overused |
| `--surface-0/1/2` | warm-white → white (kept close to current) | deep ink-navy `#0A0E16` → `#141A24` (darker/more saturated than the current near-black grey) | page/card backgrounds |
| `--good` / `--critical` / `--unknown` | tuned green/coral/grey, re-picked to sit comfortably next to the new orange rather than clash with it | same, lightened for dark bg | made/missed/unknown, unchanged semantics |

This keeps the existing CSS-custom-property architecture (already theme-aware, already has a
working `prefers-color-scheme` + `data-theme` override system) — it's a token-value swap, not
a new theming mechanism. **Both light and dark stay fully supported**, exactly as today; dark
becomes the suggested "hero" mode for screenshots since a navy base reads more like a
broadcast/coaching-tech product, but light remains equally functional.

### Typography
Keep `system-ui` as the body font (zero dependency, matches "runs 100% locally," already
correct for a no-build-step project). Two options for headings/the wordmark, for you to pick:
- **A (zero-dependency, safe default):** system-ui throughout, differentiated only by weight/
  tracking — no risk, no new dependency.
- **B (optional upgrade):** one Google Font for headings only (e.g. Space Grotesk or Outfit —
  geometric, sporty, good numeral shapes), loaded via a single `<link>`, with the system-ui
  stack as an automatic fallback if offline. Purely progressive enhancement; nothing breaks
  without it.

Give the "hero" shooting-% number more visual weight than today (larger, bolder, tabular-nums
already used elsewhere) — sports products lead with one big scoreboard number.

### Cards, buttons, tabs, spacing
- Formalize the current ad-hoc pixel spacing into an 8pt scale (`--space-1: 4px` …
  `--space-6: 48px`) for consistency — same visual sizes as today, just systematized.
- Primary button (`--brand` orange) gets a subtle hover-lift/shadow; secondary/outline style
  unchanged in spirit.
- Replace the current 8 equal-weight flat tabs with a smaller, clearer primary nav (see §2) —
  fewer, better-labeled destinations reads as more "designed," not more decorated.
- Reuse (don't replace) what already works well: the SVG chart tooltips, the
  `.confidence-badge` component, the warning-banner pattern, the responsive fixes from Day 3.

### Landing / processing screens
- **Landing:** keep the existing dropzone mechanics (drag/drop, client-side validation, error
  states — all working, don't touch) but restyle: accent-colored dashed border, a very
  low-opacity background motif of a single arc line (pure CSS/SVG, echoes the logo, no image
  asset).
- **Processing:** keep the existing stage checklist (it's genuinely good — clear, honest,
  already fixed in Day 1) but replace the plain spinner with a small looping SVG animation of a
  ball tracing an arc into a hoop — same "keep this tab open" honesty, more "alive" feel. Pure
  CSS animation, no new libraries.

### Logo concept
**A single arc line passing through a ring.** The ring reads simultaneously as a **hoop** and a
**camera/vision aperture**; the arc reads simultaneously as a **shot's trajectory** and a
**data/tracking path**. A small solid dot at the arc's start doubles as "the ball" and as a
release-point marker, so the mark reads clearly even at favicon size.

```
   ·⌢       <- small dot (ball / release point), start of the arc
  ╱   ╲
 │     │    <- ring (hoop / lens aperture), stroke-only
  ╲   ╱
   ╲ ╱
    ↓ arc sweeps down through the ring
```

Implementation: one inline `<svg viewBox="0 0 32 32">` with a `<circle>` (ring, `--brand`
stroke) and one curved `<path>` (arc, `--accent-2` stroke), both using `currentColor`/CSS vars
so it re-themes automatically — the same technique the current `.brand-mark` div already uses,
just replacing the letter "F" with a real mark. Wordmark: "Arc" in `--brand` weight next to
"Vision" in the primary ink color (two-tone), with a same-color fallback if that reads as too
busy. No literal robot/circuit/brain imagery anywhere — deliberately avoided per your ask.

---

## 2. Simplified UX / information architecture

### The problem with the current structure
8 flat, equal-weight tabs (Overview, Shots, Mechanics, Makes vs Misses, Consistency, Trends,
Replay, Methodology). A first-time player has to already understand what "coefficient of
variation" and "effect size" mean before the dashboard tells them anything useful. Overview
today is close to a real "Coach" view but is diluted by being one tab among eight equals.

### Proposed structure: 4 primary destinations

| Tab | Answers | Contains (mostly relocated, not new) |
|---|---|---|
| **Coach** (new default landing tab) | "How did I shoot? What am I doing well? What's my #1 priority? What should I do next? How did makes differ from misses?" | Hero stat block (shooting %, made/missed/unknown, honest caption — from current Overview) + new coaching cards (§3) which absorb the useful parts of today's Makes-vs-Misses/Consistency/Trends findings |
| **Shots** | "Where can I inspect individual shots?" | Unchanged — already good (shot chips, full metric table, confidence badges from Day 2, raw outcome evidence) |
| **Replay** | "Show me the video" | Unchanged — annotated/diagnostic toggle, jump-to-shot |
| **Details** | "I want the raw numbers/charts" | Sub-tabs: Mechanics charts, full Makes-vs-Misses comparison table + strip plots, full Consistency ranking, full Trends — i.e. today's Mechanics/Mvm/Consistency/Trends tabs, kept intact but demoted one level, plus a "How this works" link to the Methodology doc instead of a full top-level tab |

This is a **relocation**, not a deletion — every chart, table, and number that exists today
still exists; nothing is removed. "Advanced diagnostic/evidence information stays accessible,"
exactly as asked — it's one click into Details instead of tied for top billing with "how did I
shoot."

---

## 3. Coaching-feedback design

### Design principle (already partially embodied in the existing code, made explicit here)
Every metric in `app/analytics/metric_extractors.py`'s `METRICS` registry carries a
`lower_is_better: Optional[bool] = None` field, and **every single entry currently leaves it
unset** — the codebase already refuses to claim a universal "good" direction for any metric.
The coaching layer must preserve this exactly: nothing is ever "wrong" in an absolute sense,
only "different between your makes and misses" or "more/less consistent than your other
metrics" — always self-referential to *this player's own* session.

### The four coaching artifacts, and exactly what existing data drives them

**a) Strongest part of your form.** Source: `app/analytics/consistency.py`'s
`most_consistent_metrics()` — the metric with the lowest coefficient of variation among those
with ≥4 samples (already-gated, already computed). Phrasing: *"Your {metric} was the most
repeatable part of your shot tonight (CV = {value} across {n} shots)."* No claim about whether
the value itself is good — only that it was the most *consistent*.

**b) #1 improvement priority.** Priority order, using only existing eligibility flags:
1. If `makes_vs_misses.py`'s report is `eligible` and `top_differentiators()` returns a result
   with `effect_label` ≥ "medium": use the single largest `|effect_size|` differentiator.
   *"Your {metric} differed the most between makes ({made_mean}) and misses ({missed_mean})
   this session."*
2. Else, if consistency data exists: fall back to `least_consistent_metrics()` — the highest-CV
   metric. *"Your {metric} varied the most shot-to-shot this session."*
3. Else: the existing `not_enough_total_shots` / `not_enough_made_or_missed_shots` reason
   strings, reworded in coach-voice instead of engineering-voice, but same underlying gate.

**c) 1-3 actionable coaching cues.** Take the top 1-3 items from whichever source drove (b),
run each through a small, new, **presentation-only** translation table (metric key → neutral
description of what it measures, e.g. `elbow_angle_at_release_deg` → "how fully your shooting
elbow extends at release") and template the cue as a *separate, clearly-labeled sentence* from
the evidence:
- **Evidence line** (factual, always shown): *"Made: 162° (n=8) · Missed: 148° (n=9) · effect
  size 0.91 (large)."* — directly reusing `ComparisonResult`'s existing fields.
- **Coaching line** (interpretive, visually distinct — different font weight/color, maybe a
  "Try this" label): *"Try matching the elbow extension you show on your makes."* — built from
  the observed direction of *this player's own* made-vs-missed difference, never a fixed
  target number.

For a consistency-driven cue (no makes-vs-misses data yet): *"Working on repeating your
set-up before each shot may help tighten up your {metric}."* — again no target value, just
naming the variability itself.

**d) Makes vs. misses comparison.** The full existing `makes_vs_misses.py` report/table/strip
plots move to Details; the single top differentiator surfaces in Coach as evidence for (b)/(c).

**e) Consistency feedback.** Same pattern — full ranking in Details, top/bottom result
surfaced in Coach for (a)/(b).

**f) Uncertainty language,** using only already-computed confidence signals:
- **Session-level banner:** if `session_summary.mean_pose_quality`, `mean_ball_track_quality`,
  or `hoop_confidence` bucket to "low" via the *already-existing* `Confidence.from_score`
  (0.75/0.5 thresholds, `app/vision/types.py`), show a caveat banner atop Coach: *"Tracking
  quality was lower than usual this session — treat these findings as a rough read."*
- **Per-finding confidence badge:** reuse `feedback.py`'s existing `_confidence_from_effect`
  logic (large effect + n≥5 → high; large/medium + n≥3 → medium; else low) directly.
- **Per-shot confidence:** `ShotRecord.overall_confidence_level` is already computed
  (`min(release_confidence, pose_quality, ball_track_quality)` bucketed via `Confidence.
  from_score`) but **is not currently serialized to the frontend** — the one small, additive
  backend change proposed below exposes it.
- **"Not enough data yet" states:** reuse the existing `eligible`/`reason` fields verbatim
  (already good, human-readable) rather than inventing new copy from scratch.

### What this explicitly does NOT do
No absolute biomechanical targets ("elbow should be 90°"), no generic tips disconnected from
this session's own numbers, no claim that a metric is "wrong" absent a measured, sufficiently-
sampled difference. This mirrors `feedback.py`'s own stated design principle ("nothing here is
a template filled with a generic tip") — the redesign extends that principle, it doesn't
compromise it.

### Metric → feedback-type mapping (summary table)

| Feedback type | Existing source (unmodified) | Existing gate |
|---|---|---|
| Strongest part of form | `consistency.most_consistent_metrics()` | n ≥ 4 |
| #1 priority | `makes_vs_misses.top_differentiators()` → fallback `consistency.least_consistent_metrics()` | n≥4 total, ≥2 makes/≥2 misses; else consistency n≥4 |
| Actionable cues (1-3) | same two sources, top 1-3, + new translation dict (presentation only) | same |
| Evidence per cue | `ComparisonResult` (made/missed mean, std, n, effect size, p-value) | n/a — already computed |
| Makes vs misses detail | `makes_vs_misses.py` full report + `metric_extractors.extract_values` (already used by `charts.js`) | same |
| Consistency detail | `consistency.py` full report | n ≥ 4 |
| Trend callout | `trends.py`, exactly the existing `generate_trend_findings` gate (±10% shooting-pct change, or metric change with early/late n≥3) | n ≥ 6 shots |
| Session uncertainty banner | `session_summary.py` mean pose/ball/hoop confidence, bucketed via existing `Confidence.from_score` | existing 0.75/0.5 |
| Per-shot confidence badge | `ShotRecord.overall_confidence_level` (computed, **not yet serialized**) | existing |
| "Not enough data" copy | existing `eligible`/`reason` fields | existing |

---

## 4. Files/components that would change

**Backend (additive/presentation only — no detection/tracking/FSM/outcome/biomechanics/
threshold edits):**
- New `app/analytics/coaching.py` (+ `tests/test_coaching.py`) — synthesizes (a)-(c) above
  purely from `ConsistencyResult`/`MakesVsMissesReport`/`TrendReport`, which
  `app/pipeline/orchestrator.py` already computes at lines ~420-423. Contains the new
  metric-description translation dictionary (pure strings, no numbers invented).
- `app/pipeline/orchestrator.py` — one additive call to `coaching.py`'s entry point alongside
  the existing `consistency`/`mvm`/`trends`/`findings` calls (~line 425), attached to the
  existing `SessionResult` dataclass as a new field.
- `app/storage/serializers.py` — add `overall_confidence_level` to `serialize_shot()`, and
  serialize the new coaching block.

**Frontend (the bulk of the work, all in the existing three files):**
- `frontend/index.html` — restructure tabs (Coach/Shots/Replay/Details), new Coach markup, new
  Details sub-tab markup, new logo/wordmark markup, "FormAI" → "ArcVision" text.
- `frontend/static/css/main.css` — palette swap, spacing scale, logo styles, coaching-card
  component, processing-state animation, tab restructure styles. Day 1-3 responsive/
  accessibility work (topbar wrap, ARIA tabs, contrast-fixed `--text-muted`, `.card` overflow
  guard) is preserved and carried forward, not redone.
- `frontend/static/js/app.js` — new `renderCoach()` (absorbs/replaces `renderOverview`), new
  `renderDetails()` housing today's `renderMechanics`/`renderMvm`/`renderConsistency`/
  `renderTrends` as sub-views, Methodology moved to a footer link/modal, "FormAI" → "ArcVision"
  strings, tab-switching logic updated for the new 4-tab + sub-tab structure.
- `frontend/static/js/charts.js` — expected to need little to no change (the chart primitives
  are already generic); optionally a small sparkline helper if we want a trend indicator on the
  hero stat (nice-to-have, see §5).

**Rename-only (mechanical, already located):** `app/config.py` (module docstring), `app/main.py`
(FastAPI title + one log line), `app/analytics/feedback.py` (one user-facing string),
`scripts/diagnose_video.py`, `scripts/diagnose_fallback_corroboration.py`,
`scripts/setup_env.ps1` (console messages), `README.md` and `docs/*.md` (title/prose — the
`docs/VIDEO4_*`/`FINAL_ARCHITECTURE_DECISION.md` historical narrative should keep its content
exactly as-is, just with the product name updated where it appears, not a rewrite).

---

## 5. Staged implementation plan

Proposed as independently reviewable stages, each shippable/revertable on its own — same
incremental pattern as the Day 1-3 polish work.

1. **Rename pass.** Mechanical find/replace across the files listed above. Run full test suite
   after (should be unaffected — no logic touched).
2. **Visual identity foundation.** New CSS tokens (palette, spacing, typography), new logo SVG,
   updated button/card/badge/tab base styles — applied to the *existing* markup structure, so
   "does it look like ArcVision" is reviewable before any restructuring.
3. **Landing/processing polish.** Hero/dropzone restyle, arc-animation processing state — Day 1's
   functional behavior (validation, error handling, duration messaging) untouched.
4. **Coaching backend.** New `coaching.py` + tests + additive serializer/orchestrator wiring.
   Fully testable in isolation via pytest before any frontend depends on it; verify via a full
   test-suite run and an explicit diff-scope check (same discipline as every prior stage this
   session) that no CV/detection/tracking/FSM/outcome/biomechanics file changed.
5. **Dashboard restructuring.** Collapse to Coach/Shots/Replay/Details, build the Coach UI
   against stage 4's data, relocate Mechanics/Mvm/Consistency/Trends into Details, move
   Methodology to a footer link.
6. **Shots/Replay refinement.** Per-shot confidence badges (stage 4's new field), optional
   coaching-cue → Replay-timestamp deep link.
7. **Final QA.** Full responsive/accessibility re-check (Day 3's standard), full test suite,
   README/docs pass reflecting the new structure, new screenshots, repeat the repo-hygiene
   audit from the last pass.

Each stage stops for your review before the next starts, exactly like Days 1-3.

---

## 6. Ideas that would make ArcVision more impressive — scoped in vs. explicitly out

**In scope for this redesign (cheap, high payoff, zero new measurement):**
- **"Coach's Note"** — one auto-generated sentence at the top of Coach stitching together the
  strength + priority strings already computed: *"Your release timing was the most consistent
  part of your form tonight, and elbow extension at release is the clearest thing to work on."*
  Pure string templating over data that already exists elsewhere on the page — but reads as far
  more "intelligent" for near-zero implementation cost.
- **Confidence badges everywhere confidence numbers already exist** (per-shot, session-level) —
  credibility payoff from data the backend already computes.
- **Coaching cue → Replay timestamp deep link** — makes the tabs feel like one connected
  product instead of siloed views; cheap since shot timestamps are already in every payload.

**Explicitly out of scope for this pass (flagging, not proposing):**
- **Cross-session trends** ("your makes-vs-misses gap has narrowed since last time") — would
  require genuinely new computation (comparing across sessions, not within one), which is a
  bigger, separate feature, not a redesign of what exists today.
- **Exportable/shareable session report** (PDF/image) — a real nice-to-have for a portfolio
  demo, but adds new functionality rather than better presenting existing measurements; worth
  a future ask, not bundled into this pass.

---

## Summary

Nothing above touches `app/vision/`, `app/tracking/`, `app/events/`,
`app/biomechanics/metrics.py`'s computation, RF-DETR, thresholds, or the frozen Video 4
evaluation. The redesign is entirely: a new coat of paint (palette/type/logo), fewer and
better-organized top-level destinations, and one new synthesis layer that reads already-
computed consistency/makes-vs-misses/trend/confidence data and states it in coach voice instead
of engineering voice — with measurement and interpretation always kept visually and textually
separate, and uncertainty always stated in terms of data the system already has, never
invented ones. Awaiting your approval before implementing any stage.
