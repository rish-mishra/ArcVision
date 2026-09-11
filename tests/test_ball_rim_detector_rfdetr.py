"""
Unit tests for the RF-DETR ball/rim detector adapter
(app/vision/detection/ball_rim_detector_rfdetr.py). Uses a mocked RF-DETR
model throughout -- these tests exercise the adapter's OWN logic (class
filtering, coordinate conversion, missing-checkpoint handling), not the
real model's accuracy, which is covered separately by the training run's
own validation metrics and the real-video A/B benchmark.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector


def _fake_raw(boxes):
    """boxes: list of (x1, y1, x2, y2, confidence, class_id)"""
    if not boxes:
        return SimpleNamespace(xyxy=np.zeros((0, 4)), confidence=np.zeros((0,)), class_id=np.zeros((0,), dtype=int))
    xyxy = np.array([b[:4] for b in boxes], dtype=float)
    confidence = np.array([b[4] for b in boxes], dtype=float)
    class_id = np.array([b[5] for b in boxes], dtype=int)
    return SimpleNamespace(xyxy=xyxy, confidence=confidence, class_id=class_id)


def test_missing_checkpoint_raises_with_no_fallback(tmp_path):
    """'ball'/'rim' aren't COCO classes -- a stock RF-DETR checkpoint has
    nothing meaningful to predict for them, so a missing fine-tuned
    checkpoint must be a hard error, never a silent generic-model fallback."""
    missing_path = tmp_path / "does_not_exist.pth"
    with pytest.raises(FileNotFoundError):
        RFDETRBallRimDetector(str(missing_path))


def _make_detector(tmp_path):
    ckpt = tmp_path / "fake_checkpoint.pth"
    ckpt.write_bytes(b"not a real checkpoint, just needs to exist")
    with patch("rfdetr.RFDETRSmall") as mock_cls:
        mock_cls.return_value = MagicMock()
        detector = RFDETRBallRimDetector(str(ckpt))
    return detector


def test_extract_ball_detections_filters_class_and_converts_fields(tmp_path):
    detector = _make_detector(tmp_path)
    raw = _fake_raw([
        (10.0, 20.0, 30.0, 50.0, 0.87, 0),   # ball (class_id 0 -- see CLASS_ID_TO_NAME)
        (100.0, 100.0, 140.0, 140.0, 0.95, 1),  # rim -- must be excluded
    ])
    dets = detector.extract_ball_detections(raw, frame_index=42, timestamp_sec=1.5)
    assert len(dets) == 1
    d = dets[0]
    assert d.frame_index == 42
    assert d.timestamp_sec == 1.5
    assert (d.x1, d.y1, d.x2, d.y2) == (10.0, 20.0, 30.0, 50.0)
    assert d.confidence == pytest.approx(0.87)
    assert d.class_name == "ball_rfdetr"


def test_extract_rim_candidates_filters_class_and_computes_circle(tmp_path):
    detector = _make_detector(tmp_path)
    raw = _fake_raw([
        (10.0, 20.0, 30.0, 50.0, 0.87, 0),   # ball -- must be excluded
        (100.0, 100.0, 140.0, 180.0, 0.95, 1),  # rim: w=40, h=80
    ])
    candidates = detector.extract_rim_candidates(raw)
    assert len(candidates) == 1
    cx, cy, radius, conf = candidates[0]
    assert cx == pytest.approx(120.0)
    assert cy == pytest.approx(140.0)
    assert radius == pytest.approx(40.0)  # max(w, h) / 2 = 80 / 2
    assert conf == pytest.approx(0.95)


def test_empty_raw_detections_handled_gracefully(tmp_path):
    detector = _make_detector(tmp_path)
    raw = _fake_raw([])
    assert detector.extract_ball_detections(raw, 0, 0.0) == []
    assert detector.extract_rim_candidates(raw) == []


def test_predict_raw_converts_bgr_to_rgb_before_inference(tmp_path):
    detector = _make_detector(tmp_path)
    detector.model.predict = MagicMock(return_value="raw_result")
    frame_bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    frame_bgr[0, 0] = [10, 20, 30]  # B, G, R

    result = detector.predict_raw(frame_bgr)

    assert result == "raw_result"
    called_frame = detector.model.predict.call_args[0][0]
    assert list(called_frame[0, 0]) == [30, 20, 10]  # R, G, B
    # A [::-1] channel-reversal view has a negative stride, which
    # torchvision's to_tensor() cannot convert -- confirmed by a real
    # ValueError against an actual checkpoint before this was fixed.
    assert called_frame.flags["C_CONTIGUOUS"]


def test_extract_ball_detections_returns_empty_for_none_raw(tmp_path):
    detector = _make_detector(tmp_path)
    assert detector.extract_ball_detections(None, 0, 0.0) == []
    assert detector.extract_rim_candidates(None) == []
