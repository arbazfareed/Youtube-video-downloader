# Youtube-video-downloader

This repository contains the original Jupyter notebooks and a separate desktop
downloader application. The app is documented in
[`desktop_downloader/README.md`](./desktop_downloader/README.md); it does not
replace or modify the notebooks.

## Repository layout

```text
Youtube-video-downloader/
|-- README.md
|-- SmartDownloader.ipynb
|-- smart_downloader_onecell.ipynb
|-- smart_downloader_v9.ipynb
|-- Untitled*.ipynb
|-- .ipynb_checkpoints/             # Local Jupyter checkpoints; not app source
`-- desktop_downloader/
    |-- app.py                      # Desktop GUI
    |-- download_engine.py          # Direct and yt-dlp download logic
    |-- history_store.py            # Persistent download history
    |-- launch.py                   # Shows a friendly startup-error dialog
    |-- requirements.txt            # Python packages used by the app
    |-- Create Desktop Shortcut.bat # Windows first-time setup and shortcut
    |-- Run Smart Downloader.bat    # Windows app launcher
    |-- run_smart_downloader.sh     # Linux launcher
    |-- Run Smart Downloader.command # macOS launcher
    |-- README.md                   # Features and app options
    |-- SETUP.md                    # Installation, update, and troubleshooting
    `-- tests/
        `-- test_download_engine.py
```

Generated files such as `.venv/`, `__pycache__/`, and download history are local
data, not source files to publish.

## Start the desktop app on Windows

1. Install Python 3.10 or newer from
   [python.org](https://www.python.org/downloads/windows/). Include the Python
   launcher, pip, and Tcl/Tk during installation.
2. Open the `desktop_downloader` folder in File Explorer.
3. Double-click **Create Desktop Shortcut.bat** once. It creates the app's
   private Python environment, installs the required packages, and creates a
   desktop shortcut.
4. Open **Smart Downloader** from the desktop shortcut. VS Code is not needed.

For a new computer, macOS/Linux steps, manual installation, and troubleshooting,
see [`desktop_downloader/SETUP.md`](./desktop_downloader/SETUP.md).

## App documentation

- [Features, download options, and limitations](./desktop_downloader/README.md)
- [New-computer setup, GitHub download/update, and troubleshooting](./desktop_downloader/SETUP.md)

## Smart Downloader 10.0

Version 10.0 is developed in the separate
[`desktop_downloader_v10`](./desktop_downloader_v10/README.md) folder. It keeps
the earlier `desktop_downloader` app and its setup files unchanged, and adds
magnet URI and `.torrent` downloads through the external aria2 engine.

- [Version 10.0 features and torrent support](./desktop_downloader_v10/README.md)
- [Version 10.0 setup and aria2 installation](./desktop_downloader_v10/SETUP.md)