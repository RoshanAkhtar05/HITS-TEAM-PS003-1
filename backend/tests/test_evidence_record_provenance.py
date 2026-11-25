"""Regression tests for source-row evidence provenance in graph/timeline output."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from preprocessor.CallDetailsRecord.cdr import preprocess_cdr  # noqa: E402
from Graph_Integration_Layer.evidence_provenance import attach_evidence_provenance  # noqa: E402
from analysis.timeline_reconstruction.reconstruct import build_event_list  # noqa: E402


class EvidenceRecordProvenanceTests(unittest.TestCase):
    def test_cdr_relations_keep_source_row_and_upload_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cdr_path = root / "cdr.csv"
            cdr_path.write_text(
                "caller_number,receiver_number,timestamp,duration,call_type,tower_id\n"
                "9876543210,9123456780,2026-05-22 20:30:00,185,OUTGOING,Twr_Kol_102\n"
                "9123456780,9876543210,2026-05-22 20:45:00,60,INCOMING,Twr_Kol_105\n",
                encoding="utf-8",
            )

            graph = preprocess_cdr(str(cdr_path))
            manifest = {
                "cdr.csv": {
                    "original_filename": "operator_cdr_export.csv",
                    "evidence_id": 2,
                    "sha256": "ab" * 32,
                }
            }
            attach_evidence_provenance(graph, "cdr.csv", manifest)

            relations = graph["relations"]
            self.assertEqual(len(relations), 4)
            first_row_relations = [r for r in relations if r["source_record_number"] == 1]
            second_row_relations = [r for r in relations if r["source_record_number"] == 2]
            self.assertEqual(len(first_row_relations), 2)
            self.assertEqual(len(second_row_relations), 2)

            first = first_row_relations[0]
            self.assertEqual(first["source_file"], "operator_cdr_export.csv")
            self.assertEqual(first["evidence_id"], "2")
            self.assertEqual(first["evidence_sha256"], "ab" * 32)
            self.assertEqual(first["provenance"], "operator_cdr_export.csv:data-row:1")
            self.assertEqual(first["provenance_type"], "generated_from_parser_row_number")
            self.assertIn("ROW-000001", first["record_id"])
            self.assertTrue(first["artifact_id"].startswith("ART-"))

            # Both derived relations from the same source row share an artifact
            # locator, while each relationship has its own record identifier.
            self.assertEqual(first_row_relations[0]["artifact_id"], first_row_relations[1]["artifact_id"])
            self.assertNotEqual(first_row_relations[0]["record_id"], first_row_relations[1]["record_id"])
            self.assertNotEqual(first_row_relations[0]["artifact_id"], second_row_relations[0]["artifact_id"])

            events = build_event_list(relations, {})
            first_event = next(event for event in events if event["source_record_number"] == 1)
            self.assertEqual(first_event["source_file"], "operator_cdr_export.csv")
            self.assertEqual(first_event["evidence_id"], "2")
            self.assertEqual(first_event["artifact_id"], first["artifact_id"])
            self.assertEqual(first_event["record_id"], first["record_id"])
            self.assertEqual(first_event["provenance"], "operator_cdr_export.csv:data-row:1")
            self.assertEqual(first_event["provenance_type"], "generated_from_parser_row_number")

    def test_existing_preprocessor_provenance_is_preserved(self):
        graph = {
            "entities": [],
            "relations": [{
                "source": "a", "target": "b", "relation": "CALLED",
                "timestamp": "2026-05-22T20:30:00", "provenance": "native_parser:record-17",
                "record_id": "NATIVE-17", "artifact_id": "NATIVE-ART-17",
            }],
        }
        attach_evidence_provenance(graph, "cdr.csv", {
            "cdr.csv": {"original_filename": "uploaded.csv", "evidence_id": 9, "sha256": "ff" * 32}
        })
        relation = graph["relations"][0]
        self.assertEqual(relation["record_id"], "NATIVE-17")
        self.assertEqual(relation["artifact_id"], "NATIVE-ART-17")
        self.assertEqual(relation["provenance"], "uploaded.csv:record-17")
        self.assertEqual(relation["provenance_type"], "preprocessor_supplied")


if __name__ == "__main__":
    unittest.main()
