from __future__ import annotations

PRESET_DETAILS = {
    "best": ("Best available", "Prioritizes the highest available quality; may use larger files and require stream merging."),
    "balanced": ("Balanced 1080p", "Caps video at 1080p and keeps separate high-quality audio when available."),
    "small": ("Smaller file", "Caps video at 720p to reduce download size while keeping good viewing quality."),
    "compatible": ("MP4 compatible", "Prefers MP4 video and M4A audio for broad player compatibility; falls back if needed."),
    "fast": ("Fastest", "Prefers a single format up to 720p, reducing merge work and often completing sooner."),
}


def preset_details(key: str) -> tuple[str, str]:
    return PRESET_DETAILS.get(key, PRESET_DETAILS["best"])
