let chatHistory = [];
let activeModel = "qwen3:8b";
let systemPrompt = "You are a helpful assistant.";
let activeProject = "General";
let activeTemplate = "";
let activeRepo = "";
let savedChats = [];
let savedProjects = [];
let savedRepoTemplates = [];
let savedRepos = [];
let selectedChatId = "";
let lastRetrieved = [];
let lastPlannedChanges = null;

async function api(url, method = "GET", data = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (data !== null) opts.body = JSON.stringify(data);
  const res = await fetch(url, opts);
  const text = await res.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = { raw: text };
  }
  if (!res.ok) {
    throw new Error(payload.detail || payload.raw || `HTTP ${res.status}`);
  }
  return payload;
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function loadLocalSettings() {
  const model = localStorage.getItem("chat_model");
  const prompt = localStorage.getItem("chat_system_prompt");
  if (model) activeModel = model;
  if (prompt) systemPrompt = prompt;
  document.getElementById("activeModelLabel").textContent = `Model: ${activeModel}`;
}

function renderProjectSelect() {
  const select = document.getElementById("projectSelect");
  select.innerHTML = "";
  const allProjects = savedProjects.length ? savedProjects : ["General"];
  if (!allProjects.includes(activeProject)) activeProject = allProjects[0];
  for (const name of allProjects) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    if (name === activeProject) opt.selected = true;
    select.appendChild(opt);
  }
  document.getElementById("activeProjectLabel").textContent = `Project: ${activeProject}`;
}

function renderTemplateSelect() {
  const select = document.getElementById("templateSelect");
  select.innerHTML = '<option value="">None</option>';
  for (const t of savedRepoTemplates) {
    const opt = document.createElement("option");
    opt.value = t.template_name;
    opt.textContent = `${t.template_name} (${t.file_count} files)`;
    if (t.template_name === activeTemplate) opt.selected = true;
    select.appendChild(opt);
  }
  document.getElementById("activeTemplateLabel").textContent = `Template: ${activeTemplate || "None"}`;
}

function renderRepoSelect() {
  const select = document.getElementById("repoSelect");
  select.innerHTML = '<option value="">None</option>';
  for (const repo of savedRepos) {
    const opt = document.createElement("option");
    opt.value = repo;
    opt.textContent = repo;
    if (repo === activeRepo) opt.selected = true;
    select.appendChild(opt);
  }
  document.getElementById("activeRepoLabel").textContent = `Repo: ${activeRepo || "None"}`;
}

function renderProjects() {
  const box = document.getElementById("projectsList");
  if (savedProjects.length === 0) {
    box.innerHTML = '<div class="item-meta">No projects yet</div>';
    return;
  }
  box.innerHTML = savedProjects.map(name => `
    <button class="sidebar-item ${name === activeProject ? "active" : ""}" onclick="selectProject(${JSON.stringify(name)})">${escapeHtml(name)}</button>
  `).join("");
}

function renderChats() {
  const box = document.getElementById("chatsList");
  if (savedChats.length === 0) {
    box.innerHTML = '<div class="item-meta">No saved chats yet</div>';
    return;
  }
  box.innerHTML = savedChats.map(chat => `
    <button class="sidebar-item ${chat.id === selectedChatId ? "active" : ""}" onclick="loadSavedChat(${JSON.stringify(chat.id)})">
      <div class="item-title">${escapeHtml(chat.title)}</div>
      <div class="item-meta">${escapeHtml(chat.project)} • ${escapeHtml(chat.model)}</div>
    </button>
  `).join("");
}

function renderRepoTemplates() {
  const box = document.getElementById("repoTemplatesList");
  if (savedRepoTemplates.length === 0) {
    box.innerHTML = '<div class="item-meta">No saved templates yet</div>';
    return;
  }
  box.innerHTML = savedRepoTemplates.map(t => `
    <button class="sidebar-item ${t.template_name === activeTemplate ? "active" : ""}" onclick="selectTemplate(${JSON.stringify(t.template_name)})">
      <div class="item-title">${escapeHtml(t.template_name)}</div>
      <div class="item-meta">${escapeHtml(t.repo_name)} • ${escapeHtml(String(t.file_count))} files</div>
    </button>
  `).join("");
}

