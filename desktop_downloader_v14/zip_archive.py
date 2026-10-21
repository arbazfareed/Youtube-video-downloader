from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path


def create_zip_archive(
    source: Path,
    destination: Path,
    overwrite: bool = False,
) -> Path:
    source = Path(source).expanduser()
    if source.is_symlink():
        raise ValueError("Symbolic links cannot be added to an archive.")
    source = source.resolve()
    if not source.exists() or not (source.is_file() or source.is_dir()):
        raise FileNotFoundError(f"Input file or folder does not exist: {source}")

    destination = Path(destination).expanduser()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Output filename must end in .zip.")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output folder does not exist: {destination.parent}")
    destination = destination.resolve()
    if destination == source or (source.is_dir() and destination.is_relative_to(source)):
        raise ValueError("The ZIP file cannot be saved inside its source.")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {destination}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}.",
            suffix=".zip",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        with zipfile.ZipFile(
            temporary_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            if source.is_file():
                archive.write(source, arcname=source.name)
            else:
                for member in sorted(source.rglob("*")):
                    if member.is_symlink():
                        continue
                    relative_name = member.relative_to(source)
                    if member.is_dir():
                        archive.writestr(f"{relative_name.as_posix()}/", "")
                    elif member.is_file():
                        archive.write(member, arcname=relative_name.as_posix())

        if overwrite:
            os.replace(temporary_path, destination)
        else:
            descriptor = os.open(
                destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666
            )
            os.close(descriptor)
            try:
                os.replace(temporary_path, destination)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return destination
