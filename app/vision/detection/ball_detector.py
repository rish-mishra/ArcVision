"""
Refines raw "sports ball" candidate boxes (from the shared YOLO detector)
into basketball-specific candidates using color and shape validation.

Why this exists: COCO's "sports ball" class covers soccer balls, tennis
balls, etc., and a nano model at video-frame resolution will also
occasionally box a similarly round/orange object in the background (a
shoe, a warning sign, skin tone under some lighting). Cross-checking the
crop's dominant hue against basketball's characteristic burnt-orange and
its silhouette against a circle materially reduces false positives without
needing a custom-trained model.
"""
from __future__ import annotations

from typing import List

import cv2
import numpy as np

from app.config import CONFIG
from app.vision.types import Detection


def _circularity_score(crop_gray: np.ndarray) -> float:
    if crop_gray.size == 0:
        return 0.0
    blurred = cv2.GaussianBlur(crop_gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    perimeter = cv2.arcLength(largest, True)
    if perimeter < 1e-6:
        return 0.0
    circularity = 4 * np.pi * area / (perimeter ** 2)
    return float(min(1.0, circularity))


def _color_match_fraction(crop_bgr: np.ndarray) -> float:
    if crop_bgr.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    cfg = CONFIG.ball
    lower = np.array(cfg.hsv_lower_1, dtype=np.uint8)
    upper = np.array(cfg.hsv_upper_1, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    return float(np.count_nonzero(mask)) / float(mask.size)


def validate_ball_candidates(frame: np.ndarray, candidates: List[Detection]) -> List[Detection]:
    """
    Re-scores each candidate; drops ones that are clearly wrong size or
    have essentially no basketball-orange pixels and a non-round silhouette.
    Returns candidates sorted by adjusted confidence (best first).
    """
    cfg = CONFIG.ball
    h, w = frame.shape[:2]
    validated: List[Detection] = []

    for det in candidates:
        rel_size = det.height / float(h)
        if rel_size < cfg.min_relative_size or rel_size > cfg.max_relative_size:
            continue

        x1, y1, x2, y2 = (max(0, int(det.x1)), max(0, int(det.y1)),
                           min(w, int(det.x2)), min(h, int(det.y2)))
        if x2 <= x1 or y2 <= y1:
            continue
        crop = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        circularity = _circularity_score(gray)
        color_frac = _color_match_fraction(crop)

        shape_ok = circularity >= cfg.min_circularity
        color_ok = color_frac >= 0.12

        if not (shape_ok or color_ok):
            continue

        bonus = 0.15 * float(shape_ok) + 0.15 * float(color_ok)
        adjusted_conf = min(1.0, det.confidence + bonus)
        validated.append(Detection(det.frame_index, det.timestamp_sec, det.x1, det.y1,
                                     det.x2, det.y2, adjusted_conf, "basketball"))

    validated.sort(key=lambda d: d.confidence, reverse=True)
    return validated
