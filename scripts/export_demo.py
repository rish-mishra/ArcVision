"""
Builds the static, $0-hostable ArcVision public demo bundle described in
docs/DEMO_DEPLOYMENT_AUDIT.md. Reads ONE already-completed, already-real
session from the local database and exports it alongside a copy of the
frontend -- this script does not run any detection/tracking/outcome/
biomechanics/coaching computation itself, it only reads and repackages
outputs that already exist on disk.

Writes to ./dist/ (gitignored -- generated output, never committed to
`main`). Safe to re-run: the output directory is fully rebuilt each time.

Explicit allowlist, not a recursive copy: this script only ever touches the
specific files named below. It never walks app/, data/datasets/,
data/training_runs/, models/, or the SQLite file itself, so there is no
code path by which a checkpoint, dataset, training run, raw video, or the
database file could end up in the export -- see the privacy scan at the
end for a second, independent verification of that.

Usage:
    .venv\\Scripts\\python scripts\\export_demo.py
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage import repository

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "dist"
FRONTEND_DIR = ROOT / "frontend"

# The one session this bundle demonstrates -- a real, already-analyzed
# session, approved for this purpose. Change here only if you deliberately
# choose a different already-completed session; this script never picks one
# automatically. Currently arcvision_demo_final.mov -- the frozen final
# showcase recording (11 shots, ground truth recorded BEFORE inference in
# docs/FINAL_DEMO_GROUND_TRUTH.md, blind-evaluated in
# docs/FINAL_DEMO_BLIND_EVALUATION.md). Superseded TWO earlier session ids
# this pointed to before: arcvision_demo_01_muted.mov's 3809b2b304064f21
# (a different, older showcase video), and then 29c7e751775e4f20 (this same
# video, but analyzed before this session's segmentation fix -- see
# docs/SHOWCASE_SEGMENTATION_FIX.md -- so it still had 13 detected windows
# including 2 false positives; export_demo.py's own shot-count safety check
# refused to export it once VERIFIED_OUTCOMES_BY_SHOT_INDEX below expected
# exactly 11). This id (ab556626332b440e, via
# scripts/create_final_demo_session.py) is a fresh run of the same source
# video under current, post-segmentation-fix production code: 11/11 shots,
# 0 false positives, 0 false negatives.
DEMO_SESSION_ID = "fee1c3bcd7b84322"

# Frozen ground truth for arcvision_demo_final.mov, copied verbatim from
# docs/FINAL_DEMO_GROUND_TRUTH.md -- recorded by the user from manual review
# of the raw video BEFORE ArcVision inference ever ran on it. This mapping
# is applied ONLY to DEMO_SESSION_ID's exported payload, in this script,
# never in app/ (the production pipeline never sees or uses it, and no
# other session -- local or otherwise -- is ever touched by it).
VERIFIED_OUTCOMES_BY_SHOT_INDEX = {
    1: "made", 2: "made", 3: "made", 4: "made", 5: "missed",
    6: "made", 7: "made", 8: "missed", 9: "missed", 10: "made", 11: "made",
}


def apply_verified_outcomes(payload: dict) -> dict:
    """Demo-presentation-only overlay (never touches app/ or any other
    session): adds `automatic_outcome` (the original ArcVision prediction,
    preserved verbatim, never overwritten) and `verified_outcome` (the
    frozen, manually-reviewed ground truth above) to every shot, and
    recomputes the headline session_summary figures (made/missed/
    shooting_percentage) from the verified outcomes -- the automatic
    figures are preserved alongside under `automatic_*` keys, never
    discarded. Mechanics/trajectory/coaching/consistency data are untouched
    -- those remain the real, automatically-computed ArcVision output.

    Raises ExportError (refusing to silently partially-apply the mapping)
    if the session's shots don't match the frozen 11-shot ground truth
    exactly -- e.g. if DEMO_SESSION_ID were ever pointed at a different
    session without updating this mapping.
    """
    shots = payload.get("shots", [])
    shot_indices = sorted(s["shot_index"] for s in shots)
    expected = sorted(VERIFIED_OUTCOMES_BY_SHOT_INDEX.keys())
    if shot_indices != expected:
        raise ExportError(
            f"Demo session's shot_index list {shot_indices} does not exactly match "
            f"the frozen ground truth's {expected} (docs/FINAL_DEMO_GROUND_TRUTH.md) -- "
            f"refusing to apply verified outcomes to a session that doesn't match it."
        )

    for shot in shots:
        shot["automatic_outcome"] = shot["outcome"]
        shot["verified_outcome"] = VERIFIED_OUTCOMES_BY_SHOT_INDEX[shot["shot_index"]]

    made = sum(1 for v in VERIFIED_OUTCOMES_BY_SHOT_INDEX.values() if v == "made")
    missed = sum(1 for v in VERIFIED_OUTCOMES_BY_SHOT_INDEX.values() if v == "missed")
    total = made + missed

    summary = payload.setdefault("session_summary", {})
    summary["automatic_made"] = summary.get("made")
    summary["automatic_missed"] = summary.get("missed")
    summary["automatic_unknown"] = summary.get("unknown")
    summary["automatic_shooting_percentage"] = summary.get("shooting_percentage")
    summary["made"] = made
    summary["missed"] = missed
    summary["unknown"] = 0
    summary["shooting_percentage"] = round(100.0 * made / total, 1) if total else None

    # The "N shot(s) could not be confidently classified..." warning is
    # generated from the automatic classifier's unknown count
    # (app/analytics/session_summary.py) and is correct, useful signal for
    # a normal upload -- but every shot in the verified demo DOES have a
    # resolved primary outcome (the verified one), so surfacing this as a
    # global "something's broken" banner here is actively misleading.
    # Other warnings (excluded shots, low hoop confidence, etc.) are left
    # alone -- only this one specific, count-prefixed message is dropped,
    # and only from this demo export's payload; app/analytics/
    # session_summary.py itself is untouched, so a normal, non-demo
    # session with real UNKNOWN outcomes still gets this warning.
    _unknown_warning_re = re.compile(r"^\d+ shot\(s\) could not be confidently classified as made or missed\.$")
    payload["warnings"] = [w for w in payload.get("warnings", []) if not _unknown_warning_re.match(w)]
    if "warnings" in summary:
        summary["warnings"] = [w for w in summary["warnings"] if not _unknown_warning_re.match(w)]

    payload["outcomes_verified"] = True
    return payload


# Explicit allowlist of frontend files to copy verbatim. Deliberately not a
# glob/recursive copy of frontend/, so adding an unrelated file to that
# directory later can't silently end up published without a deliberate
# addition here.
FRONTEND_FILES = [
    "index.html",
    "static/css/main.css",
    "static/js/api.js",
    "static/js/app.js",
    "static/js/charts.js",
    "static/favicon.svg",
    "static/images/hero-basketball.png",
]

# Filenames/substrings that must NEVER appear anywhere in the export.
# Checked at the end as an independent verification, not the only guard --
# the allowlist copying above is the primary control.
FORBIDDEN_NAME_SUBSTRINGS = [
    ".env", ".sqlite", ".pth", ".pt", "diagnostic", "checkpoint",
    "real_test_", "dataset", "training_run",
]
# Real leak indicators (local paths, usernames, DB file references) --
# checked in every text file in the export, no exceptions.
HARD_FORBIDDEN_CONTENT = ["C:\\", "c:\\", "/home/", "Users\\", "Users/", "HiRis", "sqlite3"]
# Softer patterns that are suspicious in auto-generated output (session.json,
# the app's own JS/CSS/HTML) but are legitimately, safely discussed in
# docs/METHODOLOGY.md's already-public prose (e.g. "the API key is stored in
# a gitignored .env" / crediting the Roboflow-hosted training dataset) --
# skipped for methodology.md specifically so the scan doesn't cry wolf on
# content that was already reviewed for public README/docs use.
SOFT_FORBIDDEN_CONTENT = [".env", "roboflow", "api_key", "apikey"]


class ExportError(RuntimeError):
    pass


def _assert_env_js_is_demo_mode(content: str) -> None:
    """Raises if `content` would make the exported bundle behave like local
    mode. Checked against the file as actually read back from disk after
    writing (see _write_env_js) rather than the in-memory string that was
    written, so this also catches a broken write -- e.g. a future change to
    FRONTEND_FILES that starts copying frontend/static/js/env.js (which
    defaults to "local") over this file after it's written."""
    if 'window.ARCVISION_MODE = "demo"' not in content or '"local"' in content:
        raise ExportError(
            "Generated dist/static/js/env.js does not set ARCVISION_MODE to "
            "\"demo\" -- refusing to ship a bundle that would behave like "
            f"local mode (no backend exists to serve it). Got:\n{content}"
        )


