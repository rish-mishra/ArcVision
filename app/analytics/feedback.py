"""
Generates the 1-3 evidence-based findings shown to the player. Every
finding must trace back to an actual computed comparison or trend --
nothing here is a template filled with a generic tip. If no metric shows a
meaningful, sufficiently-sampled difference, the module says so explicitly
rather than inventing a finding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.analytics.makes_vs_misses import MakesVsMissesReport, top_differentiators
from app.analytics.stats_utils import ComparisonResult
from app.analytics.trends import TrendReport


@dataclass
class Finding:
    finding: str
    evidence: str
    confidence: str  # "high" | "medium" | "low"
    focus: str


def _confidence_from_effect(comp: ComparisonResult) -> str:
    n = min(comp.made_n, comp.missed_n)
    if comp.effect_label in ("large",) and n >= 5:
        return "high"
    if comp.effect_label in ("large", "medium") and n >= 3:
        return "medium"
    return "low"


def _direction_phrase(comp: ComparisonResult) -> str:
    if comp.made_mean is None or comp.missed_mean is None:
        return "differed"
    return "was higher on makes" if comp.made_mean > comp.missed_mean else "was higher on misses"


def generate_makes_vs_misses_findings(report: MakesVsMissesReport, max_findings: int = 3) -> List[Finding]:
    if not report.eligible:
        reason_text = {
            "not_enough_total_shots": "Not enough shots were detected this session to compare makes vs. misses reliably.",
            "not_enough_made_or_missed_shots": "Not enough confidently-made or confidently-missed shots were detected to compare mechanics reliably.",
        }.get(report.reason, "Insufficient data for makes-vs-misses analysis.")
        return [Finding(
            finding="No makes-vs-misses comparison available yet.",
            evidence=reason_text,
            confidence="low",
            focus="Take more shots (aim for at least a handful of clear makes and misses) so ArcVision can compare your own mechanics.",
        )]

    diffs = top_differentiators(report, top_n=max_findings)
    if not diffs:
        return [Finding(
            finding="No strong measurable difference was found between your makes and misses this session.",
            evidence=(f"Compared {len(report.comparisons)} mechanical metrics across "
                       f"{report.made_count} made and {report.missed_count} missed shots; "
                       f"none showed a consistent, adequately-sampled difference."),
            confidence="medium",
            focus="Your mechanics may already be consistent between makes and misses -- consider that a positive sign, not a lack of insight.",
        )]

    findings = []
    for comp in diffs:
        direction = _direction_phrase(comp)
        findings.append(Finding(
            finding=f"{comp.metric_name} {direction} this session.",
            evidence=(f"Made-shot mean: {comp.made_mean} (n={comp.made_n}, sd={comp.made_std}); "
                       f"Missed-shot mean: {comp.missed_mean} (n={comp.missed_n}, sd={comp.missed_std}); "
                       f"difference={comp.difference}, effect size={comp.effect_size} ({comp.effect_label})"),
            confidence=_confidence_from_effect(comp),
            focus=f"Try matching the {comp.metric_name} you show on your made shots on future attempts.",
        ))
    return findings


def generate_trend_findings(report: TrendReport) -> List[Finding]:
    if not report.eligible:
        return []
    findings = []
    if report.early_shooting_pct is not None and report.late_shooting_pct is not None:
        change = report.late_shooting_pct - report.early_shooting_pct
        if abs(change) >= 10:
            findings.append(Finding(
                finding=f"Your shooting percentage changed from {report.early_shooting_pct}% early in the session to {report.late_shooting_pct}% later.",
                evidence=f"Early third: {report.early_n_classified} classified shots; Late third: {report.late_n_classified} classified shots.",
                confidence="medium" if min(report.early_n_classified, report.late_n_classified) >= 3 else "low",
                focus="Your mechanics changed during the later portion of this session -- worth reviewing the Trends tab.",
            ))
    notable = [t for t in report.metric_trends if t.change is not None and t.early_n >= 3 and t.late_n >= 3]
    notable.sort(key=lambda t: abs(t.change), reverse=True)
    for t in notable[:1]:
        findings.append(Finding(
            finding=f"{t.label} changed from {t.early_mean} early to {t.late_mean} later in the session.",
            evidence=f"Early n={t.early_n}, Late n={t.late_n}, change={t.change} {t.unit}.",
            confidence="low",
            focus="This may reflect changing mechanics later in the session -- not necessarily fatigue.",
        ))
    return findings