function renderChat() {
  const box = document.getElementById("chatBox");
  if (chatHistory.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <h2>How can donkey help today?</h2>
        <p>Select a template and repo for smarter Zabbix widget/module work.</p>
      </div>
    `;
    return;
  }

  box.innerHTML = chatHistory.map(msg => `
    <div class="message ${msg.role}">
      <div class="message-role">${escapeHtml(msg.role)}</div>
      <div class="message-content">${escapeHtml(msg.content).replace(/\n/g, "<br>")}</div>
    </div>
  `).join("");
  box.scrollTop = box.scrollHeight;
}

function renderSources() {
  const box = document.getElementById("sourcesList");
  if (!lastRetrieved || lastRetrieved.length === 0) {
    box.innerHTML = '<div class="item-meta">No sources yet</div>';
    return;
  }

  box.innerHTML = lastRetrieved.map((s, idx) => `
    <button class="sidebar-item" onclick="openSourceByIndex(${idx})">
      <div class="item-title">[${escapeHtml(s.source_type || "source")}] ${escapeHtml(s.path || "")}</div>
      <div class="item-meta">score: ${typeof s.score === "number" ? s.score.toFixed(3) : escapeHtml(String(s.score ?? ""))}</div>
    </button>
  `).join("");
}

function renderPlannedChanges() {
  const box = document.getElementById("changeFilesList");
  if (!lastPlannedChanges || !lastPlannedChanges.files) {
    box.innerHTML = '<div class="item-meta">No proposed changes yet</div>';
    document.getElementById("diffViewer").textContent = "";
    document.getElementById("diffMeta").textContent = "No diff selected";
    return;
  }

  const files = Object.keys(lastPlannedChanges.files);
  box.innerHTML = files.map((path, idx) => `
    <button class="sidebar-item" onclick="showDiff(${idx})">
      <div class="item-title">${escapeHtml(path)}</div>
      <div class="item-meta">Click to preview diff</div>
    </button>
  `).join("");
}

function showDiff(index) {
  if (!lastPlannedChanges) return;
  const files = Object.keys(lastPlannedChanges.files);
  const path = files[index];
  document.getElementById("diffMeta").textContent = path;
  document.getElementById("diffViewer").textContent = lastPlannedChanges.diffs?.[path] || lastPlannedChanges.files[path] || "";
}

async function openSourceByIndex(index) {
  const item = lastRetrieved[index];
  if (!item) return;

  let params = new URLSearchParams({
    source_type: item.source_type || "",
    path: item.path || ""
  });

  if (item.source_type === "repo" && activeRepo) params.set("repo_name", activeRepo);
  if (item.source_type === "template" && activeTemplate) params.set("template_name", activeTemplate);
  if (item.source_type === "website") params.set("section", "chat");

  try {
    const data = await api(`/api/chat/source/view?${params.toString()}`);
    document.getElementById("sourceMeta").textContent = `${data.source_type}: ${data.path}`;
    document.getElementById("sourceViewer").textContent = data.content;
  } catch (err) {
    setStatus("Failed to open source: " + err.message);
  }
}

function selectProject(name) {
  activeProject = name;
  renderProjects();
  renderProjectSelect();
}

function changeProjectFromSelect() {
  activeProject = document.getElementById("projectSelect").value;
  renderProjects();
  renderProjectSelect();
}

async function selectTemplate(name) {
  activeTemplate = name;
  renderRepoTemplates();
  renderTemplateSelect();
}

async function changeTemplateContext() {
  activeTemplate = document.getElementById("templateSelect").value;
  renderRepoTemplates();
  renderTemplateSelect();
}

function changeRepoContext() {
  activeRepo = document.getElementById("repoSelect").value;
  renderRepoSelect();
}

function clearChat() {
  chatHistory = [];
  selectedChatId = "";
  renderChat();
  setStatus("Chat cleared.");
}

function newChat() {
  chatHistory = [];
  selectedChatId = "";
  renderChat();
  setStatus("Started new chat.");
}

async function loadState() {
  const data = await api("/api/chat/state");
  const templateData = await api("/api/chat/repo-templates");
  const repoData = await api("/api/repo/list");

  savedProjects = data.projects || [];
  savedChats = data.chats || [];
  savedRepoTemplates = templateData.templates || [];
  savedRepos = repoData.repos || [];

  document.getElementById("mainBrand").textContent = data.brand || "404DonkeyNotFound";
  document.getElementById("mainSlogan").textContent = data.slogan || "if it works, make sure donkey can break IT!";

  if (!savedProjects.includes(activeProject)) activeProject = savedProjects.length ? savedProjects[0] : "General";
  if (activeRepo && !savedRepos.includes(activeRepo)) activeRepo = "";
  if (activeTemplate && !savedRepoTemplates.some(x => x.template_name === activeTemplate)) activeTemplate = "";

  renderProjects();
  renderChats();
  renderRepoTemplates();
  renderProjectSelect();
  renderTemplateSelect();
  renderRepoSelect();
  renderSources();
  renderPlannedChanges();
}

async function saveCurrentChat() {
  const title = `Chat ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
  if (chatHistory.length === 0) {
    setStatus("Chat is empty.");
    return;
  }
  try {
    await api("/api/chat/session/save", "POST", {
      title,
      project: activeProject || "General",
      messages: chatHistory,
      model: activeModel
    });
    await loadState();
    setStatus(`Chat saved as "${title}"`);
  } catch (err) {
    setStatus("Failed to save chat: " + err.message);
  }
}

async function loadSavedChat(chatId) {
  try {
    const data = await api(`/api/chat/session/read?chat_id=${encodeURIComponent(chatId)}`);
    chatHistory = data.messages || [];
    activeProject = data.project || "General";
    selectedChatId = chatId;
    renderProjects();
    renderChats();
    renderProjectSelect();
    renderChat();
    setStatus(`Loaded saved chat: ${data.title}`);
  } catch (err) {
    setStatus("Failed to load saved chat: " + err.message);
  }
}

function buildSourceTypes() {
  const mode = document.getElementById("modeSelect").value;
  if (mode === "template") return ["template"];
  if (mode === "repo") return ["repo"];
  if (mode === "website") return ["website"];
  return null;
}

async function sendMessage() {
  const messageBox = document.getElementById("message");
  const userText = messageBox.value.trim();
  if (!userText) {
    setStatus("Write a message first.");
    return;
  }

  loadLocalSettings();
  const sourceTypes = buildSourceTypes();

  chatHistory.push({ role: "user", content: userText });
  renderChat();
  messageBox.value = "";
  setStatus(`Sending to ${activeModel}...`);

  try {
    const data = await api("/api/chat/messages/retrieval", "POST", {
      model: activeModel,
      messages: chatHistory,
      stream: false,
      use_retrieval: true,
      selected_template: activeTemplate || null,
      selected_repo: activeRepo || null,
      source_types: sourceTypes
    });

    let answer = data.message?.content || "";
    if (data.retrieved && data.retrieved.length > 0) {
      answer += "\n\nSources used:\n" + data.retrieved.map(
        s => `- [${s.source_type}] ${s.path} (score: ${typeof s.score === "number" ? s.score.toFixed(3) : s.score})`
      ).join("\n");
    }

    lastRetrieved = data.retrieved || [];
    chatHistory.push({ role: "assistant", content: answer });
    renderSources();
    renderChat();
    setStatus(`Reply received from ${activeModel}.`);
  } catch (err) {
    chatHistory.push({ role: "assistant", content: "Error: " + err.message });
    renderChat();
    setStatus("Chat failed: " + err.message);
  }
}

async function proposeChanges() {
  const instruction = document.getElementById("message").value.trim();
  if (!instruction) {
    setStatus("Write what you want to change first.");
    return;
  }
  if (!activeRepo) {
    setStatus("Select a repo first.");
    return;
  }

  setStatus("Asking AI to propose changes...");

  try {
    const data = await api("/api/chat/edit/plan", "POST", {
      model: activeModel,
      instruction,
      selected_template: activeTemplate || null,
      selected_repo: activeRepo || null
    });
    lastPlannedChanges = data;
    renderPlannedChanges();
    const firstPath = Object.keys(data.files || {})[0];
    if (firstPath) {
      document.getElementById("diffMeta").textContent = firstPath;
      document.getElementById("diffViewer").textContent = data.diffs?.[firstPath] || "";
    }
    setStatus(data.summary || "Proposed changes ready.");
  } catch (err) {
    setStatus("Change planning failed: " + err.message);
  }
}

async function applyPlannedChanges() {
  if (!activeRepo) {
    setStatus("Select a repo first.");
    return;
  }
  if (!lastPlannedChanges || !lastPlannedChanges.files) {
    setStatus("No proposed changes to apply.");
    return;
  }

  try {
    const data = await api("/api/chat/edit/apply", "POST", {
      repo_name: activeRepo,
      files: lastPlannedChanges.files
    });
    setStatus(`Applied changes: ${(data.changed_files || []).join(", ")}`);
  } catch (err) {
    setStatus("Apply failed: " + err.message);
  }
}

async function showGitStatus() {
  if (!activeRepo) {
    setStatus("Select a repo first.");
    return;
  }
  try {
    const data = await api(`/api/repo/git/status?repo_name=${encodeURIComponent(activeRepo)}`);
    document.getElementById("sourceMeta").textContent = `git status: ${activeRepo}`;
    document.getElementById("sourceViewer").textContent = data.status || "(clean)";
    setStatus("Git status loaded.");
  } catch (err) {
    setStatus("Git status failed: " + err.message);
  }
}

async function commitAndPush() {
  if (!activeRepo) {
    setStatus("Select a repo first.");
    return;
  }

  const msg = prompt("Commit message:", "AI update");
  if (!msg) return;

  const branch = prompt("Branch to use (blank = current branch):", "") || null;
  const doPush = confirm("Push to origin after commit?");

  try {
    const data = await api("/api/repo/git/commit-push", "POST", {
      repo_name: activeRepo,
      commit_message: msg,
      branch: branch,
      push: doPush
    });
    document.getElementById("sourceMeta").textContent = `git output: ${activeRepo}`;
    document.getElementById("sourceViewer").textContent =
      `COMMIT OUTPUT:\n${data.commit_output || ""}\n\nPUSH OUTPUT:\n${data.push_output || ""}`;
    setStatus("Commit/push completed.");
  } catch (err) {
    setStatus("Commit/push failed: " + err.message);
  }
}

window.onload = async function () {
  loadLocalSettings();
  renderChat();
  await loadState();
  setStatus(`Ready. Active model: ${activeModel}`);
};
