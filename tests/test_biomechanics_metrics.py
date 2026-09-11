from app.biomechanics.metrics import compute_shot_mechanics
from app.vision.types import Landmark, PoseFrame


def _pf(i, knee_y, hip_y=0.6, shoulder_y=0.3, wrist_y=None, ts=None):
    wrist_y = wrist_y if wrist_y is not None else shoulder_y - 0.1
    landmarks = {
        "left_shoulder": Landmark(0.45, shoulder_y, 0, 0.9),
        "right_shoulder": Landmark(0.55, shoulder_y, 0, 0.9),
        "left_hip": Landmark(0.45, hip_y, 0, 0.9),
        "right_hip": Landmark(0.55, hip_y, 0, 0.9),
        "right_elbow": Landmark(0.6, (shoulder_y + wrist_y) / 2, 0, 0.9),
        "right_wrist": Landmark(0.65, wrist_y, 0, 0.9),
        "right_knee": Landmark(0.55, knee_y, 0, 0.9),
        "right_ankle": Landmark(0.55, 0.95, 0, 0.9),
    }
    return PoseFrame(frame_index=i, timestamp_sec=ts if ts is not None else i / 30.0,
                       detected=True, landmarks=landmarks, pose_confidence=0.9)


def test_compute_shot_mechanics_finds_load_and_release():
    frames = []
    # Loading: knee_y increases (deeper bend approximated by knee point
    # moving toward hip/ankle line -- for this synthetic test we just vary
    # knee_y to change the hip-knee-ankle angle).
    for i, ky in enumerate([0.75, 0.8, 0.85, 0.8, 0.75]):
        frames.append(_pf(i, knee_y=ky))
    release_frame = 4
    mech = compute_shot_mechanics(frames, shooting_side="right",
                                    load_start_frame=0, upward_start_frame=2,
                                    release_frame=release_frame)
    assert mech.load_frame is not None
    assert mech.knee_angle_at_load_deg is not None
    assert mech.knee_angle_at_release_deg is not None
    assert mech.elbow_angle_at_release_deg is not None
    assert mech.release_height_norm is not None
    assert mech.pose_quality > 0
    assert mech.load_duration_sec is not None
    assert mech.total_prep_duration_sec is not None


def test_compute_shot_mechanics_handles_missing_pose_gracefully():
    frames = [PoseFrame(frame_index=i, timestamp_sec=i / 30.0, detected=False) for i in range(5)]
    mech = compute_shot_mechanics(frames, shooting_side="right",
                                    load_start_frame=0, upward_start_frame=2, release_frame=4)
    assert mech.knee_angle_at_load_deg is None
    assert "no_detected_pose_frames_in_window" in mech.warnings


def test_compute_shot_mechanics_no_window_returns_empty_with_warning():
    mech = compute_shot_mechanics([], shooting_side="right",
                                    load_start_frame=None, upward_start_frame=None, release_frame=None)
    assert mech.warnings == ["shot_window_incomplete"]
