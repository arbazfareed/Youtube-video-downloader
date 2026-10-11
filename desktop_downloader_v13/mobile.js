const params = new URLSearchParams(location.hash.slice(1));
const jobId = params.get("job");
const token = params.get("token");
const statusElement = document.getElementById("status");
const messageElement = document.getElementById("message");

async function request(path, method = "GET") {
  const response = await fetch(path, {
    method,
    headers: { "Authorization": `Bearer ${token}` }
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || `Server returned ${response.status}.`);
  }
  return result;
}

async function refresh() {
  if (!jobId || !token) {
    statusElement.textContent = "This phone link is incomplete.";
    return;
  }
  try {
    const job = await request(`/mobile/jobs/${encodeURIComponent(jobId)}`);
    statusElement.textContent = `${job.status}${job.progress == null ? "" : ` — ${job.progress.toFixed(1)}%`}`;
    messageElement.textContent = job.error || "";
  } catch (error) {
    statusElement.textContent = "Could not connect to the PC.";
    messageElement.textContent = error.message;
  }
}

for (const button of document.querySelectorAll("button[data-action]")) {
  button.addEventListener("click", async () => {
    try {
      await request(`/mobile/jobs/${encodeURIComponent(jobId)}/${button.dataset.action}`, "POST");
      await refresh();
    } catch (error) {
      messageElement.textContent = error.message;
    }
  });
}

refresh();
setInterval(refresh, 3000);
