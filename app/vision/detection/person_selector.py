"""
Chooses the "primary shooter" among all person detections in a frame/video.
V1 assumes a single shooter is the subject of the session; when bystanders
or other players are visible, the primary shooter is identified as the
person with the largest, most temporally-consistent bounding box (a
bystander in the background will be smaller and often intermittent).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.vision.types import Detection


class PrimaryShooterSelector:
    def __init__(self, min_track_frames: int = 5):
        self.min_track_frames = min_track_frames
        self._area_history: Dict[int, List[float]] = {}
        self._last_box_by_slot: Dict[int, Detection] = {}

    def _assign_slot(self, det: Detection) -> int:
        """Greedy nearest-center matching against the last frame's boxes."""
        cx, cy = det.center
        best_slot, best_dist = None, float("inf")
        for slot, last in self._last_box_by_slot.items():
            lcx, lcy = last.center
            d = ((cx - lcx) ** 2 + (cy - lcy) ** 2) ** 0.5
            if d < best_dist:
                best_dist, best_slot = d, slot
        if best_slot is not None and best_dist < max(det.width, det.height) * 1.5:
            return best_slot
        return max(self._last_box_by_slot.keys(), default=-1) + 1

    def select(self, persons: List[Detection]) -> Optional[Detection]:
        if not persons:
            return None
        for det in persons:
            slot = self._assign_slot(det)
            self._last_box_by_slot[slot] = det
            self._area_history.setdefault(slot, []).append(det.width * det.height)

        # Pick the slot with the largest recent mean area among currently-present detections.
        present_slots = set()
        for det in persons:
            for slot, last in self._last_box_by_slot.items():
                if last is det:
                    present_slots.add(slot)
                    break

        best_slot, best_score = None, -1.0
        for slot in present_slots:
            hist = self._area_history.get(slot, [])
            recent = hist[-30:]
            score = sum(recent) / len(recent) if recent else 0.0
            if score > best_score:
                best_score, best_slot = score, slot

        return self._last_box_by_slot.get(best_slot) if best_slot is not None else max(
            persons, key=lambda d: d.width * d.height
        )
