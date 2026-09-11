"""
Forensic extraction for the real_test_03 missed-shot investigation: pulls
native frames around each candidate release/apex region (the 8 near-top
ball clusters found in frame_level.csv, plus the full window-2 span and
the early portion of window 4) with ball position overlaid, for visual
confirmation of genuine release events vs. false triggers.

Usage:
    .venv\\Scripts\\python scripts\\forensic_video3_missed_shots.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_03.mov"
SESSION_DIR = ROOT / "data" / "diagnostics" / "real_test_03"
OUT_DIR = SESSION_DIR / "forensic_missed"

# (label, start_sec, end_sec) -- windows to extract, one frame every N frames
REGIONS = [
    ("cluster1_t2.4-3.6", 1.5, 4.2),
    ("cluster2_t5.5-6.2", 4.5, 7.2),
    ("window2_full_t9.5-11.7", 9.0, 12.0),
    ("cluster3_t17.1-17.6", 16.0, 18.2),
    ("cluster4_t19.9-20.5", 19.0, 21.3),
    ("window4_early_t26.0-27.5", 26.0, 27.5),
    ("cluster5_t28.8-29.6", 27.8, 30.3),
    ("cluster6_t31.7-32.4", 30.8, 33.0),
    ("cluster7_t34.9-35.6", 33.9, 36.2),
    ("cluster8_t38.2-38.6", 37.3, 39.3),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = json.loads((SESSION_DIR / "session_result.json").read_text(encoding="utf-8"))
    hoop = d["hoop"]
    cx, cy, r = hoop["rim_center_x"], hoop["rim_center_y"], hoop["rim_radius_px"]
    fps = d["video_meta"]["fps"]

    rows = list(csv.DictReader((SESSION_DIR / "frame_level.csv").open(encoding="utf-8")))
    by_frame = {int(r_["frame_index"]): r_ for r_ in rows}

    cap = cv2.VideoCapture(str(VIDEO_PATH))

    for label, t0, t1 in REGIONS:
        f0, f1 = int(t0 * fps), int(t1 * fps)
        region_dir = OUT_DIR / label
        region_dir.mkdir(parents=True, exist_ok=True)
        step = 2  # every 2nd frame to keep file counts manageable
        for fi in range(f0, f1 + 1, step):
            row = by_frame.get(fi)
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok, frame = cap.read()
            if not ok:
                continue
            vis = frame.copy()
            cv2.circle(vis, (int(cx), int(cy)), int(r), (0, 0, 255), 2)
            label_txt = f"f{fi} t={fi/fps:.3f}"
            if row is not None:
                bx, by, src, conf = row["ball_x"], row["ball_y"], row["ball_source"], row["ball_confidence"]
                if src not in ("", "unavailable") and bx:
                    bxf, byf = float(bx), float(by)
                    color = {"detected": (0, 255, 0), "interpolated": (0, 255, 255),
                             "predicted": (255, 0, 255)}.get(src, (255, 255, 255))
                    cv2.circle(vis, (int(bxf), int(byf)), 6, color, 2)
                    label_txt += f" ball=({bxf:.0f},{byf:.0f}) {src}"
            cv2.putText(vis, label_txt, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            cv2.imwrite(str(region_dir / f"f{fi:05d}.png"), vis)
        print(f"{label}: extracted frames {f0}-{f1} (step {step}) -> {region_dir}")

    cap.release()


if __name__ == "__main__":
    main()
