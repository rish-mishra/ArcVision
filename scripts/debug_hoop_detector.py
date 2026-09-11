"""
Ad-hoc visual debugger for hoop detection: runs BOTH candidate sources
(classical color/Hough, and the learned YOLO-World open-vocabulary
detector) on sampled frames of a video at the SAME analysis resolution the
production pipeline uses, saves annotated images showing every candidate
from each source plus the final cross-frame aggregated estimate. Used to
diagnose real-footage failures before touching any thresholds.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app.config import CONFIG
from app.pipeline.video_io import FrameReader, validate_video
from app.tracking.hoop_aggregator import aggregate_hoop_candidates
from app.vision.detection.hoop_detector import _orange_mask, detect_hoop_candidates
from app.vision.detection.hoop_detector_learned import LearnedHoopDetector


def debug_frame(frame_bgr, out_prefix: Path, learned_detector):
    cfg = CONFIG.hoop
    h, w = frame_bgr.shape[:2]
    search_h = int(h * 0.75)
    roi = frame_bgr[:search_h, :]
    mask = _orange_mask(roi)
    min_r = cfg.hough_min_radius_frac * h
    max_r = cfg.hough_max_radius_frac * h
    print(f"  frame size {w}x{h}, allowed radius range=[{min_r:.1f}, {max_r:.1f}]px")
    print(f"  [classical] orange mask nonzero px: {int(np.count_nonzero(mask))} / {mask.size} "
            f"({100*np.count_nonzero(mask)/mask.size:.3f}%)")

    classical = detect_hoop_candidates(frame_bgr)
    print(f"  [classical] {len(classical)} candidates")
    for (x, y, r, conf) in classical:
        print(f"      x={x:.0f} y={y:.0f} r={r:.0f} conf={conf:.3f}")

    learned = learned_detector.detect(frame_bgr) if learned_detector else []
    print(f"  [learned]   {len(learned)} candidates")
    for (x, y, r, conf) in learned:
        print(f"      x={x:.0f} y={y:.0f} r={r:.0f} conf={conf:.3f}")

    vis = frame_bgr.copy()
    for (x, y, r, conf) in classical:
        cv2.circle(vis, (int(x), int(y)), int(r), (0, 165, 255), 2)  # orange = classical
        cv2.putText(vis, f"C {conf:.2f}", (int(x) + 4, int(y) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)
    for (x, y, r, conf) in learned:
        cv2.circle(vis, (int(x), int(y)), int(r), (255, 0, 255), 2)  # magenta = learned
        cv2.putText(vis, f"L {conf:.2f}", (int(x) + 4, int(y) + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

    cv2.imwrite(str(out_prefix) + "_mask.png", mask)
    cv2.imwrite(str(out_prefix) + "_candidates.png", vis)
    return classical, learned


def main():
    video_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("real_test_01.mp4.mov")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/diagnostics/hoop_debug")
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = validate_video(video_path)
    reader = FrameReader(meta)
    print(f"Analysis resolution: {reader.analysis_width}x{reader.analysis_height}")

    learned_detector = LearnedHoopDetector.get() if CONFIG.hoop.use_learned_detector else None
    if learned_detector:
        learned_detector.warmup()

    fractions = [0.02, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]
    frames = list(reader)
    total = len(frames)

    all_candidates = []
    for frac in fractions:
        idx = int(total * frac)
        af = frames[idx]
        print(f"\n=== frame {af.frame_index} (t={af.timestamp_sec:.1f}s, {frac*100:.0f}% through) ===")
        classical, learned = debug_frame(af.image, out_dir / f"f{af.frame_index:05d}", learned_detector)
        all_candidates.extend((af.frame_index, x, y, r, conf, "classical") for (x, y, r, conf) in classical)
        all_candidates.extend((af.frame_index, x, y, r, conf, "learned") for (x, y, r, conf) in learned)

    print(f"\n=== Aggregating {len(all_candidates)} total candidates from these sampled frames ===")
    hoop = aggregate_hoop_candidates(all_candidates)
    if hoop:
        print(f"  FINAL ESTIMATE: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) "
                f"radius={hoop.rim_radius_px:.0f} confidence={hoop.confidence} votes={hoop.votes} method={hoop.method}")
        # Draw final estimate onto the first debug frame for visual confirmation.
        first_af = frames[int(total * fractions[0])]
        vis = first_af.image.copy()
        cv2.ellipse(vis, (int(hoop.rim_center_x), int(hoop.rim_center_y)),
                     (int(hoop.rim_radius_px), int(hoop.rim_radius_px * 0.35)), 0, 0, 360, (0, 255, 0), 3)
        cv2.putText(vis, f"FINAL conf={hoop.confidence} votes={hoop.votes}",
                     (int(hoop.rim_center_x) - 60, int(hoop.rim_center_y) - 30),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imwrite(str(out_dir / "final_estimate.png"), vis)
    else:
        print("  FINAL ESTIMATE: none (hoop not located)")

    print(f"\nSaved debug images to {out_dir}")


if __name__ == "__main__":
    main()
