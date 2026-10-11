# Smart Downloader (desktop)

Created by **ArbazFareed (AFJ devops)**.

A cross-platform Python desktop app for public direct file links and public media
URLs supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp). It provides a
concurrent queue, progress, cancellation, pause/resume, selectable media
connection speeds, per-download and shared global bandwidth caps, scheduled
starts, persistent history, optional checksum verification, and resumable direct
downloads when the server supports HTTP range requests. Temporary direct-download
connection failures are retried with exponential backoff while retaining partial
data. Active duplicate URLs are rejected, and the app can warn before repeating
a completed download. Completion notifications and a readable, remembered dark
theme are available. New users can choose recommended settings with one click.

It cannot download every URL. Sign-in, DRM, paywall, private, and other protected
streams are not supported. Only download content you have permission to save and
follow the source site's terms.

The supported-site option sends public media URLs to yt-dlp. This includes
extractors for services such as YouTube, TikTok, Facebook, and Instagram. In
the installed yt-dlp version, Telegram support is for Telegram public post
video embeds that match its `telegram:embed` extractor; it is not a Telegram
client for private chats or channels. Extractor support is URL-specific and can
change when sites change. No downloader can promise every link or every site.

## Launch on Windows

1. Install Python 3.10 or newer, including Tcl/Tk and the Python launcher.
2. Double-click **Create Desktop Shortcut.bat** in this folder once.
3. Double-click **Smart Downloader** on your desktop to open the app. The first
   launch creates a private `.venv` and installs the required Python packages;
   this can take several minutes. Once set up, the desktop shortcut opens the
   graphical app directly without a terminal. You do not need to open VS Code or
   type a Python command. Startup errors are shown in a message box and recorded
   in `startup-error.log`.

For a no-Python-install option, download the **SmartDownloader-Windows.zip**
asset from a GitHub Release, extract it, and double-click `SmartDownloader.exe`.
The release is built by pushing a version tag; see the repository's portable
Windows build instructions. DOCX-to-PDF conversion still requires LibreOffice,
and local media conversion requires FFmpeg.

## Command-line use

From this folder, run a download without opening the desktop window:

```powershell
.\.venv\Scripts\python.exe .\cli.py "https://example.com/file.zip" -o .\downloads --cap 1048576
```

The CLI supports `--source`, `--mode`, `--quality`, `--speed`, `--cap`,
`--checksum`, `--playlist-scope`, `--proxy`, and `--cookies`. A checksum may be
specified as `sha256:<hex>` or `md5:<hex>`. It returns exit code 0 on success,
1 on failure or checksum mismatch, and 130 when cancelled with Ctrl+C.

## Optional tools

- **Proxy:** Enter an `http://`, `https://`, `socks5://`, or `socks5h://` proxy
  URL in the Proxy box. Comma-separated proxies rotate across direct-download
  retries and supported-site attempts. SOCKS proxies work through the included
  Requests SOCKS extra.
- **Browser cookies:** Choose Chrome, Firefox, Edge, or Brave to reuse that
  browser's cookies for a download. Cookies are accessed locally, only when
  explicitly selected. The browser may need to be closed if its cookie database
  is locked. Only download content you are authorized to access.
- **REST API:** Start with `python api.py` or
  `uvicorn api:app --host 127.0.0.1 --port 8765` from this folder. The API
  listens on localhost and requires a Bearer token; the generated token is
  printed in the server log. Set `SMART_DOWNLOADER_API_TOKEN` before starting
  to use your own token. Do not expose the API to a network without a strong
  token and network encryption. Endpoints include `POST /jobs`, `GET /jobs`,
  `GET /jobs/{id}`, and `POST /jobs/{id}/cancel|pause|resume`.
- **Browser extension:** Load unpacked from `browser_extension` in Chrome, or
  load `manifest.firefox.json` as a temporary Firefox add-on. Start `launch_api.py`
  and configure the printed API token in the extension popup. Right-click a
  page, link, or media element to queue it. Browser page scripts cannot expose
  every protected or segmented stream; use the supported-site page URL where
  yt-dlp has an extractor.
