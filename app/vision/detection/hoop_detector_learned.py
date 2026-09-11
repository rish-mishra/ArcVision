"""
Learned, semantic hoop/rim/backboard candidate detector using YOLO-World
(open-vocabulary object detection), added as a second candidate SOURCE
alongside the classical color-based detector (hoop_detector.py).

Why this exists: the classical detector assumes a bright-orange rim, which
is a real assumption that real hoops violate. Diagnosing a real backyard
video (`real_test_01`) showed a dark gray/weathered metal rim against a
bright overcast sky and a clear glass backboard -- the orange color mask
found literally zero matching pixels across the entire ~52s session, so
the classical detector had nothing to aggregate. YOLO-World recognizes
"basketball hoop / rim / backboard / net" as visual concepts rather than a
specific color, and correctly (if not confidently) located the true rim in
that footage.

A single zero-shot detection is NOT trustworthy on its own -- confidences
here are commonly 0.01-0.15 even on a correct box, because this is a
general-purpose open-vocabulary model, not one specialized for basketball
hoops. The candidates this module returns are meant to be pooled with the
classical detector's candidates and passed through the SAME cross-frame
temporal aggregation (app.tracking.hoop_aggregator) that already exists:
a location proposed consistently across many sampled frames earns real
confidence; a one-off low-confidence box elsewhere does not.

Kept in a strictly interchangeable Candidate format (x, y, radius,
confidence) with the classical detector so either source -- or a future
specialized/fine-tuned hoop model -- can be added, removed, or swapped
without touching the aggregator or orchestrator logic beyond which
detectors are called.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import torch

from app.config import CONFIG, MODELS_DIR
from app.logging_config import get_logger

log = get_logger("vision.hoop_learned")

Candidate = Tuple[float, float, float, float]  # x, y, radius, confidence


class LearnedHoopDetector:
    _instance = None

    def __init__(self):
        from ultralytics import YOLOWorld
        cfg = CONFIG.hoop
        weights = MODELS_DIR / cfg.learned_model_name
        source = str(weights) if weights.exists() else cfg.learned_model_name
        self.device = 0 if torch.cuda.is_available() else "cpu"
        log.info("Loading YOLO-World open-vocabulary hoop detector (%s) on device=%s",
                  cfg.learned_model_name, self.device)
        self.model = YOLOWorld(source)
        self.model.set_classes(list(cfg.learned_prompts))
        self._warmed = False

    @classmethod
    def get(cls) -> "LearnedHoopDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def warmup(self) -> None:
        if self._warmed:
            return
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, device=self.device, verbose=False)
        self._warmed = True

    def detect(self, frame_bgr: np.ndarray) -> List[Candidate]:
        cfg = CONFIG.hoop
        results = self.model.predict(frame_bgr, device=self.device, verbose=False,
                                       conf=cfg.learned_confidence_floor)
        candidates: List[Candidate] = []
        if not results or results[0].boxes is None:
            return candidates

        for box in results[0].boxes:
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            w, h = x2 - x1, y2 - y1
            if w <= 1 or h <= 1:
                continue
            cx = (x1 + x2) / 2.0
            # A box for "basketball hoop"/"basketball backboard" often
            # spans the backboard as well as the rim, so the rim itself
            # sits in the lower portion of the box; a "basketball rim"/
            # "basketball net" box is already tight around the rim, where
            # this shifts the estimate only slightly. This is a generic
            # geometric prior (rim-below-backboard), not a per-video tune.
            cy = y1 + 0.6 * h
            radius = max(w, h) / 2.0
            candidates.append((cx, cy, radius, conf))
        return candidates
