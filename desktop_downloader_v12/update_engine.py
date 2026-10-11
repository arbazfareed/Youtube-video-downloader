from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


REPOSITORY = "arbazfareed/Youtube-video-downloader"
APP_VERSION = "12.0.0"
_MAX_RELEASE_BYTES = 1_000_000_000
_VERSION_PATTERN = re.compile(r"^v?(\d+(?:\.\d+){0,3})$")
_SHA256_PATTERN = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseUpdate:
    version: str
    asset_url: str
    digest: str
    size: int


def _version_tuple(value: str) -> tuple[int, ...]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise UpdateError(f"Unsupported release version: {value!r}")
    version = tuple(int(part) for part in match.group(1).split("."))
    return version + (0,) * (4 - len(version))


def _asset_name(system: str | None = None) -> str:
    selected_system = (system or platform.system()).casefold()
    if selected_system == "windows":
        return "SmartDownloader12-Windows.zip"
    if selected_system == "linux":
        return "SmartDownloader12-Linux.zip"
    raise UpdateError(f"Automatic updates are not packaged for {selected_system}.")


def check_for_update(
    current_version: str,
    *,
    repository: str = REPOSITORY,
    system: str | None = None,
    timeout: float = 10,
) -> ReleaseUpdate | None:
    request = Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SmartDownloader12-update-check",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            release = json.load(response)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise UpdateError(f"Could not check GitHub Releases: {error}") from error
    if not isinstance(release, dict):
        raise UpdateError("GitHub returned an invalid release record.")
    tag_name = release.get("tag_name")
    if not isinstance(tag_name, str):
        raise UpdateError("The latest release does not contain a version tag.")
    if _version_tuple(tag_name) <= _version_tuple(current_version):
        return None

    asset_name = _asset_name(system)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("The latest release does not contain an asset list.")
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != asset_name:
            continue
        asset_url = asset.get("browser_download_url")
        digest = asset.get("digest")
        size = asset.get("size")
        if (
            not isinstance(asset_url, str)
            or not asset_url.startswith(
                f"https://github.com/{repository}/releases/download/"
            )
        ):
            raise UpdateError("The release asset URL is not trusted.")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise UpdateError(
                "The release asset has no valid SHA-256 digest; refusing to download it."
            )
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or size > _MAX_RELEASE_BYTES
        ):
            raise UpdateError("The release asset has an invalid or excessive size.")
        return ReleaseUpdate(tag_name, asset_url, digest.casefold(), size)
    raise UpdateError(f"The latest release is missing {asset_name}.")


def download_verified_update(
    update: ReleaseUpdate,
    destination: Path,
    *,
    timeout: float = 30,
) -> Path:
    digest_match = _SHA256_PATTERN.fullmatch(update.digest)
    if digest_match is None:
        raise UpdateError("The update does not contain a valid SHA-256 digest.")
    _version_tuple(update.version)
    if (
        not isinstance(update.size, int)
        or isinstance(update.size, bool)
        or update.size <= 0
        or update.size > _MAX_RELEASE_BYTES
    ):
        raise UpdateError("The release asset has an invalid or excessive size.")
    if not update.asset_url.startswith(
        f"https://github.com/{REPOSITORY}/releases/download/"
    ):
        raise UpdateError("The release asset URL is not trusted.")
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".download", dir=destination.parent
    )
    temporary_path = Path(temporary_name)
    digest = hashlib.sha256()
    byte_count = 0
    request = Request(update.asset_url, headers={"User-Agent": "SmartDownloader12"})
    try:
        with os.fdopen(descriptor, "wb") as output, urlopen(
            request, timeout=timeout
        ) as response:
            while chunk := response.read(1024 * 1024):
                byte_count += len(chunk)
                if byte_count > update.size or byte_count > _MAX_RELEASE_BYTES:
                    raise UpdateError("The downloaded update exceeds its declared size.")
                digest.update(chunk)
                output.write(chunk)
        if byte_count != update.size:
            raise UpdateError(
                f"Update size mismatch: expected {update.size} bytes, got {byte_count}."
            )
        actual_digest = digest.hexdigest()
        if actual_digest.casefold() != digest_match.group(1).casefold():
            raise UpdateError("Update SHA-256 verification failed; the file was discarded.")
        os.replace(temporary_path, destination)
        return destination
    except (OSError, URLError, TimeoutError) as error:
        raise UpdateError(f"Could not download the update: {error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)
