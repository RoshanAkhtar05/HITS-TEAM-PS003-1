"""
Timeline Reconstruction Layer
===============================
Reads unified_graph.json → extracts every timestamped event → sorts
chronologically → groups into 30-minute "scene" windows → writes timeline.json

Each scene captures:
  - What happened (calls, transfers, messages, movements)
  - Who was involved
  - Which data sources contributed
  - Human-readable event descriptions

Run standalone:
    cd backend
    python -m timeline_reconstruction.reconstruct
"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

# Neo4j integration (optional — falls back to JSON if unavailable)
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from db_helper.dp_helper import get_graph_data_from_neo4j, is_neo4j_available
    _NEO4J_IMPORTED = True
except ImportError:
    _NEO4J_IMPORTED = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GRAPH_PATH = Path(__file__).parent.parent.parent / "Graph_Integration_Layer" / "output" / "unified_graph.json"
OUTPUT_PATH = Path(__file__).parent / "timeline.json"

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S+05:30",
]

SCENE_WINDOW_MINUTES = 30  # group events into 30-minute windows


# ---------------------------------------------------------------------------
# Graph Loading
# ---------------------------------------------------------------------------
def load_graph(graph_path=None, prefer_neo4j=True) -> dict:
    """
    Load graph data.
    Priority: Neo4j AuraDB → unified_graph.json (fallback).
    """
    if prefer_neo4j and _NEO4J_IMPORTED and is_neo4j_available():
        try:
            print("[timeline_reconstruction] Using Neo4j as data source.")
            return get_graph_data_from_neo4j()
        except Exception as e:
            print(f"[timeline_reconstruction] Neo4j failed ({e}), falling back to JSON.")
    print("[timeline_reconstruction] Using unified_graph.json (fallback).")
    with open(Path(graph_path) if graph_path is not None else GRAPH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Name Resolution
# ---------------------------------------------------------------------------
def get_entity_name(master: dict) -> str:
    """Extract the best human-readable name for a master entity."""
    resolved = master.get("resolved_values", [])
    entity_types = master.get("entity_types", [])
    master_type = master.get("master_type", "")

    if master_type == "PERSON" or "PERSON" in entity_types:
        for val in resolved:
            if not val:
                continue
            if val.startswith("acc") or val.startswith("android_") or val.startswith("watch_"):
                continue
            if val.replace(" ", "").isdigit():
                continue
            if val.startswith("@"):
                continue
            if "\n" in val or len(val) > 50:
                continue
            return val.title()

    if master_type == "PLACE":
        for val in resolved:
            if val and "\n" not in val and len(val) < 80:
                return val.title()

    if master_type == "INFRASTRUCTURE":
        for val in resolved:
            if val and "\n" not in val and len(val) < 80:
                return val.title()

    if master_type == "ENTITY":
        for val in resolved:
            if val and "\n" not in val and len(val) < 80:
                return val.upper() if val.startswith("acc") else val.title()

    for val in resolved:
        if val and "\n" not in val and len(val) < 80:
            return val.title()

    return master.get("master_id", "Unknown")


def build_name_map(masters: list) -> dict:
    """Build a mapping of master_id → human-readable name."""
    return {m["master_id"]: get_entity_name(m) for m in masters}


# ---------------------------------------------------------------------------
# Timestamp Parsing
# ---------------------------------------------------------------------------
def parse_timestamp(ts_str: str) -> datetime | None:
    """Try parsing a timestamp string with multiple known formats."""
    if not ts_str:
        return None
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def normalize_ts(dt: datetime) -> datetime:
    """Return aware timestamps in UTC; leave naive timestamps explicitly naive.

    A naive timestamp has no reliable timezone information. It must not be
    silently treated as UTC or compared with an aware timestamp.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return dt.astimezone(timezone.utc)
    return dt


def _timestamp_basis(dt: datetime) -> str:
    """Identify whether a timestamp can be ordered globally."""
    return "utc" if dt.tzinfo is not None and dt.utcoffset() is not None else "wall_clock_unverified"


def _window_summary(events: list[dict]) -> dict:
    """Summarise one comparable time track without mixing clock bases."""
    ordered = sorted(events, key=lambda event: event["parsed_time"])
    start = ordered[0]["parsed_time"]
    end = ordered[-1]["parsed_time"]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_minutes": round((end - start).total_seconds() / 60, 1),
        "time_basis": ordered[0].get("time_basis", "wall_clock_unverified"),
        "event_count": len(ordered),
    }


