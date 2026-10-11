# Smart Downloader 13.0 — Detailed Test Cases

This catalog expands the requested Sections 1, 2, and 4 into individual
scenarios. The automation column distinguishes simulated regression coverage
from real-machine checks; it is not a release certification.

Run the automated v13 tests from this folder:

```powershell
..\.venv-3\Scripts\python.exe -m unittest discover -s tests -v
```

**Important evidence limit:** mocked tests validate behavior in the simulated
conditions they exercise, not every real device, operating system, package,
network, or third-party server. The automated suite passing does not certify
the manual or environment-dependent cases below.

## Section 1 — Startup and system locks

| ID | Scenario and action | Expected result | Current evidence |
| --- | --- | --- | --- |
| 1.1 | Launch the installed app or packaged executable normally. | Main window opens and history is available without an unhandled error. | Manual — pending on each release build/OS. |
| 1.2 | Disable network access and launch the app. | Local GUI opens; lack of network does not crash startup. | Manual — pending. |
| 1.3 | Launch with the expected virtual environment or a required dependency missing. | The launcher either restores prerequisites as designed or presents an actionable error; it must not fail silently. | Partial — automated dependency failure reporting; missing-environment recreation is manual. |
| 1.4 | Use a copy of history.sqlite3 with invalid/corrupt SQLite content, then launch. | Damaged history is preserved as a timestamped backup; a clean DB is initialized and the user is informed. | Automated — local corrupt-DB and sidecar-preservation tests. |
| 1.5 | Configure a read-only or unwritable download destination and launch/use the app. | A clear permission/destination error is shown; the GUI remains usable. | Manual — pending with real filesystem permissions. |
| 1.6 | Start the app twice. | The app follows the implemented policy (independent instances or a clear single-instance response) without corrupting shared state. | Manual — pending; do not claim single-instance enforcement without a verified result. |
| 1.7 | Populate a safe test DB with 10,000 history rows and launch. | Startup meets the release performance target (suggested target: under 2 seconds) and history remains navigable. | Manual/performance — pending; no 10k latency result recorded. |
| 1.8 | Hold an exclusive lock on a test history DB from another process and launch. | App reports the lock and does not classify or replace the DB as corrupt. | Automated — simulated/exclusive-lock handling; external SQLite browser validation remains manual. |
| 1.9 | Run from a UNC/network share path. | App handles the path or reports a clear unsupported/permission error; no path-related crash. | Manual — pending on a Windows network share. |

## Section 2 — URL input and sanitization

| ID | Scenario and action | Expected result | Current evidence |
| --- | --- | --- | --- |
| 2.1 | Add `http://example.com/file.zip`. | URL is accepted and forwarded to the download route. | Automated — supported HTTP URL forwarding, no live transfer. |
| 2.2 | Add `https://example.com/file.zip`. | URL is accepted and forwarded to the download route. | Automated — supported HTTPS URL forwarding, no live transfer. |
| 2.3 | Submit an empty URL. | Validation asks the user to enter a URL; no worker/network request starts. | Not separately evidenced by current regression test; manual/UI check pending. |
| 2.4 | Submit an unsupported scheme such as `ftp://example.com/file`. | URL is rejected with a clear HTTP/HTTPS-only or supported-site validation message. | Automated — invalid-scheme rejection. |
| 2.5 | Submit a malformed URL such as `ht!tp://bad`. | URL is rejected before a network request; input remains recoverable. | Automated — malformed URL validation. |
| 2.6 | Submit a URL with no hostname, such as `https:///file.zip`. | URL is rejected before transfer. | Automated — missing-host/malformed URL validation. |
| 2.7 | Submit a URL containing a space in its path. | Request library safely encodes the path or reports a clear validation error; no malformed request header. | Automated — request URL encoding. |
| 2.8 | Submit a URL containing Unicode path characters. | URL is normalized/encoded for the HTTP request or rejected clearly; no crash. | Automated — Unicode request encoding. |
| 2.9 | Paste a 5,000-character URL. | Input remains stable and validation/handling is bounded; app does not freeze or crash. | Manual — pending; no explicit 5,000-character limit/latency result recorded. |
| 2.10 | Add a URL with query parameters, e.g. `?token=abc`. | Query is preserved for the request; secrets are not exposed in logs/errors. | Automated — URL forwarding and credential-redaction coverage; verify real signed URL manually. |
| 2.11 | Paste a valid URL with Ctrl+V. | URL field receives the clipboard content and remains editable. | Manual GUI interaction — pending for real desktop clipboard. |
| 2.12 | Focus URL field and press Enter. | Same add/validation action as the Add button occurs once. | Manual GUI interaction — pending. |
| 2.13 | Download from a URL that redirects. | Redirect chain is followed according to the HTTP client policy and final response is validated. | Automated — mocked redirect behavior. |
| 2.14 | Submit a path-traversal-like URL such as `/../../etc/passwd`. | Output name is reduced to a safe name within the selected directory; no write escapes the destination. | Automated — safe URL-derived filename behavior; filesystem containment should be rechecked for new routes. |
| 2.15 | Submit `https://user:pass@example.com/file.zip` against a controlled test server. | Authentication is forwarded only as intended; credentials are redacted from displayed errors/logs. | Automated — parsed auth and redaction with simulated responses; real server auth remains manual. |

