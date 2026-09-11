"""
READ-ONLY diagnostic script: extracts rim-interaction contact-sheet images for
selected shots from arcvision_demo_final.mov and real_test_04.mov, for the
human-visibility audit in docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md. Crops a
region around the hoop (already-known rim center/radius from the outcome
forensic reports) for a window of frames spanning approach -> rim interaction
-> immediate exit, and tiles them into a single labeled PNG per shot. Makes no
production code change; reads video frames directly via cv2/FrameReader.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.video_io import FrameReader, validate_video

OUT_DIR = Path("data/diagnostics/rim_interaction_clips")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TILE_SIZE = 220  # upscaled crop tile, px
COLS = 6


def shot_frame_window(shot: dict, pad_before: int = 12, pad_after: int = 12):
    a_frames = [c["a_frame"] for c in shot["candidate_pairs"]]
    b_frames = [c["b_frame"] for c in shot["candidate_pairs"]]
    fd_frames = [p["frame"] for p in shot["far_descent_detail"]]
    all_frames = a_frames + b_frames + fd_frames
    if not all_frames:
        # No candidates at all -- fall back to a window around start_frame.
        lo = shot["start_frame"]
        hi = shot["start_frame"] + 60
    else:
        lo = min(all_frames) - pad_before
        hi = max(all_frames) + pad_after
    return max(lo, shot["start_frame"] - pad_before), min(hi, shot["end_frame"])


def sample_frames(lo: int, hi: int, max_frames: int = 24):
    span = hi - lo
    if span <= 0:
        return [lo]
    n = min(max_frames, span + 1)
    step = max(1, round(span / max(1, n - 1)))
    frames = list(range(lo, hi + 1, step))
    if frames[-1] != hi:
        frames.append(hi)
    return frames


def build_contact_sheet(video_path: Path, hoop_cx: float, hoop_cy: float, hoop_r: float,
                          frame_specs: dict, fps: float, out_prefix: str):
    """frame_specs: {frame_index: label_suffix}. Single pass over the video."""
    wanted = set(frame_specs.keys())
    if not wanted:
        return {}
    meta = validate_video(video_path)
    reader = FrameReader(meta)
    crop_half = int(round(hoop_r * 4.2))
    x0, x1 = int(hoop_cx - crop_half), int(hoop_cx + crop_half)
    y0, y1 = int(hoop_cy - crop_half), int(hoop_cy + crop_half)

    crops = {}
    max_wanted = max(wanted)
    for af in reader:
        if af.frame_index > max_wanted:
            break
        if af.frame_index not in wanted:
            continue
        img = af.image
        h, w = img.shape[:2]
        cx0, cx1 = max(0, x0), min(w, x1)
        cy0, cy1 = max(0, y0), min(h, y1)
        crop = img[cy0:cy1, cx0:cx1].copy()
        # pad to a fixed square if clipped at frame edge
        pad_l, pad_t = cx0 - x0, cy0 - y0
        pad_r, pad_b = x1 - cx1, y1 - cy1
        if pad_l or pad_t or pad_r or pad_b:
            crop = cv2.copyMakeBorder(crop, max(0, pad_t), max(0, pad_b), max(0, pad_l), max(0, pad_r),
                                        cv2.BORDER_CONSTANT, value=(40, 40, 40))
        crop = cv2.resize(crop, (TILE_SIZE, TILE_SIZE), interpolation=cv2.INTER_NEAREST)
        crops[af.frame_index] = crop

    return crops


def compose_sheet(crops: dict, order: list, labels: dict, out_path: Path, title: str):
    tiles = []
    for fi in order:
        crop = crops.get(fi)
        if crop is None:
            continue
        tile = crop.copy()
        cv2.rectangle(tile, (0, 0), (TILE_SIZE - 1, 24), (0, 0, 0), -1)
        cv2.putText(tile, labels[fi], (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    if not tiles:
        return
    rows = []
    for i in range(0, len(tiles), COLS):
        row_tiles = tiles[i:i + COLS]
        while len(row_tiles) < COLS:
            row_tiles.append(np.full((TILE_SIZE, TILE_SIZE, 3), 20, dtype=np.uint8))
        rows.append(np.hstack(row_tiles))
    sheet = np.vstack(rows)
    banner = np.full((30, sheet.shape[1], 3), (30, 30, 30), dtype=np.uint8)
    cv2.putText(banner, title, (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    sheet = np.vstack([banner, sheet])
    cv2.imwrite(str(out_path), sheet)
    print(f"Saved: {out_path}")


def process_video(video_path: Path, report_path: Path, hoop_cx: float, hoop_cy: float, hoop_r: float,
                    shot_indices: list, out_prefix: str, video_label: str):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    by_idx = {s["shot_index"]: s for s in report}

    meta = validate_video(video_path)
    fps = meta.fps

    all_frame_specs = {}
    per_shot_frames = {}
    for idx in shot_indices:
        shot = by_idx.get(idx)
        if shot is None:
            print(f"WARNING: shot {idx} not found in {report_path}")
            continue
        lo, hi = shot_frame_window(shot)
        frames = sample_frames(lo, hi)
        per_shot_frames[idx] = frames
        for fi in frames:
            all_frame_specs[fi] = f"f{fi} t={fi/fps:.2f}s"

    print(f"{video_label}: extracting {len(all_frame_specs)} unique frames across {len(per_shot_frames)} shots...")
    crops = build_contact_sheet(video_path, hoop_cx, hoop_cy, hoop_r, all_frame_specs, fps, out_prefix)

    for idx, frames in per_shot_frames.items():
        shot = by_idx[idx]
        title = (f"{video_label} shot {idx}  pred={shot['outcome']}({shot['outcome_confidence']:.2f})  "
                  f"reason={shot['outcome_reason']}")
        out_path = OUT_DIR / f"{out_prefix}_shot{idx:02d}.png"
        compose_sheet(crops, frames, {fi: f"f{fi} {fi/fps:.2f}s" for fi in frames}, out_path, title)


def main():
    process_video(
        Path("arcvision_demo_final.mov").resolve(),
        Path("data/diagnostics/arcvision_demo_final_forensic/shot_forensic_report.json"),
        300.7, 146.2, 28.2,
        list(range(1, 12)), "showcase", "SHOWCASE",
    )
    process_video(
        Path("real_test_04.mov").resolve(),
        Path("data/diagnostics/video4_outcome_forensic/shot_forensic_report.json"),
        262.7, 154.5, 29.9,
        [3, 4, 9, 11, 12, 15, 17, 19, 21], "v4", "V4",
    )


if __name__ == "__main__":
    main()
