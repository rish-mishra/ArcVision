"""
Assembles the final RF-DETR-ready COCO dataset from the raw per-image
manifests fetched by fetch_ball_rim_annotations.py.

Class policy (see docs/METHODOLOGY.md "Detector architecture"):
  - "ball" and "basketball" (two overlapping source labels for the same
    physical object, confirmed by inspecting the raw project's class list)
    are merged into a single BALL class.
  - "rim" becomes RIM.
  - No "made"/"shoot"/"person"/"people" annotations were ever fetched (the
    fetch step only pulled ball/basketball/rim boxes to begin with), so
    there is nothing else to filter out here.
  - No "backboard" class exists anywhere in this source project.

Splits reuse the train/valid/test assignment Roboflow already recorded per
image (not re-split here), so results stay comparable with the source
project's own conventions.

Usage:
    .venv\\Scripts\\python scripts\\prepare_ball_rim_dataset.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_manifest"
IMAGES_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_images"
OUT_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim"

CLASS_REMAP = {"ball": "ball", "basketball": "ball", "rim": "rim"}
CATEGORIES = [
    {"id": 1, "name": "ball", "supercategory": "none"},
    {"id": 2, "name": "rim", "supercategory": "none"},
]
CATEGORY_ID = {c["name"]: c["id"] for c in CATEGORIES}


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    per_split = {"train": [], "valid": [], "test": []}
    for mf in MANIFEST_DIR.glob("*.json"):
        d = json.loads(mf.read_text(encoding="utf-8"))
        split = d["split"] if d["split"] in per_split else "train"
        per_split[split].append(d)

    total_images = 0
    total_boxes = 0
    for split, records in per_split.items():
        split_dir = OUT_DIR / split
        split_dir.mkdir(parents=True, exist_ok=True)

        images_out = []
        annotations_out = []
        ann_id = 1
        for img_id, rec in enumerate(records, 1):
            src_img = IMAGES_DIR / rec["file_name"]
            dst_img = split_dir / rec["file_name"]
            shutil.copyfile(src_img, dst_img)

            images_out.append({
                "id": img_id, "file_name": rec["file_name"],
                "width": rec["width"], "height": rec["height"],
            })
            for b in rec["boxes"]:
                cls = CLASS_REMAP[b["label"]]
                w, h = b["w"], b["h"]
                x = b["cx"] - w / 2.0
                y = b["cy"] - h / 2.0
                annotations_out.append({
                    "id": ann_id, "image_id": img_id, "category_id": CATEGORY_ID[cls],
                    "bbox": [round(x, 2), round(y, 2), round(w, 2), round(h, 2)],
                    "area": round(w * h, 2), "iscrowd": 0,
                })
                ann_id += 1

        coco = {"images": images_out, "annotations": annotations_out, "categories": CATEGORIES}
        (split_dir / "_annotations.coco.json").write_text(json.dumps(coco), encoding="utf-8")

        total_images += len(images_out)
        total_boxes += len(annotations_out)
        print(f"{split}: {len(images_out)} images, {len(annotations_out)} annotations")

    print(f"TOTAL: {total_images} images, {total_boxes} annotations -> {OUT_DIR}")


if __name__ == "__main__":
    main()
