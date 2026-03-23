const state = {
  models: [],
  chats: [],
  learningItems: [],
  templates: [],
  repos: [],
  messages: [],
};

function $(id) { return document.getElementById(id); }
function setStatus(id, message, isError = false) {
  const el = $(id);
  el.textContent = message;
  el.classList.toggle('error', isError);
}
async function api(url, method = 'GET', body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
  return data;
}
function selectedLearningIds() {
  return Array.from($('learningList').selectedOptions).map(option => option.value);
}
function renderMessages() {
  const box = $('chatMessages');
  box.innerHTML = '';
  for (const message of state.messages) {
    const article = document.createElement('article');
    article.className = `message ${message.role}`;
    article.innerHTML = `<div class="message-role">${message.role}</div><pre>${escapeHtml(message.content || '')}</pre>`;
    box.appendChild(article);
  }
}
function renderModels() {
  const select = $('modelSelect');
  select.innerHTML = '';
  for (const model of state.models) {
    const option = document.createElement('option');
    option.value = model.name;
    option.textContent = `${model.name} — ${model.description}`;
    select.appendChild(option);
  }
}
function renderLearningList() {
  const list = $('learningList');
  list.innerHTML = '';
  for (const item of state.learningItems) {
    const option = document.createElement('option');
    option.value = item.id;
    option.textContent = `${item.title} [${item.category}]`;
    list.appendChild(option);
  }
}
function renderRepos() {
  const select = $('repoSelect');
  select.innerHTML = '<option value="">Select repo</option>';
  for (const repo of state.repos) {
    const option = document.createElement('option');
    option.value = repo;
    option.textContent = repo;
    select.appendChild(option);
  }
}
function renderTemplates() {
  const list = $('templateList');
  list.innerHTML = '';
  for (const template of state.templates) {
    const option = document.createElement('option');
    option.value = template.template_name;
    option.textContent = `${template.template_name} (${template.file_count} files from ${template.repo_name})`;
    list.appendChild(option);
  }
}
function escapeHtml(value) {
  return value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}
