from __future__ import annotations

import hashlib
import hmac
from pathlib import Path


def verify_checksum(path: Path, algorithm: str, expected: str) -> tuple[str, bool]:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    return actual, hmac.compare_digest(actual.casefold(), expected.strip().casefold())
