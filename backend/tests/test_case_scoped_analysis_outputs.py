import json
import tempfile
import unittest
from pathlib import Path

from analysis.graph_summary.summarize import run_summary
from analysis.timeline_reconstruction.reconstruct import run_reconstruction


class CaseScopedAnalysisOutputTests(unittest.TestCase):
    def _write_graph(self, path: Path, prefix: str, entity_count: int):
        entities = [
            {
                "master_id": f"{prefix}_ENTITY_{index}",
                "master_type": "PERSON" if index == 0 else "ENTITY",
                "entity_types": ["PERSON" if index == 0 else "ACCOUNT"],
                "resolved_values": [f"{prefix} Person" if index == 0 else f"{prefix} Account {index}"],
                "source_entities": [],
            }
            for index in range(entity_count)
        ]
        relations = []
        for index in range(1, entity_count):
            relations.append({
                "source": entities[0]["master_id"],
                "target": entities[index]["master_id"],
                "relation": "CALLED",
                "timestamp": "2026-05-22T10:00:00+05:30",
                "confidence": 0.9,
                "source_type": "cdr",
                "source_file": f"{prefix}_cdr.csv",
                "record_id": f"{prefix}_row_{index}",
                "attributes": {"duration": 20},
            })
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"master_entities": entities, "relations": relations}), encoding="utf-8")

    def test_summary_and_timeline_outputs_are_written_to_each_case_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases = {"CASE_A": 2, "CASE_B": 4}
            for case_id, count in cases.items():
                case_root = root / case_id
                graph_path = case_root / "input_graph.json"
                summary_path = case_root / "outputs" / "summary.json"
                timeline_path = case_root / "outputs" / "timeline.json"
                self._write_graph(graph_path, case_id, count)

                summary = run_summary(graph_path=graph_path, output_path=summary_path, prefer_neo4j=False)
                timeline = run_reconstruction(graph_path=graph_path, output_path=timeline_path, prefer_neo4j=False)

                self.assertTrue(summary_path.exists())
                self.assertTrue(timeline_path.exists())
                self.assertEqual(summary["overview"]["total_entities"], count)
                self.assertEqual(timeline["total_events"], count - 1)

            case_a_summary = json.loads((root / "CASE_A" / "outputs" / "summary.json").read_text())
            case_b_summary = json.loads((root / "CASE_B" / "outputs" / "summary.json").read_text())
            self.assertEqual(case_a_summary["overview"]["total_entities"], 2)
            self.assertEqual(case_b_summary["overview"]["total_entities"], 4)


if __name__ == "__main__":
    unittest.main()
