"""
freshness.py — tracks when this dashboard first saw each project/activity row.

The Google Sheet has no "created at" / "added at" columns, so we can't know
a row's true creation time. Instead we keep a small local cache of the first
time each project_id / activity_id was observed, and treat that as a proxy
for "created". On the very first run (no cache file yet), existing rows are
backdated so they don't all show up as "new".
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CACHE_FILE = Path(__file__).parent / ".first_seen_cache.json"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"projects": {}, "activities": {}}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache))


def track_first_seen(
    projects: pd.DataFrame, activity: pd.DataFrame
) -> tuple[dict[str, datetime], dict[str, datetime]]:
    """Record first-seen timestamps for any new project_id/activity_id.

    Returns ({project_id: first_seen_datetime}, {activity_id: first_seen_datetime}).
    """
    is_first_run = not CACHE_FILE.exists()
    cache = _load_cache()
    seed_ts = EPOCH if is_first_run else datetime.now(timezone.utc).isoformat()
    changed = False

    if "project_id" in projects.columns:
        for pid in projects["project_id"]:
            if pid and pid not in cache["projects"]:
                cache["projects"][pid] = seed_ts
                changed = True

    if "activity_id" in activity.columns:
        for aid in activity["activity_id"]:
            if aid and aid not in cache["activities"]:
                cache["activities"][aid] = seed_ts
                changed = True

    if changed:
        _save_cache(cache)

    proj_first_seen = {pid: datetime.fromisoformat(ts) for pid, ts in cache["projects"].items()}
    act_first_seen = {aid: datetime.fromisoformat(ts) for aid, ts in cache["activities"].items()}
    return proj_first_seen, act_first_seen
