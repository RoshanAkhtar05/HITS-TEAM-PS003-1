import unittest
from pathlib import Path

from Graph_Integration_Layer.investigator_annotations import load_annotations, build_annotation_relations


class AnnotationMatchingTests(unittest.TestCase):
    def test_exact_identifiers_match_without_fuzzy_person_names(self):
        lookup = {
            "p1": {"type": "PERSON", "attributes": {"name": "Rahul Sen"}},
            "p2": {"type": "PERSON", "attributes": {"name": "Rahul Sharma"}},
            "phone1": {"type": "PHONE_NUMBER", "attributes": {"number": "9876543210"}},
            "device1": {"type": "DEVICE", "attributes": {"identifier": "ANDROID_001"}},
        }
        annotations = [
            {"source_entity": "Rahul Sen", "target_entity": "9876543210", "relation": "USES_PHONE", "confidence": 0.99, "_source_record_number": 1},
            {"source_entity": "Rahul", "target_entity": "ANDROID_001", "relation": "USES_DEVICE", "confidence": 0.9, "_source_record_number": 2},
        ]
        relations = build_annotation_relations(annotations, lookup)
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["source"], "p1")
        self.assertEqual(relations[0]["target"], "phone1")
        self.assertEqual(relations[0]["source_record_number"], 1)

    def test_annotation_loader_adds_one_based_source_record_number(self):
        path = Path(__file__).resolve().parents[1] / "Graph_Integration_Layer" / "data" / "annotations.csv"
        rows = load_annotations(str(path))
        self.assertEqual(rows[0]["_source_record_number"], 1)
        self.assertEqual(rows[-1]["_source_record_number"], len(rows))


if __name__ == "__main__":
    unittest.main()
