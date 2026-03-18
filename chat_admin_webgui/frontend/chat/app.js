let chatHistory = [];
let activeModel = "qwen3:8b";
let systemPrompt = "You are a helpful assistant for Linux, Bash, Python, web development, Ansible, Zabbix, and server administration.";
let activeProject = "General";
let savedChats = [];
let savedProjects = [];
let selectedChatId = null;

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

function renderProjects() {
  const box = document.getElementById("projectsList");
  if (savedProjects.length === 0) {
    box.innerHTML = `<div class="sidebar-empty">No projects yet</div>`;
    return;
  }

  box.innerHTML = savedProjects.map(name => `
    <div class="sidebar-entry">
      <button class="sidebar-item ${name === activeProject ? "active" : ""}" onclick="selectProject(${JSON.stringify(name)})">${escapeHtml(name)}</button>
      <button class="danger-icon" onclick="deleteProject(${JSON.stringify(name)})" title="Delete project">×</button>
    </div>
  `).join("");
}

function renderChats() {
  const box = document.getElementById("chatsList");
  if (savedChats.length === 0) {
    box.innerHTML = `<div class="sidebar-empty">No saved chats yet</div>`;
    return;
  }

  box.innerHTML = savedChats.map(chat => `
    <div class="sidebar-entry">
      <button class="sidebar-item ${chat.id === selectedChatId ? "active" : ""}" onclick="loadSavedChat(${JSON.stringify(chat.id)})">
        <div class="item-title">${escapeHtml(chat.title)}</div>
        <div class="item-meta">${escapeHtml(chat.project)} • ${escapeHtml(chat.model)}</div>
      </button>
      <button class="danger-icon" onclick="deleteChat(${JSON.stringify(chat.id)})" title="Delete chat">×</button>
    </div>
  `).join("");
}

function renderChat() {
  const box = document.getElementById("chatBox");

  if (chatHistory.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <h2>How can donkey help today?</h2>
        <p>Save projects and chats in the left sidebar so they stay remembered.</p>
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
  document.getElementById("projectName").value = name;
  document.getElementById("activeProjectLabel").textContent = `Project: ${name}`;
  renderProjects();
}

function clearChat() {
  chatHistory = [];
  selectedChatId = null;
  renderChat();
  renderChats();
  setStatus("Chat cleared.");
}

function newChat() {
  chatHistory = [];
  selectedChatId = null;
  document.getElementById("chatTitle").value = "";
  renderChat();
  renderChats();
  setStatus("Started new chat.");
}

async function loadState() {
  const data = await api("/api/chat/state");
  savedProjects = data.projects || [];
  savedChats = data.chats || [];

  document.getElementById("mainBrand").textContent = data.brand || "404DonkeyNotFound";
  document.getElementById("mainSlogan").textContent = data.slogan || "if it works, make sure donkey can break IT!";

  const storage = data.storage || {};
  document.getElementById("storagePathLabel").textContent = storage.projects_file
    ? `Storage: ${storage.projects_file}`
    : "Storage: unavailable";

  if (!savedProjects.includes(activeProject) && savedProjects.length > 0) {
    activeProject = savedProjects[0];
  }

  document.getElementById("activeProjectLabel").textContent = `Project: ${activeProject}`;
  renderProjects();
  renderChats();
}

async function saveProject() {
  const name = document.getElementById("projectName").value.trim();
  if (!name) {
    setStatus("Write a project name first.");
    return;
  }

  try {
    await api("/api/chat/project/save", "POST", { name });
    activeProject = name;
    await loadState();
    setStatus(`Project saved: ${name}`);
  } catch (err) {
    setStatus("Failed to save project: " + err.message);
  }
}

async function deleteProject(name) {
  const ok = window.confirm(`Delete project \"${name}\" and all chats in it?`);
  if (!ok) return;

  try {
    await api("/api/chat/project/delete", "POST", { name });
    if (activeProject === name) {
      activeProject = "General";
    }
    if (selectedChatId && !savedChats.some(chat => chat.id === selectedChatId && chat.project !== name)) {
      newChat();
    }
    await loadState();
    setStatus(`Project deleted: ${name}`);
  } catch (err) {
    setStatus("Failed to delete project: " + err.message);
  }
}

async function saveCurrentChat() {
  const title = document.getElementById("chatTitle").value.trim();
  if (!title) {
    setStatus("Write a chat name first.");
    return;
  }

  if (chatHistory.length === 0) {
    setStatus("Chat is empty.");
    return;
  }

  try {
    const result = await api("/api/chat/session/save", "POST", {
      title,
      project: activeProject || "General",
      messages: chatHistory,
      model: activeModel
    });
    selectedChatId = result.chat_id || null;
    await loadState();
    setStatus(`Chat saved as \"${title}\"`);
  } catch (err) {
    setStatus("Failed to save chat: " + err.message);
  }
}

async function deleteChat(chatId) {
  const ok = window.confirm("Delete this saved chat?");
  if (!ok) return;

  try {
    await api("/api/chat/session/delete", "POST", { chat_id: chatId });
    if (selectedChatId === chatId) {
      newChat();
    }
    await loadState();
    setStatus("Saved chat deleted.");
  } catch (err) {
    setStatus("Failed to delete chat: " + err.message);
  }
}

async function loadSavedChat(chatId) {
  try {
    const data = await api(`/api/chat/session/read?chat_id=${encodeURIComponent(chatId)}`);
    selectedChatId = chatId;
    chatHistory = data.messages || [];
    activeProject = data.project || "General";
    document.getElementById("chatTitle").value = data.title || "";
    document.getElementById("projectName").value = activeProject;
    document.getElementById("activeProjectLabel").textContent = `Project: ${activeProject}`;
    document.getElementById("activeModelLabel").textContent = `Model: ${data.model || activeModel}`;
    renderProjects();
    renderChats();
    renderChat();
    setStatus(`Loaded saved chat: ${data.title}`);
  } catch (err) {
    setStatus("Failed to load saved chat: " + err.message);
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

  const messages = [];
  if (systemPrompt) {
    messages.push({ role: "system", content: systemPrompt });
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
    const data = await api("/api/chat/messages", "POST", {
      model: activeModel,
      messages: messages,
      stream: false
    });

    const answer =
      data.message?.content ||
      data.response ||
      JSON.stringify(data, null, 2);

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