## Section 4 — Download engine and network behavior

| ID | Scenario and action | Expected result | Current evidence |
| --- | --- | --- | --- |
| 4.1 | Download a 1 MB direct file from a controlled server. | File completes, output size matches, and history/status becomes complete. | Automated — mocked direct-download behavior; live 1 MB transfer pending. |
| 4.2 | Download a 500 MB file from a range-capable server. | Parallel ranges are used when eligible; output assembles in correct order and matches expected bytes. | Partial — automated range splitting/assembly; real 500 MB throughput and integrity test pending. |
| 4.3 | Download from a server that does not support byte ranges. | The client uses a safe single-stream fallback or a clear error; it must not assemble invalid ranges. | Partial — range behavior has regression coverage; real no-Range server check pending. |
| 4.4 | Request a URL returning HTTP 404. | Transfer fails with a visible, useful error; no success-shaped output is recorded. | Automated — mocked HTTP error handling. |
| 4.5 | Request a URL returning HTTP 403. | Transfer fails with a visible, useful error; no success-shaped output is recorded. | Automated — mocked HTTP error handling. |
| 4.6 | Serve HTML content from a URL that appears to be a ZIP/file. | HTML/error content is detected and is not reported as the requested file successfully downloaded. | Automated — mocked HTML response detection. |
| 4.7 | Serve a valid file slowly. | Transfer remains active without UI blocking and can be cancelled; it eventually completes if the connection remains healthy. | Manual — pending with a throttled real server. |
| 4.8 | Drop the connection during transfer, then restore it. | Bounded retries/backoff occur; partial data is resumed only when validators/ranges make it safe, otherwise the transfer restarts or fails clearly. | Automated — mocked connection-drop and retry/resume coverage; real outage test pending. |
| 4.9 | Have server close the body before the advertised number of bytes arrive. | Partial output is not marked complete; retry occurs within policy or a clear failure is shown. | Automated — truncated-response retry and size validation. |
| 4.10 | Return an incorrect Content-Length. | Final size mismatch is detected; incomplete/corrupt output is not marked complete. | Automated — mocked advertised-size mismatch test. |
| 4.11 | Use a controlled authenticated endpoint that requires cookies. | Download succeeds only when valid cookies are configured; failure without them is clear and safe. | Manual — pending; browser cookie import/real auth is not certified by this section's automated tests. |
| 4.12 | Use a controlled endpoint requiring a Referer or custom header. | Configured header is sent to the intended request; unset headers are not fabricated. | Automated — custom-header forwarding; real endpoint check pending. |
| 4.13 | Resume a partial download where server ignores Range and returns HTTP 200. | Existing partial bytes are replaced/restarted rather than incorrectly appended. | Automated — mocked resume response handling. |
| 4.14 | Resume when server returns HTTP 416 and local partial size matches the known total. | Existing file is accepted as complete only when length/validator conditions match. | Automated — matching 416 test; mismatched/oversized cases also have regression coverage. |
| 4.15 | Queue ten direct downloads with three worker slots. | No more than three are active at once; waiting jobs start as slots free; all finish or report errors. | Automated — worker-pool concurrency test with ten tasks. |
| 4.16 | Download a valid chunked response with no Content-Length. | Stream completes safely using received bytes; progress math does not divide by zero. | Automated — chunked/unknown-length stream test. |
| 4.17 | Switch network interfaces while a transfer is running. | Transfer retries/reconnects safely on the new route or fails clearly without corrupting a completed file. | Manual — pending; requires real network adapters. |
| 4.18 | Suspend the computer during a transfer, then wake it. | Timeout/retry policy recovers or reports a bounded failure; UI remains responsive. | Manual — pending on supported OS/hardware. |
| 4.19 | Return HTTP 429 with Retry-After or repeated rate limiting. | Client backs off within configured policy and does not hammer the server indefinitely. | Automated — mocked HTTP 429 retry; real server policy verification pending. |
| 4.20 | Return HTTP 200 with an empty body / zero-byte file. | Valid zero-byte responses complete safely when permitted; no division-by-zero or false positive for a non-empty advertised file. | Automated — zero-byte and size mismatch test coverage. |
| 4.21 | Serve a gzip-encoded response while range offsets are in use. | Byte offsets remain correct; client requests identity encoding for range transfers or otherwise decodes safely without corrupt output. | Partial — requests use `Accept-Encoding: identity`; an actual gzip/range server integration test remains pending. |