# ---------------------------------------------------------------------------
# Event Description Formatting
# ---------------------------------------------------------------------------
def format_event_description(event: dict) -> str:
    """
    Create a human-readable single-line description for each event type.
    """
    action = event.get("action", "")
    from_name = event.get("from", "?")
    to_name = event.get("to", "?")
    attrs = event.get("attributes", {})

    if action == "CALLED":
        duration = attrs.get("duration", "?")
        call_type = attrs.get("call_type", "").lower()
        return f"{from_name} called {to_name} ({duration}s, {call_type})"

    if action == "EMAILED":
        subject = attrs.get("subject", "")
        signals = attrs.get("forensic_signals", {})
        active = [k for k, v in signals.items() if v is True]
        desc = f"{from_name} emailed {to_name}"
        if subject:
            desc += f" -- Subject: {subject}"
        if active:
            desc += f" [FLAGGED: {', '.join(active)}]"
        return desc

    if action == "MESSAGED":
        text = attrs.get("text", "")
        snippet = text[:80] + ("..." if len(text) > 80 else "")
        return f"{from_name} -> {to_name}: '{snippet}'"

    if action == "TRANSFERRED_TO":
        amount = attrs.get("amount", "?")
        method = attrs.get("transaction_type", "?")
        amount_label = f"{amount:,}" if isinstance(amount, (int, float)) else str(amount)
        return f"{from_name} -> {to_name}: Rs.{amount_label} ({method})"

    if action == "LOCATED_AT":
        accuracy = attrs.get("accuracy", "?")
        speed = attrs.get("speed", 0)
        motion = "moving" if speed and speed > 1 else "stationary"
        return f"{from_name} at {to_name} (accuracy: {accuracy}m, {motion})"

    if action == "CONNECTED_TO_TOWER":
        return f"{from_name} connected to {to_name}"

    if action == "MOVED_TO":
        distance = attrs.get("distance_meters", "?")
        if isinstance(distance, (int, float)):
            distance = f"{distance:.0f}"
        return f"Movement: {from_name} -> {to_name} ({distance}m)"

    if action == "DETECTED":
        return f"Camera detected: {to_name} at {from_name}"

    if action in ("POSTED_ON", "MENTIONED_USER"):
        content = attrs.get("content", "")
        snippet = content[:80] + ("..." if len(content) > 80 else "")
        return f"{from_name} posted on {to_name}: '{snippet}'" if content else f"{from_name} -> {to_name}"

    if action == "MENTIONED":
        return f"{from_name} mentioned {to_name}"

    if action == "TRANSFERRED_MONEY":
        return f"{from_name} transferred money to {to_name} (FIR reference)"

    # Fallback
    return f"{action}: {from_name} -> {to_name}"


# ---------------------------------------------------------------------------
# Event List Builder
# ---------------------------------------------------------------------------
def build_event_list(
    relations: list,
    name_map: dict,
    unplaced_events: list | None = None,
) -> list[dict]:
    """Convert relations to events while preserving timestamp uncertainty.

    Timezone-aware timestamps are normalised to UTC for comparison. Naive
    timestamps remain on an explicitly unverified wall-clock track. Relations
    with missing or invalid timestamps are retained separately when the
    optional ``unplaced_events`` list is supplied.
    """
    events = []

    for index, rel in enumerate(relations):
        ts_raw = rel.get("timestamp", "")
        ts = parse_timestamp(ts_raw)
        if not ts:
            if unplaced_events is not None:
                reason = "missing_timestamp" if ts_raw in (None, "") else "unparseable_timestamp"
                unplaced_events.append({
                    "relation_index": index,
                    "action": rel.get("relation", "UNKNOWN"),
                    "from_id": rel.get("source", ""),
                    "to_id": rel.get("target", ""),
                    "timestamp_raw": ts_raw,
                    "timestamp_status": reason,
                    "source_file": rel.get("source_file") or rel.get("provenance"),
                    "evidence_id": rel.get("evidence_id"),
                    "evidence_sha256": rel.get("evidence_sha256"),
                    "artifact_id": rel.get("artifact_id"),
                    "record_id": rel.get("record_id"),
                    "provenance": rel.get("provenance"),
                    "provenance_type": rel.get("provenance_type"),
                    "source_record_number": rel.get("source_record_number"),
                })
            continue

        comparable_ts = normalize_ts(ts)
        time_basis = _timestamp_basis(ts)
        timestamp_utc = (
            comparable_ts.isoformat().replace("+00:00", "Z")
            if time_basis == "utc" else None
        )

        # Determine source type (handle both source_type and provenance fields)
        source_type = rel.get("source_type", "")
        if not source_type:
            prov = rel.get("provenance", "")
            if prov and isinstance(prov, str):
                source_type = prov.split(":")[0].replace(".txt", "").replace(".json", "")

        event = {
            # Keep the source's timestamp representation for audit/display.
            "timestamp": str(ts_raw),
            "timestamp_utc": timestamp_utc,
            "timestamp_status": "timezone_aware" if time_basis == "utc" else "timezone_unknown",
            "time_basis": time_basis,
            "parsed_time": comparable_ts,  # internal only; removed before JSON output
            "action": rel.get("relation", "UNKNOWN"),
            "from": name_map.get(rel.get("source", ""), rel.get("source", "?")),
            "from_id": rel.get("source", ""),
            "to": name_map.get(rel.get("target", ""), rel.get("target", "?")),
            "to_id": rel.get("target", ""),
            "source_type": source_type or "unknown",
            "confidence": rel.get("confidence", 0.0),
            "attributes": rel.get("attributes", {}),
            "evidence_id": rel.get("evidence_id"),
            "evidence_sha256": rel.get("evidence_sha256"),
            "artifact_id": rel.get("artifact_id"),
            "record_id": rel.get("record_id"),
            "provenance": rel.get("provenance"),
            "provenance_type": rel.get("provenance_type"),
            "source_record_number": rel.get("source_record_number"),
            "source_file": rel.get("source_file"),
        }

        event["description"] = format_event_description(event)
        events.append(event)

    # Sort within comparable tracks only: UTC events first, then unverified
    # wall-clock events. No ordering is asserted between those two tracks.
    events.sort(key=lambda event: (
        0 if event["time_basis"] == "utc" else 1,
        event["parsed_time"],
    ))
    return events


