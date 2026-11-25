"""Parse one synthetic incoming-evidence event file into a graph fragment.

This adapter is for controlled demonstrations only. It does not connect to
police systems or claim a live operational feed.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid


def _entity(entity_type: str, value: str, attrs: dict, source_file: str) -> dict:
    return {
        "temp_id": f"REPLAY_{uuid.uuid4().hex[:10]}",
        "type": entity_type,
        "attributes": attrs,
        "confidence": 1.0,
        "source": "synthetic_evidence_replay",
        "source_file": source_file,
    }


def preprocess_replay_event_file(file_path: str) -> dict:
    path = Path(file_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        records = raw.get("events") if isinstance(raw.get("events"), list) else [raw]
    elif isinstance(raw, list):
        records = raw
    else:
        raise ValueError("Incoming evidence JSON must be an event object or a list of events.")

    entities: list[dict] = []
    relations: list[dict] = []
    entity_index: dict[tuple[str, str], str] = {}

    def get_entity(entity_type: str, value: str, attributes: dict) -> str:
        clean_value = str(value or "").strip()
        if not clean_value:
            raise ValueError(f"Missing identifier for {entity_type} in incoming event.")
        key = (entity_type, clean_value.lower())
        if key not in entity_index:
            created = _entity(entity_type, clean_value, attributes, path.name)
            entities.append(created)
            entity_index[key] = created["temp_id"]
        return entity_index[key]

    for record_number, event in enumerate(records, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"Incoming event {record_number} is not a JSON object.")
        event_type = str(event.get("event_type") or "").strip().lower()
        timestamp = event.get("timestamp")
        confidence = float(event.get("confidence", 1.0))
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Incoming event {record_number} confidence must be between 0 and 1.")
        base = {
            "attributes": {
                "synthetic_replay": True,
                "stream_event_id": event.get("event_id") or f"{path.stem}-{record_number:03d}",
            },
            "timestamp": timestamp,
            "confidence": confidence,
            "source_type": "synthetic_evidence_replay",
            "source_record_number": record_number,
            "provenance": f"{path.name}:event:{record_number}",
        }

        if event_type == "call":
            caller = re.sub(r"\D", "", str(event.get("caller_phone") or ""))[-10:]
            receiver = re.sub(r"\D", "", str(event.get("receiver_phone") or ""))[-10:]
            caller_id = get_entity("PHONE_NUMBER", caller, {"number": caller})
            receiver_id = get_entity("PHONE_NUMBER", receiver, {"number": receiver})
            relation = dict(base)
            relation.update({
                "source": caller_id,
                "target": receiver_id,
                "relation": "CALLED",
                "attributes": {
                    **base["attributes"],
                    "duration": int(event.get("duration_seconds", 0)),
                    "call_type": str(event.get("call_type") or "OUTGOING").upper(),
                },
            })
            relations.append(relation)
            tower = str(event.get("cell_tower") or "").strip()
            if tower:
                tower_id = get_entity("CELL_TOWER", tower, {"tower_id": tower})
                tower_relation = dict(base)
                tower_relation.update({
                    "source": caller_id,
                    "target": tower_id,
                    "relation": "CONNECTED_TO_TOWER",
                })
                relations.append(tower_relation)

        elif event_type in {"transfer", "transaction", "bank_transfer"}:
            sender = str(event.get("sender_account") or "").strip().upper()
            receiver = str(event.get("receiver_account") or "").strip().upper()
            sender_id = get_entity("ACCOUNT", sender, {"account_id": sender})
            receiver_id = get_entity("ACCOUNT", receiver, {"account_id": receiver})
            amount = float(event.get("amount", 0))
            relation = dict(base)
            relation.update({
                "source": sender_id,
                "target": receiver_id,
                "relation": "TRANSFERRED_TO",
                "attributes": {
                    **base["attributes"],
                    "amount": amount,
                    "transaction_id": event.get("transaction_id") or base["attributes"]["stream_event_id"],
                    "status": event.get("status") or "SUCCESS",
                    "device_id": event.get("device_id"),
                },
            })
            relations.append(relation)
            device = str(event.get("device_id") or "").strip()
            if device:
                device_id = get_entity("DEVICE", device, {"identifier": device})
                device_relation = dict(base)
                device_relation.update({
                    "source": sender_id,
                    "target": device_id,
                    "relation": "USED_DEVICE",
                    "attributes": {**base["attributes"], "transaction_id": relation["attributes"]["transaction_id"]},
                })
                relations.append(device_relation)

        elif event_type in {"location", "gps", "device_location"}:
            device = str(event.get("device_id") or "").strip()
            device_id = get_entity("DEVICE", device, {"identifier": device})
            latitude = float(event["latitude"])
            longitude = float(event["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError(f"Incoming event {record_number} has invalid coordinates.")
            location_id = get_entity(
                "LOCATION",
                f"{latitude:.5f},{longitude:.5f}",
                {"latitude": latitude, "longitude": longitude},
            )
            relation = dict(base)
            relation.update({
                "source": device_id,
                "target": location_id,
                "relation": "LOCATED_AT",
                "attributes": {
                    **base["attributes"],
                    "accuracy": float(event.get("accuracy_meters", 0)),
                },
            })
            relations.append(relation)
        else:
            raise ValueError(
                f"Unsupported event_type '{event_type}' in {path.name}. Use call, transfer or location."
            )

    return {"entities": entities, "relations": relations}
