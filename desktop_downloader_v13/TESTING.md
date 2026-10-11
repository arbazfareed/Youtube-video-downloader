# v13 test and behavior checklist

Detailed case-by-case procedures for startup, URL input, and direct downloads
are in [TEST_CASES.md](./TEST_CASES.md). The technical requirements and
acceptance mapping are in [SOFTWARE_REQUIREMENTS.md](./SOFTWARE_REQUIREMENTS.md),
and plain-language user stories and testing guidance are in
[USER_GUIDE.md](./USER_GUIDE.md).

Run the automated suite from this directory:

```powershell
..\.venv-3\Scripts\python.exe -m unittest discover -s tests -v
```

The checklist tests use temporary directories and databases, mocked HTTP and
subprocess responses, and test doubles for application state. They do not
change network adapters, sleep the computer, or access normal user history.

## Progress from the previous pass

Earlier passes completed Sections 1–14 and passed 181 tests. The Section 15–20
extension added 10 regression tests, bringing the suite to 191. This
localization/accessibility pass added four tests, bringing the total to 195.
The previous embedded-player pass brought the suite to 203 tests. The
independent fullscreen-player regression coverage adds one test; the complete
suite now passes 204 tests.

| Behavior | Before this extension | After this extension |
| --- | --- | --- |
| Queued cancellation | Set a cancellation event; queued executor work could still wait for a worker. | Keep the job's `Future` and cancel it if it has not started; active work remains event-cancelled without a UI-thread join. |
| Direct resume | Checked that a returned range began at the partial-file size. | Also reject a wrong offset, incomplete range, or mismatched range length; an oversized partial is not accepted as complete from a mismatched 416. |
| Parallel assembly | Copied segment files in one non-interruptible operation. | Copies in bounded chunks, checks cancellation between chunks, closes handles, and removes an incomplete assembled `.part` while retaining segment files for retry. |
| aria2 RPC | Could keep polling indefinitely if aria2 stayed alive but stopped answering status requests. | Fails after a bounded RPC outage and terminates the helper process. |
| Image tools and preview | Pillow decompression-bomb exceptions were not normalized into the UI's handled image errors. | Convert bomb errors to user-facing validation errors in image processing and preview. |
| Batch and clipboard | Clipboard read failures could interrupt polling, and the app did not have regression coverage for 100-link batches or clipboard recovery. | Clipboard read errors are reported and polling continues; 100-link batches are covered. Clipboard polling remains autofill-only (see Section 15 limitation below). |
| UI event load | Rapid same-status progress callbacks could enqueue updates faster than the interface needs to render them. | Same-status progress events are throttled to about 20 updates per second per job; status transitions remain immediate. |
| Filename and assembly locks | Long names could lose useful extensions, and a transient Windows file lock could fail assembly immediately. | Long names preserve ordinary extensions; atomic replacement retries transient permission locks and reports a persistent lock clearly. |
| Parallel state recovery | Corrupt range metadata or an externally enlarged segment could interfere with a later retry. | Malformed metadata starts with fresh range state, and segments with a size mismatch are discarded and fetched again. |
| Urdu and keyboard accessibility | Urdu coverage did not include several primary controls, and link/queue/status focus shortcuts were not available. | Primary navigation and download controls have Urdu labels; shortcuts focus the URL field, queue, and progress status; Space toggles pause/resume while the queue has focus. |
| VLC fullscreen behavior | Full-screen action applied the fullscreen attribute to the Smart Downloader root, expanding the entire app instead of only the video. | VLC is reattached to a dedicated fullscreen video surface with its own playback/volume/audio-track controls; main app geometry stays unchanged and Escape/F11 restores embedded playback. |

The suite also covers bandwidth-limit edge cases, schedule validation,
concurrent history writes, SQL-like URL text, chunked checksum reads,
notification failures, and aria2 process cleanup. Mocked checks do not
substitute for device, OS, network, or packaged-app tests.

## Automated coverage

- **Startup and storage:** dependency-install failures show the launcher's
  friendly error; corrupt SQLite history is copied to a timestamped
  `.corrupt.bak` file and a new database is initialized; exclusive-lock errors
  are surfaced; multiple history instances can use the same database.
- **URLs and input:** HTTP/HTTPS acceptance; invalid schemes, absent hosts, and
  malformed IPv6 URLs are rejected before transfer; requests encoding for
  spaces and Unicode; long URL handling; query and authentication forwarding;
  credentials are redacted from terminal/error text; root URLs get a safe
  fallback filename. Existing tests also cover clipboard input, batch input,
  duplicate checks, and filename traversal/device-name sanitization.
- **Direct downloads:** disk-space preflight when the server advertises total
  size; zero-byte and unknown-length streams; HTML, 403, and 404 responses;
  redirect following; 429 retry; truncated-response retry and byte-count
  verification; a server ignoring resume ranges; and a matching 416 completion.
  Requests advertise `Accept-Encoding: identity` so range offsets remain
  consistent with bytes written. The extension rejects misaligned or
  incomplete resumed ranges and does not promote an oversized partial file
  after a mismatched 416 response.
