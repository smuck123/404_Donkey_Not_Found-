from fastapi import FastAPI, HTTPException, Query, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import shutil
import shutil as pyshutil
import json
import uuid
import subprocess
import re
import difflib
import base64
import mimetypes
import os


app = FastAPI(title="404DonkeyNotFound")

OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3:8b"
SEARCH_API_URL = "http://127.0.0.1:8020/search"

BASE_DIR = Path(__file__).resolve().parent.parent
CHAT_ROOT = (BASE_DIR / "frontend" / "chat").resolve()
ADMIN_ROOT = (BASE_DIR / "frontend" / "admin").resolve()
EDIT_ROOT = (BASE_DIR / "editable" / "chat_site").resolve()
BACKUP_ROOT = (BASE_DIR / "backups").resolve()
SHARED_ROOT = (BASE_DIR / "shared_folders").resolve()
DATA_ROOT = (BASE_DIR / "data").resolve()
CHATS_ROOT = (DATA_ROOT / "chats").resolve()
PROJECTS_FILE = (DATA_ROOT / "projects" / "projects.json").resolve()
REPOS_ROOT = (BASE_DIR / "repos").resolve()
DOWNLOADS_ROOT = (BASE_DIR / "downloads").resolve()
EXPORTS_ROOT = (BASE_DIR / "exports").resolve()
IMAGES_ROOT = (DATA_ROOT / "images").resolve()
REPO_TEMPLATES_ROOT = (DATA_ROOT / "repo_templates").resolve()
REPO_TEMPLATES_META_ROOT = (DATA_ROOT / "repo_templates_meta").resolve()
LEARNING_ROOT = (DATA_ROOT / "learning_library").resolve()
GENERATED_IMAGES_ROOT = (DATA_ROOT / "generated_images").resolve()

IMAGE_BACKEND_URL = os.getenv("IMAGE_BACKEND_URL", "http://127.0.0.1:7860/sdapi/v1/txt2img")
IMAGE_BACKEND_TIMEOUT = int(os.getenv("IMAGE_BACKEND_TIMEOUT", "300"))
IMAGE_REWRITE_TIMEOUT = int(os.getenv("IMAGE_REWRITE_TIMEOUT", "120"))
MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "2048"))
MAX_IMAGE_STEPS = int(os.getenv("MAX_IMAGE_STEPS", "150"))
MAX_LEARNING_UPLOAD_BYTES = int(os.getenv("MAX_LEARNING_UPLOAD_BYTES", str(2 * 1024 * 1024)))

ALLOWED_EDIT_SUFFIXES = {
    ".html", ".css", ".js", ".txt", ".json", ".md", ".yaml", ".yml",
    ".py", ".sh", ".php", ".xml", ".conf", ".ini", ".svg"
}

ALLOWED_LEARNING_UPLOAD_SUFFIXES = {
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".xml", ".csv",
    ".log", ".py", ".js", ".ts", ".html", ".css", ".ini", ".conf", ".cfg",
    ".sh", ".sql"
}

MODEL_INFO = {
    "qwen3:8b": "Balanced general-purpose model. Good for chat, code, Linux help, and website edits.",
    "qwen3:4b": "Smaller and faster than qwen3:8b. Good when you want lighter resource usage.",
    "llama3.1:8b": "Strong general assistant model. Good for writing, explanations, and coding support.",
    "deepseek-r1:8b": "Reasoning-focused model. Good for step-by-step analysis and harder technical tasks.",
    "phi4:latest": "Compact model with good performance for general assistant work and coding help.",
    "gemma2:9b": "General-purpose model. Good for text generation and structured responses.",
    "mistral-nemo:latest": "Good for broad assistant tasks and long-context work."
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list
    stream: bool = False


class RetrievalChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: list
    stream: bool = False
    source_types: list[str] | None = None
    path_contains: str | None = None
    use_retrieval: bool = True
    selected_template: str | None = None
    selected_learning_ids: list[str] | None = None


class SourceViewRequest(BaseModel):
    source_type: str
    path: str
    repo_name: str | None = None
    template_name: str | None = None
    section: str | None = None

class ChatEditPlanRequest(BaseModel):
    model: str = DEFAULT_MODEL
    instruction: str
    selected_template: str | None = None
    selected_repo: str | None = None
    target_paths: list[str] | None = None
    selected_learning_ids: list[str] | None = None

class ApplyEditRequest(BaseModel):
    repo_name: str
    files: dict[str, str]

class GitCommitPushRequest(BaseModel):
    repo_name: str
    commit_message: str
    branch: str | None = None
    push: bool = True

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
    template: str | None = None
    repo: str | None = None
    learning_ids: list[str] = []

class RepoCloneRequest(BaseModel):
    repo_url: str
    repo_name: str | None = None

class RepoFileRequest(BaseModel):
    repo_name: str
    relative_path: str

class RepoSaveRequest(BaseModel):
    repo_name: str
    relative_path: str
    content: str

class RepoImproveRequest(BaseModel):
    model: str = DEFAULT_MODEL
    repo_name: str
    task: str
    target_files: list[str]

class WebFetchRequest(BaseModel):
    url: str

class SummarizeTextRequest(BaseModel):
    model: str = DEFAULT_MODEL
    text: str
    task: str = "Summarize this clearly."

class WebSummarizeRequest(BaseModel):
    model: str = DEFAULT_MODEL
    url: str
    task: str = "Summarize this clearly."

class ImagePromptRequest(BaseModel):
    model: str = DEFAULT_MODEL
    user_input: str
    aspect_ratio: str = "16:9"
    accent_color: str | None = None


class ImageGenerateRequest(BaseModel):
    model: str = Field(default="stabilityai/stable-diffusion-xl-base-1.0")
    prompt: str
    negative_prompt: str = ""
    width: int = 832
    height: int = 1216
    steps: int = 30
    guidance: float = 6.5
    format: str = "png"
    rewrite_prompt: bool = True

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions(cls, value: int):
        if value < 256 or value > MAX_IMAGE_DIMENSION:
            raise ValueError(f"Image dimensions must be between 256 and {MAX_IMAGE_DIMENSION}")
        if value % 8 != 0:
            raise ValueError("Image dimensions must be divisible by 8")
        return value

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, value: int):
        if value < 1 or value > MAX_IMAGE_STEPS:
            raise ValueError(f"Steps must be between 1 and {MAX_IMAGE_STEPS}")
        return value

    @field_validator("guidance")
    @classmethod
    def validate_guidance(cls, value: float):
        if value < 1 or value > 20:
            raise ValueError("Guidance must be between 1 and 20")
        return value

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str):
        normalized = (value or "png").strip().lower()
        if normalized not in {"png", "jpg", "jpeg", "webp"}:
            raise ValueError("Format must be png, jpg, jpeg, or webp")
        return "jpg" if normalized == "jpeg" else normalized


class RepoTemplateSaveRequest(BaseModel):
    repo_name: str
    template_name: str
    selected_files: list[str] = []

