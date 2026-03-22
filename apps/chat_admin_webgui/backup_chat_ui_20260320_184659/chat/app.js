let chatHistory = [];
let activeModel = "qwen3:8b";
let systemPrompt = "You are a helpful assistant for Linux, Bash, Python, web development, Ansible, Zabbix, and server administration.";
let activeProject = "General";
let activeTemplate = "";
let activeTemplatePreview = "";
let savedChats = [];
let savedProjects = [];
let savedRepoTemplates = [];
let selectedChatId = "";

async function api(url, method = "GET", data = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" }
  };

  if (data !== null) {
    opts.body = JSON.stringify(data);
  }

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
  div.textContent = text;
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
  if (!allProjects.includes(activeProject)) {
    activeProject = allProjects[0];
  }

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

function renderProjects() {
  const box = document.getElementById("projectsList");
  if (savedProjects.length === 0) {
    box.innerHTML = `<div class="sidebar-empty">No projects yet</div>`;
    return;
  }

  box.innerHTML = savedProjects.map(name => `
    <button class="sidebar-item ${name === activeProject ? "active" : ""}" onclick="selectProject(${JSON.stringify(name)})">${escapeHtml(name)}</button>
  `).join("");
}

function renderChats() {
  const box = document.getElementById("chatsList");
  if (savedChats.length === 0) {
    box.innerHTML = `<div class="sidebar-empty">No saved chats yet</div>`;
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
    box.innerHTML = `<div class="sidebar-empty">No saved templates yet</div>`;
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
        <p>Use saved templates as context when asking for Zabbix widgets, modules, or templates.</p>
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

function selectProject(name) {
  activeProject = name;
  document.getElementById("activeProjectLabel").textContent = `Project: ${name}`;
  renderProjects();
  renderProjectSelect();
}

function changeProjectFromSelect() {
  const value = document.getElementById("projectSelect").value;
  selectProject(value);
}

async function selectTemplate(templateName) {
  activeTemplate = templateName;
  document.getElementById("activeTemplateLabel").textContent = `Template: ${templateName || "None"}`;
  renderRepoTemplates();
  renderTemplateSelect();
  await loadTemplateContext();
}

async function changeTemplateContext() {
  activeTemplate = document.getElementById("templateSelect").value;
  document.getElementById("activeTemplateLabel").textContent = `Template: ${activeTemplate || "None"}`;
  renderRepoTemplates();
  await loadTemplateContext();
}

async function loadTemplateContext() {
  activeTemplatePreview = "";

  if (!activeTemplate) {
    setStatus("Template context cleared.");
    return;
  }

  try {
    const data = await api(`/api/chat/repo-template/files?template_name=${encodeURIComponent(activeTemplate)}`);
    const previewParts = [];
    for (const item of (data.previews || []).slice(0, 12)) {
      previewParts.push(`--- FILE: ${item.path} ---\n${item.content}`);
    }
    activeTemplatePreview = previewParts.join("\n\n");
    setStatus(`Loaded template context: ${activeTemplate}`);
  } catch (err) {
    setStatus("Failed to load template context: " + err.message);
  }
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
  document.getElementById("chatTitle").value = "";
  renderChat();
  setStatus("Started new chat.");
}

async function loadState() {
  const data = await api("/api/chat/state");
  const templateData = await api("/api/chat/repo-templates");
  savedProjects = data.projects || [];
  savedChats = data.chats || [];
  savedRepoTemplates = templateData.templates || [];

  document.getElementById("mainBrand").textContent = data.brand || "404DonkeyNotFound";
  document.getElementById("mainSlogan").textContent = data.slogan || "if it works, make sure donkey can break IT!";

  if (!savedProjects.includes(activeProject)) {
    activeProject = savedProjects.length ? savedProjects[0] : "General";
  }

  renderProjects();
  renderChats();
  renderRepoTemplates();
  renderProjectSelect();
  renderTemplateSelect();
}

async function saveCurrentChat() {
  const titleInput = document.getElementById("chatTitle");
  const title = titleInput.value.trim() || `Chat ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;

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
    titleInput.value = title;
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
    document.getElementById("chatTitle").value = data.title || "";
    document.getElementById("activeProjectLabel").textContent = `Project: ${activeProject}`;
    document.getElementById("activeModelLabel").textContent = `Model: ${data.model || activeModel}`;
    renderProjects();
    renderChats();
    renderProjectSelect();
    renderChat();
    setStatus(`Loaded saved chat: ${data.title}`);
  } catch (err) {
    setStatus("Failed to load saved chat: " + err.message);
  }
}

async function deleteSelectedChat() {
  if (!selectedChatId) {
    setStatus("Select a saved chat first.");
    return;
  }

  const ok = confirm("Delete selected chat?");
  if (!ok) return;

  try {
    await api(`/api/chat/session/delete?chat_id=${encodeURIComponent(selectedChatId)}`, "POST");
    if (selectedChatId) {
      chatHistory = [];
      document.getElementById("chatTitle").value = "";
    }
    selectedChatId = "";
    await loadState();
    renderChat();
    setStatus("Chat deleted.");
  } catch (err) {
    setStatus("Failed to delete chat: " + err.message);
  }
}

async function deleteSelectedProject() {
  if (!activeProject) {
    setStatus("Select a project first.");
    return;
  }

  const ok = confirm(`Delete project "${activeProject}"?`);
  if (!ok) return;

  try {
    await api("/api/chat/project/delete", "POST", { name: activeProject });
    activeProject = "General";
    await loadState();
    setStatus("Project deleted.");
  } catch (err) {
    setStatus("Failed to delete project: " + err.message);
  }
}

async function sendMessage() {
  const messageBox = document.getElementById("message");
  const userText = messageBox.value.trim();

  if (!userText) {
    setStatus("Write a message first.");
    return;
  }

  loadLocalSettings();

  let contextualSystemPrompt = systemPrompt;
  if (activeTemplate && activeTemplatePreview) {
    contextualSystemPrompt += `

Use this saved template context when useful for analysis, Zabbix widget creation, Zabbix module work, or template modification.

TEMPLATE NAME:
${activeTemplate}

TEMPLATE CONTENT PREVIEW:
${activeTemplatePreview}`;
  }

  const messages = [];
  if (contextualSystemPrompt) {
    messages.push({ role: "system", content: contextualSystemPrompt });
  }

  for (const msg of chatHistory) {
    messages.push({ role: msg.role, content: msg.content });
  }

  messages.push({ role: "user", content: userText });

  chatHistory.push({ role: "user", content: userText });
  renderChat();
  messageBox.value = "";
  setStatus(`Sending to ${activeModel}...`);

  try {
    const data = await api("/api/chat/messages/retrieval", "POST", {
      model: activeModel,
      messages: messages,
      stream: false,
      use_retrieval: true,
      selected_template: activeTemplate || null,
      selected_repo: activeRepo || null,
      selected_template: activeTemplate || null
    });

    let answer =
      data.message?.content ||
      data.response ||
      JSON.stringify(data, null, 2);

    if (data.retrieved && data.retrieved.length > 0) {
      answer += "\n\nSources used:\n" + data.retrieved.map(
        s => `- [${s.source_type}] ${s.path} (score: ${typeof s.score === "number" ? s.score.toFixed(3) : s.score})`
      ).join("\n");
    }

    chatHistory.push({ role: "assistant", content: answer });
    renderChat();
    setStatus(`Reply received from ${activeModel}.`);
  } catch (err) {
    chatHistory.push({ role: "assistant", content: "Error: " + err.message });
    renderChat();
    setStatus("Chat failed: " + err.message);
  }
}

window.onload = async function () {
  loadLocalSettings();
  renderChat();
  await loadState();
  setStatus(`Ready. Active model: ${activeModel}`);
};
