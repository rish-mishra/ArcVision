"""
v3 continuation fine-tune: same recipe as v2 (continue from the existing
checkpoint, conservative LR) but the ONLY deliberately changed lever
relative to v2 is oversampling of the corrected hard-negative material
(data/datasets/basketball_ball_rim_v3_merged/, built by
build_merged_dataset_v3.py) -- LR and epoch budget are unchanged from v2,
by design, to isolate exposure as the single tested variable per the
postmortem's finding (correct-direction, under-weighted signal).

Writes to a SEPARATE output directory (data/training_runs/rfdetr_ball_rim_v3/)
and never touches models/rfdetr_ball_rim_v1.pth, data/training_runs/rfdetr_ball_rim_v1/,
or the v2 run's own directory. Production's CONFIG.ball_rim_rfdetr.checkpoint_name
is untouched.

Usage:
    .venv\\Scripts\\python scripts\\train_ball_rim_detector_v3.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_v3_merged"
OUTPUT_DIR = ROOT / "data" / "training_runs" / "rfdetr_ball_rim_v3"
PRETRAIN_CHECKPOINT = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name

EPOCHS = 4                 # unchanged from v2
BATCH_SIZE = 2              # unchanged from v2
GRAD_ACCUM_STEPS = 8        # unchanged from v2
LR = 1e-5                   # UNCHANGED from v2, deliberately -- oversampling is the only tested lever
EARLY_STOPPING_PATIENCE = 2  # unchanged from v2


def _exposure_report(train_ann_path: Path) -> dict:
    d = json.loads(train_ann_path.read_text(encoding="utf-8"))
    total = len(d["images"])
    new_slots = sum(1 for im in d["images"] if im["file_name"].startswith("hardneg_"))
    effective_batch = BATCH_SIZE * GRAD_ACCUM_STEPS
    micro_batches_per_epoch = total / BATCH_SIZE
    p_new_in_microbatch = 1 - (1 - new_slots / total) ** BATCH_SIZE
    p_new_in_optimizer_step = 1 - (1 - p_new_in_microbatch) ** GRAD_ACCUM_STEPS
    return {
        "total_train_images": total,
        "new_hardneg_slots": new_slots,
        "new_material_fraction": round(new_slots / total, 4),
        "v2_new_material_fraction_for_comparison": 0.0043,
        "effective_batch_size": effective_batch,
        "estimated_fraction_of_optimizer_steps_touching_new_material_per_epoch": round(p_new_in_optimizer_step, 3),
        "epochs": EPOCHS,
    }


def main():
    if not PRETRAIN_CHECKPOINT.exists():
        raise FileNotFoundError(f"Base checkpoint not found at {PRETRAIN_CHECKPOINT}")
    train_ann = DATASET_DIR / "train" / "_annotations.coco.json"
    if not train_ann.exists():
        raise FileNotFoundError(f"Merged dataset not found at {DATASET_DIR} -- run build_merged_dataset_v3.py first.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    exposure = _exposure_report(train_ann)
    print("Exposure report:", json.dumps(exposure, indent=2))

    config = {
        "model": "RFDETRSmall", "pretrain_weights": str(PRETRAIN_CHECKPOINT),
        "epochs": EPOCHS, "batch_size": BATCH_SIZE, "grad_accum_steps": GRAD_ACCUM_STEPS, "lr": LR,
        "early_stopping_patience": EARLY_STOPPING_PATIENCE,
        "dataset_dir": str(DATASET_DIR), "started_at": datetime.now(timezone.utc).isoformat(),
        "exposure_report": exposure,
        "note": "v3: same LR/epochs as v2 (deliberately unchanged) -- the only tested variable is oversampling "
                 "of corrected (both-class-annotated, full-frame, no crops) hard-negative material. "
                 "V2 arm~1541 (W5) window held out entirely, never in this dataset.",
    }
    (OUTPUT_DIR / "training_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

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
