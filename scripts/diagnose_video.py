"""
Standalone diagnostic tool for a single video: runs the full pipeline and
dumps everything needed to understand exactly what the system saw and
decided, without needing to go through the web UI. This is the primary
tool for investigating real-footage failures -- when a real shot is
mis-segmented, mis-classified, or a metric looks wrong, run this first and
inspect the JSON dump and plots before changing any thresholds.

Usage:
    .venv\\Scripts\\python scripts\\diagnose_video.py path\\to\\video.mp4 [--out-dir data\\diagnostics\\myclip]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.annotation.diagnostic_renderer import render_diagnostic_video
from app.logging_config import get_logger
from app.pipeline.orchestrator import run_pipeline
from app.storage.serializers import serialize_session_result, to_jsonable
from app.vision.types import DataSource

log = get_logger("scripts.diagnose_video")


def _print_progress(stage: str, pct: float) -> None:
    print(f"[{pct*100:5.1f}%] {stage}")


def dump_frame_level_csv(result, out_path: Path) -> None:
    """One row per analyzed frame: pose confidence, ball source/confidence,
    knee angle if available -- the first thing to scan when a shot boundary
    or release looks wrong on a real video."""
    import csv
    pose_by_frame = {p.frame_index: p for p in result.pose_frames}
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "timestamp_sec", "pose_detected", "pose_confidence",
                           "ball_x", "ball_y", "ball_source", "ball_confidence"])
        for obs in result.ball_observations:
            pf = pose_by_frame.get(obs.frame_index)
            writer.writerow([
                obs.frame_index, round(obs.timestamp_sec, 4),
                pf.detected if pf else False, round(pf.pose_confidence, 3) if pf else 0.0,
                round(obs.center_x, 1) if obs.source != DataSource.UNAVAILABLE else "",
                round(obs.center_y, 1) if obs.source != DataSource.UNAVAILABLE else "",
                obs.source.value, round(obs.confidence, 3),
            ])


def make_diagnostic_plots(result, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ts = [o.timestamp_sec for o in result.ball_observations]
    ys = [o.center_y if o.source != DataSource.UNAVAILABLE else float("nan") for o in result.ball_observations]
    sources = [o.source.value for o in result.ball_observations]

    fig, ax = plt.subplots(figsize=(11, 4))
    color_map = {"detected": "#0ca30c", "interpolated": "#eda100", "predicted": "#eb6834", "unavailable": "#d03b3b"}
    for src, color in color_map.items():
        xs = [t for t, y, s in zip(ts, ys, sources) if s == src]
        yv = [y for y, s in zip(ys, sources) if s == src]
        ax.scatter(xs, yv, s=8, color=color, label=src)
    for shot in result.shots:
        ax.axvspan(shot.start_time_sec, shot.end_time_sec, color="gray", alpha=0.08)
        if shot.release_time_sec:
            ax.axvline(shot.release_time_sec, color="blue", linestyle="--", linewidth=0.8)
    ax.invert_yaxis()
    ax.set_xlabel("time (s)")
    ax.set_ylabel("ball y (px, image coords, inverted)")
    ax.set_title("Ball vertical position over time (shaded = detected shot windows, dashed = release)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "ball_trajectory.png", dpi=130)
    plt.close(fig)

    pf_conf = [(p.timestamp_sec, p.pose_confidence) for p in result.pose_frames]
    fig, ax = plt.subplots(figsize=(11, 3))
    ax.plot([t for t, _ in pf_conf], [c for _, c in pf_conf], color="#2a78d6", linewidth=1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("pose confidence")
    ax.set_title("Pose detection confidence over time")
    fig.tight_layout()
    fig.savefig(out_dir / "pose_confidence.png", dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Diagnose FormAI Basketball pipeline behavior on one video.")
    parser.add_argument("video", type=str, help="Path to a video file")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory (default: data/diagnostics/<video-stem>)")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"ERROR: video not found: {video_path}")
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else Path("data/diagnostics") / video_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing {video_path} -> {out_dir}")
    result = run_pipeline(video_path, _print_progress)

    (out_dir / "session_result.json").write_text(
        json.dumps(serialize_session_result(result), indent=2), encoding="utf-8"
    )
    dump_frame_level_csv(result, out_dir / "frame_level.csv")

    shot_summary = []
    for s in result.shots:
        shot_summary.append({
            "shot_index": s.shot_index, "outcome": s.outcome.value, "outcome_confidence": s.outcome_confidence,
            "outcome_reason": s.outcome_reason, "release_time_sec": s.release_time_sec,
            "release_confidence": s.release_confidence, "shooting_side": s.shooting_side,
            "warnings": s.warnings, "excluded": s.excluded_from_analysis,
        })
    print("\n=== Shot summary ===")
    for row in shot_summary:
        print(f"  Shot {row['shot_index']}: {row['outcome'].upper()} "
                f"(conf={row['outcome_confidence']}, reason={row['outcome_reason']}) "
                f"release={row['release_time_sec']}s side={row['shooting_side']}")
        if row["warnings"]:
            print(f"      warnings: {row['warnings']}")

    if result.hoop:
        print(f"\nHoop: center=({result.hoop.rim_center_x:.0f},{result.hoop.rim_center_y:.0f}) "
                f"radius={result.hoop.rim_radius_px:.0f} confidence={result.hoop.confidence} votes={result.hoop.votes}")
    else:
        print("\nHoop: NOT located")

    if result.warnings:
        print("\nSession warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print("\nGenerating diagnostic plots...")
    try:
        make_diagnostic_plots(result, out_dir)
    except Exception as e:
        print(f"  (plot generation failed: {e})")

    print("Rendering diagnostic overlay video (this can take a while)...")
    render_diagnostic_video(video_path, result.video_meta, result.shots, result.hoop,
                              result.pose_frames, result.ball_observations, out_dir / "diagnostic.mp4")

    print(f"\nDone. See {out_dir}:")
    print("  session_result.json  - full structured pipeline output")
    print("  frame_level.csv      - per-frame pose/ball diagnostic trace")
    print("  ball_trajectory.png  - ball y-position over time with shot windows")
    print("  pose_confidence.png  - pose confidence over time")
    print("  diagnostic.mp4       - overlay video with raw confidences/states")


if __name__ == "__main__":
    main()
