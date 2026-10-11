const extensionApi = globalThis.browser || globalThis.chrome;

const menuItems = [
  ["download-page", "Download this page with Smart Downloader 12", ["page"]],
  ["download-link", "Download this link with Smart Downloader 12", ["link"]],
  ["download-media", "Download this video/audio with Smart Downloader 12", ["video", "audio"]],
  ["download-detected", "Download detected media with Smart Downloader 12", ["page"]]
];

extensionApi.runtime.onInstalled.addListener(() => {
  for (const [id, title, contexts] of menuItems) {
    extensionApi.contextMenus.create({ id, title, contexts });
  }
});

function allowedUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:", "magnet:"].includes(url.protocol);
  } catch {
    return false;
  }
}

async function submitDownload(url) {
  if (!allowedUrl(url)) {
    throw new Error("The page did not expose a downloadable HTTP(S) or magnet link.");
  }
  const config = await extensionApi.storage.local.get({
    apiUrl: "http://127.0.0.1:8765",
    apiToken: "",
    output: "downloads"
  });
  const endpoint = new URL(config.apiUrl);
  if (!["127.0.0.1", "localhost", "::1"].includes(endpoint.hostname)) {
    throw new Error("For safety, the API address must point to this computer.");
  }
  endpoint.pathname = "/jobs";
  endpoint.search = "";
  endpoint.hash = "";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${config.apiToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ url, output: config.output, source: "auto", mode: "video" })
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || `Smart Downloader API returned ${response.status}.`);
  }
  await extensionApi.storage.local.set({
    lastResult: `Queued job ${body.id}`,
    lastJobId: body.id
  });
}

extensionApi.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    let url;
    if (info.menuItemId === "download-link") {
      url = info.linkUrl;
    } else if (info.menuItemId === "download-media" && allowedUrl(info.srcUrl || "")) {
      url = info.srcUrl;
    } else if (info.menuItemId === "download-detected" && tab?.id !== undefined) {
      const result = await extensionApi.tabs.sendMessage(tab.id, { type: "find-media" });
      url = result?.url || tab.url;
    } else {
      url = tab?.url;
    }
    await submitDownload(url || "");
  } catch (error) {
    await extensionApi.storage.local.set({
      lastResult: `Could not queue download: ${error.message}`
    });
  }
});
