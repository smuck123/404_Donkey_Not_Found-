#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE = BASE_DIR / "data" / "web_cache"
CACHE.mkdir(parents=True, exist_ok=True)

def safe_name(url: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', url)[:180] + ".txt"

def main():
    if len(sys.argv) != 2:
        print("usage: cache_web_page.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    r = requests.get(url, timeout=60, headers={"User-Agent": "404DonkeyNotFound/1.0"})
    r.raise_for_status()

    text = r.text
    if "<html" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())

    out = CACHE / safe_name(url)
    out.write_text(text, encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
