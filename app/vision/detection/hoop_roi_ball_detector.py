"""
Targeted, high-resolution secondary ball detector scoped to a region
around the (already-localized) hoop.

Why this exists: the global ball detector (COCO YOLOv8n + YOLO-World
"basketball", see ball_detector.py / ball_detector_learned.py) recalls the
ball reasonably well in open flight near the shooter, but on a real video
its tracked trajectory never got closer than several hundred pixels to the
hoop for ANY of seven real shots -- the ball simply wasn't detected during
the few hundred milliseconds it takes to cross the rim's vicinity. That
gap is exactly the evidence make/miss detection needs most.

The hoop's location is known and the camera is static for the whole
session, so instead of asking a generic detector to find a small, often
motion-blurred ball anywhere in a 960x540 frame, this crops a modest
region around the hoop and upscales it before re-running detection --
the same object occupies far more pixels, which is what actually helps
small-object recall (confirmed empirically: this is the same principle
that made prompting YOLO-World directly as "basketball" instead of relying
on generic recall pay off elsewhere in this pipeline). Kept as a SEPARATE,
opt-in pass over each shot's flight window only (not the whole video) so
it cannot affect shot segmentation's already-validated ball tracking.
"""
from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np
import torch

from app.config import CONFIG, MODELS_DIR
from app.logging_config import get_logger
from app.vision.detection.ball_detector import _circularity_score, _color_match_fraction
from app.vision.types import Detection, HoopLocation

log = get_logger("vision.hoop_roi_ball")


def _compute_roi(hoop: HoopLocation, frame_w: int, frame_h: int, margin_factor: float) -> Tuple[int, int, int, int]:
    """Square-ish ROI centered on the hoop, generously margined so the
    approach/departure trajectory is captured too, clipped to the frame."""
    half = hoop.rim_radius_px * margin_factor
    x1 = max(0, int(hoop.rim_center_x - half))
    x2 = min(frame_w, int(hoop.rim_center_x + half))
    y1 = max(0, int(hoop.rim_center_y - half * 1.3))  # a bit more room above (approach from above)
    y2 = min(frame_h, int(hoop.rim_center_y + half))
    return x1, y1, x2, y2


class HoopROIBallDetector:
    """
    Not a singleton like the global detectors -- constructed once per
    video with that video's hoop location, reusing the same underlying
    YOLO-World model instance as the global learned ball detector (set to
    a different, ball-specific prompt already) so this doesn't cost a
    second model load.
    """

    def __init__(self, hoop: HoopLocation, frame_w: int, frame_h: int, upscale: float = 4.0,
                  margin_factor: float = 5.0):
        self.hoop = hoop
        self.roi = _compute_roi(hoop, frame_w, frame_h, margin_factor)
        self.upscale = upscale
        self.frame_w, self.frame_h = frame_w, frame_h

        from ultralytics import YOLOWorld
        cfg = CONFIG.ball
        weights = MODELS_DIR / cfg.learned_model_name
        source = str(weights) if weights.exists() else cfg.learned_model_name
        self.device = 0 if torch.cuda.is_available() else "cpu"
        self.model = YOLOWorld(source)
        self.model.set_classes(["basketball"])
        self._warmed = False

    def warmup(self) -> None:
        if self._warmed:
            return
        dummy = np.zeros((256, 256, 3), dtype=np.uint8)
        self.model.predict(dummy, device=self.device, verbose=False)
        self._warmed = True

    def detect(self, frame_bgr: np.ndarray, frame_index: int, timestamp_sec: float) -> List[Detection]:
        x1, y1, x2, y2 = self.roi
        if x2 <= x1 or y2 <= y1:
            return []
        crop = frame_bgr[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        if ch < 4 or cw < 4:
            return []
        upscaled = cv2.resize(crop, (int(cw * self.upscale), int(ch * self.upscale)),
                                interpolation=cv2.INTER_CUBIC)

        detections: List[Detection] = []

        # --- Learned (semantic) pass on the upscaled crop ---
        results = self.model.predict(upscaled, device=self.device, verbose=False,
                                       conf=CONFIG.ball.learned_confidence_floor)
        if results and results[0].boxes is not None:
            for box in results[0].boxes:
                conf = float(box.conf.item())
                bx1, by1, bx2, by2 = [float(v) for v in box.xyxy[0].tolist()]
                # Map back: upscaled-crop coords -> crop coords -> full-frame coords.
                fx1 = x1 + bx1 / self.upscale
                fy1 = y1 + by1 / self.upscale
                fx2 = x1 + bx2 / self.upscale
                fy2 = y1 + by2 / self.upscale
                detections.append(Detection(frame_index, timestamp_sec, fx1, fy1, fx2, fy2, conf, "hoop_roi_learned"))

        # --- Classical color/circularity pass on the same upscaled crop,
        # as supplementary (lower-trust) evidence only. A rim/net/backboard
        # filled ROI has plenty of clutter, so this alone would be noisy --
        # it is never the only source consumed downstream (the rim
        # interaction analysis discounts single-source, low-confidence
        # candidates -- see events/outcome_detector.py). ---
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area < 30:
                continue
            (ccx, ccy), r = cv2.minEnclosingCircle(c)
            if r < 3 or r > min(upscaled.shape[:2]) * 0.4:
                continue
            bx1, by1, bx2, by2 = ccx - r, ccy - r, ccx + r, ccy + r
            sub = upscaled[max(0, int(by1)):int(by2), max(0, int(bx1)):int(bx2)]
            if sub.size == 0:
                continue
            circularity = _circularity_score(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY))
            color_frac = _color_match_fraction(sub)
            if circularity < 0.5 and color_frac < 0.1:
                continue
            conf = 0.15 + 0.1 * float(circularity >= 0.5) + 0.1 * float(color_frac >= 0.1)
            fx1 = x1 + bx1 / self.upscale
            fy1 = y1 + by1 / self.upscale
            fx2 = x1 + bx2 / self.upscale
            fy2 = y1 + by2 / self.upscale
            detections.append(Detection(frame_index, timestamp_sec, fx1, fy1, fx2, fy2, conf, "hoop_roi_classical"))

        return detections
