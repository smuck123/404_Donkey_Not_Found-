from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import requests
import zipfile
import io
import json
import shutil
import subprocess

app = FastAPI(title="Ollama Web GUI + Zabbix Example Builder")

OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"

BASE_DIR = Path("/opt/ollama_webgui").resolve()
SAFE_EDIT_ROOT = (BASE_DIR / "editable").resolve()
EXAMPLES_ROOT = (BASE_DIR / "examples" / "zabbix").resolve()
GENERATED_ROOT = (BASE_DIR / "generated_widgets").resolve()

ALLOWED_CONTEXT_SUFFIXES = {".php", ".json", ".md", ".txt", ".yaml", ".yml", ".js", ".css", ".html"}
MAX_CONTEXT_FILES = 50
MAX_CONTEXT_CHARS = 200000

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    prompt: str
    system: str | None = None
    stream: bool = False

class ChatMessageRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list
    stream: bool = False

class SaveFileRequest(BaseModel):
    relative_path: str
    content: str

class ReadFileRequest(BaseModel):
    relative_path: str

class GenerateFromExampleRequest(BaseModel):
    model: str = DEFAULT_MODEL
    example_name: str
    user_request: str
    output_folder: str = "generated_widget"
    write_files: bool = True

def safe_join(root: Path, relative_path: str) -> Path:
    p = (root / relative_path).resolve()
    if not str(p).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path not allowed")
    return p

def collect_example_context(folder: Path):
    chunks = []
    count = 0
    total_chars = 0

    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix.lower() in ALLOWED_CONTEXT_SUFFIXES:
            rel = p.relative_to(folder)
            text = p.read_text(encoding="utf-8", errors="replace")
            block = f"\n--- FILE: {rel} ---\n{text}\n"
            new_total = total_chars + len(block)

            if count >= MAX_CONTEXT_FILES or new_total > MAX_CONTEXT_CHARS:
                break

            chunks.append(block)
            total_chars = new_total
            count += 1

    return "".join(chunks), count, total_chars

def extract_json_block(text: str):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return text[start:end + 1]

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/models")
def list_models():
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load models: {e}")

@app.post("/api/chat")
def chat(req: ChatRequest):
    payload = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": req.stream
    }
    if req.system:
        payload["system"] = req.system

    try:
        r = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=300)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama request failed: {e}")

@app.post("/api/chat/messages")
def chat_messages(req: ChatMessageRequest):
    payload = {
        "model": req.model,
        "messages": req.messages,
        "stream": req.stream
    }

    try:
        r = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=300)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama chat request failed: {e}")

@app.post("/api/files/save")
def save_file(req: SaveFileRequest):
    target = safe_join(SAFE_EDIT_ROOT, req.relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "path": str(target.relative_to(SAFE_EDIT_ROOT))}

@app.post("/api/files/read")
def read_file(req: ReadFileRequest):
    target = safe_join(SAFE_EDIT_ROOT, req.relative_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": str(target.relative_to(SAFE_EDIT_ROOT)),
        "content": target.read_text(encoding="utf-8", errors="replace")
    }

@app.get("/api/files/list")
def list_files():
    files = []
    for p in SAFE_EDIT_ROOT.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(SAFE_EDIT_ROOT)))
    return {"files": sorted(files)}

@app.post("/api/examples/upload-zip")
async def upload_example_zip(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed")

    content = await file.read()

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {e}")

    folder_name = Path(file.filename).stem.replace(" ", "_")
    target_dir = safe_join(EXAMPLES_ROOT, folder_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    for member in zf.infolist():
        member_name = member.filename

        if member_name.startswith("/") or ".." in Path(member_name).parts:
            raise HTTPException(status_code=400, detail=f"Unsafe ZIP entry: {member_name}")

        dest = safe_join(target_dir, member_name)

        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)

    return {
        "status": "uploaded",
        "example_name": folder_name,
        "path": str(target_dir)
    }

@app.get("/api/examples/list")
def list_examples():
    EXAMPLES_ROOT.mkdir(parents=True, exist_ok=True)
    examples = [p.name for p in EXAMPLES_ROOT.iterdir() if p.is_dir()]
    return {"examples": sorted(examples)}

@app.get("/api/examples/files/{example_name}")
def list_example_files(example_name: str):
    folder = safe_join(EXAMPLES_ROOT, example_name)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Example not found")

    files = []
    for p in folder.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(folder)))

    return {"example_name": example_name, "files": sorted(files)}