# ---------------------------------------------------------------------------
# Scene Grouping
# ---------------------------------------------------------------------------
def assign_scene_label(events: list[dict]) -> str:
    """
    Auto-generate a descriptive label for a scene based on the dominant
    event types within it.
    """
    action_counts = Counter(e["action"] for e in events)
    top_actions = action_counts.most_common(3)
    top_names = [a for a, _ in top_actions]

    # Map action combos to readable labels
    if "TRANSFERRED_TO" in top_names:
        return "Financial Transfers"
    if "CALLED" in top_names and "MESSAGED" in top_names:
        return "Coordinated Communications"
    if "CALLED" in top_names:
        return "Voice Communications"
    if "MESSAGED" in top_names:
        return "Chat Activity"
    if "EMAILED" in top_names:
        return "Email Exchange"
    if "LOCATED_AT" in top_names and "MOVED_TO" in top_names:
        return "Movement & Tracking"
    if "LOCATED_AT" in top_names:
        return "Location Tracking"
    if "DETECTED" in top_names:
        return "Surveillance Detection"
    if "POSTED_ON" in top_names:
        return "Social Media Activity"
    if "MENTIONED" in top_names:
        return "Entity Mentions"
    if "CONNECTED_TO_TOWER" in top_names:
        return "Cell Tower Connections"

    return "Mixed Activity"


