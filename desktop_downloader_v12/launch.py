from __future__ import annotations

import hashlib
import importlib.metadata
import re
import subprocess
import sys
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def _requirement_names(requirements_path: Path) -> list[str]:
    names = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        names.append(re.split(r"[<=>!~\[]", requirement, maxsplit=1)[0].strip())
    return names


def _ensure_dependencies() -> None:
    if getattr(sys, "frozen", False):
        return

    app_dir = Path(__file__).resolve().parent
    requirements_path = app_dir / "requirements.txt"
    requirements = requirements_path.read_bytes()
    digest = hashlib.sha256(requirements).hexdigest()
    stamp_path = app_dir / ".venv" / ".requirements-sha256"
    try:
        installed_digest = stamp_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        installed_digest = ""

    missing = []
    for package in _requirement_names(requirements_path):
        try:
            importlib.metadata.distribution(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)

    if digest == installed_digest and not missing:
        return

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "-r",
            str(requirements_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        raise RuntimeError(f"Could not install app dependencies.\n{output}")
    stamp_path.write_text(digest, encoding="ascii")


def main() -> None:
    try:
        _ensure_dependencies()
        from app import main as run_app

        run_app()
    except Exception as error:
        app_dir = Path(sys.executable).resolve().parent if getattr(
            sys, "frozen", False,
        ) else Path(__file__).resolve().parent
        log_path = app_dir / "startup-error.log"
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
            details = f"{error}\n\nDetails were saved to:\n{log_path}"
        except OSError:
            details = str(error)

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Smart Downloader 12.0 could not start",
            f"The app encountered a startup error.\n\n{details}",
            parent=root,
        )
        root.destroy()


if __name__ == "__main__":
    main()
