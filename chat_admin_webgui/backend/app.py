from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import subprocess
import requests
import shutil
import json
import uuid

app = FastAPI(title="404DonkeyNotFound")

OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_BASE_DIR = Path("/opt/chat_admin_webgui").resolve()
BASE_DIR = DEPLOY_BASE_DIR if DEPLOY_BASE_DIR.exists() else (REPO_ROOT / "chat_admin_webgui").resolve()
CHAT_ROOT = (BASE_DIR / "frontend" / "chat").resolve()
ADMIN_ROOT = (BASE_DIR / "frontend" / "admin").resolve()
EDIT_ROOT = (BASE_DIR / "editable" / "chat_site").resolve()
BACKUP_ROOT = (BASE_DIR / "backups").resolve()
SHARED_ROOT = (BASE_DIR / "shared_folders").resolve()
DATA_ROOT = (BASE_DIR / "data").resolve()
CHATS_ROOT = (DATA_ROOT / "chats").resolve()
PROJECTS_FILE = (DATA_ROOT / "projects" / "projects.json").resolve()
SYNC_SCRIPT = (REPO_ROOT / "sync_and_push.sh").resolve()

ALLOWED_EDIT_SUFFIXES = {".html", ".css", ".js", ".txt", ".json", ".md", ".yaml", ".yml", ".py", ".sh"}

MODEL_INFO = {
    "qwen3:8b": "Balanced general-purpose model. Good for chat, code, Linux help, and website edits.",
    "qwen3:4b": "Smaller and faster than qwen3:8b. Good when you want lighter resource usage.",
    "llama3.1:8b": "Strong general assistant model. Good for writing, explanations, and coding support.",
    "deepseek-r1:8b": "Reasoning-focused model. Good for step-by-step analysis and harder technical tasks.",
    "phi4": "Compact model with good performance for general assistant work and coding help.",
    "gemma2:9b": "General-purpose model. Good for text generation and structured responses.",
    "mistral-nemo": "Good for broad assistant tasks and long-context work."
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def support_api_prefix(request: Request, call_next):
    if request.scope["path"].startswith("/api/"):
        request.scope["path"] = request.scope["path"][4:] or "/"
    return await call_next(request)


class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list
    stream: bool = False


class ReadFileRequest(BaseModel):
    section: str
    relative_path: str


class SaveFileRequest(BaseModel):
    section: str
    relative_path: str
    content: str


class RollbackRequest(BaseModel):
    section: str
    relative_path: str
    backup_name: str


class ImproveWebsiteRequest(BaseModel):
    model: str = DEFAULT_MODEL
    task: str
    target_files: list[str] = []
    section: str = "chat"


class SharedReadRequest(BaseModel):
    folder_name: str
    relative_path: str


class SharedSaveRequest(BaseModel):
    folder_name: str
    relative_path: str
    content: str


class SharedImproveRequest(BaseModel):
    model: str = DEFAULT_MODEL
    folder_name: str
    task: str
    target_files: list[str]


class SaveProjectRequest(BaseModel):
    name: str


class SaveChatRequest(BaseModel):
    title: str
    project: str = "General"
    messages: list
    model: str = DEFAULT_MODEL
    chat_id: str | None = None


class DeleteProjectRequest(BaseModel):
    name: str


class DeleteChatRequest(BaseModel):
    chat_id: str


class GitSyncRequest(BaseModel):
    branch: str = "dev"
    message: str | None = None


def ensure_data_files():
    CHATS_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text("[]", encoding="utf-8")


def read_projects():
    ensure_data_files()
    try:
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def write_projects(projects):
    ensure_data_files()
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def list_chat_meta():
    ensure_data_files()
    items = []
    for f in sorted(CHATS_ROOT.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", f.stem),
                "project": data.get("project", "General"),
                "model": data.get("model", DEFAULT_MODEL),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", []))
            })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


def get_chat_file(chat_id: str) -> Path:
    ensure_data_files()
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    if not safe_id:
        raise HTTPException(status_code=400, detail="Invalid chat id")
    return (CHATS_ROOT / f"{safe_id}.json").resolve()


