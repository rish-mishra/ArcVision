"""
Diagnostic visualization: for each shot in a completed session, plots the
reliable (detected/interpolated) ball trajectory in image space against
the hoop location and its tight/wide interaction bands, so the evidence
behind each MADE/MISSED/UNKNOWN call can be checked visually at a glance.

Usage:
    .venv\\Scripts\\python scripts\\plot_rim_interactions.py <session_result.json> [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_result", type=str)
    parser.add_argument("--frame-csv", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default=None)
    args = parser.parse_args()

    session_path = Path(args.session_result)
    out_dir = Path(args.out_dir) if args.out_dir else session_path.parent
    frame_csv = Path(args.frame_csv) if args.frame_csv else session_path.parent / "frame_level.csv"

    d = json.loads(session_path.read_text(encoding="utf-8"))
    hoop = d["hoop"]
    cx, cy, r = hoop["rim_center_x"], hoop["rim_center_y"], hoop["rim_radius_px"]

    import csv
    rows = list(csv.DictReader(frame_csv.open(encoding="utf-8")))

    n = len(d["shots"])
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4.5), squeeze=False)
    axes = axes[0]

    for ax, s in zip(axes, d["shots"]):
        lo = s["release_time_sec"] or s["start_time_sec"]
        hi = s["end_time_sec"]
        pts = [row for row in rows if lo <= float(row["timestamp_sec"]) <= hi
                and row["ball_source"] in ("detected", "interpolated")]

        for row in pts:
            x, y = float(row["ball_x"]), float(row["ball_y"])
            color = "#0ca30c" if row["ball_source"] == "detected" else "#eda100"
            ax.scatter(x, y, s=25, color=color, zorder=3)

        tight = hoop["rim_radius_px"] * 1.6 + 8
        wide = hoop["rim_radius_px"] * 3.0 + 8
        ax.add_patch(patches.Rectangle((cx - tight, cy - r * 0.35), 2 * tight, r * 0.7,
                                          facecolor="none", edgecolor="#2a78d6", linewidth=1.5, label="tight band"))
        ax.add_patch(patches.Circle((cx, cy), wide, facecolor="none", edgecolor="#898781",
                                       linestyle="--", linewidth=1, label="wide zone"))
        ax.add_patch(patches.Ellipse((cx, cy), 2 * r, 0.7 * r, facecolor="none", edgecolor="#d03b3b", linewidth=2))

        outcome = s["outcome"]
        conf = s["outcome_confidence"]
        color_map = {"made": "#0ca30c", "missed": "#d03b3b", "unknown": "#898781"}
        ax.set_title(f"Shot {s['shot_index']}: {outcome.upper()} ({conf:.2f})", fontsize=10,
                      color=color_map.get(outcome, "black"))
        ax.invert_yaxis()
        ax.set_xlim(0, 960)
        ax.set_ylim(540, 0)
        ax.set_xlabel("x (px)")
        if s is d["shots"][0]:
            ax.set_ylabel("y (px, image coords)")

    fig.suptitle("Ball trajectory vs. hoop interaction zones (green=detected, orange=interpolated, "
                  "red ellipse=rim, blue box=tight/MADE band, dashed=wide/MISS zone)", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_path = out_dir / "rim_interactions.png"
    fig.savefig(out_path, dpi=130)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
