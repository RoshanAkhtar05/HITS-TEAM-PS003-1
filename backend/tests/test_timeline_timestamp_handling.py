"""Regression tests for timeline timezone and unplaced-evidence handling."""
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from analysis.timeline_reconstruction.reconstruct import (  # noqa: E402
    build_event_list,
    group_into_scenes,
    normalize_ts,
    parse_timestamp,
)


class TimelineTimestampTests(unittest.TestCase):
    def test_aware_timestamp_is_normalised_to_utc_without_losing_source_value(self):
        relations = [{
            "source": "p1", "target": "p2", "relation": "CALLED",
            "timestamp": "2026-11-23T10:00:00+05:30",
            "provenance": "cdr.csv:row8", "evidence_id": "EV-8",
        }]
        events = build_event_list(relations, {})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["timestamp"], "2026-11-23T10:00:00+05:30")
        self.assertEqual(events[0]["timestamp_utc"], "2026-11-23T04:30:00Z")
        self.assertEqual(events[0]["timestamp_status"], "timezone_aware")
        self.assertEqual(events[0]["evidence_id"], "EV-8")
        self.assertEqual(normalize_ts(parse_timestamp(relations[0]["timestamp"])).isoformat(), "2026-11-23T04:30:00+00:00")

    def test_naive_timestamp_remains_unverified_and_is_not_assumed_utc(self):
        events = build_event_list([{
            "source": "p1", "target": "p2", "relation": "CALLED",
            "timestamp": "2026-11-23 10:00:00",
        }], {})
        self.assertEqual(events[0]["timestamp_status"], "timezone_unknown")
        self.assertIsNone(events[0]["timestamp_utc"])
        self.assertEqual(events[0]["time_basis"], "wall_clock_unverified")

    def test_mixed_clock_bases_are_grouped_into_separate_scenes(self):
        events = build_event_list([
            {"source": "p1", "target": "p2", "relation": "CALLED", "timestamp": "2026-11-23T10:00:00+05:30"},
            {"source": "p1", "target": "p2", "relation": "MESSAGED", "timestamp": "2026-11-23 10:05:00"},
        ], {})
        scenes = group_into_scenes(events)
        self.assertEqual(len(scenes), 2)
        self.assertEqual({scene["time_basis"] for scene in scenes}, {"utc", "wall_clock_unverified"})
        self.assertEqual(sum(scene["event_count"] for scene in scenes), 2)

    def test_missing_and_invalid_timestamps_are_retained_as_unplaced(self):
        unplaced = []
        events = build_event_list([
            {"source": "p1", "target": "p2", "relation": "CALLED"},
            {"source": "p3", "target": "p4", "relation": "MESSAGED", "timestamp": "not-a-date", "evidence_sha256": "deadbeef"},
        ], {}, unplaced)
        self.assertEqual(events, [])
        self.assertEqual(len(unplaced), 2)
        self.assertEqual(unplaced[0]["timestamp_status"], "missing_timestamp")
        self.assertEqual(unplaced[1]["timestamp_status"], "unparseable_timestamp")
        self.assertEqual(unplaced[1]["evidence_sha256"], "deadbeef")

    def test_events_preserve_source_and_record_provenance(self):
        event = build_event_list([{
            "source": "p1", "target": "p2", "relation": "TRANSFERRED_TO",
            "timestamp": "2026-11-23T10:00:00Z", "source_file": "bank.csv",
            "evidence_id": "EVD-7", "evidence_sha256": "0123456789abcdef",
            "artifact_id": "ART-2", "record_id": "ROW-9", "provenance": "bank.csv:9",
        }], {})[0]
        self.assertEqual(event["source_file"], "bank.csv")
        self.assertEqual(event["evidence_id"], "EVD-7")
        self.assertEqual(event["evidence_sha256"], "0123456789abcdef")
        self.assertEqual(event["artifact_id"], "ART-2")
        self.assertEqual(event["record_id"], "ROW-9")
        self.assertEqual(event["provenance"], "bank.csv:9")


if __name__ == "__main__":
    unittest.main()