def get_root(section: str) -> Path:
    if section == "chat":
        return CHAT_ROOT
    if section == "admin":
        return ADMIN_ROOT
    if section == "editable":
        return EDIT_ROOT
    raise HTTPException(status_code=400, detail=f"Unknown section: {section}")


def safe_join(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path not allowed")
    return target


def validate_editable_file(path: Path):
    if path.suffix.lower() not in ALLOWED_EDIT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {path.suffix}")


def backup_file(section: str, target: Path, root: Path):
    if not target.exists() or not target.is_file():
        return None
    rel = target.relative_to(root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (BACKUP_ROOT / section / rel.parent / rel.name).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file_path = backup_dir / f"{timestamp}.bak"
    shutil.copy2(target, backup_file_path)
    return backup_file_path


def collect_files_for_context(section: str, files: list[str]):
    root = get_root(section)
    chunks = []
    for rel in files:
        target = safe_join(root, rel)
        validate_editable_file(target)
        if target.exists() and target.is_file():
            content = target.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"--- FILE: {rel} ---\n{content}\n")
    return "\n".join(chunks)


def get_shared_folder_root(folder_name: str) -> Path:
    folder = safe_join(SHARED_ROOT, folder_name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def collect_shared_files(folder_name: str, files: list[str]):
    root = get_shared_folder_root(folder_name)
    chunks = []
    for rel in files:
        target = safe_join(root, rel)
        validate_editable_file(target)
        if target.exists() and target.is_file():
            content = target.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"--- FILE: {rel} ---\n{content}\n")
    return "\n".join(chunks)


@app.get("/health")
def health():
    return {"status": "ok", "app": "404DonkeyNotFound", "base_dir": str(BASE_DIR)}


@app.get("/models")
def models():
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        models = data.get("models", [])
        enriched = []
        for m in models:
            name = m.get("name", "")
            info = MODEL_INFO.get(name, "Installed Ollama model. Use it for chat or file improvement tasks.")
            enriched.append({
                "name": name,
                "details": m,
                "description": info
            })
        return {"models": enriched}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load models: {e}")


@app.post("/chat/messages")
def chat(req: ChatRequest):
    try:
        r = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": req.model,
                "messages": req.messages,
                "stream": req.stream
            },
            timeout=300
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to chat with Ollama: {e}")


@app.get("/chat/state")
def chat_state():
    ensure_data_files()
    projects = read_projects()
    if "General" not in projects:
        projects = ["General", *projects]
    return {
        "brand": "404DonkeyNotFound",
        "slogan": "if it works, make sure donkey can break IT!",
        "projects": projects,
        "chats": list_chat_meta(),
        "storage": {
            "base_dir": str(BASE_DIR),
            "projects_file": str(PROJECTS_FILE),
            "chats_dir": str(CHATS_ROOT),
        }
    }


