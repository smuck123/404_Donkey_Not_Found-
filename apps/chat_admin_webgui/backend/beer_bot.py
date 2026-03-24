from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import requests


WARSAW_BEER_LIST_URL = "https://warsawbeerfestival.com/beer-list/"
WARSAW_AMBASSADORS_URL = "https://warsawbeerfestival.com/#ambasadors"
WARSAW_PIWA_MAP_URL = "https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf"
DEFAULT_ROUTE_SIZE = 5
ROUTE_EXAMPLES = [
    "Route 1 (Hop Hunt): IPA-heavy stands near the main festival flow.",
    "Route 2 (Dark Power): stouts/porters with higher ABV and slower sipping pace.",
    "Route 3 (Fruit & Funk): sours, gose, and fruit-forward experiments.",
    "Route 4 (Classic Poland): lagers, pils, and clean traditional profiles.",
    "Route 5 (Strong Mission): beers above 8% ABV, with food stop in the middle.",
]


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


def parse_abv_number(value: str) -> float | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return None


def parse_beer_route_command(query: str) -> dict:
    low = (query or "").lower()
    if not query:
        return {"detected": False}
    style_match = re.search(r"\b(ipa|lager|ale|stout|porter|pils|sour|wit|weizen|gose|ko[źz]lak|pale)\b", low)
    numbers = [int(x) for x in re.findall(r"\b(\d{1,2})\b", low)]
    has_route_keyword = "route" in low or "trasa" in low
    has_plus_keyword = "+" in low or "more than" in low or "powyzej" in low or "above" in low
    has_abv_signal = "%" in low or "abv" in low or has_plus_keyword or len(numbers) >= 2

    if not style_match and not has_route_keyword:
        return {"detected": False}

    route_id = None
    count = DEFAULT_ROUTE_SIZE
    min_abv = None

    if has_route_keyword and numbers:
        route_id = numbers[0]
        if len(numbers) >= 2:
            min_abv = float(numbers[1])
        if len(numbers) >= 3:
            count = max(1, min(12, numbers[2]))
    elif len(numbers) >= 2:
        count = max(1, min(12, numbers[0]))
        min_abv = float(numbers[1])
    elif len(numbers) == 1:
        if has_abv_signal:
            min_abv = float(numbers[0])
        else:
            count = max(1, min(12, numbers[0]))

    return {
        "detected": bool(style_match or has_route_keyword),
        "style": style_match.group(1).lower() if style_match else "",
        "route_id": route_id,
        "count": count,
        "min_abv": min_abv,
    }


def filter_route_beers(beers: list[dict], route: dict) -> list[dict]:
    if not beers:
        return []
    style = (route.get("style") or "").lower()
    min_abv = route.get("min_abv")
    count = int(route.get("count") or DEFAULT_ROUTE_SIZE)
    out = []
    for beer in beers:
        beer_style = (beer.get("style") or "").lower()
        if style and style not in beer_style:
            continue
        abv_val = parse_abv_number(beer.get("abv", "") or beer.get("notes", ""))
        if min_abv is not None and (abv_val is None or abv_val < min_abv):
            continue
        out.append(beer)
        if len(out) >= count:
            break
    return out


def extract_drunk_beers(messages: list[dict]) -> list[str]:
    text = " \n ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    if not text:
        return []
    candidates = []
    patterns = [
        r"(?:i drank|i drink|drank|had|wypi[łl]em|pil[eę]m|pi[łl]em)\s+([^.!?\n]{3,80})",
        r"(?:already tried|i tried)\s+([^.!?\n]{3,80})",
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I):
            chunk = re.sub(r"\b(and|or|plus|then|oraz|i)\b", ",", raw, flags=re.I)
            for part in chunk.split(","):
                cleaned = normalize_space(part.strip(" -:;,."))
                if len(cleaned) < 3 or len(cleaned) > 60:
                    continue
                candidates.append(cleaned)
    unique = []
    seen = set()
    for name in candidates:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return unique[:20]


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
    route = parse_beer_route_command(latest_user)
    route_matches = filter_route_beers(beers, route) if route.get("detected") else []
    memory = extract_memory_signals(messages)
    drunk_beers = extract_drunk_beers(messages)
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
    route_lines = [
        f"- {b.get('name','')} | brewery: {b.get('brewery','?')} | style: {b.get('style','?')} | abv: {b.get('abv','?')}"
        for b in route_matches
    ]
    ambassador_lines = [f"- {name}" for name in catalog.get("ambassadors", [])[:20]]
    warning = catalog.get("warning", "")
    route_examples_text = "\n".join(f"- {x}" for x in ROUTE_EXAMPLES)
    drunk_lines = [f"- {x}" for x in drunk_beers]
    route_instruction = "No explicit route command detected."
    if route.get("detected"):
        route_instruction = (
            f"Detected route intent: route_id={route.get('route_id', 'none')}, "
            f"style={route.get('style') or 'any'}, min_abv={route.get('min_abv', 'none')}, count={route.get('count', DEFAULT_ROUTE_SIZE)}."
        )

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
- Beers user says they already drank: {", ".join(drunk_beers) if drunk_beers else "none recorded yet"}

Starter behavior:
- {starter}
- Add variety in tone: use bartender, scientist, donkey detective, and festival guide speaking styles.
- Handle command 'piwa_what to do' or 'piwa_what_to_do' by giving the day-specific action plan below.
- If user says 'help beers' (or similar), explain commands:
  1) 'beer route 5 8 IPA' => route style IPA, 5 beers, at least 8% ABV.
  2) '3 10 STOUT' => 3 stouts with at least 10% ABV.
  3) 'beer route <route_id> <min_abv> <style> [count]' supported.
- If user asks for map guidance, include the map URL and suggest 5 route examples listed below.
- {today_hint}

Route examples:
{route_examples_text}

Route command parse:
- {route_instruction}

Best matches for latest message:
{chr(10).join(match_lines) if match_lines else "- No beer matches available."}

Route matches for latest command:
{chr(10).join(route_lines) if route_lines else "- No route-specific beer matches right now."}

Remembered as already drank in this chat:
{chr(10).join(drunk_lines) if drunk_lines else "- Nothing remembered yet from 'I drank ...' phrases."}

Ambassadors remembered:
{chr(10).join(ambassador_lines) if ambassador_lines else "- No ambassadors extracted yet."}
"""
