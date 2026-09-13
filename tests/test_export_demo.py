"""Regression coverage for scripts/export_demo.py's ARCVISION_MODE handling.

This does NOT run the full export (build() needs a real completed session in
the local dev database, which isn't available in a generic test environment).
It targets _write_env_js/_assert_env_js_is_demo_mode directly -- the exact
code path responsible for the bug reported during static-demo browser QA,
where an exported bundle behaved like local mode (upload dropzone, History,
"Processed locally on this machine" all present) instead of demo mode.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("export_demo", ROOT / "scripts" / "export_demo.py")
export_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_demo)


def test_write_env_js_produces_demo_mode(tmp_path):
    export_demo._write_env_js(tmp_path)
    content = (tmp_path / "static" / "js" / "env.js").read_text(encoding="utf-8")
    assert 'window.ARCVISION_MODE = "demo"' in content
    assert '"local"' not in content


def test_write_env_js_creates_missing_parent_dirs(tmp_path):
    # Regression guard: writing env.js must not depend on some other
    # FRONTEND_FILES copy having already created static/js/ first.
    output_dir = tmp_path / "fresh_export"
    assert not output_dir.exists()
    export_demo._write_env_js(output_dir)
    assert (output_dir / "static" / "js" / "env.js").exists()


def test_assert_env_js_rejects_local_mode():
    with pytest.raises(export_demo.ExportError):
        export_demo._assert_env_js_is_demo_mode('window.ARCVISION_MODE = "local";\n')


def test_assert_env_js_rejects_missing_mode_line():
    with pytest.raises(export_demo.ExportError):
        export_demo._assert_env_js_is_demo_mode('window.ARCVISION_REPO_URL = "";\n')


def test_assert_env_js_accepts_demo_mode():
    export_demo._assert_env_js_is_demo_mode(
        'window.ARCVISION_MODE = "demo";\n'
        'window.ARCVISION_REPO_URL = "";\n'
    )


# ---------------------------------------------------------------------------
# ARCVISION -- FINAL DEMO MODE: verified-outcome overlay (apply_verified_outcomes).
# These build a synthetic payload matching the real shape (shot_index +
# outcome + outcome_confidence + session_summary) rather than needing the
# real DB session, per the existing pattern in this file.
# ---------------------------------------------------------------------------

def _synthetic_demo_payload():
    shots = []
    for i in range(1, 12):
        shot = {
            "shot_index": i,
            "outcome": "unknown",  # deliberately NOT matching ground truth, so
            "outcome_confidence": 0.0,  # tests can tell "automatic" and "verified" apart
            "outcome_reason": "rim_interaction_not_sufficiently_observed",
        }
        if i == 11:
            # Mirrors the real demo's Shot 11 (see docs/FINAL_PREPUBLICATION_REPORT.md
            # section H example): a clipped-flight warning plus a mechanics
            # warning -- two distinct measurement notes on one shot.
            shot["warnings"] = ["video_ended_during_flight"]
            shot["mechanics"] = {"warnings": ["shooting_arm_landmarks_low_confidence_at_release"]}
        shots.append(shot)
    unknown_warning = "10 shot(s) could not be confidently classified as made or missed."
    other_warning = "Hoop location confidence was low for this session; outcome detection may be unreliable."
    return {
        "shots": shots,
        "session_summary": {"total_shots_detected": 11, "made": 1, "missed": 0, "unknown": 10,
                              "excluded": 0, "shooting_percentage": 100.0,
                              "warnings": [unknown_warning, other_warning]},
        "warnings": [unknown_warning, other_warning],
    }


def test_a_demo_session_can_contain_verified_outcomes():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    for shot in payload["shots"]:
        assert "verified_outcome" in shot
        assert shot["verified_outcome"] in ("made", "missed")


def test_c_raw_automatic_outcome_is_preserved_not_overwritten():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    for shot in payload["shots"]:
        # The synthetic fixture set every shot's raw outcome to "unknown" --
        # confirming automatic_outcome still says "unknown" (not silently
        # replaced by the verified value) while `outcome` itself is untouched.
        assert shot["outcome"] == "unknown"
        assert shot["automatic_outcome"] == "unknown"
    summary = payload["session_summary"]
    assert summary["automatic_made"] == 1
    assert summary["automatic_missed"] == 0
    assert summary["automatic_unknown"] == 10


def test_d_normal_sessions_never_receive_verified_labels():
    """No production code path (app/) calls apply_verified_outcomes -- it is
    only ever invoked from this script's own _load_demo_session_payload,
    itself only reachable via DEMO_SESSION_ID. A normal/local session's
    payload, never passed through this function, must have no
    verified_outcome key at all."""
    normal_payload = _synthetic_demo_payload()  # never passed through apply_verified_outcomes
    for shot in normal_payload["shots"]:
        assert "verified_outcome" not in shot
        assert "automatic_outcome" not in shot
    assert "outcomes_verified" not in normal_payload

    # Direct filesystem scan of app/ (NOT `git grep` -- several of this
    # project's directories, including scripts/ and app/ itself, are
    # currently untracked, which would make a git-based search silently
    # find nothing and pass vacuously regardless of what the code actually
    # does). Confirms no production module imports or calls the demo-only
    # verified-outcome overlay.
    app_dir = export_demo.ROOT / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "apply_verified_outcomes" in text or "VERIFIED_OUTCOMES_BY_SHOT_INDEX" in text:
            offenders.append(str(path.relative_to(export_demo.ROOT)))
    assert offenders == [], f"verified-outcome demo logic referenced from production app/ code: {offenders}"


def test_e_demo_totals_are_8_made_3_missed_11_total():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    summary = payload["session_summary"]
    assert summary["made"] == 8
    assert summary["missed"] == 3
    assert summary["made"] + summary["missed"] == 11
    assert summary["unknown"] == 0


def test_f_demo_fg_percentage_is_72_7():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    assert payload["session_summary"]["shooting_percentage"] == 72.7


def test_g_all_11_mappings_align_with_frozen_ground_truth_doc():
    import re

    gt_path = export_demo.ROOT / "docs" / "FINAL_DEMO_GROUND_TRUTH.md"
    text = gt_path.read_text(encoding="utf-8")
    rows = re.findall(r"\|\s*(\d+)\s*\|[^|]*\|\s*(MADE|MISSED)\s*\|", text)
    assert len(rows) == 11, f"expected 11 ground-truth rows, found {len(rows)}"
    doc_mapping = {int(idx): outcome.lower() for idx, outcome in rows}
    assert doc_mapping == export_demo.VERIFIED_OUTCOMES_BY_SHOT_INDEX


def test_apply_verified_outcomes_rejects_mismatched_shot_set():
    payload = _synthetic_demo_payload()
    payload["shots"] = payload["shots"][:-1]  # only 10 shots, not 11
    with pytest.raises(export_demo.ExportError):
        export_demo.apply_verified_outcomes(payload)


# ---------------------------------------------------------------------------
# Overnight pass: NaN/Infinity must never reach the exported session.json --
# see docs/OVERNIGHT_PUBLICATION_READINESS.md section C/K.
# ---------------------------------------------------------------------------

def test_dump_strict_session_json_rejects_nan():
    payload = _synthetic_demo_payload()
    payload["session_summary"]["some_stat"] = float("nan")
    with pytest.raises(export_demo.ExportError):
        export_demo._dump_strict_session_json(payload)


def test_dump_strict_session_json_rejects_infinity():
    payload = _synthetic_demo_payload()
    payload["session_summary"]["some_stat"] = float("inf")
    with pytest.raises(export_demo.ExportError):
        export_demo._dump_strict_session_json(payload)


def test_dump_strict_session_json_accepts_clean_payload_and_round_trips():
    import json

    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    text = export_demo._dump_strict_session_json(payload)
    # json.loads is strict (unlike json.dumps, it has no NaN/Infinity
    # extension) -- this is the same parser behavior as the browser's
    # JSON.parse, so a successful round-trip here is the real guarantee.
    reparsed = json.loads(text)
    assert reparsed["outcomes_verified"] is True


# ---------------------------------------------------------------------------
# ARCVISION -- CLEAN UP VERIFIED DEMO OUTCOME PRESENTATION. Presentation-only:
# these prove the misleading global "N shot(s) could not be confidently
# classified" banner is suppressed for the verified demo (whose primary
# outcomes are all resolved) while remaining completely untouched for a
# normal/local session with real automatic UNKNOWN outcomes, and that the
# automatic prediction/confidence/reason are preserved (not deleted), just
# moved to a secondary, collapsed presentation in the frontend.
# ---------------------------------------------------------------------------

def test_a_verified_demo_drops_global_unknown_warning():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    assert not any("could not be confidently classified" in w for w in payload["warnings"])
    assert not any("could not be confidently classified" in w for w in payload["session_summary"]["warnings"])


def test_a_verified_demo_keeps_other_real_warnings():
    # Only the one specific, count-prefixed "unknown" message is dropped --
    # a genuine quality warning (e.g. low hoop confidence) must survive.
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    assert any("Hoop location confidence was low" in w for w in payload["warnings"])


def test_b_normal_session_summary_still_generates_the_unknown_warning():
    # Real production path (app/analytics/session_summary.py), completely
    # untouched by this pass -- a normal upload with a real automatically-
    # UNKNOWN shot must still surface the warning. This never goes through
    # export_demo.py or apply_verified_outcomes() at all.
    from app.analytics.session_summary import compute_session_summary
    from app.analytics.makes_vs_misses import MakesVsMissesReport
    from app.analytics.shot_record import ShotRecord
    from app.events.outcome_detector import ShotOutcome

    shot = ShotRecord(
        shot_index=1, start_time_sec=0.0, release_time_sec=1.0, end_time_sec=2.0,
        outcome=ShotOutcome.UNKNOWN, outcome_confidence=0.0, outcome_reason="test",
        release_confidence=0.5, pose_quality=0.5, ball_track_quality=0.5, hoop_confidence=0.5,
        shooting_side="left", mechanics=None, trajectory=None, warnings=[],
        excluded_from_analysis=False, exclusion_reason=None, outcome_evidence={},
    )
    mvm = MakesVsMissesReport(eligible=False, reason="insufficient sample", made_count=0, missed_count=0,
                                unknown_count=1, comparisons=[])
    summary = compute_session_summary([shot], [], mvm)
    assert any("could not be confidently classified" in w for w in summary.warnings)


def test_c_verified_outcome_is_the_only_field_in_the_primary_outcome_row():
    # Frontend regression: the verified branch of renderShotDetail()'s
    # primary "Outcome" row must not reference automatic_outcome/
    # outcome_confidence -- the featured demo's shot detail never renders
    # the automatic classifier's call at all (see the ARCVISION -- FEATURED
    # DEMO AUTOMATIC DIAGNOSTICS CLEANUP tests below).
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("const outcomeRows = verified")
    end = app_js.index(";", app_js.index(": [", start))
    outcome_rows_block = app_js[start:end]
    assert "VERIFIED" in outcome_rows_block
    assert "automatic_outcome" not in outcome_rows_block
    assert "outcome_confidence" not in outcome_rows_block


def test_f_quality_panel_still_rendered_unconditionally():
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function renderShotDetail")
    end = app_js.index("const MECHANICS_METRICS")
    body = app_js[start:end]
    # renderQualityPanel must be called once, unconditionally (not inside
    # an `if (!verified)` branch) -- tracking/pose quality warnings are
    # real automatic-mechanics information and must stay visible for
    # every shot, verified or not.
    assert body.count("renderQualityPanel(shot") == 1
    assert "if (!verified)" not in body
    assert "${qualityPanel}" in body


def test_g_no_backend_or_cv_module_references_the_warning_filter():
    # Same isolation guarantee as test_d_normal_sessions_never_receive_verified_labels
    # above, extended to the new warning-suppression logic: it must live
    # only in scripts/export_demo.py, never in app/ (production code, used
    # by every normal upload).
    app_dir = export_demo.ROOT / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "_unknown_warning_re" in text:
            offenders.append(str(path))
    assert offenders == []
    # And confirm app/analytics/session_summary.py's own warning-generation
    # line is still exactly what it was before this pass -- proving the
    # production message/logic itself was never edited, only filtered
    # after the fact in the demo export.
    session_summary_src = (export_demo.ROOT / "app" / "analytics" / "session_summary.py").read_text(encoding="utf-8")
    assert 'warnings.append(f"{unknown} shot(s) could not be confidently classified as made or missed.")' in session_summary_src


# ---------------------------------------------------------------------------
# ARCVISION -- COLLAPSE DEMO QUALITY NOTES. Presentation-only: the ordinary
# per-shot measurement-quality panel collapses by default in verified demo
# mode (frontend/static/js/app.js's renderQualityPanel(..., collapseIfOrdinary)),
# while a genuinely fatal/excluded shot stays expanded, and normal/local
# sessions are completely unaffected. No warning code, title, or explanation
# is deleted or altered anywhere -- only whether the panel starts open.
# ---------------------------------------------------------------------------

def _quality_panel_source():
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function renderQualityPanel")
    end = app_js.index("function renderShotDetail")
    return app_js[start:end]


def test_a_verified_demo_measurement_notes_collapsed_by_default():
    body = _quality_panel_source()
    # A native <details> element with no `open` attribute starts closed --
    # confirm the collapsed branch is a bare <details ...> (no `open`) and
    # is only taken when collapseIfOrdinary is true and the shot isn't a
    # fatal/excluded case.
    collapsed_branch = body[body.index("if (collapseIfOrdinary"):body.index("return `\n    <div class=\"quality-panel\">")]
    assert '<details class="coach-evidence quality-panel-collapsed">' in collapsed_branch
    assert "<details class=\"coach-evidence quality-panel-collapsed\" open" not in collapsed_branch
    assert "!exclusionInfo" in body  # fatal/excluded shots never take the collapsed branch


def test_b_measurement_notes_count_is_correct():
    body = _quality_panel_source()
    assert "Measurement notes (${items.length})" in body


def test_c_expanding_shows_all_original_notes():
    # The collapsed <details> wraps the exact same _qualityPanelBody(items,
    # rawCodes) call used for the always-expanded (normal-mode) case -- so
    # every item that would show in normal mode is present, just inside
    # the closed disclosure rather than deleted or truncated.
    body = _quality_panel_source()
    collapsed_branch = body[body.index("if (collapseIfOrdinary"):body.index("return `\n    <div class=\"quality-panel\">")]
    assert "_qualityPanelBody(items, rawCodes)" in collapsed_branch


def test_d_shot_11_still_contains_both_original_notes():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    shot11 = next(s for s in payload["shots"] if s["shot_index"] == 11)
    assert shot11["warnings"] == ["video_ended_during_flight"]
    assert shot11["mechanics"]["warnings"] == ["shooting_arm_landmarks_low_confidence_at_release"]

    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert '"Clip ended mid-shot"' in app_js  # video_ended_during_flight's friendly title
    assert "Limited pose confidence at release" in app_js  # the other note's friendly title


def test_e_technical_details_disclosure_remains_accessible():
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("function _qualityPanelBody")
    body = app_js[start:start + 400]
    assert '<details class="coach-evidence quality-panel-tech">' in body
    assert "<summary>Technical details</summary>" in body


def test_g_normal_mode_quality_panel_unchanged():
    # renderShotDetail's non-verified branch must call renderQualityPanel
    # with collapseIfOrdinary=false (the 4th argument), and must not
    # reorder it relative to the metric table -- i.e. normal/local
    # sessions get byte-for-byte the same call as before this pass.
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    call_start = app_js.index("renderQualityPanel(shot, m.warnings")
    call_line = app_js[call_start:app_js.index("\n", call_start)]
    assert "!!verified)" in call_line  # collapseIfOrdinary is exactly the verified flag, false for normal sessions
    non_verified_branch = app_js[app_js.index(": `\n    <h3>Shot"):app_js.index("const MECHANICS_METRICS")]
    assert "${qualityPanel}" in non_verified_branch
    assert "${metricTable}" in non_verified_branch
    # quality panel still precedes the metric table for normal sessions
    assert non_verified_branch.index("${qualityPanel}") < non_verified_branch.index("${metricTable}")


# ---------------------------------------------------------------------------
# ARCVISION -- FEATURED DEMO AUTOMATIC DIAGNOSTICS CLEANUP. The verified
# demo's shot detail used to hide the automatic classifier's prediction/
# confidence/reason/evidence inside a collapsed "Automatic analysis details"
# <details> disclosure (renderAutomaticAnalysisDetails()) -- useful for
# engineering, but confusing in a public portfolio demo (e.g. a VERIFIED
# MADE shot with an expandable "MISSED" underneath it). This pass removes
# that disclosure (and the now-unused function) from the featured session's
# UI entirely -- presentation-only: automatic_outcome/outcome_confidence/
# outcome_reason/outcome_evidence remain fully preserved in the exported
# session.json (see test_c_raw_automatic_outcome_is_preserved_not_overwritten
# above, unaffected by this pass), and local/non-verified sessions keep
# showing their automatic evidence exactly as before via `evidenceSection`.
# ---------------------------------------------------------------------------

def test_h_automatic_analysis_details_removed_from_app_js():
    # The disclosure, its <summary> label, and the function that built it
    # must all be gone -- not just unreferenced.
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "renderAutomaticAnalysisDetails" not in app_js
    assert "Automatic analysis details" not in app_js


def test_i_verified_branch_never_renders_automatic_prediction_fields():
    # The featured/verified template (renderShotDetail's `verified ? ...`
    # branch) must not reference automatic_outcome, outcome_confidence, or
    # outcome_reason anywhere -- not just absent from the old disclosure.
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    verified_branch = app_js[app_js.index("? `\n    <h3>Shot"):app_js.index(": `\n    <h3>Shot")]
    assert "automatic_outcome" not in verified_branch
    assert "outcome_confidence" not in verified_branch
    assert "outcome_reason" not in verified_branch
    assert "evidenceSection" not in verified_branch


def test_j_quality_panel_details_element_unaffected_by_the_removal():
    # The measurement-quality panel is a separate, independent <details>
    # element (renderQualityPanel) that must keep working exactly as before
    # -- this pass only removes the automatic-analysis disclosure, nothing
    # else in the shot-detail card.
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "quality-panel-collapsed" in app_js
    assert "function renderQualityPanel" in app_js


def test_k_local_upload_branch_still_shows_automatic_evidence():
    # Normal/local sessions (verified always undefined) are unaffected by
    # this pass -- their branch still builds the primary Outcome row from
    # the automatic outcome/confidence/reason, and still inlines
    # `evidenceSection` (the raw outcome-evidence table), exactly as before.
    app_js = (export_demo.ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    non_verified_branch = app_js[app_js.index(": `\n    <h3>Shot"):app_js.index("const MECHANICS_METRICS")]
    assert "shot.outcome.toUpperCase()" in app_js  # non-verified Outcome row source
    assert "${evidenceSection}" in non_verified_branch


def test_h_no_warning_data_removed_from_exported_json():
    payload = export_demo.apply_verified_outcomes(_synthetic_demo_payload())
    shot11 = next(s for s in payload["shots"] if s["shot_index"] == 11)
    # Per-shot warning data (the actual codes powering every note) is
    # completely untouched by apply_verified_outcomes() -- only the
    # session-level "N shot(s) could not be confidently classified..."
    # string is filtered (see test_a_verified_demo_drops_global_unknown_warning).
    assert shot11["warnings"] == ["video_ended_during_flight"]
    assert shot11["mechanics"]["warnings"] == ["shooting_arm_landmarks_low_confidence_at_release"]
    import json
    text = export_demo._dump_strict_session_json(payload)
    reparsed = json.loads(text)
    shot11_reparsed = next(s for s in reparsed["shots"] if s["shot_index"] == 11)
    assert shot11_reparsed["warnings"] == ["video_ended_during_flight"]