class RepoTemplateDeleteRequest(BaseModel):
    template_name: str

class ExportTextRequest(BaseModel):
    filename: str
    content: str

class LearningItemSaveRequest(BaseModel):
    title: str
    category: str = "reference"
    tags: list[str] = []
    content: str

class LearningBatchSaveRequest(BaseModel):
    items: list[LearningItemSaveRequest]


class LearningUrlImportRequest(BaseModel):
    url: str
    title: str | None = None
    category: str = "web-reference"
    tags: list[str] = []


class SaveImageRequest(BaseModel):
    svg: str
    prompt: str = ""
    model_workflow: str = "study-image-studio"
    width: int
    height: int
    title: str = "Study card"

def ensure_data_files():
    CHATS_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPOS_ROOT.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    REPO_TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
    REPO_TEMPLATES_META_ROOT.mkdir(parents=True, exist_ok=True)
    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text("[]", encoding="utf-8")

def build_image_urls(filename: str) -> dict:
    return {
        "download_url": f"/api/images/download?filename={filename}",
        "preview_url": f"/api/images/preview?filename={filename}"
    }


def get_generated_image_file(filename: str) -> Path:
    safe_name = safe_slug(filename, "image")
    target = (GENERATED_IMAGES_ROOT / safe_name).resolve()
    if not str(target).startswith(str(GENERATED_IMAGES_ROOT)):
        raise HTTPException(status_code=403, detail="Generated image path not allowed")
    return target


def maybe_rewrite_image_prompt(req: ImageGenerateRequest) -> str:
    if not req.rewrite_prompt:
        return req.prompt
    system_text = (
        "You rewrite image-generation prompts for a diffusion model. "
        "Return only the improved prompt text with no JSON, markdown, or commentary. "
        "Preserve the user intent and keep it concise but vivid."
    )
    user_text = (
        f"Original prompt:\n{req.prompt}\n\n"
        f"Negative prompt:\n{req.negative_prompt or '(none)'}\n\n"
        f"Target size: {req.width}x{req.height}.\n"
        "Improve this for text-to-image generation."
    )
    try:
        rewritten = ask_ollama_text(req.model, system_text, user_text, timeout=IMAGE_REWRITE_TIMEOUT).strip()
        return rewritten or req.prompt
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Timed out while rewriting the image prompt with Ollama")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to rewrite image prompt with Ollama: {e}")


def call_image_backend(req: ImageGenerateRequest, final_prompt: str) -> tuple[bytes, str]:
    payload = {
        "prompt": final_prompt,
        "negative_prompt": req.negative_prompt,
        "width": req.width,
        "height": req.height,
        "steps": req.steps,
        "cfg_scale": req.guidance,
        "sampler_name": "Euler a",
        "send_images": True,
        "save_images": False
    }
    if req.model:
        payload["override_settings"] = {"sd_model_checkpoint": req.model}

    try:
        r = requests.post(IMAGE_BACKEND_URL, json=payload, timeout=IMAGE_BACKEND_TIMEOUT)
        r.raise_for_status()
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Timed out while generating the image")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Image backend request failed: {e}")

    try:
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image backend returned invalid JSON: {e}")

    images = data.get("images") or []
    if not images:
        raise HTTPException(status_code=500, detail="Image backend returned no images")

    image_b64 = images[0]
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decode generated image: {e}")

    output_format = req.format
    info = data.get("info")
    if isinstance(info, str):
        try:
            info = json.loads(info)
        except Exception:
            info = None
    if isinstance(info, dict):
        backend_format = (info.get("format") or "").lower()
        if backend_format in {"png", "jpg", "jpeg", "webp"}:
            output_format = "jpg" if backend_format == "jpeg" else backend_format

    return image_bytes, output_format


def detect_image_extension(image_bytes: bytes, fallback: str) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return fallback


def save_generated_image(image_bytes: bytes, output_format: str) -> str:
    ensure_data_files()
    actual_format = detect_image_extension(image_bytes, output_format)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"image_{timestamp}_{uuid.uuid4().hex[:8]}.{actual_format}"
    target = get_generated_image_file(filename)
    target.write_bytes(image_bytes)
    return filename


def safe_slug(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("._-")
    return slug or fallback

def get_image_file(image_id: str, suffix: str) -> Path:
    safe_id = safe_slug(image_id, "image")
    target = (IMAGES_ROOT / f"{safe_id}{suffix}").resolve()
    if not str(target).startswith(str(IMAGES_ROOT)):
        raise HTTPException(status_code=403, detail="Image path not allowed")
    return target

def serialize_image_metadata(meta: dict) -> dict:
    dimensions = meta.get("dimensions") or {}
    return {
        "image_id": meta.get("image_id", ""),
        "title": meta.get("title", ""),
        "prompt": meta.get("prompt", ""),
        "model_workflow": meta.get("model/workflow", ""),
        "created_timestamp": meta.get("created_timestamp", ""),
        "dimensions": {
            "width": int(dimensions.get("width", 0) or 0),
            "height": int(dimensions.get("height", 0) or 0),
        },
        "file_path": meta.get("file_path", ""),
        "filename": meta.get("filename", ""),
        "download_url": f"/api/images/read/{meta.get('image_id', '')}",
    }

def load_image_metadata(image_id: str) -> tuple[Path, Path, dict]:
    svg_path = get_image_file(image_id, ".svg")
    meta_path = get_image_file(image_id, ".json")
    if not svg_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image metadata unreadable: {exc}")
    return svg_path, meta_path, meta

def get_learning_item_file(item_id: str) -> Path:
    safe_id = safe_slug(item_id, "item")
    target = (LEARNING_ROOT / f"{safe_id}.json").resolve()
    if not str(target).startswith(str(LEARNING_ROOT)):
        raise HTTPException(status_code=403, detail="Learning item path not allowed")
    return target

def list_learning_items():
    ensure_data_files()
    items = []
    for f in sorted(LEARNING_ROOT.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", f.stem),
                "category": data.get("category", "reference"),
                "tags": data.get("tags", []),
                "updated_at": data.get("updated_at", ""),
                "content_preview": data.get("content", "")[:220]
            })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items

def load_learning_context(item_ids: list[str] | None, max_chars: int = 24000):
    if not item_ids:
        return ""
    chunks = []
    total = 0
    for item_id in item_ids:
        target = get_learning_item_file(item_id)
        if not target.exists():
            continue
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            continue
        block = (
            f"--- LEARNING ITEM: {data.get('title', item_id)} ---\n"
            f"CATEGORY: {data.get('category', 'reference')}\n"
            f"TAGS: {', '.join(data.get('tags', []))}\n"
            f"{data.get('content', '')}\n"
        )
        if total + len(block) > max_chars:
            break
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks)

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

def collect_files_for_context(root: Path, files: list[str]):
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

