// =========================
// LOCAL STORAGE STORE
// =========================
const STORE_KEY = "transcript_service_state_v1";

function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveStore(partial) {
  const prev = loadStore() || {};
  const next = { ...prev, ...partial, updated_at: Date.now() };
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(next));
  } catch {}
  return next;
}

function clearStore() {
  try {
    localStorage.removeItem(STORE_KEY);
  } catch {}
}

// =========================
// DOM
// =========================
const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadResp = document.getElementById("uploadResp");

const jobSection = document.getElementById("jobSection");
const outputsBox = document.getElementById("outputsBox");
const startJobBtn = document.getElementById("startJobBtn");

const statusSection = document.getElementById("statusSection");
const jobIdLabel = document.getElementById("jobIdLabel");
const jobStatusLabel = document.getElementById("jobStatusLabel");
const statusJson = document.getElementById("statusJson");
const downloadBtn = document.getElementById("downloadBtn");
const resetBtn = document.getElementById("resetBtn");

const recentJobsSection = document.getElementById("recentJobsSection");
const recentJobsList = document.getElementById("recentJobsList");

const errorSection = document.getElementById("errorSection");
const errorBox = document.getElementById("errorBox");

let currentJobId = null;
let pollTimer = null;

// =========================
// CLIENT ID
// =========================
const CLIENT_KEY = "transcript_client_id";

function getClientId() {
  let id = localStorage.getItem(CLIENT_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(CLIENT_KEY, id);
  }
  return id;
}

// =========================
// UI HELPERS
// =========================
function showError(err) {
  errorSection.classList.remove("hidden");
  errorBox.textContent = typeof err === "string" ? err : JSON.stringify(err, null, 2);
}

function clearError() {
  errorSection.classList.add("hidden");
  errorBox.textContent = "";
}

function setUploadDebug(obj) {
  uploadResp.classList.remove("hidden");
  uploadResp.textContent = JSON.stringify(obj, null, 2);
}

function renderOutputs(outputs) {
  outputsBox.innerHTML = "";
  outputs.forEach((o) => {
    const id = `out_${o}`;
    const line = document.createElement("label");
    line.className = "checkbox";
    line.innerHTML = `
      <input type="checkbox" id="${id}" value="${o}" checked />
      <span>${o}</span>
    `;
    outputsBox.appendChild(line);
  });
}

function getSelectedOutputs() {
  const checked = Array.from(outputsBox.querySelectorAll("input[type=checkbox]:checked"));
  return checked.map((x) => x.value);
}

// =========================
// API HELPERS
// =========================
async function apiJson(url, opts = {}) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {}
  if (!res.ok) {
    throw { status: res.status, body: data ?? text };
  }
  return data ?? {};
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("client_id", getClientId());
  return await apiJson("/uploads", { method: "POST", body: fd });
}

async function createJob(jobId, outputs) {
  return await apiJson("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      job_id: jobId, 
      requested_outputs: outputs, 
      client_id: getClientId() 
    }),
  });
}

async function getJob(jobId) {
  return await apiJson(`/jobs/${jobId}`);
}

async function listJobsByClient() {
  const clientId = getClientId();
  return await apiJson(`/jobs?client_id=${encodeURIComponent(clientId)}`);
}

function renderRecentJobs(jobs) {
  recentJobsList.innerHTML = "";

  if (!Array.isArray(jobs) || jobs.length === 0) {
    recentJobsSection.classList.add("hidden");
    return;
  }

  recentJobsSection.classList.remove("hidden");

  jobs.forEach((job) => {
    const row = document.createElement("div");
    row.className = "recent-job-row";

    const status = job.status || "-";
    const canDownload = status === "succeeded";

    row.innerHTML = `
      <div>
        <strong>${job.job_id}</strong><br />
        <small>Status: ${status}</small>
      </div>
      <div class="recent-job-actions">
        <button class="resume-btn" data-job-id="${job.job_id}">Resume</button>
        ${
          canDownload
            ? `<button class="download-recent-btn" data-job-id="${job.job_id}">Download</button>`
            : ""
        }
      </div>
    `;

    recentJobsList.appendChild(row);
  });

  recentJobsList.querySelectorAll(".resume-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const jobId = btn.dataset.jobId;
      currentJobId = jobId;
      statusSection.classList.remove("hidden");
      jobIdLabel.textContent = jobId;
      jobStatusLabel.textContent = "loading...";
      statusJson.textContent = "";
      downloadBtn.classList.add("hidden");
      startPolling(jobId);
    });
  });

  recentJobsList.querySelectorAll(".download-recent-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const jobId = btn.dataset.jobId;
      window.location.href = `/jobs/${jobId}/result`;
    });
  });
}

