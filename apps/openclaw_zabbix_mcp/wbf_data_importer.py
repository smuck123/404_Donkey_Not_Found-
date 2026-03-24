import json
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

BEER_LIST_URL = "https://warsawbeerfestival.com/beer-list/"
EVENTS_URL = "https://warsawbeerfestival.com/"
MAP_PDF_URL = "https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf"


class WBFDataImporter:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _fetch_text(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def _fetch_binary(self, url: str) -> bytes:
        response = requests.get(url, timeout=self.timeout)
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

    def import_beers(self) -> list[dict[str, Any]]:
        html = self._fetch_text(BEER_LIST_URL)
        if not BeautifulSoup:
            return self._import_beers_without_bs4(html)
        soup = BeautifulSoup(html, "html.parser")
        beers: list[dict[str, Any]] = []

        for row in soup.select("table tr"):
            cols = [self._clean(c.get_text(" ")) for c in row.find_all(["td", "th"])]
            if len(cols) < 2:
                continue
            lowered = " ".join(cols).lower()
            if "beer" in lowered and "brew" in lowered:
                continue
            name = cols[0]
            brewery = cols[1] if len(cols) > 1 else ""
            style = cols[2] if len(cols) > 2 else ""
            abv = self._safe_abv(" ".join(cols))
            if not name or len(name) < 2:
                continue
            beers.append(
                {
                    "name": name,
                    "brewery": brewery,
                    "style": style,
                    "abv": abv,
                    "source_url": BEER_LIST_URL,
                }
            )

        if not beers:
            for card in soup.select("article, .beer, .beer-item, .elementor-post, .grid-item"):
                txt = self._clean(card.get_text("\n"))
                lines = [self._clean(x) for x in txt.split("\n") if self._clean(x)]
                if len(lines) < 2:
                    continue
                name = lines[0]
                brewery = lines[1]
                style = ""
                for line in lines[2:]:
                    if re.search(r"%", line):
                        continue
                    if len(line) > 2:
                        style = line
                        break
                beers.append(
                    {
                        "name": name,
                        "brewery": brewery,
                        "style": style,
                        "abv": self._safe_abv(txt),
                        "source_url": BEER_LIST_URL,
                    }
                )

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for beer in beers:
            key = (beer.get("name", "").lower(), beer.get("brewery", "").lower())
            if key[0]:
                dedup[key] = beer
        return list(dedup.values())

    def _import_beers_without_bs4(self, html: str) -> list[dict[str, Any]]:
        beers = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.IGNORECASE | re.DOTALL)
            cols = [self._clean(re.sub(r"<[^>]+>", " ", cell)) for cell in cells]
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
        return beers

    def import_events(self) -> list[dict[str, Any]]:
        html = self._fetch_text(EVENTS_URL)
        if not BeautifulSoup:
            return self._import_events_without_bs4(html)
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict[str, Any]] = []

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.get_text(strip=True) or "{}")
            except json.JSONDecodeError:
                continue
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
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

        if not out:
            text = self._clean(soup.get_text("\n"))
            lines = [self._clean(x) for x in text.split("\n") if self._clean(x)]
            for idx, line in enumerate(lines):
                if not re.search(r"\b\d{1,2}:\d{2}\b", line):
                    continue
                title = lines[idx - 1] if idx > 0 else f"Event {idx + 1}"
                start = self._extract_datetime_from_text(line)
                out.append(
                    {
                        "title": title,
                        "start_ts": start,
                        "end_ts": None,
                        "location": "",
                        "description": line,
                        "source_url": EVENTS_URL,
                    }
                )

        return [x for x in out if x.get("title")]

    def _import_events_without_bs4(self, html: str) -> list[dict[str, Any]]:
        out = []
        scripts = re.findall(
            r'<script[^>]*type=[\"\']application/ld\\+json[\"\'][^>]*>(.*?)</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        for block in scripts:
            try:
                payload = json.loads(block)
            except json.JSONDecodeError:
                continue
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                if isinstance(record, dict) and record.get("@type") == "Event":
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
        pdf_content = self._fetch_binary(MAP_PDF_URL)
        reader = PdfReader(BytesIO(pdf_content))
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
            zone = ""
            zone_match = re.search(r"\b(HALL|ZONE|STREFA|SALA)\s*([A-Z0-9]+)\b", line, re.IGNORECASE)
            if zone_match:
                zone = f"{zone_match.group(1)} {zone_match.group(2)}"
            exhibitors.append(
                {
                    "name": name,
                    "zone": zone,
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

    @staticmethod
    def _extract_datetime_from_text(text: str) -> str | None:
        # fallback parser for plain schedule lines like 2026-04-03 18:00
        match = re.search(r"(20\d{2}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", text)
        if not match:
            return None
        try:
            return datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}:00").isoformat()
        except ValueError:
            return None
