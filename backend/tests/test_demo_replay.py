import json
import tempfile
import unittest
from pathlib import Path

from api.case_pipeline import stage_case_inputs
from preprocessor.DemoReplay.replay import preprocess_replay_event_file


class DemoReplayTests(unittest.TestCase):
    def test_replay_json_is_staged_as_separate_evidence_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "incoming_evidence_001.json").write_text(json.dumps([{
                "event_type": "call", "caller_phone": "9876543210", "receiver_phone": "9123456780",
                "timestamp": "2026-05-22T21:05:00+05:30", "duration_seconds": 45,
            }]))
            (uploads / "incoming_evidence_002.json").write_text(json.dumps([{
                "event_type": "transfer", "sender_account": "ACC1001", "receiver_account": "ACC9001",
                "amount": 9400, "timestamp": "2026-05-22T21:16:00+05:30",
            }]))
            staged = stage_case_inputs(uploads, root / "workspace")
            self.assertIn("demo_replay_001", staged["staged_sources"])
            self.assertIn("demo_replay_002", staged["staged_sources"])
            self.assertEqual(len(staged["source_manifest"]), 2)

    def test_replay_parser_supports_call_transfer_and_location_with_source_rows(self):
        events = [
            {"event_type": "call", "caller_phone": "9876543210", "receiver_phone": "9123456780", "timestamp": "2026-05-22T21:05:00+05:30"},
            {"event_type": "transfer", "sender_account": "ACC1001", "receiver_account": "ACC9001", "amount": 9400, "timestamp": "2026-05-22T21:16:00+05:30"},
            {"event_type": "location", "device_id": "ANDROID_001", "latitude": 22.5727, "longitude": 88.3640, "timestamp": "2026-05-22T21:22:00+05:30"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incoming_evidence_001.json"
            path.write_text(json.dumps(events))
            graph = preprocess_replay_event_file(str(path))
        self.assertEqual({r["relation"] for r in graph["relations"]}, {"CALLED", "TRANSFERRED_TO", "LOCATED_AT"})
        self.assertEqual({r["source_record_number"] for r in graph["relations"]}, {1, 2, 3})
        self.assertTrue(all(r.get("timestamp") for r in graph["relations"]))

    def test_replay_parser_rejects_unknown_event_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incoming_evidence_001.json"
            path.write_text(json.dumps([{"event_type": "unknown"}]))
            with self.assertRaises(ValueError):
                preprocess_replay_event_file(str(path))


if __name__ == "__main__":
    unittest.main()
