# v13 test and behavior checklist

Run the automated suite from this directory:

```powershell
..\.venv-3\Scripts\python.exe -m unittest discover -s tests -v
```

The checklist tests use temporary directories and databases, mocked HTTP and
subprocess responses, and test doubles for application state. They do not
change network adapters, sleep the computer, or access normal user history.

## Progress from the previous pass

The earlier passes completed Sections 1–14 and passed 181 tests. This pass
adds 10 Section 15–20 regression tests; the complete suite now passes 191 tests.

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
Rapid cancel/re-add timing, zombie socket/thread counts, measured RAM/CPU,
24-hour stability, 5 GB transfers, real antivirus locks, paths beyond Windows
`MAX_PATH`, and 10,000-row scrolling performance also need a live GUI/network
run. Sections 1–20 therefore have documented coverage, not blanket
certification. Run each manual or environment-dependent case against its
required OS, app build, external tools, real server, or hardware before making
release claims. Same-length arbitrary edits to partial-file or segment bytes
are not authenticated by these tests; use a supplied checksum to verify the
completed output when that threat matters.

## Sections 15–20 tracker

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
```
