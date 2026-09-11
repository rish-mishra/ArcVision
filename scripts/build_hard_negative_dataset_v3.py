"""
v3 hard-negative dataset builder -- corrects both flaws found in v2:

1. RIM OMISSION: every v2 image was audited only for the ball. Several
   clearly show the hoop and left it unlabeled, teaching the model "no rim
   here" in frames that visibly contain one -- the direct, confirmed cause
   of v2's rim-coverage collapse (99.4% -> 0.2% on V1). Every image here is
   annotated for BOTH classes: the rim position is essentially static per
   video (confirmed: V2 rim center varies only (723-727, 138-141) px across
   all 4 windows) so one representative rim bbox per video is used.

2. SCALE MISMATCH: v2's negatives were 320x320 crops, presenting the
   artifact ~1.6-2.8x larger than its natural appearance in a full V2 frame
   (910x512, already near RF-DETR's 512 training resolution). v3 uses ONLY
   full, native-resolution frames -- no crops anywhere. Every one of these
   frames genuinely contains the real ball (confirmed by direct visual
   check for W1/W3/W4 -- held or actively dribbled -- and W2 -- resting on
   the ground), so each is a correctly-labeled POSITIVE, not a
   zero-annotation negative; the implicit suppression of the false
   roofline query comes from the standard bipartite-matching loss on these
   correctly-labeled images, not from a manufactured crop.

Frame selection uses only frames with an RF-DETR raw detection already
confirmed correct in this session's diagnostics -- no interpolation into
ambiguous territory. Every one of these frames was additionally spot-
verified by direct visual inspection (not just trusted from the
coordinate data) before use, which caught a real bug: an earlier version
of this script read V2 frames via plain cv2.VideoCapture.set(frame_index),
but every "frame_index" used throughout this session is an
ANALYSIS-pipeline index (FrameReader), not a raw video frame number --
V2's native fps (~59.9) is downsampled 2x to the ~30fps analysis rate, so
analysis frame_index N is raw/source frame N*2. Reading raw frame N
directly therefore pulled content from an earlier, unrelated moment (confirmed
directly: analysis frame_index=541 is raw/source frame 1082). Fixed via
FRAME_STRIDE below; re-verified visually. This also corrected an earlier,
overly-conservative read of W3 as "an active dribble" (based on the wrong
frame) -- the correctly-extracted frames show a continuous held-ball ->
real-shot-release sequence, so W3's usable range was extended accordingly.

Strengthens exposure via OVERSAMPLING (repeated image_id entries pointing
at the same file) rather than epochs/LR -- see main()'s REPEAT_FACTOR and
the printed exposure-ratio report.

Held out completely, as in v2: W5 (arm~1541) and its temporal neighborhood
-- never appears anywhere in this script.

No crop-based negatives of any kind in this version, per the corrected plan.

Usage:
    .venv\\Scripts\\python scripts\\build_hard_negative_dataset_v3.py
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "datasets" / "basketball_ball_rim_hardneg_v3"
IMAGES_DIR = OUT_DIR / "images"

CATEGORIES = [
    {"id": 1, "name": "ball", "supercategory": "none"},
    {"id": 2, "name": "rim", "supercategory": "none"},
]
BALL_CAT_ID = 1
RIM_CAT_ID = 2

V2 = ROOT / "real_test_02.mp4.mov"
V1 = ROOT / "real_test_01.mp4.mov"
V3 = ROOT / "real_test_03.mov"
ANALYSIS_SIZE = {V1: (960, 540), V3: (960, 540)}  # V2 native == analysis (910x512); see prior session's finding
# CRITICAL: every frame_index used throughout this session's V2 diagnostics is an
# ANALYSIS-pipeline index (FrameReader), not a raw video frame number. V2's native
# fps is ~59.9 against an analysis target of ~30fps, giving frame_stride=2 -- so
# analysis frame_index N is raw/source frame N*2 (confirmed directly: FrameReader
# reports source_frame_index=1082 for analysis frame_index=541). V1 and V3 both
# have frame_stride=1 (native fps already ~29), so no correction needed there.
# A prior version of this script read frames via plain cv2.VideoCapture.set(N)
# directly for V2, which was silently reading the WRONG raw frame for every V2
# image (off by 2x, i.e. from an earlier, unrelated moment) -- caught by visually
# verifying a built image against its own bbox annotation before use.
FRAME_STRIDE = {V2: 2, V1: 1, V3: 1}

# One representative rim bbox per video (cx, cy, r), from direct RF-DETR
# rim detections already collected this session -- static camera, rim
# position doesn't move within a video.
RIM_BY_VIDEO = {
    V2: (725.0, 139.5, 32.0),
    V1: (154.0, 128.0, 38.0),
    V3: (255.0, 89.0, 43.0),
}

REPEAT_FACTOR = 8  # oversampling factor for the V2 hard-negative-window material


class Builder:
    def __init__(self):
        self.images = []
        self.annotations = []
        self.next_img_id = 1
        self.next_ann_id = 1
        self._caps = {}
        self._frame_cache = {}

    def _cap(self, video_path: Path):
        key = str(video_path)
        if key not in self._caps:
            self._caps[key] = cv2.VideoCapture(key)
        return self._caps[key]

    def _read(self, video_path: Path, frame_index: int):
        """``frame_index`` is always an ANALYSIS-pipeline index; converted to
        the raw source frame number via FRAME_STRIDE before seeking."""
        key = (str(video_path), frame_index)
        if key in self._frame_cache:
            return self._frame_cache[key]
        source_frame_index = frame_index * FRAME_STRIDE[video_path]
        cap = self._cap(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"could not read frame {frame_index} from {video_path}")
        if video_path in ANALYSIS_SIZE:
            frame = cv2.resize(frame, ANALYSIS_SIZE[video_path], interpolation=cv2.INTER_AREA)
        self._frame_cache[key] = frame
        return frame

    def add_full_frame_positive(self, video_path: Path, frame_index: int, tag: str,
                                  bx: float, by: float, bw: float, bh: float, repeats: int = 1):
        """Writes the image file ONCE, but adds `repeats` distinct COCO
        image_id entries (each with its own ball+rim annotations) pointing
        at that same file -- the oversampling mechanism. Returns the list
        of new image_ids."""
        frame = self._read(video_path, frame_index)
        h, w = frame.shape[:2]
        fname = f"{tag}_f{frame_index}.jpg"
        if not (IMAGES_DIR / fname).exists():
            cv2.imwrite(str(IMAGES_DIR / fname), frame)

        rcx, rcy, rr = RIM_BY_VIDEO[video_path]
        ids = []
        for _ in range(repeats):
            img_id = self.next_img_id
            self.next_img_id += 1
            ids.append(img_id)
            self.images.append({"id": img_id, "file_name": fname, "width": w, "height": h})

            bx1, by1 = bx - bw / 2, by - bh / 2
            self.annotations.append({
                "id": self.next_ann_id, "image_id": img_id, "category_id": BALL_CAT_ID,
                "bbox": [round(bx1, 1), round(by1, 1), round(bw, 1), round(bh, 1)],
                "area": round(bw * bh, 1), "iscrowd": 0,
            })
            self.next_ann_id += 1

            rx1, ry1, rw_, rh_ = rcx - rr, rcy - rr, 2 * rr, 2 * rr
            self.annotations.append({
                "id": self.next_ann_id, "image_id": img_id, "category_id": RIM_CAT_ID,
                "bbox": [round(rx1, 1), round(ry1, 1), round(rw_, 1), round(rh_, 1)],
                "area": round(rw_ * rh_, 1), "iscrowd": 0,
            })
            self.next_ann_id += 1
        return ids

    def write_train_only(self):
        (OUT_DIR / "train").mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "train" / "_annotations.coco.json").write_text(
            json.dumps({"images": self.images, "annotations": self.annotations, "categories": CATEGORIES}, indent=2),
            encoding="utf-8",
        )
        print(f"train: {len(self.images)} image slots ({len(set(im['file_name'] for im in self.images))} unique files), "
              f"{len(self.annotations)} annotations")


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    b = Builder()
    manifest = []

    # ---- V2 training windows: conservative, pre-drift, model-confirmed-correct frames ----
    # (frame, bx, by, bw, bh) per window -- all `picked_source == 'detected'`
    # in the original checkpoint's own trace, all strictly before that
    # window's velocity-drift trigger frame (W1<52->drift@59, W2<324->drift@331ish,
    # W3<545 -- restricted further, see module docstring, W4<1354->drift@1360ish).
    W1 = [(35,177.3,358.2,35.0,31.1),(36,177.3,358.4,35.6,31.4),(37,177.3,358.9,36.2,31.3),
          (38,177.8,359.2,36.0,31.4),(39,178.6,359.9,35.7,31.6),(40,179.5,361.5,34.9,30.8),
          (41,180.6,362.4,34.7,31.8),(42,181.9,364.2,33.9,31.1),(43,183.3,365.9,33.6,30.0),
          (44,184.9,368.2,34.7,30.0),(45,186.4,370.2,34.0,29.7),(46,188.5,371.6,34.3,30.7),
          (47,191.4,372.4,33.5,29.5),(48,194.4,370.3,34.0,30.5)]
    W2 = [(310,161.9,369.7,33.2,31.5),(311,161.2,369.4,34.3,32.2),(312,160.8,369.7,34.4,32.1),
          (313,160.7,369.8,34.4,31.7),(314,160.1,370.2,34.8,32.4),(315,160.0,371.0,34.2,33.1),
          (316,159.2,372.2,34.9,33.4),(317,159.5,374.0,34.9,32.8),(318,161.5,376.7,33.8,32.4),
          (319,163.4,379.0,35.0,32.3),(320,166.3,380.0,34.5,31.9)]
    # W3 range extended 540-552 (was conservatively cut at 544 before the
    # frame-index bug below was found and fixed): direct visual verification
    # at the corrected frames showed a continuous, genuine held-ball ->
    # real-shot-release sequence all the way to 552 (confirmed: frame 552
    # shows the player mid-release, ball overhead) -- not the artifact.
    W3 = [(540,149.9,371.8,34.6,32.1),(541,152.5,372.9,35.6,31.7),(542,155.5,372.5,36.0,31.6),
          (543,160.1,368.0,35.9,32.1),(544,162.3,359.3,35.2,30.2),(545,162.9,347.0,33.9,30.4),
          (546,160.3,334.1,34.7,29.0),(547,157.8,320.2,33.6,29.6),(548,155.7,306.2,36.8,29.8),
          (549,157.1,290.9,35.4,30.0),(550,160.3,273.2,33.3,30.2),(551,172.1,251.3,33.3,32.1),
          (552,187.4,226.2,36.5,31.3)]
    W4 = [(1348,167.5,378.7,34.7,30.5),(1349,170.8,379.4,35.4,30.0),(1350,175.4,378.6,34.2,28.0),
          (1351,178.9,371.8,35.5,30.3),(1352,181.0,360.9,35.7,30.3),(1353,180.5,347.7,34.8,30.7)]

    for label, frames in [("W1", W1), ("W2", W2), ("W3", W3), ("W4", W4)]:
        for fi, bx, by, bw, bh in frames:
            ids = b.add_full_frame_positive(V2, fi, f"v2_{label}", bx, by, bw, bh, repeats=REPEAT_FACTOR)
            manifest.append({"video": "V2", "window": label, "frame_index": fi, "repeats": REPEAT_FACTOR, "image_ids": ids})

    n_v2_base = len(W1) + len(W2) + len(W3) + len(W4)
    n_v2_slots = n_v2_base * REPEAT_FACTOR

    # ---- Genuine V1/V3 positives (recall protection, NOT oversampled) ----
    genuine = [
        (V1, 67, 721.4, 389.0, 33.2, 38.6), (V1, 70, 705.4, 366.1, 34.0, 37.4), (V1, 74, 713.4, 307.7, 32.6, 34.9),
        (V1, 1398, 712.1, 320.7, 32.6, 34.2), (V1, 1402, 687.5, 255.3, 34.3, 35.7),
        (V3, 475, 759.5, 338.5, 42.2, 44.2), (V3, 479, 739.1, 318.5, 40.5, 43.8), (V3, 483, 739.6, 267.5, 40.7, 40.6),
    ]
    for video, fi, bx, by, bw, bh in genuine:
        tag = "v1_genuine" if video == V1 else "v3_genuine"
        ids = b.add_full_frame_positive(video, fi, tag, bx, by, bw, bh, repeats=1)
        manifest.append({"video": tag.split("_")[0].upper(), "window": "genuine", "frame_index": fi, "repeats": 1, "image_ids": ids})

    b.write_train_only()
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nV2 hard-negative-window base images: {n_v2_base} unique, x{REPEAT_FACTOR} repeats = {n_v2_slots} slots")
    print(f"Genuine V1/V3 positives: {len(genuine)} (not oversampled)")
    print("Held out entirely (never in this dataset): V2 arm~1541 window (W5) + temporal neighborhood.")
    print("No original-dataset images touched; no valid-split additions (valid stays the pure original set).")


if __name__ == "__main__":
    main()
