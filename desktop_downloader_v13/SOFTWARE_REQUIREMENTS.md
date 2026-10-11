# Smart Downloader 13.0 — Software Requirements Specification

## 1. Document purpose

This specification describes the expected behavior of Smart Downloader 13.0
(v13), the verification approach, and the limits of the evidence currently
available. It is intended for developers, testers, release owners, and anyone
evaluating whether a particular behavior has actually been verified.

Detailed, executable-oriented scenarios for startup, URL handling, and direct
downloads are in [TEST_CASES.md](./TEST_CASES.md). A plain-language overview
and user stories are in [USER_GUIDE.md](./USER_GUIDE.md). The broader v13
coverage and manual checks are tracked in [TESTING.md](./TESTING.md).

## 2. Product scope

Smart Downloader 13.0 is a desktop application for organizing and running
downloads of public direct-file URLs and public media URLs supported by
yt-dlp. Depending on configuration and optional dependencies, it also provides
media playback, torrents through aria2, local image and file utilities, and
other integrations described in the [v13 README](./README.md).

This SRS focuses on the test plan requested for Sections 1 (Startup), 2 (URL
Input), and 4 (Download Engine), plus quality and evidence requirements that
apply across the app.

### 2.1 Out of scope

- Downloading DRM-protected, paywalled, private, or otherwise unauthorized
  content.
- Guaranteeing that every URL or third-party website remains supported.
- Certifying every operating system, packaged executable, network, storage
  device, or external application from a mocked unit test.
- Treating unrun or environment-dependent tests as passed.

## 3. Users and operating environment

### 3.1 User classes

- **Desktop user:** adds URLs, selects a destination, manages transfers, and
  opens completed media or files.
- **Power user / operator:** configures download options, uses CLI or API
  integrations, and diagnoses failures.
- **Tester / release owner:** runs automated tests and performs environment-
  dependent checks before release.

### 3.2 Environment

The source app is Python-based and runs on supported desktop environments.
Packaged Windows and Linux builds have separate operating-system requirements.
Some features require external tools such as VLC, FFmpeg, or aria2. Consult the
version-specific README and SETUP guide for supported prerequisites.

## 4. Functional requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| FR-START-01 | The app shall start without requiring network access for its local GUI and history initialization. | Manual offline launch on each release OS; see TC-1.1 and TC-1.2. |
| FR-START-02 | Startup dependency and history failures shall be reported clearly rather than silently ignored. | Automated dependency and database error tests; see TC-1.3 and TC-1.8. |
| FR-START-03 | When history corruption is detected, the app shall preserve the damaged database before initializing a replacement. A database lock shall not be treated as corruption. | Automated corrupt/locked history tests; see TC-1.4 and TC-1.8. |
| FR-URL-01 | The app shall accept valid HTTP and HTTPS URLs and reject unsupported schemes or malformed hosts before transfer. | Automated URL validation tests; see TC-2.1–TC-2.6. |
| FR-URL-02 | URL encoding, query parameters, and credentials shall be handled without corrupting the request or exposing credentials in errors. | Automated request/auth tests; see TC-2.7, TC-2.8, TC-2.10, and TC-2.15. |
| FR-URL-03 | URL-derived output names shall be safe and shall not escape the chosen destination directory. | Automated filename sanitization tests plus manual review; see TC-2.14. |
| FR-DL-01 | A direct download shall stream data to disk, handle known and unknown lengths, and avoid marking a truncated or mismatched response complete. | Automated mocked HTTP tests; see TC-4.1, TC-4.9, TC-4.10, TC-4.16, and TC-4.20. |
| FR-DL-02 | When supported by the server, a direct download may use HTTP ranges and shall fall back safely if the server does not honor ranges. | Automated range/resume tests and manual server checks; see TC-4.2, TC-4.3, TC-4.13, and TC-4.14. |
| FR-DL-03 | Transient network and rate-limit failures shall use bounded retries; terminal HTTP failures shall be shown to the user. | Automated mocked HTTP tests; see TC-4.4, TC-4.5, TC-4.8, and TC-4.19. |
| FR-DL-04 | Download options such as cookies and custom headers shall be applied only when configured and supported by the transfer route. | Automated option-forwarding tests and manual authenticated-server checks; see TC-4.11 and TC-4.12. |
| FR-DL-05 | A destination disk-space check shall run when a trustworthy total size is known; an unknown size shall not cause unsafe preallocation. | Automated known-size check and manual low-disk validation; see the Section 3.11 storage check in TESTING.md. |
| FR-I18N-01 | Urdu selection shall translate the primary navigation, download controls, queue headings, key settings, and keyboard-help labels; missing translations shall fall back to English. | Translation unit tests; manual visual validation with Urdu-capable fonts. |
| FR-A11Y-01 | Core download actions shall be reachable by keyboard using documented shortcuts and ordinary Tab/Shift+Tab traversal. | Shortcut registration and focus tests; manual interaction test. |
| FR-A11Y-02 | The download queue shall support keyboard focus and selection; Space shall toggle pause/resume for the selected job while the queue has focus. | Automated shortcut callback tests; manual keyboard/screen-reader check. |
| FR-A11Y-03 | Progress status and progress controls shall be keyboard-focusable so users can move focus to read current state through assistive technology. | UI construction and manual platform-specific screen-reader validation. |
| FR-MEDIA-01 | VLC playback shall be embedded in the Smart Downloader Media preview area without creating a separate player window/taskbar entry. Playback controls shall remain in the main interface; minimizing/restoring the app shall hide/restore playback UI without closing it. | Automated embedding/lifecycle tests; manual Windows taskbar and minimize/restore verification. |
| FR-MEDIA-04 | The embedded video surface shall expand with the main application window. Full screen/F11 shall make the app full screen and Escape shall restore its prior geometry. Stop shall stop playback while retaining controls; Close player shall restore the normal preview. | Automated widget/fullscreen/stop/close tests; real display behavior remains manual. |
| FR-MEDIA-02 | The player shall display the current volume as a percentage and apply slider changes from 0–100 to VLC. | Automated volume callback test; real sound-level check is manual. |
| FR-MEDIA-03 | When VLC provides audio-track descriptions, the player shall list the tracks and select the chosen VLC track; unavailable tracks shall be visibly disabled. | Automated track-listing/selection and no-track tests; multi-track media validation is manual. |

