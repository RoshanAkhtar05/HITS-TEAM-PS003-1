import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from Graph_Integration_Layer.main import main


class MultiSourceIntegrationSmokeTests(unittest.TestCase):
    def test_bundled_synthetic_investigation_processes_all_integrated_sources(self):
        source_dir = Path(__file__).resolve().parents[1] / "Graph_Integration_Layer" / "data"
        source_files = [
            "cdr.csv", "gps.csv", "transactions.csv", "fir.txt",
            "emails.txt", "chat.txt", "social.json", "annotations.csv",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "inputs"
            input_dir.mkdir()
            vehicle_dir = root / "vehicle"
            vehicle_dir.mkdir()
            source_manifest = {}
            for filename in source_files:
                source = source_dir / filename
                shutil.copy2(source, input_dir / filename)
                source_manifest[filename] = {
                    "original_filename": filename,
                    "evidence_id": f"TEST-{filename}",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }

            result = main(
                data_dir=input_dir,
                vehicle_data_dir=vehicle_dir,
                output_path=root / "unified_graph.json",
                source_manifest=source_manifest,
            )

        statuses = {item["category"]: item["status"] for item in result["preprocessor_status"]}
        for category in ("cdr", "gps", "transactions", "fir", "emails", "chat", "social", "annotations"):
            self.assertEqual(statuses.get(category), "processed", category)
        graph = result["graph"]
        self.assertGreater(len(graph.get("master_entities", [])), 10)
        self.assertGreater(len(graph.get("relations", [])), 20)
        for relation in graph["relations"]:
            self.assertTrue(relation.get("source_file"))
            self.assertTrue(relation.get("record_id"))
            self.assertTrue(relation.get("provenance"))


if __name__ == "__main__":
    unittest.main()
