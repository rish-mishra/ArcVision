"""
Short continuation fine-tune of the existing RF-DETR ball/rim checkpoint on
the merged hard-negative dataset (data/datasets/basketball_ball_rim_v2_merged/,
built by build_merged_dataset_v2_hardneg.py). Starts from the EXISTING
checkpoint (models/rfdetr_ball_rim_v1.pth), not from scratch, and trains for
a small number of epochs -- standard continued-fine-tuning practice given
the new material is ~0.4% of the dataset by image count.

Writes to a SEPARATE output directory
(data/training_runs/rfdetr_ball_rim_v2_hardneg/) and never touches
models/rfdetr_ball_rim_v1.pth or data/training_runs/rfdetr_ball_rim_v1/.
Production's CONFIG.ball_rim_rfdetr.checkpoint_name is untouched by this
script -- switching production to the new checkpoint is a separate,
future, explicit decision.

Usage:
    .venv\\Scripts\\python scripts\\train_ball_rim_detector_v2_hardneg.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_v2_merged"
OUTPUT_DIR = ROOT / "data" / "training_runs" / "rfdetr_ball_rim_v2_hardneg"
PRETRAIN_CHECKPOINT = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name

EPOCHS = 4
BATCH_SIZE = 2
GRAD_ACCUM_STEPS = 8
LR = 1e-5  # an order of magnitude below the original 1e-4 -- a gentle continuation nudge, not a re-training
EARLY_STOPPING_PATIENCE = 2


def _dataset_metadata() -> dict:
    counts = {}
    for split in ("train", "valid", "test"):
        ann_path = DATASET_DIR / split / "_annotations.coco.json"
        d = json.loads(ann_path.read_text(encoding="utf-8"))
        counts[split] = {"images": len(d["images"]), "annotations": len(d["annotations"])}
    return {
        "base": "Continuation fine-tune of rfdetr_ball_rim_v1 (see its own dataset_metadata.json for the "
                 "original University of Arizona dataset provenance).",
        "addition": "data/datasets/basketball_ball_rim_hardneg_v1/manifest.json documents every new image "
                     "added here: source video, frame index, and category (v2_train_positive / "
                     "v2_train_negative / cross_video_negative / genuine_positive).",
        "held_out_not_in_this_dataset": "V2 arm=1541 artifact window and its temporal neighborhood -- "
                                           "evaluation-only, never included in train or valid here.",
        "counts": counts,
    }


def main():
    if not PRETRAIN_CHECKPOINT.exists():
        raise FileNotFoundError(f"Base checkpoint not found at {PRETRAIN_CHECKPOINT}")
    if not (DATASET_DIR / "train" / "_annotations.coco.json").exists():
        raise FileNotFoundError(f"Merged dataset not found at {DATASET_DIR} -- run "
                                  "build_merged_dataset_v2_hardneg.py first.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        "model": "RFDETRSmall", "pretrain_weights": str(PRETRAIN_CHECKPOINT),
        "epochs": EPOCHS, "batch_size": BATCH_SIZE, "grad_accum_steps": GRAD_ACCUM_STEPS, "lr": LR,
        "early_stopping_patience": EARLY_STOPPING_PATIENCE,
        "dataset_dir": str(DATASET_DIR), "started_at": datetime.now(timezone.utc).isoformat(),
        "note": "Continuation fine-tune targeting the RF-DETR roofline/sky false-positive class found on "
                 "real_test_02.mp4.mov -- see the migration reports for the full investigation.",
    }
    (OUTPUT_DIR / "training_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "dataset_metadata.json").write_text(json.dumps(_dataset_metadata(), indent=2), encoding="utf-8")

    import _rfdetr_compat
    _rfdetr_compat.apply()

    from rfdetr import RFDETRSmall
    model = RFDETRSmall(pretrain_weights=str(PRETRAIN_CHECKPOINT))
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
