# Youtube-video-downloader

This repository contains the original Jupyter notebooks and a separate desktop
downloader application. The app is documented in
[`desktop_downloader/README.md`](./desktop_downloader/README.md); it does not
replace or modify the notebooks.

The versioned desktop apps provide queued direct-file and public-media
downloads, retry/resume support, local history, and media/file utilities.
Version 13 adds an optional VLC-powered in-app player and has its own
automated/manual test coverage guide, which tracks behavior checks for Sections
1–20 and distinguishes automated regression tests from environment-dependent
manual verification.

## Repository layout

```text
Youtube-video-downloader/
|-- README.md
|-- SmartDownloader.ipynb
|-- smart_downloader_onecell.ipynb
|-- smart_downloader_v9.ipynb
|-- Untitled*.ipynb
|-- .ipynb_checkpoints/             # Local Jupyter checkpoints; not app source
|-- tests/                          # Root package smoke tests
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
see [`desktop_downloader/SETUP.md`](./desktop_downloader/SETUP.md). Separate
versioned apps are maintained in `desktop_downloader_v10/`,
`desktop_downloader_v11/`, `desktop_downloader_v12/`, and
`desktop_downloader_v13/`.

## Portable downloads

The GitHub Actions workflow builds portable Windows ZIPs for the original
desktop app and Smart Downloader 11.0, 12.0, and 13.0. To publish the ZIPs, create and
push a new version tag from the repository root:

```powershell
git tag v13.0.0
git push origin v13.0.0
```

After the **Build desktop downloads** workflow succeeds, the four Windows ZIPs
and Linux ZIPs for versions 12.0 and 13.0 appear as assets on that GitHub
Release (six ZIPs total). On another Windows PC, download and
extract the ZIP, then double-click the `.exe`; Python and the app's Python
packages do not need to be installed. Some optional integrations still use
external programs; see the version-specific README for those limitations.

## App documentation

- [Features, download options, and limitations](./desktop_downloader/README.md)
- [New-computer setup, GitHub download/update, and troubleshooting](./desktop_downloader/SETUP.md)

## Smart Downloader 11.0

Version 11.0 is a separate copy of version 10.0 in
[`desktop_downloader_v11`](./desktop_downloader_v11/README.md). It preserves the
separate v10 folder and has its own local data folder. The original
[`desktop_downloader`](./desktop_downloader/README.md) and v11 both include
the requested bug fixes, soft-hidden history, a shared global bandwidth cap,
duplicate-active-URL protection, OS completion notifications, a dark-mode
toggle, and optional MD5/SHA256 verification. Existing v10 source remains
unchanged.

- [Version 11.0 features and fixes](./desktop_downloader_v11/README.md)
- [Version 11.0 setup and aria2 installation](./desktop_downloader_v11/SETUP.md)

## Smart Downloader 12.0

Version 12.0 is a separate copy of v11 in
[`desktop_downloader_v12`](./desktop_downloader_v12/README.md). Its GUI is split
into focused modules for UI construction, themes, preferences, queue management,
downloads, media tools, and events. Existing versions remain unchanged.

- [Version 12.0 features and refactored app structure](./desktop_downloader_v12/README.md)
- [Version 12.0 setup and aria2 installation](./desktop_downloader_v12/SETUP.md)

## Smart Downloader 13.0

Version 13.0 is an independent copy of v12 in
[`desktop_downloader_v13`](./desktop_downloader_v13/README.md). It keeps
separate local history and adds a refreshed three-panel interface with a media
inspector, direct audio/video player launch controls, Urdu translations for
primary controls, and keyboard navigation/accessibility improvements. Earlier
versions remain unchanged.

- [Version 13.0 features and refreshed interface](./desktop_downloader_v13/README.md)
- [Version 13.0 setup and aria2 installation](./desktop_downloader_v13/SETUP.md)
- [Version 13.0 technical requirements and acceptance criteria](./desktop_downloader_v13/SOFTWARE_REQUIREMENTS.md)
- [Version 13.0 detailed startup, URL, and download test cases](./desktop_downloader_v13/TEST_CASES.md)
- [Version 13.0 plain-language user and test guide](./desktop_downloader_v13/USER_GUIDE.md)
- [Version 13.0 test coverage and manual verification checklist](./desktop_downloader_v13/TESTING.md)

## Smart Downloader 10.0

Version 10.0 is developed in the separate
[`desktop_downloader_v10`](./desktop_downloader_v10/README.md) folder. It keeps
the earlier `desktop_downloader` app and its setup files unchanged, and adds
magnet URI and `.torrent` downloads through the external aria2 engine.

- [Version 10.0 features and torrent support](./desktop_downloader_v10/README.md)
- [Version 10.0 setup and aria2 installation](./desktop_downloader_v10/SETUP.md)