def get_repo_root(repo_name: str) -> Path:
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', repo_name.strip())
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid repo name")
    root = (REPOS_ROOT / safe_name).resolve()
    if not str(root).startswith(str(REPOS_ROOT)):
        raise HTTPException(status_code=403, detail="Repo path not allowed")
    return root



def get_repo_template_root(template_name: str) -> Path:
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', template_name.strip())
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid template name")
    root = (REPO_TEMPLATES_ROOT / safe_name).resolve()
    if not str(root).startswith(str(REPO_TEMPLATES_ROOT)):
        raise HTTPException(status_code=403, detail="Template path not allowed")
    return root

def get_repo_template_meta_file(template_name: str) -> Path:
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', template_name.strip())
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid template name")
    meta = (REPO_TEMPLATES_META_ROOT / f"{safe_name}.json").resolve()
    if not str(meta).startswith(str(REPO_TEMPLATES_META_ROOT)):
        raise HTTPException(status_code=403, detail="Template meta path not allowed")
    return meta

def repo_name_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
    return name or f"repo_{uuid.uuid4().hex[:8]}"

def ask_ollama_json(model: str, system_text: str, user_text: str, timeout: int = 600):
    r = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text}
            ],
            "stream": False
        },
        timeout=timeout
    )
    r.raise_for_status()
    data = r.json()
    raw = data.get("message", {}).get("content", "")
    if not raw:
        raise HTTPException(status_code=500, detail="Ollama returned empty response")
    try:
        return json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(status_code=500, detail="Ollama did not return valid JSON")
        return json.loads(raw[start:end+1])

def ask_ollama_text(model: str, system_text: str, user_text: str, timeout: int = 600):
    r = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text}
            ],
            "stream": False
        },
        timeout=timeout
    )
    r.raise_for_status()
    data = r.json()
    return data.get("message", {}).get("content", "")

def ask_ollama_with_images(model: str, system_text: str, user_text: str, images: list[str], timeout: int = 600):
    r = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text, "images": images}
            ],
            "stream": False
        },
        timeout=timeout
    )
    r.raise_for_status()
    data = r.json()
    return data.get("message", {}).get("content", "")

def wrap_text(text: str, max_chars: int, max_lines: int = 4):
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        if len(proposed) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = proposed
    if current:
        lines.append(current)
    return lines[:max_lines]

def escape_xml(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def svg_text_block(lines: list[str], x: int, start_y: int, line_height: int, size: int, color: str, weight: int = 400):
    out = []
    for idx, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{start_y + (idx * line_height)}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" font-family="Arial, sans-serif">{escape_xml(line)}</text>'
        )
    return "".join(out)

def normalize_aspect_ratio(value: str | None) -> str:
    mapping = {
        "landscape": "16:9",
        "square": "1:1",
        "portrait": "4:5",
        "16:9": "16:9",
        "1:1": "1:1",
        "4:5": "4:5",
    }
    return mapping.get((value or "").strip().lower(), "16:9")

def build_structured_image_prompt(model: str, user_input: str, aspect_ratio: str = "16:9"):
    normalized_ratio = normalize_aspect_ratio(aspect_ratio)
    prompt = f"""
Convert the user's image request into safe, production-ready JSON for an image backend.

Return ONLY valid JSON with this exact shape:
{{
  "final_prompt": "detailed prompt for the image model",
  "negative_prompt": "things the image model should avoid",
  "style_tags": ["tag1", "tag2"],
  "aspect_ratio": "{normalized_ratio}",
  "safety_notes": ["note 1", "note 2"]
}}

Requirements:
- final_prompt must be concise but specific, written as a direct image-generation prompt.
- negative_prompt should remove low-quality artifacts, unreadable text, clutter, distortion, and unsafe elements.
- style_tags must be short lowercase tags.
- aspect_ratio must be one of: 16:9, 1:1, 4:5.
- safety_notes must mention policy-sensitive concerns or say that no additional issues were found.
- Preserve the user's core intent while making the result visually coherent.
- Do not include markdown or commentary.

USER INPUT:
{user_input}
"""
    structured = ask_ollama_json(
        model,
        "You convert user image requests into valid JSON prompts for an image backend. Return JSON only.",
        prompt
    )
    return {
        "final_prompt": (structured.get("final_prompt") or "").strip(),
        "negative_prompt": (structured.get("negative_prompt") or "").strip(),
        "style_tags": [str(tag).strip().lower() for tag in structured.get("style_tags", []) if str(tag).strip()][:8],
        "aspect_ratio": normalize_aspect_ratio(structured.get("aspect_ratio") or normalized_ratio),
        "safety_notes": [str(note).strip() for note in structured.get("safety_notes", []) if str(note).strip()][:6],
    }

def render_image_backend_svg(structured_prompt: dict, accent_color: str | None = None):
    ratio = normalize_aspect_ratio(structured_prompt.get("aspect_ratio"))
    sizes = {
        "16:9": {"width": 1600, "height": 900, "title_chars": 28, "body_chars": 42},
        "1:1": {"width": 1080, "height": 1080, "title_chars": 22, "body_chars": 30},
        "4:5": {"width": 1080, "height": 1350, "title_chars": 22, "body_chars": 30},
    }
    layout = sizes[ratio]
    width = layout["width"]
    height = layout["height"]
    accent = accent_color.strip() if accent_color and accent_color.strip() else "#38bdf8"

    prompt_lines = wrap_text(structured_prompt.get("final_prompt", ""), layout["title_chars"], 4)
    style_tags = structured_prompt.get("style_tags", [])
    negative_prompt = structured_prompt.get("negative_prompt", "")
    safety_notes = structured_prompt.get("safety_notes", [])

    subtitle = ", ".join(style_tags[:4]) or "Structured prompt generated by Ollama"
    subtitle_lines = wrap_text(subtitle, layout["body_chars"], 3)
    notes = [f"Negative: {negative_prompt}"] if negative_prompt else []
    notes.extend([f"Safety: {note}" for note in safety_notes[:3]])
    bullet_lines = []
    for item in notes:
        bullet_lines.extend(wrap_text(f"• {item}", layout["body_chars"], 2))

    bullet_start_y = 710 if ratio == "4:5" else 590
    title_y = 270 if ratio == "4:5" else 250
    subtitle_y = 470 if ratio == "4:5" else 430
    title_size = 54 if ratio == "4:5" else 64

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{escape_xml(accent)}"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="{width - 120}" cy="120" r="180" fill="{escape_xml(accent)}" opacity="0.15"/>
  <circle cx="140" cy="{height - 120}" r="220" fill="{escape_xml(accent)}" opacity="0.08"/>
  <rect x="60" y="60" width="{width - 120}" height="{height - 120}" rx="36" fill="#0f172a" fill-opacity="0.35" stroke="#ffffff" stroke-opacity="0.10"/>
  <text x="110" y="140" fill="{escape_xml(accent)}" font-size="36" font-weight="700" font-family="Arial, sans-serif">404DonkeyNotFound image backend</text>
  {svg_text_block(prompt_lines, 110, title_y, 74, title_size, "#ffffff", 700)}
  {svg_text_block(subtitle_lines, 110, subtitle_y, 42, 28, "#cbd5e1", 400)}
  {svg_text_block(bullet_lines, 130, bullet_start_y, 40, 26, "#f8fafc", 400)}
  <rect x="110" y="{height - 150}" width="{min(width - 220, 520)}" height="10" rx="5" fill="url(#accent)"/>
  <text x="110" y="{height - 90}" fill="#93c5fd" font-size="28" font-weight="600" font-family="Arial, sans-serif">Prompt packaged for image generation</text>
