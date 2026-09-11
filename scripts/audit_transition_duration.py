"""
Diagnostic: runs detect_release_events with tracing enabled and reports how
long each continuous stay in TRANSITION lasted (in trusted-pair steps and in
seconds), across a video. Not part of the pipeline.

Usage:
    .venv\\Scripts\\python scripts\\audit_transition_duration.py path\\to\\video.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.release_event_detector import detect_release_events
from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def main():
    video_path = Path(sys.argv[1]).resolve()
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)
    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)

    trace = []
    events = detect_release_events(frame_signals, torso_scale_px, trace=trace)

    # Find every run of consecutive TRANSITION states and its duration.
    runs = []
    cur_start = None
    cur_frames = 0
    for entry in trace:
        if entry.state_after == "transition":
            if cur_start is None:
                cur_start = entry.a_frame
            cur_frames += 1
        else:
            if cur_start is not None:
                runs.append((cur_start, entry.a_frame, cur_frames))
                cur_start = None
                cur_frames = 0
    if cur_start is not None:
        runs.append((cur_start, trace[-1].b_frame, cur_frames))

    fps = meta.fps
    print(f"{video_path.name}: {len(events)} candidate(s), {len(trace)} trusted-pair transitions traced")
    print(f"TRANSITION runs: {len(runs)}")
    if runs:
        durations_s = [n / fps for _, _, n in runs]
        durations_s.sort()
        print(f"  min={durations_s[0]:.3f}s  max={durations_s[-1]:.3f}s  "
              f"median={durations_s[len(durations_s)//2]:.3f}s  mean={sum(durations_s)/len(durations_s):.3f}s")
        long_runs = [(s, e, n) for s, e, n in runs if n / fps > 0.5]
        print(f"  runs longer than 0.5s: {len(long_runs)}")
        for s, e, n in sorted(runs, key=lambda r: -r[2])[:10]:
            print(f"    frames {s}-{e} ({n} steps, {n/fps:.3f}s)")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
