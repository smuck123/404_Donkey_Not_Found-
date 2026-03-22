let chatHistory = [];
let activeModel = "qwen3:8b";
let systemPrompt = "You are a helpful assistant.";
const activeProject = "General";
let activeTemplate = "";
let activeRepo = "";
let savedChats = [];
let savedRepoTemplates = [];
let savedRepos = [];
let savedLearningItems = [];
let savedImages = [];
let availableModels = [];
let selectedChatId = "";
let lastRetrieved = [];
let lastPlannedChanges = null;
let lastGeneratedImage = "";
let lastGeneratedImageMeta = null;
let activeTemplateFiles = [];
let lastGeneratedImageDownloadUrl = "";

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

async function apiForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
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

function startImagePromptInChat() {
  const starter = [
    "Make me a picture.",
    "Topic:",
    "Style:",
    "What must be visible:",
    "Optional text inside image:"
  ].join("\n");
  const box = document.getElementById("message");
  box.value = starter;
  box.focus();
  switchRightPanelMode("image");
  setStatus("Added a picture request starter to the chat box.");
}

function jumpToSection(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.remove("flash-focus");
  void el.offsetWidth;
  el.classList.add("flash-focus");
}

function focusResultCard(id, mode = null) {
  if (mode) switchRightPanelMode(mode);
  jumpToSection(id);
}

function currentModelLooksVisionCapable() {
  const name = String(activeModel || "").toLowerCase();
  return ["llava", "vision", "minicpm-v", "bakllava", "moondream", "qwen2.5vl", "qwen-vl", "multimodal"].some(token => name.includes(token));
}

function switchRightPanelMode(targetMode = null) {
  const select = document.getElementById("rightPanelMode");
  const mode = targetMode || select?.value || "image";
  if (select) select.value = mode;
  document.querySelectorAll(".right-panel-card").forEach(card => {
    const show = card.dataset.panelMode === mode;
    card.classList.toggle("is-active", show);
    card.classList.toggle("hidden-by-mode", !show);
  });
}

function openRightPanelMode(mode, focusId = null) {
  switchRightPanelMode(mode);
  if (focusId) jumpToSection(focusId);
}

