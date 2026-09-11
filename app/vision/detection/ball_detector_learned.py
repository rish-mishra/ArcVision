"""
Learned basketball candidate detector using YOLO-World, prompted directly
as "basketball" rather than relying on COCO's generic "sports ball" class.

Why this exists: diagnosing a real video showed COCO-pretrained YOLOv8n
recalls this real basketball (held by the shooter, moderate camera
distance, partially occluded by the hand while gripped) in under 10% of
frames, even at increased inference resolution -- the ball's small,
partly-occluded appearance while held is a fundamentally hard case for a
generic small-object class trained mostly on more prominent balls
(soccer/tennis/etc. at closer range). The SAME frames prompted through
YOLO-World specifically as "basketball" recalled it in roughly 37% of
frames instead. Still imperfect on its own -- that imperfection is exactly
what app.tracking.kalman_tracker's gap-bridging and the shot state
machine's fallback trigger (app/events/shot_state_machine.py) exist to
absorb -- but a large enough improvement to use as a primary candidate
source rather than a rarely-firing supplement.

Kept in the same Detection format as the classical/COCO ball candidates
(app.vision.detection.ball_detector) so the orchestrator can simply pool
both sources before handing them to the tracker, and so this source can be
swapped for a future specialized/fine-tuned basketball model without
touching tracking or shot-analysis code.
"""
from __future__ import annotations

from typing import List

import numpy as np
import torch

from app.config import CONFIG, MODELS_DIR
from app.logging_config import get_logger
from app.vision.types import Detection

log = get_logger("vision.ball_learned")


class LearnedBallDetector:
    _instance = None

    def __init__(self):
        from ultralytics import YOLOWorld
        cfg = CONFIG.ball
        weights = MODELS_DIR / cfg.learned_model_name
        source = str(weights) if weights.exists() else cfg.learned_model_name
        self.device = 0 if torch.cuda.is_available() else "cpu"
        log.info("Loading YOLO-World open-vocabulary ball detector (%s) on device=%s",
                  cfg.learned_model_name, self.device)
        self.model = YOLOWorld(source)
        self.model.set_classes(list(cfg.learned_prompts))
        self._warmed = False

    @classmethod
    def get(cls) -> "LearnedBallDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def warmup(self) -> None:
        if self._warmed:
            return
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, device=self.device, verbose=False)
        self._warmed = True

    def detect(self, frame_bgr, frame_index: int, timestamp_sec: float) -> List[Detection]:
        cfg = CONFIG.ball
        h = frame_bgr.shape[0]
        results = self.model.predict(frame_bgr, device=self.device, verbose=False,
                                       conf=cfg.learned_confidence_floor)
        detections: List[Detection] = []
        if not results or results[0].boxes is None:
            return detections

        for box in results[0].boxes:
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            height = y2 - y1
            rel_size = height / float(h)
            if rel_size < cfg.min_relative_size or rel_size > cfg.max_relative_size:
                continue
            detections.append(Detection(frame_index, timestamp_sec, x1, y1, x2, y2, conf, "basketball_learned"))

        return detections