## 5. Non-functional requirements

| ID | Requirement | Verification method |
| --- | --- | --- |
| NFR-REL-01 | A network failure, malformed input, corrupt history file, or supported external-process failure shall not crash the GUI silently. | Unit/integration tests plus manual fault injection. |
| NFR-REL-02 | Download success shall reflect verified transfer completion, not merely an HTTP success status. | Size/range checks in automated tests; real-server validation before release. |
| NFR-PERF-01 | The UI shall remain responsive while downloads run; progress event volume shall be bounded without delaying status transitions. | Automated throttling regression test; manual high-throughput GUI test. |
| NFR-PERF-02 | Large file transfer and checksum operations shall stream or copy bounded chunks rather than buffer the entire file in memory. | Automated chunk-level tests; separate memory measurement for release claims. |
| NFR-SEC-01 | User credentials embedded in a URL shall not appear in ordinary error or log text. | Automated redaction test; see TC-2.15. |
| NFR-SEC-02 | URL-derived filenames shall not permit path traversal or use unsafe Windows device names. | Automated sanitization tests; see TC-2.14 and TESTING.md. |
| NFR-PORT-01 | Filesystem operations shall support Unicode and spaces through platform path abstractions. | Automated Windows-path test plus macOS/Linux manual checks. |
| NFR-MAINT-01 | Regression tests and documentation shall identify what is automated, mocked, manual, or not yet verified. | Review this SRS, TEST_CASES.md, and TESTING.md together. |

## 6. Verification states and release claims

Use these labels in test reports:

- **Automated — mocked:** a deterministic test double simulates the OS, server,
  process, or UI. This validates code behavior at the tested boundary but does
  not prove real-device behavior.
- **Automated — local:** the test runs against a temporary local database,
  filesystem, or application object.
- **Manual — pending:** a tester must perform and record the scenario on the
  required OS, hardware, real server, or packaged build.
- **Partial:** automated evidence covers only part of the stated scenario.
- **Not run:** no result has been recorded.

Passing the current unit suite is not equivalent to passing all manual,
environment-dependent, scale, or release checks. In particular, offline
packaged launches, 10,000-row startup performance, network changes, suspend and
resume, real authentication, memory/CPU thresholds, cross-platform execution,
long-duration stability, real subprocess cleanup, and screen-reader/Urdu font
behavior on supported operating systems require separate runs. The app does not
claim automatic live-region announcements across every Tk and screen-reader
combination. VLC codec/resolution combinations and audio-track switching also
depend on installed VLC, the media file, graphics hardware, and output device;
the unit tests do not certify actual playback.
See [TESTING.md](./TESTING.md) for the current list of these limitations.

## 7. Traceability and test reports

Case IDs in [TEST_CASES.md](./TEST_CASES.md) map the requirements above to
actions, expected outcomes, and current evidence. Every failure report should
include:

```text
Test ID:
Environment / build:
Preconditions:
Observed behavior:
Expected behavior:
Error traceback / log (redact secrets):
Result: pass / fail / blocked / not run
Fix or follow-up:
Retest result:
```

Do not include real passwords, API tokens, private URLs, or personal download
history in a report. Keep original logs only where permitted and redact
credentials before sharing them.

## 8. Change control

Changes that alter expected user behavior should update the relevant functional
requirement, test case, automated test where practical, and user-facing guide.
Do not claim a test passed unless its result was observed and recorded.
