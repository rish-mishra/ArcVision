"""
Fixes a presentation bug in the featured public demo's replay video: the
outcome text ("MADE"/"MISSED"/"UNKNOWN") burned into demo/annotated.mp4 by
app/annotation/renderer.py at render time reflects the AUTOMATIC classifier's
prediction (ShotRecord.outcome) -- because that is the only outcome that
exists at render time, before verified outcomes are ever applied. The public
demo's UI then overlays the frozen manually-verified outcome
(scripts/export_demo.py's VERIFIED_OUTCOMES_BY_SHOT_INDEX) on top of that same
session, so a shot the classifier got wrong (e.g. shot 7: automatic "missed",
verified "made") shows a contradiction: UI says MADE, video visibly says
MISSED.

This script does NOT re-run detection/pose/tracking (no app.pipeline.
orchestrator.run_pipeline call) -- that data isn't needed to fix this. It
opens the ALREADY-RENDERED annotated.mp4 (skeleton/ball/hoop/shot-number/
RELEASE overlays are all correct and untouched) and, for each shot, patches
over ONLY the small outcome-label region during its ~1.2s post-result window
with the verified outcome instead, reusing app/annotation/renderer.py's own
_draw_label/_OUTCOME_COLOR/_COLOR_TEXT_BG so the replacement text is pixel-
identical in font/size/background style to the label it replaces. Everything
else in every frame is copied through unchanged.

Scope: writes a NEW file (annotated_featured.mp4, alongside the original
annotated.mp4) for scripts/export_demo.py's DEMO_SESSION_ID only. The
original annotated.mp4 and its DB row (annotated_video_path) are left
completely untouched, so local/normal ArcVision sessions are unaffected.

Usage:
    .venv\\Scripts\\python scripts\\regenerate_featured_demo_replay_labels.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.annotation.renderer import _COLOR_TEXT_BG, _draw_label, _OUTCOME_COLOR
from app.events.outcome_detector import ShotOutcome
from app.pipeline.video_io import transcode_to_browser_mp4
from app.storage import repository

# Import the single frozen ground-truth mapping rather than re-declaring one
# here. Shared with scripts/export_demo.py via its own module (not imported
# directly from export_demo.py) so export_demo.py can call regenerate()
# below without a circular import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_ground_truth import DEMO_SESSION_ID, VERIFIED_OUTCOMES_BY_SHOT_INDEX  # noqa: E402

POST_RESULT_WINDOW_SEC = 1.2  # must match app/annotation/renderer.py's _active_shot_for_time default


def _active_shot(shots: list[dict], t: float) -> dict | None:
    """Mirrors app/annotation/renderer.py's _active_shot_for_time exactly
    (same window, same first-match-in-order semantics) but over plain dicts
    loaded from the stored session JSON -- constructing real ShotRecord
    instances isn't needed since only start/end time are read here."""
    for s in shots:
        if s["start_time_sec"] <= t <= s["end_time_sec"] + POST_RESULT_WINDOW_SEC:
            return s
    return None


class RegenerationError(RuntimeError):
    """Raised (never SystemExit) so scripts/export_demo.py can catch this and
    turn it into a clear ExportError instead of letting a bare SystemExit
    propagate or, worse, letting the caller silently fall back to the stale
    original video."""


def regenerate(session_id: str) -> Path:
    """Regenerates <session>'s featured-demo replay (verified outcome labels
    in place of the automatic ones the original render burned in) and
    returns the output path. Deterministic: same inputs (the original
    annotated.mp4 + the frozen VERIFIED_OUTCOMES_BY_SHOT_INDEX mapping)
    always produce the same labels, and this never touches CV inference.
    Called both from this script's CLI entry point and, when the featured
    file is missing, automatically by scripts/export_demo.py."""
    row = repository.get_session(session_id)
    if row is None:
        raise RegenerationError(f"Session {session_id} not found in the database.")
    original_path = Path(row["annotated_video_path"])
    if not original_path.exists():
        raise RegenerationError(f"Original annotated video not found: {original_path}")

    payload = json.loads(row["analysis_json"])
    shots = payload["shots"]
    shot_indices = sorted(s["shot_index"] for s in shots)
    expected = sorted(VERIFIED_OUTCOMES_BY_SHOT_INDEX.keys())
    if shot_indices != expected:
        raise RegenerationError(
            f"Session's shot_index list {shot_indices} does not match the frozen "
            f"ground truth's {expected} -- refusing to relabel."
        )

    output_path = original_path.with_name("annotated_featured.mp4")
    raw_output = output_path.with_suffix(".raw.mp4")

    cap = cv2.VideoCapture(str(original_path))
    if not cap.isOpened():
        raise RegenerationError(f"Could not open {original_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Source: {original_path} ({w}x{h} @ {fps:.3f}fps)")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(raw_output), fourcc, fps, (w, h))

    # Largest possible label ("UNKNOWN") at the exact font/scale/thickness
    # used for the outcome label, so the erase rect always fully covers
    # whatever the original render drew there, regardless of what the
    # verified replacement text is -- computed via the real font metrics
    # rather than a guessed pixel size, then filled with the renderer's own
    # label background color before the new text is drawn on top.
    (max_tw, max_th), _ = cv2.getTextSize("UNKNOWN", cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
    org = (12, 90)
    erase_tl = (org[0] - 4, org[1] - max_th - 6)
    erase_br = (org[0] + max_tw + 4, org[1] + 4)

    patched_frames = 0
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = frame_idx / fps
            shot = _active_shot(shots, t)
            if shot and t > shot["end_time_sec"]:
                verified = VERIFIED_OUTCOMES_BY_SHOT_INDEX[shot["shot_index"]]
                outcome_enum = ShotOutcome.MADE if verified == "made" else ShotOutcome.MISSED
                cv2.rectangle(frame, erase_tl, erase_br, _COLOR_TEXT_BG, -1)
                _draw_label(frame, verified.upper(), org, _OUTCOME_COLOR[outcome_enum], scale=0.8, thickness=2)
                patched_frames += 1
            writer.write(frame)
            frame_idx += 1
    finally:
        writer.release()
        cap.release()

    print(f"Patched {patched_frames} frames across {len(shots)} shots.")
    transcode_to_browser_mp4(raw_output, output_path)
    raw_output.unlink(missing_ok=True)
    print(f"Wrote {output_path}")
    return output_path


def main() -> None:
    try:
        regenerate(DEMO_SESSION_ID)
    except RegenerationError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