</svg>""".strip()
    return {
        "svg": svg,
        "mime_type": "image/svg+xml",
        "width": width,
        "height": height,
        "aspect_ratio": ratio
    }



def search_local_context(query: str, top_k: int = 6, source_types=None, path_contains=None):
    payload = {
        "query": query,
        "top_k": top_k
    }
    if source_types:
        payload["source_types"] = source_types
    if path_contains:
        payload["path_contains"] = path_contains

    r = requests.post(SEARCH_API_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json().get("results", [])



TEMPLATE_BASE = str(BASE_DIR / "data" / "repo_templates")


REPO_BASE = str(BASE_DIR / "repos")

def load_repo_content(repo_name: str, max_chars=12000):
    import os
    base = os.path.join(REPO_BASE, repo_name)
    if not os.path.isdir(base):
        return ""
    out, total = [], 0
    for root, _, files in os.walk(base):
        if ".git" in root:
            continue
        for f in files:
            pth = os.path.join(root, f)
            try:
                with open(pth, "r", errors="ignore") as fh:
                    content = fh.read(1500)
                rel = os.path.relpath(pth, base)
                chunk = f"\n--- REPO FILE: {rel} ---\n{content}\n"
                total += len(chunk)
                if total > max_chars:
                    return "\n".join(out)
                out.append(chunk)
            except:
                continue
    return "\n".join(out)

def load_template_content(template_name: str, max_chars=12000):
    base = os.path.join(TEMPLATE_BASE, template_name)
    if not os.path.isdir(base):
        return ""

    collected = []
    total = 0

    for root, _, files in os.walk(base):
        for f in files:
            path = os.path.join(root, f)
            try:
                with open(path, "r", errors="ignore") as fh:
                    content = fh.read(2000)
                    rel = os.path.relpath(path, base)
                    chunk = f"\n--- FILE: {rel} ---\n{content}\n"
                    total += len(chunk)
                    if total > max_chars:
                        return "\n".join(collected)
                    collected.append(chunk)
            except:
                continue

    return "\n".join(collected)

def build_retrieval_context(results):
    if not results:
        return ""

    parts = []
    for i, item in enumerate(results, start=1):
        parts.append(
            f"""--- RESULT {i} ---
SOURCE TYPE: {item.get("source_type","")}
PATH: {item.get("path","")}
SCORE: {item.get("score","")}
CONTENT:
{item.get("content","")}
"""
        )
    return "\n".join(parts)

def fetch_web_text(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    r = requests.get(url, timeout=60, headers={"User-Agent": "404DonkeyNotFound/1.0"})
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    text = r.text
    title = url
    cleaned = text

    if "html" in content_type or "<html" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        cleaned = soup.get_text("\n")
        cleaned = "\n".join(line.strip() for line in cleaned.splitlines() if line.strip())

    return {
        "url": url,
        "title": title,
        "content_type": content_type,
        "content": cleaned[:120000]
    }



@app.get("/")
def serve_chat_ui():
    return FileResponse(str(CHAT_ROOT / "index.html"))


@app.get("/style.css")
def serve_chat_style():
    return FileResponse(str(CHAT_ROOT / "style.css"), media_type="text/css")


@app.get("/app.js")
def serve_chat_script():
    return FileResponse(str(CHAT_ROOT / "app.js"), media_type="application/javascript")


@app.get("/admin/")
def serve_admin_ui():
    return FileResponse(str(ADMIN_ROOT / "index.html"))


@app.get("/admin/style.css")
def serve_admin_style():
    return FileResponse(str(ADMIN_ROOT / "style.css"), media_type="text/css")


@app.get("/admin/app.js")
def serve_admin_script():
    return FileResponse(str(ADMIN_ROOT / "app.js"), media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "app": "404DonkeyNotFound"}

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
            json={"model": req.model, "messages": req.messages, "stream": req.stream},
            timeout=300
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to chat with Ollama: {e}")

@app.get("/chat/state")
def chat_state():
    ensure_data_files()
    return {
        "brand": "404DonkeyNotFound",
        "slogan": "if it works, make sure donkey can break IT!",
        "projects": read_projects(),
        "chats": list_chat_meta(),
        "learning_items": list_learning_items()
    }

@app.get("/chat/learning")
def chat_learning_list():
    return {"items": list_learning_items()}

@app.get("/chat/learning/read")
def chat_learning_read(item_id: str = Query(...)):
    target = get_learning_item_file(item_id)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Learning item not found")
    return json.loads(target.read_text(encoding="utf-8"))

@app.post("/chat/learning/save")
def chat_learning_save(req: LearningItemSaveRequest):
    ensure_data_files()
    title = req.title.strip()
    content = req.content.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    item_id = f"{safe_slug(title, 'learning')}_{uuid.uuid4().hex[:8]}"
    tags = [safe_slug(tag, "") for tag in req.tags if safe_slug(tag, "")]
    now = datetime.utcnow().isoformat() + "Z"
    payload = {
        "id": item_id,
        "title": title,
        "category": req.category.strip() or "reference",
        "tags": tags,
        "content": content,
        "updated_at": now
    }
    get_learning_item_file(item_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "saved", "item": payload}

@app.post("/chat/learning/save-batch")
def chat_learning_save_batch(req: LearningBatchSaveRequest):
    ensure_data_files()
    if not req.items:
        raise HTTPException(status_code=400, detail="At least one learning item is required")

    saved_items = []
    for raw_item in req.items:
        title = raw_item.title.strip()
        content = raw_item.content.strip()
        if not title or not content:
            continue

        item_id = f"{safe_slug(title, 'learning')}_{uuid.uuid4().hex[:8]}"
        tags = [safe_slug(tag, "") for tag in raw_item.tags if safe_slug(tag, "")]
        now = datetime.utcnow().isoformat() + "Z"
        payload = {
            "id": item_id,
            "title": title,
            "category": raw_item.category.strip() or "reference",
            "tags": tags,
            "content": content,
            "updated_at": now
        }
        get_learning_item_file(item_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        saved_items.append(payload)

    if not saved_items:
        raise HTTPException(status_code=400, detail="No valid learning items were provided")

    return {"status": "saved", "count": len(saved_items), "items": saved_items}

@app.post("/chat/learning/import-url")
def chat_learning_import_url(req: LearningUrlImportRequest):
    ensure_data_files()
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    page = fetch_web_text(req.url.strip())
    title = (req.title or "").strip() or page.get("title") or req.url.strip()
    content = (page.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Fetched URL had no readable text content")

    item_id = f"{safe_slug(title, 'learning')}_{uuid.uuid4().hex[:8]}"
    tags = [safe_slug(tag, "") for tag in req.tags if safe_slug(tag, "")]
    now = datetime.utcnow().isoformat() + "Z"
    payload = {
        "id": item_id,
        "title": title,
        "category": req.category.strip() or "web-reference",
        "tags": tags,
        "content": content[:120000],
        "source_url": req.url.strip(),
        "updated_at": now
    }
    get_learning_item_file(item_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "saved", "item": payload}

@app.post("/chat/learning/upload")
async def chat_learning_upload(
    files: list[UploadFile] = File(...),
    category: str = Form("uploaded-reference"),
    tags: str = Form("")
):
    ensure_data_files()
    saved_items = []
    cleaned_tags = [safe_slug(tag, "") for tag in tags.split(",") if safe_slug(tag.strip(), "")]

    for upload in files:
        filename = upload.filename or "upload.txt"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_LEARNING_UPLOAD_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported upload type: {suffix or 'no extension'}")

        content_bytes = await upload.read()
        if not content_bytes:
            continue
        if len(content_bytes) > MAX_LEARNING_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail=f"File too large: {filename}")

        content = content_bytes.decode("utf-8", errors="replace").strip()
        if not content:
            continue

        title = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Uploaded reference"
        item_id = f"{safe_slug(title, 'learning')}_{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat() + "Z"
        payload = {
            "id": item_id,
            "title": title,
            "category": category.strip() or "uploaded-reference",
            "tags": cleaned_tags,
            "content": content,
            "source_filename": filename,
            "updated_at": now
        }
        get_learning_item_file(item_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        saved_items.append(payload)

    if not saved_items:
        raise HTTPException(status_code=400, detail="No readable text files were uploaded")

    return {"status": "saved", "count": len(saved_items), "items": saved_items}

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

@app.post("/chat/session/save")
def chat_session_save(req: SaveChatRequest):
    title = req.title.strip()
    project = req.project.strip() or "General"
    if not title:
        raise HTTPException(status_code=400, detail="Chat title is required")

    projects = read_projects()
    if project not in projects:
        projects.append(project)
        projects.sort()
        write_projects(projects)

    chat_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    payload = {
        "id": chat_id,
        "title": title,
        "project": project,
        "model": req.model,
        "template": (req.template or "").strip(),
        "repo": (req.repo or "").strip(),
        "learning_ids": req.learning_ids or [],
        "updated_at": now,
        "messages": req.messages
    }
    get_chat_file(chat_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "saved", "chat_id": chat_id, "title": title, "project": project}

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
    return {"section": req.section, "path": str(target.relative_to(root)), "content": target.read_text(encoding="utf-8", errors="replace")}

@app.post("/admin/save")
def admin_save_file(req: SaveFileRequest):
    root = get_root(req.section)
    target = safe_join(root, req.relative_path)
    validate_editable_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_file(req.section, target, root)
    target.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "section": req.section, "path": str(target.relative_to(root)), "backup_created": str(backup_path) if backup_path else None}

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
    return {"section": section, "relative_path": relative_path, "backup_name": backup_name, "content": backup_file_path.read_text(encoding="utf-8", errors="replace")}

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
    return {"status": "rolled_back", "section": req.section, "path": str(target.relative_to(root)), "restored_from": req.backup_name, "previous_version_backup": str(current_backup) if current_backup else None}

@app.post("/admin/improve")
def admin_improve_website(req: ImproveWebsiteRequest):
    if not req.target_files:
        raise HTTPException(status_code=400, detail="No target files selected")
    root = get_root(req.section)
    context = collect_files_for_context(root, req.target_files)
    if not context.strip():
        raise HTTPException(status_code=400, detail="No readable files found for context")
    prompt = f"""
