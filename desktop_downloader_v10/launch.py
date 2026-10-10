from __future__ import annotations

import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def main() -> None:
    try:
        from app import main as run_app

        run_app()
    except Exception as error:
        log_path = Path(__file__).with_name("startup-error.log")
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
            details = f"{error}\n\nDetails were saved to:\n{log_path}"
        except OSError:
            details = str(error)

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Smart Downloader 10.0 could not start",
            f"The app encountered a startup error.\n\n{details}",
            parent=root,
        )
        root.destroy()


if __name__ == "__main__":
    main()
