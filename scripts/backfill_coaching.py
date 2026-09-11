"""
One-off: adds app.analytics.coaching output to already-completed sessions
whose stored analysis_json predates the Coach feature (Stage 4). This does
NOT re-run any detection/tracking/outcome/biomechanics computation -- it
reconstructs ShotRecord objects from the already-stored, already-computed
shot JSON and re-runs only the presentation-layer analytics
(consistency/makes-vs-misses/coaching) over those exact same values. Safe
to re-run; skips sessions that already have a "coaching" key.

Usage:
    .venv\\Scripts\\python scripts\\backfill_coaching.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analytics.coaching import build_coaching_summary
from app.analytics.consistency import compute_consistency
from app.analytics.makes_vs_misses import compute_makes_vs_misses
from app.analytics.session_summary import compute_session_summary
from app.analytics.shot_record import ShotRecord, TrajectoryMetrics
from app.biomechanics.metrics import ShotMechanics
from app.events.outcome_detector import ShotOutcome
from app.storage import repository
from app.storage.db import db_session
from app.storage.serializers import to_jsonable


def _rebuild_shot(d: dict) -> ShotRecord:
    mech = ShotMechanics(**d["mechanics"])
    traj = TrajectoryMetrics(**d["trajectory"])
    return ShotRecord(
        shot_index=d["shot_index"], start_time_sec=d["start_time_sec"],
        release_time_sec=d["release_time_sec"], end_time_sec=d["end_time_sec"],
        outcome=ShotOutcome(d["outcome"]), outcome_confidence=d["outcome_confidence"],
        outcome_reason=d["outcome_reason"], release_confidence=d["release_confidence"],
        pose_quality=d["pose_quality"], ball_track_quality=d["ball_track_quality"],
        hoop_confidence=d["hoop_confidence"], shooting_side=d["shooting_side"],
        mechanics=mech, trajectory=traj, warnings=d.get("warnings", []),
        excluded_from_analysis=d.get("excluded_from_analysis", False),
        exclusion_reason=d.get("exclusion_reason"), outcome_evidence=d.get("outcome_evidence", {}),
    )


def main():
    updated = 0
    skipped_has_coaching = 0
    skipped_not_completed = 0
    for row_summary in repository.list_sessions():
        session_id = row_summary["session_id"]
        row = repository.get_session(session_id)
        if row["status"] != "completed" or not row["analysis_json"]:
            skipped_not_completed += 1
            continue
        payload = json.loads(row["analysis_json"])
        if "coaching" in payload:
            skipped_has_coaching += 1
            continue

        shots = [_rebuild_shot(d) for d in payload["shots"]]
        consistency = compute_consistency(shots)
        mvm = compute_makes_vs_misses(shots)
        summary = compute_session_summary(shots, consistency, mvm)
        coaching = build_coaching_summary(shots, summary, consistency, mvm)

        payload["coaching"] = to_jsonable(coaching)
        # overall_confidence_level was also added to per-shot serialization
        # in this same stage -- backfill it too so Shots-tab badges work on
        # these older sessions as well.
        for shot_json, shot_obj in zip(payload["shots"], shots):
            shot_json["overall_confidence_level"] = shot_obj.overall_confidence_level.value

        with db_session() as conn:
            conn.execute("UPDATE sessions SET analysis_json = ? WHERE session_id = ?",
                          (json.dumps(payload), session_id))
        updated += 1
        print(f"backfilled {session_id} ({row['original_filename']}): "
              f"coaching.eligible={coaching.eligible}, priority={coaching.priority.metric_key if coaching.priority else None}")

    print(f"\nDone. Updated {updated} session(s); "
          f"{skipped_has_coaching} already had coaching; {skipped_not_completed} not completed.")


if __name__ == "__main__":
    main()