You are helping improve website files.

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
    "index.html": "full updated file content"
  }}
}}

Rules:
- Return only JSON
- Include only files that should change
- Always return full file contents
"""
    return ask_ollama_json(req.model, "You are an expert web UI assistant that updates website files and returns valid JSON only.", prompt)

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
    return {"folder_name": req.folder_name, "path": req.relative_path, "content": target.read_text(encoding="utf-8", errors="replace")}

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
    root = get_shared_folder_root(req.folder_name)
    context = collect_files_for_context(root, req.target_files)
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
"""
    return ask_ollama_json(req.model, "You improve project files and return valid JSON only.", prompt)

@app.get("/repo/list")
def repo_list():
    ensure_data_files()
    repos = []
    for p in REPOS_ROOT.iterdir():
        if p.is_dir():
            repos.append(p.name)
    return {"repos": sorted(repos)}


@app.post("/repo/pull")
def repo_pull(repo_name: str = Query(...)):
    repo_root = get_repo_root(repo_name)
    if not (repo_root / ".git").exists():
        raise HTTPException(status_code=404, detail="Repo not found")
    result = subprocess.run(
        ["git", "-C", str(repo_root), "pull"],
        capture_output=True,
        text=True,
        timeout=300
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or result.stdout.strip() or "git pull failed")
    return {"status": "pulled", "repo_name": repo_name, "output": result.stdout}

@app.get("/repo/files")
def repo_files(repo_name: str = Query(...)):
    repo_root = get_repo_root(repo_name)
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Repo not found")
    files = []
    for p in repo_root.rglob("*"):
        if ".git/" in str(p):
            continue
        if p.is_file() and p.suffix.lower() in ALLOWED_EDIT_SUFFIXES:
            files.append(str(p.relative_to(repo_root)))
    return {"repo_name": repo_name, "files": sorted(files)}

@app.post("/repo/read")
def repo_read(req: RepoFileRequest):
    repo_root = get_repo_root(req.repo_name)
    target = safe_join(repo_root, req.relative_path)
    validate_editable_file(target)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Repo file not found")
    return {"repo_name": req.repo_name, "path": req.relative_path, "content": target.read_text(encoding="utf-8", errors="replace")}

@app.post("/repo/save")
def repo_save(req: RepoSaveRequest):
    repo_root = get_repo_root(req.repo_name)
    target = safe_join(repo_root, req.relative_path)
    validate_editable_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "repo_name": req.repo_name, "path": req.relative_path}

@app.post("/repo/improve")
def repo_improve(req: RepoImproveRequest):
    if not req.target_files:
        raise HTTPException(status_code=400, detail="No target files selected")
    repo_root = get_repo_root(req.repo_name)
    context = collect_files_for_context(repo_root, req.target_files)
    if not context.strip():
        raise HTTPException(status_code=400, detail="No readable repo files found for context")
    prompt = f"""
You are helping improve files in a repository.

REPO:
{req.repo_name}

TASK:
{req.task}

CURRENT FILES:
{context}

Return ONLY valid JSON in this format:
{{
  "summary": "short explanation",
  "files": {{
    "path/to/file.yaml": "full updated content"
  }}
}}
"""
    return ask_ollama_json(req.model, "You improve repository files and return valid JSON only.", prompt)

