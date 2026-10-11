# Smart Downloader setup

Use this guide to download the project from GitHub, install Smart Downloader
12.0 on a new computer, or update your local copy. Version 12.0 is a separate copy of v11 in
the `desktop_downloader_v12` folder. Its GUI has been split into focused
modules; v11 and all earlier versions remain unchanged. Each version keeps its
own app files and local history. The desktop app does not require Jupyter or VS
Code to run.

## Download the project from GitHub

### Recommended: clone with Git

Install Git for Windows, then open PowerShell in the location where you want
the project folder. Run:

```powershell
git clone https://github.com/arbazfareed/Youtube-video-downloader.git
Set-Location .\Youtube-video-downloader\desktop_downloader_v12
```

The version 12.0 app files, launchers, documentation, and requirements file are
in this `desktop_downloader_v12` folder.

### Alternative: download a ZIP

1. Open the [GitHub repository](https://github.com/arbazfareed/Youtube-video-downloader).
2. Select **Code**, then **Download ZIP**.
3. Extract the ZIP file.
4. Open the extracted `Youtube-video-downloader\desktop_downloader_v12` folder.

The ZIP method does not install Git. To receive future code updates, download
and extract a newer ZIP or use the Git method above.

## Requirements

- Python 3.10 or newer.
- Tkinter. It is included with most Windows Python installers; on Linux install
  the system `python3-tk` package if it is missing.
- Git only if you want to clone or update the project using Git.
- Internet access for initial package installation and downloading.
- Native desktop notifications use Plyer, which is installed from
  `requirements.txt`; notification support depends on the operating system.
- FFmpeg is optional. Install it only for MP3 conversion or merging separate
  audio/video streams.
- PDF-to-DOCX conversion is included in the Python requirements. DOCX-to-PDF
  also needs LibreOffice: install its Windows desktop installer or, on
  Debian/Ubuntu Linux, run `sudo apt install libreoffice-writer`. The app finds
  `soffice` on PATH or in common install locations.
- aria2 is required for magnet URI and `.torrent` downloads. On Windows, run
  `winget install --id aria2.aria2 --exact` in PowerShell. On macOS use
  `brew install aria2`; on Debian/Ubuntu use `sudo apt install aria2`.
  Restart the app after installation. aria2 is a separate torrent engine
  controlled by the GUI; MediaGet itself and its proprietary formats are not
  integrated.
- No separate speed-accelerator package is required. Parallel HTTP range
  downloads and yt-dlp media fragment connections are provided by this app.
- The launcher checks installed packages against `requirements.txt` at startup
  and installs updated dependencies before importing the GUI. This repairs
  older app environments after new packages are added.
- Proxy support includes SOCKS dependencies from `requests[socks]`. Browser
  cookie access is provided by yt-dlp's built-in browser cookie reader.

## Windows: first-time setup

1. Download or clone the repository using the instructions above.
2. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/).
   Include the Python launcher, pip, and Tcl/Tk.
3. Open the `desktop_downloader_v12` folder in File Explorer.
4. Double-click **Create Desktop Shortcut.bat**. It creates `.venv`, installs
   `requirements.txt`, and creates a **Smart Downloader 12.0** desktop shortcut. The
   first installation needs internet and may take several minutes.
5. Open **Smart Downloader 12.0** from the desktop. You do not need to open VS Code
   or enter a Python command to use the app.

If you prefer to install and launch manually, open PowerShell in the
`desktop_downloader_v12` folder and run:

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

## API, proxies, cookies, and extraction

The optional REST API, archive tools, proxy support, and SOCKS dependencies are
installed from `requirements.txt` on first launch. The API runs only on
localhost by default and prints its Bearer token in the server log. Do not bind
it to a LAN address unless you set `SMART_DOWNLOADER_API_TOKEN` and protect
connections with a trusted network or TLS proxy. Browser cookies are loaded only
for a download where a browser was explicitly selected. RAR archives need an
UnRAR-compatible executable. Automatic 7z extraction is not supported.

