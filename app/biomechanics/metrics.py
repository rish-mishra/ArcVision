"""
Computes per-shot biomechanical measurements from pose landmarks, the shot
window boundaries, and the release estimate. All measurements are either
joint angles (degrees, well-defined regardless of camera distance) or
body-relative distances normalized by the shooter's own torso length for
that frame (see app.vision.types module docstring on coordinate
conventions) -- never a fabricated physical unit.

Any measurement that cannot be computed (missing/low-confidence landmarks)
is returned as None with the reason recorded in `warnings`, rather than
guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.biomechanics.geometry import (
    elbow_angle, knee_angle, midpoint, torso_lean_deg, torso_length,
    normalize_by_torso,
)
from app.vision.types import PoseFrame

_VIS_MIN = 0.4


@dataclass
class ShotMechanics:
    load_frame: Optional[int] = None
    knee_angle_at_load_deg: Optional[float] = None
    knee_angle_at_release_deg: Optional[float] = None
    elbow_angle_at_load_deg: Optional[float] = None
    elbow_angle_at_release_deg: Optional[float] = None
    torso_lean_at_load_deg: Optional[float] = None
    torso_lean_at_release_deg: Optional[float] = None
    release_height_norm: Optional[float] = None
    release_horizontal_offset_norm: Optional[float] = None
    load_duration_sec: Optional[float] = None
    upward_duration_sec: Optional[float] = None
    total_prep_duration_sec: Optional[float] = None
    pose_quality: float = 0.0
    warnings: List[str] = field(default_factory=list)


def _by_frame(frames: List[PoseFrame]) -> Dict[int, PoseFrame]:
    return {f.frame_index: f for f in frames}


def _leg_points(pf: PoseFrame, side: Optional[str]):
    sides = [side] if side in ("left", "right") else ["left", "right"]
    for s in sides:
        hip, knee, ankle = pf.landmark(f"{s}_hip"), pf.landmark(f"{s}_knee"), pf.landmark(f"{s}_ankle")
        if hip and knee and ankle and min(hip.visibility, knee.visibility, ankle.visibility) >= _VIS_MIN:
            return (hip.x, hip.y), (knee.x, knee.y), (ankle.x, ankle.y)
    return None


def _arm_points(pf: PoseFrame, side: Optional[str]):
    if side not in ("left", "right"):
        return None
    shoulder = pf.landmark(f"{side}_shoulder")
    elbow = pf.landmark(f"{side}_elbow")
    wrist = pf.landmark(f"{side}_wrist")
    if shoulder and elbow and wrist and min(shoulder.visibility, elbow.visibility, wrist.visibility) >= _VIS_MIN:
        return (shoulder.x, shoulder.y), (elbow.x, elbow.y), (wrist.x, wrist.y)
    return None


def torso_points(pf: PoseFrame):
    """Canonical shoulder/hip torso reference for this frame, in the same
    normalized (0-1) coordinates as PoseFrame's own landmarks -- bilateral
    (averages both shoulders, both hips, not just one side) and abstains
    (returns None) rather than trusting a single low-visibility landmark.
    Public because app/pipeline/orchestrator.py also uses this as the
    canonical torso reference (converted to pixel space there), not just
    compute_shot_mechanics below."""
    ls, rs = pf.landmark("left_shoulder"), pf.landmark("right_shoulder")
    lh, rh = pf.landmark("left_hip"), pf.landmark("right_hip")
    if not (ls and rs and lh and rh):
        return None
    if min(ls.visibility, rs.visibility, lh.visibility, rh.visibility) < _VIS_MIN:
        return None
    shoulder_mid = midpoint((ls.x, ls.y), (rs.x, rs.y))
    hip_mid = midpoint((lh.x, lh.y), (rh.x, rh.y))
    return shoulder_mid, hip_mid


def compute_shot_mechanics(pose_frames: List[PoseFrame], shooting_side: Optional[str],
                            load_start_frame: Optional[int], upward_start_frame: Optional[int],
                            release_frame: Optional[int]) -> ShotMechanics:
    result = ShotMechanics()
    by_frame = _by_frame(pose_frames)

    lo = load_start_frame if load_start_frame is not None else (
        upward_start_frame if upward_start_frame is not None else release_frame)
    hi = release_frame if release_frame is not None else upward_start_frame
    if lo is None or hi is None:
        result.warnings.append("shot_window_incomplete")
        return result

    window = [by_frame[i] for i in range(lo, hi + 1) if i in by_frame and by_frame[i].detected]
    if not window:
        result.warnings.append("no_detected_pose_frames_in_window")
        return result

    result.pose_quality = round(sum(pf.pose_confidence for pf in window) / len(window), 3)

    # --- Load frame: point of maximum knee flexion (minimum knee angle) ---
    best_frame, best_angle = None, None
    for pf in window:
        legs = _leg_points(pf, shooting_side)
        if legs is None:
            continue
        angle = knee_angle(*legs)
        if angle is None:
            continue
        if best_angle is None or angle < best_angle:
            best_angle, best_frame = angle, pf.frame_index
    if best_frame is not None:
        result.load_frame = best_frame
        result.knee_angle_at_load_deg = round(best_angle, 1)
        load_pf = by_frame[best_frame]
        torso_pts = torso_points(load_pf)
        if torso_pts:
            lean = torso_lean_deg(*torso_pts)
            result.torso_lean_at_load_deg = round(lean, 1) if lean is not None else None
        arm_pts = _arm_points(load_pf, shooting_side)
        if arm_pts:
            ea = elbow_angle(*arm_pts)
            result.elbow_angle_at_load_deg = round(ea, 1) if ea is not None else None
    else:
        result.warnings.append("knee_angle_unavailable_at_load")

    # --- Release-frame metrics ---
    release_pf = by_frame.get(release_frame) if release_frame is not None else None
    if release_pf is None or not release_pf.detected:
        result.warnings.append("pose_unavailable_at_release")
    else:
        legs = _leg_points(release_pf, shooting_side)
        if legs:
            ka = knee_angle(*legs)
            result.knee_angle_at_release_deg = round(ka, 1) if ka is not None else None
        arm_pts = _arm_points(release_pf, shooting_side)
        if arm_pts:
            ea = elbow_angle(*arm_pts)
            result.elbow_angle_at_release_deg = round(ea, 1) if ea is not None else None
        torso_pts = torso_points(release_pf)
        if torso_pts:
            lean = torso_lean_deg(*torso_pts)
            result.torso_lean_at_release_deg = round(lean, 1) if lean is not None else None
            t_len = torso_length(*torso_pts)
            if arm_pts and t_len > 1e-6:
                _, _, wrist = arm_pts
                shoulder_mid, hip_mid = torso_pts
                height_px = hip_mid[1] - wrist[1]  # image-y grows downward
                result.release_height_norm = round(normalize_by_torso(height_px, t_len), 3)
                horiz_px = wrist[0] - shoulder_mid[0]
                result.release_horizontal_offset_norm = round(normalize_by_torso(horiz_px, t_len), 3)
        if not arm_pts:
            result.warnings.append("shooting_arm_landmarks_low_confidence_at_release")

    # --- Timing ---
    if load_start_frame is not None and upward_start_frame is not None:
        lo_pf, hi_pf = by_frame.get(load_start_frame), by_frame.get(upward_start_frame)
        if lo_pf and hi_pf:
            result.load_duration_sec = round(hi_pf.timestamp_sec - lo_pf.timestamp_sec, 3)
    if upward_start_frame is not None and release_frame is not None:
        lo_pf, hi_pf = by_frame.get(upward_start_frame), by_frame.get(release_frame)
        if lo_pf and hi_pf:
            result.upward_duration_sec = round(hi_pf.timestamp_sec - lo_pf.timestamp_sec, 3)
    if load_start_frame is not None and release_frame is not None:
        lo_pf, hi_pf = by_frame.get(load_start_frame), by_frame.get(release_frame)
        if lo_pf and hi_pf:
            result.total_prep_duration_sec = round(hi_pf.timestamp_sec - lo_pf.timestamp_sec, 3)

    return result
