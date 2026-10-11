from __future__ import annotations

import hashlib
import importlib.metadata
import os
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


def _smoke_test_app(app_class) -> None:
    root = tk.Tk()
    try:
        app_class(root)
        root.update()
        if root.title() != "Smart Downloader" or not root.winfo_viewable():
            raise RuntimeError("The Smart Downloader window did not become visible.")
    finally:
        root.destroy()


def _attach_console() -> None:
    if os.name != "nt" or (sys.stdout is not None and sys.stderr is not None):
        return

    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AttachConsole.argtypes = [ctypes.c_ulong]
    kernel32.AttachConsole.restype = ctypes.c_int
    kernel32.AllocConsole.restype = ctypes.c_int
    if not kernel32.AttachConsole(0xFFFFFFFF) and not kernel32.AllocConsole():
        raise OSError(ctypes.get_last_error(), "Could not open a command console.")
    sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")


def main() -> int:
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "--cli":
        _attach_console()
        _ensure_dependencies()
        from cli import main as run_cli

        return run_cli(arguments[1:])
    if arguments and arguments[0] == "--api":
        _attach_console()
        _ensure_dependencies()
        from api import main as run_api

        run_api()
        return 0

    smoke_test = "--smoke-test" in arguments
    try:
        _ensure_dependencies()
        from app import DownloaderApp, main as run_app

        if smoke_test:
            _smoke_test_app(DownloaderApp)
        else:
            run_app()
        return 0
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

        if smoke_test:
            raise

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Smart Downloader could not start",
            f"The app encountered a startup error.\n\n{details}",
            parent=root,
        )
        root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
