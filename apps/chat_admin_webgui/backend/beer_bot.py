from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import requests


WARSAW_BEER_LIST_URL = "https://warsawbeerfestival.com/beer-list/"
WARSAW_AMBASSADORS_URL = "https://warsawbeerfestival.com/#ambasadors"
WARSAW_PIWA_MAP_URL = "https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def strip_html_tags(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return normalize_space(text)


def parse_beer_list_html(html: str) -> list[dict]:
    text = strip_html_tags(html)
    lines = [normalize_space(x) for x in re.split(r"[;\n\r]+", text) if normalize_space(x)]
    beers = []
    style_re = re.compile(r"\b(ipa|lager|ale|stout|porter|pils|sour|wit|weizen|gose|ko[źz]lak|pale)\b", re.I)
    for line in lines:
        if len(line) < 14 or len(line) > 240:
            continue
        if not style_re.search(line) and "%" not in line:
            continue
        parts = [normalize_space(p) for p in re.split(r"\s+[–|-]\s+|\s+\|\s+", line) if normalize_space(p)]
        if len(parts) < 2:
            continue
        beers.append({
            "name": parts[0],
            "brewery": parts[1] if len(parts) > 1 else "",
            "style": parts[2] if len(parts) > 2 else "",
            "abv": parts[3] if len(parts) > 3 and "%" in parts[3] else "",
            "notes": " | ".join(parts[3:]) if len(parts) > 3 else ""
        })
    seen = set()
    deduped = []
    for beer in beers:
        key = (
            beer.get("name", "").lower(),
            beer.get("brewery", "").lower(),
            beer.get("style", "").lower(),
            beer.get("abv", "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(beer)
    return deduped


def extract_ambassadors(html: str) -> list[str]:
    text = strip_html_tags(html)
    parts = [normalize_space(p) for p in re.split(r"[,\n;|]+", text)]
    names = []
    for part in parts:
        if len(part) < 4 or len(part) > 70:
            continue
        if re.search(r"\b(ambas|festival|warsaw|piwa|beer list|kup|bilet|program)\b", part.lower()):
            continue
        if re.match(r"^[A-ZŻŹĆĄŚĘŁÓŃ][A-Za-zŻŹĆĄŚĘŁÓŃżźćąśęłóń.' -]{3,}$", part):
            names.append(part)
    unique = []
    seen = set()
    for name in names:
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        unique.append(name)
    return unique[:40]


def read_or_refresh_cache(data_root: Path, max_age_hours: int = 12) -> dict:
    cache_file = (data_root / "beer_cache" / "festival_context.json").resolve()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow()
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(cached.get("updated_at", "").replace("Z", "+00:00"))
            age_seconds = (now - updated_at.replace(tzinfo=None)).total_seconds()
            if age_seconds <= max_age_hours * 3600 and cached.get("beers"):
                cached["source"] = "cache:fresh"
                return cached
        except Exception:
            pass

    payload = {
        "updated_at": now.isoformat() + "Z",
        "source": "web:partial",
        "beer_list_url": WARSAW_BEER_LIST_URL,
        "ambassadors_url": WARSAW_AMBASSADORS_URL,
        "map_url": WARSAW_PIWA_MAP_URL,
        "beers": [],
        "ambassadors": [],
    }

    errors = []
    try:
        beer_r = requests.get(WARSAW_BEER_LIST_URL, timeout=45, headers={"User-Agent": "DonkeyBeerBot/1.0"})
        beer_r.raise_for_status()
        payload["beers"] = parse_beer_list_html(beer_r.text)
    except Exception as exc:
        errors.append(f"beer list refresh failed: {exc}")

    try:
        amb_r = requests.get(WARSAW_AMBASSADORS_URL, timeout=45, headers={"User-Agent": "DonkeyBeerBot/1.0"})
        amb_r.raise_for_status()
        payload["ambassadors"] = extract_ambassadors(amb_r.text)
    except Exception as exc:
        errors.append(f"ambassadors refresh failed: {exc}")

    payload["beer_count"] = len(payload["beers"])
    payload["ambassador_count"] = len(payload["ambassadors"])
    if errors:
        payload["warning"] = " | ".join(errors)
    if payload["beers"] or payload["ambassadors"]:
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    if cache_file.exists():
        stale = json.loads(cache_file.read_text(encoding="utf-8"))
        stale["source"] = "cache:stale"
        stale["warning"] = payload.get("warning", "live refresh failed")
        return stale
    payload["source"] = "unavailable"
    return payload


def select_beers_for_query(beers: list[dict], query: str, limit: int = 18) -> list[dict]:
    if not beers:
        return []
    tokens = [t for t in re.findall(r"[a-zA-Z0-9%+]+", (query or "").lower()) if len(t) >= 3]
    if not tokens:
        return beers[:limit]
    scored = []
    for beer in beers:
        hay = " ".join([beer.get("name", ""), beer.get("brewery", ""), beer.get("style", ""), beer.get("abv", ""), beer.get("notes", "")]).lower()
        score = sum(1 for t in tokens if t in hay)
        if score > 0:
            scored.append((score, beer))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in scored[:limit]] if scored else beers[:limit]


def extract_memory_signals(messages: list[dict]) -> dict:
    all_user_text = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    low = all_user_text.lower()
    style_tokens = ["ipa", "lager", "stout", "porter", "sour", "gose", "pils", "wheat", "hazy", "session", "dark", "fruity"]
    chosen_styles = [t for t in style_tokens if t in low]
    locations = []
    for loc in ["centrum", "praga", "mokotow", "muranow", "warsaw", "hala", "stage", "food zone", "main bar"]:
        if loc in low:
            locations.append(loc)
    return {
        "styles": chosen_styles[:8],
        "locations": locations[:8],
        "mentions_beer": "beer" in low or "piwo" in low or "piwa" in low,
    }


def build_today_hint(now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    weekday = now.strftime("%A")
    plans = {
        "Monday": "Recovery mode: pick easy-drinking lagers and make a short tasting plan.",
        "Tuesday": "Try one safe classic + one wildcard sour and compare notes.",
        "Wednesday": "Mid-week mission: go for balanced ABV so you can taste more styles.",
        "Thursday": "Pre-weekend warmup: ask for hop-forward picks then check the map for nearby food.",
        "Friday": "Prime festival vibe: start light, then move to bold stouts/imperials.",
        "Saturday": "Big exploration day: build a mini route across different breweries.",
        "Sunday": "Final lap: revisit your top pick and try one totally different style.",
    }
    return f"{weekday} plan: {plans.get(weekday, 'Taste responsibly and stay hydrated.')}"


def build_beer_bot_context(data_root: Path, messages: list[dict], latest_user: str) -> str:
    catalog = read_or_refresh_cache(data_root=data_root, max_age_hours=12)
    beers = catalog.get("beers", [])
    matched = select_beers_for_query(beers, latest_user, limit=18)
    memory = extract_memory_signals(messages)
    today_hint = build_today_hint()
    starter = ""
    latest_low = (latest_user or "").lower()
    if "beer" in latest_low or "piwo" in latest_low or "piwa" in latest_low:
        starter = "Detected the word 'beer/piwo'. Ask: 'Do you want to get a beer now? If yes, what style mood do you want?'"
    elif not memory["styles"]:
        starter = "If preference is missing, ask a quick preference question before recommending."

    match_lines = [
        f"- {b.get('name','')} | brewery: {b.get('brewery','?')} | style: {b.get('style','?')} | abv: {b.get('abv','?')}"
        for b in matched
    ]
    ambassador_lines = [f"- {name}" for name in catalog.get("ambassadors", [])[:20]]
    warning = catalog.get("warning", "")

    return f"""Festival source status: {catalog.get('source', 'unknown')}, updated_at={catalog.get('updated_at', 'unknown')}
Beer list URL: {catalog.get('beer_list_url', WARSAW_BEER_LIST_URL)}
Ambassadors URL: {catalog.get('ambassadors_url', WARSAW_AMBASSADORS_URL)}
Interactive map URL: {catalog.get('map_url', WARSAW_PIWA_MAP_URL)}
Remembered beers: {catalog.get('beer_count', len(beers))}
Remembered ambassadors: {catalog.get('ambassador_count', len(catalog.get('ambassadors', [])))}
Warning: {warning or 'none'}

Conversation memory:
- Preferred styles seen: {", ".join(memory["styles"]) if memory["styles"] else "none yet"}
- Locations seen: {", ".join(memory["locations"]) if memory["locations"] else "none yet"}
- Mentioned beer words before: {"yes" if memory["mentions_beer"] else "no"}

Starter behavior:
- {starter}
- Add variety in tone: use bartender, scientist, donkey detective, and festival guide speaking styles.
- Handle command 'piwa_what to do' or 'piwa_what_to_do' by giving the day-specific action plan below.
- {today_hint}

Best matches for latest message:
{chr(10).join(match_lines) if match_lines else "- No beer matches available."}

Ambassadors remembered:
{chr(10).join(ambassador_lines) if ambassador_lines else "- No ambassadors extracted yet."}
"""
