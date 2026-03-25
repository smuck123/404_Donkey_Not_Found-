import json
import os
import re
from io import BytesIO
from datetime import datetime
from typing import Any

import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FALLBACK_BEERS_FILE = os.path.join(BASE_DIR, "beers_fallback.json")

BEER_LIST_URL = "https://warsawbeerfestival.com/beer-list/"
EVENTS_URL = "https://warsawbeerfestival.com/"
MAP_PDF_URL = "https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf"


class WBFDataImporter:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _fetch_text(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        response = requests.get(url, timeout=self.timeout, headers=headers)
        response.raise_for_status()
        return response.text

    def _fetch_binary(self, url: str) -> bytes:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
        }
        response = requests.get(url, timeout=self.timeout, headers=headers)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _safe_abv(text: str) -> float | None:
        match = re.search(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", text or "")
        if not match:
            return None
        return float(match.group(1).replace(",", "."))

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _load_fallback_beers(self) -> list[dict[str, Any]]:
        if not os.path.exists(FALLBACK_BEERS_FILE):
            return []
        with open(FALLBACK_BEERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        out = []
        for beer in data:
            out.append(
                {
                    "name": self._clean(beer.get("name", "")),
                    "brewery": self._clean(beer.get("brewery", "")),
                    "style": self._clean(beer.get("style", "")),
                    "abv": beer.get("abv"),
                    "zone": self._clean(beer.get("zone", "")),
                    "stand": self._clean(beer.get("stand", "")),
                    "source_url": beer.get("source_url", "manual"),
                }
            )
        return [x for x in out if x.get("name")]

    def import_beers(self) -> list[dict[str, Any]]:
        beers: list[dict[str, Any]] = []

        try:
            html = self._fetch_text(BEER_LIST_URL)

            if BeautifulSoup:
                soup = BeautifulSoup(html, "html.parser")

                for row in soup.select("table tr"):
                    cols = [self._clean(c.get_text(" ")) for c in row.find_all(["td", "th"])]
                    if len(cols) < 2:
                        continue

                    lowered = " ".join(cols).lower()
                    if "beer" in lowered and "brew" in lowered:
                        continue

                    beers.append(
                        {
                            "name": cols[0],
                            "brewery": cols[1] if len(cols) > 1 else "",
                            "style": cols[2] if len(cols) > 2 else "",
                            "abv": self._safe_abv(" ".join(cols)),
                            "source_url": BEER_LIST_URL,
                        }
                    )
        except Exception:
            beers = []

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for beer in beers:
            key = (
                (beer.get("name") or "").strip().lower(),
                (beer.get("brewery") or "").strip().lower(),
            )
            if key[0]:
                dedup[key] = beer

        result = list(dedup.values())

        if len(result) < 5:
            fallback = self._load_fallback_beers()
            if fallback:
                return fallback
            raise RuntimeError("Beer import failed and beers_fallback.json is missing or empty.")

        return result

    def import_events(self) -> list[dict[str, Any]]:
        try:
            html = self._fetch_text(EVENTS_URL)
        except Exception:
            return []

        if not BeautifulSoup:
            return []

        soup = BeautifulSoup(html, "html.parser")
        out: list[dict[str, Any]] = []

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.get_text(strip=True) or "{}")
            except json.JSONDecodeError:
                continue

            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                if not isinstance(record, dict):
                    continue
                if record.get("@type") != "Event":
                    continue

                out.append(
                    {
                        "title": self._clean(record.get("name", "")),
                        "start_ts": self._normalize_datetime(record.get("startDate")),
                        "end_ts": self._normalize_datetime(record.get("endDate")),
                        "location": self._extract_location(record.get("location")),
                        "description": self._clean(record.get("description", "")),
                        "source_url": EVENTS_URL,
                    }
                )

        return [x for x in out if x.get("title")]

    def import_exhibitors_from_pdf(self) -> list[dict[str, Any]]:
        if not PdfReader:
            return []

        try:
            pdf_content = self._fetch_binary(MAP_PDF_URL)
            reader = PdfReader(BytesIO(pdf_content))
        except Exception:
            return []

        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)

        lines = [self._clean(x) for x in text.split("\n") if self._clean(x)]
        exhibitors = []
        pending_floor = ""

        for line in lines:
            upper = line.upper()

            if "FLOOR" in upper or "PIĘTRO" in upper:
                pending_floor = line
                continue

            stand_match = re.search(r"\b([A-Z]?\d{1,3})\b", line)
            if not stand_match:
                continue

            stand = stand_match.group(1)
            name = self._clean(line.replace(stand, "", 1).strip("-: "))
            if len(name) < 3:
                continue

            exhibitors.append(
                {
                    "name": name,
                    "zone": "",
                    "stand": stand,
                    "floor": pending_floor,
                    "source_url": MAP_PDF_URL,
                }
            )

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for ex in exhibitors:
            dedup[(ex["name"].lower(), ex["stand"].lower())] = ex
        return list(dedup.values())

    @staticmethod
    def _extract_location(raw: Any) -> str:
        if isinstance(raw, dict):
            return (raw.get("name") or raw.get("address") or "").strip()
        return str(raw or "").strip()

    @staticmethod
    def _normalize_datetime(raw: Any) -> str | None:
        if not raw:
            return None
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).isoformat()
        except ValueError:
            return None
