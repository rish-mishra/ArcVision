"""
ArcVision Coach: synthesizes an already-computed session's consistency,
makes-vs-misses, and quality signals into a short, personalized coaching
summary. This module computes NOTHING new about the shot itself -- it only
reads app.analytics.consistency / makes_vs_misses / session_summary output
(all already produced by app.pipeline.orchestrator.run_pipeline before this
is called) and decides which of those already-computed, already-gated
findings are strong enough to present as coaching, and in what order.

Design constraints (see docs/ARCVISION_REDESIGN_PLAN.md for the full
rationale this implements):

- Never invents an "ideal" value for any metric. Every entry in
  app.analytics.metric_extractors.METRICS carries lower_is_better=None by
  design, and this module never treats a raw metric value as good/bad in
  isolation. All coaching is self-referential -- this player's makes vs.
  their own misses, or this metric's variability vs. their own other
  metrics -- never a claim about correct form in general.
- Reuses every existing eligibility/confidence gate verbatim (minimum
  sample sizes in consistency.py/makes_vs_misses.py, the effect-size labels
  from stats_utils.py, feedback.py's own confidence-from-effect tiering,
  and the Confidence.from_score bucketing already used elsewhere in the
  app). No new numeric threshold is introduced anywhere in this file.
- Deterministic: a pure function of the same ShotRecord list every time --
  no randomness, no external calls, no LLM.
- "Evidence" and "coaching cue" are always separate fields. Evidence is a
  restatement of a measured comparison (means, sample sizes, effect size,
  or coefficient of variation) and never contains an imperative. A cue is
  a conservative, generic-basketball-language suggestion built from the
  *direction* of that evidence, never a specific numeric target.
- Weak evidence produces LESS output, not lower-quality output: sections
  with no sufficiently-supported finding say so in plain language rather
  than presenting a shaky one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.analytics.consistency import ConsistencyResult, least_consistent_metrics, most_consistent_metrics
from app.analytics.feedback import _confidence_from_effect
from app.analytics.makes_vs_misses import MakesVsMissesReport, top_differentiators
from app.analytics.metric_extractors import METRICS
from app.analytics.session_summary import SessionSummary
from app.analytics.shot_record import ShotRecord
from app.vision.types import Confidence

_LABEL_TO_KEY = {m.label: m.key for m in METRICS}


@dataclass
class Evidence:
    """A factual, measured statement -- never an instruction. Every number
    quoted in `text` is also available structured in `detail`, so a
    recommendation can always be traced back to the measurement behind it."""
    text: str
    detail: dict = field(default_factory=dict)


@dataclass
class CoachingCue:
    """A conservative, generic-basketball-language suggestion. Deliberately
    never carries a numeric target -- see the module docstring."""
    text: str


@dataclass
class SupportedFinding:
    metric_key: str
    metric_label: str
    evidence: Evidence


@dataclass
class CoachingPriority(SupportedFinding):
    source: str = ""  # "makes_vs_misses" | "consistency"
    confidence: str = "low"  # "high" | "medium" | "low" -- reuses feedback.py's own tiering for the mvm source
    cues: List[CoachingCue] = field(default_factory=list)


@dataclass
class CoachingSummary:
    eligible: bool
    coach_note: str
    strength: Optional[SupportedFinding] = None
    priority: Optional[CoachingPriority] = None
    makes_vs_misses_note: Optional[Evidence] = None
    makes_vs_misses_reason: Optional[str] = None
    consistency_note: Optional[Evidence] = None
    consistency_reason: Optional[str] = None
    confidence: str = "low"  # overall session-level evidence quality
    data_quality_notes: List[str] = field(default_factory=list)


_GENERIC_PRACTICE_CUE = CoachingCue(
    "Video a few reps focused on just this one thing before your next full session, so you can check it directly."
)

# metric_key -> (cue built from a makes-vs-misses difference, cue built from
# a shot-to-shot consistency observation). Both are neutral, generic
# basketball language -- never a numeric target, never phrased as a
# universal ideal.
_METRIC_CUES = {
    "knee_angle_at_load_deg": (
        "Try setting up with the same knee bend you used on your makes before you rise into the shot.",
        "Try setting up with the same knee bend on every shot before you rise.",
    ),
    "knee_angle_at_release_deg": (
        "Try extending your legs the same way at release that you did on your makes.",
        "Try finishing your leg extension the same way on every shot.",
    ),
    "elbow_angle_at_load_deg": (
        "Try starting your shot with the same elbow position you used on your makes.",
        "Try keeping your elbow set-up position consistent shot to shot.",
    ),
    "elbow_angle_at_release_deg": (
        "Try extending your shooting elbow the same way you did on your makes.",
        "Try finishing with the same elbow extension on every shot.",
    ),
    "torso_lean_at_load_deg": (
        "Try matching the torso posture you had at the set point on your makes.",
        "Try keeping your torso posture consistent at the set point.",
    ),
    "torso_lean_at_release_deg": (
        "Try matching the torso posture you had at release on your makes.",
        "Try keeping your torso posture consistent at release.",
    ),
    "release_height_norm": (
        "Try releasing from the same height you used on your makes, rather than varying it shot to shot.",
        "Focus on a repeatable release point rather than consciously aiming for a specific height.",
    ),
    "release_horizontal_offset_norm": (
        "Try releasing the ball from the same position relative to your body that you used on your makes.",
        "Try keeping the ball's release position relative to your body the same shot to shot.",
    ),
    "load_duration_sec": (
        "Try matching the set-up rhythm you used on your makes before you rise into the shot.",
        "Try keeping your set-up timing consistent before you rise into each shot.",
    ),
    "upward_duration_sec": (
        "Try matching the release rhythm you used on your makes.",
        "Try keeping the timing of your rise-to-release motion consistent.",
    ),
    "total_prep_duration_sec": (
        "Try matching the overall shot rhythm you used on your makes.",
        "Try keeping your overall shot rhythm -- set-up through release -- consistent shot to shot.",
    ),
    "apex_height_norm": (
        "Try matching the arc height you had on your makes.",
        "Try keeping your shot's arc height consistent shot to shot.",
    ),
    "trajectory_straightness_ratio": (
        "Try releasing with the same follow-through you used on your makes -- it's closely tied to a straight flight path.",
        "Try keeping your follow-through consistent -- it's closely tied to a straight flight path.",
    ),
}

_MVM_REASON_TEXT = {
    "not_enough_total_shots": "Not enough shots were detected this session to compare makes vs. misses reliably.",
    "not_enough_made_or_missed_shots": (
        "Not enough confidently-made and confidently-missed shots were detected this session to compare them reliably."
    ),
}
_NO_STRONG_DIFFERENCE_TEXT = "No strong measurable difference was found between your makes and misses this session."
_NO_CONSISTENCY_DATA_TEXT = "Not enough shots yet (at least 4 needed for one metric) for shot-to-shot consistency analysis."


def _session_data_quality(summary: SessionSummary) -> Confidence:
    scores = [s for s in (summary.mean_pose_quality, summary.mean_ball_track_quality) if s is not None]
    if not scores:
        return Confidence.EXCLUDED
    return Confidence.from_score(min(scores))


def _direction_phrase(comp) -> str:
    if comp.made_mean is None or comp.missed_mean is None:
        return "differed"
    return "higher on your makes" if comp.made_mean > comp.missed_mean else "higher on your misses"


def _mvm_evidence_text(comp) -> str:
    return (f"{comp.metric_name} averaged {comp.made_mean} on makes (n={comp.made_n}) vs {comp.missed_mean} on "
            f"misses (n={comp.missed_n}) -- {_direction_phrase(comp)}, a {comp.effect_label} difference "
            f"(effect size {comp.effect_size}).")


def _mvm_detail(comp) -> dict:
    return {
        "made_mean": comp.made_mean, "missed_mean": comp.missed_mean,
        "made_n": comp.made_n, "missed_n": comp.missed_n,
        "effect_size": comp.effect_size, "effect_label": comp.effect_label, "p_value": comp.p_value,
    }


def _consistency_evidence_text(c: ConsistencyResult, superlative: str) -> str:
    return f"Your {c.label.lower()} was the {superlative} measurement, relative to your other tracked mechanics, across your {c.n} shots this session (CV={c.coefficient_of_variation})."


def _consistency_detail(c: ConsistencyResult) -> dict:
    return {"coefficient_of_variation": c.coefficient_of_variation, "n": c.n, "mean": c.mean_value, "std_dev": c.std_dev}


def _select_strength(consistency_results: List[ConsistencyResult]) -> Optional[SupportedFinding]:
    top = most_consistent_metrics(consistency_results, top_n=1)
    if not top:
        return None
    c = top[0]
    return SupportedFinding(
        metric_key=c.metric_key, metric_label=c.label,
        evidence=Evidence(text=_consistency_evidence_text(c, "most consistent"), detail=_consistency_detail(c)),
    )


def _select_priority(mvm_report: MakesVsMissesReport, consistency_results: List[ConsistencyResult]) -> Optional[CoachingPriority]:
    # Evidence hierarchy, in order: (1) a makes-vs-misses differentiator
    # strong enough to clear feedback.py's own existing medium/high
    # confidence bar; (2) the least-consistent, sufficiently-sampled
    # metric, as a fallback signal when makes-vs-misses data isn't
    # available or didn't turn up anything strong; (3) nothing -- reported
    # honestly by the caller, not guessed at.
    diffs = top_differentiators(mvm_report, top_n=1)
    if diffs:
        comp = diffs[0]
        conf = _confidence_from_effect(comp)
        if conf in ("medium", "high"):
            key = _LABEL_TO_KEY.get(comp.metric_name, comp.metric_name)
            mvm_cue, _ = _METRIC_CUES.get(key, (None, None))
            cue_text = mvm_cue or f"Try matching the {comp.metric_name.lower()} you show on your made shots."
            return CoachingPriority(
                metric_key=key, metric_label=comp.metric_name,
                evidence=Evidence(text=_mvm_evidence_text(comp), detail=_mvm_detail(comp)),
                source="makes_vs_misses", confidence=conf,
                cues=[CoachingCue(cue_text), _GENERIC_PRACTICE_CUE],
            )

    least = least_consistent_metrics(consistency_results, top_n=1)
    if least:
        c = least[0]
        _, consistency_cue = _METRIC_CUES.get(c.metric_key, (None, None))
        cue_text = consistency_cue or f"Try keeping your {c.label.lower()} more consistent shot to shot."
        return CoachingPriority(
            metric_key=c.metric_key, metric_label=c.label,
            evidence=Evidence(text=_consistency_evidence_text(c, "least consistent"), detail=_consistency_detail(c)),
            source="consistency", confidence="medium",
            cues=[CoachingCue(cue_text), _GENERIC_PRACTICE_CUE],
        )

    return None


def _makes_vs_misses_note(mvm_report: MakesVsMissesReport) -> Tuple[Optional[Evidence], Optional[str]]:
    if not mvm_report.eligible:
        return None, _MVM_REASON_TEXT.get(mvm_report.reason, "Not enough data yet to compare makes vs. misses.")
    diffs = top_differentiators(mvm_report, top_n=1)
    if not diffs:
        return None, _NO_STRONG_DIFFERENCE_TEXT
    comp = diffs[0]
    if _confidence_from_effect(comp) == "low":
        return None, _NO_STRONG_DIFFERENCE_TEXT
    return Evidence(text=_mvm_evidence_text(comp), detail=_mvm_detail(comp)), None


def _consistency_note(consistency_results: List[ConsistencyResult]) -> Tuple[Optional[Evidence], Optional[str]]:
    least = least_consistent_metrics(consistency_results, top_n=1)
    if not least:
        return None, _NO_CONSISTENCY_DATA_TEXT
    c = least[0]
    return Evidence(text=_consistency_evidence_text(c, "least consistent"), detail=_consistency_detail(c)), None


def _build_coach_note(strength: Optional[SupportedFinding], priority: Optional[CoachingPriority]) -> str:
    if strength and priority:
        return (f"Your {strength.metric_label.lower()} was the most consistent part of your form this session, "
                f"and {priority.metric_label.lower()} is the clearest place to focus next.")
    if priority:
        return f"This session's clearest signal is in your {priority.metric_label.lower()} -- see below for what the evidence shows."
    if strength:
        return f"Your {strength.metric_label.lower()} was the most consistent part of your form this session -- there wasn't a clear priority to flag yet."
    return "There wasn't enough evidence yet this session to identify a clear strength or priority -- take a few more shots and check back."


def build_coaching_summary(shots: List[ShotRecord], session_summary: SessionSummary,
                             consistency_results: List[ConsistencyResult],
                             mvm_report: MakesVsMissesReport) -> CoachingSummary:
    usable = [s for s in shots if not s.excluded_from_analysis]
    if not usable:
        return CoachingSummary(
            eligible=False,
            coach_note="No reliably-tracked shots were available this session, so ArcVision can't generate coaching feedback yet.",
            confidence="low", data_quality_notes=["no_usable_shots"],
        )

    quality = _session_data_quality(session_summary)
    if quality in (Confidence.LOW, Confidence.EXCLUDED):
        return CoachingSummary(
            eligible=False,
            coach_note=("Pose and ball-tracking quality were too low this session for ArcVision to generate "
                         "reliable coaching feedback. A clip with the shooter and ball clearly visible the whole "
                         "time will give ArcVision more to work with."),
            confidence="low", data_quality_notes=["low_tracking_quality"],
        )

    data_quality_notes = []
    if quality == Confidence.MEDIUM:
        data_quality_notes.append("Tracking quality was moderate this session -- treat these findings as a rough read.")

    strength = _select_strength(consistency_results)
    priority = _select_priority(mvm_report, consistency_results)

    # Only one metric can have enough samples for consistency at all (a
    # short session) -- don't present it as both "your strength" and "your
    # #1 priority" at once, which would be self-contradictory. Priority is
    # the more actionable claim, so it wins; strength is dropped for this
    # session rather than showing a confusing duplicate.
    if strength and priority and priority.source == "consistency" and strength.metric_key == priority.metric_key:
        strength = None

    mvm_note, mvm_reason = _makes_vs_misses_note(mvm_report)
    consistency_note, consistency_reason = _consistency_note(consistency_results)

    overall_confidence = "medium" if quality == Confidence.MEDIUM else (priority.confidence if priority else "low")

    return CoachingSummary(
        eligible=True,
        coach_note=_build_coach_note(strength, priority),
        strength=strength, priority=priority,
        makes_vs_misses_note=mvm_note, makes_vs_misses_reason=mvm_reason,
        consistency_note=consistency_note, consistency_reason=consistency_reason,
        confidence=overall_confidence, data_quality_notes=data_quality_notes,
    )