function setLearningActionStatus(text) {
  const el = document.getElementById("learningActionStatus");
  if (el) el.textContent = text;
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

function updateModelDescription() {
  const select = document.getElementById("modelSelect");
  const info = availableModels.find(model => model.name === activeModel) || availableModels[select?.selectedIndex || 0];
  const box = document.getElementById("modelDescription");
  if (!box) return;
  box.textContent = info?.description || "Pick a model for chat, image prompt rewriting, and vision tasks.";
}

function renderModelSelect() {
  const select = document.getElementById("modelSelect");
  if (!select) return;
  const models = availableModels.length ? availableModels : [{ name: activeModel, description: "Saved model" }];
  select.innerHTML = "";
  for (const model of models) {
    const opt = document.createElement("option");
    opt.value = model.name;
    opt.textContent = model.name;
    opt.title = model.description || model.name;
    if (model.name === activeModel) opt.selected = true;
    select.appendChild(opt);
  }
  document.getElementById("activeModelLabel").textContent = `Model: ${activeModel}`;
  updateModelDescription();
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
  return;
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

function buildTemplateSegments(files) {
  const groups = new Map();
  for (const path of files || []) {
    const normalized = String(path || "").trim();
    if (!normalized) continue;
    const [head] = normalized.split("/");
    const key = normalized.includes("/") ? head : "root files";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(normalized);
  }
  return [...groups.entries()]
    .map(([name, items]) => ({ name, items: items.sort() }))
    .sort((a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name));
}

function renderTemplateSegments() {
  const meta = document.getElementById("templateStudioMeta");
  const box = document.getElementById("templateSegmentsList");
  if (!box || !meta) return;

  if (!activeTemplate) {
    meta.textContent = "Select or save a template pack to inspect its segments";
    box.innerHTML = '<div class="item-meta">No template selected</div>';
    return;
  }

  if (!activeTemplateFiles.length) {
    meta.textContent = `${activeTemplate} • no files loaded yet`;
    box.innerHTML = '<div class="item-meta">No segmented files available</div>';
    return;
  }

  const segments = buildTemplateSegments(activeTemplateFiles);
  meta.textContent = `${activeTemplate} • ${activeTemplateFiles.length} files • ${segments.length} segments`;
  box.innerHTML = segments.map(segment => `
    <div class="segment-group">
      <div class="item-title">${escapeHtml(segment.name)}</div>
      <div class="item-meta">${segment.items.length} file(s)</div>
      <ul class="segment-list">
        ${segment.items.slice(0, 6).map(item => `<li>${escapeHtml(item)}</li>`).join("")}
        ${segment.items.length > 6 ? `<li>+ ${segment.items.length - 6} more</li>` : ""}
      </ul>
    </div>
  `).join("");
}

function getSelectedLearningIds() {
  return [...document.querySelectorAll('input[name="learningItem"]:checked')].map(el => el.value);
}

function renderLearningItems() {
  const box = document.getElementById("learningList");
  if (!box) return;
  if (savedLearningItems.length === 0) {
    box.innerHTML = '<div class="item-meta">No learning items yet</div>';
    return;
  }
  const selected = new Set(getSelectedLearningIds());
  box.innerHTML = savedLearningItems.map(item => `
    <label class="sidebar-item learning-item">
      <input type="checkbox" name="learningItem" value="${escapeHtml(item.id)}" ${selected.has(item.id) ? "checked" : ""}>
      <div>
        <div class="item-title">${escapeHtml(item.title)}</div>
        <div class="item-meta">${escapeHtml(item.category)} • ${escapeHtml((item.tags || []).join(", ") || "no tags")}</div>
      </div>
    </label>
  `).join("");
}

function renderImageGallery() {
  const box = document.getElementById("imageGalleryList");
  if (!box) return;
  if (savedImages.length === 0) {
    box.innerHTML = '<div class="item-meta">No saved images yet</div>';
    return;
  }

  box.innerHTML = savedImages.map(image => {
    const dims = image.dimensions || {};
    const promptPreview = (image.prompt || "").trim();
    return `
      <div class="sidebar-item gallery-item">
        <div class="item-title">${escapeHtml(image.title || image.image_id)}</div>
        <div class="item-meta">${escapeHtml(image.created_timestamp || "unknown")} • ${escapeHtml(`${dims.width || 0}x${dims.height || 0}`)}</div>
        <div class="item-meta">${escapeHtml(image.model_workflow || "study-image-studio")}</div>
        <div class="item-meta">${escapeHtml(promptPreview ? promptPreview.slice(0, 120) : "No prompt saved")}</div>
        <div class="button-row">
          <button onclick="reopenSavedImage(${JSON.stringify(image.image_id)})">Reopen</button>
          <button onclick="downloadSavedImage(${JSON.stringify(image.image_id)})">Download</button>
          <button onclick="deleteSavedImage(${JSON.stringify(image.image_id)})">Delete</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderImageSummary() {
  const box = document.getElementById("imageResultSummary");
  if (!box) return;
  if (!lastGeneratedImageMeta) {
    box.innerHTML = `
      <div class="item-title">No image yet</div>
      <div class="item-meta">Generate an SVG concept or a real image to see details and reuse it later.</div>
    `;
    return;
  }
  const bullets = (lastGeneratedImageMeta.bullets || []).slice(0, 4);
  box.innerHTML = `
    <div class="item-title">${escapeHtml(lastGeneratedImageMeta.title || "Generated image")}</div>
    <div class="item-meta">${escapeHtml(lastGeneratedImageMeta.modelWorkflow || activeModel)} • ${escapeHtml(`${lastGeneratedImageMeta.width || 0}x${lastGeneratedImageMeta.height || 0}`)}</div>
    <div class="item-meta">${escapeHtml(lastGeneratedImageMeta.subtitle || "Preview ready below. Save it to gallery if you want to reopen it later.")}</div>
    ${bullets.length ? `<ul class="segment-list">${bullets.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
}

function renderChat() {
  const box = document.getElementById("chatBox");
  if (chatHistory.length === 0) {
    box.innerHTML = `
      <div class="empty-state">
        <h2>Build, teach, and create from one workspace.</h2>
        <p>Select a template or repo, chat with contextual retrieval, upload training material for your Ollama stack, and turn notes into ready-to-share images.</p>
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
  focusResultCard("diffPreviewCard", "changes");
}

async function openSourceByIndex(index) {
  const item = lastRetrieved[index];
  if (!item) return;

  const normalizedPath = String(item.path || "").replace(/\\/g, "/");
  let params = new URLSearchParams({
    source_type: item.source_type || "",
    path: normalizedPath
  });

  if (item.source_type === "repo") {
    const repoName = activeRepo || normalizedPath.split("/repos/")[1]?.split("/")[0] || "";
    const repoPath = normalizedPath.includes("/repos/") ? normalizedPath.split("/repos/")[1]?.split("/").slice(1).join("/") : normalizedPath;
    if (repoName) params.set("repo_name", repoName);
    params.set("path", repoPath || normalizedPath);
  }
  if (item.source_type === "template") {
    const templateName = activeTemplate || normalizedPath.split("/repo_templates/")[1]?.split("/")[0] || "";
    const templatePath = normalizedPath.includes("/repo_templates/") ? normalizedPath.split("/repo_templates/")[1]?.split("/").slice(1).join("/") : normalizedPath;
    if (templateName) params.set("template_name", templateName);
    params.set("path", templatePath || normalizedPath);
  }
  if (item.source_type === "website") params.set("section", "chat");

  try {
    const data = await api(`/api/chat/source/view?${params.toString()}`);
    document.getElementById("sourceMeta").textContent = `${data.source_type}: ${data.path}`;
    document.getElementById("sourceViewer").textContent = data.content;
    focusResultCard("sourceViewerCard", "sources");
  } catch (err) {
    setStatus("Failed to open source: " + err.message);
  }
}

async function selectTemplate(name) {
  activeTemplate = name;
  renderRepoTemplates();
  renderTemplateSelect();
  await refreshTemplateSegments();
}

async function changeTemplateContext() {
  activeTemplate = document.getElementById("templateSelect").value;
  renderRepoTemplates();
  renderTemplateSelect();
  await refreshTemplateSegments();
}

function changeRepoContext() {
  activeRepo = document.getElementById("repoSelect").value;
  renderRepoSelect();
}

function changeModelContext() {
  activeModel = document.getElementById("modelSelect").value || activeModel;
  localStorage.setItem("chat_model", activeModel);
  renderModelSelect();
  const visionHint = currentModelLooksVisionCapable() ? " Vision should work with uploaded pictures." : " For Image Vision, switch to a vision-capable model if needed.";
  setStatus(`Active model changed to ${activeModel}.` + visionHint);
}

async function refreshModels() {
  try {
    const data = await api("/api/models");
    availableModels = data.models || [];
    if (!availableModels.some(model => model.name === activeModel) && availableModels[0]) {
      activeModel = availableModels[0].name;
    }
    renderModelSelect();
    setStatus(`Loaded ${availableModels.length} model(s).`);
  } catch (err) {
    setStatus("Failed to load models: " + err.message);
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
  renderChat();
  setStatus("Started new chat.");
}

async function loadState() {
  const [data, templateData, repoData, imageData, modelData] = await Promise.all([
    api("/api/chat/state"),
    api("/api/chat/repo-templates"),
    api("/api/repo/list"),
    api("/api/images/list"),
    api("/api/models").catch(() => ({ models: [] }))
  ]);

  savedChats = data.chats || [];
  savedRepoTemplates = templateData.templates || [];
  savedRepos = repoData.repos || [];
  savedLearningItems = data.learning_items || [];
  savedImages = imageData.images || [];
  availableModels = modelData.models || [];

  document.getElementById("mainBrand").textContent = data.brand || "404DonkeyNotFound";
  document.getElementById("mainSlogan").textContent = data.slogan || "if it works, make sure donkey can break IT!";

  if (activeRepo && !savedRepos.includes(activeRepo)) activeRepo = "";
  if (activeTemplate && !savedRepoTemplates.some(x => x.template_name === activeTemplate)) activeTemplate = "";

  renderChats();
  renderRepoTemplates();
  renderLearningItems();
  renderTemplateSelect();
  renderRepoSelect();
  renderModelSelect();
  renderSources();
  renderPlannedChanges();
  renderImageGallery();
  renderImageSummary();
  await refreshTemplateSegments();
}

function showWorkspaceGuide() {
  const guide = [
    "Workspace guide:",
    "1. Add repos from Admin, then come back and select the repo here.",
    "2. Save a template pack from the selected repo if you want reusable context.",
    "3. Choose Mode: Auto uses all sources, Templates only limits retrieval to templates, Repos only limits retrieval to repos, Website only limits retrieval to website files.",
    "4. To make pictures, use Image Studio on the right and watch the preview panel below the buttons.",
    "5. For Image Vision, choose a vision-capable model first, upload a picture, then click Look at picture.",
    "6. Use Learning Capture to save notes, upload files, or import a URL. Successful actions now keep that panel open and show status there.",
    "7. When you click a source or diff, the page now jumps directly to the output viewer."
  ].join("\n");
  document.getElementById("message").value = guide;
  setStatus("Added the workspace guide to the composer.");
  jumpToSection("workspaceContext");
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
      project: activeProject,
      messages: chatHistory,
      model: activeModel,
      template: activeTemplate || "",
      repo: activeRepo || "",
      learning_ids: getSelectedLearningIds()
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
    activeModel = data.model || activeModel;
    activeTemplate = data.template || "";
    activeRepo = data.repo || "";
    selectedChatId = chatId;
    renderChats();
    renderTemplateSelect();
    renderRepoSelect();
    renderModelSelect();
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
  try {
    await api(`/api/chat/session/delete?chat_id=${encodeURIComponent(selectedChatId)}`, "POST");
    selectedChatId = "";
    chatHistory = [];
    renderChat();
    await loadState();
    setStatus("Deleted selected chat.");
  } catch (err) {
    setStatus("Failed to delete chat: " + err.message);
  }
}

function buildSourceTypes() {
  const mode = document.getElementById("modeSelect").value;
  if (mode === "template") return ["template"];
  if (mode === "repo") return ["repo"];
  if (mode === "website") return ["website"];
  return null;
}

function applyPromptPreset(text) {
  const messageBox = document.getElementById("message");
  messageBox.value = text;
  messageBox.focus();
}

function fillLearningFromComposer() {
  const message = document.getElementById("message").value.trim();
  if (!message) {
    setStatus("Write something in the composer first.");
    return;
  }
  if (!document.getElementById("learningTitle").value.trim()) {
    document.getElementById("learningTitle").value = `Study note ${new Date().toISOString().slice(0, 10)}`;
  }
  document.getElementById("learningContent").value = message;
  setLearningActionStatus("Composer text copied into the learning form.");
  openRightPanelMode("learning", "learningCaptureCard");
  setStatus("Copied composer text into Learning Capture.");
}

function parseBulkLearningInput(rawText) {
  return rawText
    .split(/\n---+\n/g)
    .map(block => block.trim())
    .filter(Boolean)
    .map(block => {
      const lines = block.split("\n");
      let title = "";
      let category = document.getElementById("learningCategory").value.trim() || "reference";
      let tags = [];
      const contentLines = [];

      for (const line of lines) {
        if (!title && line.startsWith("### ")) {
          title = line.replace(/^###\s+/, "").trim();
          continue;
        }
        if (/^category:/i.test(line)) {
          category = line.split(":").slice(1).join(":").trim() || category;
          continue;
        }
        if (/^tags:/i.test(line)) {
          tags = line.split(":").slice(1).join(":").split(",").map(x => x.trim()).filter(Boolean);
          continue;
        }
        contentLines.push(line);
      }

      return {
        title: title || `Study item ${Math.random().toString(36).slice(2, 8)}`,
        category,
        tags,
        content: contentLines.join("\n").trim()
      };
    })
    .filter(item => item.title && item.content);
}

async function saveLearningItem() {
  const title = document.getElementById("learningTitle").value.trim();
  const category = document.getElementById("learningCategory").value.trim();
  const tags = document.getElementById("learningTags").value.split(",").map(x => x.trim()).filter(Boolean);
  const content = document.getElementById("learningContent").value.trim();
  if (!title || !content) {
    setStatus("Learning title and content are required.");
    return;
  }
  try {
    await api("/api/chat/learning/save", "POST", { title, category, tags, content });
    setLearningActionStatus(`Saved learning item: ${title}`);
    document.getElementById("learningTitle").value = "";
    document.getElementById("learningTags").value = "";
    document.getElementById("learningContent").value = "";
    await loadState();
    openRightPanelMode("learning", "learningCaptureCard");
    setStatus(`Saved learning item "${title}".`);
  } catch (err) {
    setStatus("Failed to save learning item: " + err.message);
  }
}

async function uploadLearningFiles() {
  const input = document.getElementById("learningUploadFiles");
  const files = [...(input.files || [])];
  if (files.length === 0) {
    setStatus("Choose one or more files first.");
    return;
  }

  const formData = new FormData();
  formData.append("category", document.getElementById("learningCategory").value.trim() || "uploaded-reference");
  formData.append("tags", document.getElementById("learningTags").value.trim());
  for (const file of files) formData.append("files", file);

  try {
    const data = await apiForm("/api/chat/learning/upload", formData);
    setLearningActionStatus(`Uploaded ${data.count || files.length} file(s) into the learning library.`);
    input.value = "";
    await loadState();
    openRightPanelMode("learning", "learningCaptureCard");
    setStatus(`Uploaded ${data.count || files.length} file(s) into the learning library.`);
  } catch (err) {
    setStatus("File upload failed: " + err.message);
  }
}

async function importLearningUrl() {
  const url = document.getElementById("learningUrlInput").value.trim();
  if (!url) {
    setStatus("Enter a URL first.");
    return;
  }
  const category = document.getElementById("learningCategory").value.trim() || "web-reference";
  const tags = document.getElementById("learningTags").value.split(",").map(x => x.trim()).filter(Boolean);
  try {
    await api("/api/chat/learning/import-url", "POST", { url, category, tags });
    setLearningActionStatus(`Imported URL source: ${url}`);
    document.getElementById("learningUrlInput").value = "";
    await loadState();
    openRightPanelMode("learning", "learningCaptureCard");
    setStatus("Imported URL into the learning library.");
  } catch (err) {
    setStatus("URL import failed: " + err.message);
  }
}

async function importLearningBatch() {
  const rawText = document.getElementById("learningBulkInput").value.trim();
  if (!rawText) {
    setStatus("Paste study material into the bulk import box first.");
    return;
  }

  const items = parseBulkLearningInput(rawText);
  if (items.length === 0) {
    setStatus("Bulk import format was empty or invalid.");
    return;
  }

  try {
    const data = await api("/api/chat/learning/save-batch", "POST", { items });
    setLearningActionStatus(`Imported ${data.count || items.length} study item(s).`);
    document.getElementById("learningBulkInput").value = "";
    await loadState();
    openRightPanelMode("learning", "learningCaptureCard");
    setStatus(`Imported ${data.count || items.length} study item(s).`);
  } catch (err) {
    setStatus("Bulk import failed: " + err.message);
  }
}

async function appendSelectionToComposer() {
  const ids = getSelectedLearningIds();
  if (ids.length === 0) {
    setStatus("Select one or more learning items first.");
    return;
  }

  try {
    const loaded = await Promise.all(ids.slice(0, 6).map(id =>
      api(`/api/chat/learning/read?item_id=${encodeURIComponent(id)}`)
    ));
    const messageBox = document.getElementById("message");
    const blocks = loaded.map(item =>
      `### ${item.title}\nCategory: ${item.category}\nTags: ${(item.tags || []).join(", ")}\n${item.content}`
    );
    messageBox.value = [messageBox.value.trim(), blocks.join("\n\n---\n\n")].filter(Boolean).join("\n\n");
    messageBox.focus();
    setLearningActionStatus(`Added ${loaded.length} selected learning item(s) into the composer.`);
    openRightPanelMode("learning", "learningCaptureCard");
    setStatus(`Added ${loaded.length} learning item(s) to the composer.`);
  } catch (err) {
    setStatus("Failed to add learning items to composer: " + err.message);
  }
}

function buildImagePayload(titleSource, bodySource) {
  const cleanedBody = (bodySource || "")
    .split("\n")
    .map(line => line.replace(/^[•*-]\s*/, "").trim())
    .filter(Boolean);

  return {
    title: (titleSource || "Study Pack").trim().slice(0, 80),
    subtitle: cleanedBody[0] || "Fast review notes and guided practice.",
    bullets: cleanedBody.slice(1, 5),
  };
}

function buildImageFromComposer() {
  const message = document.getElementById("message").value.trim();
  if (!message) {
    setStatus("Composer is empty.");
    return;
  }
  const payload = buildImagePayload(message.split("\n")[0], message);
  document.getElementById("imageTitle").value = payload.title;
  document.getElementById("imageSubtitle").value = payload.subtitle;
  document.getElementById("imageBullets").value = payload.bullets.join("\n");
  document.getElementById("imagePrompt").value = [payload.title, payload.subtitle, ...payload.bullets].filter(Boolean).join(", ");
  setStatus("Prepared image content from the composer.");
}

async function buildImageFromLearning() {
  const ids = getSelectedLearningIds();
  if (ids.length === 0) {
    setStatus("Select a learning item first.");
    return;
  }
  try {
    const item = await api(`/api/chat/learning/read?item_id=${encodeURIComponent(ids[0])}`);
    const payload = buildImagePayload(item.title, item.content);
    document.getElementById("imageTitle").value = payload.title;
    document.getElementById("imageSubtitle").value = payload.subtitle;
    document.getElementById("imageBullets").value = payload.bullets.join("\n");
    document.getElementById("imagePrompt").value = [payload.title, payload.subtitle, ...payload.bullets].filter(Boolean).join(", ");
    setStatus(`Prepared image content from "${item.title}".`);
  } catch (err) {
    setStatus("Failed to build image from learning item: " + err.message);
  }
}

function escapeXml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

async function generateStudyImage() {
  const title = document.getElementById("imageTitle").value.trim();
  const subtitle = document.getElementById("imageSubtitle").value.trim();
  const bullets = document.getElementById("imageBullets").value
    .split("\n")
    .map(line => line.replace(/^[•*-]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 5);
  const promptInput = [title, subtitle, ...bullets].filter(Boolean).join("\n");
  if (!promptInput) {
    setStatus("Add at least a title, subtitle, or bullets first.");
    return;
  }
  const accent = document.getElementById("imageAccent").value.trim() || "#38bdf8";
  const aspectMap = { landscape: "16:9", square: "1:1", portrait: "4:5" };
  const layout = document.getElementById("imageLayout").value;
  try {
    const data = await api("/api/chat/image-studio/generate", "POST", {
      model: activeModel,
      user_input: promptInput,
      aspect_ratio: aspectMap[layout] || "16:9",
      accent_color: accent
    });
    const image = data.image || {};
    lastGeneratedImage = image.svg || "";
    lastGeneratedImageMeta = {
      title: title || "Generated image",
      subtitle,
      bullets,
      accent,
      layout,
      width: image.width || 0,
      height: image.height || 0,
      modelWorkflow: image.backend || "study-image-studio/svg",
      mimeType: image.mime_type || "image/svg+xml"
    };
    lastGeneratedImageDownloadUrl = "";
    document.getElementById("imagePreview").src = image.data_url || "";
    document.getElementById("imageStudioMeta").textContent = `${layout} • ${image.width || 0}x${image.height || 0} • ${activeModel}`;
    renderImageSummary();
    focusResultCard("imageStudioCard", "image");
    setStatus("Image prompt sent through the backend pipeline.");
  } catch (err) {
    setStatus("Image generation failed: " + err.message);
  }
}

async function generateRealImage() {
  const title = document.getElementById("imageTitle").value.trim();
  const subtitle = document.getElementById("imageSubtitle").value.trim();
  const bullets = document.getElementById("imageBullets").value
    .split("\n")
    .map(line => line.replace(/^[•*-]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 5);
  const prompt = document.getElementById("imagePrompt").value.trim() || [title, subtitle, ...bullets].filter(Boolean).join(", ");
  if (!prompt) {
    setStatus("Add a prompt or fill in the image fields first.");
    return;
  }

  const width = Number(document.getElementById("imageWidth").value || 832);
  const height = Number(document.getElementById("imageHeight").value || 1216);
  const steps = Number(document.getElementById("imageSteps").value || 30);
  const guidance = Number(document.getElementById("imageGuidance").value || 6.5);
  const negativePrompt = document.getElementById("imageNegativePrompt").value.trim();
  const imageModel = document.getElementById("imageModelName").value.trim() || "stabilityai/stable-diffusion-xl-base-1.0";
  const format = document.getElementById("imageOutputFormat").value;
  const rewritePrompt = document.getElementById("imageRewritePrompt").checked;

  try {
    const data = await api("/api/images/generate", "POST", {
      model: imageModel,
      prompt,
      negative_prompt: negativePrompt,
      width,
      height,
      steps,
      guidance,
      format,
      rewrite_prompt: rewritePrompt
    });
    lastGeneratedImage = data.data_url || "";
    lastGeneratedImageDownloadUrl = data.download_url || "";
    lastGeneratedImageMeta = {
      title: title || "Generated image",
      subtitle,
      bullets,
      width: data.width || width,
      height: data.height || height,
      modelWorkflow: data.model || imageModel,
      mimeType: `image/${data.format || format}`,
      prompt: data.final_prompt || prompt,
      filename: data.filename || ""
    };
    document.getElementById("imagePreview").src = data.data_url || "";
    document.getElementById("imageStudioMeta").textContent = `${data.width || width}x${data.height || height} • ${data.model || imageModel} • ${data.format || format}`;
    renderImageSummary();
    focusResultCard("imageStudioCard", "image");
    setStatus(`Generated real image ${data.filename || ""}`.trim());
  } catch (err) {
    const hint = String(err.message || "").includes("Not Found") ? " Check whether the image backend endpoint is configured and reachable." : "";
    setStatus("Real image generation failed: " + err.message + hint);
  }
}

async function saveGeneratedImage() {
  if (!lastGeneratedImage || !lastGeneratedImageMeta) {
    setStatus("Generate an image first.");
    return null;
  }

  if ((lastGeneratedImageMeta.mimeType || "").startsWith("image/") && !String(lastGeneratedImageMeta.mimeType).includes("svg")) {
    if (lastGeneratedImageDownloadUrl) {
      window.open(lastGeneratedImageDownloadUrl, "_blank");
      setStatus("Real image was already saved by the backend and opened for download.");
      return {
        download_url: lastGeneratedImageDownloadUrl,
        title: lastGeneratedImageMeta.title || "Generated image"
      };
    }
    throw new Error("Real image download URL is missing.");
  }

  const prompt = [
    lastGeneratedImageMeta.title,
    lastGeneratedImageMeta.subtitle,
    ...(lastGeneratedImageMeta.bullets || [])
  ].filter(Boolean).join("\n");

  const saved = await api("/api/images", "POST", {
    svg: lastGeneratedImage,
    prompt,
    model_workflow: lastGeneratedImageMeta.modelWorkflow,
    width: lastGeneratedImageMeta.width,
    height: lastGeneratedImageMeta.height,
    title: lastGeneratedImageMeta.title
  });
  await loadState();
  setStatus(`Saved image "${saved.title || lastGeneratedImageMeta.title}" to the gallery.`);
  return saved;
}

async function downloadGeneratedImage() {
  try {
    const saved = await saveGeneratedImage();
    if (!saved) return;
    window.open(saved.download_url, "_blank");
    setStatus("Saved image metadata and opened the download.");
  } catch (err) {
    setStatus("Failed to save/download image: " + err.message);
  }
}

async function reopenSavedImage(imageId) {
  try {
    const [meta, svgText] = await Promise.all([
      api(`/api/images/read/${encodeURIComponent(imageId)}?format=meta`),
      fetch(`/api/images/read/${encodeURIComponent(imageId)}?format=raw`).then(async res => {
        const text = await res.text();
        if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
        return text;
      })
    ]);

    const promptLines = (meta.prompt || "").split("\n").map(line => line.trim()).filter(Boolean);
    lastGeneratedImage = svgText;
    lastGeneratedImageMeta = {
      title: meta.title || promptLines[0] || "",
      subtitle: promptLines[1] || "",
      bullets: promptLines.slice(2),
      accent: document.getElementById("imageAccent").value.trim() || "#38bdf8",
      layout: "saved",
      width: meta.dimensions?.width || 0,
      height: meta.dimensions?.height || 0,
      modelWorkflow: meta.model_workflow || "study-image-studio/svg",
      mimeType: "image/svg+xml"
    };
    lastGeneratedImageDownloadUrl = `/api/images/read/${encodeURIComponent(imageId)}`;
    document.getElementById("imageTitle").value = lastGeneratedImageMeta.title;
    document.getElementById("imageSubtitle").value = lastGeneratedImageMeta.subtitle;
    document.getElementById("imageBullets").value = lastGeneratedImageMeta.bullets.join("\n");
    document.getElementById("imagePreview").src = `/api/images/read/${encodeURIComponent(imageId)}`;
    document.getElementById("imageStudioMeta").textContent = `${meta.created_timestamp || "saved image"} • ${meta.dimensions?.width || 0}x${meta.dimensions?.height || 0}`;
    renderImageSummary();
    setStatus(`Reopened saved image ${meta.title || imageId}.`);
  } catch (err) {
    setStatus("Failed to reopen saved image: " + err.message);
  }
}

function copyImageHelp() {
  const help = [
    "How to create a picture:",
    "1. Choose a model in the top bar.",
    "2. Open Image Studio on the right.",
    "3. Add a title, subtitle, bullets, or a direct prompt.",
    "4. Click Create SVG concept for a fast draft or Create real image for the backend.",
    "5. The preview appears immediately under Image Studio.",
    "6. Save to gallery if you want to reopen or download it later."
  ].join("\n");
  document.getElementById("message").value = help;
  openRightPanelMode("image", "imageStudioCard");
  setStatus("Added image creation help to the composer.");
}

function downloadSavedImage(imageId) {
  window.open(`/api/images/read/${encodeURIComponent(imageId)}`, "_blank");
  setStatus(`Opened download for image ${imageId}.`);
}

async function analyzeUploadedImage() {
  const input = document.getElementById("imageAnalysisFile");
  const prompt = document.getElementById("imageAnalysisPrompt").value.trim() || "Describe this image in detail and extract visible text.";
  if (!input.files || input.files.length === 0) {
    setStatus("Choose an image to analyze first.");
    return;
  }

  try {
    const formData = new FormData();
    formData.append("model", activeModel);
    formData.append("prompt", prompt);
    formData.append("image", input.files[0]);
    const data = await apiForm("/api/images/analyze", formData);
    document.getElementById("imageAnalysisMeta").textContent = `${data.filename || "image"} • ${data.model}`;
    document.getElementById("imageAnalysisResult").textContent = data.analysis || "";
    if (data.preview_data_url) {
      document.getElementById("imagePreview").src = data.preview_data_url;
    }
    focusResultCard("imageStudioCard", "image");
    setStatus("Image analysis completed.");
  } catch (err) {
    const hint = currentModelLooksVisionCapable() ? "" : " Try switching to a vision-capable model first.";
    setStatus("Image analysis failed: " + err.message + hint);
  }
}

async function deleteSavedImage(imageId) {
  try {
    await api(`/api/images/${encodeURIComponent(imageId)}`, "DELETE");
    await loadState();
    setStatus(`Deleted image ${imageId}.`);
  } catch (err) {
    setStatus("Failed to delete image: " + err.message);
  }
}

async function previewLearningItem() {
  const ids = getSelectedLearningIds();
  if (ids.length === 0) {
    setStatus("Select a learning item to preview.");
    return;
  }
  try {
    const data = await api(`/api/chat/learning/read?item_id=${encodeURIComponent(ids[0])}`);
    document.getElementById("sourceMeta").textContent = `learning: ${data.title}`;
    document.getElementById("sourceViewer").textContent = data.content;
    focusResultCard("sourceViewerCard", "sources");
    setStatus(`Previewed learning item "${data.title}".`);
  } catch (err) {
    setStatus("Failed to preview learning item: " + err.message);
  }
}

async function refreshTemplateSegments() {
  if (!activeTemplate) {
    activeTemplateFiles = [];
    renderTemplateSegments();
    return;
  }

  try {
    const data = await api(`/api/chat/repo-template/files?template_name=${encodeURIComponent(activeTemplate)}`);
    activeTemplateFiles = data.files || [];
    renderTemplateSegments();
  } catch (err) {
    activeTemplateFiles = [];
    renderTemplateSegments();
    setStatus("Failed to load template segments: " + err.message);
  }
}

async function saveTemplateSnapshot() {
  if (!activeRepo) {
    setStatus("Select a repo first so a template pack can be created from it.");
    return;
  }

  const templateName = document.getElementById("templateNameInput").value.trim() || `${activeRepo}-template`;
  try {
    await api("/api/repo/template/save", "POST", {
      repo_name: activeRepo,
      template_name: templateName,
      selected_files: []
    });
    activeTemplate = templateName;
    document.getElementById("templateNameInput").value = templateName;
    await loadState();
    setStatus(`Saved template pack "${templateName}" from repo "${activeRepo}".`);
  } catch (err) {
    setStatus("Failed to save template pack: " + err.message);
  }
}

async function deleteActiveTemplate() {
  if (!activeTemplate) {
    setStatus("Select a template pack first.");
    return;
  }

  try {
    await api("/api/repo/template/delete", "POST", { template_name: activeTemplate });
    const deleted = activeTemplate;
    activeTemplate = "";
    activeTemplateFiles = [];
    await loadState();
    setStatus(`Deleted template pack "${deleted}".`);
  } catch (err) {
    setStatus("Failed to delete template pack: " + err.message);
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
      selected_learning_ids: getSelectedLearningIds(),
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
      selected_repo: activeRepo || null,
      selected_learning_ids: getSelectedLearningIds()
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
    focusResultCard("sourceViewerCard", "sources");
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
  switchRightPanelMode("image");
  await loadState();
  renderImageSummary();
  setLearningActionStatus("No learning action yet");
  setStatus(`Ready. Active model: ${activeModel}`);
};
