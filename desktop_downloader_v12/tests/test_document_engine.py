import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf as fitz

from document_engine import (
    convert_docx_to_pdf,
    convert_pdf_to_docx,
    find_libreoffice,
)


class DocumentEngineTests(unittest.TestCase):
    @patch("document_engine.subprocess.run")
    @patch("document_engine.find_libreoffice", return_value=Path("soffice"))
    def test_docx_to_pdf_runs_libreoffice_and_creates_selected_output(
        self, _find_office, run
    ):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.docx"
            source.write_bytes(b"docx input")
            output = Path(directory) / "custom-name.pdf"

            def convert(arguments, **_kwargs):
                output_directory = Path(arguments[arguments.index("--outdir") + 1])
                (output_directory / "source.pdf").write_bytes(b"pdf output")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            run.side_effect = convert
            result = convert_docx_to_pdf(source, output)

            self.assertEqual(result, output.resolve())
            self.assertEqual(output.read_bytes(), b"pdf output")
            self.assertIn("--headless", run.call_args.args[0])

    @patch("document_engine.shutil.which", side_effect=[None, "C:/LibreOffice/soffice"])
    def test_libreoffice_discovery_supports_both_command_names(self, which):
        self.assertEqual(find_libreoffice(), Path("C:/LibreOffice/soffice"))
        self.assertEqual(
            [call.args[0] for call in which.call_args_list],
            ["soffice", "libreoffice"],
        )

    def test_docx_to_pdf_reports_missing_libreoffice(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.docx"
            source.write_bytes(b"docx input")
            with patch("document_engine.find_libreoffice", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "requires LibreOffice"):
                    convert_docx_to_pdf(source)

    def test_pdf_to_docx_converts_local_text_pdf(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_text((72, 72), "Local conversion smoke test")
            pdf.save(source)
            pdf.close()

            output = convert_pdf_to_docx(source)

            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as document:
                self.assertIn("word/document.xml", document.namelist())

    def test_pdf_to_docx_refuses_to_replace_existing_output_by_default(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.pdf"
            source.write_bytes(b"not used because output validation happens first")
            output = Path(directory) / "source.docx"
            output.write_bytes(b"keep existing")

            with self.assertRaises(FileExistsError):
                convert_pdf_to_docx(source, output)

            self.assertEqual(output.read_bytes(), b"keep existing")


if __name__ == "__main__":
    unittest.main()