- **Phone control:** To allow phone access, start the API with
  `SMART_DOWNLOADER_API_HOST=0.0.0.0` and a strong
  `SMART_DOWNLOADER_API_TOKEN`, then use **Show phone QR** in the extension
  popup. The phone and PC must be on the same trusted Wi-Fi network. The QR
  contains a job-only token that expires after 24 hours; it can monitor,
  pause, resume, or cancel that API job, but it does not transfer the download
  to the phone. Keep the API off public networks.
- **Cloud destinations:** Open **More settings** > **Schedule & files**, select
  Amazon S3, Google Drive, or Dropbox, then use **Account setup**. S3 access
  keys and
  provider tokens are stored in the operating system credential store; Google
  Drive uses a local OAuth sign-in, and Dropbox uses its app authorization
  flow. Downloads are staged locally, uploaded after verification/extraction,
  and removed from staging only after upload succeeds. If an upload fails, the
  local copy is retained and its path is shown. Cloud SDKs are installed by the
  launcher from `requirements.txt`. The remote-folder field is an S3 prefix,
  Dropbox path, or Google Drive folder ID.
- **Archive extraction:** Turn on **Auto-extract archives** to extract ZIP, TAR,
  and TGZ files after successful downloads. Extraction rejects unsafe paths and
  links and will not overwrite an existing folder. RAR requires a compatible
  UnRAR tool. 7z archives are downloaded normally but must be extracted manually.

For MP3 conversion and merging separate video/audio streams, install FFmpeg:

```powershell
winget install --id Gyan.FFmpeg.Shared --exact
```

## Launch on macOS or Linux

- Install Python 3.10 or newer and its Tkinter package. On Ubuntu/Debian, install
  `python3-tk` and `python3-venv` using the operating-system package manager.
- Open this folder in the file manager and run `Run Smart Downloader.command` on
  macOS or `run_smart_downloader.sh` on Linux. If macOS blocks the downloaded
  command file, use the Finder context menu to open it. On Linux, mark the shell
  script as executable in its file properties if prompted.
- The launcher creates a private `.venv` and installs Python packages on its
  first run. FFmpeg is optional for direct files and required for MP3 conversion
  and merging separate video/audio streams.

This is desktop software; it is not an Android or iOS app. A mobile version
would need a separate application and platform-specific packaging.

## Options and behavior

- **Link type:** Auto detects common direct file types. Direct file forces a
  normal HTTP download. Supported site passes the URL to yt-dlp. For media
  links from social/video sites, use Auto or Supported site rather than Direct
  file.
- **Media:** Video, Best audio, or MP3 audio. Best audio downloads the source's
  best audio-only stream without converting its container. MP3 converts audio
  to MP3 and requires FFmpeg. For video, Smart Downloader keeps the best
  source-provided audio track for each language yt-dlp reports. Multiple audio
  languages are packaged in an MKV file with language labels and English set as
  the default when available; a single audio track stays in MP4.
  This cannot create dubbed tracks that the source does not provide, and many
  sites expose only one audio language. Direct-file links are saved as-is.
- **Live streams:** Supported live URLs show **Recording live stream** with
  elapsed recording time instead of an ETA. Pause, resume, and cancel use the
  same queue controls as other downloads. The source must remain available and
  supported by yt-dlp until recording ends.
- **Maximum resolution:** Best available, 8K (4320p), 5K (2880p), 4K (2160p),
  1440p, 1080p, 720p, 480p, 360p, 240p, or 144p. These are height limits. A
  source may not offer the selected resolution; the app chooses the best
  available format under that limit. Best available uses the source's best
  format. Available formats depend on the site and the specific video.
- **Download scope:** Auto downloads one video from a single-video link and the
  list when the URL identifies a playlist. Single video asks yt-dlp to ignore a
  playlist when possible. Entire playlist downloads a list when the URL points
  to one; a regular video URL still only contains one video. Playlist downloads
  are organized in a playlist-named subfolder.
