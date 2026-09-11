"""
Assembles the training-ready merged dataset for the v3 fine-tune: COPIES
the original data/datasets/basketball_ball_rim/ unchanged, and merges in
data/datasets/basketball_ball_rim_hardneg_v3/train (train split only --
v3 has no valid-split additions, so the "valid" split here is the PURE,
untouched original validation set, matching the requirement to monitor
ball/rim performance on the untouched original validation data).

Usage:
    .venv\\Scripts\\python scripts\\build_merged_dataset_v3.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "datasets" / "basketball_ball_rim"
HARDNEG = ROOT / "data" / "datasets" / "basketball_ball_rim_hardneg_v3"
MERGED = ROOT / "data" / "datasets" / "basketball_ball_rim_v3_merged"

CATEGORIES = [
    {"id": 1, "name": "ball", "supercategory": "none"},
    {"id": 2, "name": "rim", "supercategory": "none"},
]


def merge_split(split: str, add_hardneg: bool):
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

    n_hardneg_slots = 0
    if add_hardneg:
        hn_ann = json.loads((HARDNEG / "train" / "_annotations.coco.json").read_text(encoding="utf-8"))
        for im in hn_ann["images"]:
            new_id = next_img_id
            next_img_id += 1
            fname_key = im["file_name"]
            dst_fname = f"hardneg_{fname_key}"
            images.append({"id": new_id, "file_name": dst_fname, "width": im["width"], "height": im["height"]})
            src = HARDNEG / "images" / fname_key
            dst = out_dir / dst_fname
            if not dst.exists():
                shutil.copy2(src, dst)
            img_id_map[("hardneg", im["id"])] = new_id
            n_hardneg_slots += 1
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
    print(f"{split}: {len(orig_ann['images'])} original + {n_hardneg_slots} hardneg-v3 slots = {len(images)} images, "
          f"{len(annotations)} annotations")


def main():
    if MERGED.exists():
        raise RuntimeError(f"{MERGED} already exists -- remove it manually first if rebuilding.")
    merge_split("train", add_hardneg=True)
    merge_split("valid", add_hardneg=False)  # pure original validation set, untouched
    merge_split("test", add_hardneg=False)
    print(f"\nMerged dataset written to {MERGED}")
    print(f"Original dataset and hard-negative-v3 set left untouched. Valid split is 100% original (no new material).")


if __name__ == "__main__":
    main()
