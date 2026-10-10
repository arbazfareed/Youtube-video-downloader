# Smart Downloader setup

Use this guide to download the project from GitHub, install it on a new
computer, or update your local copy. The desktop app is the `desktop_downloader`
folder inside the repository; it has its own Python dependencies and does not
need Jupyter or VS Code to run.

## Download the project from GitHub

### Recommended: clone with Git

Install Git for Windows, then open PowerShell in the location where you want
the project folder. Run:

```powershell
git clone https://github.com/arbazfareed/Youtube-video-downloader.git
Set-Location .\Youtube-video-downloader\desktop_downloader
```

The app files, launchers, documentation, and requirements file are in this
`desktop_downloader` folder.

### Alternative: download a ZIP

1. Open the [GitHub repository](https://github.com/arbazfareed/Youtube-video-downloader).
2. Select **Code**, then **Download ZIP**.
3. Extract the ZIP file.
4. Open the extracted `Youtube-video-downloader\desktop_downloader` folder.

The ZIP method does not install Git. To receive future code updates, download
and extract a newer ZIP or use the Git method above.

## Requirements

- Python 3.10 or newer.
- Tkinter. It is included with most Windows Python installers; on Linux install
  the system `python3-tk` package if it is missing.
- Git only if you want to clone or update the project using Git.
- Internet access for initial package installation and downloading.
- FFmpeg is optional. Install it only for MP3 conversion or merging separate
  audio/video streams.
- No separate speed-accelerator package is required. Parallel HTTP range
  downloads and yt-dlp media fragment connections are provided by this app.

## Windows: first-time setup

1. Download or clone the repository using the instructions above.
2. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/).
   Include the Python launcher, pip, and Tcl/Tk.
3. Open the `desktop_downloader` folder in File Explorer.
4. Double-click **Create Desktop Shortcut.bat**. It creates `.venv`, installs
   `requirements.txt`, and creates a **Smart Downloader** desktop shortcut. The
   first installation needs internet and may take several minutes.
5. Open **Smart Downloader** from the desktop. You do not need to open VS Code
   or enter a Python command to use the app.

If you prefer to install and launch manually, open PowerShell in the
`desktop_downloader` folder and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe launch.py
```

If you downloaded a ZIP, the initial setup can also be started by double-clicking
**Run Smart Downloader.bat**. This installs the app packages and opens the GUI,
but does not create the desktop shortcut.

## macOS

Install Python 3.10 or newer and ensure its Tcl/Tk support is available. In
Terminal, from this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

The `Run Smart Downloader.command` launcher can also perform the first-time
environment setup.

## Linux

Install Python, venv, and Tkinter using your distribution's package manager.
For Debian/Ubuntu:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-tk
```

Then from this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

## Optional FFmpeg

- Windows: `winget install --id Gyan.FFmpeg.Shared --exact`
- macOS: install FFmpeg with Homebrew (`brew install ffmpeg`).
- Debian/Ubuntu: `sudo apt install ffmpeg`.

Restart Smart Downloader after installing FFmpeg.

## Get the latest app version

If you cloned the repo with Git, open PowerShell in the repository folder and
run:

```powershell
git pull --ff-only origin main
Set-Location .\desktop_downloader
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
```

Close the app before updating it. If you have local source edits, commit or
back them up before pulling; Git may refuse to update files that conflict with
uncommitted changes. If you used a ZIP, download and extract the latest ZIP
instead.

## Publish your changes to GitHub

These commands publish the root guide and desktop app without staging unrelated
notebooks or checkpoint files. Run them in PowerShell from the repository root:

```powershell
git status --short
git add README.md desktop_downloader/
git diff --cached --check
git diff --cached --stat
git commit -m "Update desktop downloader documentation"
git push origin main
```

Review the staged diff before committing. If GitHub asks you to authenticate,
complete the sign-in prompt or configure GitHub CLI/Git credentials. Do not
commit `.venv/`, download output, or local history.

## Updating Python packages only

Activate the existing `.venv` or call its Python directly, then run:

```text
python -m pip install --upgrade -r requirements.txt
```

On Windows, replace `python` with `.\.venv\Scripts\python.exe`; on macOS/Linux,
use `.venv/bin/python`. Updating `yt-dlp` can restore support when media sites
change, but no version guarantees that every URL will work.

## Speed and resume notes

- **Maximum** uses up to 16 concurrent media fragments or direct-file ranges.
  More connections are not always faster; servers can limit connections, and
  your network plan and Wi-Fi also set the limit.
- Parallel direct downloads require a large file and HTTP range support.
  Smaller files, servers without ranges, and jobs with a speed cap use a
  sequential connection instead.
- Direct-file range data is stored next to the destination as hidden-in-purpose
  `.part.segment-*` files and a `.segments.json` resume record until the
  download finishes. Keep these files together if moving an interrupted job.
- A bandwidth cap is applied per download. For example, three jobs capped at
  1 MB/s can together use up to roughly 3 MB/s.
- Scheduled downloads start only while the app remains open.

## Troubleshooting

- **App does not open:** check `startup-error.log` in this folder. Confirm
  Python and Tkinter are installed, then rerun the launcher.
- **Package installation fails:** check internet access and run the pip install
  command above from this folder. Avoid deleting `.venv` while the app is open.
- **MP3 or merged output fails:** install FFmpeg, restart the app, and retry.
- **Site link fails:** choose Auto or Supported site, use a public URL, and
  update yt-dlp. Site changes, sign-in, DRM, privacy restrictions, and region
  restrictions can prevent downloads.
- **Direct download does not speed up:** the server may not allow byte ranges,
  or the file may be small. The app falls back to a single connection.
