from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import logging
import re
import requests
from bs4 import BeautifulSoup


WARSAW_BEER_LIST_URL = "https://warsawbeerfestival.com/beer-list/"
WARSAW_AMBASSADORS_URL = "https://warsawbeerfestival.com/#ambasadors"
WARSAW_PIWA_MAP_URL = "https://warszawskifestiwalpiwa.pl/mapa_interaktywna.pdf"
ROUTE_IDEAS = {
    1: "Hop Hunter: Start near main bar, go to IPA-heavy taps, then finish near food zone.",
    2: "Crisp Cruiser: Pils + lagers lane with short walking distance.",
    3: "Dark Lord Path: Porter/stout route in shaded chill areas.",
    4: "Sour Safari: Fruity and sour-focused stands, with palate reset at water points.",
    5: "Wildcard Donkey: One classic, one weird, one ambassador pick, one local surprise.",
}
ROUTE_EXAMPLES = [
    "Route 1 (Hop Hunt): IPA-heavy stands near the main festival flow.",
    "Route 2 (Crisp Cruiser): pils/lagers with short walking distance.",
    "Route 3 (Dark Lord): porter/stout route in chill, shaded areas.",
    "Route 4 (Sour Safari): sours + fruit beers, with water reset points.",
    "Route 5 (Wildcard Donkey): classic + weird + ambassador + local surprise.",
]
DEFAULT_ROUTE_SIZE = 5
HELP_BEERS_EXAMPLES = [
    "help beers",
    "beer route 2 IPA top 4 under 7%",
    "piwa what now",
    "piwa_what to do",
    "revisit drank beers",
]
logger = logging.getLogger(__name__)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def strip_html_tags(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return normalize_space(text)


def parse_beer_list_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    beers = []

    def add_beer(entry: dict):
        name = normalize_space(entry.get("name", ""))
        if not name:
            return
        normalized = {
            "name": name,
            "brewery": normalize_space(entry.get("brewery", "")),
            "style": normalize_space(entry.get("style", "")),
            "abv": normalize_space(entry.get("abv", "")),
            "notes": normalize_space(entry.get("notes", "")),
        }
        if all(not normalized.get(k) for k in ("brewery", "style", "abv", "notes")):
            return
        beers.append(normalized)

    for row in soup.select("table tr"):
        cells = [normalize_space(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        add_beer(
            {
                "name": cells[0],
                "brewery": cells[1] if len(cells) > 1 else "",
                "style": cells[2] if len(cells) > 2 else "",
                "abv": cells[3] if len(cells) > 3 else "",
                "notes": " | ".join(cells[4:]) if len(cells) > 4 else "",
            }
        )

    for item in soup.select("li, article, div"):
        text = normalize_space(item.get_text(" ", strip=True))
        if len(text) < 18 or len(text) > 240:
            continue
        if not re.search(r"\b(ipa|lager|ale|stout|porter|pils|sour|wit|weizen|abv|%|brewery)\b", text.lower()):
            continue
        parts = [normalize_space(p) for p in re.split(r"\s+[–|-]\s+|\s+\|\s+", text) if normalize_space(p)]
        if len(parts) < 2:
            continue
        add_beer(
            {
                "name": parts[0],
                "brewery": parts[1] if len(parts) > 1 else "",
                "style": parts[2] if len(parts) > 2 else "",
                "abv": parts[3] if len(parts) > 3 and "%" in parts[3] else "",
                "notes": " | ".join(parts[3:]) if len(parts) > 3 else "",
            }
        )

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
    cached = None
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
        if len(payload["beers"]) == 0 and cache_file.exists():
            errors.append("beer list refresh parsed 0 beers; kept previous cached beer list")
            try:
                stale = json.loads(cache_file.read_text(encoding="utf-8"))
                stale["source"] = "cache:stale"
                stale["warning"] = " | ".join(errors)
                return stale
            except Exception:
                pass
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
    logger.info("beer cache refresh complete: beer_count=%s", payload["beer_count"])
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


def parse_abv_value(value: str) -> float | None:
    if not value:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", value)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def parse_route_command(latest_user: str) -> dict:
    text = (latest_user or "").strip()
    low = text.lower()
    route_match = re.search(r"\bbeer\s*route\b|\bpiwa\s*route\b|\btrasa\s*piw\b", low)
    if not route_match:
        return {"active": False, "debug": "No 'beer route' command detected."}

    nums = [int(x) for x in re.findall(r"\b\d+\b", text)]
    style_match = re.search(r"\b(ipa|stout|porter|lager|pils|sour|gose|wheat|hazy|ale)\b", low)
    count_match = re.search(r"\b(?:count|top|x)\s*(\d+)\b", low)
    abv_cap_match = re.search(r"\b(?:under|max|below)\s*(\d+(?:[.,]\d+)?)\s*%?\b", low)
    abv_floor_match = re.search(r"\b(?:over|min|above)\s*(\d+(?:[.,]\d+)?)\s*%?\b", low)

    route_id = nums[0] if nums else 1
    route_id = max(1, min(5, route_id))
    start_stop = nums[1] if len(nums) > 1 else None
    end_stop = nums[2] if len(nums) > 2 else None
    count = int(count_match.group(1)) if count_match else DEFAULT_ROUTE_SIZE
    count = max(1, min(12, count))
    abv_max = float(abv_cap_match.group(1).replace(",", ".")) if abv_cap_match else None
    abv_min = float(abv_floor_match.group(1).replace(",", ".")) if abv_floor_match else None

    return {
        "active": True,
        "route_id": route_id,
        "route_hint": ROUTE_IDEAS.get(route_id, ROUTE_IDEAS[1]),
        "start_stop": start_stop,
        "end_stop": end_stop,
        "style": style_match.group(1) if style_match else "",
        "count": count,
        "abv_min": abv_min,
        "abv_max": abv_max,
        "debug": f"Parsed route={route_id}, start={start_stop}, end={end_stop}, style={style_match.group(1) if style_match else 'none'}, count={count}, abv_min={abv_min}, abv_max={abv_max}",
    }


def detect_festival_plan_intent(latest_user: str) -> bool:
    text = normalize_space((latest_user or "").lower().replace("_", " "))
    if not text:
        return False
    triggers = [
        "piwa what now",
        "piwa what to do",
        "piwa what",
        "what now piwa",
    ]
    return any(t in text for t in triggers)


def detect_help_beers_intent(latest_user: str) -> bool:
    text = normalize_space((latest_user or "").lower().replace("_", " "))
    if not text:
        return False
    return ("help beers" in text) or ("beer help" in text) or ("pomoc piwa" in text)


def detect_revisit_intent(latest_user: str) -> bool:
    text = normalize_space((latest_user or "").lower().replace("_", " "))
    if not text:
        return False
    triggers = [
        "revisit",
        "repeat",
        "again",
        "show drank beers",
        "revisit drank beers",
        "pokaz znowu",
    ]
    return any(t in text for t in triggers)


def build_help_beers_text() -> str:
    return "\n".join([
        "- help beers",
        "- beer route <route_id> <style> top <count> under <abv>%",
        "- beer route 3 stout top 5 over 8%",
        "- piwa what now  (for day plan + map tips)",
        "- revisit drank beers  (allow previously consumed beers again)",
    ])


def build_day_plan_actions(today_hint: str) -> str:
    return "\n".join([
        f"- {today_hint}",
        "- Start near your closest zone on the interactive map, then move in one direction only.",
        "- Use a 2+1 rhythm: two beer stops, then one water/food stop.",
        "- Alternate strong and light beers to reduce palate fatigue.",
        "- Mark 2 fallback stands nearby in case queues are long.",
    ])


def extract_requested_style(latest_user: str) -> str:
    text = normalize_space((latest_user or "").lower())
    if not text:
        return ""
    style_match = re.search(r"\b(ipa|stout|porter|lager|pils|sour|gose|wheat|hazy|ale)\b", text)
    if not style_match:
        return ""
    style = style_match.group(1)
    if re.search(r"\b(want|looking for|like|prefer|chce|poprosz[eę]|lubi[eę]|beer want)\b", text):
        return style
    return style if len(text.split()) <= 5 else ""


def filter_beers(beers: list[dict], style: str = "", abv_min: float | None = None, abv_max: float | None = None) -> list[dict]:
    out = []
    style_low = (style or "").lower().strip()
    for beer in beers:
        if style_low:
            hay = " ".join([beer.get("name", ""), beer.get("style", ""), beer.get("notes", "")]).lower()
            if style_low not in hay:
                continue
        abv = parse_abv_value(beer.get("abv", ""))
        if abv_min is not None and (abv is None or abv < abv_min):
            continue
        if abv_max is not None and (abv is None or abv > abv_max):
            continue
        out.append(beer)
    return out


def extract_consumed_beers(messages: list[dict]) -> list[str]:
    consumed = []
    patterns = [
        r"\bi\s+drank\s+([^.,;\n]+)",
        r"\bi\s+had\s+([^.,;\n]+)",
        r"\bi\s+already\s+drank\s+([^.,;\n]+)",
        r"\b(wypi[łl]em|wypi[łl]am|pi[łl]em)\s+([^.,;\n]+)",
    ]
    for m in messages:
        if m.get("role") != "user":
            continue
        text = m.get("content", "")
        low = text.lower()
        for pattern in patterns:
            for hit in re.finditer(pattern, low):
                chunk = hit.group(1) if len(hit.groups()) == 1 else hit.group(2)
                parts = [normalize_space(p) for p in re.split(r"\band\b|,|/|\+|\boraz\b", chunk) if normalize_space(p)]
                for part in parts:
                    if len(part) >= 3:
                        consumed.append(part)
    unique = []
    seen = set()
    for item in consumed:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique[:20]


def exclude_consumed(beers: list[dict], consumed: list[str]) -> list[dict]:
    if not consumed:
        return beers
    consumed_low = [x.lower() for x in consumed]
    out = []
    for beer in beers:
        hay = " ".join([beer.get("name", ""), beer.get("brewery", ""), beer.get("style", "")]).lower()
        if any(c in hay for c in consumed_low):
            continue
        out.append(beer)
    return out


def build_beer_bot_context(data_root: Path, messages: list[dict], latest_user: str) -> str:
    catalog = read_or_refresh_cache(data_root=data_root, max_age_hours=12)
    beers = catalog.get("beers", [])
    matched = select_beers_for_query(beers, latest_user, limit=24)
    memory = extract_memory_signals(messages)
    consumed = extract_consumed_beers(messages)
    today_hint = build_today_hint()
    route = parse_route_command(latest_user)
    wants_plan = detect_festival_plan_intent(latest_user)
    wants_help = detect_help_beers_intent(latest_user)
    wants_revisit = detect_revisit_intent(latest_user)
    requested_style = extract_requested_style(latest_user)
    starter = ""
    latest_low = (latest_user or "").lower()
    if normalize_space(latest_low) in {"beer", "piwo", "piwa"}:
        starter = "User asked only for beer. First ask: 'What beer style do you want (e.g., stout, ipa, lager)?'"
    elif "beer" in latest_low or "piwo" in latest_low or "piwa" in latest_low:
        starter = "Detected the word 'beer/piwo'. Ask: 'Do you want to get a beer now? If yes, what style mood do you want?'"
    elif not memory["styles"]:
        starter = "If preference is missing, ask a quick preference question before recommending."

    filtered = matched
    if route.get("active"):
        filtered = filter_beers(
            filtered,
            style=route.get("style", ""),
            abv_min=route.get("abv_min"),
            abv_max=route.get("abv_max"),
        )
        filtered = filtered[: route.get("count", 5)]
    if not wants_revisit:
        filtered = exclude_consumed(filtered, consumed)

    match_lines = [
        f"- {b.get('name','')} | brewery: {b.get('brewery','?')} | style: {b.get('style','?')} | abv: {b.get('abv','?')}"
        for b in filtered
    ]
    ambassador_lines = [f"- {name}" for name in catalog.get("ambassadors", [])[:20]]
    warning = catalog.get("warning", "")
    route_lines = [f"- Route {key}: {value}" for key, value in ROUTE_IDEAS.items()]
    consumed_lines = [f"- {x}" for x in consumed]
    route_examples = "\n".join(f"- {x}" for x in ROUTE_EXAMPLES)
    day_plan_actions = build_day_plan_actions(today_hint)
    help_beers_text = build_help_beers_text()
    style_focus = filter_beers(beers, style=requested_style) if requested_style else []
    if style_focus and not wants_revisit:
        style_focus = exclude_consumed(style_focus, consumed)
    style_focus_lines = [
        f"- {b.get('name','')} | brewery: {b.get('brewery','?')} | style: {b.get('style','?')} | abv: {b.get('abv','?')}"
        for b in style_focus[:8]
    ]

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
- Add variety in tone: use festival guide, donkey detective, lab analyzer, fankydog, and friendly/crazy bartender speaking styles.
- Handle command variants like 'piwa what now', 'piwa_what to do', or 'piwa what to do' by giving the day-specific action plan below.
- {today_hint}
- If user says 'help beers' (or similar), return a concise beer-command help with examples.
- Plan intent detected now: {"yes" if wants_plan else "no"}
- Help intent detected now: {"yes" if wants_help else "no"}
- Revisit consumed beers intent detected: {"yes" if wants_revisit else "no"}
- Requested style detected from latest message: {requested_style or "none"}
- Help command examples: {", ".join(HELP_BEERS_EXAMPLES)}

Route intelligence:
{chr(10).join(route_lines)}
- Route example set:
{route_examples}
- Route parse diagnostics: {route.get("debug", "none")}
- Active route hint: {route.get("route_hint", "none")}
- Route start/end stops: {route.get("start_stop", "n/a")} -> {route.get("end_stop", "n/a")}

Remembered consumed beers (avoid repeats):
{chr(10).join(consumed_lines) if consumed_lines else "- none remembered"}

Best matches for latest message and filters:
{chr(10).join(match_lines) if match_lines else "- No beer matches available after filters/consumed exclusion."}

Direct style matches for latest style request (e.g. 'beer want stout'):
{chr(10).join(style_focus_lines) if style_focus_lines else "- No style-specific matches detected from latest message."}

Ambassadors remembered:
{chr(10).join(ambassador_lines) if ambassador_lines else "- No ambassadors extracted yet."}

Map guidance hints:
- Use the interactive map URL to suggest nearby stands and shorter walking loops.
- Prefer a route that alternates strong and light beers, and include water/food break hints.

If plan command is detected, return this day-plan template:
{day_plan_actions}

If help command is detected, return this concise command help:
{help_beers_text}
"""
