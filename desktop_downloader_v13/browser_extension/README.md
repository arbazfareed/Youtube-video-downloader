# Smart Downloader 13 browser extension

The extension adds context-menu actions for a page, link, video/audio element,
or media element detected on the page. It sends the selected URL to the local
Smart Downloader 13 REST API; it does not bypass sign-in, DRM, or website access
controls. Site support depends on yt-dlp and the specific URL.

## Start the API

From the source folder, run `launch_api.py`. From a portable Windows release,
run `.\SmartDownloader13.exe --api` in PowerShell; from Linux, run
`./SmartDownloader13 --api` in a terminal. The API prints its
Bearer token in the terminal. Keep the API bound to `127.0.0.1` for extension
use on this computer. The extension refuses to send that token to a non-local
server.

## Install in Chrome

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Choose **Load unpacked** and select this `browser_extension` folder.
3. Open the extension popup. Paste the API token from the API terminal and set
   the save folder on the PC, then choose **Save settings**.
4. Right-click a page, link, or video/audio element and choose the Smart
   Downloader 12 action. Use **Download detected media** for a media element
   found on the page. For sites such as YouTube, send the page URL so yt-dlp can
   use its site extractor.

## Install in Firefox

Firefox Developer Edition or another build that supports temporary add-ons:

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on** and select `manifest.firefox.json`.
3. Configure the API token and output folder in the add-on popup.

Temporary Firefox add-ons are removed when the browser closes. Permanent
distribution requires Mozilla signing.

The API token is saved in the browser extension's local storage. Do not share
your browser profile or API token. This extension uses the authenticated
loopback REST API directly, so a separate native-messaging host is not needed.
