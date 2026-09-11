"""
Aggregates per-frame hoop/rim circle candidates -- from one or more
detector SOURCES (classical color/Hough, learned open-vocabulary, or any
future replacement) -- into a single stable hoop location, since the
camera is assumed mostly static for the whole session.

Each candidate must carry the FRAME it came from. This matters more than
it might look: a single frame can legitimately produce more than one
candidate for the very same physical rim (e.g. both a contour-based and a
Hough-circle hit, or two overlapping open-vocabulary class prompts firing
on the same box), and confusing "number of candidates" with "number of
independent observations" lets one frame's duplicate detections outweigh
several other frames' single, genuine detections. This was found on a real
video where a moving object (almost certainly the ball in the shooter's
hand) produced two near-duplicate high-confidence boxes within a couple of
individual frames, which very nearly outscored the true hoop -- seen
consistently, but only once per frame, across many more frames. Counting
DISTINCT FRAMES per cluster (not raw candidate count) is what makes a
truly static, repeatedly-observed hoop win over a spatially-scattered
moving false positive as more frames are sampled, which is the whole
point of "the camera is static, so aggregate across frames."
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.config import CONFIG
from app.vision.types import HoopLocation

# (frame_index, x, y, radius, detector_confidence, source_label)
Candidate = Tuple[int, float, float, float, float, str]


def _cluster(candidates: List[Candidate], distance_px: float) -> List[List[Candidate]]:
    clusters: List[List[Candidate]] = []
    for c in candidates:
        placed = False
        for cluster in clusters:
            cx = sum(p[1] for p in cluster) / len(cluster)
            cy = sum(p[2] for p in cluster) / len(cluster)
            if ((c[1] - cx) ** 2 + (c[2] - cy) ** 2) ** 0.5 <= distance_px:
                cluster.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])
    return clusters


def _best_per_frame(cluster: List[Candidate]) -> Dict[int, Candidate]:
    """Collapse a cluster to its single highest-confidence candidate per
    frame, so a frame that happened to contribute multiple overlapping
    boxes counts once, at its best evidence -- not once per box."""
    best: Dict[int, Candidate] = {}
    for c in cluster:
        frame_index = c[0]
        if frame_index not in best or c[4] > best[frame_index][4]:
            best[frame_index] = c
    return best


def aggregate_hoop_candidates(candidates: List[Candidate]) -> Optional[HoopLocation]:
    """
    candidates: every detection found across all sampled frames, from any
    number of detector sources, each tagged with its originating frame
    index. Returns None if no candidates were found at all.
    """
    cfg = CONFIG.hoop
    if not candidates:
        return None

    clusters = _cluster(candidates, cfg.cluster_distance_px)
    deduped = [_best_per_frame(cl) for cl in clusters]
    # Rank by (distinct frames seen, mean per-frame confidence) -- frame
    # count first, since that's the actual temporal-consistency signal;
    # confidence only breaks ties among clusters with equally many frames.
    deduped.sort(key=lambda d: (len(d), sum(c[4] for c in d.values()) / len(d)), reverse=True)
    best = list(deduped[0].values())

    cx = sum(p[1] for p in best) / len(best)
    cy = sum(p[2] for p in best) / len(best)
    r = sum(p[3] for p in best) / len(best)
    votes = len(best)  # number of distinct frames, after per-frame dedup

    agreement = min(1.0, votes / max(cfg.min_votes_for_confidence, 1))
    mean_detector_conf = sum(p[4] for p in best) / len(best)
    confidence = 0.6 * agreement + 0.4 * mean_detector_conf

    sources = sorted({p[5] for p in best})

    return HoopLocation(
        rim_center_x=cx,
        rim_center_y=cy,
        rim_radius_px=r,
        confidence=round(confidence, 3),
        votes=votes,
        method="+".join(sources),
    )