- **Pause, resume, and history:** existing tests cover pause/resume/cancel event
  behavior, resuming a partial direct file, preserving parallel segment state,
  and marking unfinished jobs interrupted when history is reopened.
- **Cancellation and cleanup:** queued futures can be cancelled before worker
  startup; active cancellation uses events without joining on the UI thread;
  scheduled jobs cancel their timers; parallel assembly checks cancellation
  between chunks, closes files, removes its incomplete assembled `.part`, and
  retains completed range segments for a safe retry. An oversized segment
  modified on disk is discarded and downloaded again. Existing tests cover
  clearing terminal rows without removing active downloads.
- **Bandwidth and scheduling:** shared limits across jobs, cancellable waits,
  unlimited/zero-limit safety, future schedule parsing, malformed input, and
  past-time rejection.
- **History and checksums:** concurrent SQLite add/update operations and SQL-like
  text in a URL; correct MD5/SHA-256 verification and wrong-hash rejection.
  Checksum calculation reads in fixed-size chunks rather than loading a whole
  file into memory.
- **Notifications and torrents:** a failed OS notification is surfaced as a
  warning without changing a completed download to failed; mocked aria2
  cancellation terminates the subprocess, an aria2 crash is reported, and a
  persistent RPC outage fails instead of polling indefinitely.
- **Image tools:** image decompression-bomb errors are converted to a clear,
  handled validation error; corrupt image files fail with a Pillow I/O error
  that the UI's asynchronous image-operation handler reports.
- **Themes and history:** existing tests verify dark-mode preference
  persistence, finished-row hiding, and history restoration.
- **Batch and clipboard (Section 15):** 100-link batch input, clipboard watcher
  disabled behavior, non-URL filtering, and recovery after clipboard lock/read
  errors. The clipboard watcher polls the current clipboard about every 800 ms,
  fills the URL field, and does not auto-enqueue. Intermediate clipboard values
  may be missed during rapid changes; the app does not promise clipboard
  history or capture every copy.
- **Filenames and storage (Section 16):** long filenames retain their extension,
  Windows reserved names and unsafe components are sanitized, spaced Unicode
  destination paths work with `pathlib`, and file assembly retries transient
  permission locks before surfacing a persistent error. Malformed parallel
  metadata and changed segment sizes recover by restarting those ranges.
- **Concurrency and UI load (Section 17):** a ten-job worker-pool test verifies
  three transfers can run concurrently; same-status progress updates are
  throttled to approximately 20 Hz per job while status transitions pass
  through immediately.
- **Memory and CPU (Section 18):** checksum reads are bounded and parallel
  assembly copies in fixed-size chunks. These tests verify bounded operations,
  not the checklist's RAM/CPU thresholds or 24-hour stability.
- **Cross-platform paths (Section 19):** Unicode filenames and paths containing
  spaces are covered on the current Windows test host. This is not a macOS or
  Linux launch certification.
- **Localization and keyboard access:** Urdu core navigation, download controls,
  settings, queue headings, and shortcut-help strings have translation tests.
  Keyboard shortcut routing/focus targets and Urdu shortcut help are unit
  tested. The progress summary and bar are keyboard focusable. Actual Tk key
  events, visual Urdu shaping, and screen-reader output are platform-dependent
  and must be checked manually.
- **VLC player controls:** automated tests verify video/audio file acceptance,
  embedding without a second top-level window, stop/close lifecycle, volume
  percentage, audio-track listing/selection and empty-track handling,
  separate fullscreen surface targeting, unchanged main-app geometry, Escape/F11
  return-to-preview behavior, fullscreen controls, and player help. The test environment does not have
  python-vlc installed, so VLC is mocked; these tests do not verify real codecs,
  playback at actual resolutions, aspect ratio, sound output, track switching
  against a media file, or fullscreen rendering on a physical display.
- **Shutdown and cleanup (Section 20):** mocked tests verify aria2 termination
  on cancellation and RPC failure. They do not prove that forcibly killing the
  packaged app leaves no real yt-dlp/aria2 process, socket, or worker behind.

## Manual or environment-dependent checks not claimed as passed