async function refreshRecentJobs() {
  try {
    const data = await listJobsByClient();
    renderRecentJobs(data.jobs || []);
  } catch (err) {
    console.error("Failed to load recent jobs", err);
  }
}
// =========================
// POLLING
// =========================
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function startPolling(jobId) {
  stopPolling();

  jobStatusLabel.textContent = "polling...";
  downloadBtn.classList.add("hidden");

  pollTimer = setInterval(async () => {
    try {
      const st = await getJob(jobId);

      jobStatusLabel.textContent = st.status || "-";
      statusJson.textContent = JSON.stringify(st, null, 2);

      // persist latest status
      saveStore({
        job_id: jobId,
        status: st.status || null,
      });

      if (st.status === "succeeded") {
        downloadBtn.classList.remove("hidden");
        stopPolling();
      } else if (st.status === "failed") {
        stopPolling();
        showError(st.error || st);
      }
    } catch (e) {
      stopPolling();
      showError(e);
    }
  }, 1500);
}

// =========================
// RESET UI
// =========================
function resetUI() {
  clearError();
  stopPolling();

  currentJobId = null;
  fileInput.value = "";

  uploadResp.classList.add("hidden");
  uploadResp.textContent = "";

  jobSection.classList.add("hidden");
  statusSection.classList.add("hidden");
  downloadBtn.classList.add("hidden");

  startJobBtn.disabled = true;

  jobIdLabel.textContent = "-";
  jobStatusLabel.textContent = "-";
  statusJson.textContent = "";
}

// =========================
// EVENTS
// =========================
uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  stopPolling();

  const file = fileInput.files?.[0];
  if (!file) return;

  try {
    const up = await uploadFile(file);
    setUploadDebug(up);

    currentJobId = up.job_id;

    // Persist job id + available outputs (so we can restore on refresh even before starting)
    saveStore({
      job_id: currentJobId,
      available_outputs: up.available_outputs || [],
      requested_outputs: null,
      status: "uploaded",
    });

    renderOutputs(up.available_outputs || []);
    jobSection.classList.remove("hidden");
    startJobBtn.disabled = (up.available_outputs || []).length === 0;

    statusSection.classList.add("hidden");
    downloadBtn.classList.add("hidden");
    jobIdLabel.textContent = currentJobId;
    jobStatusLabel.textContent = "uploaded";
    statusJson.textContent = "";

    await refreshRecentJobs();
  } catch (err) {
    showError(err);
  }
});

startJobBtn.addEventListener("click", async () => {
  clearError();
  if (!currentJobId) return;

  const selected = getSelectedOutputs();
  if (selected.length === 0) {
    showError("Sélectionne au moins un output.");
    return;
  }

  try {
    const resp = await createJob(currentJobId, selected);

    // Persist requested outputs
    saveStore({
      job_id: currentJobId,
      requested_outputs: selected,
      status: resp.status || "queued",
    });

    statusSection.classList.remove("hidden");
    jobIdLabel.textContent = resp.job_id || currentJobId;
    jobStatusLabel.textContent = resp.status || "queued";

    startPolling(currentJobId);
    await refreshRecentJobs();
  } catch (err) {
    showError(err);
  }
});

downloadBtn.addEventListener("click", () => {
  if (!currentJobId) return;
  window.location.href = `/jobs/${currentJobId}/result`;
});

resetBtn.addEventListener("click", () => {
  clearStore();
  resetUI();
});

// =========================
// INIT (restore last job)
// =========================
(function init() {
  resetUI();
  
  const saved = loadStore();
  refreshRecentJobs();
  if (!saved?.job_id) return;

  currentJobId = saved.job_id;

  // Restore UI sections
  jobIdLabel.textContent = currentJobId;
  statusSection.classList.remove("hidden");
  jobStatusLabel.textContent = saved.status || "restored";

  // If we have available outputs, show the outputs section too
  if (Array.isArray(saved.available_outputs) && saved.available_outputs.length > 0) {
    renderOutputs(saved.available_outputs);
    jobSection.classList.remove("hidden");
    startJobBtn.disabled = false;

    // If we had requested outputs, re-check those specifically
    if (Array.isArray(saved.requested_outputs) && saved.requested_outputs.length > 0) {
      const set = new Set(saved.requested_outputs);
      Array.from(outputsBox.querySelectorAll("input[type=checkbox]")).forEach((el) => {
        el.checked = set.has(el.value);
      });
    }
  }

  // Resume polling to “re-find” the job server-side
  startPolling(currentJobId);
})();