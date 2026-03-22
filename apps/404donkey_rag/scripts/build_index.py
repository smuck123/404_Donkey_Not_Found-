#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Dict

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path("/opt/chat_admin_webgui")
RAG = Path("/opt/404donkey_rag")
INDEX_DIR = RAG / "indexes"
DATA_DIR = RAG / "data"
CHUNKS_JSONL = DATA_DIR / "chunks" / "chunks.jsonl"
META_JSON = DATA_DIR / "meta" / "chunks_meta.json"
FAISS_FILE = INDEX_DIR / "chunks.faiss"

ALLOWED = {".py", ".php", ".js", ".html", ".css", ".md", ".txt", ".json", ".yaml", ".yml", ".xml", ".sh", ".conf", ".ini"}
SOURCES = [
    BASE / "repos",
    BASE / "data" / "repo_templates",
    BASE / "frontend",
    BASE / "data" / "chats",
    Path("/opt/404donkey_rag/data/web_cache"),
]

EMBED_MODEL = "/opt/404donkey_rag/models/bge-large-en-v1.5"

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def chunk_text(text: str, chunk_size: int = 1600, overlap: int = 250) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks

def infer_source_type(path: Path) -> str:
    p = str(path)
    if "/repos/" in p:
        return "repo"
    if "/repo_templates/" in p:
        return "template"
    if "/frontend/" in p:
        return "website"
    if "/chats/" in p:
        return "chat"
    if "/web_cache/" in p:
        return "web"
    return "other"

def collect_files() -> List[Path]:
    files = []
    for root in SOURCES:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if ".git/" in str(p):
                continue
            if p.suffix.lower() not in ALLOWED:
                continue
            files.append(p)
    return files

def main() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "chunks").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "meta").mkdir(parents=True, exist_ok=True)

    all_chunks: List[Dict] = []
    files = collect_files()

    chunk_id = 0
    for path in files:
        text = read_text(path)
        if not text.strip():
            continue

        rel = str(path)
        source_type = infer_source_type(path)

        for i, chunk in enumerate(chunk_text(text)):
            all_chunks.append({
                "id": chunk_id,
                "path": rel,
                "source_type": source_type,
                "chunk_index": i,
                "content": chunk
            })
            chunk_id += 1

    with CHUNKS_JSONL.open("w", encoding="utf-8") as f:
        for row in all_chunks:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta = [{"id": c["id"], "path": c["path"], "source_type": c["source_type"], "chunk_index": c["chunk_index"]} for c in all_chunks]
    META_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    model = SentenceTransformer(EMBED_MODEL)
    texts = [c["content"] for c in all_chunks]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True, batch_size=32)
    arr = np.array(embeddings).astype("float32")

    index = faiss.IndexFlatIP(arr.shape[1])
    index.add(arr)
    faiss.write_index(index, str(FAISS_FILE))

    print(f"Indexed files: {len(files)}")
    print(f"Indexed chunks: {len(all_chunks)}")
    print(f"FAISS index: {FAISS_FILE}")

if __name__ == "__main__":
    main()
