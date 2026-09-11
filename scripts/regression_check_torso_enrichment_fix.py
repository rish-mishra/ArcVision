"""
One-off regression-check script for the enrich_near_hoop clamp fix and the
apex_height_norm torso-length fix (app/pipeline/orchestrator.py). Runs the
full production pipeline (detection through coaching, no video rendering)
on each given video and prints shot count, outcomes, apex_height_norm
values, and coaching strength/priority -- for direct before/after /
cross-video comparison. Read-only: writes nothing to the database.

Usage:
    .venv\\Scripts\\python scripts\\regression_check_torso_enrichment_fix.py video1.mov [video2.mov ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.orchestrator import run_pipeline


def main():
    for video_arg in sys.argv[1:]:
        video_path = Path(video_arg).resolve()
        print(f"\n{'=' * 70}\n{video_path.name}\n{'=' * 70}")
        result = run_pipeline(video_path)
        print(f"shots detected: {len(result.shots)}")
        outcomes = [s.outcome.value for s in result.shots]
        print(f"outcomes: {outcomes}")
        print(f"summary: made={result.session_summary.made} missed={result.session_summary.missed} "
              f"unknown={result.session_summary.unknown} pct={result.session_summary.shooting_percentage}")
        for s in result.shots:
            print(f"  shot {s.shot_index}: outcome={s.outcome.value} conf={s.outcome_confidence} "
                  f"apex_height_norm={s.trajectory.apex_height_norm} "
                  f"straightness={s.trajectory.straightness_ratio}")
        if result.coaching is not None:
            c = result.coaching
            strength_key = c.strength.metric_key if c.strength else None
            priority_key = c.priority.metric_key if c.priority else None
            print(f"coaching: eligible={c.eligible} confidence={c.confidence} "
                  f"strength={strength_key} priority={priority_key}")


if __name__ == "__main__":
    main()
