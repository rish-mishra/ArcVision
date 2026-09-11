"""
API-level tests: upload validation, job status/results lifecycle, and
error handling. The "happy path" test exercises the REAL detection/pose
models end-to-end on a tiny synthetic video (a moving circle -- not real
basketball footage) purely to prove the upload -> background job ->
storage -> results wiring works without crashing; it does not assert on
shot-detection accuracy, since that requires real footage.
"""
import io
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_synthetic_video(path: Path, seconds=3, fps=15, size=(480, 360)):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    n = int(seconds * fps)
    for i in range(n):
        frame = np.full((size[1], size[0], 3), 40, dtype=np.uint8)
        cx = int(50 + (size[0] - 100) * (i / n))
        cy = int(size[1] * 0.5 + 40 * np.sin(i / 3.0))
        cv2.circle(frame, (cx, cy), 12, (20, 120, 220), -1)  # a basketball-orange-ish circle
        cv2.rectangle(frame, (size[0] // 2 - 30, 20), (size[0] // 2 + 30, 60), (200, 200, 200), 2)
        writer.write(frame)
    writer.release()


def test_upload_rejects_bad_extension(tmp_path):
    bad_file = tmp_path / "clip.txt"
    bad_file.write_text("not a video")
    with bad_file.open("rb") as f:
        resp = client.post("/api/sessions/upload", files={"file": ("clip.txt", f, "text/plain")})
    assert resp.status_code == 400


def test_upload_rejects_too_short_video(tmp_path):
    path = tmp_path / "short.mp4"
    _make_synthetic_video(path, seconds=0.3, fps=15)
    with path.open("rb") as f:
        resp = client.post("/api/sessions/upload", files={"file": ("short.mp4", f, "video/mp4")})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "too_short"


def test_status_404_for_unknown_session():
    resp = client.get("/api/sessions/doesnotexist/status")
    assert resp.status_code == 404


def test_results_404_for_unknown_session():
    resp = client.get("/api/sessions/doesnotexist/results")
    assert resp.status_code == 404


def test_methodology_endpoint_returns_markdown():
    resp = client.get("/api/methodology")
    assert resp.status_code == 200
    assert "markdown" in resp.json()
    assert len(resp.json()["markdown"]) > 100


def test_full_upload_and_process_lifecycle(tmp_path):
    path = tmp_path / "session.mp4"
    _make_synthetic_video(path, seconds=3, fps=15)

    with path.open("rb") as f:
        resp = client.post("/api/sessions/upload", files={"file": ("session.mp4", f, "video/mp4")})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    deadline = time.time() + 120
    status = None
    while time.time() < deadline:
        status_resp = client.get(f"/api/sessions/{session_id}/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(1.0)

    assert status is not None
    assert status["status"] == "completed", f"job did not complete: {status}"

    results_resp = client.get(f"/api/sessions/{session_id}/results")
    assert results_resp.status_code == 200
    payload = results_resp.json()
    assert "shots" in payload
    assert "session_summary" in payload
    assert isinstance(payload["warnings"], list)

    sessions_resp = client.get("/api/sessions")
    assert sessions_resp.status_code == 200
    assert any(s["session_id"] == session_id for s in sessions_resp.json())

    del_resp = client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 200