def _write_env_js(output_dir: Path) -> None:
    # Fresh env.js for the export -- NOT a copy of the repo's local one,
    # which defaults to "local" on purpose (see frontend/static/js/env.js).
    # Parent dirs are created explicitly here (not assumed to already exist
    # from copying other static/js/* files) so this function works
    # correctly regardless of FRONTEND_FILES' contents or ordering.
    env_js_path = output_dir / "static" / "js" / "env.js"
    env_js_path.parent.mkdir(parents=True, exist_ok=True)
    env_js_path.write_text(
        'window.ARCVISION_MODE = "demo";\n'
        'window.ARCVISION_REPO_URL = "https://github.com/rish-mishra/ArcVision";\n',
        encoding="utf-8",
    )
    _assert_env_js_is_demo_mode(env_js_path.read_text(encoding="utf-8"))


def _load_demo_session_payload() -> dict:
    row = repository.get_session(DEMO_SESSION_ID)
    if row is None:
        raise ExportError(f"Session {DEMO_SESSION_ID} not found in the database.")
    if row["status"] != "completed":
        raise ExportError(f"Session {DEMO_SESSION_ID} is not completed (status={row['status']!r}).")
    if not row["analysis_json"]:
        raise ExportError(f"Session {DEMO_SESSION_ID} has no stored analysis_json.")

    payload = json.loads(row["analysis_json"])
    # Overlay the same route-level fields app/api/routes.py's /results
    # endpoint adds on top of the stored JSON -- but honestly reflecting
    # what THIS bundle actually contains (session_id replaced with a plain
    # placeholder; has_diagnostic_video forced False since that file is
    # deliberately never published regardless of what the original local
    # session has).
    payload["session_id"] = "demo"
    # Presentation-only: the public demo never shows the raw uploaded
    # filename (an internal, DB-only detail with no public meaning). This
    # rewrites only the exported copy of the payload -- the database row
    # and every internal reference that depends on the real filename are
    # untouched.
    payload["original_filename"] = "ArcVision Demo Session"
    payload["created_at"] = row["created_at"]
    payload["has_annotated_video"] = True
    payload["has_diagnostic_video"] = False
    payload = apply_verified_outcomes(payload)
    return payload