@app.post("/web/fetch")
def web_fetch(req: WebFetchRequest):
    return fetch_web_text(req.url)

@app.post("/web/summarize")
def web_summarize(req: WebSummarizeRequest):
    page = fetch_web_text(req.url)
    prompt = f"""
TASK:
{req.task}

URL:
{page["url"]}

TITLE:
{page["title"]}

CONTENT:
{page["content"]}
"""
    summary = ask_ollama_text(req.model, "You summarize web pages clearly and concisely.", prompt)
    return {"url": page["url"], "title": page["title"], "summary": summary, "content_preview": page["content"][:4000]}

@app.post("/api/chat/image-studio/generate")
def generate_image_studio_asset(req: ImagePromptRequest):
    if not (req.user_input or "").strip():
        raise HTTPException(status_code=400, detail="user_input is required")

    structured_prompt = build_structured_image_prompt(req.model, req.user_input.strip(), req.aspect_ratio)
    rendered = render_image_backend_svg(structured_prompt, req.accent_color)
    encoded_svg = requests.utils.quote(rendered["svg"])

    return {
        "structured_prompt": structured_prompt,
        "image": {
            "backend": "svg",
            "mime_type": rendered["mime_type"],
            "width": rendered["width"],
            "height": rendered["height"],
            "aspect_ratio": rendered["aspect_ratio"],
            "svg": rendered["svg"],
            "data_url": f"data:{rendered['mime_type']};charset=utf-8,{encoded_svg}"
        }
    }

@app.post("/api/images/generate")
def generate_real_image(req: ImageGenerateRequest):
    if not (req.prompt or "").strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    final_prompt = maybe_rewrite_image_prompt(req).strip()
    image_bytes, output_format = call_image_backend(req, final_prompt)
    filename = save_generated_image(image_bytes, output_format)
    encoded = base64.b64encode(image_bytes).decode("utf-8")

    return {
        "prompt": req.prompt,
        "final_prompt": final_prompt,
        "negative_prompt": req.negative_prompt,
        "model": req.model,
        "width": req.width,
        "height": req.height,
        "steps": req.steps,
        "guidance": req.guidance,
        "format": output_format,
        "filename": filename,
        "data_url": f"data:image/{output_format};base64,{encoded}",
        **build_image_urls(filename),
    }

@app.post("/api/images/analyze")
async def analyze_uploaded_image(
    model: str = Form(DEFAULT_MODEL),
    prompt: str = Form("Describe this image in detail and call out important objects, style, and text."),
    image: UploadFile = File(...),
):
    content_type = (image.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    system_text = (
        "You analyze user-provided images. Be specific, grounded in visible details, "
        "and clearly mention any uncertainty instead of guessing."
    )
    encoded = base64.b64encode(image_bytes).decode("utf-8")

    try:
        analysis = ask_ollama_with_images(model, system_text, prompt.strip() or "Describe this image.", [encoded], timeout=180)
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Timed out while analyzing the image")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to analyze image with Ollama: {exc}")

    preview_b64 = encoded
    if content_type:
        mime_type = content_type
    else:
        mime_type = mimetypes.guess_type(image.filename or "")[0] or "image/png"

    return {
        "model": model,
        "prompt": prompt,
        "filename": image.filename or "upload",
        "content_type": mime_type,
        "analysis": analysis.strip(),
        "preview_data_url": f"data:{mime_type};base64,{preview_b64}",
    }

@app.post("/text/summarize")
def text_summarize(req: SummarizeTextRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")
    prompt = f"""
TASK:
{req.task}

TEXT:
{req.text}
"""
    summary = ask_ollama_text(req.model, "You summarize text clearly and concisely.", prompt)
    return {"summary": summary}

@app.post("/images")
def save_image(req: SaveImageRequest):
    ensure_data_files()
    image_id = f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    svg_path = get_image_file(image_id, ".svg")
    meta_path = get_image_file(image_id, ".json")

    svg_path.write_text(req.svg, encoding="utf-8")
    meta = {
        "image_id": image_id,
        "title": req.title.strip() or "Study card",
        "prompt": req.prompt.strip(),
        "model/workflow": req.model_workflow.strip() or "study-image-studio",
        "created_timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "dimensions": {
            "width": req.width,
            "height": req.height,
        },
        "file_path": str(svg_path.relative_to(BASE_DIR)),
        "filename": svg_path.name,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        "status": "saved",
        **serialize_image_metadata(meta),
    }

@app.get("/api/images/download")
def download_generated_image(filename: str = Query(...)):
    target = get_generated_image_file(filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Generated image not found")
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=mime_type, filename=target.name)

@app.get("/api/images/preview")
def preview_generated_image(filename: str = Query(...)):
    target = get_generated_image_file(filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Generated image not found")
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(str(target), media_type=mime_type)

@app.get("/images/list")
def image_list():
    ensure_data_files()
    items = []
    for meta_path in sorted(IMAGES_ROOT.glob("*.json"), reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            svg_path = get_image_file(meta.get("image_id", meta_path.stem), ".svg")
            if not svg_path.exists():
                continue
            items.append(serialize_image_metadata(meta))
        except Exception:
            continue
    items.sort(key=lambda item: item.get("created_timestamp", ""), reverse=True)
    return {"images": items}

@app.get("/images/read/{image_id}")
def image_read(image_id: str, format: str = Query("file")):
    svg_path, _, meta = load_image_metadata(image_id)
    if format == "meta":
        return serialize_image_metadata(meta)
    if format == "raw":
        return Response(content=svg_path.read_text(encoding="utf-8"), media_type="image/svg+xml")
    return FileResponse(str(svg_path), media_type="image/svg+xml", filename=meta.get("filename", svg_path.name))

@app.delete("/images/{image_id}")
def image_delete(image_id: str):
    svg_path, meta_path, meta = load_image_metadata(image_id)
    svg_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    return {"status": "deleted", "image_id": meta.get("image_id", image_id)}

@app.post("/export/text")
def export_text(req: ExportTextRequest):
    ensure_data_files()
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', req.filename.strip() or f"export_{uuid.uuid4().hex[:8]}.txt")
    out = (EXPORTS_ROOT / safe_name).resolve()
    if not str(out).startswith(str(EXPORTS_ROOT)):
        raise HTTPException(status_code=403, detail="Export path not allowed")
    out.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "filename": safe_name, "download_url": f"/api/export/download?filename={safe_name}"}

@app.get("/export/download")
def export_download(filename: str = Query(...)):
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    target = (EXPORTS_ROOT / safe_name).resolve()
    if not str(target).startswith(str(EXPORTS_ROOT)) or not target.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(str(target), filename=safe_name)











@app.post("/repo/test")
def repo_test(req: RepoCloneRequest):
    git_bin = pyshutil.which("git") or "/usr/bin/git"
    try:
        result = subprocess.run(
            [git_bin, "ls-remote", req.repo_url],
            capture_output=True,
            text=True,
            timeout=120
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"repo test execution failed: {e}")

    if result.returncode != 0:
        err = (result.stderr or "").strip() or (result.stdout or "").strip() or "repo test failed"
        raise HTTPException(status_code=500, detail=err)

    return {
        "status": "ok",
        "repo_url": req.repo_url,
        "git_bin": git_bin
    }


@app.post("/repo/clone")
def repo_clone(req: RepoCloneRequest):
    ensure_data_files()
    git_bin = pyshutil.which("git") or "/usr/bin/git"
    repo_name = req.repo_name.strip() if req.repo_name else repo_name_from_url(req.repo_url)
    repo_root = get_repo_root(repo_name)

    if repo_root.exists() and (repo_root / ".git").exists():
        return {"status": "exists", "repo_name": repo_name, "path": str(repo_root), "git_bin": git_bin}

    if repo_root.exists() and repo_root.is_dir() and any(repo_root.iterdir()):
        raise HTTPException(status_code=400, detail="Target local repo folder already exists and is not empty")

    repo_root.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [git_bin, "clone", "--depth", "1", req.repo_url, str(repo_root)],
            capture_output=True,
            text=True,
            timeout=300
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"git clone execution failed: {e}")

    if result.returncode != 0:
        err = (result.stderr or "").strip() or (result.stdout or "").strip() or "git clone failed"
        raise HTTPException(status_code=500, detail=err)

    return {
        "status": "cloned",
        "repo_name": repo_name,
        "path": str(repo_root),
        "git_bin": git_bin
    }