- **Queue:** Up to three downloads run at once. Select a row to cancel it.
- **Sidebar navigation:** Filter the queue to **All tasks**, **Downloading**,
  **Completed**, or **Media library**. The main screen keeps the link, save
  folder, common media choices, progress, and queue visible; less common
  controls remain under **Settings** and **More settings**.
- **Convert local media to MP3:** Choose **Convert to MP3** in the sidebar,
  select an audio or video file, and choose an `.mp3` destination. The source
  file is preserved. FFmpeg must be installed; conversion runs in the
  background.
- **Document conversion:** Use **Tools & utilities** to convert DOCX to PDF
  or PDF to DOCX. PDF-to-DOCX runs locally with the installed `pdf2docx`
  package. DOCX-to-PDF needs LibreOffice installed on Windows or Linux; the app
  looks for `soffice` on PATH and common installation paths. Conversion runs in
  the background and does not replace an existing file unless you confirm it
  in the save dialog. Scanned PDFs need OCR separately, and complex page
  layouts may not convert perfectly.
- **History:** Use the **History** menu to hide, restore, and clear finished
  downloads without deleting their saved records.
- **Persistent history:** Entries are saved in the app's local
  `SmartDownloader/history.sqlite3` data folder and restored at startup. Jobs
  that were active or scheduled when the app closed are marked Interrupted;
  they are not silently restarted.
- **Hidden history:** Clear finished and Hide selected hide terminal rows
  without deleting their database records. Select Show hidden to review them
  and Restore selected to return a row to the main history view.
- **Scheduled start:** Enter a local time in `YYYY-MM-DD HH:MM` format to hold a
  job until that time. Leave it blank to start immediately. Scheduled jobs
  start only while the app is running; closing the app stops their timers and
  they appear as Interrupted next time.
- **Bandwidth caps:** Set an individual job cap and an optional global cap
  (Unlimited, 256 KB/s, 512 KB/s, 1 MB/s, 2 MB/s, or 5 MB/s). The global cap is
  shared across app downloads; the per-download cap can further restrict one job.
- **Duplicate detection:** A URL already queued, scheduled, or downloading
  cannot be added again. The app can also ask before repeating a completed
  download; turn off **Warn if already downloaded** in **More settings** >
  **Schedule & files** to skip that confirmation.
- **Notifications and appearance:** The app sends an OS notification when a job
  completes. Use the **Dark mode** switch in the header for a high-contrast
  theme; your choice is saved.
- **Recommended settings:** New users can click **Use recommended** for the
  everyday video settings, then paste a link, choose a folder, and add it.
- **Clipboard and batch links:** Turn on **Auto-fill copied links** to place a
  copied web link into the link box. Choose **Batch...** to paste several links
  (one per line), load them from a `.txt` file, or paste them from the clipboard.
  A single checksum is not applied to a batch.
- **Checksum verification:** In **More settings** > **Speed & checks**, enter
  the expected MD5 or SHA256 digest before
  adding a single-file download, or paste it with a `sha256:` or `md5:` prefix.
  A mismatch marks the job Failed and shows both expected and calculated values.
  Playlist/folder results cannot be verified as a single file.
- **Image gallery and sequences:** Choose **Image gallery** in the Media menu
  and add a public webpage to preview common image links before downloading them.
  Or choose **Sequence...** for a numbered URL pattern such as
  `https://site.example/img_{:03d}.jpg`. Gallery scanning only finds common
  HTML image attributes; it does not bypass sign-in, scripts, or site protections.
- **Image tools:** Right-click a completed image to convert it to PNG, JPEG,
  WebP, or AVIF, or resize it to maximum width and height. JPEG conversion
  composites transparent pixels on white. AVIF depends on the Pillow build.
- **EXIF privacy:** Right-click a completed image and choose **Strip EXIF** to
  save a metadata-free copy beside it. The original is kept unchanged; animated
  images are not processed.
- **Thumbnail preview:** Select a completed image row to show a small preview
  alongside the download list. Some image formats may need Pillow codec support.
