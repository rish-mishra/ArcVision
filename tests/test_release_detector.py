from app.events.release_detector import estimate_release
from app.events.shot_state_machine import FrameSignals, ShotWindow

FPS = 30.0


def _signal(i, dist, vvel):
    return FrameSignals(frame_index=i, timestamp_sec=i / FPS, ball_available=True,
                          ball_hand_dist_norm=dist, ball_vertical_velocity_norm=vvel)


def test_release_estimate_refines_to_precise_separation_frame():
    frames = [_signal(i, 0.05, 0.0) for i in range(5)]
    frames += [_signal(i, 0.05, -0.5) for i in range(5, 8)]
    # separation begins at frame 8, crosses the tighter precise threshold at 9
    frames += [_signal(8, 0.15, -0.5)]
    frames += [_signal(9, 0.30, -0.5)]
    frames += [_signal(i, 0.9, -0.3) for i in range(10, 14)]

    window = ShotWindow(shot_index=1, start_frame=0, end_frame=13,
                          load_start_frame=0, upward_start_frame=5,
                          release_candidate_frame=8, flight_end_frame=13)
    est = estimate_release(window, frames)
    assert est is not None
    assert est.release_frame == 9
    assert est.confidence > 0.4


def test_release_estimate_none_without_candidate():
    window = ShotWindow(shot_index=1, start_frame=0, end_frame=10,
                          load_start_frame=0, upward_start_frame=None,
                          release_candidate_frame=None, flight_end_frame=10)
    assert estimate_release(window, []) is None


def test_release_estimate_falls_back_to_candidate_when_signal_unclear():
    frames = [_signal(i, 0.05, 0.0) for i in range(5)]
    window = ShotWindow(shot_index=1, start_frame=0, end_frame=4,
                          load_start_frame=0, upward_start_frame=2,
                          release_candidate_frame=3, flight_end_frame=4)
    est = estimate_release(window, frames)
    assert est is not None
    assert est.release_frame == 3
    assert est.basis == "state_machine_candidate_only"
