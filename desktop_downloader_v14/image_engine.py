from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


def scrape_image_urls(
    page_url: str,
    timeout: float = 20,
    headers: Mapping[str, str] | None = None,
) -> list[str]:
    """Collect unique image links from common public HTML image attributes."""
    request_headers = {"User-Agent": "SmartDownloader/1.0"}
    if headers:
        request_headers.update(headers)
    response = requests.get(
        page_url,
        headers=request_headers,
        timeout=timeout,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[str] = []

    for tag in soup.find_all(("img", "source")):
        for attribute in ("src", "data-src", "data-original"):
            value = tag.get(attribute)
            if value:
                candidates.append(value.strip())
        srcset = tag.get("srcset", "")
        for candidate in srcset.split(","):
            value = candidate.strip().split()
            if value:
                candidates.append(value[0])

    for tag in soup.find_all("meta", property="og:image"):
        value = tag.get("content")
        if value:
            candidates.append(value.strip())

    image_urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        absolute = urljoin(page_url, candidate)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if Path(parsed.path).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if absolute not in seen:
            seen.add(absolute)
            image_urls.append(absolute)
    return image_urls


def generate_sequence_urls(pattern: str, start: int, end: int) -> list[str]:
    if start < 0 or end < start:
        raise ValueError("Enter a non-negative start number and an end number at or after it.")
    if end - start > 9999:
        raise ValueError("A sequence can contain at most 10,000 links.")
    if pattern.count("{:") != 1 or not re.search(r"\{:(?:0\d+)?d\}", pattern):
        raise ValueError("Use one number placeholder such as {:03d} in the link pattern.")
    try:
        return [pattern.format(number) for number in range(start, end + 1)]
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError("The link pattern must contain one numeric placeholder, such as {:03d}.") from error



def _unique_output_path(source: Path, suffix: str, extension: str) -> Path:
    """Choose a generated filename without clobbering an earlier result."""
    candidate = source.with_name(f"{source.stem}_{suffix}{extension}")
    index = 1
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_{suffix} ({index}){extension}")
        index += 1
    return candidate


def _save_unique_output(source: Path, suffix: str, extension: str, save_image) -> Path:
    """Save to a temporary file, then atomically publish without overwriting."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source.stem}_{suffix}-",
        suffix=extension,
        dir=source.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        save_image(temporary)
        candidate = source.with_name(f"{source.stem}_{suffix}{extension}")
        index = 1
        while True:
            try:
                # A hard link atomically creates the name and fails if it exists.
                os.link(temporary, candidate)
                return candidate
            except FileExistsError:
                candidate = source.with_name(
                    f"{source.stem}_{suffix} ({index}){extension}"
                )
                index += 1
    finally:
        temporary.unlink(missing_ok=True)


def convert_image(path: str | Path, target_format: str, quality: int = 90) -> Path:
    from PIL import Image

    source = Path(path)
    output_format = target_format.upper().replace("JPG", "JPEG")
    if output_format not in {"PNG", "JPEG", "WEBP", "AVIF"}:
        raise ValueError("Choose PNG, JPEG, WebP, or AVIF.")
    if not 1 <= quality <= 100:
        raise ValueError("Image quality must be between 1 and 100.")
    extension = ".jpg" if output_format == "JPEG" else f".{output_format.lower()}"
    target = None
    try:
        with Image.open(source) as image:
            if output_format == "JPEG" and image.mode in {"RGBA", "LA", "P"}:
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            elif output_format in {"JPEG", "WEBP"} and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            target = _save_unique_output(
                source, "converted", extension,
                lambda temporary: image.save(temporary, format=output_format, quality=quality),
            )
    except Image.DecompressionBombError as error:
        raise ValueError("Image dimensions exceed the safe processing limit.") from error
    return target


def resize_image(path: str | Path, max_width: int, max_height: int) -> Path:
    from PIL import Image, ImageOps

    if max_width <= 0 or max_height <= 0:
        raise ValueError("Width and height must be greater than zero.")
    source = Path(path)
    target = None
    try:
        with Image.open(source) as opened:
            if source.suffix.lower() == ".gif" and getattr(opened, "n_frames", 1) > 1:
                # Resizing only the currently selected Pillow frame silently
                # turns an animated GIF into a still image. Resize every frame
                # and retain the animation timing and loop metadata.
                frames = []
                durations = []
                for frame_index in range(opened.n_frames):
                    opened.seek(frame_index)
                    frame = ImageOps.exif_transpose(opened.copy()).convert("RGBA")
                    frame.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    frames.append(frame)
                    durations.append(opened.info.get("duration", 100))
                loop = opened.info.get("loop", 0)

                def save_animation(temporary):
                    frames[0].save(
                        temporary,
                        format="GIF",
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=loop,
                        disposal=2,
                        optimize=False,
                    )

                target = _save_unique_output(source, "resized", ".gif", save_animation)
            else:
                # Normalize EXIF orientation before sizing; otherwise a rotated
                # portrait image can exceed the requested displayed dimensions.
                image = ImageOps.exif_transpose(opened)
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                if source.suffix.lower() in {".jpg", ".jpeg"} and image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                target = _save_unique_output(
                    source, "resized", source.suffix, lambda temporary: image.save(temporary)
                )
    except Image.DecompressionBombError as error:
        raise ValueError("Image dimensions exceed the safe processing limit.") from error
    return target


def strip_exif(path: str | Path) -> Path:
    """Write a metadata-free copy beside the source and leave the source intact."""
    from PIL import Image

    source = Path(path)
    target = None
    try:
        from PIL import ImageOps

        with Image.open(source) as opened:
            if getattr(opened, "n_frames", 1) > 1:
                raise ValueError("Animated images are not supported for EXIF removal.")
            # Apply the orientation stored in EXIF before dropping metadata.
            # Otherwise portrait phone photos can become sideways after cleanup.
            image = ImageOps.exif_transpose(opened)
            image.load()
            image_format = image.format
            mode = image.mode
            if mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I", "F"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                mode = image.mode
            clean = Image.new(mode, image.size)
            clean.paste(image)
            if mode == "P":
                clean.putpalette(image.getpalette())
            if image_format == "JPEG" and mode not in {"RGB", "L"}:
                clean = clean.convert("RGB")
            target = _save_unique_output(
                source, "no_exif", source.suffix,
                lambda temporary: clean.save(temporary, format=image_format),
            )
    except Image.DecompressionBombError as error:
        raise ValueError("Image dimensions exceed the safe processing limit.") from error
    return target
