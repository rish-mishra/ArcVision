"""
One-off diagnostic (not part of any pipeline): hooks RF-DETR's underlying
model to capture raw pred_logits/pred_boxes (every query, every class,
BEFORE thresholding/NMS/top-k selection) for a specific list of frames,
and reports, for the query nearest the already-known reported detection:
its ball/rim sigmoid probabilities, and how many OTHER queries propose a
box in the same local neighborhood (competing/unstable predictions the
normal extraction path never surfaces).

Usage:
    .venv\\Scripts\\python scripts\\diagnose_rfdetr_raw_logits.py video.mp4 out.csv frame1,frame2,...
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def box_cxcywh_to_xyxy_px(boxes_norm: torch.Tensor, w: float, h: float) -> torch.Tensor:
    cx, cy, bw, bh = boxes_norm.unbind(-1)
    x1 = (cx - 0.5 * bw) * w
    y1 = (cy - 0.5 * bh) * h
    x2 = (cx + 0.5 * bw) * w
    y2 = (cy + 0.5 * bh) * h
    return torch.stack([x1, y1, x2, y2], dim=-1)


def main():
    video_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2])
    target_frames = set(int(x) for x in sys.argv[3].split(","))
    # known_xy: optional "frame:x:y" quadruples appended as extra args, for matching
    # the query nearest an already-established detection position.
    known_xy = {}
    for extra in sys.argv[4:]:
        fi, x, y = extra.split(":")
        known_xy[int(fi)] = (float(x), float(y))

    meta = validate_video(video_path)
    reader = FrameReader(meta)

    import os
    checkpoint_override = os.environ.get("RFDETR_CHECKPOINT_OVERRIDE")
    rfdetr_checkpoint = Path(checkpoint_override) if checkpoint_override else (MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name)
    rf = RFDETRBallRimDetector(str(rfdetr_checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()

    captured = {}

    def hook(module, inp, out):
        captured["raw"] = out

    underlying_module = rf.model.model.model  # RFDETRBallRimDetector.model -> RFDETRSmall.model (ModelContext) -> ModelContext.model (LWDETR nn.Module)
    handle = underlying_module.register_forward_hook(hook)

    rows = []
    frames_list = list(reader)
    for af in frames_list:
        if af.frame_index not in target_frames:
            continue
        h, w = af.image.shape[0], af.image.shape[1]
        rf_raw = rf.predict_raw(af.image)  # triggers the hook; also gives us the normal extraction for cross-check
        validated = rf.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)

        raw = captured.get("raw")
        if isinstance(raw, dict):
            pred_boxes, pred_logits = raw["pred_boxes"], raw["pred_logits"]
        else:
            pred_boxes, pred_logits = raw[0], raw[1]  # (1,Q,4), (1,Q,C)
        prob = pred_logits.sigmoid()[0].cpu()  # (Q,C)
        boxes_px = box_cxcywh_to_xyxy_px(pred_boxes[0].cpu(), w, h)  # (Q,4)
        centers = torch.stack([(boxes_px[:, 0] + boxes_px[:, 2]) / 2, (boxes_px[:, 1] + boxes_px[:, 3]) / 2], dim=-1)

        ball_prob = prob[:, 0]
        rim_prob = prob[:, 1] if prob.shape[1] > 1 else torch.zeros_like(ball_prob)

        # Anchor: either the extraction's own top ball detection, or a caller-supplied (x,y).
        if af.frame_index in known_xy:
            anchor = torch.tensor(known_xy[af.frame_index])
        elif validated:
            anchor = torch.tensor(validated[0].center)
        else:
            top_q = int(torch.argmax(ball_prob))
            anchor = centers[top_q]

        dists = ((centers - anchor) ** 2).sum(-1).sqrt()
        nearest_q = int(torch.argmin(dists))

        # Local neighborhood: queries whose box center sits within 40px of the anchor.
        local_mask = dists < 40.0
        n_local = int(local_mask.sum())
        local_ball_probs = ball_prob[local_mask]
        local_rim_probs = rim_prob[local_mask]

        # Global instability: how many queries anywhere in the frame propose ball_prob > 0.1
        # (i.e., how "busy"/multi-modal the ball-class response surface is this frame).
        n_global_ball_gt_01 = int((ball_prob > 0.1).sum())
        n_global_ball_gt_03 = int((ball_prob > 0.3).sum())

        rows.append({
            "frame_index": af.frame_index,
            "anchor_x": round(float(anchor[0]), 1), "anchor_y": round(float(anchor[1]), 1),
            "nearest_q_ball_prob": round(float(ball_prob[nearest_q]), 4),
            "nearest_q_rim_prob": round(float(rim_prob[nearest_q]), 4),
            "nearest_q_dist_px": round(float(dists[nearest_q]), 1),
            "n_queries_within_40px": n_local,
            "local_ball_prob_max": round(float(local_ball_probs.max()), 4) if n_local else "",
            "local_ball_prob_2nd_max": round(float(torch.topk(local_ball_probs, min(2, n_local)).values[-1]), 4) if n_local >= 2 else "",
            "local_rim_prob_max": round(float(local_rim_probs.max()), 4) if n_local else "",
            "n_global_ball_gt_0.1": n_global_ball_gt_01,
            "n_global_ball_gt_0.3": n_global_ball_gt_03,
            "top1_ball_prob_anywhere": round(float(ball_prob.max()), 4),
        })
        print(f"frame {af.frame_index}: {rows[-1]}")

    handle.remove()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