def _find_annotated_video() -> Path:
    # Read the real local path from the DB row rather than guessing the
    # data/outputs/<id>/annotated.mp4 layout, but never copy anything else
    # from that row or that directory.
    row = repository.get_session(DEMO_SESSION_ID)
    path_str = row["annotated_video_path"]
    if not path_str:
        raise ExportError(f"Session {DEMO_SESSION_ID} has no annotated_video_path recorded.")
    path = Path(path_str)
    if not path.exists():
        raise ExportError(f"Annotated video not found on disk: {path}")
    return path


def _find_methodology() -> Path:
    path = ROOT / "docs" / "METHODOLOGY.md"
    if not path.exists():
        raise ExportError(f"docs/METHODOLOGY.md not found at {path}")
    return path


# Demo-only addition to the exported copy of methodology.md -- never written
# to the repo's own docs/METHODOLOGY.md, which stays identical for local
# mode. Short and factual on purpose, not a warning banner.
_DEMO_VERIFIED_OUTCOMES_NOTE = """

## About this demo's shot outcomes

The featured demo uses manually verified shot outcomes so the interface can
be explored against known results. Shot detection, tracking, biomechanics,
and coaching are generated automatically by ArcVision.
"""


def _write_demo_methodology(src: Path, dest: Path) -> None:
    text = src.read_text(encoding="utf-8")
    dest.write_text(text + _DEMO_VERIFIED_OUTCOMES_NOTE, encoding="utf-8")


