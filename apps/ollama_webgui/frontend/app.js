let chatMessages = [];

async function api(url, method = "GET", data = null, isForm = false) {
  const options = { method };

  if (!isForm) {
    options.headers = { "Content-Type": "application/json" };
  }

  if (data) {
    options.body = isForm ? data : JSON.stringify(data);
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

function renderChat() {
  const box = document.getElementById("chatHistory");
  box.innerHTML = "";

  for (const msg of chatMessages) {
    const div = document.createElement("div");
    div.className = "chat-message " + (msg.role === "user" ? "chat-user" : "chat-assistant");

    const role = document.createElement("div");
    role.className = "chat-role";
    role.textContent = msg.role;

    const content = document.createElement("div");
    content.textContent = msg.content;

    div.appendChild(role);
    div.appendChild(content);
    box.appendChild(div);
  }

  box.scrollTop = box.scrollHeight;
}

function clearChat() {
  chatMessages = [];
  renderChat();
  document.getElementById("chatStatus").textContent = "Chat cleared.";
}

async function loadModels() {
  const status = document.getElementById("modelStatus");
  const select = document.getElementById("modelSelect");
  select.innerHTML = "";

  try {
    const data = await api("/api/models");
    const models = data.models || [];
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m.name;
      opt.textContent = m.name;
      select.appendChild(opt);
    }
    status.textContent = `Loaded ${models.length} model(s).`;
  } catch (e) {
    status.textContent = "Failed to load models: " + e.message;
  }
}

async function sendChatMessage() {
  const model = document.getElementById("modelSelect").value;
  const systemPrompt = document.getElementById("systemPrompt").value.trim();
  const input = document.getElementById("chatInput");
  const status = document.getElementById("chatStatus");
  const content = input.value.trim();

  if (!model) {
    status.textContent = "No model selected.";
    return;
  }

  if (!content) {
    status.textContent = "Type a message first.";
    return;
  }

  const messages = [];
  if (systemPrompt) {
    messages.push({ role: "system", content: systemPrompt });
  }
  for (const m of chatMessages) {
    messages.push(m);
  }
  messages.push({ role: "user", content });

  chatMessages.push({ role: "user", content });
  renderChat();
  input.value = "";
  status.textContent = "Sending...";

  try {
    const data = await api("/api/chat/messages", "POST", {
      model: model,
      messages: messages,
      stream: false
    });

    const answer =
      data.message?.content ||
      data.response ||
      JSON.stringify(data, null, 2);

    chatMessages.push({ role: "assistant", content: answer });
    renderChat();
    status.textContent = "Reply received.";
  } catch (e) {
    status.textContent = "Chat failed: " + e.message;
  }
}

async function uploadZip() {
  const input = document.getElementById("zipFile");
  const status = document.getElementById("zipStatus");

  if (!input.files.length) {
    status.textContent = "Choose a ZIP file first.";
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    const data = await api("/api/examples/upload-zip", "POST", formData, true);
    status.textContent = JSON.stringify(data, null, 2);
    await loadExamples();
  } catch (e) {
    status.textContent = "Upload failed: " + e.message;
  }
}

async function loadExamples() {
  const select = document.getElementById("exampleSelect");
  const status = document.getElementById("exampleStatus");
  const fileSelect = document.getElementById("exampleFileSelect");

  select.innerHTML = "";
  fileSelect.innerHTML = "";
  document.getElementById("exampleFileContent").textContent = "";

  try {
    const data = await api("/api/examples/list");
    for (const ex of data.examples) {
      const opt = document.createElement("option");
      opt.value = ex;
      opt.textContent = ex;
      select.appendChild(opt);
    }
    status.textContent = `Loaded ${data.examples.length} example folder(s).`;
  } catch (e) {
    status.textContent = "Failed to load examples: " + e.message;
  }
}

async function listExampleFiles() {
  const example = document.getElementById("exampleSelect").value;
  const fileSelect = document.getElementById("exampleFileSelect");
  const status = document.getElementById("exampleStatus");
  fileSelect.innerHTML = "";
  document.getElementById("exampleFileContent").textContent = "";

  if (!example) {
    status.textContent = "Select an example first.";
    return;
  }

  try {
    const data = await api(`/api/examples/files/${encodeURIComponent(example)}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      fileSelect.appendChild(opt);
    }
    status.textContent = `Example ${example}: ${data.files.length} file(s).`;
  } catch (e) {
    status.textContent = "Failed to list example files: " + e.message;
  }
}

async function readExampleFile() {
  const example = document.getElementById("exampleSelect").value;
  const file = document.getElementById("exampleFileSelect").value;
  const status = document.getElementById("exampleStatus");
  const content = document.getElementById("exampleFileContent");

  if (!example || !file) {
    status.textContent = "Select an example and file first.";
    return;
  }

  try {
    const data = await api(`/api/examples/read/${encodeURIComponent(example)}?path=${encodeURIComponent(file)}`);
    content.textContent = data.content;
    status.textContent = `Opened ${data.path}`;
  } catch (e) {
    status.textContent = "Failed to read example file: " + e.message;
  }
}

async function generateFromExample() {
  const model = document.getElementById("modelSelect").value;
  const example = document.getElementById("exampleSelect").value;
  const userRequest = document.getElementById("userRequest").value;
  const outputFolder = document.getElementById("outputFolder").value;
  const status = document.getElementById("generateStatus");

  if (!model) {
    status.textContent = "No Ollama model selected.";
    return;
  }

  if (!example) {
    status.textContent = "Select an example folder first.";
    return;
  }

  status.textContent = "Generating...";

  try {
    const data = await api("/api/widgets/generate-from-example", "POST", {
      model: model,
      example_name: example,
      user_request: userRequest,
      output_folder: outputFolder,
      write_files: true
    });

    status.textContent = JSON.stringify(data, null, 2);
    await loadGeneratedFolders();
  } catch (e) {
    status.textContent = "Generation failed: " + e.message;
  }
}

async function loadGeneratedFolders() {
  const select = document.getElementById("generatedFolderSelect");
  const fileSelect = document.getElementById("generatedFileSelect");
  const status = document.getElementById("generatedStatus");

  select.innerHTML = "";
  fileSelect.innerHTML = "";
  document.getElementById("generatedFileContent").textContent = "";

  try {
    const data = await api("/api/generated/list");
    for (const folder of data.generated) {
      const opt = document.createElement("option");
      opt.value = folder;
      opt.textContent = folder;
      select.appendChild(opt);
    }
    status.textContent = `Loaded ${data.generated.length} generated folder(s).`;
  } catch (e) {
    status.textContent = "Failed to load generated folders: " + e.message;
  }
}

async function listGeneratedFiles() {
  const folder = document.getElementById("generatedFolderSelect").value;
  const fileSelect = document.getElementById("generatedFileSelect");
  const status = document.getElementById("generatedStatus");
  fileSelect.innerHTML = "";
  document.getElementById("generatedFileContent").textContent = "";

  if (!folder) {
    status.textContent = "Select a generated folder first.";
    return;
  }

  try {
    const data = await api(`/api/generated/files/${encodeURIComponent(folder)}`);
    for (const file of data.files) {
      const opt = document.createElement("option");
      opt.value = file;
      opt.textContent = file;
      fileSelect.appendChild(opt);
    }
    status.textContent = `Generated folder ${folder}: ${data.files.length} file(s).`;
  } catch (e) {
    status.textContent = "Failed to list generated files: " + e.message;
  }
}

async function readGeneratedFile() {
  const folder = document.getElementById("generatedFolderSelect").value;
  const file = document.getElementById("generatedFileSelect").value;
  const status = document.getElementById("generatedStatus");
  const content = document.getElementById("generatedFileContent");

  if (!folder || !file) {
    status.textContent = "Select a generated folder and file first.";
    return;
  }

  try {
    const data = await api(`/api/generated/read/${encodeURIComponent(folder)}?path=${encodeURIComponent(file)}`);
    content.textContent = data.content;
    status.textContent = `Opened ${data.path}`;
  } catch (e) {
    status.textContent = "Failed to read generated file: " + e.message;
  }
}

window.onload = async function () {
  await loadModels();
  await loadExamples();
  await loadGeneratedFolders();
  renderChat();
};
