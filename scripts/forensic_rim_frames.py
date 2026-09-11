"""
Phase 1 forensic extraction: for each shot, pulls native-resolution video
frames spanning its rim-interaction evidence window, overlaid with the
hoop location and the ball's tracked position/source at each frame.

Usage:
    .venv\\Scripts\\python scripts\\forensic_rim_frames.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_02.mp4.mov"
SESSION_DIR = ROOT / "data" / "diagnostics" / "real_test_02"
OUT_DIR = SESSION_DIR / "forensic"

MARGIN_FRAMES = 12  # analysis frames before/after the key evidence frame(s)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = json.loads((SESSION_DIR / "session_result.json").read_text(encoding="utf-8"))
    hoop = d["hoop"]
    cx, cy, r = hoop["rim_center_x"], hoop["rim_center_y"], hoop["rim_radius_px"]
    native_fps = d["video_meta"]["fps"]
    analysis_fps = d["analysis_fps"]
    stride = round(native_fps / analysis_fps)

    rows = list(csv.DictReader((SESSION_DIR / "frame_level.csv").open(encoding="utf-8")))
    by_analysis_frame = {int(r_["frame_index"]): r_ for r_ in rows}

    cap = cv2.VideoCapture(str(VIDEO_PATH))

    for s in d["shots"]:
        shot_idx = s["shot_index"]
        ev = s["outcome_evidence"]
        key_frames = set()
        if "deflection_frame" in ev:
            key_frames.add(ev["deflection_frame"])
            if "approach_points" in ev:
                pass
        if "crossing_above_frame" in ev:
            key_frames.add(ev["crossing_above_frame"])
        if "crossing_below_frame" in ev:
            key_frames.add(ev["crossing_below_frame"])
        if not key_frames:
            key_frames.add(ev.get("apex_frame"))
        key_frames.discard(None)
        if not key_frames:
            continue

        lo = min(key_frames) - MARGIN_FRAMES
        hi = max(key_frames) + MARGIN_FRAMES

        shot_dir = OUT_DIR / f"shot{shot_idx}"
        shot_dir.mkdir(parents=True, exist_ok=True)

        for af in range(lo, hi + 1):
            row = by_analysis_frame.get(af)
            if row is None:
                continue
            native_idx = af * stride
            cap.set(cv2.CAP_PROP_POS_FRAMES, native_idx)
            ok, frame = cap.read()
            if not ok:
                continue

            vis = frame.copy()
            cv2.circle(vis, (int(cx), int(cy)), int(r), (0, 0, 255), 2)
            cv2.ellipse(vis, (int(cx), int(cy)), (int(r), int(r * 0.35)), 0, 0, 360, (0, 165, 255), 1)

            ball_x, ball_y, src, conf = row["ball_x"], row["ball_y"], row["ball_source"], row["ball_confidence"]
            label = f"f{af} t={row['timestamp_sec']}"
            if src not in ("", "unavailable") and ball_x:
                bx, by = float(ball_x), float(ball_y)
                color = {"detected": (0, 255, 0), "interpolated": (0, 255, 255), "predicted": (255, 0, 255)}.get(src, (255, 255, 255))
                cv2.circle(vis, (int(bx), int(by)), 6, color, 2)
                label += f" ball=({bx:.0f},{by:.0f}) {src} conf={conf}"
            tag = "KEY" if af in key_frames else ""
            cv2.putText(vis, f"{label} {tag}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            cv2.imwrite(str(shot_dir / f"f{af:05d}.png"), vis)

        print(f"shot {shot_idx}: extracted analysis frames {lo}-{hi} (key={sorted(key_frames)}) -> {shot_dir}")

    cap.release()


if __name__ == "__main__":
    main()
