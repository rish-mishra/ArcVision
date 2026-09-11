"""
Classical computer-vision hoop/rim detector.

COCO-pretrained detectors have no rim/hoop class, and pulling in a random
community-trained weights file from the internet is both a license-
provenance risk and unavailable in an offline environment, so V1 uses a
deterministic, inspectable classical-CV approach instead of faking a
location:

  1. Restrict the search to the upper portion of the frame (rims are
     elevated) and mask for the rim's characteristic orange color.
  2. Find candidate circles both from contours on that mask and from a
     Hough circle transform on the masked grayscale image.
  3. Because the camera is assumed mostly static for the whole clip, run
     this over a sample of frames spread across the video and aggregate
     (app.tracking.hoop_aggregator) -- a rim that is found in roughly the
     same place across many frames is trustworthy; a one-off detection is
     not.

This module's output feeds a replaceable interface: if a fine-tuned
hoop-detection model is added later, it only needs to produce the same
per-frame candidate list consumed by the aggregator.
"""
from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from app.config import CONFIG

Candidate = Tuple[float, float, float, float]  # x, y, radius, confidence


def _orange_mask(frame_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    cfg = CONFIG.ball  # rim color range overlaps the ball's orange
    lower = np.array(cfg.hsv_lower_1, dtype=np.uint8)
    upper = np.array(cfg.hsv_upper_1, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def detect_hoop_candidates(frame_bgr: np.ndarray) -> List[Candidate]:
    cfg = CONFIG.hoop
    h, w = frame_bgr.shape[:2]
    search_h = int(h * 0.75)  # rim is rarely in the bottom quarter of frame
    roi = frame_bgr[:search_h, :]

    mask = _orange_mask(roi)
    candidates: List[Candidate] = []

    min_r = cfg.hough_min_radius_frac * h
    max_r = cfg.hough_max_radius_frac * h

    # Contour-based candidates from the color mask.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        area = cv2.contourArea(c)
        if area < 20:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(c)
        if not (min_r <= r <= max_r):
            continue
        perimeter = cv2.arcLength(c, True)
        if perimeter < 1e-6:
            continue
        circularity = 4 * np.pi * area / (perimeter ** 2)
        if circularity < 0.35:  # rims are often partial ellipses due to perspective
            continue
        conf = float(min(1.0, circularity))
        candidates.append((float(cx), float(cy), float(r), conf))

    # Hough-circle candidates on the masked, blurred grayscale for redundancy.
    gray_masked = cv2.bitwise_and(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), mask=mask)
    blurred = cv2.medianBlur(gray_masked, 5)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=cfg.hough_dp,
        minDist=cfg.hough_min_dist_frac * h,
        param1=cfg.hough_param1, param2=cfg.hough_param2,
        minRadius=int(min_r), maxRadius=int(max_r),
    )
    if circles is not None:
        for x, y, r in circles[0]:
            candidates.append((float(x), float(y), float(r), 0.5))

    return candidates