@app.post("/chat/project/save")
def chat_project_save(req: SaveProjectRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    projects = read_projects()
    if name not in projects:
        projects.append(name)
        projects.sort()
        write_projects(projects)
    return {"status": "saved", "project": name, "projects": projects}


@app.post("/chat/project/delete")
def chat_project_delete(req: DeleteProjectRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    projects = read_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    remaining = [project for project in projects if project != name]
    write_projects(remaining)

    for chat_file in CHATS_ROOT.glob("*.json"):
        try:
            payload = json.loads(chat_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("project") == name:
            chat_file.unlink(missing_ok=True)

    return {"status": "deleted", "project": name, "projects": remaining}


@app.post("/chat/session/save")
def chat_session_save(req: SaveChatRequest):
    title = req.title.strip()
    project = req.project.strip() or "General"
    if not title:
        raise HTTPException(status_code=400, detail="Chat title is required")

    projects = read_projects()
    if project != "General" and project not in projects:
        projects.append(project)
        projects.sort()
        write_projects(projects)

    chat_id = req.chat_id.strip() if req.chat_id else str(uuid.uuid4())
    chat_file = get_chat_file(chat_id)
    now = datetime.utcnow().isoformat() + "Z"
    payload = {
        "id": chat_id,
        "title": title,
        "project": project,
        "model": req.model,
        "updated_at": now,
        "messages": req.messages
    }

    chat_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "saved", "chat_id": chat_id, "title": title, "project": project}


@app.post("/chat/session/delete")
def chat_session_delete(req: DeleteChatRequest):
    chat_file = get_chat_file(req.chat_id)
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_file.unlink()
    return {"status": "deleted", "chat_id": req.chat_id}


@app.get("/chat/session/read")
def chat_session_read(chat_id: str):
    chat_file = get_chat_file(chat_id)
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    return json.loads(chat_file.read_text(encoding="utf-8"))


@app.get("/admin/files")
def admin_list_files(section: str):
    root = get_root(section)
    root.mkdir(parents=True, exist_ok=True)
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_EDIT_SUFFIXES:
            files.append(str(p.relative_to(root)))
    return {"section": section, "files": sorted(files)}


@app.post("/admin/read")
def admin_read_file(req: ReadFileRequest):
    root = get_root(req.section)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "section": req.section,
        "path": str(target.relative_to(root)),
        "content": target.read_text(encoding="utf-8", errors="replace")
    }


@app.post("/admin/save")
def admin_save_file(req: SaveFileRequest):
    root = get_root(req.section)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_file(req.section, target, root)
    target.write_text(req.content, encoding="utf-8")
    return {
        "status": "saved",
        "section": req.section,
        "path": str(target.relative_to(root)),
        "backup_created": str(backup_path) if backup_path else None
    }


@app.get("/admin/backups")
def admin_list_backups(section: str, relative_path: str):
    root = get_root(section)
    target = safe_join(root, relative_path)
    validate_editable_file(target)
    rel = target.relative_to(root)
    backup_dir = (BACKUP_ROOT / section / rel.parent / rel.name).resolve()
    if not backup_dir.exists():
        return {"section": section, "relative_path": relative_path, "backups": []}
    backups = [p.name for p in sorted(backup_dir.glob("*.bak"), reverse=True)]
    return {"section": section, "relative_path": relative_path, "backups": backups}


@app.get("/admin/backup/read")
def admin_read_backup(section: str, relative_path: str, backup_name: str):
    root = get_root(section)
    target = safe_join(root, relative_path)
    validate_editable_file(target)
    rel = target.relative_to(root)
    backup_dir = (BACKUP_ROOT / section / rel.parent / rel.name).resolve()
    backup_file_path = safe_join(backup_dir, backup_name)
    if not backup_file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return {
        "section": section,
        "relative_path": relative_path,
        "backup_name": backup_name,
        "content": backup_file_path.read_text(encoding="utf-8", errors="replace")
    }


@app.post("/admin/rollback")
def admin_rollback(req: RollbackRequest):
    root = get_root(req.section)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    rel = target.relative_to(root)
    backup_dir = (BACKUP_ROOT / req.section / rel.parent / rel.name).resolve()
    backup_file_path = safe_join(backup_dir, req.backup_name)
    if not backup_file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    target.parent.mkdir(parents=True, exist_ok=True)
    current_backup = backup_file(req.section, target, root)
    shutil.copy2(backup_file_path, target)
    return {
        "status": "rolled_back",
        "section": req.section,
        "path": str(target.relative_to(root)),
        "restored_from": req.backup_name,
        "previous_version_backup": str(current_backup) if current_backup else None
    }


@app.post("/admin/improve")
def admin_improve_website(req: ImproveWebsiteRequest):
    if not req.target_files:
        raise HTTPException(status_code=400, detail="No target files selected")
    context = collect_files_for_context(req.section, req.target_files)
    if not context.strip():
        raise HTTPException(status_code=400, detail="No readable files found for context")
    prompt = f"""
You are helping improve a website.

SECTION:
{req.section}

TASK:
{req.task}

CURRENT FILES:
{context}

Return ONLY valid JSON in this format:
{{
  "summary": "short explanation",
  "files": {{
    "index.html": "full updated file content",
    "style.css": "full updated file content",
    "app.js": "full updated file content"
  }}
}}

Rules:
- Return only JSON
- Include only files that should change
- Always return full file contents, not partial diffs
- Keep HTML, CSS, and JS consistent with each other
"""
    try:
        r = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": req.model,
                "messages": [
                    {"role": "system", "content": "You are an expert web UI assistant that updates website files and returns valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            },
            timeout=600
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ask Ollama for improvement: {e}")
    raw = data.get("message", {}).get("content", "")
    if not raw:
        raise HTTPException(status_code=500, detail="Ollama returned empty response")
    try:
        parsed = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(status_code=500, detail="Ollama did not return valid JSON")
        parsed = json.loads(raw[start:end+1])
    return parsed


@app.get("/admin/shared-folders")
def admin_list_shared_folders():
    SHARED_ROOT.mkdir(parents=True, exist_ok=True)
    folders = [p.name for p in SHARED_ROOT.iterdir() if p.is_dir()]
    return {"folders": sorted(folders)}


@app.get("/admin/shared-files")
def admin_list_shared_files(folder_name: str):
    root = get_shared_folder_root(folder_name)
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_EDIT_SUFFIXES:
            files.append(str(p.relative_to(root)))
    return {"folder_name": folder_name, "files": sorted(files)}


@app.post("/admin/shared-read")
def admin_shared_read(req: SharedReadRequest):
    root = get_shared_folder_root(req.folder_name)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Shared file not found")
    return {
        "folder_name": req.folder_name,
        "path": req.relative_path,
        "content": target.read_text(encoding="utf-8", errors="replace")
    }


@app.post("/admin/shared-save")
def admin_shared_save(req: SharedSaveRequest):
    root = get_shared_folder_root(req.folder_name)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "folder_name": req.folder_name, "path": req.relative_path}


@app.post("/admin/shared-improve")
def admin_shared_improve(req: SharedImproveRequest):
    if not req.target_files:
        raise HTTPException(status_code=400, detail="No target files selected")
    context = collect_shared_files(req.folder_name, req.target_files)
    if not context.strip():
        raise HTTPException(status_code=400, detail="No readable shared files found for context")
    prompt = f"""
You are helping improve files from a project folder.

FOLDER:
{req.folder_name}

TASK:
{req.task}

CURRENT FILES:
{context}

Return ONLY valid JSON in this format:
{{
  "summary": "short explanation",
  "files": {{
    "some/file.txt": "full updated content"
  }}
}}

Rules:
- Return only JSON
- Include only files that should change
- Always return full file contents
"""
    try:
        r = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": req.model,
                "messages": [
                    {"role": "system", "content": "You improve project files and return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            },
            timeout=600
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ask Ollama for shared-folder improvement: {e}")
    raw = data.get("message", {}).get("content", "")
    if not raw:
        raise HTTPException(status_code=500, detail="Ollama returned empty response")
    try:
        parsed = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(status_code=500, detail="Ollama did not return valid JSON")
        parsed = json.loads(raw[start:end+1])
    return parsed


@app.post("/admin/git/sync")
def admin_git_sync(req: GitSyncRequest):
    branch = (req.branch or "dev").strip() or "dev"
    message = (req.message or f"AI website update {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%SZ')}").strip()

    if not SYNC_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Sync script not found: {SYNC_SCRIPT}")

    try:
        result = subprocess.run(
            [str(SYNC_SCRIPT), branch, message],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run git sync: {e}")

    response = {
        "status": "ok" if result.returncode == 0 else "failed",
        "branch": branch,
        "message": message,
        "code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "script": str(SYNC_SCRIPT),
    }
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=response)
    return response


@app.get("/admin", include_in_schema=False)
def admin_redirect():
    return RedirectResponse(url="/admin/")


@app.get("/portal", include_in_schema=False)
def portal_redirect():
    return RedirectResponse(url="/admin/")


@app.get("/editable", include_in_schema=False)
def editable_redirect():
    return RedirectResponse(url="/editable/")


app.mount("/admin", StaticFiles(directory=ADMIN_ROOT, html=True), name="admin")
app.mount("/portal", StaticFiles(directory=ADMIN_ROOT, html=True), name="portal")
app.mount("/editable", StaticFiles(directory=EDIT_ROOT, html=True), name="editable")
app.mount("/", StaticFiles(directory=CHAT_ROOT, html=True), name="chat")
