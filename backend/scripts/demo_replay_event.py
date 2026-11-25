#!/usr/bin/env python3
"""Upload one deterministic synthetic event and reprocess a local demo case.

Example (with TATHYA-DF API already running):
    python scripts/demo_replay_event.py --case-id OP_SHADOW_TRANSFER_DEMO

Run repeatedly to replay one additional event per invocation. This is a
controlled synthetic replay, not a connection to a live police feed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.case_pipeline import validate_case_id  # noqa: E402

PROJECT_ROOT = BACKEND_DIR.parent
SEQUENCE_PATH = BACKEND_DIR / "demo_scenario" / "operation_shadow_transfer" / "replay_sequence.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the next synthetic Operation Shadow Transfer event.")
    parser.add_argument("--case-id", required=True, help="Existing case ID that already contains the base demo evidence")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="TATHYA-DF API base URL")
    args = parser.parse_args()
    try:
        validate_case_id(args.case_id)
    except ValueError as exc:
        parser.error(str(exc))

    uploads_dir = BACKEND_DIR / "uploads" / args.case_id
    state_dir = BACKEND_DIR / "case_data" / args.case_id
    state_path = state_dir / "demo_replay_state.json"
    if not uploads_dir.is_dir():
        parser.error(f"No upload folder for case {args.case_id!r}: {uploads_dir}")
    if not SEQUENCE_PATH.is_file():
        parser.error(f"Replay sequence not found: {SEQUENCE_PATH}")

    sequence = json.loads(SEQUENCE_PATH.read_text(encoding="utf-8"))
    state_dir.mkdir(parents=True, exist_ok=True)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"next_index": 0}
    index = int(state.get("next_index", 0))
    if index >= len(sequence):
        print("All synthetic replay events have already been sent.")
        return 0

    event = sequence[index]
    filename = f"incoming_evidence_{index + 1:03d}.json"
    file_path = uploads_dir / filename
    api = args.base_url.rstrip("/")
    try:
        if not file_path.exists():
            content = json.dumps([event], indent=2, ensure_ascii=False).encode("utf-8")
            upload_response = requests.post(
                f"{api}/api/cases/{args.case_id}/upload",
                files={"file": (filename, content, "application/json")},
                timeout=60,
            )
            upload_response.raise_for_status()
            upload = upload_response.json()
            print(f"Uploaded synthetic event {index + 1}/{len(sequence)}: {event.get('event_id')}")
            print(f"Evidence ID: {upload.get('id')} | SHA-256: {upload.get('file_hash')}")
        else:
            print(f"Found previously uploaded event file {filename}; retrying case processing without overwriting it.")

        process_response = requests.post(
            f"{api}/api/case/process",
            json={"case_id": args.case_id},
            timeout=300,
        )
        process_response.raise_for_status()
        result = process_response.json()
        replay_statuses = [item for item in (result.get("source_processing") or []) if item.get("category") == "demo_replay"]
        if not replay_statuses or any(item.get("status") != "processed" for item in replay_statuses):
            print("The event file was uploaded, but the replay parser did not report a successful processing status.", file=sys.stderr)
            for item in replay_statuses:
                print(f"Replay status: {item.get('status')} — {item.get('error') or 'no additional detail'}", file=sys.stderr)
            return 1
        print("Case reprocessed successfully.")
        print(f"Graph: {result.get('entity_count')} entities / {result.get('relation_count')} relationships")
        print(f"Timeline: {result.get('timeline_event_count')} events / {result.get('timeline_scene_count')} scenes")
        print("Refresh the case in Chrome to view the updated graph and timeline.")
        state_path.write_text(json.dumps({"next_index": index + 1}, indent=2), encoding="utf-8")
        return 0
    except requests.RequestException as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        response = getattr(exc, "response", None)
        if response is not None:
            print(response.text, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
