from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


def calculate_checksum(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: Path, algorithm: str, expected: str) -> tuple[str, bool]:
    actual = calculate_checksum(path, algorithm)
    return actual, hmac.compare_digest(actual.casefold(), expected.strip().casefold())
