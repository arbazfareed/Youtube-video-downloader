import tempfile
import unittest
import zipfile
from pathlib import Path

from zip_archive import create_zip_archive


class ZipCreationTests(unittest.TestCase):
    def test_archives_a_file_by_its_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "notes.txt"
            source.write_text("offline archive", encoding="utf-8")
            destination = create_zip_archive(source, root / "notes.zip")

            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.namelist(), ["notes.txt"])
                self.assertEqual(archive.read("notes.txt"), b"offline archive")

    def test_archives_folder_contents_without_adding_a_duplicate_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photos"
            (source / "2026").mkdir(parents=True)
            (source / "2026" / "image.txt").write_text("image", encoding="utf-8")
            destination = create_zip_archive(source, root / "photos.zip")

            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.namelist(), ["2026/", "2026/image.txt"])
                self.assertEqual(archive.read("2026/image.txt"), b"image")

    def test_refuses_overwrite_and_paths_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "folder"
            source.mkdir()
            (source / "file.txt").write_text("content", encoding="utf-8")
            destination = root / "existing.zip"
            destination.write_bytes(b"keep")

            with self.assertRaises(FileExistsError):
                create_zip_archive(source / "file.txt", destination)
            self.assertEqual(destination.read_bytes(), b"keep")
            with self.assertRaisesRegex(ValueError, "inside its source"):
                create_zip_archive(source, source / "nested.zip")

    def test_overwrite_replaces_existing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.txt"
            source.write_text("new", encoding="utf-8")
            destination = root / "output.zip"
            destination.write_bytes(b"old")

            create_zip_archive(source, destination, overwrite=True)

            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(archive.read("input.txt"), b"new")

    def test_rejects_non_zip_output_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.txt"
            source.write_text("content", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"end in \.zip"):
                create_zip_archive(source, root / "output.tar")
            with self.assertRaises(FileNotFoundError):
                create_zip_archive(root / "missing.txt", root / "output.zip")


if __name__ == "__main__":
    unittest.main()
