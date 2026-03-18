let improveResult = null;
let improveSharedResult = null;
let loadedModels = [];

async function api(url, method = "GET", data = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (data) {
    options.body = JSON.stringify(data);
  }

  const res = await fetch(url, options);
  const text = await res.text();

  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = { raw: text };
  }

  if (!res.ok) {
    throw new Error(parsed.detail || parsed.raw || "Request failed");
  }

  return parsed;
}

function getSection() {
  return document.getElementById("sectionSelect").value;
}

async function loadModels() {
  const select = document.getElementById("modelSelect");
  const status = document.getElementById("settingsStatus");
  select.innerHTML = "";

  try {
    const data = await api("/api/models");
    loadedModels = data.models || [];

    for (const m of loadedModels) {
      const opt = document.createElement("option");
      opt.value = m.name;
      opt.textContent = m.name;
      select.appendChild(opt);
    }

    const savedModel = localStorage.getItem("chat_model") || "qwen3:8b";
    if ([...select.options].some(o => o.value === savedModel)) {
      select.value = savedModel;
    }

    showModelInfo();
    status.textContent = `Loaded ${loadedModels.length} model(s).`;
  } catch (e) {
    status.textContent = "Failed to load models: " + e.message;
  }
}

function showModelInfo() {
  const current = document.getElementById("modelSelect").value;
  const info = loadedModels.find(m => m.name === current);
  document.getElementById("modelInfo").textContent =
    info ? `${info.name}\n\n${info.description}` : "No model information available.";
}

function loadSettingsFromStorage() {
  const savedModel = localStorage.getItem("chat_model");
  const savedPrompt = localStorage.getItem("chat_system_prompt");

  if (savedPrompt) {
    document.getElementById("systemPrompt").value = savedPrompt;
  }

  if (savedModel) {
    const select = document.getElementById("modelSelect");
    if ([...select.options].some(o => o.value === savedModel)) {
      select.value = savedModel;
    }
  }

  showModelInfo();
}

function saveSettings() {
  const model = document.getElementById("modelSelect").value;
  const prompt = document.getElementById("systemPrompt").value;
  localStorage.setItem("chat_model", model);
  localStorage.setItem("chat_system_prompt", prompt);
  document.getElementById("settingsStatus").textContent = `Saved settings. Active model: ${model}`;
}