@app.post("/repo/delete")
def repo_delete(repo_name: str = Query(...)):
    repo_root = get_repo_root(repo_name)
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Repo not found")
    try:
        shutil.rmtree(repo_root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete repo: {e}")
    return {"status": "deleted", "repo_name": repo_name}



@app.get("/repo/templates")
def repo_templates_list():
    ensure_data_files()
    items = []
    for meta_file in sorted(REPO_TEMPLATES_META_ROOT.glob("*.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            items.append(data)
        except Exception:
            continue
    items.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return {"templates": items}

@app.post("/repo/template/save")
def repo_template_save(req: RepoTemplateSaveRequest):
    ensure_data_files()
    repo_root = get_repo_root(req.repo_name)
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Repo not found")

    template_root = get_repo_template_root(req.template_name)
    meta_file = get_repo_template_meta_file(req.template_name)

    if template_root.exists():
        shutil.rmtree(template_root)
    template_root.mkdir(parents=True, exist_ok=True)

    selected = req.selected_files or []
    copied = []

    if selected:
        for rel in selected:
            src = safe_join(repo_root, rel)
            if src.is_file():
                dst = safe_join(template_root, rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)
    else:
        for src in repo_root.rglob("*"):
            if ".git/" in str(src):
                continue
            if src.is_file() and src.suffix.lower() in ALLOWED_EDIT_SUFFIXES:
                rel = str(src.relative_to(repo_root))
                dst = safe_join(template_root, rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)

    meta = {
        "template_name": req.template_name,
        "repo_name": req.repo_name,
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "file_count": len(copied),
        "files": copied
    }
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {"status": "saved", "template": meta}

@app.post("/repo/template/delete")
def repo_template_delete(req: RepoTemplateDeleteRequest):
    template_root = get_repo_template_root(req.template_name)
    meta_file = get_repo_template_meta_file(req.template_name)

    if template_root.exists():
        shutil.rmtree(template_root)
    if meta_file.exists():
        meta_file.unlink()

    return {"status": "deleted", "template_name": req.template_name}

@app.get("/repo/template/files")
def repo_template_files(template_name: str = Query(...)):
    template_root = get_repo_template_root(template_name)
    if not template_root.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    files = []
    for p in template_root.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(template_root)))
    return {"template_name": template_name, "files": sorted(files)}

@app.get("/chat/repo-templates")
def chat_repo_templates():
    ensure_data_files()
    items = []
    for meta_file in sorted(REPO_TEMPLATES_META_ROOT.glob("*.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            items.append({
                "template_name": data.get("template_name", ""),
                "repo_name": data.get("repo_name", ""),
                "file_count": data.get("file_count", 0),
                "saved_at": data.get("saved_at", "")
            })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return {"templates": items}


@app.post("/chat/project/delete")
def chat_project_delete(req: SaveProjectRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    projects = read_projects()
    if name in projects:
        projects.remove(name)
        write_projects(projects)

    return {"status": "deleted", "project": name, "projects": projects}

@app.post("/chat/session/delete")
def chat_session_delete(chat_id: str = Query(...)):
    chat_file = get_chat_file(chat_id)
    if not chat_file.exists():
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_file.unlink()
    return {"status": "deleted", "chat_id": chat_id}

@app.get("/chat/repo-template/files")
def chat_repo_template_files(template_name: str = Query(...)):
    template_root = get_repo_template_root(template_name)
    if not template_root.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    files = []
    previews = []
    for p in sorted(template_root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(template_root))
            files.append(rel)
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
            previews.append({
                "path": rel,
                "content": content[:12000]
            })

    return {
        "template_name": template_name,
        "files": files,
        "previews": previews
    }



@app.post("/chat/messages/retrieval")
def chat_messages_retrieval(req: RetrievalChatRequest):
    try:
        user_messages = [m for m in req.messages if m.get("role") == "user"]
        latest_user = user_messages[-1]["content"] if user_messages else ""

        source_types = req.source_types
        path_contains = req.path_contains

        if req.selected_template and not path_contains:
            path_contains = req.selected_template

        retrieved = []
        retrieval_context = ""

        if req.use_retrieval and latest_user.strip():
            if not source_types:
                q = latest_user.lower()
                if "widget" in q or "module" in q:
                    source_types = ["repo", "template"]
                elif "template" in q:
                    source_types = ["template", "web"]
                elif "admin" in q or "website" in q or "chat page" in q:
                    source_types = ["website"]
                else:
                    source_types = ["repo", "template", "website", "chat", "web"]

            try:
                retrieved = search_local_context(
                    query=latest_user,
                    top_k=6,
                    source_types=source_types,
                    path_contains=path_contains
                )
                retrieval_context = build_retrieval_context(retrieved)
            except Exception as e:
                retrieval_context = f"Retrieval failed: {e}"

        template_context = load_template_content(req.selected_template) if req.selected_template else ""
        learning_context = load_learning_context(req.selected_learning_ids)

        system_message = {
            "role": "system",
            "content": f"""You are a coding assistant focused on LOCAL DATA.

RULES:
- ALWAYS use TEMPLATE CONTENT if present.
- ALWAYS use LEARNING LIBRARY CONTENT if present.
- ALWAYS use RETRIEVED CONTEXT if present.
- If information exists in provided context, DO NOT use generic knowledge.
- Reference file names when explaining.
 for Linux, Bash, Python, web development, Ansible, Zabbix widgets, Zabbix modules, and Zabbix templates.

Use retrieved local context when relevant.
If the retrieved context is insufficient, say what is missing.
Prefer concrete answers based on the retrieved data when available.

TEMPLATE CONTENT:
{template_context}

LEARNING LIBRARY CONTENT:
{learning_context}

RETRIEVED CONTEXT:
{retrieval_context}
"""
        }

        outgoing = [system_message] + req.messages

        r = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": req.model,
                "messages": outgoing,
                "stream": req.stream
            },
            timeout=300
        )
        r.raise_for_status()
        data = r.json()

        answer = data.get("message", {}).get("content", "")
        return {
            "message": {
                "role": "assistant",
                "content": answer
            },
            "learning_items_used": req.selected_learning_ids or [],
            "retrieved": [
                {
                    "source_type": x.get("source_type"),
                    "path": x.get("path"),
                    "score": x.get("score")
                }
                for x in retrieved
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed retrieval chat: {e}")



@app.get("/chat/source/view")
def chat_source_view(source_type: str, path: str, repo_name: str | None = None, template_name: str | None = None, section: str | None = None):
    root = get_source_root(source_type, repo_name=repo_name, template_name=template_name, section=section)
    target = safe_join(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {
        "source_type": source_type,
        "path": path,
        "content": content
    }

@app.post("/chat/edit/plan")
def chat_edit_plan(req: ChatEditPlanRequest):
    if not req.selected_repo:
        raise HTTPException(status_code=400, detail="selected_repo is required for change planning")

    repo_root = get_repo_root(req.selected_repo)
    target_paths = req.target_paths or []

    if not target_paths:
        retrieved = search_local_context(
            query=req.instruction,
            top_k=8,
            source_types=["repo", "template"],
            path_contains=req.selected_repo
        )
        repo_hits = []
        for item in retrieved:
            if item.get("source_type") == "repo" and req.selected_repo in item.get("path", ""):
                rel = item["path"].split(f"/{req.selected_repo}/", 1)[-1]
                repo_hits.append(rel)
        target_paths = list(dict.fromkeys(repo_hits))

    if not target_paths:
        target_paths = list_repo_allowed_files(req.selected_repo)[:8]

    current_context = []
    originals = {}

    for rel in target_paths:
        target = safe_join(repo_root, rel)
        if target.exists() and target.is_file():
            content = target.read_text(encoding="utf-8", errors="replace")
            originals[rel] = content
            current_context.append(f"--- FILE: {rel} ---\n{content}\n")

    template_context = load_template_content(req.selected_template) if req.selected_template else ""
    repo_context = load_repo_content(req.selected_repo, max_chars=8000)
    learning_context = load_learning_context(req.selected_learning_ids, max_chars=16000)

    prompt = f"""
You are editing files inside a repository.

SELECTED REPO:
{req.selected_repo}

SELECTED TEMPLATE:
{req.selected_template or "None"}

USER INSTRUCTION:
{req.instruction}

TEMPLATE CONTEXT:
{template_context}

LEARNING LIBRARY CONTEXT:
{learning_context}

REPO CONTEXT:
{repo_context}

CURRENT TARGET FILES:
{chr(10).join(current_context)}

Return ONLY valid JSON:
{{
  "summary": "short explanation",
  "files": {{
    "relative/path.ext": "full updated content"
  }}
}}

Rules:
- Only return files that should change
- Paths must already belong to the selected repo
- Return full file contents
- No markdown
"""
    planned = ask_ollama_json(req.model, "You are a repository code editor. Return valid JSON only.", prompt)

    files = planned.get("files", {})
    diffs = {}
    for rel, new_content in files.items():
        old = originals.get(rel, "")
        diffs[rel] = make_unified_diff(old, new_content, rel)

    return {
        "summary": planned.get("summary", ""),
        "files": files,
        "diffs": diffs,
        "target_paths": list(files.keys())
    }

@app.post("/chat/edit/apply")
def chat_edit_apply(req: ApplyEditRequest):
    repo_root = get_repo_root(req.repo_name)
    changed = []
    for rel, content in req.files.items():
        target = safe_join(repo_root, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changed.append(rel)
    return {
        "status": "applied",
        "repo_name": req.repo_name,
        "changed_files": changed
    }

@app.get("/repo/git/status")
def repo_git_status(repo_name: str):
    repo_root = get_repo_root(repo_name)
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo_root), "status", "--short"],
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or result.stdout or "git status failed").strip())
    return {
        "repo_name": repo_name,
        "status": result.stdout
    }

