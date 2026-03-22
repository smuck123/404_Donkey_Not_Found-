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
let savedLearningItems = [];
let savedImages = [];
let selectedChatId = "";
let lastRetrieved = [];
let lastPlannedChanges = null;
let lastGeneratedImage = "";
let lastGeneratedImageMeta = null;

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
  const imageData = await api("/api/images/list");

  savedProjects = data.projects || [];
  savedChats = data.chats || [];
  savedRepoTemplates = templateData.templates || [];
  savedRepos = repoData.repos || [];
  savedLearningItems = data.learning_items || [];
  savedImages = imageData.images || [];

  document.getElementById("mainBrand").textContent = data.brand || "404DonkeyNotFound";
  document.getElementById("mainSlogan").textContent = data.slogan || "if it works, make sure donkey can break IT!";

  if (!savedProjects.includes(activeProject)) activeProject = savedProjects.length ? savedProjects[0] : "General";
  if (activeRepo && !savedRepos.includes(activeRepo)) activeRepo = "";
  if (activeTemplate && !savedRepoTemplates.some(x => x.template_name === activeTemplate)) activeTemplate = "";

  renderProjects();
  renderChats();
  renderRepoTemplates();
  renderLearningItems();
  renderProjectSelect();
  renderTemplateSelect();
  renderRepoSelect();
  renderSources();
  renderPlannedChanges();
  renderImageGallery();
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
    document.getElementById("learningTitle").value = "";
    document.getElementById("learningTags").value = "";
    document.getElementById("learningContent").value = "";
    await loadState();
    setStatus(`Saved learning item "${title}".`);
  } catch (err) {
    setStatus("Failed to save learning item: " + err.message);
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
    document.getElementById("learningBulkInput").value = "";
    await loadState();
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

function svgTextBlock(lines, x, startY, lineHeight, size, color, weight = 400) {
  return lines.map((line, idx) => (
    `<text x="${x}" y="${startY + (idx * lineHeight)}" fill="${color}" font-size="${size}" font-weight="${weight}" font-family="Arial, sans-serif">${escapeXml(line)}</text>`
  )).join("");
}

function wrapSvgText(text, maxChars) {
  const words = (text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars) {
      if (current) lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 4);
}

function generateStudyImage() {
  const title = document.getElementById("imageTitle").value.trim();
  if (!title) {
    setStatus("Image title is required.");
    return;
  }

  const subtitle = document.getElementById("imageSubtitle").value.trim();
  const bullets = document.getElementById("imageBullets").value
    .split("\n")
    .map(line => line.replace(/^[•*-]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 5);
  const accent = document.getElementById("imageAccent").value.trim() || "#38bdf8";
  const layout = document.getElementById("imageLayout").value;
  const modelWorkflow = "study-image-studio/svg";
  const sizes = {
    landscape: { width: 1600, height: 900 },
    square: { width: 1080, height: 1080 },
    portrait: { width: 1080, height: 1350 }
  };
  const { width, height } = sizes[layout] || sizes.landscape;

  const titleLines = wrapSvgText(title, layout === "landscape" ? 28 : 22);
  const subtitleLines = wrapSvgText(subtitle, layout === "landscape" ? 48 : 30);
  const bulletLines = bullets.flatMap(item => wrapSvgText(`• ${item}`, layout === "landscape" ? 42 : 28));
  const bulletStartY = layout === "portrait" ? 710 : 590;

  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="${escapeXml(accent)}"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="${width - 120}" cy="120" r="180" fill="${escapeXml(accent)}" opacity="0.15"/>
  <circle cx="140" cy="${height - 120}" r="220" fill="${escapeXml(accent)}" opacity="0.08"/>
  <rect x="60" y="60" width="${width - 120}" height="${height - 120}" rx="36" fill="#0f172a" fill-opacity="0.35" stroke="#ffffff" stroke-opacity="0.10"/>
  <text x="110" y="140" fill="${escapeXml(accent)}" font-size="36" font-weight="700" font-family="Arial, sans-serif">404DonkeyNotFound</text>
  ${svgTextBlock(titleLines, 110, layout === "portrait" ? 270 : 250, 74, layout === "portrait" ? 54 : 64, "#ffffff", 700)}
  ${svgTextBlock(subtitleLines, 110, layout === "portrait" ? 470 : 430, 42, 28, "#cbd5e1", 400)}
  ${svgTextBlock(bulletLines, 130, bulletStartY, 40, 26, "#f8fafc", 400)}
  <rect x="110" y="${height - 150}" width="${Math.min(width - 220, 520)}" height="10" rx="5" fill="url(#accent)"/>
  <text x="110" y="${height - 90}" fill="#93c5fd" font-size="28" font-weight="600" font-family="Arial, sans-serif">Study card • Ready to share</text>
</svg>`.trim();

  lastGeneratedImage = svg;
  lastGeneratedImageMeta = {
    title,
    subtitle,
    bullets,
    accent,
    layout,
    width,
    height,
    modelWorkflow
  };
  const encoded = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  document.getElementById("imagePreview").src = encoded;
  document.getElementById("imageStudioMeta").textContent = `${layout} • ${width}x${height} • accent ${accent}`;
  setStatus("Study image created. You can preview or download it.");
}

async function saveGeneratedImage() {
  if (!lastGeneratedImage || !lastGeneratedImageMeta) {
    setStatus("Generate an image first.");
    return null;
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
      modelWorkflow: meta.model_workflow || "study-image-studio/svg"
    };
    document.getElementById("imageTitle").value = lastGeneratedImageMeta.title;
    document.getElementById("imageSubtitle").value = lastGeneratedImageMeta.subtitle;
    document.getElementById("imageBullets").value = lastGeneratedImageMeta.bullets.join("\n");
    document.getElementById("imagePreview").src = `/api/images/read/${encodeURIComponent(imageId)}`;
    document.getElementById("imageStudioMeta").textContent = `${meta.created_timestamp || "saved image"} • ${meta.dimensions?.width || 0}x${meta.dimensions?.height || 0}`;
    setStatus(`Reopened saved image ${meta.title || imageId}.`);
  } catch (err) {
    setStatus("Failed to reopen saved image: " + err.message);
  }
}

function downloadSavedImage(imageId) {
  window.open(`/api/images/read/${encodeURIComponent(imageId)}`, "_blank");
  setStatus(`Opened download for image ${imageId}.`);
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
    setStatus(`Previewed learning item "${data.title}".`);
  } catch (err) {
    setStatus("Failed to preview learning item: " + err.message);
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
