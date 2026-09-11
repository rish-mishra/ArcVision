"""
Single shared YOLOv8n (COCO-pretrained) inference pass per frame, used as
the base detector for both the primary-shooter person box and basketball
candidate boxes. Running one model once per frame (instead of two separate
detector instances) keeps inference cost down.

COCO has no "basketball" or "hoop/rim" class, so:
  * "person" (class 0) is used directly for shooter localization.
  * "sports ball" (class 32) is used as a *candidate* basketball detector;
    app.vision.detection.ball_detector applies color/circularity/size
    validation on top of it, since a generic sports-ball detector alone
    will also fire on similarly shaped/colored background objects.

This is a documented, acknowledged limitation (see docs/METHODOLOGY.md and
README "Known Limitations"). The interface below is what a future
fine-tuned basketball/hoop-specific model would plug into instead.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import torch

from app.config import CONFIG, MODELS_DIR
from app.logging_config import get_logger
from app.vision.types import Detection

log = get_logger("vision.yolo")

_PERSON_CLASS = 0
_SPORTS_BALL_CLASS = 32


class YoloMultiDetector:
    _instance = None

    def __init__(self):
        from ultralytics import YOLO
        weights = MODELS_DIR / CONFIG.ball.model_name
        if not weights.exists():
            weights = CONFIG.ball.model_name  # let ultralytics auto-download
        self.device = 0 if torch.cuda.is_available() else "cpu"
        log.info("Loading YOLOv8n detector on device=%s", self.device)
        self.model = YOLO(str(weights))
        self._warmed = False

    @classmethod
    def get(cls) -> "YoloMultiDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def warmup(self):
        if self._warmed:
            return
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, device=self.device, verbose=False)
        self._warmed = True

    def detect(self, frame: np.ndarray, frame_index: int,
               timestamp_sec: float) -> Dict[str, List[Detection]]:
        results = self.model.predict(
            frame, device=self.device, verbose=False,
            conf=min(CONFIG.person.confidence_threshold, CONFIG.ball.confidence_threshold),
            classes=[_PERSON_CLASS, _SPORTS_BALL_CLASS],
        )
        persons: List[Detection] = []
        balls: List[Detection] = []
        if not results:
            return {"person": persons, "ball_candidate": balls}

        r = results[0]
        if r.boxes is None:
            return {"person": persons, "ball_candidate": balls}

        for box in r.boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            if cls_id == _PERSON_CLASS and conf >= CONFIG.person.confidence_threshold:
                persons.append(Detection(frame_index, timestamp_sec, x1, y1, x2, y2, conf, "person"))
            elif cls_id == _SPORTS_BALL_CLASS and conf >= CONFIG.ball.confidence_threshold:
                balls.append(Detection(frame_index, timestamp_sec, x1, y1, x2, y2, conf, "sports_ball"))

        return {"person": persons, "ball_candidate": balls}