- **Proxy and cookies:** In **More settings** > **Connection**, set a
  per-download proxy or opt in to cookies from
  Chrome, Firefox, Edge, or Brave. These options are not available for torrents.
- **Archive extraction:** Enable **Auto-extract archives** in **More settings**
  > **Schedule & files** to unpack supported
  archives after download. Extraction uses a separate folder, refuses to
  overwrite existing folders, and blocks path traversal and links.
- **Speed graph:** The chart below the progress summary shows the most recent
  speed samples for the active download; the scale is relative to that job.
- **Plugins:** The `plugins` folder loads non-underscore Python modules that
  expose `register()` with a name and event-handler dictionary. Hooks include
  `on_start(job_id, url)`, `on_progress(job_id, percent)`,
  `on_complete(job_id, filepath)`, `on_error(job_id, error)`, and
  `on_cancel(job_id)`. An `on_complete` handler may return a replacement file
  path. The bundled example lowercases completed filenames; rename its file to
  `_example_plugin.py` to disable it. Plugins run Python code with the same
  permissions as the app, so install only plugins you trust.
- **Clear finished:** In the **History** menu, hide completed, failed, cancelled,
  and interrupted rows
  without deleting persistent history or downloaded files. Use Show hidden and
  Restore selected to review and unhide old rows.
- **Download speed:** Balanced, Fast, and Maximum use 4, 8, and 16 concurrent
  media fragments respectively for supported yt-dlp downloads. Large direct
  files also use up to that many parallel HTTP range requests when the server
  advertises range support and provides a stable file validator. Incomplete
  ranges are kept separately and can resume on a later attempt. Servers without
  range support, small files, or downloads with a bandwidth cap use the
  sequential direct-file path. More connections can help on some sources, but
  may also trigger throttling; actual speed depends on the source and connection.
- **Delta Sync:** Existing direct files are updated by changed chunks only when
  the server advertises `X-Chunk-Hash-Manifest` on a byte-range response. The
  header points to a JSON manifest with `size`, `chunk_size`, `algorithm`
  (`sha256` or `sha512`), and an ordered `chunks` array of hex digests. The
  server must also support byte-range requests. Every fetched chunk is verified
  before the existing file is atomically replaced. Without this server support,
  downloads use the normal path; ETag or Last-Modified alone is not Delta Sync.
- **Pause/resume:** Select an active or queued row and click **Pause / resume**.
  Pausing retains downloaded partial data. Direct downloads resume
  from the partial file on reconnection when the server supports HTTP ranges;
  media downloads use yt-dlp's continuation support.
- **Recovery:** Temporary network and DNS failures are retried until the
  download is cancelled or connectivity returns; the retry delay grows to a
  maximum of 60 seconds. Parallel direct-file ranges retry independently and
  retain completed range data. Range support is required for resuming partial
  direct files. yt-dlp uses its own fragment and extractor retry handling.
  Interrupted jobs retain their download settings in history and can be
  restarted with **Resume / retry selected** after the app is reopened.
- **Destination:** Choose a save folder and use **Open downloads folder** to
  view it in the system file manager. The download list shows each job's save
  location and transfer details such as file name, size, speed, and ETA when the
  source provides them. The progress bar and status summary show percent,
  current transfer details, and the save folder. Select a row and use **Open
  selected location** to open its saved file or folder. The **Help** button
  explains options inside the app. The footer credits Arbaz Fareed (AFJ DEVOPS).

## Tests

From this folder, run all app, image, proxy, API, cookie, and archive tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

See [SETUP.md](./SETUP.md) for system prerequisites, first-time setup, and
troubleshooting. The download engines do not require a separate accelerator
package; direct-file parallel ranges and yt-dlp's media fragment concurrency
are built into the app.

The platform-routing tests verify that representative public video-site links
are sent through yt-dlp and that the installed Telegram embed extractor
recognizes a public post URL. They do not guarantee that every individual post
is available for download; source availability and permissions still apply.
