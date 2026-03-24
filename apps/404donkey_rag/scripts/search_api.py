#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent.parent
RAG = BASE_DIR
CHUNKS_JSONL = RAG / "data" / "chunks" / "chunks.jsonl"
FAISS_FILE = RAG / "indexes" / "chunks.faiss"
EMBED_MODEL = str(RAG / "models" / "bge-large-en-v1.5")

app = FastAPI(title="404Donkey Search API")
model = SentenceTransformer(EMBED_MODEL)
index = faiss.read_index(str(FAISS_FILE))

chunks = []
with CHUNKS_JSONL.open("r", encoding="utf-8") as f:
    for line in f:
        chunks.append(json.loads(line))

class SearchRequest(BaseModel):
    query: str
    top_k: int = 8
    source_types: Optional[List[str]] = None
    path_contains: Optional[str] = None

@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(chunks)}

@app.post("/search")
def search(req: SearchRequest):
    q = model.encode([req.query], normalize_embeddings=True)
    q = np.array(q).astype("float32")
    scores, ids = index.search(q, max(req.top_k * 8, req.top_k))

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        row = chunks[int(idx)]

        if req.source_types and row["source_type"] not in req.source_types:
            continue
        if req.path_contains and req.path_contains.lower() not in row["path"].lower():
            continue

        results.append({
            "score": float(score),
            "id": row["id"],
            "path": row["path"],
            "source_type": row["source_type"],
            "chunk_index": row["chunk_index"],
            "content": row["content"]
        })

        if len(results) >= req.top_k:
            break

    return {"results": results}
