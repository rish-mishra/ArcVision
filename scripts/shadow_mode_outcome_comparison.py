"""
READ-ONLY driver for the evidence-weighted outcome shadow experiment.
Reconstructs each shot's ball trajectory + hoop from already-existing
diagnostic artifacts on disk (data/diagnostics/*/frame_level.csv +
session_result.json, produced by prior, real detection runs -- no new
detection pass is run by this script) and the current demo session's DB
row, then calls BOTH the real, unmodified app.events.outcome_detector.
detect_outcome() and the shadow scorer on the identical trajectory slice
for a fair, isolated comparison of only the crossing-search/scoring logic.

Writes a comparison report to data/diagnostics/shadow_outcome_experiment/.
Does not modify any production file, test, threshold, or stored session.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.outcome_detector import detect_outcome
from app.vision.types import BallObservation, DataSource, HoopLocation
from scripts.shadow_mode_evidence_weighted_outcome import detect_outcome_shadow

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "diagnostics" / "shadow_outcome_experiment"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_SRC_MAP = {"detected": DataSource.DETECTED, "interpolated": DataSource.INTERPOLATED,
            "predicted": DataSource.PREDICTED, "unavailable": DataSource.UNAVAILABLE}


def _load_frame_level_csv(path: Path) -> dict:
    """frame_index -> BallObservation, for the WHOLE video."""
    by_frame = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fi = int(row["frame_index"])
            src = _SRC_MAP.get(row["ball_source"], DataSource.UNAVAILABLE)
            if src == DataSource.UNAVAILABLE or row["ball_x"] == "":
                continue
            by_frame[fi] = BallObservation(
                frame_index=fi, timestamp_sec=float(row["timestamp_sec"]),
                center_x=float(row["ball_x"]), center_y=float(row["ball_y"]),
                radius_px=10.0,  # not recorded in frame_level.csv; a fixed placeholder used
                                 # identically for both production and shadow calls below, so
                                 # it cancels out of the comparison (band sizing affects both
                                 # equally) -- see report caveat.
                confidence=float(row["ball_confidence"]), source=src,
            )
    return by_frame


def _hoop_from_dict(d: dict) -> HoopLocation:
    return HoopLocation(rim_center_x=d["rim_center_x"], rim_center_y=d["rim_center_y"],
                          rim_radius_px=d["rim_radius_px"], confidence=d["confidence"],
                          votes=d["votes"], method=d["method"],
                          backboard_bbox=d.get("backboard_bbox"))


def _shot_flight_points(shot: dict, ball_by_frame: dict, analysis_fps: float) -> list:
    # ShotRecord's stored JSON only carries *_time_sec, not frame indices --
    # convert using the session's own recorded analysis_fps (same fps the
    # frame_level.csv frame_index column was produced at).
    release_time = shot.get("release_time_sec")
    start_time = shot.get("start_time_sec", 0.0)
    end_time = shot["end_time_sec"]
    flight_start_time = release_time if release_time is not None else start_time
    flight_start = round(flight_start_time * analysis_fps)
    end_frame = round(end_time * analysis_fps)
    return [ball_by_frame[fi] for fi in range(flight_start, end_frame + 1) if fi in ball_by_frame]


def evaluate_video_from_diagnostic_dir(name: str, diag_dir: Path, ground_truth: dict | None = None,
                                         exclude_release_times: list | None = None):
    session = json.loads((diag_dir / "session_result.json").read_text(encoding="utf-8"))
    ball_by_frame = _load_frame_level_csv(diag_dir / "frame_level.csv")
    hoop = _hoop_from_dict(session["hoop"])
    analysis_fps = session["analysis_fps"]
    rows = []
    exclude_release_times = exclude_release_times or []

    for shot in session["shots"]:
        release_time = shot.get("release_time_sec")
        if release_time is not None and any(abs(release_time - t) < 2.0 for t in exclude_release_times):
            continue  # previously-documented false-positive shot window (V4 Part A) -- not a real shot
        flight_points = _shot_flight_points(shot, ball_by_frame, analysis_fps)

        prod = detect_outcome(flight_points, hoop)
        shadow = detect_outcome_shadow(flight_points, hoop)

        truth = None
        if ground_truth is not None and release_time is not None:
            best = min(ground_truth, key=lambda gt: abs(gt[0] - release_time), default=None)
            if best is not None and abs(best[0] - release_time) < 5.0:
                truth = best[1]

        rows.append({
            "video": name, "shot_index": shot["shot_index"], "release_time": round(release_time, 2) if release_time else None,
            "truth": truth, "production": prod.outcome.value, "production_conf": prod.confidence,
            "shadow": shadow.outcome.value, "shadow_conf": shadow.confidence, "shadow_reason": shadow.reason,
            "changed": prod.outcome.value != shadow.outcome.value,
            "n_candidates": getattr(shadow, "n_candidates_evaluated", 0),
            "chosen_pair": (shadow.chosen_candidate.a_frame, shadow.chosen_candidate.b_frame) if getattr(shadow, "chosen_candidate", None) else None,
        })
    return rows


def evaluate_demo_from_forensic_dumps(session_json_path: Path, forensic_dir: Path):
    session = json.loads(session_json_path.read_text(encoding="utf-8"))
    hoop = _hoop_from_dict(session["hoop"])
    rows = []
    for shot in session["shots"]:
        sid = shot["shot_index"]
        frames_path = forensic_dir / f"shot_{sid}_frames.json"
        if not frames_path.exists():
            continue
        frames = json.loads(frames_path.read_text(encoding="utf-8"))
        release_time = shot.get("release_time_sec")
        release_frame = None
        # shot_index frames dump has 'frame'/'obs_xy'/'obs_source'/'obs_conf'; reconstruct.
        flight_points = []
        for r in frames:
            if r["obs_xy"] is None:
                continue
            src = _SRC_MAP.get(r["obs_source"], DataSource.UNAVAILABLE)
            flight_points.append(BallObservation(
                frame_index=r["frame"], timestamp_sec=r["frame"] / 29.9624,
                center_x=r["obs_xy"][0], center_y=r["obs_xy"][1], radius_px=10.0,
                confidence=r["obs_conf"] or 0.0, source=src,
            ))
        # Match production's own flight_start..end_frame slice using the
        # shot's own recorded release/end frame (from the forensic dump's
        # in_window/past_end flags rather than re-deriving release here).
        window_frames = [r["frame"] for r in frames if r["in_window"]]
        if not window_frames:
            continue
        flight_start = min(window_frames)
        end_frame = max(window_frames)
        flight_points = [p for p in flight_points if flight_start <= p.frame_index <= end_frame]

        prod = detect_outcome(flight_points, hoop)
        shadow = detect_outcome_shadow(flight_points, hoop)
        rows.append({
            "video": "demo", "shot_index": sid, "release_time": round(release_time, 2) if release_time else None,
            "truth": None, "production": prod.outcome.value, "production_conf": prod.confidence,
            "shadow": shadow.outcome.value, "shadow_conf": shadow.confidence, "shadow_reason": shadow.reason,
            "changed": prod.outcome.value != shadow.outcome.value,
            "n_candidates": getattr(shadow, "n_candidates_evaluated", 0),
            "chosen_pair": (shadow.chosen_candidate.a_frame, shadow.chosen_candidate.b_frame) if getattr(shadow, "chosen_candidate", None) else None,
        })
    return rows


def main():
    all_rows = []

    all_rows += evaluate_video_from_diagnostic_dir("V1", ROOT / "data/diagnostics/real_test_01_final")
    all_rows += evaluate_video_from_diagnostic_dir("V2", ROOT / "data/diagnostics/real_test_02_final")
    all_rows += evaluate_video_from_diagnostic_dir("V3", ROOT / "data/diagnostics/real_test_03")

    v4_gt = [
        (3, "MISSED"), (15, "MADE"), (27, "MADE"), (38, "MISSED"), (44, "MISSED"), (49, "MISSED"),
        (61, "MISSED"), (69, "MISSED"), (81, "MADE"), (91, "MADE"), (100, "MISSED"), (112, "MISSED"),
        (124, "MADE"), (139, "MISSED"), (149, "MISSED"), (163, "MADE"), (176, "MADE"), (186, "MISSED"),
    ]
    v4_false_positive_release_times = [22.5, 57.7, 77.5, 109.7, 132.9]
    all_rows += evaluate_video_from_diagnostic_dir(
        "V4", ROOT / "data/diagnostics/real_test_04", ground_truth=v4_gt,
        exclude_release_times=v4_false_positive_release_times)

    demo_session_path = ROOT / "data/diagnostics/arcvision_demo_01_forensic_session.json"
    if not demo_session_path.exists():
        # Fall back: read directly from the DB row used for the earlier forensic dump.
        sys.path.insert(0, str(ROOT))
        from app.storage import repository
        row = repository.get_session("08b2d16fa1404b90")
        demo_session_path.write_text(row["analysis_json"], encoding="utf-8")
    all_rows += evaluate_demo_from_forensic_dumps(demo_session_path, ROOT / "data/diagnostics/arcvision_demo_01_forensic")

    (OUT_DIR / "comparison.json").write_text(json.dumps(all_rows, indent=2), encoding="utf-8")

    print(f"{'video':6s} {'shot':4s} {'t':>6s} {'truth':8s} {'prod':8s} {'shadow':8s} {'chg':4s} {'s_conf':7s} {'n_cand':6s} reason")
    for r in all_rows:
        print(f"{r['video']:6s} {r['shot_index']:<4d} {str(r['release_time']):>6s} "
              f"{str(r['truth']):8s} {r['production']:8s} {r['shadow']:8s} "
              f"{'YES' if r['changed'] else '':4s} {r['shadow_conf']:<7.3f} {r['n_candidates']:<6d} {r['shadow_reason']}")

    print(f"\nSaved: {OUT_DIR}/comparison.json")


if __name__ == "__main__":
    main()
