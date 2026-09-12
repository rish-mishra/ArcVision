"""
Static-source regression checks for frontend/static/js/app.js.

There's no JS test runner in this project (the frontend is intentionally
build-tool-free -- see README "Why these specific models/libraries"), so
real end-to-end frontend behavior is verified by scripts/browser_qa.py
(a real headless-Chromium driver) rather than here. This file exists only
to pin a couple of specific past regressions at the source-text level so a
future edit can't silently reintroduce them without at least one test
failing, cheaply, without a browser.
"""
from pathlib import Path

APP_JS = (Path(__file__).resolve().parent.parent / "frontend" / "static" / "js" / "app.js").read_text(
    encoding="utf-8"
)


def _function_body(name: str) -> str:
    start = APP_JS.index(f"function {name}(")
    depth = 0
    i = APP_JS.index("{", start)
    body_start = i
    while True:
        if APP_JS[i] == "{":
            depth += 1
        elif APP_JS[i] == "}":
            depth -= 1
            if depth == 0:
                return APP_JS[body_start : i + 1]
        i += 1


def test_init_tabs_does_not_globally_deactivate_every_tab_panel():
    # Regression: initTabs() used to run
    # document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"))
    # on every click, which also matches the unrelated standalone
    # #tab-methodology-standalone panel (it shares the .tab-panel class only
    # for its own show/hide styling, not because it's one of the Coach/
    # Shots/Replay/Details tabs). Its "active" class is only ever set once,
    # in the static HTML, so the first dashboard tab click silently and
    # permanently blanked the Methodology page for the rest of the session.
    # See docs/OVERNIGHT_PUBLICATION_READINESS.md section C.
    body = _function_body("initTabs")
    assert 'document.querySelectorAll(".tab-panel")' not in body, (
        "initTabs() must not query .tab-panel globally -- it must only "
        "deactivate the panels it owns (see ownedPanels), or it will "
        "break the unrelated standalone Methodology panel again."
    )
    assert "ownedPanels" in body


# ---------------------------------------------------------------------------
# ARCVISION -- REMOVE UNKNOWN FROM VERIFIED DEMO CHARTS.
#
# Root cause (confirmed by reading the code, not guessed): renderMechanics()
# built its per-shot bar-chart colors from the raw automatic `s.outcome`
# field, and renderShots()/renderReplay() already had the correct pattern
# via a small central helper, displayOutcome(s) = s.verified_outcome ||
# s.outcome. The Mechanics charts just weren't calling it. The legend was a
# second, independent bug: three hardcoded Made/Missed/Unknown swatches
# rendered unconditionally regardless of what outcomes were actually being
# plotted.
#
# Scope note: app/analytics/makes_vs_misses.py's comparisons (effect size,
# p-value, made/missed means -- surfaced in the Makes vs Misses sub-tab's
# ranked list, table, and per-metric strip charts) are a backend-computed
# statistic over the automatic outcome grouping. Re-grouping just the
# strip-chart dots by verified_outcome without recomputing that statistic
# would make the chart visually disagree with its own effect-size/p-value
# caption sitting right next to it -- a new, worse inconsistency, and
# functionally an uncomputed/estimated comparison, which is explicitly out
# of scope ("do not estimate anything, do not create new predictions").
# Left untouched, deliberately, matching the established "mechanics/
# coaching remain automatic" boundary from earlier passes.
# ---------------------------------------------------------------------------

def test_display_outcome_prioritizes_verified_over_automatic():
    # This is the exact Shot 9 case: verified_outcome="missed",
    # automatic outcome/s.outcome="made". `||` short-circuits on the first
    # truthy value, so a present (non-empty-string) verified_outcome always
    # wins regardless of what s.outcome says.
    body = _function_body("displayOutcome")
    assert body.strip() == "{ return s.verified_outcome || s.outcome; }"


def test_mechanics_chart_coloring_uses_display_outcome_not_raw_outcome():
    body = _function_body("renderMechanics")
    assert "displayOutcome(s)" in body
    # Regression guard: renderMechanics used to build its per-shot color
    # array as `shots.map((s) => s.outcome)` -- the exact raw-automatic-
    # outcome leak this pass fixes. Confirm that specific pattern is gone.
    assert "shots.map((s) => s.outcome)" not in body


def test_mechanics_legend_is_generated_from_displayed_categories():
    body = _function_body("outcomeLegendRow")
    # Each category is conditional on actually being present in what's
    # displayed -- not a fixed three-item list -- so a verified demo whose
    # 11 shots are all made/missed simply never has "unknown" in `present`,
    # and normal sessions with a real automatic UNKNOWN still get it.
    assert 'present.has("made")' in body
    assert 'present.has("missed")' in body
    assert 'present.has("unknown")' in body
    render_body = _function_body("renderMechanics")
    assert "outcomeLegendRow(outcomes)" in render_body
    # Regression guard against the old hardcoded three-swatch block.
    assert '>Unknown</div>' not in render_body


def test_missing_mechanics_values_are_not_fabricated():
    # The per-shot values array must still come straight from the real
    # metric accessor with no fallback/default -- a missing measurement
    # stays missing (perShotBarChart already skips null/undefined points),
    # it is never filled in just so every shot has a bar.
    body = _function_body("renderMechanics")
    assert "shots.map((s) => m.path(s))" in body


def test_chart_coloring_fix_never_assigns_automatic_or_verified_outcome():
    # displayOutcome() and its Mechanics-chart call site only ever READ
    # verified_outcome/automatic_outcome/outcome -- this pass must not
    # introduce any write to those fields anywhere in app.js (that would
    # mean mutating real analysis data to make a chart look a certain way,
    # exactly what "do not estimate/invent" rules out).
    for body in (_function_body("displayOutcome"), _function_body("renderMechanics"), _function_body("outcomeLegendRow")):
        assert ".verified_outcome =" not in body
        assert ".automatic_outcome =" not in body
        assert ".outcome =" not in body


