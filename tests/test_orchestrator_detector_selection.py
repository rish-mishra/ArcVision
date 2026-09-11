"""
Tests that run_pipeline() picks the fine-tuned RF-DETR ball/rim detector
when available, and falls back to the generic YOLOv8/YOLO-World/
classical-CV stack (with an explicit warning) when it isn't -- without
needing a full A/B accuracy comparison, which is covered separately by
scripts/benchmark_ball_rim_detectors.py against real footage.

Uses a tiny synthetic video (not real basketball footage) purely to
exercise the branch-selection wiring end-to-end without crashing.
"""
import dataclasses
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import CONFIG, BallRimDetectorConfig
from app.pipeline import orchestrator as orchestrator_module
from app.pipeline.orchestrator import run_pipeline


def _make_synthetic_video(path: Path, seconds=3, fps=15, size=(320, 240)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    n = int(seconds * fps)
    for i in range(n):
        frame = np.full((size[1], size[0], 3), 40, dtype=np.uint8)
        cx = int(30 + (size[0] - 60) * (i / n))
        cy = int(size[1] * 0.5)
        cv2.circle(frame, (cx, cy), 10, (20, 120, 220), -1)
        writer.write(frame)
    writer.release()


def test_falls_back_to_generic_stack_with_warning_when_checkpoint_missing(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    _make_synthetic_video(video_path)

    patched_cfg = dataclasses.replace(
        CONFIG, ball_rim_rfdetr=BallRimDetectorConfig(enabled=True, checkpoint_name="definitely_missing.pth")
    )
    monkeypatch.setattr(orchestrator_module, "CONFIG", patched_cfg)

    result = run_pipeline(video_path)

    assert any("fine-tuned basketball/rim detector was unavailable" in w for w in result.warnings)


def test_disabled_flag_skips_rfdetr_even_if_checkpoint_exists(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    _make_synthetic_video(video_path)

    real_checkpoint = Path(__file__).resolve().parent.parent / "models" / CONFIG.ball_rim_rfdetr.checkpoint_name
    if not real_checkpoint.exists():
        pytest.skip("Real RF-DETR checkpoint not present in this environment -- nothing to disable.")

    patched_cfg = dataclasses.replace(
        CONFIG, ball_rim_rfdetr=BallRimDetectorConfig(enabled=False, checkpoint_name=CONFIG.ball_rim_rfdetr.checkpoint_name)
    )
    monkeypatch.setattr(orchestrator_module, "CONFIG", patched_cfg)

    result = run_pipeline(video_path)

    # Disabled deliberately, not "missing" -- must not claim unavailability.
    assert not any("fine-tuned basketball/rim detector was unavailable" in w for w in result.warnings)


def test_uses_rfdetr_without_fallback_warning_when_checkpoint_present(tmp_path):
    real_checkpoint = Path(__file__).resolve().parent.parent / "models" / CONFIG.ball_rim_rfdetr.checkpoint_name
    if not real_checkpoint.exists():
        pytest.skip("Real RF-DETR checkpoint not present in this environment.")

    video_path = tmp_path / "clip.mp4"
    _make_synthetic_video(video_path)

    result = run_pipeline(video_path)

    assert not any("fine-tuned basketball/rim detector was unavailable" in w for w in result.warnings)
