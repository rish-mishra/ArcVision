"""
Ensures required pretrained model weights are present in models/ before the
app runs. Safe to re-run; skips anything already downloaded.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import MODELS_DIR
from app.logging_config import get_logger

log = get_logger("scripts.download_models")


def ensure_yolo_weights() -> None:
    dest = MODELS_DIR / "yolov8n.pt"
    if dest.exists():
        log.info("yolov8n.pt already present at %s", dest)
        return
    from ultralytics import YOLO
    log.info("Downloading yolov8n.pt (Ultralytics COCO-pretrained nano model)...")
    model = YOLO("yolov8n.pt")
    downloaded = Path("yolov8n.pt")
    if downloaded.exists():
        downloaded.rename(dest)
    log.info("Saved to %s", dest)


def ensure_yolo_world_weights() -> None:
    dest = MODELS_DIR / "yolov8s-worldv2.pt"
    if dest.exists():
        log.info("yolov8s-worldv2.pt already present at %s", dest)
        return
    from ultralytics import YOLOWorld
    log.info("Downloading yolov8s-worldv2.pt (open-vocabulary detector used for hoop detection)...")
    YOLOWorld("yolov8s-worldv2.pt")
    downloaded = Path("yolov8s-worldv2.pt")
    if downloaded.exists():
        downloaded.rename(dest)
    log.info("Saved to %s", dest)


if __name__ == "__main__":
    ensure_yolo_weights()
    ensure_yolo_world_weights()
    print("Model setup complete.")
