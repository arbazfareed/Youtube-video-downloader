from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_libreoffice() -> Path | None:
    for executable in ("soffice", "libreoffice"):
        located = shutil.which(executable)
        if located:
            return Path(located)

    candidates: list[Path] = []
    if os.name == "nt":
        for variable in (
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "PROGRAMW6432",
            "LOCALAPPDATA",
        ):
            base = os.environ.get(variable)
            if base:
                candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        candidates.append(
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        )
    else:
        candidates.extend(
            (
                Path("/usr/lib/libreoffice/program/soffice"),
                Path("/usr/lib64/libreoffice/program/soffice"),
                Path("/usr/bin/soffice"),
            )
        )
    return next((path for path in candidates if path.is_file()), None)


def _validate_conversion(
    source: Path,
    output: Path | None,
    source_extension: str,
    output_extension: str,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    source = Path(source).expanduser()
    if source.suffix.lower() != source_extension:
        raise ValueError(f"Choose a {source_extension.upper()} file.")
    if not source.is_file():
        raise FileNotFoundError(f"Input file does not exist: {source}")

    destination = (
        Path(output).expanduser()
        if output is not None
        else source.with_suffix(output_extension)
    )
    if destination.suffix.lower() != output_extension:
        raise ValueError(f"Output filename must end in {output_extension}.")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output folder does not exist: {destination.parent}")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {destination}")
    return source.resolve(), destination.resolve()


def convert_docx_to_pdf(
    source: Path,
    output: Path | None = None,
    libreoffice: Path | None = None,
    overwrite: bool = False,
) -> Path:
    source, destination = _validate_conversion(
        source, output, ".docx", ".pdf", overwrite
    )
    executable = libreoffice or find_libreoffice()
    if executable is None:
        raise RuntimeError(
            "DOCX to PDF conversion requires LibreOffice. Install LibreOffice "
            "and make sure 'soffice' is on PATH, then try again."
        )

    try:
        with tempfile.TemporaryDirectory(
            prefix=".smart-downloader-pdf-", dir=destination.parent
        ) as temporary_directory:
            temporary_output = Path(temporary_directory) / source.with_suffix(".pdf").name
            office_profile = Path(temporary_directory) / "profile"
            result = subprocess.run(
                [
                    str(executable),
                    "--headless",
                    f"-env:UserInstallation={office_profile.as_uri()}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    temporary_directory,
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if (
                result.returncode != 0
                or not temporary_output.is_file()
                or temporary_output.stat().st_size == 0
            ):
                detail = (result.stderr or result.stdout).strip()
                message = f"LibreOffice could not convert {source.name} to PDF."
                if detail:
                    message += f"\n{detail}"
                raise RuntimeError(message)
            temporary_output.replace(destination)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"LibreOffice did not finish converting {source.name} within five minutes."
        ) from error
    except OSError as error:
        raise RuntimeError(f"Could not run LibreOffice: {error}") from error
    return destination


def convert_pdf_to_docx(
    source: Path,
    output: Path | None = None,
    overwrite: bool = False,
) -> Path:
    source, destination = _validate_conversion(
        source, output, ".pdf", ".docx", overwrite
    )
    try:
        from pdf2docx import Converter
    except ImportError as error:
        raise RuntimeError(
            "PDF to DOCX conversion requires pdf2docx. Install the app's "
            "requirements and try again."
        ) from error

    try:
        with tempfile.TemporaryDirectory(
            prefix=".smart-downloader-docx-", dir=destination.parent
        ) as temporary_directory:
            temporary_output = Path(temporary_directory) / "converted.docx"
            converter = Converter(str(source))
            try:
                converter.convert(str(temporary_output))
            finally:
                converter.close()
            if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                raise RuntimeError("PDF to DOCX conversion produced an empty output.")
            temporary_output.replace(destination)
    except Exception as error:
        raise RuntimeError(f"Could not convert {source.name} to DOCX: {error}") from error
    return destination
