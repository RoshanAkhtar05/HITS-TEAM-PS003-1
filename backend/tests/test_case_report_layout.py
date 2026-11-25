import json
import tempfile
import unittest
from pathlib import Path

from api.case_report import build_case_report_markdown, refresh_case_report_from_outputs
from api.pdf_generator import markdown_to_pdf, _split_markdown_table_row


class CaseReportLayoutTests(unittest.TestCase):
    def _fixture(self):
        manifest = {
            "staged_sources": {"cdr": "cdr.csv", "gps": "gps.csv"},
            "source_processing": [
                {"category": "cdr", "source_file": "cdr.csv", "status": "processed", "entities": 2, "relations": 1},
                {"category": "gps", "source_file": "gps.csv", "status": "processed", "entities": 1, "relations": 1},
            ],
        }
        graph = {
            "master_entities": [
                {"master_id": "M1", "master_type": "PHONE_NUMBER", "resolved_values": ["10000000001"]},
                {"master_id": "M2", "master_type": "CELL_TOWER", "resolved_values": ["Tower A"]},
            ],
            "relations": [
                {
                    "source": "M1", "target": "M2", "relation": "CONNECTED_TO_TOWER",
                    "source_file": "cdr.csv", "evidence_id": "EVD-1", "record_id": "cdr:row:2",
                }
            ],
        }
        timeline = {
            "scenes": [
                {
                    "scene_id": "SCENE_01", "label": "Cell tower connections",
                    "time_basis": "wall_clock_unverified", "timezone_status": "timezone_unknown",
                    "window_start": "2026-05-22T20:30:00", "window_end": "2026-05-22T21:00:00",
                    "events": [
                        {
                            "timestamp": "2026-05-22 20:30:00", "timestamp_status": "timezone_unknown",
                            "description": "10000000001 connected to Tower A", "source_file": "cdr.csv",
                            "evidence_id": "EVD-1", "record_id": "cdr:row:2",
                            "provenance": "cdr.csv#row=2",
                        }
                    ],
                }
            ],
            "unplaced_events": [{"description": "GPS record with no timestamp", "source_file": "gps.csv"}],
        }
        return manifest, graph, timeline

    def test_markdown_table_row_is_split_into_cells(self):
        self.assertEqual(
            _split_markdown_table_row("| CDR | cdr.csv | processed | 8 | 30 | — |"),
            ["CDR", "cdr.csv", "processed", "8", "30", "—"],
        )

    def test_report_timeline_counts_reconcile(self):
        manifest, graph, timeline = self._fixture()
        report = build_case_report_markdown("CASE_TEST", "Test Case", manifest, graph, timeline)
        self.assertIn("Total timeline events extracted: 2", report)
        self.assertIn("Events placed into scenes: 1", report)
        self.assertIn("Unplaced events requiring review: 1", report)
        self.assertIn("Events with timezone unknown: 1", report)
        self.assertIn("Timeline accounting", report)

    def test_relationship_summary_contains_source_references(self):
        manifest, graph, timeline = self._fixture()
        report = build_case_report_markdown("CASE_TEST", "Test Case", manifest, graph, timeline)
        self.assertIn("Connected To Tower", report)
        self.assertIn("cdr.csv", report)
        self.assertIn("EVD-1", report)
        self.assertIn("cdr:row:2", report)


    def test_export_refreshes_report_from_existing_case_outputs(self):
        manifest, graph, timeline = self._fixture()
        manifest["status"] = "success"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "validation").mkdir()
            (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (output / "unified_graph.json").write_text(json.dumps(graph), encoding="utf-8")
            (output / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (output / "validation" / "alerts.json").write_text("[]", encoding="utf-8")
            (output / "investigation_report.md").write_text("outdated report", encoding="utf-8")

            refreshed = refresh_case_report_from_outputs("CASE_TEST", "Test Case", output)
            saved = (output / "investigation_report.md").read_text(encoding="utf-8")

            self.assertEqual(refreshed, saved)
            self.assertIn("Total timeline events extracted: 2", saved)
            self.assertIn("cdr:row:2", saved)

    def test_pdf_generation_renders_markdown_tables(self):
        manifest, graph, timeline = self._fixture()
        report = build_case_report_markdown("CASE_TEST", "Test Case", manifest, graph, timeline)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.pdf"
            markdown_to_pdf(report, output, "CASE_TEST")
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