async function loadModels() {
  const data = await api('/models');
  state.models = data.models || [];
  renderModels();
}
async function loadLearning() {
  const data = await api('/chat/learning');
  state.learningItems = data.items || [];
  renderLearningList();
}
async function loadRepos() {
  const data = await api('/repo/list');
  state.repos = data.repos || [];
  renderRepos();
}
async function loadTemplates() {
  const data = await api('/chat/repo-templates');
  state.templates = data.templates || [];
  renderTemplates();
}
async function loadState() {
  const data = await api('/chat/state');
  state.chats = data.chats || [];
  state.learningItems = data.learning_items || [];
  renderLearningList();
}
async function sendChat() {
  const text = $('chatInput').value.trim();
  if (!text) return;
  const model = $('modelSelect').value;
  const system = $('systemPrompt').value.trim();
  if (system && !state.messages.length) state.messages.push({ role: 'system', content: system });
  state.messages.push({ role: 'user', content: text });
  renderMessages();
  $('chatInput').value = '';
  setStatus('chatStatus', 'Talking to Ollama...');
  try {
    const data = await api('/chat/messages/retrieval', 'POST', {
      model,
      messages: state.messages,
      selected_learning_ids: selectedLearningIds(),
      use_retrieval: true,
    });
    const reply = data.message?.content || data.response || 'No response returned.';
    state.messages.push({ role: 'assistant', content: reply });
    renderMessages();
    setStatus('chatStatus', 'Reply received.');
  } catch (error) {
    setStatus('chatStatus', error.message, true);
  }
}
async function saveLearning() {
  try {
    const payload = {
      title: $('learningTitle').value.trim(),
      category: $('learningCategory').value.trim(),
      tags: $('learningTags').value.split(',').map(v => v.trim()).filter(Boolean),
      content: $('learningContent').value.trim(),
    };
    await api('/chat/learning/save', 'POST', payload);
    $('learningContent').value = '';
    setStatus('chatStatus', 'Learning item saved.');
    await loadLearning();
  } catch (error) {
    setStatus('chatStatus', error.message, true);
  }
}
async function previewLearning() {
  const ids = selectedLearningIds();
  if (!ids.length) return;
  try {
    const item = await api(`/chat/learning/read?item_id=${encodeURIComponent(ids[0])}`);
    $('learningPreview').textContent = JSON.stringify(item, null, 2);
  } catch (error) {
    $('learningPreview').textContent = error.message;
  }
}
async function makePreviewImage() {
  try {
    setStatus('imageStatus', 'Building SVG concept...');
    const data = await api('/api/chat/image-studio/generate', 'POST', {
      model: $('modelSelect').value,
      user_input: $('imagePrompt').value.trim(),
      aspect_ratio: $('aspectRatio').value,
      accent_color: $('accentColor').value.trim(),
    });
    $('imagePreview').src = data.image.data_url;
    $('imagePreview').classList.remove('hidden');
    $('downloadLink').classList.add('hidden');
    $('imageMeta').textContent = JSON.stringify(data.structured_prompt, null, 2);
    setStatus('imageStatus', 'SVG concept created.');
  } catch (error) {
    setStatus('imageStatus', error.message, true);
  }
}
async function generateRealImage() {
  try {
    setStatus('imageStatus', 'Generating image...');
    const data = await api('/api/images/generate', 'POST', {
      prompt: $('imagePrompt').value.trim(),
      model: 'stabilityai/stable-diffusion-xl-base-1.0',
      width: 1024,
      height: 1024,
      steps: 30,
      guidance: 6.5,
      format: 'png',
      rewrite_prompt: true,
      negative_prompt: ''
    });
    $('imagePreview').src = data.data_url;
    $('imagePreview').classList.remove('hidden');
    $('downloadLink').href = data.download_url;
    $('downloadLink').textContent = `Download ${data.filename}`;
    $('downloadLink').classList.remove('hidden');
    $('imageMeta').textContent = JSON.stringify(data, null, 2);
    setStatus('imageStatus', 'Real image generated.');
  } catch (error) {
    setStatus('imageStatus', error.message, true);
  }
}
async function saveChat() {
  if (!state.messages.length) return;
  const title = prompt('Chat title?', `chat-${new Date().toISOString().slice(0, 16)}`);
  if (!title) return;
  try {
    await api('/chat/session/save', 'POST', {
      title,
      project: 'General',
      messages: state.messages,
      model: $('modelSelect').value,
      learning_ids: selectedLearningIds(),
      template: $('templateList').value || '',
      repo: $('repoSelect').value || '',
    });
    setStatus('chatStatus', 'Chat saved.');
  } catch (error) {
    setStatus('chatStatus', error.message, true);
  }
}
async function saveTemplate() {
  const repoName = $('repoSelect').value;
  const templateName = $('templateName').value.trim();
  if (!repoName || !templateName) {
    setStatus('chatStatus', 'Select a repo and enter a template name.', true);
    return;
  }
  try {
    await api('/repo/template/save', 'POST', { repo_name: repoName, template_name: templateName, selected_files: [] });
    setStatus('chatStatus', 'Template pack saved.');
    await loadTemplates();
  } catch (error) {
    setStatus('chatStatus', error.message, true);
  }
}
async function showTemplateFiles() {
  const templateName = $('templateList').value;
  if (!templateName) return;
  try {
    const data = await api(`/chat/repo-template/files?template_name=${encodeURIComponent(templateName)}`);
    $('templatePreview').textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    $('templatePreview').textContent = error.message;
  }
}
function clearChat() {
  state.messages = [];
  renderMessages();
  setStatus('chatStatus', 'Chat cleared.');
}
async function boot() {
  try {
    await Promise.all([loadModels(), loadLearning(), loadRepos(), loadTemplates(), loadState()]);
    if (!$('imagePrompt').value) $('imagePrompt').value = 'A modern Zabbix dashboard hero image with glowing charts, server racks, cyber-blue palette, and polished product-poster lighting.';
    setStatus('chatStatus', 'Ready.');
  } catch (error) {
    setStatus('chatStatus', error.message, true);
  }
}
$('refreshModelsBtn').addEventListener('click', loadModels);
$('sendBtn').addEventListener('click', sendChat);
$('saveChatBtn').addEventListener('click', saveChat);
$('clearChatBtn').addEventListener('click', clearChat);
$('saveLearningBtn').addEventListener('click', saveLearning);
$('previewLearningBtn').addEventListener('click', previewLearning);
$('refreshLearningBtn').addEventListener('click', loadLearning);
$('makePreviewBtn').addEventListener('click', makePreviewImage);
$('generateRealBtn').addEventListener('click', generateRealImage);
$('saveTemplateBtn').addEventListener('click', saveTemplate);
$('loadTemplateFilesBtn').addEventListener('click', showTemplateFiles);
$('refreshTemplatesBtn').addEventListener('click', loadTemplates);
boot();
