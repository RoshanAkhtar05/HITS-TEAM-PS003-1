import tempfile
import unittest
from pathlib import Path

from api.case_pipeline import (
    classify_evidence_file,
    stage_case_inputs,
    validate_case_id,
)


class CasePipelineStagingTests(unittest.TestCase):
    def test_classifies_only_explicit_supported_source_names(self):
        self.assertEqual(classify_evidence_file(Path("cdr_records.csv")), ("cdr", "cdr.csv"))
        self.assertEqual(classify_evidence_file(Path("bank_transactions.csv")), ("transactions", "transactions.csv"))
        self.assertIsNone(classify_evidence_file(Path("random_export.csv")))
        self.assertIsNone(classify_evidence_file(Path("camera.mp4")))

    def test_stages_sources_into_separate_case_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            workspace = root / "case_data" / "CASE-123"
            uploads.mkdir(parents=True)
            (uploads / "cdr_records.csv").write_text("caller,receiver\n111,222\n", encoding="utf-8")
            (uploads / "bank_transactions.csv").write_text("from,to,amount\nA,B,10\n", encoding="utf-8")
            (uploads / "photo.jpg").write_bytes(b"image")

            result = stage_case_inputs(uploads, workspace)

            self.assertTrue((Path(result["input_dir"]) / "cdr.csv").exists())
            self.assertTrue((Path(result["input_dir"]) / "transactions.csv").exists())
            self.assertEqual(result["unsupported_files"], ["photo.jpg"])
            self.assertTrue((uploads / "photo.jpg").exists())  # original evidence is retained

    def test_staged_source_manifest_keeps_upload_identity_and_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "cdr_export.csv").write_text("caller,receiver\n111,222\n", encoding="utf-8")

            result = stage_case_inputs(
                uploads,
                root / "workspace",
                evidence_records=[{
                    "id": 42,
                    "filename": "cdr_export.csv",
                    "file_hash": "abc123",
                }],
            )

            self.assertEqual(
                result["source_manifest"]["cdr.csv"],
                {"original_filename": "cdr_export.csv", "evidence_id": 42, "sha256": "abc123"},
            )

    def test_newest_evidence_record_is_used_for_reuploaded_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "fir_e2e_test.txt").write_text(
                "updated synthetic FIR", encoding="utf-8"
            )

            result = stage_case_inputs(
                uploads,
                root / "workspace",
                evidence_records=[
                    {"id": 99, "filename": "fir_e2e_test.txt", "file_hash": "new-hash"},
                    {"id": 42, "filename": "fir_e2e_test.txt", "file_hash": "old-hash"},
                ],
            )

            self.assertEqual(
                result["source_manifest"]["fir.txt"],
                {
                    "original_filename": "fir_e2e_test.txt",
                    "evidence_id": 99,
                    "sha256": "new-hash",
                },
            )

    def test_duplicate_source_category_is_reported_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            uploads.mkdir()
            (uploads / "cdr_a.csv").write_text("a\n", encoding="utf-8")
            (uploads / "cdr_b.csv").write_text("b\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "More than one uploaded file"):
                stage_case_inputs(uploads, root / "workspace")

    def test_rejects_path_like_case_ids(self):
        self.assertEqual(validate_case_id("CASE-123_Test"), "CASE-123_Test")
        with self.assertRaises(ValueError):
            validate_case_id("../CASE-123")


if __name__ == "__main__":
    unittest.main()
