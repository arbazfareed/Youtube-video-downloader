# Smart Downloader 13.0 — User and Test Guide

## What this guide is for

This guide explains the app and its checks in everyday language. For engineering
requirements, see [SOFTWARE_REQUIREMENTS.md](./SOFTWARE_REQUIREMENTS.md). For
step-by-step QA actions and expected results, see
[TEST_CASES.md](./TEST_CASES.md). The full implementation coverage notes are
in [TESTING.md](./TESTING.md).

## What Smart Downloader does

Smart Downloader helps you queue downloads from supported public file and media
links, choose where files are saved, watch progress, pause or cancel work, and
reopen download history later. Depending on your setup, v13 also includes
media playback and additional tools. See the [v13 README](./README.md) and
[setup guide](./SETUP.md) for supported features and requirements.

The app cannot guarantee every site or URL will work. It is not intended to
bypass DRM, sign-in restrictions, paywalls, or other access controls. Download
only material you are allowed to save and follow the source service's terms.

## User stories

| Story | As a user, I want to… | So that… | Acceptance reference |
| --- | --- | --- | --- |
| US-01 | Open the app and receive a clear message if a required dependency or history file has a problem. | I can use the app or know what to fix instead of seeing a silent crash. | TC-1.1–TC-1.9 |
| US-02 | Paste an HTTP or HTTPS link and get a helpful message when it is malformed or unsupported. | I can correct the link before a transfer begins. | TC-2.1–TC-2.6 |
| US-03 | Use URLs containing spaces, non-English characters, or query parameters. | Valid links work without corrupting the request. | TC-2.7–TC-2.10 |
| US-04 | Keep authentication details and saved files safe. | My credentials are not printed in errors and a crafted filename cannot escape my chosen folder. | TC-2.14–TC-2.15 |
| US-05 | See whether a file really completed, including when the connection stops early. | I do not mistake a truncated file for a successful download. | TC-4.1, TC-4.8–TC-4.10, TC-4.14 |
| US-06 | Resume a transfer when the server supports it. | I can continue without corruptly appending data if the server's response changed. | TC-4.2–TC-4.3, TC-4.13–TC-4.14 |
| US-07 | Queue multiple files without the app starting too many at once. | My computer and network remain manageable. | TC-4.15 |
| US-08 | Understand when an external server, network, or device still needs a real-world check. | Test results are honest and I know what has not been certified. | TEST_CASES.md and TESTING.md |

## How to read the test results

- **Automated — local** means a test uses temporary files, a database, or app
  objects on the test machine.
- **Automated — mocked** means a test pretends to be a server, operating
  system, or external program. It checks app logic, not the real service.
- **Partial** means only part of a scenario has been tested automatically.
- **Manual — pending** means someone must run that case on the specified
  computer, OS, network, or packaged build and record what happened.
- **Not separately evidenced** means there is no dedicated recorded test for
  that exact scenario yet.

The automated v13 suite previously passed 191 tests. That count does **not**
mean every real-device or environment-specific check passed. In particular,
offline packaged launches, 10,000-row startup time, actual network changes,
sleep/wake behavior, real authentication, long-duration stability, measured
memory/CPU, and real child-process cleanup need their own checks.

The clipboard helper checks the current clipboard periodically and can fill the
URL box; it does not automatically add clipboard URLs to the queue. A rapid
series of copies may be missed.

## Simple check-before-release workflow

1. Read the exact case in [TEST_CASES.md](./TEST_CASES.md).
2. Run automated tests using the command at the top of that document.
3. For a manual case, use a safe test folder and test data; avoid real account
   credentials and personal history.
4. Record the app commit, OS, steps, expected result, actual result, and any
   error in the provided failure report template.
5. Mark a case passed only after observing the expected result on the stated
   setup. If it cannot be run, mark it blocked or not run.
6. Share logs only after removing passwords, tokens, and private URLs.

## Where to get help

For installation and troubleshooting, follow [SETUP.md](./SETUP.md). For
feature details and known limitations, use [README.md](./README.md). When
reporting a problem, include the test ID if the issue occurred while following
the checklist, but do not include private credentials.
