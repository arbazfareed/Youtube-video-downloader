from __future__ import annotations

from pathlib import Path


def rename_lowercase(job_id: str, filepath: str) -> str:
    del job_id
    source = Path(filepath)
    if not source.is_file():
        return str(source)
    desired = source.with_name(source.name.lower())
    if source.name == desired.name:
        return str(source)
    target = desired
    suffix = 1
    while target.exists() and not target.samefile(source):
        target = desired.with_name(f"{desired.stem} ({suffix}){desired.suffix}")
        suffix += 1
    source.rename(target)
    return str(target)


def register() -> dict:
    return {
        "name": "example-lowercase-filenames",
        "events": {"on_complete": rename_lowercase},
    }
