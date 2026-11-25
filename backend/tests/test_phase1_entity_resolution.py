"""Focused regression tests for Phase 1 entity resolution and graph integration."""
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "Graph_Integration_Layer"))
from entity_resolution import resolve_entities
from graph_integrator import integrate_graph


class EntityResolutionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.entities = [
            {"id": "p1", "type": "PERSON", "attributes": {"name": "Asha Rao"}},
            {"id": "ph1", "type": "PHONE_NUMBER", "attributes": {"number": "9000000001"}},
            {"id": "a1", "type": "ACCOUNT", "attributes": {"account_id": "ACC100"}},
            {"id": "d1", "type": "DEVICE", "attributes": {"identifier": "android-01"}},
            {"id": "l1", "type": "LOCATION", "attributes": {"name": "Chennai"}},
            {"id": "ph2", "type": "PHONE_NUMBER", "attributes": {"number": "9000000001"}},
        ]
        self.relations = [
            {"source": "p1", "target": "ph1", "relation": "USES_PHONE", "timestamp": "2026-01-01T10:00:00", "provenance": "cdr.csv:row1"},
            {"source": "p1", "target": "a1", "relation": "OWNS_ACCOUNT", "timestamp": "2026-01-01T10:01:00", "provenance": "bank.csv:row1"},
            {"source": "p1", "target": "d1", "relation": "USES_DEVICE", "timestamp": "2026-01-01T10:02:00", "provenance": "device.csv:row1"},
            {"source": "p1", "target": "l1", "relation": "LOCATED_AT", "timestamp": "2026-01-01T10:03:00", "provenance": "gps.csv:row1"},
            {"source": "p1", "target": "ph1", "relation": "USES_PHONE", "timestamp": "2026-01-01T10:00:00", "provenance": "cdr2.csv:row7"},
        ]

    def test_distinct_entity_types_are_not_merged(self):
        result = resolve_entities(self.entities, self.relations)
        ids = ["p1", "ph1", "a1", "d1", "l1"]
        self.assertEqual(len({result["resolved_mapping"][i] for i in ids}), 5)

    def test_same_type_duplicate_phone_records_are_resolved(self):
        result = resolve_entities(self.entities, self.relations)
        self.assertEqual(result["resolved_mapping"]["ph1"], result["resolved_mapping"]["ph2"])

    def test_relationships_from_independent_sources_are_preserved(self):
        result = resolve_entities(self.entities, self.relations)
        graph = integrate_graph(self.entities, self.relations, result)
        self.assertEqual(len(graph["relations"]), len(self.relations))
        self.assertTrue(all(r["source"] != r["target"] for r in graph["relations"]))


if __name__ == "__main__":
    unittest.main()