@app.post("/repo/git/commit-push")
def repo_git_commit_push(req: GitCommitPushRequest):
    repo_root = get_repo_root(req.repo_name)

    if req.branch:
        checkout = subprocess.run(
            ["/usr/bin/git", "-C", str(repo_root), "checkout", "-B", req.branch],
            capture_output=True,
            text=True,
            timeout=120
        )
        if checkout.returncode != 0:
            raise HTTPException(status_code=500, detail=(checkout.stderr or checkout.stdout or "git checkout failed").strip())

    add = subprocess.run(
        ["/usr/bin/git", "-C", str(repo_root), "add", "-A"],
        capture_output=True,
        text=True,
        timeout=120
    )
    if add.returncode != 0:
        raise HTTPException(status_code=500, detail=(add.stderr or add.stdout or "git add failed").strip())

    commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repo_root), "commit", "-m", req.commit_message],
        capture_output=True,
        text=True,
        timeout=120
    )
    commit_out = (commit.stdout or "") + "\n" + (commit.stderr or "")

    if commit.returncode != 0 and "nothing to commit" not in commit_out.lower():
        raise HTTPException(status_code=500, detail=commit_out.strip() or "git commit failed")

    push_out = ""
    if req.push:
        branch_name = req.branch
        if not branch_name:
            branch_proc = subprocess.run(
                ["/usr/bin/git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if branch_proc.returncode != 0:
                raise HTTPException(status_code=500, detail=(branch_proc.stderr or branch_proc.stdout or "git rev-parse failed").strip())
            branch_name = branch_proc.stdout.strip()

        push = subprocess.run(
            ["/usr/bin/git", "-C", str(repo_root), "push", "-u", "origin", branch_name],
            capture_output=True,
            text=True,
            timeout=300
        )
        push_out = (push.stdout or "") + "\n" + (push.stderr or "")
        if push.returncode != 0:
            raise HTTPException(status_code=500, detail=push_out.strip() or "git push failed")

    return {
        "status": "ok",
        "repo_name": req.repo_name,
        "commit_output": commit_out.strip(),
        "push_output": push_out.strip()
    }