## Smart VLC player — separate playback, seeking, fullscreen, and audio controls

Run these manual cases with the packaged app or source app and an installed VLC
runtime. Use media you are permitted to play. The automated tests mock VLC:
they verify control wiring and geometry but cannot certify decoding/rendering
on a real display.

| ID | Scenario and action | Expected result | Current evidence |
| --- | --- | --- | --- |
| PV-1 | Open a local supported video on a standard display. | Video and controls appear in a separate resizable Smart VLC window; the main app preview remains available. | Automated separate-Toplevel regression test; actual video rendering and taskbar check manual. |
| PV-2 | Minimize and restore the Smart VLC window while media is playing. | The player minimizes independently; restoring it returns to the same playback state while the downloader remains usable. | Separate-window/control lifecycle automated; real OS minimize/restore behavior manual. |
| PV-3 | Press Stop, then Play; next press Close player. | Stop halts playback but retains controls; Play resumes; Close player stops playback and closes only the player window. | Automated stop/close/window lifecycle; real playback state manual. |
| PV-4 | Play available clips at 240p, 360p, 480p, 720p, 1080p, 1440p, and 2160p/4K; resize the player window. | Supported resolutions play in the resizable player; aspect ratio is preserved and the video remains visible. | Manual — pending; unit tests do not decode video. |
| PV-5 | Play portrait and ultrawide media, then resize the player window. | Video maintains its source aspect ratio within the video area; letterboxing is acceptable, unintended cropping is not. | Manual — pending. |
| PV-6 | Move volume through 0%, intermediate values, and 100%. | VLC receives a value in the 0–100 range and the displayed integer percentage matches the slider. | Automated callback test; real output loudness/mute verification manual. |
| PV-7 | Open media with multiple audio tracks; switch between tracks during playback. | Track names are listed, the chosen VLC track becomes active, and playback continues. Media with no tracks shows a disabled track selector. | Automated list/selection/no-track tests; real multi-track playback manual. |
| PV-8 | Enter player fullscreen using the button and F11; press Escape, then enter/exit again. | The separate player window becomes fullscreen without reparenting the video surface; the main app stays windowed and unchanged, and Escape/F11 returns to windowed playback. | Unit test plus Windows smoke test confirmed playback time advances across fullscreen with the same video handle and unchanged host geometry; visible frame output still requires manual inspection. |
| PV-9 | Drag the timeline and repeat PV-1 through PV-8 with audio-only media. | Seeking updates playback position and elapsed/total time; help explains the separate window, seek, Stop/Close, volume, and tracks. | Automated seek/time/help tests plus mocked audio path; real audio/video playback manual. |
| PV-10 | Run Smart Downloader on a narrow/portrait display or resize the window below 760 px, then inspect the downloader and media preview. | Navigation collapses and the media inspector reflows below the downloader area; labels and the two-column action buttons remain reachable rather than clipped off the right edge. | Automated 600/900/1300 px layout transition; physical resolution/high-DPI verification manual. |
| PV-11 | Enter player fullscreen on a narrow display and inspect controls. | The video remains visible on the same surface and playback controls remain accessible; Escape/F11 restores windowed playback. | Automated same-surface fullscreen test; real VLC rendering manual. |

## Failure report template

Use this template for every failed, blocked, or manually executed case:

```text
Test ID:
Date/time and timezone:
App version / commit:
OS / architecture:
Test server or fixture:
Preconditions:
Action:
Expected result:
Observed result:
Error traceback / log (remove credentials and tokens):
Result: pass / fail / blocked / not run
Failure cause (confirmed or unknown):
Fix needed:
Retest result:
```

## Results and limitations

The current v13 unit suite passes 209 tests. That result is evidence for
those automated tests only. Cases labelled manual, partial, or not separately
evidenced above remain open for their stated environment or scenario. Update
the evidence label only after running and recording the exact case; do not infer
that a test passed from a related test or from the overall suite count.