@app.get("/api/examples/read/{example_name}")
def read_example_file(example_name: str, path: str):
    folder = safe_join(EXAMPLES_ROOT, example_name)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Example not found")

    target = safe_join(folder, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Example file not found")

    return {
        "example_name": example_name,
        "path": path,
        "content": target.read_text(encoding="utf-8", errors="replace")
    }

@app.post("/api/widgets/generate-from-example")
def generate_from_example(req: GenerateFromExampleRequest):
    example_folder = safe_join(EXAMPLES_ROOT, req.example_name)
    if not example_folder.exists():
        raise HTTPException(status_code=404, detail="Example not found")

    context, file_count, total_chars = collect_example_context(example_folder)
    if not context.strip():
        raise HTTPException(status_code=400, detail="No supported files found in example folder")

    prompt = f"""
You are generating a Zabbix widget/module example.

Use the supplied example files as reference and keep a similar structure and style.

EXAMPLE_NAME:
{req.example_name}

EXAMPLE_FILES:
{context}

TASK:
{req.user_request}

Return ONLY valid JSON in this exact structure:
{{
  "summary": "short summary",
  "files": {{
    "manifest.json": "...file content...",
    "README.md": "...file content...",
    "Module.php": "...file content...",
    "actions/ExampleAction.php": "...file content...",
    "views/example.view.php": "...file content..."
  }}
}}

Rules:
- Return only JSON, no markdown fences.
- Keep file contents realistic for a Zabbix widget/module example.
- If a file is not needed, you may omit it.
- Use the example style and naming conventions where practical.
"""

    payload = {
        "model": req.model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        r = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama request failed: {e}")

    raw_response = data.get("response", "")
    try:
        parsed = json.loads(raw_response)
    except Exception:
        try:
            parsed = json.loads(extract_json_block(raw_response))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Model did not return valid JSON: {e}")

    files = parsed.get("files", {})
    output_dir = safe_join(GENERATED_ROOT, req.output_folder)
    written = []

    if req.write_files:
        output_dir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in files.items():
            target = safe_join(output_dir, rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            written.append(str(target.relative_to(output_dir)))

    return {
        "summary": parsed.get("summary", ""),
        "example_name": req.example_name,
        "context_files_used": file_count,
        "context_chars_used": total_chars,
        "output_dir": str(output_dir),
        "written_files": written,
        "model_response": parsed
    }

@app.get("/api/generated/list")
def list_generated():
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    items = [p.name for p in GENERATED_ROOT.iterdir() if p.is_dir()]
    return {"generated": sorted(items)}

@app.get("/api/generated/files/{folder_name}")
def list_generated_files(folder_name: str):
    folder = safe_join(GENERATED_ROOT, folder_name)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Generated folder not found")

    files = []
    for p in folder.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(folder)))
    return {"folder_name": folder_name, "files": sorted(files)}

@app.get("/api/generated/read/{folder_name}")
def read_generated_file(folder_name: str, path: str):
    folder = safe_join(GENERATED_ROOT, folder_name)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Generated folder not found")

    target = safe_join(folder, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found")

    return {
        "folder_name": folder_name,
        "path": path,
        "content": target.read_text(encoding="utf-8", errors="replace")
    }

@app.post("/api/system/reload-nginx")
def reload_nginx():
    try:
        result = subprocess.run(
            ["sudo", "/usr/bin/systemctl", "reload", "nginx"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload nginx: {e}")
