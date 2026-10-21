# Youtube-video-downloader

This repository contains the original Jupyter notebooks and a separate desktop
downloader application. The app is documented in
[`desktop_downloader/README.md`](./desktop_downloader/README.md); it does not
replace or modify the notebooks.

The versioned desktop apps provide queued direct-file and public-media
downloads, retry/resume support, local history, and media/file utilities.
Version 14 adds an advanced media preview player with permanent playback controls,
multi-track audio stream selection, proxy rotation, yt-dlp one-click updating,
and full portable packaging.

## Repository layout

```text
Youtube-video-downloader/
|-- README.md
|-- SmartDownloader.ipynb
|-- smart_downloader_onecell.ipynb
|-- smart_downloader_v9.ipynb
|-- Untitled*.ipynb
|-- tests/                          # Root package smoke tests
|-- desktop_downloader/             # Original desktop downloader
|-- desktop_downloader_v10/         # Version 10.0 with torrent support
|-- desktop_downloader_v11/         # Version 11.0 with dark theme & bandwidth caps
|-- desktop_downloader_v12/         # Version 12.0 modular architecture
|-- desktop_downloader_v13/         # Version 13.0 with VLC media player & inspector
`-- desktop_downloader_v14/         # Version 14.0 with preview player, multi-track audio, & offline bundle
```

Generated files such as `.venv/`, `__pycache__/`, and download history are local
data, not source files to publish.

## Start the desktop app on Windows

1. Install Python 3.10 or newer from
   [python.org](https://www.python.org/downloads/windows/). Include the Python
   launcher, pip, and Tcl/Tk during installation.
2. Open the `desktop_downloader_v14` folder (or `desktop_downloader`) in File Explorer.
3. Double-click **Create Desktop Shortcut.bat** once. It creates the app's
   private Python environment, installs the required packages, and creates a
   desktop shortcut.
4. Open **Smart Downloader** from the desktop shortcut. VS Code is not needed.

For a new computer, macOS/Linux steps, manual installation, and troubleshooting,
see [`desktop_downloader_v14/SETUP.md`](./desktop_downloader_v14/SETUP.md). Separate
versioned apps are maintained in `desktop_downloader_v10/`,
`desktop_downloader_v11/`, `desktop_downloader_v12/`,
`desktop_downloader_v13/`, and `desktop_downloader_v14/`.

## Portable downloads

The GitHub Actions workflow builds portable Windows ZIPs for the desktop apps. To publish the ZIPs, create and
push a new version tag from the repository root:

```powershell
git tag v14.0.0
git push origin v14.0.0
```

On another Windows PC, download and extract the portable ZIP, then double-click the `.exe`;
Python and the app's Python packages do not need to be installed.

## Smart Downloader 14.0

Version 14.0 is an enhanced release in
[`desktop_downloader_v14`](./desktop_downloader_v14/README.md). It features a
permanent media preview controls bar with inline playback, Direct3D9 software
rendering to eliminate blank preview windows on Windows, multi-stream and
multi-voice audio track selection (e.g. Hindi, English, original), one-click
yt-dlp updating, proxy rotation, scheduled downloads, and 292 comprehensive unit
tests.

- [Version 14.0 features and documentation](./desktop_downloader_v14/README.md)
- [Version 14.0 setup and aria2 installation](./desktop_downloader_v14/SETUP.md)
- [Version 14.0 technical requirements and acceptance criteria](./desktop_downloader_v14/SOFTWARE_REQUIREMENTS.md)
- [Version 14.0 test cases and manual verification](./desktop_downloader_v14/TEST_CASES.md)
- [Version 14.0 plain-language user and test guide](./desktop_downloader_v14/USER_GUIDE.md)
- [Version 14.0 test coverage guide](./desktop_downloader_v14/TESTING.md)

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

## Smart Downloader 12.0

Version 12.0 is a separate copy of v11 in
[`desktop_downloader_v12`](./desktop_downloader_v12/README.md). Its GUI is split
into focused modules for UI construction, themes, preferences, queue management,
downloads, media tools, and events. Existing versions remain unchanged.

- [Version 12.0 features and refactored app structure](./desktop_downloader_v12/README.md)
- [Version 12.0 setup and aria2 installation](./desktop_downloader_v12/SETUP.md)

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

## Smart Downloader 10.0

Version 10.0 is developed in the separate
[`desktop_downloader_v10`](./desktop_downloader_v10/README.md) folder. It keeps
the earlier `desktop_downloader` app and its setup files unchanged, and adds
magnet URI and `.torrent` downloads through the external aria2 engine.

- [Version 10.0 features and torrent support](./desktop_downloader_v10/README.md)
- [Version 10.0 setup and aria2 installation](./desktop_downloader_v10/SETUP.md)