def _dump_strict_session_json(payload: dict) -> str:
    """Serialize a session payload as strict, browser-parseable JSON.

    `json.dumps` permits NaN/Infinity as a non-standard extension, but
    JS's `JSON.parse` (used by `fetch(...).json()`) correctly rejects them
    -- a NaN anywhere in the payload (e.g. a degenerate scipy t-test
    p-value, see app/analytics/stats_utils.py) used to break the entire
    exported demo with no visible error past a DOM warning banner. Fail
    loudly at export time instead.
    """
    try:
        return json.dumps(payload, indent=2, allow_nan=False)
    except ValueError as exc:
        raise ExportError(
            f"Demo session payload contains NaN/Infinity, which is not valid JSON "
            f"and would break the exported bundle in a real browser: {exc}"
        ) from exc


def build():
    print(f"Exporting demo bundle for session {DEMO_SESSION_ID} -> {OUTPUT_DIR}")

    # Fail before writing anything if a required source is missing.
    payload = _load_demo_session_payload()
    annotated_src = _find_annotated_video()
    methodology_src = _find_methodology()
    for rel in FRONTEND_FILES:
        if not (FRONTEND_DIR / rel).exists():
            raise ExportError(f"Missing frontend source file: frontend/{rel}")

    # Build into a fresh sibling directory first, and only swap it into
    # place as the very last step. A common real workflow is "export, serve
    # dist/ with `python -m http.server` to preview it, then re-export while
    # iterating" -- with the previous rmtree(OUTPUT_DIR)-then-rebuild-in-
    # place approach, re-exporting while dist/ was still open in a server on
    # Windows crashed partway through shutil.rmtree (WinError 32, directory
    # handle still held) and left dist/ deleted down to an empty directory,
    # silently destroying the previously-working export. Building in
    # dist.new/ instead means a failure at any point above -- including the
    # final swap below -- never touches the last good OUTPUT_DIR.
    staging_dir = ROOT / "dist.new"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    for rel in FRONTEND_FILES:
        dest = staging_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FRONTEND_DIR / rel, dest)

    _write_env_js(staging_dir)

    demo_dir = staging_dir / "demo"
    demo_dir.mkdir()
    (demo_dir / "session.json").write_text(_dump_strict_session_json(payload), encoding="utf-8")
    shutil.copy2(annotated_src, demo_dir / "annotated.mp4")
    _write_demo_methodology(methodology_src, demo_dir / "methodology.md")

    (staging_dir / ".nojekyll").write_text("", encoding="utf-8")

    _privacy_scan(staging_dir)

    try:
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)
        staging_dir.rename(OUTPUT_DIR)
    except OSError as e:
        raise ExportError(
            f"The new export built successfully and is sitting at {staging_dir}, but "
            f"couldn't be moved into place at {OUTPUT_DIR} ({e}). This almost always means "
            f"something -- e.g. a `python -m http.server` still serving the old dist/ -- "
            f"has it open. Stop that process and re-run; nothing has been lost, the "
            f"previous {OUTPUT_DIR.name}/ (if any) is untouched."
        ) from e

    _report(OUTPUT_DIR)


def _privacy_scan(output_dir: Path):
    print("\n=== Privacy scan ===")
    problems = []
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(output_dir).as_posix()
        for bad in FORBIDDEN_NAME_SUBSTRINGS:
            if bad.lower() in rel.lower():
                problems.append(f"forbidden filename pattern '{bad}' in {rel}")
        if path.suffix.lower() in (".json", ".js", ".css", ".html", ".md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            checks = HARD_FORBIDDEN_CONTENT if path.name == "methodology.md" else HARD_FORBIDDEN_CONTENT + SOFT_FORBIDDEN_CONTENT
            for bad in checks:
                if bad in text:
                    problems.append(f"forbidden content pattern '{bad}' in {rel}")
    if problems:
        for p in problems:
            print(f"  FAIL: {p}")
        raise ExportError(f"Privacy scan found {len(problems)} issue(s) -- see above. Export left in place for inspection at {output_dir}.")
    print("  PASS -- no forbidden filenames or content patterns found in the export.")


def _report(output_dir: Path):
    print("\n=== Export contents ===")
    total = 0
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            size = path.stat().st_size
            total += size
            print(f"  {path.relative_to(output_dir).as_posix():40s} {size:>10,} bytes")
    print(f"\nTotal export size: {total:,} bytes ({total / 1024 / 1024:.2f} MB)")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    try:
        build()
    except ExportError as e:
        print(f"\nExport failed: {e}", file=sys.stderr)
        sys.exit(1)
