"""
Basketball-specific BALL/RIM detector fine-tuned from RF-DETR-Small on the
University of Arizona "Basketball Shooting Robot" dataset (Roboflow
Universe, CC BY 4.0) -- see docs/METHODOLOGY.md "Detector architecture"
for the full training/benchmarking story and scripts/train_ball_rim_detector.py
for how the checkpoint this loads was produced.

Unlike the existing detectors, one RF-DETR forward pass yields BOTH classes
at once (it was trained specifically for this task, not adapted from a
generic detector), so this module exposes a single `predict_raw()` plus
two cheap extraction helpers -- callers that need both ball and rim
evidence from the same frame (the production pipeline, once benchmarking
justifies using this as a real source) only pay for one inference call.

Kept in the same `Detection` / `(x, y, radius, confidence)` candidate
formats as every other detector in this package specifically so it can be
pooled alongside (or eventually instead of) the existing YOLOv8/YOLO-World/
classical-CV sources without any downstream code (BallTracker,
aggregate_hoop_candidates, shot segmentation, outcome detection) needing to
change -- see app/pipeline/orchestrator.py for where sources are pooled.

This module intentionally has NO fallback to a stock/COCO-pretrained
RF-DETR checkpoint: without the fine-tuned weights, RF-DETR has no
"ball"/"rim" classes to predict at all (they aren't COCO categories), so a
missing checkpoint is a hard configuration error, not a case to silently
degrade from.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.logging_config import get_logger
from app.vision.types import Detection

log = get_logger("vision.ball_rim_rfdetr")

Candidate = Tuple[float, float, float, float]  # x, y, radius, confidence

# RF-DETR re-indexes categories to a 0-based internal class list at
# training time regardless of the COCO category "id" values used to
# prepare the dataset (scripts/prepare_ball_rim_dataset.py used id=1 for
# "ball", id=2 for "rim" -- COCO convention) -- confirmed empirically
# against the trained checkpoint's own `class_names` attribute (['ball',
# 'rim']) and its actual `.predict()` class_id outputs (0/1, not 1/2).
# Do not "fix" this back to a 1-based mapping without re-verifying against
# a real checkpoint; it will silently swap ball and rim detections.
CLASS_ID_TO_NAME = {0: "ball", 1: "rim"}


class RFDETRBallRimDetector:
    _instance: Optional["RFDETRBallRimDetector"] = None

    def __init__(self, checkpoint_path: str, confidence_floor: float = 0.3):
        if not Path(checkpoint_path).exists():
            raise FileNotFoundError(
                f"RF-DETR ball/rim checkpoint not found at {checkpoint_path}. This detector has no "
                "generic fallback -- 'ball'/'rim' aren't COCO classes, so a stock RF-DETR checkpoint "
                "cannot substitute. Train one first (scripts/train_ball_rim_detector.py) or point "
                "checkpoint_path at an existing one."
            )
        from rfdetr import RFDETRSmall
        self.confidence_floor = confidence_floor
        log.info("Loading fine-tuned RF-DETR ball/rim detector from %s", checkpoint_path)
        self.model = RFDETRSmall(pretrain_weights=checkpoint_path)
        self._warmed = False

    @classmethod
    def get(cls, checkpoint_path: str) -> "RFDETRBallRimDetector":
        if cls._instance is None:
            cls._instance = cls(checkpoint_path)
        return cls._instance

    def warmup(self) -> None:
        if self._warmed:
            return
        dummy = np.zeros((512, 512, 3), dtype=np.uint8)
        self.model.predict(dummy, threshold=self.confidence_floor)
        self._warmed = True

    def predict_raw(self, frame_bgr: np.ndarray):
        """Returns the raw supervision.Detections result -- one RF-DETR
        forward pass covering both classes. frame_bgr is converted to RGB
        (RF-DETR/the underlying vision transformer expects RGB, matching
        how it was trained) before inference."""
        # .copy() is required, not cosmetic: the [::-1] channel-reversal view
        # has a negative stride, which torchvision's to_tensor() cannot
        # convert (confirmed: raises ValueError without it).
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        return self.model.predict(rgb, threshold=self.confidence_floor)

    def extract_ball_detections(self, raw, frame_index: int, timestamp_sec: float) -> List[Detection]:
        detections: List[Detection] = []
        if raw is None or len(raw.xyxy) == 0:
            return detections
        for i in range(len(raw.xyxy)):
            if CLASS_ID_TO_NAME.get(int(raw.class_id[i])) != "ball":
                continue
            x1, y1, x2, y2 = [float(v) for v in raw.xyxy[i]]
            conf = float(raw.confidence[i])
            detections.append(Detection(frame_index, timestamp_sec, x1, y1, x2, y2, conf, "ball_rfdetr"))
        return detections

    def extract_rim_candidates(self, raw) -> List[Candidate]:
        candidates: List[Candidate] = []
        if raw is None or len(raw.xyxy) == 0:
            return candidates
        for i in range(len(raw.xyxy)):
            if CLASS_ID_TO_NAME.get(int(raw.class_id[i])) != "rim":
                continue
            x1, y1, x2, y2 = [float(v) for v in raw.xyxy[i]]
            conf = float(raw.confidence[i])
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            radius = max(x2 - x1, y2 - y1) / 2.0
            candidates.append((cx, cy, radius, conf))
        return candidates