def test_all_outcome_colored_shot_visualizations_share_one_helper():
    # Shots-tab chips, Replay chips, and Mechanics bar-chart coloring must
    # all resolve the same way -- through displayOutcome(s) -- rather than
    # three independent (and divergence-prone) implementations.
    call_sites = APP_JS.count("displayOutcome(s)")
    assert call_sites >= 3, (
        f"expected displayOutcome(s) used by chips (x2: Shots + Replay) and "
        f"Mechanics chart coloring, found only {call_sites} call site(s)"
    )


# ---------------------------------------------------------------------------
# ARCVISION -- FINAL CHART CLARITY PASS. A shot genuinely missing from a
# per-shot Mechanics chart (no reliable measurement -- never fabricated,
# interpolated, or replaced) can read as a rendering bug without context.
# omittedShotsNote() adds a small, conditional footnote only when a metric's
# real values actually omit one or more shots.
# ---------------------------------------------------------------------------

def test_a_note_shown_when_a_metric_omits_a_shot():
    body = _function_body("omittedShotsNote")
    assert 'values.some((v) => v === null || v === undefined)' in body
    assert "Some shots are omitted when a reliable measurement wasn't available." in body
    # The note is returned precisely when `omitted` is true -- not
    # unconditionally appended after the chart.
    assert "if (!omitted) return" in body


def test_b_no_note_when_a_metric_has_every_shots_value():
    # Same function, opposite branch: omittedShotsNote must have an early
    # return producing no note at all when nothing is missing, not just a
    # visually-empty note.
    body = _function_body("omittedShotsNote")
    assert 'if (!omitted) return "";' in body


def test_c_missing_values_still_come_straight_from_the_metric_accessor():
    # The values passed into omittedShotsNote are the exact same
    # metricValues array used to draw the chart -- computed once, before
    # either consumer runs, never re-derived or defaulted for the note.
    render_body = _function_body("renderMechanics")
    assert "const metricValues = MECHANICS_METRICS.map((m) => shots.map((s) => m.path(s)));" in render_body
    assert "omittedShotsNote(metricValues[i])" in render_body
    assert "values: metricValues[i]" in render_body


def test_d_omitted_shots_note_never_writes_to_the_values_it_inspects():
    # Purely a read (Array.prototype.some) -- must never assign into
    # `values` (which would mean fabricating/interpolating a point) or
    # mutate it in any way.
    body = _function_body("omittedShotsNote")
    assert "values[" not in body
    assert ".push(" not in body
    assert ".fill(" not in body


def test_e_verified_outcome_coloring_still_untouched_by_this_pass():
    # Regression guard shared with the previous pass: this pass must not
    # reintroduce raw `s.outcome` chart coloring while touching the same
    # function to add the note.
    body = _function_body("renderMechanics")
    assert "displayOutcome(s)" in body
    assert "shots.map((s) => s.outcome)" not in body


def test_f_omitted_shots_note_has_no_mode_check_normal_sessions_get_it_too():
    # The note is purely a function of whether THIS metric's real values
    # contain a gap -- no ARCVISION_MODE/verified_outcome branch gates it,
    # so a normal/local session with a genuinely missing measurement gets
    # the exact same footnote, and one with complete data gets none,
    # exactly like the verified demo.
    body = _function_body("omittedShotsNote")
    assert "ARCVISION_MODE" not in body
    assert "verified_outcome" not in body


# ---------------------------------------------------------------------------
# ARCVISION -- FEATURED DEMO SHOOTING-SIDE CLEANUP.
#
# The shooting-side heuristic (app/biomechanics/shooting_side.py) cannot
# reliably determine the shooting hand on the featured demo's side/profile
# camera angle -- all 11 real shots are right-handed but the heuristic
# alternates. That is a genuine data-quality limitation, not a bug, and is
# out of scope to fix further. Instead the "Shooting side" row is hidden
# from display for the featured demo ONLY, reusing shot.verified_outcome --
# the same pre-existing flag `outcomeRows` already branches on two lines
# above, present only on the one frozen/verified demo session and never on
# a normal local upload -- rather than inventing a new session-ID check.
# ---------------------------------------------------------------------------

def test_shooting_side_row_hidden_only_for_verified_demo_shots():
    body = _function_body("renderShotDetail")
    assert '...(verified ? [] : [["Shooting side", shot.shooting_side || "undetermined"]])' in body


def test_shooting_side_removal_reuses_existing_verified_flag_not_a_new_check():
    # No session-ID hack: the gate must be the same `verified` local
    # (shot.verified_outcome) already used for the Outcome row, not a new
    # DEMO_SESSION_ID / ARCVISION_MODE / session_id comparison.
    body = _function_body("renderShotDetail")
    assert "const verified = shot.verified_outcome;" in body
    assert "session_id" not in body
    assert "DEMO_SESSION_ID" not in body


def test_shooting_side_row_removes_cleanly_no_blank_row_left_behind():
    # The row is excluded via an empty-array spread branch, not blanked out
    # with an empty label/value pair -- so no gap/blank row can ever render.
    body = _function_body("renderShotDetail")
    assert '["Shooting side", ""]' not in body
    assert '["", ""]' not in body


def test_shooting_side_removal_never_writes_the_underlying_field():
    # Presentation-only: this change must only ever READ shot.shooting_side,
    # never assign to it -- the stored data (and the demo's frozen ground
    # truth) stays untouched.
    body = _function_body("renderShotDetail")
    assert ".shooting_side =" not in body