## Browser extension and phone control

Load the Chrome extension unpacked from `browser_extension`, or use
`manifest.firefox.json` from Firefox's `about:debugging` page. Start the API
with `launch_api.py`, then copy its printed token into the extension popup.
The extension sends page and media links to the API on this computer.

## Cloud destinations

Choose Amazon S3, Google Drive, or Dropbox in the desktop app's Cloud
destination menu and select **Cloud account setup**. S3 access keys and provider
tokens use the operating system credential store. Google Drive requires an
OAuth client JSON configuration and completes sign-in in a browser. Dropbox
requires a Dropbox app key/secret and browser authorization. The app stages
downloads locally, uploads them after checksum verification and optional
extraction, and removes the staging folder only after a successful upload.
Failed uploads retain the local copy and show its location. The API accepts
`cloud_provider` values `s3`, `google drive`, or `dropbox`; configure the
provider on the same computer first.

Phone QR control is opt-in. Set a strong `SMART_DOWNLOADER_API_TOKEN` and
`SMART_DOWNLOADER_API_HOST=0.0.0.0` before starting the API to allow trusted
devices on the same Wi-Fi network to connect. Use the extension's **Show phone
QR** button after queuing an API job. The QR token only grants access to that
one job and expires after 24 hours. Do not expose the API to the internet.

## Get the latest app version

If you cloned the repo with Git, open PowerShell in the repository folder and
run:

```powershell
git pull --ff-only origin main
Set-Location .\desktop_downloader_v12
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
```

Close the app before updating it. If you have local source edits, commit or
back them up before pulling; Git may refuse to update files that conflict with
uncommitted changes. If you used a ZIP, download and extract the latest ZIP
instead.

## Publish your changes to GitHub

These commands publish the root guide and version 12.0 app without staging unrelated
notebooks or checkpoint files. Run them in PowerShell from the repository root:

```powershell
git status --short
git add README.md desktop_downloader_v12/
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
- Each download can have its own bandwidth cap, and **Global max speed** limits
  combined app traffic. Direct downloads apply the shared limiter before
  writing data; yt-dlp and aria2 report progress in updates, so instantaneous
  network rates can vary around the global cap.
- Scheduled downloads start only while the app remains open.

## History and verification

- **Clear finished** hides completed, failed, and cancelled rows instead of
  deleting their history. Enable **Show hidden** and choose **Restore
  selected** to bring a hidden row back.
- The app remembers your dark theme and duplicate-warning choice. It warns
  before repeating a completed download unless **Warn if already downloaded**
  in **More settings** > **Schedule & files** is turned off. Dark mode is in
  the main-window header.
- The sidebar filters the queue by **All tasks**, **Downloading**, **Completed**,
  or **Media library**. Use **More settings** for less common options and
  **History** for hide, restore, and clear-finished actions.
- Choose **Convert to MP3** in the sidebar to convert a local audio or video
  file. FFmpeg is required, and the original source is not overwritten.
- New users can choose **Use recommended**. Then paste a link, choose a save
  folder, and click **Add download**.
- Optional checksum verification accepts an MD5 or SHA-256 hash; you can include
  its prefix, such as `sha256:<hash>`.
- Turn on **Auto-fill copied links** to fill the link box when a web link is
  copied. Choose **Batch...** to paste many links, load a `.txt` file, or use
  clipboard contents; enter one link per line. A single checksum is not applied
  to batch items.
- A download can optionally be checked against an expected MD5 or SHA-256
  digest. Digest verification is available for single-file downloads, not
  playlists or multi-file results.

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
- **Torrent link fails:** confirm aria2 is installed and `aria2c --version`
  works in PowerShell or Terminal; restart the app after installing aria2.
  Use a valid `magnet:` link or a direct HTTP(S) `.torrent` URL. Torrent peers
  may see your network address and receive pieces while the download is active.
