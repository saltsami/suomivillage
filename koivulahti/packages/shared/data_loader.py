import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from .schemas import EventTypeItem, NPCProfile, Place, RelationshipEdge


DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_event_types_catalog() -> Dict[str, Any]:
    path = DATA_DIR / "event_types.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_places() -> List[Place]:
    catalog = load_event_types_catalog()
    return [Place(**p) for p in catalog.get("places", [])]


def get_npc_profiles() -> List[NPCProfile]:
    catalog = load_event_types_catalog()
    return [NPCProfile(**p) for p in catalog.get("npc_profiles", [])]


def get_relationship_edges() -> List[RelationshipEdge]:
    catalog = load_event_types_catalog()
    edges = catalog.get("relationship_init", {}).get("edges", [])
    return [RelationshipEdge(**e) for e in edges]


def get_event_types() -> List[EventTypeItem]:
    catalog = load_event_types_catalog()
    items = catalog.get("event_types", {}).get("items", [])
    return [EventTypeItem(**i) for i in items]


def get_day1_seed_events() -> List[Dict[str, Any]]:
    catalog = load_event_types_catalog()
    scenario = catalog.get("day1_seed_scenario", {}) or {}
    base_date = scenario.get("date_local")
    events = scenario.get("events", [])
    normalized: List[Dict[str, Any]] = []
    for e in events:
        item = dict(e)
        if "type" not in item and "e" in item:
            item["type"] = item["e"]
        if "severity" not in item and "seveity" in item:
            item["severity"] = item["seveity"]
        ts_local = item.get("ts_local")
        if ts_local and base_date:
            # If ts_local is time-only, prepend scenario date.
            if re.match(r"^\d{2}:\d{2}:\d{2}$", ts_local):
                item["ts_local"] = f"{base_date}T{ts_local}"
            # If ts_local is malformed like "YYYY-HH:MM:SS", treat as year + time.
            elif re.match(r"^\d{4}-\d{2}:\d{2}:\d{2}$", ts_local):
                year, time_part = ts_local.split("-", 1)
                date_part = base_date
                if re.match(r"^\d{4}-\d{2}-\d{2}$", base_date):
                    date_part = f"{year}{base_date[4:]}"
                item["ts_local"] = f"{date_part}T{time_part}"
            # If space-separated datetime, normalize to ISO.
            elif " " in ts_local and "T" not in ts_local:
                item["ts_local"] = ts_local.replace(" ", "T")
        normalized.append(item)
    return normalized


def get_impact_scoring_config() -> Dict[str, Any]:
    catalog = load_event_types_catalog()
    return catalog.get("impact_scoring", {}) or {}
