"""
SHADOW-ONLY research module. Not imported by production (app/pipeline,
app/events, app/api, or anything reachable from run_pipeline()). See
docs/NET_MOTION_SHADOW.md.

Extracts interpretable, DIAGNOSTIC (not verdict) temporal-visual-change
evidence from a short rim-centered frame sequence, per
docs/OUTCOME_NEXT_REPRESENTATION_DECISION.md's Option D: the trajectory-only
outcome architecture is closed for the core ambiguous rim-interaction
problem (see docs/POST_CONTACT_REVERSAL_SHADOW.md Part 4); the new
information source under test here is TEMPORAL VISUAL CHANGE around the
rim/net, deliberately not yet turned into a MADE/MISSED decision rule.

Representation, deliberately the simplest deterministic one justified by
the task at hand (no optical flow, no learned model): per consecutive
grayscale frame pair, mean ABSOLUTE PIXEL DIFFERENCE within a rim-relative
NET ROI (a region below the rim, sized from the existing rim radius),
compared against the SAME measure in two CONTROL ROIs of identical size
placed immediately beside the net ROI at the same vertical band -- this is
what makes the signal a RELATIVE (net-motion / local-background-motion)
ratio rather than a raw magnitude, so uniform brightness changes, camera
shake, and background motion (which affect the net ROI and its immediate
neighbors roughly equally) are naturally suppressed without any fitted
threshold: the "no differential motion" baseline is exactly ratio == 1,
not a chosen number.

Ball contamination is handled by masking out a circular region at the
ball's own tracked position (when available for a given frame) before
computing the net ROI's mean difference, so a ball passing through/near the
net ROI does not itself register as net/structure motion.

Exactly two new numeric constants are introduced in this whole module,
both fixed by physical reasoning BEFORE any real-video evaluation and never
adjusted afterward (see docs/NET_MOTION_SHADOW.md for the full accounting):

- NET_ROI_VERTICAL_SPAN_RIM_RADII = 2.0: how far below the rim the net ROI
  extends, in rim radii. A net's visible drop is commonly on the order of
  the rim's own diameter; this is a round, physically-motivated multiple of
  the EXISTING rim_radius_px, not a value selected by checking which one
  makes any specific labeled shot separate correctly.
- BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS = 0.5: regulation basketball radius
  (~4.7 in) is roughly half a regulation rim's radius (~9 in) -- real
  equipment proportions, not a fitted value. Used ONLY as a fallback when no
  real per-frame ball radius is available; wherever a real, DETECTED radius
  exists it is used directly instead (see `BallSample.radius_px`/`.source`).

Every other quantity in this module is either a direct pixel measurement, a
structural (zero-parameter) comparison, or numerical-safety epsilon.

--- Part 2 addition (docs/NET_MOTION_SHADOW.md Part 2: controlled
measurement) --- adds SHOOTER masking, reusing existing per-frame
person/pose bounding-box geometry the pipeline already computes (see
`PersonSample`), and upgrades ball masking to track whether each frame's
ball sample was a real DETECTED observation, an INTERPOLATED bridge, or
simply absent (`BallSample.source`) -- interpolated/missing samples are
never treated as equivalent evidence to a real detection; both the net ROI
and BOTH control ROIs are now masked identically for ball and person, since
either can contaminate any of the three regions. No new numeric constant
was introduced for this addition -- person exclusion uses the detector's
own reported bounding box directly, with no added margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.config import CONFIG
from app.vision.types import HoopLocation

NET_ROI_VERTICAL_SPAN_RIM_RADII = 2.0
BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS = 0.5
_EPS = 1e-6


@dataclass
class BallSample:
    """One frame's ball position, for masking only -- not the full
    BallObservation type, so this module has no dependency on tracker
    internals beyond what it actually needs."""
    frame_index: int
    center_x: float
    center_y: float
    radius_px: Optional[float] = None  # if None, BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS is used
    source: str = "detected"  # "detected" | "interpolated" -- never treated as equally reliable


@dataclass
class PersonSample:
    """One frame's shooter/person bounding box (pixel coords), for masking
    only. Reuses whatever the pipeline's own person detector already
    reports -- no added margin, no new constant."""
    frame_index: int
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Roi:
    x0: int
    y0: int
    x1: int
    y1: int

    def clip(self, w: int, h: int) -> "Roi":
        return Roi(max(0, self.x0), max(0, self.y0), min(w, self.x1), min(h, self.y1))

    def valid(self) -> bool:
        return self.x1 > self.x0 and self.y1 > self.y0

    def slice(self, arr: np.ndarray) -> np.ndarray:
        return arr[self.y0:self.y1, self.x0:self.x1]


@dataclass
class NetMotionEpisode:
    reason: str
    quality: str  # "insufficient" | "measured"

    net_roi: Optional[Roi] = None
    control_roi_left: Optional[Roi] = None
    control_roi_right: Optional[Roi] = None

    frame_indices_used: List[int] = field(default_factory=list)
    net_motion_series: List[float] = field(default_factory=list)
    control_motion_series: List[float] = field(default_factory=list)
    relative_motion_series: List[float] = field(default_factory=list)  # net / control per pair
    ball_masked_fraction_series: List[float] = field(default_factory=list)  # fraction of net ROI excluded by the ball mask, per pair

    n_frame_pairs: int = 0
    n_elevated_pairs: int = 0  # relative_motion > 1.0 -- structural (zero-parameter), NOT a fitted cutoff
    max_relative_motion: float = 0.0
    mean_relative_motion: float = 0.0

    # Part 2 additions -- masking completeness/provenance, per pair.
    person_mask_available_series: List[bool] = field(default_factory=list)
    ball_mask_source_series: List[str] = field(default_factory=list)  # "detected" | "interpolated" | "none"
    n_fully_clean_pairs: int = 0  # person geometry available AND ball source == "detected" (or "none", i.e. genuinely absent)

    evidence: dict = field(default_factory=dict)


def _rois(hoop: HoopLocation) -> tuple:
    r = hoop.rim_radius_px
    half_w = r * CONFIG.outcome.horizontal_margin_frac_of_rim_radius  # existing config, zero ball-radius term (module-level, not per-frame)
    y0 = int(round(hoop.rim_bottom_y))
    y1 = int(round(hoop.rim_bottom_y + NET_ROI_VERTICAL_SPAN_RIM_RADII * r))
    net = Roi(int(round(hoop.rim_center_x - half_w)), y0, int(round(hoop.rim_center_x + half_w)), y1)
    width = net.x1 - net.x0
    gap = width  # controls placed immediately adjacent, non-overlapping -- a structural placement rule, not a fitted offset
    left = Roi(net.x0 - gap - width, y0, net.x0 - gap, y1)
    right = Roi(net.x1 + gap, y0, net.x1 + gap + width, y1)
    return net, left, right


def _ball_mask(shape: tuple, roi: Roi, ball: Optional[BallSample], hoop: HoopLocation) -> np.ndarray:
    """True where NOT the ball (pixels to KEEP). All-True if no ball sample
    for this frame. Preserved for Part 1 backward compatibility."""
    mask = np.ones((roi.y1 - roi.y0, roi.x1 - roi.x0), dtype=bool)
    if ball is None:
        return mask
    radius = ball.radius_px if ball.radius_px is not None else hoop.rim_radius_px * BALL_MASK_RADIUS_FRAC_OF_RIM_RADIUS
    yy, xx = np.mgrid[roi.y0:roi.y1, roi.x0:roi.x1]
    dist2 = (xx - ball.center_x) ** 2 + (yy - ball.center_y) ** 2
    mask &= dist2 > radius ** 2
    return mask


def _person_mask(roi: Roi, person: Optional[PersonSample]) -> np.ndarray:
    """True where NOT the shooter/person (pixels to KEEP). All-True if no
    person sample for this frame -- callers must separately track that as
    reduced masking completeness, never silently treat it as clean."""
    mask = np.ones((roi.y1 - roi.y0, roi.x1 - roi.x0), dtype=bool)
    if person is None:
        return mask
    yy, xx = np.mgrid[roi.y0:roi.y1, roi.x0:roi.x1]
    inside_person = (xx >= person.x1) & (xx <= person.x2) & (yy >= person.y1) & (yy <= person.y2)
    mask &= ~inside_person
    return mask


def analyze_net_motion_from_frames(gray_frames: List[np.ndarray], frame_indices: List[int],
                                     hoop: Optional[HoopLocation],
                                     ball_by_frame: Optional[Dict[int, BallSample]] = None,
                                     person_by_frame: Optional[Dict[int, PersonSample]] = None,
                                     cfg=None) -> NetMotionEpisode:
    """Pure, video-I/O-free core: given already-decoded grayscale frames
    (same size, in ascending frame_index order) and existing rim geometry,
    measure relative net-region motion per consecutive frame pair. No
    verdict is produced -- see module docstring. `person_by_frame` is the
    Part 2 addition: when provided, shooter/person pixels are excluded from
    ALL THREE regions (net + both controls), and masking completeness is
    tracked per pair rather than silently assumed."""
    cfg = cfg or CONFIG.outcome
    ball_by_frame = ball_by_frame or {}
    person_by_frame = person_by_frame or {}

    if hoop is None or hoop.confidence < cfg.min_hoop_confidence_to_attempt:
        return NetMotionEpisode("hoop_location_not_reliable", "insufficient")
    if len(gray_frames) != len(frame_indices):
        return NetMotionEpisode("frame_index_mismatch", "insufficient")
    if len(gray_frames) < 2:
        return NetMotionEpisode("insufficient_frames", "insufficient")

    h, w = gray_frames[0].shape[:2]
    net, left, right = _rois(hoop)
    net, left, right = net.clip(w, h), left.clip(w, h), right.clip(w, h)
    if not net.valid():
        return NetMotionEpisode("net_roi_outside_frame", "insufficient")

    ep = NetMotionEpisode("", "insufficient", net_roi=net, control_roi_left=left, control_roi_right=right)

    def _region_motion(roi: Roi, diff: np.ndarray, ball: Optional[BallSample], person: Optional[PersonSample]):
        if not roi.valid():
            return None, 0.0
        combined = _ball_mask((h, w), roi, ball, hoop) & _person_mask(roi, person)
        region_diff = roi.slice(diff)
        masked_frac = 1.0 - (combined.sum() / combined.size) if combined.size else 0.0
        motion = float(region_diff[combined].mean()) if combined.any() else 0.0
        return motion, masked_frac

    for i in range(1, len(gray_frames)):
        prev, cur = gray_frames[i - 1].astype(np.float32), gray_frames[i].astype(np.float32)
        diff = np.abs(cur - prev)
        fi = frame_indices[i]
        fi_prev = frame_indices[i - 1]

        ball = ball_by_frame.get(fi) or ball_by_frame.get(fi_prev)
        person = person_by_frame.get(fi) or person_by_frame.get(fi_prev)

        net_motion, net_masked_frac = _region_motion(net, diff, ball, person)
        left_motion, _ = _region_motion(left, diff, ball, person)
        right_motion, _ = _region_motion(right, diff, ball, person)
        control_vals = [v for v in (left_motion, right_motion) if v is not None]
        control_motion = float(np.mean(control_vals)) if control_vals else 0.0

        relative = (net_motion or 0.0) / max(control_motion, _EPS)

        ball_source = "none" if ball is None else ball.source
        person_available = person is not None

        ep.frame_indices_used.append(fi)
        ep.net_motion_series.append(round(net_motion or 0.0, 4))
        ep.control_motion_series.append(round(control_motion, 4))
        ep.relative_motion_series.append(round(relative, 4))
        ep.ball_masked_fraction_series.append(round(net_masked_frac, 4))
        ep.person_mask_available_series.append(person_available)
        ep.ball_mask_source_series.append(ball_source)

    ep.n_frame_pairs = len(ep.relative_motion_series)
    if ep.n_frame_pairs == 0:
        ep.reason = "no_valid_control_region"
        return ep

    ep.n_elevated_pairs = sum(1 for r in ep.relative_motion_series if r > 1.0)
    ep.max_relative_motion = max(ep.relative_motion_series)
    ep.mean_relative_motion = round(float(np.mean(ep.relative_motion_series)), 4)
    ep.n_fully_clean_pairs = sum(
        1 for avail, src in zip(ep.person_mask_available_series, ep.ball_mask_source_series)
        if avail and src in ("detected", "none")
    )
    ep.quality = "measured"
    ep.reason = "net_motion_measured"
    return ep
