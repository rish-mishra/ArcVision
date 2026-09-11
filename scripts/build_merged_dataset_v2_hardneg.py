"""
Assembles the training-ready merged dataset for the v2 hard-negative
fine-tune: COPIES (never moves/modifies) images and annotations from the
original data/datasets/basketball_ball_rim/ and the new
data/datasets/basketball_ball_rim_hardneg_v1/ into a third, separate
directory, data/datasets/basketball_ball_rim_v2_merged/. Both source
datasets are left completely untouched -- reverting this experiment is
deleting the merged directory (and the training run's output directory),
nothing else.

Usage:
    .venv\\Scripts\\python scripts\\build_merged_dataset_v2_hardneg.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "datasets" / "basketball_ball_rim"
HARDNEG = ROOT / "data" / "datasets" / "basketball_ball_rim_hardneg_v1"
MERGED = ROOT / "data" / "datasets" / "basketball_ball_rim_v2_merged"

CATEGORIES = [
    {"id": 1, "name": "ball", "supercategory": "none"},
    {"id": 2, "name": "rim", "supercategory": "none"},
]


def merge_split(split: str, hardneg_split: str):
    out_dir = MERGED / split
    out_dir.mkdir(parents=True, exist_ok=True)

    orig_ann = json.loads((ORIGINAL / split / "_annotations.coco.json").read_text(encoding="utf-8"))
    images = []
    annotations = []
    next_img_id = 1
    next_ann_id = 1
    img_id_map = {}

    for im in orig_ann["images"]:
        new_id = next_img_id
        next_img_id += 1
        img_id_map[("orig", im["id"])] = new_id
        images.append({"id": new_id, "file_name": im["file_name"], "width": im["width"], "height": im["height"]})
        src = ORIGINAL / split / im["file_name"]
        dst = out_dir / im["file_name"]
        if not dst.exists():
            shutil.copy2(src, dst)
    for a in orig_ann["annotations"]:
        annotations.append({
            "id": next_ann_id, "image_id": img_id_map[("orig", a["image_id"])],
            "category_id": a["category_id"], "bbox": a["bbox"], "area": a["area"], "iscrowd": a["iscrowd"],
        })
        next_ann_id += 1

    hardneg_path = HARDNEG / hardneg_split / "_annotations.coco.json"
    n_hardneg_images = 0
    if hardneg_path.exists():
        hn_ann = json.loads(hardneg_path.read_text(encoding="utf-8"))
        for im in hn_ann["images"]:
            new_id = next_img_id
            next_img_id += 1
            img_id_map[("hardneg", im["id"])] = new_id
            fname = f"hardneg_{im['file_name']}"  # prefixed: never collides with original filenames
            images.append({"id": new_id, "file_name": fname, "width": im["width"], "height": im["height"]})
            src = HARDNEG / "images" / im["file_name"]
            dst = out_dir / fname
            if not dst.exists():
                shutil.copy2(src, dst)
            n_hardneg_images += 1
        for a in hn_ann["annotations"]:
            annotations.append({
                "id": next_ann_id, "image_id": img_id_map[("hardneg", a["image_id"])],
                "category_id": a["category_id"], "bbox": a["bbox"], "area": a["area"], "iscrowd": a["iscrowd"],
            })
            next_ann_id += 1

    (out_dir / "_annotations.coco.json").write_text(
        json.dumps({"images": images, "annotations": annotations, "categories": CATEGORIES}, indent=2),
        encoding="utf-8",
    )
    print(f"{split}: {len(orig_ann['images'])} original + {n_hardneg_images} hard-negative-set = {len(images)} images, "
          f"{len(annotations)} annotations")


def main():
    if MERGED.exists():
        raise RuntimeError(f"{MERGED} already exists -- refusing to silently overwrite; remove it manually first "
                             "if you intend to rebuild the merged dataset.")
    merge_split("train", "train")
    merge_split("valid", "valid")
    # test split: pass through the original test set unchanged (no hard-negative test material)
    merge_split("test", "__none__")
    print(f"\nMerged dataset written to {MERGED}")
    print(f"Original dataset ({ORIGINAL}) and hard-negative set ({HARDNEG}) left untouched.")


if __name__ == "__main__":
    main()
