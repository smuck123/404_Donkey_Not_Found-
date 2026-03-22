let improveResult = null;
let improveRepoResult = null;
let loadedModels = [];

async function api(url, method = "GET", data = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (data) options.body = JSON.stringify(data);

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

function switchMode() {
  const mode = document.getElementById("modeSelect").value;
  document.querySelectorAll(".mode-panel").forEach(el => el.classList.add("hidden"));
  const panel = document.getElementById(`panel-${mode}`);
  if (panel) panel.classList.remove("hidden");
}

function repoNameFromUrl(url) {
  let name = (url || "").trim();
  if (!name) return "";
  name = name.replace(/\/+$/, "");
  name = name.split("/").pop() || "";
  if (name.endsWith(".git")) name = name.slice(0, -4);
  return name.replace(/[^A-Za-z0-9._-]/g, "_");
}

function suggestRepoName() {
  const url = document.getElementById("repoUrl").value;
  const name = repoNameFromUrl(url);
  if (name) document.getElementById("repoName").value = name;
}

function getSection() {
  return document.getElementById("sectionSelect").value;
}

function setOpenedFile(path) {
  document.getElementById("openedFileLabel").textContent = path || "None";
}

function setOpenedRepoFile(path) {
  document.getElementById("openedRepoFileLabel").textContent = path || "None";
}

function openCurrentPage() {
  const section = getSection();
  if (section === "chat") window.open("/", "_blank");
  if (section === "admin") window.open("/admin/", "_blank");
}

function fillGeneratedFileList(filesObject, elementId) {
  const list = document.getElementById(elementId);
  list.innerHTML = "";
  for (const path of Object.keys(filesObject || {})) {
    const opt = document.createElement("option");
    opt.value = path;
    opt.textContent = path;
    list.appendChild(opt);
  }
}

async function loadModels() {
  const select = document.getElementById("modelSelect");
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
    document.getElementById("settingsStatus").textContent = `Loaded ${loadedModels.length} model(s).`;
  } catch (e) {
    document.getElementById("settingsStatus").textContent = "Failed to load models: " + e.message;
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
  document.getElementById("settingsStatus").textContent = `Saved. Main chat now uses model: ${model}`;
}

async function loadFiles() {
  const list = document.getElementById("fileList");
  list.innerHTML = "";
  document.getElementById("filePath").value = "";
  document.getElementById("fileContent").value = "";
  setOpenedFile("");

  try {
    const data = await api(`/api/admin/files?section=${encodeURIComponent(getSection())}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      list.appendChild(opt);
    }
    document.getElementById("fileStatus").textContent = `Loaded ${data.files.length} file(s) from ${getSection()}.`;
  } catch (e) {
    document.getElementById("fileStatus").textContent = "Failed to load files: " + e.message;
  }
}

async function openSelectedFile() {
  const selected = document.getElementById("fileList").value;
  if (!selected) {
    document.getElementById("fileStatus").textContent = "Select a file first.";
    return;
  }

  try {
    const data = await api("/api/admin/read", "POST", {
      section: getSection(),
      relative_path: selected
    });

    document.getElementById("filePath").value = data.path;
    document.getElementById("fileContent").value = data.content;
    setOpenedFile(data.path);
    document.getElementById("fileStatus").textContent = `Opened ${data.path}`;
  } catch (e) {
    document.getElementById("fileStatus").textContent = "Open failed: " + e.message;
  }
}

async function saveFile() {
  const path = document.getElementById("filePath").value;
  const content = document.getElementById("fileContent").value;

  if (!path) {
    document.getElementById("fileStatus").textContent = "Open a file first.";
    return;
  }

  try {
    const data = await api("/api/admin/save", "POST", {
      section: getSection(),
      relative_path: path,
      content: content
    });
    document.getElementById("fileStatus").textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    document.getElementById("fileStatus").textContent = "Save failed: " + e.message;
  }
}

function previewGeneratedFile() {
  const selected = document.getElementById("generatedFileList").value;
  if (!improveResult || !improveResult.files || !selected) {
    document.getElementById("improvePreview").textContent = "";
    return;
  }
  document.getElementById("improvePreview").textContent = improveResult.files[selected];
  document.getElementById("improveStatus").textContent = `Previewing generated file: ${selected}`;
}

async function askImprove() {
  const file = document.getElementById("filePath").value;
  const task = document.getElementById("improveTask").value;
  const model = document.getElementById("modelSelect").value;

  if (!file) {
    document.getElementById("improveStatus").textContent = "Open a file first.";
    return;
  }

  document.getElementById("improveStatus").textContent = "Generating improved version...";
  document.getElementById("improvePreview").textContent = "";
  document.getElementById("generatedFileList").innerHTML = "";

  try {
    improveResult = await api("/api/admin/improve", "POST", {
      model: model,
      task: task,
      target_files: [file],
      section: getSection()
    });

    fillGeneratedFileList(improveResult.files || {}, "generatedFileList");
    const firstKey = Object.keys(improveResult.files || {})[0];
    if (firstKey) {
      document.getElementById("generatedFileList").value = firstKey;
      previewGeneratedFile();
    }

    document.getElementById("improveStatus").textContent = improveResult.summary || "Generated improved version.";
  } catch (e) {
    document.getElementById("improveStatus").textContent = "Improve failed: " + e.message;
  }
}

async function applySelectedGeneratedFile() {
  const selected = document.getElementById("generatedFileList").value;
  if (!improveResult || !improveResult.files || !selected) {
    document.getElementById("improveStatus").textContent = "Select a generated file first.";
    return;
  }

  try {
    await api("/api/admin/save", "POST", {
      section: getSection(),
      relative_path: selected,
      content: improveResult.files[selected]
    });

    if (selected === document.getElementById("filePath").value) {
      document.getElementById("fileContent").value = improveResult.files[selected];
    }

    document.getElementById("improveStatus").textContent = `Applied ${selected}`;
  } catch (e) {
    document.getElementById("improveStatus").textContent = "Apply failed: " + e.message;
  }
}

async function loadRepos() {
  const select = document.getElementById("repoSelect");
  select.innerHTML = "";
  try {
    const data = await api("/api/repo/list");
    for (const repo of data.repos) {
      const opt = document.createElement("option");
      opt.value = repo;
      opt.textContent = repo;
      select.appendChild(opt);
    }
    document.getElementById("repoStatus").textContent = `Loaded ${data.repos.length} repo(s).`;
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Failed to load repos: " + e.message;
  }
}

async function testRepoUrl() {
  const url = document.getElementById("repoUrl").value.trim();
  const name = document.getElementById("repoName").value.trim();

  if (!url) {
    document.getElementById("repoStatus").textContent = "Enter a repo URL first.";
    return;
  }

  try {
    const data = await api("/api/repo/test", "POST", {
      repo_url: url,
      repo_name: name || null
    });
    document.getElementById("repoStatus").textContent = `Repo URL is reachable: ${data.repo_url}`;
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Repo URL test failed: " + e.message;
  }
}

async function cloneRepo() {
  const repoUrl = document.getElementById("repoUrl").value.trim();
  let repoName = document.getElementById("repoName").value.trim();

  if (!repoUrl) {
    document.getElementById("repoStatus").textContent = "Enter a repo URL first.";
    return;
  }

  if (!repoName) {
    repoName = repoNameFromUrl(repoUrl);
    document.getElementById("repoName").value = repoName;
  }

  document.getElementById("repoStatus").textContent = "Cloning repository...";

  try {
    const data = await api("/api/repo/clone", "POST", {
      repo_url: repoUrl,
      repo_name: repoName || null
    });
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);
    await loadRepos();
    document.getElementById("repoSelect").value = data.repo_name;
    await loadRepoFiles();
  } catch (e) {
    document.getElementById("repoStatus").textContent =
      "Clone failed.\n\nCheck:\n- repo URL is correct\n- repo is public or server has access\n- git is installed\n\nError:\n" + e.message;
  }
}

async function pullRepo() {
  const repoName = document.getElementById("repoSelect").value;
  if (!repoName) {
    document.getElementById("repoStatus").textContent = "Select a repo first.";
    return;
  }

  try {
    const data = await api(`/api/repo/pull?repo_name=${encodeURIComponent(repoName)}`, "POST");
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);
    await loadRepoFiles();
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Pull failed: " + e.message;
  }
}

async function loadRepoFiles() {
  const repoName = document.getElementById("repoSelect").value;
  const list = document.getElementById("repoFileList");
  list.innerHTML = "";
  document.getElementById("repoPath").value = "";
  document.getElementById("repoContent").value = "";
  setOpenedRepoFile("");

  if (!repoName) {
    document.getElementById("repoStatus").textContent = "Select a repo first.";
    return;
  }

  try {
    const data = await api(`/api/repo/files?repo_name=${encodeURIComponent(repoName)}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      list.appendChild(opt);
    }
    document.getElementById("repoStatus").textContent = `Loaded ${data.files.length} repo file(s).`;
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Load repo files failed: " + e.message;
  }
}

async function openRepoFile() {
  const repoName = document.getElementById("repoSelect").value;
  const selectedFiles = getSelectedRepoFiles();
  const file = selectedFiles.length ? selectedFiles[0] : document.getElementById("repoFileList").value;

  if (!repoName || !file) {
    document.getElementById("repoStatus").textContent = "Select a repo file first.";
    return;
  }

  try {
    const data = await api("/api/repo/read", "POST", {
      repo_name: repoName,
      relative_path: file
    });
    document.getElementById("repoPath").value = data.path;
    document.getElementById("repoContent").value = data.content;
    setOpenedRepoFile(data.path);
    document.getElementById("repoStatus").textContent = `Opened repo file ${data.path}`;
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Open repo file failed: " + e.message;
  }
}

async function saveRepoFile() {
  const repoName = document.getElementById("repoSelect").value;
  const path = document.getElementById("repoPath").value;
  const content = document.getElementById("repoContent").value;

  if (!repoName || !path) {
    document.getElementById("repoStatus").textContent = "Open a repo file first.";
    return;
  }

  try {
    const data = await api("/api/repo/save", "POST", {
      repo_name: repoName,
      relative_path: path,
      content: content
    });
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Save repo file failed: " + e.message;
  }
}

function previewGeneratedRepoFile() {
  const selected = document.getElementById("generatedRepoFileList").value;
  if (!improveRepoResult || !improveRepoResult.files || !selected) {
    document.getElementById("repoImprovePreview").textContent = "";
    return;
  }
  document.getElementById("repoImprovePreview").textContent = improveRepoResult.files[selected];
  document.getElementById("repoStatus").textContent = `Previewing generated repo file: ${selected}`;
}

async function askImproveRepo() {
  const repoName = document.getElementById("repoSelect").value;
  const path = document.getElementById("repoPath").value;
  const task = document.getElementById("repoImproveTask").value;
  const model = document.getElementById("modelSelect").value;

  if (!repoName || !path) {
    document.getElementById("repoStatus").textContent = "Open a repo file first.";
    return;
  }

  document.getElementById("repoImprovePreview").textContent = "";
  document.getElementById("generatedRepoFileList").innerHTML = "";
  document.getElementById("repoStatus").textContent = "Generating improved repo file...";

  try {
    improveRepoResult = await api("/api/repo/improve", "POST", {
      model: model,
      repo_name: repoName,
      task: task,
      target_files: [path]
    });

    fillGeneratedFileList(improveRepoResult.files || {}, "generatedRepoFileList");
    const firstKey = Object.keys(improveRepoResult.files || {})[0];
    if (firstKey) {
      document.getElementById("generatedRepoFileList").value = firstKey;
      previewGeneratedRepoFile();
    }

    document.getElementById("repoStatus").textContent = improveRepoResult.summary || "Generated improved repo file.";
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Improve repo file failed: " + e.message;
  }
}

async function applySelectedGeneratedRepoFile() {
  const repoName = document.getElementById("repoSelect").value;
  const selected = document.getElementById("generatedRepoFileList").value;

  if (!repoName || !improveRepoResult || !improveRepoResult.files || !selected) {
    document.getElementById("repoStatus").textContent = "Select a generated repo file first.";
    return;
  }

  try {
    await api("/api/repo/save", "POST", {
      repo_name: repoName,
      relative_path: selected,
      content: improveRepoResult.files[selected]
    });

    if (selected === document.getElementById("repoPath").value) {
      document.getElementById("repoContent").value = improveRepoResult.files[selected];
    }

    document.getElementById("repoStatus").textContent = `Applied ${selected}`;
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Apply repo file failed: " + e.message;
  }
}

async function applyImproveRepo() {
  const repoName = document.getElementById("repoSelect").value;

  if (!repoName || !improveRepoResult || !improveRepoResult.files) {
    document.getElementById("repoStatus").textContent = "Nothing to apply.";
    return;
  }

  try {
    for (const [path, content] of Object.entries(improveRepoResult.files)) {
      await api("/api/repo/save", "POST", {
        repo_name: repoName,
        relative_path: path,
        content: content
      });
    }
    document.getElementById("repoStatus").textContent = "Applied all generated repo files.";
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Apply all repo files failed: " + e.message;
  }
}

async function fetchWebPage() {
  const url = document.getElementById("webUrl").value.trim();
  if (!url) {
    document.getElementById("webStatus").textContent = "Enter a URL first.";
    return;
  }

  try {
    const data = await api("/api/web/fetch", "POST", { url });
    document.getElementById("webContent").value = data.content;
    document.getElementById("webStatus").textContent = `Fetched: ${data.title}`;
  } catch (e) {
    document.getElementById("webStatus").textContent = "Fetch failed: " + e.message;
  }
}

async function summarizeWebPage() {
  const url = document.getElementById("webUrl").value.trim();
  const model = document.getElementById("modelSelect").value;

  if (!url) {
    document.getElementById("webStatus").textContent = "Enter a URL first.";
    return;
  }

  try {
    const data = await api("/api/web/summarize", "POST", {
      model: model,
      url: url,
      task: "Summarize this page and explain the useful parts for Zabbix modules and templates."
    });
    document.getElementById("webContent").value = data.summary;
    document.getElementById("webStatus").textContent = `Summarized: ${data.title}`;
  } catch (e) {
    document.getElementById("webStatus").textContent = "Summarize failed: " + e.message;
  }
}

async function summarizeText() {
  const model = document.getElementById("modelSelect").value;
  const text = document.getElementById("summaryInput").value;
  const task = document.getElementById("summaryTask").value;

  if (!text.trim()) {
    document.getElementById("summaryStatus").textContent = "Paste some text first.";
    return;
  }

  try {
    const data = await api("/api/text/summarize", "POST", {
      model: model,
      text: text,
      task: task
    });
    document.getElementById("summaryOutput").value = data.summary;
    document.getElementById("summaryStatus").textContent = "Summary created.";
  } catch (e) {
    document.getElementById("summaryStatus").textContent = "Summarize failed: " + e.message;
  }
}

window.onload = async function () {
  await loadModels();
  loadSettingsFromStorage();
  await loadFiles();
  await loadRepos();
  await loadRepoTemplates();
  switchMode();
};


async function deleteRepo() {
  const repoName = document.getElementById("repoSelect").value;

  if (!repoName) {
    document.getElementById("repoStatus").textContent = "Select a repo first.";
    return;
  }

  const ok = confirm(`Delete repo "${repoName}" from local server?`);
  if (!ok) return;

  try {
    const data = await api(`/api/repo/delete?repo_name=${encodeURIComponent(repoName)}`, "POST");
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);

    document.getElementById("repoPath").value = "";
    document.getElementById("repoContent").value = "";
    document.getElementById("repoFileList").innerHTML = "";
    document.getElementById("generatedRepoFileList").innerHTML = "";
    document.getElementById("repoImprovePreview").textContent = "";
    setOpenedRepoFile("");

    await loadRepos();
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Delete failed: " + e.message;
  }
}



