"""
Compares MediaPipe BlazePose (this app's current pose estimator) against
RF-DETR Keypoint (RFDETRKeypointPreview, zero-shot COCO-17 keypoints, no
training needed) on real frames from real_test_01.mp4.mov -- specifically
each shot's release moment, since that's the biomechanically critical,
often partially-occluded/motion-blurred instant this comparison matters
most for.

Does NOT touch or require the ball/rim training run; entirely independent.

Usage:
    .venv\\Scripts\\python scripts\\compare_pose_models.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app.vision.pose.pose_estimator import PoseEstimator
from app.vision.types import POSE_LANDMARK_NAMES

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_01.mp4.mov"
OUT_DIR = ROOT / "data" / "diagnostics" / "pose_model_comparison"

# COCO-17 order used by RFDETRKeypointPreview.
COCO17 = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
COCO17_INDEX = {name: i for i, name in enumerate(COCO17)}

# Joints this app actually uses (see app/vision/types.py POSE_LANDMARK_NAMES).
COMPARE_JOINTS = [n for n in POSE_LANDMARK_NAMES if n in COCO17_INDEX]

SKELETON_EDGES = [
    ("left_shoulder", "right_shoulder"), ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"), ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"), ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"), ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
]


def _draw_skeleton(frame, points: dict, color, label: str, y_offset: int):
    for a, b in SKELETON_EDGES:
        if a in points and b in points:
            cv2.line(frame, points[a], points[b], color, 2)
    for name, (x, y) in points.items():
        cv2.circle(frame, (x, y), 4, color, -1)
    cv2.putText(frame, label, (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    session = json.loads((ROOT / "data" / "diagnostics" / "real_test_01" / "session_result.json")
                           .read_text(encoding="utf-8"))
    fps = session["video_meta"]["fps"]
    release_frames = [(s["shot_index"], int(round(s["release_time_sec"] * fps)))
                        for s in session["shots"] if s["release_time_sec"]]

    print("Loading MediaPipe...")
    mp_estimator = PoseEstimator()

    print("Loading RFDETRKeypointPreview (forced to CPU -- the GPU is busy with the ball/rim "
           "training run, and this comparison isn't worth risking an OOM in that job)...")
    from rfdetr import RFDETRKeypointPreview
    rfdetr_model = RFDETRKeypointPreview(device="cpu")
    from PIL import Image

    cap = cv2.VideoCapture(str(VIDEO_PATH))

    mp_times, rf_times = [], []
    results_summary = []

    for shot_idx, frame_idx in release_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            print(f"shot {shot_idx}: FAILED to read frame {frame_idx}")
            continue
        h, w = frame.shape[:2]

        # --- MediaPipe (full frame -- matches process_frame path; the
        # production pipeline runs it on a person crop, but comparing both
        # models against the same identical input isolates the pose-model
        # difference specifically, rather than also varying the input crop) ---
        t0 = time.time()
        pf = mp_estimator.process_frame(frame, frame_idx, frame_idx / fps)
        mp_times.append(time.time() - t0)

        mp_points = {}
        mp_conf = {}
        if pf.detected:
            for name in COMPARE_JOINTS:
                lm = pf.landmark(name)
                if lm is not None:
                    mp_points[name] = (int(lm.x * w), int(lm.y * h))
                    mp_conf[name] = lm.visibility

        # --- RF-DETR Keypoint ---
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        t0 = time.time()
        det = rfdetr_model.predict(img, threshold=0.3)
        rf_times.append(time.time() - t0)

        rf_points = {}
        rf_conf = {}
        if len(det.xy) > 0:
            # Largest-area person box = the shooter (closest/most prominent).
            xyxy = det.data["xyxy"]
            areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
            person_i = int(np.argmax(areas))
            kp_conf = det.keypoint_confidence if hasattr(det, "keypoint_confidence") else det.confidence
            for name in COMPARE_JOINTS:
                ki = COCO17_INDEX[name]
                x, y = det.xy[person_i, ki]
                rf_points[name] = (int(x), int(y))
                rf_conf[name] = float(kp_conf[person_i, ki])

        # --- Compare ---
        joint_report = {}
        for name in COMPARE_JOINTS:
            entry = {"mp_conf": mp_conf.get(name), "rf_conf": rf_conf.get(name)}
            if name in mp_points and name in rf_points:
                dx = mp_points[name][0] - rf_points[name][0]
                dy = mp_points[name][1] - rf_points[name][1]
                entry["agreement_px"] = round(float((dx ** 2 + dy ** 2) ** 0.5), 1)
            joint_report[name] = entry
        results_summary.append({"shot_index": shot_idx, "frame_index": frame_idx, "joints": joint_report})

        # --- Visualize both skeletons on the same frame ---
        vis = frame.copy()
        _draw_skeleton(vis, mp_points, (0, 255, 0), "MediaPipe (green)", 40)
        _draw_skeleton(vis, rf_points, (0, 0, 255), "RF-DETR Keypoint (red)", 70)
        out_path = OUT_DIR / f"shot{shot_idx}_release_f{frame_idx}.png"
        cv2.imwrite(str(out_path), vis)
        print(f"shot {shot_idx} (frame {frame_idx}): saved {out_path.name}")

    cap.release()
    mp_estimator.close()

    print(f"\nMediaPipe avg latency: {1000*sum(mp_times)/len(mp_times):.1f} ms/frame")
    print(f"RF-DETR Keypoint avg latency: {1000*sum(rf_times)/len(rf_times):.1f} ms/frame")

    (OUT_DIR / "comparison_report.json").write_text(json.dumps(results_summary, indent=2), encoding="utf-8")
    print(f"\nFull per-joint report saved to {OUT_DIR / 'comparison_report.json'}")


if __name__ == "__main__":
    main()
