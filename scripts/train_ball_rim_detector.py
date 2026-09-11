"""
Fine-tunes RF-DETR-Small on the BALL/RIM dataset prepared by
prepare_ball_rim_dataset.py.

Model size choice: RFDETRSmall (32.1M params, 512x512 input) -- matches the
comparable public implementation referenced for this project, and
hands-on benchmarking on this machine's RTX 4050 (6GB VRAM) showed the
COCO-pretrained Small model uses well under 200MB for single-image
inference, leaving comfortable headroom for training. Nano would sacrifice
resolution/accuracy for a GPU that doesn't need the savings; Medium/Large
would cut into the safety margin without a demonstrated need.

Batch size: RF-DETR's own guidance targets an effective batch size of 16
(batch_size * grad_accum_steps). On a 6GB laptop GPU (vs. the 16GB T4 their
docs size batch_size=4/grad_accum=4 for), batch_size=2/grad_accum_steps=8
is the conservative starting point; if this OOMs, drop to batch_size=1/
grad_accum_steps=16.

Saves alongside the checkpoint: exact training config, dataset metadata
(source, license, class remap, image/annotation counts), and installed
package versions -- so this run is fully reproducible and the model can be
retrained or replaced later without guessing what produced it.

Usage:
    .venv\\Scripts\\python scripts\\train_ball_rim_detector.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim"
OUTPUT_DIR = ROOT / "data" / "training_runs" / "rfdetr_ball_rim_v1"

EPOCHS = 40
BATCH_SIZE = 2
GRAD_ACCUM_STEPS = 8
LR = 1e-4
EARLY_STOPPING_PATIENCE = 8


def _dataset_metadata() -> dict:
    counts = {}
    for split in ("train", "valid", "test"):
        ann_path = DATASET_DIR / split / "_annotations.coco.json"
        d = json.loads(ann_path.read_text(encoding="utf-8"))
        counts[split] = {"images": len(d["images"]), "annotations": len(d["annotations"])}
    return {
        "source": "University of Arizona 'Basketball Shooting Robot' (Roboflow Universe)",
        "source_url": "https://universe.roboflow.com/the-university-of-arizona-th1yv/basketball-shooting-robot",
        "license": "CC BY 4.0",
        "note": "Pulled directly from the raw project's per-image annotations (not the "
                 "one generated/downloadable version, which contains only the 'rim' class "
                 "with zero ball annotations). ball+basketball source labels merged into "
                 "a single 'ball' class; 'rim' kept as-is. person/people/made/shoot labels "
                 "were never fetched.",
        "classes": ["ball", "rim"],
        "counts": counts,
    }


def _pip_freeze() -> str:
    import subprocess
    return subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        "model": "RFDETRSmall", "epochs": EPOCHS, "batch_size": BATCH_SIZE,
        "grad_accum_steps": GRAD_ACCUM_STEPS, "lr": LR,
        "early_stopping_patience": EARLY_STOPPING_PATIENCE,
        "dataset_dir": str(DATASET_DIR), "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUTPUT_DIR / "training_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "dataset_metadata.json").write_text(json.dumps(_dataset_metadata(), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "pip_freeze.txt").write_text(_pip_freeze(), encoding="utf-8")

    import _rfdetr_compat
    _rfdetr_compat.apply()

    from rfdetr import RFDETRSmall
    model = RFDETRSmall()
    model.train(
        dataset_dir=str(DATASET_DIR),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        grad_accum_steps=GRAD_ACCUM_STEPS,
        lr=LR,
        output_dir=str(OUTPUT_DIR),
        early_stopping=True,
        early_stopping_patience=EARLY_STOPPING_PATIENCE,
    )

    print("Training complete. Output dir:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
