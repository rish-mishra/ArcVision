"""
One-off dataset builder (not part of any pipeline, run once to produce the
hard-negative fine-tune dataset): extracts frames/crops from V1/V2/V3 and
writes a SEPARATE, self-contained COCO dataset at
data/datasets/basketball_ball_rim_hardneg_v1/ -- never touches the
original data/datasets/basketball_ball_rim/ directory or its manifest.

Categories written (see the migration report for the full reasoning):
  - CORRECT POSITIVES: frames within the 4 TRAINING V2 artifact windows,
    taken from the early, unambiguously-real portion of each window (well
    before the reported detection drifts onto the roofline), labeled with
    RF-DETR's own already-correct bbox from that frame.
  - TRUE NEGATIVES: square crops from later, clearly-drifted frames in the
    same 4 windows (source=detected, y comfortably above the player's own
    y-range), centered on the false detection -- the real ball (still held
    by the player, y>300 in this camera's framing) is never inside these
    crop bounds, verified by construction (crop y-range stays under 260,
    the player's own detections in this window never go above y~330).
  - CROSS-VIDEO NEGATIVES: a few crops from V1/V3 sky/roofline regions,
    manually spot-checked, never near any known ball position.
  - GENUINE POSITIVES: frames from V1/V3 shots NOT used anywhere in this
    session's Architecture C evaluation reference set (70/1402 in V1,
    477-ish in V3 -- 885/1099/562/905/738 are reserved for evaluation).

The held-out V2 artifact window (arm=1541) and its temporal neighborhood
contribute NOTHING here -- intentionally absent, not filtered later.

Usage:
    .venv\\Scripts\\python scripts\\build_hard_negative_dataset.py
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_hardneg_v1"
IMAGES_DIR = OUT_DIR / "images"

CATEGORIES = [
    {"id": 1, "name": "ball", "supercategory": "none"},
    {"id": 2, "name": "rim", "supercategory": "none"},
]
BALL_CAT_ID = 1

V2 = ROOT / "real_test_02.mp4.mov"
V1 = ROOT / "real_test_01.mp4.mov"
V3 = ROOT / "real_test_03.mov"

# V1/V3 are read at native 1280x720 here (plain cv2.VideoCapture) but every
# bbox coordinate collected earlier this session for them came from
# FrameReader's ANALYSIS resolution (960x540 -- confirmed by direct check,
# native != analysis for these two videos, unlike V2 where they're equal).
# Frames sourced with coordinates from that earlier diagnostic data MUST be
# resized down to 960x540 before the coordinates mean anything; the two
# cross-video negative crops were instead picked by eye directly from native
# 1280x720 screenshots, so those stay at native resolution untouched.
ANALYSIS_SIZE = {V1: (960, 540), V3: (960, 540)}


class Builder:
    def __init__(self):
        self.images = []
        self.annotations = []
        self.next_img_id = 1
        self.next_ann_id = 1
        self._caps = {}

    def _cap(self, video_path: Path):
        key = str(video_path)
        if key not in self._caps:
            self._caps[key] = cv2.VideoCapture(key)
        return self._caps[key]

    def _read(self, video_path: Path, frame_index: int, to_analysis_res: bool = False):
        cap = self._cap(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"could not read frame {frame_index} from {video_path}")
        if to_analysis_res and video_path in ANALYSIS_SIZE:
            frame = cv2.resize(frame, ANALYSIS_SIZE[video_path], interpolation=cv2.INTER_AREA)
        return frame

    def add_positive_full_frame(self, video_path: Path, frame_index: int, tag: str,
                                  bx: float, by: float, bw: float, bh: float):
        # Coordinates always come from the analysis-resolution diagnostic
        # data for every positive frame in this dataset (V1/V2/V3 alike).
        frame = self._read(video_path, frame_index, to_analysis_res=True)
        h, w = frame.shape[:2]
        fname = f"{tag}_f{frame_index}.jpg"
        cv2.imwrite(str(IMAGES_DIR / fname), frame)
        img_id = self.next_img_id
        self.next_img_id += 1
        self.images.append({"id": img_id, "file_name": fname, "width": w, "height": h})
        x1, y1 = bx - bw / 2, by - bh / 2
        self.annotations.append({
            "id": self.next_ann_id, "image_id": img_id, "category_id": BALL_CAT_ID,
            "bbox": [round(x1, 1), round(y1, 1), round(bw, 1), round(bh, 1)],
            "area": round(bw * bh, 1), "iscrowd": 0,
        })
        self.next_ann_id += 1
        return fname

    def add_negative_crop(self, video_path: Path, frame_index: int, tag: str,
                            cx: float, cy: float, size: int = 320, to_analysis_res: bool = True):
        frame = self._read(video_path, frame_index, to_analysis_res=to_analysis_res)
        h, w = frame.shape[:2]
        x0 = int(max(0, min(w - size, cx - size / 2)))
        y0 = int(max(0, min(h - size, cy - size / 2)))
        x1 = min(w, x0 + size)
        y1 = min(h, y0 + size)
        crop = frame[y0:y1, x0:x1]
        fname = f"{tag}_f{frame_index}_neg.jpg"
        cv2.imwrite(str(IMAGES_DIR / fname), crop)
        img_id = self.next_img_id
        self.next_img_id += 1
        self.images.append({"id": img_id, "file_name": fname, "width": crop.shape[1], "height": crop.shape[0]})
        return fname

    def write(self, split_assignment: dict):
        """split_assignment: {image_id: 'train'|'valid'}"""
        by_split = {"train": {"images": [], "annotations": []}, "valid": {"images": [], "annotations": []}}
        img_by_id = {im["id"]: im for im in self.images}
        for img_id, split in split_assignment.items():
            by_split[split]["images"].append(img_by_id[img_id])
        ann_by_img = {}
        for ann in self.annotations:
            ann_by_img.setdefault(ann["image_id"], []).append(ann)
        for split, data in by_split.items():
            for im in data["images"]:
                data["annotations"].extend(ann_by_img.get(im["id"], []))
            split_dir = OUT_DIR / split
            split_dir.mkdir(parents=True, exist_ok=True)
            (split_dir / "_annotations.coco.json").write_text(
                json.dumps({"images": data["images"], "annotations": data["annotations"], "categories": CATEGORIES}, indent=2),
                encoding="utf-8",
            )
            print(f"{split}: {len(data['images'])} images, {len(data['annotations'])} annotations")


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    b = Builder()
    manifest = []  # (image_id, category, video, frame_index) for the report

    # ---- V2 training windows: correct positives (early, confirmed-real) ----
    positives = [
        ("W1", 40, 179.5, 361.5, 34.9, 30.8), ("W1", 46, 188.5, 371.6, 34.3, 30.7),
        ("W2", 312, 160.8, 369.7, 34.4, 32.1), ("W2", 318, 161.5, 376.7, 33.8, 32.4),
        ("W3", 542, 155.5, 372.5, 36.0, 31.6), ("W3", 546, 160.3, 334.1, 34.7, 29.0),
        ("W4", 1349, 170.8, 379.4, 35.4, 30.0), ("W4", 1352, 181.0, 360.9, 35.7, 30.3),
    ]
    for tag, fi, bx, by, bw, bh in positives:
        fname = b.add_positive_full_frame(V2, fi, f"v2_{tag}_pos", bx, by, bw, bh)
        manifest.append((b.next_img_id - 1, "v2_train_positive", "V2", fi, fname))

    # ---- V2 training windows: true negatives (drifted, safely cropped) ----
    negatives = [
        ("W1", 61, 277.2, 152.0), ("W1", 65, 357.3, 78.8), ("W1", 70, 457.4, 20.5), ("W1", 76, 574.7, 10.4),
        ("W2", 333, 230.3, 177.9), ("W2", 337, 305.1, 97.0), ("W2", 343, 418.7, 20.2), ("W2", 349, 529.0, 9.0),
        ("W3", 554, 226.5, 176.9), ("W3", 558, 306.5, 95.8), ("W3", 564, 431.4, 17.7), ("W3", 570, 556.2, 7.2),
        ("W4", 1362, 237.4, 169.6), ("W4", 1366, 309.9, 87.3), ("W4", 1371, 404.7, 18.8), ("W4", 1377, 518.3, 4.1),
    ]
    for tag, fi, cx, cy in negatives:
        fname = b.add_negative_crop(V2, fi, f"v2_{tag}_neg", cx, cy)
        manifest.append((b.next_img_id - 1, "v2_train_negative", "V2", fi, fname))

    # ---- Cross-video negatives (V1/V3 sky regions, spot-checked separately) ----
    # Only frames actually spot-checked by direct screenshot (V1 f100 and V3 f100
    # were also checked and REJECTED -- both show the real ball inside the
    # proposed crop region; kept out entirely rather than guessed around).
    cross_negs = [
        (V1, 200, 400, 100, "v1"),   # verified: ball is at floor level, far from this sky-region crop
        (V3, 200, 500, 60, "v3"),    # verified: ball is near treeline at y~470, below this sky-only crop
    ]
    for video, fi, cx, cy, tag in cross_negs:
        # to_analysis_res=False: these two crop centers were picked by eye
        # directly from native 1280x720 screenshots, not from
        # analysis-resolution diagnostic data -- resizing first would shift
        # the crop away from the region actually verified ball-free.
        fname = b.add_negative_crop(video, fi, f"{tag}_crossneg", cx, cy, to_analysis_res=False)
        manifest.append((b.next_img_id - 1, "cross_video_negative", tag.upper(), fi, fname))

    # ---- Genuine positives from V1/V3, NOT overlapping the eval reference set ----
    genuine = [
        (V1, 67, 721.4, 389.0, 33.2, 38.6), (V1, 70, 705.4, 366.1, 34.0, 37.4), (V1, 74, 713.4, 307.7, 32.6, 34.9),
        (V1, 1398, 712.1, 320.7, 32.6, 34.2), (V1, 1402, 687.5, 255.3, 34.3, 35.7),
        (V3, 475, 759.5, 338.5, 42.2, 44.2), (V3, 479, 739.1, 318.5, 40.5, 43.8), (V3, 483, 739.6, 267.5, 40.7, 40.6),
    ]
    for video, fi, bx, by, bw, bh in genuine:
        tag = "v1_genuine" if video == V1 else "v3_genuine"
        fname = b.add_positive_full_frame(video, fi, tag, bx, by, bw, bh)
        manifest.append((b.next_img_id - 1, "genuine_positive", tag.split("_")[0].upper(), fi, fname))

    # ---- Train/valid split: whole windows/categories as atomic blocks, never split ----
    # Held out for VALIDATION (never trained on): V2 window W4's negatives+positives
    # (a full artifact window, held out the same way the eval-only W5 window is --
    # this gives an in-training-data validation signal from a block the optimizer
    # never sees gradients from, on top of W5's fully-separate, never-touched status).
    split = {}
    for img_id, category, video, fi, fname in manifest:
        if category in ("v2_train_positive", "v2_train_negative") and fname.startswith("v2_W4"):
            split[img_id] = "valid"
        else:
            split[img_id] = "train"

    b.write(split)

    (OUT_DIR / "manifest.json").write_text(
        json.dumps([{"image_id": i, "category": c, "video": v, "frame_index": f, "file": fn} for i, c, v, f, fn in manifest], indent=2),
        encoding="utf-8",
    )
    print(f"\nTotal new images: {len(b.images)}")
    print("Held out entirely from this dataset (eval-only): V2 arm=1541 window + its temporal neighborhood.")
    print(f"Wrote manifest to {OUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