async function loadFiles() {
  const list = document.getElementById("fileList");
  const status = document.getElementById("fileStatus");
  list.innerHTML = "";

  try {
    const data = await api(`/api/admin/files?section=${encodeURIComponent(getSection())}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      list.appendChild(opt);
    }
    status.textContent = `Loaded ${data.files.length} editable file(s) from ${getSection()}.`;
  } catch (e) {
    status.textContent = "Failed to load files: " + e.message;
  }
}

async function openSelectedFile() {
  const selected = document.getElementById("fileList").value;
  const status = document.getElementById("fileStatus");

  if (!selected) {
    status.textContent = "Select a file first.";
    return;
  }

  try {
    const data = await api("/api/admin/read", "POST", {
      section: getSection(),
      relative_path: selected
    });

    document.getElementById("filePath").value = data.path;
    document.getElementById("fileContent").value = data.content;
    status.textContent = `Opened ${data.path}`;
  } catch (e) {
    status.textContent = "Open failed: " + e.message;
  }
}

async function saveFile() {
  const path = document.getElementById("filePath").value;
  const content = document.getElementById("fileContent").value;
  const status = document.getElementById("fileStatus");

  try {
    const data = await api("/api/admin/save", "POST", {
      section: getSection(),
      relative_path: path,
      content: content
    });
    status.textContent = JSON.stringify(data, null, 2);
    await loadFiles();
    await loadBackups();
  } catch (e) {
    status.textContent = "Save failed: " + e.message;
  }
}

async function loadBackups() {
  const path = document.getElementById("filePath").value || document.getElementById("fileList").value;
  const list = document.getElementById("backupList");
  const status = document.getElementById("backupStatus");
  list.innerHTML = "";
  document.getElementById("backupPreview").textContent = "";

  if (!path) {
    status.textContent = "Select or open a file first.";
    return;
  }

  try {
    const data = await api(`/api/admin/backups?section=${encodeURIComponent(getSection())}&relative_path=${encodeURIComponent(path)}`);
    for (const backup of data.backups) {
      const opt = document.createElement("option");
      opt.value = backup;
      opt.textContent = backup;
      list.appendChild(opt);
    }
    status.textContent = `Loaded ${data.backups.length} backup(s) for ${path}`;
  } catch (e) {
    status.textContent = "Failed to load backups: " + e.message;
  }
}

async function readBackup() {
  const path = document.getElementById("filePath").value || document.getElementById("fileList").value;
  const backup = document.getElementById("backupList").value;
  const status = document.getElementById("backupStatus");
  const preview = document.getElementById("backupPreview");

  if (!path || !backup) {
    status.textContent = "Select a file and backup first.";
    return;
  }

  try {
    const data = await api(`/api/admin/backup/read?section=${encodeURIComponent(getSection())}&relative_path=${encodeURIComponent(path)}&backup_name=${encodeURIComponent(backup)}`);
    preview.textContent = data.content;
    status.textContent = `Previewing backup ${backup}`;
  } catch (e) {
    status.textContent = "Failed to read backup: " + e.message;
  }
}

async function rollbackFile() {
  const path = document.getElementById("filePath").value || document.getElementById("fileList").value;
  const backup = document.getElementById("backupList").value;
  const status = document.getElementById("backupStatus");

  if (!path || !backup) {
    status.textContent = "Select a file and backup first.";
    return;
  }

  try {
    const data = await api("/api/admin/rollback", "POST", {
      section: getSection(),
      relative_path: path,
      backup_name: backup
    });
    status.textContent = JSON.stringify(data, null, 2);
    await openSelectedFile();
    await loadBackups();
  } catch (e) {
    status.textContent = "Rollback failed: " + e.message;
  }
}

async function askImprove() {
  const file = document.getElementById("filePath").value || document.getElementById("fileList").value;
  const task = document.getElementById("improveTask").value;
  const model = document.getElementById("modelSelect").value;
  const status = document.getElementById("improveStatus");
  const preview = document.getElementById("improvePreview");

  if (!file) {
    status.textContent = "Select a file first.";
    return;
  }

  status.textContent = "Asking Ollama to improve website files...";
  preview.textContent = "";

  try {
    improveResult = await api("/api/admin/improve", "POST", {
      model: model,
      task: task,
      target_files: [file],
      section: getSection()
    });

    preview.textContent = JSON.stringify(improveResult, null, 2);
    status.textContent = improveResult.summary || "Improvement generated.";
  } catch (e) {
    status.textContent = "Improve request failed: " + e.message;
  }
}

async function applyImproveResult() {
  const status = document.getElementById("improveStatus");

  if (!improveResult || !improveResult.files) {
    status.textContent = "No improvement result to apply.";
    return;
  }

  try {
    for (const [path, content] of Object.entries(improveResult.files)) {
      await api("/api/admin/save", "POST", {
        section: getSection(),
        relative_path: path,
        content: content
      });
    }

    status.textContent = "Generated files applied successfully.";
    await loadFiles();
  } catch (e) {
    status.textContent = "Failed to apply generated files: " + e.message;
  }
}

async function loadSharedFolders() {
  const select = document.getElementById("sharedFolderSelect");
  const status = document.getElementById("sharedStatus");
  select.innerHTML = "";

  try {
    const data = await api("/api/admin/shared-folders");
    for (const folder of data.folders) {
      const opt = document.createElement("option");
      opt.value = folder;
      opt.textContent = folder;
      select.appendChild(opt);
    }
    status.textContent = `Loaded ${data.folders.length} shared folder(s).`;
    if (data.folders.length > 0) {
      await loadSharedFiles();
    }
  } catch (e) {
    status.textContent = "Failed to load shared folders: " + e.message;
  }
}

async function loadSharedFiles() {
  const folder = document.getElementById("sharedFolderSelect").value;
  const list = document.getElementById("sharedFileList");
  const status = document.getElementById("sharedStatus");
  list.innerHTML = "";
  document.getElementById("sharedPreview").textContent = "";

  if (!folder) {
    status.textContent = "Select a shared folder first.";
    return;
  }

  try {
    const data = await api(`/api/admin/shared-files?folder_name=${encodeURIComponent(folder)}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      list.appendChild(opt);
    }
    status.textContent = `Loaded ${data.files.length} shared file(s) from ${folder}.`;
  } catch (e) {
    status.textContent = "Failed to load shared files: " + e.message;
  }
}

