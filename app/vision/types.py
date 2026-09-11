"""
Shared data contracts used across the vision, tracking, events, and
biomechanics layers. Keeping these in one place is what lets the ball
detector, hoop detector, or pose estimator be swapped out later without
touching downstream analysis code.

Coordinate conventions (documented once, relied on everywhere):
  * All pixel coordinates (`*_px`) are in the ANALYSIS resolution frame
    (see VideoConfig.analysis_max_dim), origin top-left, x right, y down.
  * All normalized pose coordinates are in [0, 1] relative to the analysis
    frame width/height, as produced by MediaPipe.
  * "Body-normalized" quantities (used for cross-shot comparison) are
    expressed as a fraction of the shooter's torso length for that frame,
    which cancels out camera distance/zoom differences reasonably well for
    a mostly-stationary phone camera. This is explicitly NOT a physical
    (meter-based) measurement -- see docs/METHODOLOGY.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DataSource(str, Enum):
    """Provenance of a measurement -- never let downstream code conflate these."""
    DETECTED = "detected"          # directly observed by a detector this frame
    INTERPOLATED = "interpolated"  # bridged across a short detector gap
    PREDICTED = "predicted"        # extrapolated by the tracker's motion model
    UNAVAILABLE = "unavailable"    # no defensible value; must not be used as fact


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EXCLUDED = "excluded"

    @staticmethod
    def from_score(score: float, high: float = 0.75, medium: float = 0.5) -> "Confidence":
        if score >= high:
            return Confidence.HIGH
        if score >= medium:
            return Confidence.MEDIUM
        if score > 0:
            return Confidence.LOW
        return Confidence.EXCLUDED


POSE_LANDMARK_NAMES = (
    "nose",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)


@dataclass
class Landmark:
    x: float  # normalized [0,1]
    y: float  # normalized [0,1]
    z: float  # normalized, relative depth (MediaPipe convention, not metric)
    visibility: float  # [0,1] model-reported confidence this landmark is visible


@dataclass
class PoseFrame:
    frame_index: int
    timestamp_sec: float
    detected: bool
    landmarks: dict = field(default_factory=dict)  # name -> Landmark
    pose_confidence: float = 0.0  # mean visibility over the core joints used
    shooting_side: Optional[str] = None  # "left" | "right" | None if undetermined
    smoothed: bool = False

    def landmark(self, name: str) -> Optional[Landmark]:
        return self.landmarks.get(name)

    def has_all(self, names) -> bool:
        return all(
            n in self.landmarks and self.landmarks[n].visibility >= 0.0
            for n in names
        )


@dataclass
class Detection:
    frame_index: int
    timestamp_sec: float
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_name: str

    @property
    def center(self):
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclass
class BallObservation:
    frame_index: int
    timestamp_sec: float
    center_x: float
    center_y: float
    radius_px: float
    confidence: float
    source: DataSource
    track_id: Optional[int] = None


@dataclass
class HoopLocation:
    """A single, video-level hoop location (camera assumed mostly static)."""
    rim_center_x: float
    rim_center_y: float
    rim_radius_px: float
    confidence: float
    votes: int
    method: str  # "hough_color" | "manual"
    backboard_bbox: Optional[tuple] = None

    @property
    def rim_top_y(self) -> float:
        return self.rim_center_y - self.rim_radius_px * 0.35

    @property
    def rim_bottom_y(self) -> float:
        return self.rim_center_y + self.rim_radius_px * 0.35
