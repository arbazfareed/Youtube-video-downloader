# Smart Downloader 10.0 (desktop)

Created by **ArbazFareed (AFJ devops)**.

A cross-platform Python desktop app for public direct file links and public media
URLs supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp). It provides a
concurrent queue, progress, cancellation, pause/resume, selectable media
connection speeds, a per-download bandwidth cap, scheduled starts, persistent
history, and resumable direct downloads when the server supports HTTP range
requests. Temporary direct-download connection failures are retried with
exponential backoff while retaining partial data.

Version 10.0 is a separate folder from the earlier `desktop_downloader`
version. It adds in-app BitTorrent downloads for magnet URIs and direct
`.torrent` links, using aria2 as the transfer engine. This is BitTorrent
protocol support, not integration with MediaGet's private application data or
proprietary formats. Install aria2 separately to use torrent links. Peers may
receive pieces from your computer while a torrent download is active.

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
2. To enable torrents, install aria2 from PowerShell:

   ```powershell
   winget install --id aria2.aria2 --exact
   ```

3. Double-click **Create Desktop Shortcut.bat** in this folder once.
4. Double-click **Smart Downloader 10.0** on your desktop to open the app. The first
   launch creates a private `.venv` and installs the required Python packages;
   this can take several minutes. Once set up, the desktop shortcut opens the
   graphical app directly without a terminal. You do not need to open VS Code or
   type a Python command. Startup errors are shown in a message box and recorded
   in `startup-error.log`.

For MP3 conversion and merging separate video/audio streams, install FFmpeg:

```powershell
winget install --id Gyan.FFmpeg.Shared --exact
```

## Launch on macOS or Linux

- Install Python 3.10 or newer and its Tkinter package. On Ubuntu/Debian, install
  `python3-tk` and `python3-venv` using the operating-system package manager.
- Install aria2 for torrent downloads: on macOS use `brew install aria2`; on
  Debian/Ubuntu use `sudo apt install aria2`.
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

- **Link type:** Auto detects common direct file and torrent URLs. Direct file
  forces a normal HTTP download. Supported site passes the URL to yt-dlp.
  Torrent/magnet accepts a `magnet:` URI or a direct HTTP(S) `.torrent` URL and
  requires aria2. For media
  links from social/video sites, use Auto or Supported site rather than Direct
  file.
- **Media:** Video, Best audio, or MP3 audio. Best audio downloads the source's
  best audio-only stream without converting its container. MP3 converts audio
  to MP3 and requires FFmpeg. Direct-file links are saved as-is.
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
- **Persistent history:** Entries are saved in the app's local
  `SmartDownloader10/history.sqlite3` data folder and restored at startup. Jobs
  that were active or scheduled when the app closed are marked Interrupted;
  they are not silently restarted.
- **Scheduled start:** Enter a local time in `YYYY-MM-DD HH:MM` format to hold a
  job until that time. Leave it blank to start immediately. Scheduled jobs
  start only while the app is running; closing the app stops their timers and
  they appear as Interrupted next time.
- **Bandwidth cap:** Unlimited, 256 KB/s, 512 KB/s, 1 MB/s, 2 MB/s, or 5 MB/s.
  The cap is per download; when multiple downloads run, their combined speed
  can be higher than the selected cap.
- **Clear finished:** Removes completed, failed, and cancelled rows from the
  queue display. It does not remove any downloaded files and leaves queued or
  active jobs untouched. It also removes those entries from persistent history.
- **Download speed:** Balanced, Fast, and Maximum use 4, 8, and 16 concurrent
  media fragments respectively for supported yt-dlp downloads. Large direct
  files also use up to that many parallel HTTP range requests when the server
  advertises range support and provides a stable file validator. Incomplete
  ranges are kept separately and can resume on a later attempt. Servers without
  range support, small files, or downloads with a bandwidth cap use the
  sequential direct-file path. More connections can help on some sources, but
  may also trigger throttling; actual speed depends on the source and connection.
- **Pause/resume:** Select an active or queued row and click **Pause / resume
  selected**. Pausing retains downloaded partial data. Direct downloads resume
  from the partial file on reconnection when the server supports HTTP ranges;
  media downloads use yt-dlp's continuation support. Torrent jobs are paused
  and resumed through aria2.
- **Recovery:** Direct downloads retry temporary network/server failures up to
  ten times on the sequential path, with a delay that grows to a maximum of 30
  seconds. Parallel direct-file ranges retry independently and retain completed
  range data. Range support is required for resuming partial direct files.
  yt-dlp uses its own fragment and extractor retry handling.
- **Destination:** Choose a save folder and use **Open downloads folder** to
  view it in the system file manager. The download list shows each job's save
  location and transfer details such as file name, size, speed, and ETA when the
  source provides them. The progress bar and status summary show percent,
  current transfer details, and the save folder. Select a row and use **Open
  selected location** to open its saved file or folder. The **Help** button
  explains options inside the app. The footer credits ArbazFareed (AFJ devops).

## Tests

From this folder, run the engine tests:

```powershell
py -m unittest discover -s tests
```

See [SETUP.md](./SETUP.md) for system prerequisites, first-time setup, and
troubleshooting. The download engines do not require a separate accelerator
package; direct-file parallel ranges and yt-dlp's media fragment concurrency
are built into the app.

The platform-routing tests verify that representative public video-site links
are sent through yt-dlp and that the installed Telegram embed extractor
recognizes a public post URL. They do not guarantee that every individual post
is available for download; source availability and permissions still apply.
