"""
Regenerates ONLY the `coaching` field of the featured demo session's stored
analysis_json, using the updated app/analytics/coaching.py (basketball-
language pass). Reuses the SAME already-computed consistency/makes-vs-
misses/session-summary data already stored for this session -- no CV
inference is re-run (no detector, no pose pipeline, no shot segmentation,
no outcome classifier), and every other key in the stored payload (shots,
mechanics, trajectory, consistency, makes_vs_misses, session_summary, video
paths, shooting_side, outcomes, etc.) is verified unchanged before writing.

This is the coaching-layer equivalent of
scripts/regenerate_featured_demo_replay_labels.py from an earlier pass: a
targeted regeneration of one presentation layer from data that already
exists, not a re-run of anything CV-related.

Usage:
    .venv\\Scripts\\python scripts\\regenerate_featured_demo_coaching_language.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analytics.coaching import build_coaching_summary
from app.analytics.consistency import ConsistencyResult
from app.analytics.makes_vs_misses import MakesVsMissesReport
from app.analytics.session_summary import SessionSummary
from app.analytics.stats_utils import ComparisonResult
from app.storage import repository
from app.storage.db import db_session
from app.storage.serializers import to_jsonable

DEMO_SESSION_ID = "fee1c3bcd7b84322"


@dataclass
class _ShotStub:
    excluded_from_analysis: bool


def main() -> None:
    row = repository.get_session(DEMO_SESSION_ID)
    if row is None:
        raise SystemExit(f"Session {DEMO_SESSION_ID} not found.")
    payload = json.loads(row["analysis_json"])

    consistency_results = [ConsistencyResult(**c) for c in payload["consistency"]]
    comparisons = [ComparisonResult(**c) for c in payload["makes_vs_misses"]["comparisons"]]
    mvm = payload["makes_vs_misses"]
    mvm_report = MakesVsMissesReport(
        eligible=mvm["eligible"], reason=mvm["reason"], made_count=mvm["made_count"],
        missed_count=mvm["missed_count"], unknown_count=mvm["unknown_count"], comparisons=comparisons,
    )
    ss = payload["session_summary"]
    session_summary = SessionSummary(**{k: ss[k] for k in SessionSummary.__dataclass_fields__})
    shots_stub = [_ShotStub(excluded_from_analysis=s["excluded_from_analysis"]) for s in payload["shots"]]

    new_coaching = build_coaching_summary(shots_stub, session_summary, consistency_results, mvm_report)
    new_coaching_dict = to_jsonable(new_coaching)

    old_priority_key = (payload["coaching"].get("priority") or {}).get("metric_key")
    old_strength_key = (payload["coaching"].get("strength") or {}).get("metric_key")
    new_priority_key = new_coaching.priority.metric_key if new_coaching.priority else None
    new_strength_key = new_coaching.strength.metric_key if new_coaching.strength else None
    if old_priority_key != new_priority_key or old_strength_key != new_strength_key:
        raise SystemExit(
            f"Refusing to write: selection changed (priority {old_priority_key!r}->{new_priority_key!r}, "
            f"strength {old_strength_key!r}->{new_strength_key!r}). This script must never change which "
            f"metric wins -- only its presentation."
        )

    new_payload = dict(payload)
    new_payload["coaching"] = new_coaching_dict

    # Verify every OTHER key is byte-for-byte identical before writing --
    # this must only ever touch "coaching".
    unchanged_keys = [k for k in payload if k != "coaching"]
    for k in unchanged_keys:
        if json.dumps(payload[k], sort_keys=True) != json.dumps(new_payload[k], sort_keys=True):
            raise SystemExit(f"Refusing to write: key {k!r} would change, and this script must only touch 'coaching'.")

    with db_session() as conn:
        conn.execute(
            "UPDATE sessions SET analysis_json = ? WHERE session_id = ?",
            (json.dumps(new_payload), DEMO_SESSION_ID),
        )

    print(f"Updated coaching field for session {DEMO_SESSION_ID}.")
    print("New coach_note:", new_coaching.coach_note)
    print(f"priority metric_key unchanged: {old_priority_key!r}")
    print(f"strength metric_key unchanged: {old_strength_key!r}")


if __name__ == "__main__":
    main()