The automated tests do not establish the following checklist items: launching
the packaged Windows/Linux executable offline; a clean machine without Python
or a missing `.venv`; real read-only or UNC/network folders; rendering startup
errors in a desktop session; opening a database locked by an external SQLite
application; GUI startup time with 10,000 visible queue entries; real GUI
responsiveness when adding 100 jobs; rapid clipboard changes without missed
intermediate values; real cookies or Referer-authenticated servers; actual
network-interface changes, Wi-Fi loss, or suspend/resume; pause during a real
media merge; speed-cap accuracy on a real high-throughput link; system clock
changes or daylight-saving transitions; live notification delivery on
Windows/macOS/Linux; real aria2 peer discovery/RPC disconnects; a real
100,000-by-100,000 image; memory use on a multi-gigabyte checksum; image gallery
downloads against external sites; or playback against an installed VLC runtime.
Actual player resolution, aspect-ratio behavior while resizing, audio output,
multi-track switching, and fullscreen movement across displays also require
manual testing with suitable media and installed VLC.
Rapid cancel/re-add timing, zombie socket/thread counts, measured RAM/CPU,
24-hour stability, 5 GB transfers, real antivirus locks, paths beyond Windows
`MAX_PATH`, and 10,000-row scrolling performance also need a live GUI/network
run. Sections 1–22 therefore have documented coverage, not blanket
certification. Run each manual or environment-dependent case against its
required OS, app build, external tools, real server, or hardware before making
release claims. Same-length arbitrary edits to partial-file or segment bytes
are not authenticated by these tests; use a supplied checksum to verify the
completed output when that threat matters.

## Sections 15–22 tracker

`[A]` means covered by automated tests listed above; `[M]` means manual or
environment-specific verification remains. A test marked `[A]` does not imply
that every real-world variant or performance target in that section passed.

```text
SECTION 15 — BATCH / CLIPBOARD
15.1 [A] 15.2 [A] 15.3 [A] 15.4 [A] 15.5 [A] 15.6 [A] 15.7 [A] 15.8 [M]

SECTION 16 — FILENAME / PATH / STORAGE
16.1 [A*] 16.2 [M] 16.3 [A] 16.4 [A] 16.5 [A] 16.6 [M] 16.7 [M] 16.8 [A]
16.9 [A] 16.10 [A] 16.11 [M]

SECTION 17 — CONCURRENCY / THREAD SAFETY
17.1 [A] 17.2 [A] 17.3 [A] 17.4 [A] 17.5 [M] 17.6 [M] 17.7 [M] 17.8 [M]

SECTION 18 — MEMORY / CPU
18.1 [M] 18.2 [M] 18.3 [M] 18.4 [M] 18.5 [M] 18.6 [M] 18.7 [A]

SECTION 19 — CROSS-PLATFORM
19.1 [M] 19.2 [M] 19.3 [M] 19.4 [A] 19.5 [A] 19.6 [M] 19.7 [M]

SECTION 20 — SHUTDOWN / PROCESSES / CLEANUP
20.1 [M] 20.2 [M] 20.3 [M] 20.4 [M] 20.5 [M] 20.6 [A*]

SECTION 21 — LOCALIZATION / ACCESSIBILITY
21.1 [A*] Urdu core UI translation and English fallback for untranslated text
21.2 [A] Keyboard shortcuts register and focus their intended controls
21.3 [A] Space toggles pause/resume when the queue has focus
21.4 [A] Urdu keyboard shortcut help text
21.5 [M] Tab/Shift+Tab traversal with mouse-free workflow
21.6 [M] Read current progress status using supported screen reader
21.7 [M] Urdu shaping, font coverage, contrast, and screen-reader output per OS
21.8 [M] Verify Urdu right-to-left reading and layout suitability with users

SECTION 22 — VLC PLAYER / DISPLAY / AUDIO
22.1 [A] Player video/controls embed in main Media preview; no separate window
22.2 [A] Stop retains the UI; Close player restores preview without closing app
22.3 [M] Minimize/restore app and verify the embedded interface stays available
22.4 [A] Volume slider applies 0–100 values and shows rounded percentage
22.5 [A] Track list maps displayed tracks to VLC IDs; no-track state is disabled
22.6 [A] Dedicated video fullscreen does not change main-app geometry
22.7 [A] Escape/F11 returns video to preview; fullscreen has playback/audio controls
22.8 [A] Player Help explains separate fullscreen and controls
22.9 [M] Test available 240p/360p/480p/720p/1080p/1440p/2160p media
22.10 [M] Test portrait/ultrawide clips, aspect ratio, resizing, volume, and tracks
PV-1–PV-9 [A/M] Detailed VLC checks and manual resolution matrix are in TEST_CASES.md

FAILURES ENCOUNTERED AND ADDRESSED
- Progress callbacks could overwhelm UI event processing:
  same-status updates are throttled; status changes are not delayed.
- Long sanitized filenames could lose extensions:
  base truncation now preserves ordinary extensions.
- Transient assembly/replace file locks failed immediately:
  replacement retries with bounded backoff and surfaces persistent errors.
- Clipboard contention could interrupt polling:
  clipboard errors are reported and polling continues; rapid-copy capture is
  still best-effort and clipboard contents are never automatically enqueued.
- Malformed parallel metadata could poison resume state:
  invalid metadata is discarded and range data is fetched afresh.

* Mocked subprocess coverage only; verify real child-process shutdown manually.
* Mocked retry coverage only; verify recovery from real network loss manually.
* Tk and screen-reader behavior varies by platform; verify announcements and
  Urdu glyph shaping on the supported OS/screen-reader combinations.
```