function getSelectedRepoFiles() {
  return Array.from(document.getElementById("repoFileList").selectedOptions).map(o => o.value);
}

function selectAllRepoFiles() {
  const list = document.getElementById("repoFileList");
  for (const opt of list.options) {
    opt.selected = true;
  }
  document.getElementById("repoStatus").textContent = `Selected ${list.options.length} repo file(s).`;
}

function clearRepoFileSelection() {
  const list = document.getElementById("repoFileList");
  for (const opt of list.options) {
    opt.selected = false;
  }
  document.getElementById("repoStatus").textContent = "Cleared repo file selection.";
}

async function saveRepoTemplate() {
  const repoName = document.getElementById("repoSelect").value;
  const templateName = document.getElementById("repoTemplateName").value.trim();
  const selectedFiles = getSelectedRepoFiles();

  if (!repoName) {
    document.getElementById("repoStatus").textContent = "Select a repo first.";
    return;
  }

  if (!templateName) {
    document.getElementById("repoStatus").textContent = "Write a template name first.";
    return;
  }

  try {
    const data = await api("/api/repo/template/save", "POST", {
      repo_name: repoName,
      template_name: templateName,
      selected_files: selectedFiles
    });
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);
    await loadRepoTemplates();
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Save template failed: " + e.message;
  }
}

async function loadRepoTemplates() {
  const list = document.getElementById("repoTemplateList");
  if (!list) return;
  list.innerHTML = "";

  try {
    const data = await api("/api/repo/templates");
    for (const t of data.templates) {
      const opt = document.createElement("option");
      opt.value = t.template_name;
      opt.textContent = `${t.template_name} (${t.file_count} files)`;
      list.appendChild(opt);
    }
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Load templates failed: " + e.message;
  }
}

async function deleteRepoTemplate() {
  const list = document.getElementById("repoTemplateList");
  if (!list || !list.value) {
    document.getElementById("repoStatus").textContent = "Select a saved template first.";
    return;
  }

  const templateName = list.value;
  const ok = confirm(`Delete saved template "${templateName}"?`);
  if (!ok) return;

  try {
    const data = await api("/api/repo/template/delete", "POST", {
      template_name: templateName
    });
    document.getElementById("repoStatus").textContent = JSON.stringify(data, null, 2);
    await loadRepoTemplates();
  } catch (e) {
    document.getElementById("repoStatus").textContent = "Delete template failed: " + e.message;
  }
}
