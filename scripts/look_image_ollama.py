#!/usr/bin/env python3
"""Analyze an image with an Ollama vision-capable model."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

import requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an image to Ollama for visual analysis.")
    parser.add_argument("image", help="Path to the image file.")
    parser.add_argument("--model", default="llava:latest", help="Vision-capable Ollama model.")
    parser.add_argument("--prompt", default="Describe this image in detail and extract any visible text.", help="Question or instruction for the model.")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/chat", help="Ollama /api/chat endpoint.")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout in seconds.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You analyze user-provided images and stay grounded in visible details."},
            {"role": "user", "content": args.prompt, "images": [image_b64]},
        ],
        "stream": False,
    }
    response = requests.post(args.ollama_url, json=payload, timeout=args.timeout)
    response.raise_for_status()
    data = response.json()
    print(data.get("message", {}).get("content", "").strip())


if __name__ == "__main__":
    main()
