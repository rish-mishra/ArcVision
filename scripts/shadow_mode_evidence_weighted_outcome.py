"""
READ-ONLY shadow-mode experiment (see this session's architectural review of
app/events/outcome_detector.py). Tests whether an evidence-WEIGHTED
alternative to the current MADE crossing search -- which today rejects a
candidate crossing outright if drift or occlusion-dip individually fail a
fitted cutoff -- generalizes better across the frozen video corpus.

This module does not import-and-mutate, monkeypatch, or otherwise alter
app.events.outcome_detector. It imports its already-existing helper
functions (preprocessing: reliable-point filtering, outlier rejection, apex
finding, band sizing, occlusion-dip computation) UNCHANGED and read-only,
and duplicates its MISS-branch logic verbatim (unavoidable: that logic is
private module-level code, not separately importable, and is explicitly
OUT of scope for this experiment -- only the MADE crossing-search step is
being tested). No production file is edited by this script or by running it.

Design (per the architectural review, Q10):
  - All physically-grounded hard prerequisites are preserved exactly:
    chronological above-then-below ordering, a bounded time window for the
    pair (max_seconds_through_rim -- an existing constant, reused, not new),
    no observed deflection out of the wide zone between the pair, and
    reliable-source-only points throughout (inherited from the existing
    _reliable()/_reject_trajectory_outliers() preprocessing).
  - Every (above, below) pair satisfying those prerequisites is scored
    (not just the first chronological one), using the EXACT SAME quality
    formula production already computes (drift_quality, occlusion_quality,
    gap_quality, approach_quality, exit_quality, source_quality) -- the only
    change is that drift and occlusion no longer gate candidacy by
    themselves; they contribute to the composite score instead.
  - The best-scoring candidate is compared against the SAME
    min_outcome_confidence_to_report bar production already uses. No new
    constant is introduced anywhere in this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.config import CONFIG
from app.events.outcome_detector import (
    OutcomeResult, ShotOutcome,
    _above_rim, _below_rim, _find_apex, _in_band, _interaction_band,
    _near_rim_height, _occlusion_dip_ratio, _reject_trajectory_outliers, _reliable, _wide_zone,
)
from app.vision.types import BallObservation, DataSource, HoopLocation


@dataclass
class CandidateInfo:
    a_frame: int
    b_frame: int
    drift_px: float
    dip_ratio: float
    score: float


@dataclass
class ShadowOutcomeResult(OutcomeResult):
    n_candidates_evaluated: int = 0
    chosen_candidate: Optional[CandidateInfo] = None
    all_candidates: List[CandidateInfo] = field(default_factory=list)


def detect_outcome_shadow(trajectory: List[BallObservation], hoop: Optional[HoopLocation],
                           cfg=None) -> ShadowOutcomeResult:
    cfg = cfg or CONFIG.outcome

    if hoop is None or hoop.confidence < cfg.min_hoop_confidence_to_attempt:
        return ShadowOutcomeResult(ShotOutcome.UNKNOWN, 0.0, "hoop_location_not_reliable")

    points = sorted(trajectory, key=lambda p: p.frame_index)
    reliable = _reliable(points)
    n_before_outlier_rejection = len(reliable)
    reliable = _reject_trajectory_outliers(reliable, cfg)
    n_outliers_rejected = n_before_outlier_rejection - len(reliable)
    n_detected = sum(1 for p in reliable if p.source == DataSource.DETECTED)
    n_interp = sum(1 for p in reliable if p.source == DataSource.INTERPOLATED)
    n_predicted = sum(1 for p in points if p.source == DataSource.PREDICTED)

    track_stability = (n_detected / len(reliable)) if reliable else 0.0
    stability_factor = 0.5 + 0.5 * track_stability

    evidence = {
        "n_reliable_points": len(reliable), "n_detected": n_detected, "n_interpolated": n_interp,
        "n_predicted_only": n_predicted, "hoop_confidence": hoop.confidence,
        "n_trajectory_outliers_rejected": n_outliers_rejected,
        "track_stability": round(track_stability, 3),
    }

    if len(reliable) < cfg.min_reliable_points_to_attempt:
        evidence["why"] = "too few directly-observed/interpolated ball points to reason about at all"
        return ShadowOutcomeResult(ShotOutcome.UNKNOWN, 0.0, "insufficient_ball_trajectory_data", evidence=evidence)

    apex = _find_apex(reliable)
    apex_is_endpoint = apex is reliable[0] or apex is reliable[-1]
    ascent_pts = [p for p in reliable if p.frame_index <= apex.frame_index]
    descent_pts = [p for p in reliable if p.frame_index >= apex.frame_index]
    evidence["apex_frame"] = apex.frame_index
    evidence["apex_observed_as_endpoint"] = apex_is_endpoint
    evidence["n_ascent_points"] = len(ascent_pts)
    evidence["n_descent_points"] = len(descent_pts)

    if apex_is_endpoint and len(reliable) < cfg.min_reliable_points_when_apex_unconfirmed:
        evidence["why"] = "apex not clearly bracketed by observed points, and too few points to compensate"
        return ShadowOutcomeResult(ShotOutcome.UNKNOWN, 0.0, "apex_not_reliably_observed", evidence=evidence)

    if len(descent_pts) < cfg.min_descent_points_to_attempt:
        evidence["why"] = "descent phase has too few observed points to assess rim interaction"
        return ShadowOutcomeResult(ShotOutcome.UNKNOWN, 0.0, "insufficient_descent_observation", evidence=evidence)

    avg_radius = sum(p.radius_px for p in reliable) / len(reliable)
    tight_band = _interaction_band(hoop, avg_radius, cfg)
    wide_band = _wide_zone(hoop, avg_radius, cfg)
    evidence["tight_band_px"] = round(tight_band, 1)
    evidence["wide_band_px"] = round(wide_band, 1)

    descent_above_tight = [p for p in descent_pts if _above_rim(p, hoop) and _in_band(p, hoop, tight_band)]
    descent_below_tight = [p for p in descent_pts if _below_rim(p, hoop) and _in_band(p, hoop, tight_band)]

    # ================= MADE candidate search (evidence-weighted) =================
    # Hard prerequisites kept exactly as production: chronological order,
    # bounded time window, no deflection observed between the pair. Drift
    # and occlusion are no longer independent pass/fail gates -- both
    # contribute continuously to the same composite score production
    # already computes, evaluated over EVERY qualifying pair rather than
    # just the first chronologically found.
    max_drift = hoop.rim_radius_px * cfg.max_crossing_drift_frac_of_rim_radius
    candidates: List[CandidateInfo] = []
    best: Optional[CandidateInfo] = None
    best_evidence_extra = {}

    for a in descent_above_tight:
        later_below = [b for b in descent_below_tight
                        if b.frame_index > a.frame_index
                        and (b.timestamp_sec - a.timestamp_sec) <= cfg.max_seconds_through_rim]
        for b in later_below:
            between = [p for p in reliable if a.frame_index < p.frame_index < b.frame_index]
            deflected_between = any(not _in_band(p, hoop, wide_band) for p in between)
            if deflected_between:
                continue  # hard prerequisite: no observed escape from the wide zone mid-crossing

            drift = abs(b.center_x - a.center_x)
            crossing_span = [a] + between + [b]
            dip_ratio = _occlusion_dip_ratio(crossing_span, points)

            gap = b.frame_index - a.frame_index
            gap_seconds = b.timestamp_sec - a.timestamp_sec
            gap_quality = 1.0 - (gap_seconds / (cfg.max_seconds_through_rim + 1e-6))
            drift_quality = 1.0 - (drift / max_drift) if max_drift > 0 else 0.0
            occlusion_quality = 1.0 - (dip_ratio / cfg.min_occlusion_dip_frac)
            approach_quality = min(1.0, len(descent_above_tight) / max(cfg.min_points_above, 1))
            exit_quality = min(1.0, len(descent_below_tight) / max(cfg.min_points_below, 1))
            source_quality = 1.0 if (a.source == DataSource.DETECTED and b.source == DataSource.DETECTED) else 0.8

            confidence = (0.12 + 0.20 * drift_quality + 0.20 * occlusion_quality + 0.10 * approach_quality
                           + 0.08 * exit_quality + 0.15 * gap_quality + 0.15 * source_quality
                           ) * (0.5 + 0.5 * hoop.confidence) * stability_factor
            confidence = max(0.0, min(1.0, confidence))

            cand = CandidateInfo(a_frame=a.frame_index, b_frame=b.frame_index,
                                   drift_px=round(drift, 1), dip_ratio=round(dip_ratio, 3),
                                   score=round(confidence, 3))
            candidates.append(cand)
            if best is None or cand.score > best.score:
                best = cand
                best_evidence_extra = {
                    "crossing_above_frame": a.frame_index, "crossing_below_frame": b.frame_index,
                    "points_between": len(between), "crossing_drift_px": round(drift, 1),
                    "max_crossing_drift_px": round(max_drift, 1), "crossing_gap_seconds": round(gap_seconds, 3),
                    "occlusion_dip_ratio": round(dip_ratio, 3),
                }

    if best is not None:
        evidence.update(best_evidence_extra)
        if best.score < cfg.min_outcome_confidence_to_report:
            return ShadowOutcomeResult(
                ShotOutcome.UNKNOWN, best.score, "rim_crossing_observed_but_low_confidence",
                evidence=evidence, n_candidates_evaluated=len(candidates),
                chosen_candidate=best, all_candidates=candidates,
            )
        return ShadowOutcomeResult(
            ShotOutcome.MADE, best.score, "ball_crossed_rim_band_top_to_bottom",
            evidence=evidence, n_candidates_evaluated=len(candidates),
            chosen_candidate=best, all_candidates=candidates,
        )

    # ================= MISS (verbatim copy of production's positive-evidence logic) =================
    descent_near_wide_above = [p for p in descent_pts if _in_band(p, hoop, wide_band) and _above_rim(p, hoop)]
    if descent_near_wide_above:
        last_approach = descent_near_wide_above[-1]
        after = [p for p in reliable if p.frame_index > last_approach.frame_index
                 and (p.timestamp_sec - last_approach.timestamp_sec) <= cfg.max_seconds_deflection_after_approach]
        deflected = [p for p in after if not _in_band(p, hoop, wide_band)]
        if deflected and len(descent_near_wide_above) >= cfg.min_points_above:
            deflection_frame = deflected[0]
            dt = deflection_frame.timestamp_sec - last_approach.timestamp_sec
            promptness_quality = 1.0 - (dt / (cfg.max_seconds_deflection_after_approach + 1e-6))
            evidence.update({
                "approach_points": len(descent_near_wide_above), "deflection_frame": deflection_frame.frame_index,
                "deflection_seconds_after_approach": round(dt, 3),
            })
            approach_quality = min(1.0, len(descent_near_wide_above) / max(cfg.min_points_above, 1))
            confidence = (0.30 + 0.30 * promptness_quality + 0.20 * approach_quality
                          + 0.20 * min(1.0, 0.08 * len(descent_near_wide_above))) * (0.5 + 0.5 * hoop.confidence) * stability_factor
            confidence = min(1.0, confidence)
            if confidence < cfg.min_outcome_confidence_to_report:
                return ShadowOutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                             "possible_deflection_but_low_confidence", evidence=evidence)
            return ShadowOutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                                        "ball_approached_rim_then_deflected_away",
                                        points_above=len(descent_near_wide_above), evidence=evidence)

    near_apex_descent = [p for p in descent_pts
                          if (p.timestamp_sec - apex.timestamp_sec) <= cfg.max_seconds_from_apex_for_descent_evidence]
    near_height_pts = [p for p in near_apex_descent if _near_rim_height(p, hoop, cfg)]
    beside = [p for p in near_height_pts if not _in_band(p, hoop, wide_band)]
    if beside and len(descent_pts) >= cfg.min_descent_points_to_attempt:
        confidence = min(1.0, 0.5 + 0.05 * len(beside)) * (0.5 + 0.5 * hoop.confidence) * stability_factor
        evidence["beside_points"] = len(beside)
        if confidence < cfg.min_outcome_confidence_to_report:
            return ShadowOutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                         "possible_miss_beside_hoop_but_low_confidence", evidence=evidence)
        return ShadowOutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                                    "ball_passed_beside_hoop_at_rim_height", evidence=evidence)

    far_descent = [p for p in near_apex_descent if _below_rim(p, hoop) and not _in_band(p, hoop, wide_band)]
    had_height_context = any(p.center_y <= hoop.rim_center_y + wide_band for p in ascent_pts + descent_pts)
    if far_descent and had_height_context and len(descent_pts) >= cfg.min_descent_points_to_attempt:
        confidence = min(1.0, 0.4 + 0.05 * len(far_descent)) * (0.5 + 0.5 * hoop.confidence) * stability_factor
        evidence["far_descent_points"] = len(far_descent)
        if confidence < cfg.min_outcome_confidence_to_report:
            return ShadowOutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                         "trajectory_diverged_but_low_confidence", evidence=evidence)
        return ShadowOutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                                    "ball_descended_well_clear_of_hoop", evidence=evidence)

    evidence["why"] = "no phase sequence met the positive-evidence bar for MADE or MISSED"
    return ShadowOutcomeResult(ShotOutcome.UNKNOWN, 0.0, "rim_interaction_not_sufficiently_observed", evidence=evidence)
