import tempfile
import unittest
from pathlib import Path

from api.pdf_generator import markdown_to_pdf


class PDFReportGenerationTests(unittest.TestCase):
    def test_report_pdf_handles_unicode_punctuation_and_currency(self):
        markdown = """# TATHYA-DF Report

- Timeline window — 22 May 2026 → 23 May 2026
- Transfer amount: ₹9,500
- Investigator review: “Verify the source record.”
"""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.pdf"
            markdown_to_pdf(markdown, out, "TEST_CASE")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
