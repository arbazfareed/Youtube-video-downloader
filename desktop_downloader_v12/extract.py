from __future__ import annotations

import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO


def _member_path(root: Path, name: str) -> Path:
    normalized = name.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        not normalized
        or "\x00" in normalized
        or relative.is_absolute()
        or PureWindowsPath(name).is_absolute()
        or PureWindowsPath(name).drive
        or any(part in {"..", "."} for part in relative.parts)
        or (relative.parts and ":" in relative.parts[0])
    ):
        raise ValueError(f"Unsafe archive member path: {name!r}")
    target = (root / Path(*relative.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Archive member escapes the extraction folder: {name!r}")
    return target


def _copy_member(source: BinaryIO, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        shutil.copyfileobj(source, output)


def _extract_zip(archive_path: Path, target: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = _member_path(target, member.filename)
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind == stat.S_IFLNK or kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError(f"Links and special files are not extracted: {member.filename!r}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                with archive.open(member) as source:
                    _copy_member(source, destination)


def _extract_tar(archive_path: Path, target: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive.getmembers():
            destination = _member_path(target, member.name)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError(f"Could not read archive member: {member.name}")
                with source:
                    _copy_member(source, destination)
            else:
                raise ValueError(
                    f"Links and special files are not extracted: {member.name!r}"
                )


def _extract_rar(archive_path: Path, target: Path) -> None:
    try:
        import rarfile
    except ImportError as error:
        raise RuntimeError("RAR extraction requires the rarfile package.") from error

    with rarfile.RarFile(archive_path) as archive:
        for member in archive.infolist():
            destination = _member_path(target, member.filename)
            if member.is_symlink():
                raise ValueError(f"Links are not extracted: {member.filename!r}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                with archive.open(member) as source:
                    _copy_member(source, destination)


def extract_archive(path: Path) -> Path | None:
    archive_path = path.expanduser().resolve()
    if not archive_path.is_file():
        return None

    suffixes = [suffix.lower() for suffix in archive_path.suffixes]
    if suffixes[-2:] == [".tar", ".gz"]:
        folder_name = archive_path.name[:-7]
        archive_type = "tar"
    elif suffixes[-2:] == [".tar", ".bz2"]:
        folder_name = archive_path.name[:-8]
        archive_type = "tar"
    elif suffixes[-2:] == [".tar", ".xz"]:
        folder_name = archive_path.name[:-7]
        archive_type = "tar"
    else:
        suffix = archive_path.suffix.lower()
        archive_type = {
            ".zip": "zip",
            ".tar": "tar",
            ".tgz": "tar",
            ".rar": "rar",
        }.get(suffix)
        if archive_type is None:
            return None
        folder_name = archive_path.stem

    destination = archive_path.parent / folder_name
    if destination.exists():
        raise FileExistsError(f"Extraction folder already exists: {destination}")

    with tempfile.TemporaryDirectory(
        prefix=f".{folder_name}.extract-", dir=archive_path.parent
    ) as temporary_directory:
        staging = Path(temporary_directory)
        if archive_type == "zip":
            _extract_zip(archive_path, staging)
        elif archive_type == "tar":
            _extract_tar(archive_path, staging)
        elif archive_type == "rar":
            _extract_rar(archive_path, staging)
        staging.rename(destination)
    return destination