def group_into_scenes(
    events: list[dict],
    window_minutes: int = SCENE_WINDOW_MINUTES,
) -> list[dict]:
    """Group events into time windows without mixing incompatible clocks.

    UTC-normalised events and timezone-unknown wall-clock events are always
    placed in separate scene tracks. Scene windows are elapsed-time windows
    from the first event in each track, not calendar-aligned buckets.
    """
    if not events:
        return []

    tracks = defaultdict(list)
    for event in events:
        basis = event.get("time_basis", "wall_clock_unverified")
        tracks[basis].append(event)

    scenes = []
    scene_number = 0
    # Deterministic track ordering; this does not imply an ordering between
    # the actual events in different tracks.
    for basis in ("utc", "wall_clock_unverified"):
        track_events = tracks.get(basis, [])
        if not track_events:
            continue

        track_events = sorted(track_events, key=lambda event: event["parsed_time"])
        earliest = track_events[0]["parsed_time"]
        buckets = defaultdict(list)
        for event in track_events:
            offset = (event["parsed_time"] - earliest).total_seconds() / 60
            bucket_idx = int(offset // window_minutes)
            buckets[bucket_idx].append(event)

        for idx in sorted(buckets.keys()):
            bucket_events = buckets[idx]
            window_start = earliest + timedelta(minutes=idx * window_minutes)
            window_end = window_start + timedelta(minutes=window_minutes)
            source_types = Counter(e["source_type"] for e in bucket_events)
            dominant_sources = [source for source, _ in source_types.most_common(3)]
            action_types = Counter(e["action"] for e in bucket_events)
            actors = set()
            for event in bucket_events:
                actors.add(event["from"])
                actors.add(event["to"])

            clean_events = [
                {key: value for key, value in event.items() if key != "parsed_time"}
                for event in bucket_events
            ]
            scene_number += 1
            scenes.append({
                "scene_id": f"SCENE_{scene_number:02d}",
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "time_basis": basis,
                "timezone_status": "verified_offset" if basis == "utc" else "timezone_unknown",
                "label": assign_scene_label(bucket_events),
                "event_count": len(bucket_events),
                "action_breakdown": dict(action_types.most_common()),
                "dominant_source_types": dominant_sources,
                "active_actors": sorted(actors - {"?", "Unknown"}),
                "events": clean_events,
            })

    return scenes


# ---------------------------------------------------------------------------
# Summary Stats
# ---------------------------------------------------------------------------
def compute_timeline_stats(events: list[dict], scenes: list[dict]) -> dict:
    """Compute high-level statistics about the timeline."""
    if not events:
        return {}

    action_counts = Counter(e["action"] for e in events)
    source_counts = Counter(e["source_type"] for e in events)

    # Find peak activity scene
    peak_scene = max(scenes, key=lambda s: s["event_count"]) if scenes else None

    return {
        "total_events": len(events),
        "total_scenes": len(scenes),
        "action_type_counts": dict(action_counts.most_common()),
        "source_type_counts": dict(source_counts.most_common()),
        "peak_activity_scene": peak_scene["scene_id"] if peak_scene else None,
        "peak_activity_count": peak_scene["event_count"] if peak_scene else 0,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_reconstruction(graph_path=None, output_path=None, prefer_neo4j=True) -> dict:
    """Run timeline reconstruction and save an uncertainty-aware timeline."""
    resolved_graph_path = Path(graph_path) if graph_path is not None else GRAPH_PATH
    resolved_output_path = Path(output_path) if output_path is not None else OUTPUT_PATH
    print(f"Loading graph from: {resolved_graph_path}")
    graph = load_graph(resolved_graph_path, prefer_neo4j=prefer_neo4j)
    masters = graph.get("master_entities", [])
    relations = graph.get("relations", [])
    print(f"  Entities: {len(masters)}, Relations: {len(relations)}")

    name_map = build_name_map(masters)
    print("  Building event list...")
    unplaced_events = []
    events = build_event_list(relations, name_map, unplaced_events)
    print(f"  -> {len(events)} timestamped events; {len(unplaced_events)} without usable timestamps")

    events_by_basis = defaultdict(list)
    for event in events:
        events_by_basis[event["time_basis"]].append(event)
    incident_windows = {
        basis: _window_summary(track_events)
        for basis, track_events in events_by_basis.items()
        if track_events
    }

    # Keep the legacy single-window field only when every event is on one
    # comparable clock. For mixed clocks, explicitly avoid a false combined
    # start/end/duration claim.
    if len(incident_windows) == 1:
        incident_window = next(iter(incident_windows.values()))
    elif len(incident_windows) > 1:
        incident_window = {
            "start": None,
            "end": None,
            "duration_minutes": None,
            "status": "multiple_non_comparable_time_bases",
        }
    else:
        incident_window = {
            "start": None,
            "end": None,
            "duration_minutes": 0,
            "status": "no_timestamped_events",
        }

    print(f"  Grouping into {SCENE_WINDOW_MINUTES}-minute scenes per clock track...")
    scenes = group_into_scenes(events, SCENE_WINDOW_MINUTES)
    print(f"  -> {len(scenes)} scenes generated")
    for scene in scenes:
        print(
            f"     {scene['scene_id']}: {scene['window_start']} - {scene['window_end']} "
            f"| {scene['event_count']} events | {scene['label']} | {scene['time_basis']}"
        )

    stats = compute_timeline_stats(events, scenes)
    stats["unplaced_event_count"] = len(unplaced_events)
    stats["timezone_unknown_event_count"] = len(events_by_basis.get("wall_clock_unverified", []))
    stats["timezone_aware_event_count"] = len(events_by_basis.get("utc", []))

    timeline = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "incident_window": incident_window,
        "incident_windows": incident_windows,
        "stats": stats,
        "total_events": len(events),
        "total_scenes": len(scenes),
        "unplaced_event_count": len(unplaced_events),
        "unplaced_events": unplaced_events,
        "scenes": scenes,
    }

    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved_output_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"[OK] Timeline saved to: {resolved_output_path}")
    print(f"     Timestamped events: {len(events)} across {len(scenes)} scenes")
    print(f"     Unplaced events: {len(unplaced_events)}")
    print(f"     Separate time tracks: {len(incident_windows)}")
    print(f"{'='*60}")
    return timeline


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_reconstruction()