async function openSharedFile() {
  const folder = document.getElementById("sharedFolderSelect").value;
  const file = document.getElementById("sharedFileList").value;
  const status = document.getElementById("sharedStatus");

  if (!folder || !file) {
    status.textContent = "Select a shared folder and file first.";
    return;
  }

  try {
    const data = await api("/api/admin/shared-read", "POST", {
      folder_name: folder,
      relative_path: file
    });
    document.getElementById("sharedPath").value = data.path;
    document.getElementById("sharedContent").value = data.content;
    status.textContent = `Opened shared file ${data.path}`;
  } catch (e) {
    status.textContent = "Failed to open shared file: " + e.message;
  }
}

async function saveSharedFile() {
  const folder = document.getElementById("sharedFolderSelect").value;
  const path = document.getElementById("sharedPath").value;
  const content = document.getElementById("sharedContent").value;
  const status = document.getElementById("sharedStatus");

  if (!folder || !path) {
    status.textContent = "Select a folder and file first.";
    return;
  }

  try {
    const data = await api("/api/admin/shared-save", "POST", {
      folder_name: folder,
      relative_path: path,
      content: content
    });
    status.textContent = JSON.stringify(data, null, 2);
    await loadSharedFiles();
  } catch (e) {
    status.textContent = "Failed to save shared file: " + e.message;
  }
}

async function askImproveShared() {
  const folder = document.getElementById("sharedFolderSelect").value;
  const file = document.getElementById("sharedPath").value || document.getElementById("sharedFileList").value;
  const task = document.getElementById("sharedTask").value;
  const model = document.getElementById("modelSelect").value;
  const status = document.getElementById("sharedStatus");
  const preview = document.getElementById("sharedPreview");

  if (!folder || !file) {
    status.textContent = "Select a shared folder and file first.";
    return;
  }

  status.textContent = "Asking Ollama to improve shared folder files...";
  preview.textContent = "";

  try {
    improveSharedResult = await api("/api/admin/shared-improve", "POST", {
      model: model,
      folder_name: folder,
      task: task,
      target_files: [file]
    });

    preview.textContent = JSON.stringify(improveSharedResult, null, 2);
    status.textContent = improveSharedResult.summary || "Shared-folder improvement generated.";
  } catch (e) {
    status.textContent = "Shared improve request failed: " + e.message;
  }
}

async function applyImproveShared() {
  const folder = document.getElementById("sharedFolderSelect").value;
  const status = document.getElementById("sharedStatus");

  if (!improveSharedResult || !improveSharedResult.files) {
    status.textContent = "No shared improvement result to apply.";
    return;
  }

  try {
    for (const [path, content] of Object.entries(improveSharedResult.files)) {
      await api("/api/admin/shared-save", "POST", {
        folder_name: folder,
        relative_path: path,
        content: content
      });
    }

    status.textContent = "Generated shared files applied successfully.";
    await loadSharedFiles();
  } catch (e) {
    status.textContent = "Failed to apply generated shared files: " + e.message;
  }
}


async function runGitSync() {
  const branch = document.getElementById("gitBranch").value.trim() || "dev";
  const message = document.getElementById("gitMessage").value.trim();
  const status = document.getElementById("gitStatus");

  status.textContent = `Syncing editable site to git branch ${branch}...`;

  try {
    const data = await api("/api/admin/git/sync", "POST", {
      branch,
      message: message || null
    });
    status.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    status.textContent = "Git sync failed: " + e.message;
  }
}

window.onload = async function () {
  await loadModels();
  loadSettingsFromStorage();
  await loadFiles();
  await loadSharedFolders();
};
