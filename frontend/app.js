const connectButton = document.querySelector("#connectButton");
const folderSection = document.querySelector("#folderSection");
const folderSelect = document.querySelector("#folderSelect");
const refreshFoldersButton = document.querySelector("#refreshFoldersButton");
const selectFolderButton = document.querySelector("#selectFolderButton");
const selfieSection = document.querySelector("#selfieSection");
const selfieInput = document.querySelector("#selfieInput");
const selfiePreview = document.querySelector("#selfiePreview");
const dropZone = document.querySelector("#dropZone");
const dropText = document.querySelector("#dropText");
const scanButton = document.querySelector("#scanButton");
const progressSection = document.querySelector("#progressSection");
const progressText = document.querySelector("#progressText");
const progressBar = document.querySelector("#progressBar");
const resultsSection = document.querySelector("#resultsSection");
const resultsGrid = document.querySelector("#resultsGrid");
const resultCount = document.querySelector("#resultCount");
const message = document.querySelector("#message");

let selectedFolderId = "";
let selectedSelfie = null;
let matchCount = 0;

function show(element) {
  element.classList.remove("hidden");
}

function hide(element) {
  element.classList.add("hidden");
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { credentials: "include", ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || "Request failed");
  }
  return payload;
}

async function connectGoogleDrive() {
  try {
    setMessage("");
    const payload = await requestJson("/auth/google");
    window.location.href = payload.auth_url;
  } catch (error) {
    setMessage(error.message, true);
  }
}

async function loadFolders() {
  try {
    setMessage("");
    folderSelect.innerHTML = '<option value="">Loading folders...</option>';
    const folders = await requestJson("/drive/folders");
    folderSelect.innerHTML = "";

    if (!folders.length) {
      folderSelect.innerHTML = '<option value="">No folders found</option>';
      return;
    }

    for (const folder of folders) {
      const option = document.createElement("option");
      option.value = folder.id;
      option.textContent = folder.name;
      folderSelect.append(option);
    }
  } catch (error) {
    folderSelect.innerHTML = '<option value="">Connect Google Drive first</option>';
    setMessage(error.message, true);
  }
}

function selectFolder() {
  selectedFolderId = folderSelect.value;
  if (!selectedFolderId) {
    setMessage("Choose a Drive folder first.", true);
    return;
  }
  show(selfieSection);
  setMessage("Folder selected. Add your selfie next.");
}

function setSelfie(file) {
  if (!file) return;
  selectedSelfie = file;
  selfiePreview.src = URL.createObjectURL(file);
  show(selfiePreview);
  hide(dropText);
  scanButton.disabled = false;
}

function addMatchCard(event) {
  matchCount += 1;
  resultCount.textContent = `Found ${matchCount} photos with you in them`;

  const card = document.createElement("article");
  card.className = "result-card";
  card.innerHTML = `
    <img src="${event.thumbnail_url}" alt="${event.file_name}">
    <div class="result-body">
      <h3></h3>
      <p>${Math.round(event.score * 100)}% match</p>
      ${event.drive_url ? `<a href="${event.drive_url}" target="_blank" rel="noreferrer">Open in Drive</a>` : ""}
    </div>
  `;
  card.querySelector("h3").textContent = event.file_name;
  resultsGrid.append(card);
}

function handleSseEvent(event) {
  if (event.type === "progress") {
    const percent = event.total ? (event.current / event.total) * 100 : 0;
    progressText.textContent = `Scanning photo ${event.current} of ${event.total}: ${event.file_name}`;
    progressBar.style.width = `${percent}%`;
  }

  if (event.type === "match") {
    addMatchCard(event);
  }

  if (event.type === "done") {
    progressText.textContent = `Finished scanning ${event.total_scanned} photos.`;
    progressBar.style.width = "100%";
    scanButton.disabled = false;
  }

  if (event.type === "error") {
    setMessage(event.message, true);
  }
}

async function startScan() {
  if (!selectedFolderId || !selectedSelfie) {
    setMessage("Select a folder and upload a selfie first.", true);
    return;
  }

  scanButton.disabled = true;
  matchCount = 0;
  resultsGrid.innerHTML = "";
  resultCount.textContent = "Found 0 photos with you in them";
  progressBar.style.width = "0";
  progressText.textContent = "Starting scan...";
  show(progressSection);
  show(resultsSection);
  setMessage("");

  const formData = new FormData();
  formData.append("folder_id", selectedFolderId);
  formData.append("selfie", selectedSelfie);

  try {
    const response = await fetch("/scan", {
      method: "POST",
      credentials: "include",
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Scan failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.split("\n").find((item) => item.startsWith("data: "));
        if (line) {
          handleSseEvent(JSON.parse(line.slice(6)));
        }
      }
    }
  } catch (error) {
    scanButton.disabled = false;
    setMessage(error.message, true);
  }
}

connectButton.addEventListener("click", connectGoogleDrive);
refreshFoldersButton.addEventListener("click", loadFolders);
selectFolderButton.addEventListener("click", selectFolder);
scanButton.addEventListener("click", startScan);

selfieInput.addEventListener("change", (event) => setSelfie(event.target.files[0]));

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  setSelfie(event.dataTransfer.files[0]);
});

if (new URLSearchParams(window.location.search).get("auth") === "success") {
  show(folderSection);
  loadFolders();
  window.history.replaceState({}, document.title, "/");
}
