import unittest
from pathlib import Path

from preprocessor.FIR_Preprocessed.fir import preprocess_fir


class FirStructuredFallbackTests(unittest.TestCase):
    def test_neutral_persons_referenced_section_is_extracted_deterministically(self):
        fir_path = Path(__file__).resolve().parents[1] / "Graph_Integration_Layer" / "data" / "fir.txt"
        graph = preprocess_fir(fir_path.read_text(encoding="utf-8"))
        people = {
            entity.get("attributes", {}).get("name")
            for entity in graph.get("entities", [])
            if entity.get("type") == "PERSON"
        }
        self.assertIn("Dev Ahuja", people)
        self.assertIn("Mira Das", people)
        self.assertIn("Kabir Roy", people)
        self.assertIn("Neel Basu", people)
        self.assertTrue(graph.get("relations"))
        self.assertTrue(all(item.get("source_record_number") for item in graph["relations"]))
        self.assertTrue(all("persons-referenced-entry-" in item.get("provenance", "") for item in graph["relations"]))


if __name__ == "__main__":
    unittest.main()
