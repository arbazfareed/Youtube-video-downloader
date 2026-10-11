const extensionApi = globalThis.browser || globalThis.chrome;
const fields = ["apiUrl", "apiToken", "output"];

async function loadSettings() {
  const values = await extensionApi.storage.local.get({
    apiUrl: "http://127.0.0.1:8765",
    apiToken: "",
    output: "downloads",
    lastResult: "",
    lastJobId: ""
  });
  for (const name of fields) {
    document.getElementById(name).value = values[name];
  }
  document.getElementById("result").textContent = values.lastResult;
  document.getElementById("showQr").disabled = !values.lastJobId;
}

async function saveSettings() {
  const values = Object.fromEntries(fields.map(name => [
    name,
    document.getElementById(name).value.trim()
  ]));
  const apiUrl = new URL(values.apiUrl);
  if (apiUrl.protocol !== "http:" ||
      !["127.0.0.1", "localhost", "[::1]", "::1"].includes(apiUrl.hostname)) {
    throw new Error("Use this computer's local API address, such as http://127.0.0.1:8765.");
  }
  if (!values.apiToken || !values.output) {
    throw new Error("Enter the API token and the local save folder.");
  }
  await extensionApi.storage.local.set(values);
  document.getElementById("result").textContent = "Settings saved.";
}

async function downloadCurrentPage() {
  await saveSettings();
  const [tab] = await extensionApi.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) {
    throw new Error("Could not read the active page URL.");
  }
  const config = await extensionApi.storage.local.get();
  const endpoint = new URL("/jobs", config.apiUrl);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${config.apiToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ url: tab.url, output: config.output, source: "auto", mode: "video" })
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || `Smart Downloader API returned ${response.status}.`);
  }
  document.getElementById("result").textContent = `Queued job ${body.id}`;
  document.getElementById("showQr").disabled = false;
  await extensionApi.storage.local.set({
    lastResult: `Queued job ${body.id}`,
    lastJobId: body.id
  });
}

document.getElementById("save").addEventListener("click", () => {
  saveSettings().catch(error => {
    document.getElementById("result").textContent = error.message;
  });
});
document.getElementById("downloadPage").addEventListener("click", () => {
  downloadCurrentPage().catch(error => {
    document.getElementById("result").textContent = error.message;
  });
});
document.getElementById("showQr").addEventListener("click", async () => {
  try {
    await saveSettings();
    const config = await extensionApi.storage.local.get();
    const endpoint = new URL(
      `/jobs/${encodeURIComponent(config.lastJobId)}/handoff/qr`,
      config.apiUrl
    );
    const response = await fetch(endpoint, {
      headers: { "Authorization": `Bearer ${config.apiToken}` }
    });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || `Smart Downloader API returned ${response.status}.`);
    }
    document.getElementById("qr").src = URL.createObjectURL(await response.blob());
    document.getElementById("result").textContent = "Scan with your phone on the same Wi-Fi.";
  } catch (error) {
    document.getElementById("result").textContent = error.message;
  }
});
loadSettings().catch(error => {
  document.getElementById("result").textContent = error.message;
});
