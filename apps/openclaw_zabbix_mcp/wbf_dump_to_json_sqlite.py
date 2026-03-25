#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

PLN_TO_EUR = 0.23

RATING_RE = re.compile(r"Rated\s+([0-9]+(?:\.[0-9]+)?)\s+out of 5 on Untappd", re.IGNORECASE)
ABV_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%\s*ABV", re.IGNORECASE)
IBU_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*IBU", re.IGNORECASE)
DISPLAYING_RE = re.compile(r"^Displaying all \d+ items$", re.IGNORECASE)
MORE_INFO_RE = re.compile(r"^More Info\s*▸\s*$", re.IGNORECASE)
NO_ITEMS_RE = re.compile(r"^No items found$", re.IGNORECASE)

PRICE_RE = re.compile(r"zł\s*([0-9]+(?:[.,][0-9]{2})?)", re.IGNORECASE)

SERVING_RE = re.compile(
    r"""^
    (?P<size>
        \d+(?:[.,]\d+)?\s*(?:ml|mL|L)
        |
        \d+(?:[.,]\d+)?L
    )
    (?:\s+(?P<package>Draft|Bottle|Can|Btl))?
    (?:\s+(?P<price>zł\d+(?:[.,]\d{2})?))?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

STYLE_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<style>"
    r"(?:IPA|Stout|Porter|Pilsner|Lager|Sour|Wheat Beer|Wild Ale|Historical Beer|"
    r"Farmhouse Ale|Fruit Beer|Freeze-Distilled Beer|Mead|Belgian Blonde|Belgian Enkel|"
    r"Bitter|Brown Ale|Strong Ale|Rauchbier|Bock|Kvass|Cider|Grape Ale|Gluten-Free|"
    r"Schwarzbier|Spiced|Pale Ale|Barleywine|Brett Beer|Honey Beer|Lambic|Scotch Ale|"
    r"Red Ale|Non-Alcoholic|Old|Braggot|Belgian Quadrupel|Belgian Quadruple|"
    r"Belgian Dubbel|Belgian Tripel|Belgian Pale Ale|Belgian IPA|Farmhouse IPA|"
    r"Witbier|Märzen|Kellerbier|Munich Dunkel|Polotmavé \(Czech Amber\)|"
    r"Světlé \(Czech Pale\)|Helles|American Amber|Cyser|Melomel|Metheglin|Traditional|Other)"
    r"(?:\s*-\s*.+)?"
    r")\s*$",
    re.IGNORECASE,
)

LEADING_INDEX_RE = re.compile(r"^\d+\.\s*")


@dataclass
class ServingOption:
    size: Optional[str] = None
    package: Optional[str] = None
    price_pln: Optional[float] = None
    price_eur: Optional[float] = None
    raw_text: Optional[str] = None


@dataclass
class Beer:
    name: str
    style: Optional[str] = None
    abv: Optional[float] = None
    ibu: Optional[float] = None
    rating: Optional[float] = None
    brewery: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    serving_options: List[ServingOption] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)


@dataclass
class Brewery:
    brewery: str
    location: Optional[str] = None
    note: Optional[str] = None
    beers: List[Beer] = field(default_factory=list)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_line(line: str) -> str:
    return line.replace("\u00a0", " ").strip()


def round_eur(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * PLN_TO_EUR, 2)


def parse_price_pln(raw_price: Optional[str]) -> Optional[float]:
    if not raw_price:
        return None
    m = PRICE_RE.search(raw_price)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def parse_serving_option(line: str) -> Optional[ServingOption]:
    m = SERVING_RE.match(line)
    if not m:
        return None

    size = m.group("size")
    package = m.group("package")
    raw_price = m.group("price")

    price_pln = parse_price_pln(raw_price)
    price_eur = round_eur(price_pln)

    return ServingOption(
        size=normalize_whitespace(size) if size else None,
        package=normalize_whitespace(package) if package else None,
        price_pln=price_pln,
        price_eur=price_eur,
        raw_text=normalize_whitespace(line),
    )


def dedupe_serving_options(items: List[ServingOption]) -> List[ServingOption]:
    seen = set()
    out = []
    for item in items:
        key = (item.size, item.package, item.price_pln, item.raw_text)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def is_obvious_noise(line: str) -> bool:
    if not line:
        return True
    if DISPLAYING_RE.match(line):
        return True
    if MORE_INFO_RE.match(line):
        return True
    if NO_ITEMS_RE.match(line):
        return True
    return False


def looks_like_serving(line: str) -> bool:
    return bool(SERVING_RE.match(line))


def looks_like_style_or_beerish_text(line: str) -> bool:
    if not line:
        return False

    l = normalize_whitespace(line).lower()

    bad_markers = [
        " ipa",
        "stout",
        "porter",
        "lager",
        "pils",
        "pilsner",
        "gose",
        "sour",
        "wild ale",
        "historical beer",
        "wheat beer",
        "freeze-distilled beer",
        "mead -",
        "cider -",
        "barleywine",
        "hefeweizen",
        "new england",
        "imperial",
        "smoothie",
        "abv",
        "ibu",
        "rated ",
    ]

    if any(x in l for x in bad_markers):
        return True

    if STYLE_LINE_RE.match(LEADING_INDEX_RE.sub("", line)):
        return True

    return False


def looks_like_location_text(line: str) -> bool:
    if not line:
        return False

    l = normalize_whitespace(line)
    low = l.lower()

    location_hints = [
        ",",
        "voivodeship",
        "mazowieck",
        "małopol",
        "pomorsk",
        "warmińsko",
        "śląsk",
        "podlask",
        "lubelsk",
        "dolnośląsk",
        "estonia",
        "latvia",
        "lithuania",
        "poland",
        "germany",
        "romania",
        "czech",
        "fl",
    ]

    return any(h in low for h in location_hints)


def looks_like_brewery_name(line: str) -> bool:
    if not line:
        return False

    l = normalize_whitespace(line)
    low = l.lower()

    if is_obvious_noise(l):
        return False

    if looks_like_serving(l):
        return False

    if looks_like_style_or_beerish_text(l):
        return False

    if len(l) > 80:
        return False

    if ABV_RE.search(l) or IBU_RE.search(l) or RATING_RE.search(l):
        return False

    banned_exact = {
        "unknown brewery",
        "draft",
        "bottle",
        "can",
        "btl",
    }
    if low in banned_exact:
        return False

    return True


def parse_abv_ibu_rating(line: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "abv": None,
        "ibu": None,
        "rating": None,
        "brewery": None,
        "location": None,
    }

    m_abv = ABV_RE.search(line)
    if m_abv:
        result["abv"] = float(m_abv.group(1))

    m_ibu = IBU_RE.search(line)
    if m_ibu:
        result["ibu"] = float(m_ibu.group(1))

    m_rating = RATING_RE.search(line)
    if m_rating:
        result["rating"] = float(m_rating.group(1))

    cleaned = ABV_RE.sub("", line)
    cleaned = IBU_RE.sub("", cleaned)
    cleaned = RATING_RE.sub("", cleaned)
    cleaned = normalize_whitespace(cleaned)

    if not cleaned:
        return result

    m = re.match(r"^(?P<brewery>.+?)\s+(?P<location>[^,]+,\s*.+)$", cleaned)
    if m:
        brewery = normalize_whitespace(m.group("brewery"))
        location = normalize_whitespace(m.group("location"))

        if looks_like_brewery_name(brewery) and looks_like_location_text(location):
            result["brewery"] = brewery
            result["location"] = location

    return result


def looks_like_brewery_header(lines: List[str], idx: int) -> bool:
    line = clean_line(lines[idx])
    if not looks_like_brewery_name(line):
        return False

    next_nonempty = None
    for j in range(idx + 1, min(idx + 6, len(lines))):
        t = clean_line(lines[j])
        if t:
            next_nonempty = t
            break

    if next_nonempty is None:
        return False

    next_clean = LEADING_INDEX_RE.sub("", next_nonempty)

    if NO_ITEMS_RE.match(next_nonempty):
        return True

    if looks_like_style_or_beerish_text(next_clean):
        return True

    if ABV_RE.search(next_nonempty):
        return True

    return False


def find_style_line(lines: List[str], start_idx: int, max_lookahead: int = 3) -> Optional[int]:
    for j in range(start_idx, min(start_idx + max_lookahead, len(lines))):
        line = clean_line(lines[j])
        if not line:
            continue
        line2 = LEADING_INDEX_RE.sub("", line)
        if STYLE_LINE_RE.match(line2):
            return j
    return None


def parse_beer_block(lines: List[str], start_idx: int, default_brewery: str) -> tuple[Optional[Beer], int]:
    i = start_idx
    n = len(lines)

    while i < n and not clean_line(lines[i]):
        i += 1
    if i >= n:
        return None, i

    name_line = LEADING_INDEX_RE.sub("", clean_line(lines[i]))
    i += 1

    while i < n and not clean_line(lines[i]):
        i += 1
    if i >= n:
        return Beer(name=name_line, brewery=default_brewery), i

    style_line_raw = LEADING_INDEX_RE.sub("", clean_line(lines[i]))
    style = None
    parsed_name_from_style = None

    m_style = STYLE_LINE_RE.match(style_line_raw)
    if m_style:
        parsed_name_from_style = normalize_whitespace(m_style.group("name"))
        style = normalize_whitespace(m_style.group("style"))
        i += 1
    else:
        parsed_name_from_style = name_line

    beer_name = parsed_name_from_style or name_line

    while i < n and not clean_line(lines[i]):
        i += 1

    abv = None
    ibu = None
    rating = None
    brewery = default_brewery
    location = None
    description_parts: List[str] = []
    serving_options: List[ServingOption] = []
    raw_lines: List[str] = []

    if i < n:
        info_line = clean_line(lines[i])
        if ABV_RE.search(info_line) or RATING_RE.search(info_line) or "ABV" in info_line or "IBU" in info_line:
            parsed = parse_abv_ibu_rating(info_line)
            abv = parsed["abv"]
            ibu = parsed["ibu"]
            rating = parsed["rating"]

            if parsed["brewery"]:
                brewery = parsed["brewery"]
            if parsed["location"]:
                location = parsed["location"]

            raw_lines.append(info_line)
            i += 1

    while i < n:
        line = clean_line(lines[i])

        if not line:
            i += 1
            continue

        if is_obvious_noise(line):
            if DISPLAYING_RE.match(line):
                break
            i += 1
            continue

        if looks_like_serving(line):
            break

        style_at_here = LEADING_INDEX_RE.sub("", line)
        if STYLE_LINE_RE.match(style_at_here):
            break

        if looks_like_brewery_header(lines, i):
            lookahead_style = find_style_line(lines, i + 1, max_lookahead=3)
            if lookahead_style == i + 1:
                break

        raw_lines.append(line)
        description_parts.append(line)
        i += 1

    while i < n:
        line = clean_line(lines[i])
        if not line:
            i += 1
            continue
        if looks_like_serving(line):
            parsed_serving = parse_serving_option(line)
            if parsed_serving:
                serving_options.append(parsed_serving)
            i += 1
            continue
        break

    description = normalize_whitespace(" ".join(description_parts)) if description_parts else None

    beer = Beer(
        name=beer_name,
        style=style,
        abv=abv,
        ibu=ibu,
        rating=rating,
        brewery=brewery,
        location=location,
        description=description,
        serving_options=dedupe_serving_options(serving_options),
        raw_lines=raw_lines,
    )
    return beer, i


def parse_dump(text: str) -> List[Brewery]:
    lines = [clean_line(x) for x in text.splitlines()]
    n = len(lines)
    breweries: List[Brewery] = []

    current_brewery: Optional[Brewery] = None
    i = 0

    while i < n:
        line = lines[i]

        if not line:
            i += 1
            continue

        if is_obvious_noise(line):
            i += 1
            continue

        if looks_like_brewery_header(lines, i):
            next_style = find_style_line(lines, i + 1, max_lookahead=2)
            if next_style == i + 1:
                brewery_name = line
                current_brewery = Brewery(brewery=brewery_name)
                breweries.append(current_brewery)
                i += 1

                note_parts = []
                while i < n:
                    peek = lines[i]
                    if not peek:
                        i += 1
                        continue
                    if is_obvious_noise(peek):
                        i += 1
                        break
                    style_pos = find_style_line(lines, i, max_lookahead=2)
                    if style_pos is not None:
                        break
                    if looks_like_serving(peek):
                        break
                    if ABV_RE.search(peek):
                        break
                    if looks_like_style_or_beerish_text(peek):
                        break
                    note_parts.append(peek)
                    i += 1

                if note_parts:
                    current_brewery.note = normalize_whitespace(" ".join(note_parts))
                continue

        if current_brewery is not None:
            style_pos = find_style_line(lines, i + 1, max_lookahead=2)
            if style_pos is not None:
                beer, new_i = parse_beer_block(lines, i, current_brewery.brewery)
                if beer:
                    if not current_brewery.location and beer.location:
                        current_brewery.location = beer.location
                    current_brewery.beers.append(beer)
                    i = new_i
                    continue

        i += 1

    return breweries


def breweries_to_jsonable(breweries: List[Brewery]) -> List[Dict[str, Any]]:
    result = []
    for b in breweries:
        result.append(
            {
                "brewery": b.brewery,
                "location": b.location,
                "note": b.note,
                "beers": [
                    {
                        "name": beer.name,
                        "style": beer.style,
                        "abv": beer.abv,
                        "ibu": beer.ibu,
                        "rating": beer.rating,
                        "brewery": beer.brewery,
                        "location": beer.location,
                        "description": beer.description,
                        "serving_options": [
                            {
                                "size": s.size,
                                "package": s.package,
                                "price_pln": s.price_pln,
                                "price_eur": s.price_eur,
                                "raw_text": s.raw_text,
                            }
                            for s in beer.serving_options
                        ],
                    }
                    for beer in b.beers
                ],
            }
        )
    return result


def init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS breweries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            location TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS beers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brewery_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            style TEXT,
            abv REAL,
            ibu REAL,
            rating REAL,
            location TEXT,
            description TEXT,
            UNIQUE(brewery_id, name),
            FOREIGN KEY (brewery_id) REFERENCES breweries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS serving_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beer_id INTEGER NOT NULL,
            size TEXT,
            package TEXT,
            price_pln REAL,
            price_eur REAL,
            raw_text TEXT NOT NULL,
            UNIQUE(beer_id, raw_text),
            FOREIGN KEY (beer_id) REFERENCES beers(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()


def save_to_sqlite(breweries: List[Brewery], sqlite_path: Path) -> None:
    conn = sqlite3.connect(sqlite_path)
    try:
        init_sqlite(conn)

        for brewery in breweries:
            conn.execute(
                """
                INSERT INTO breweries(name, location, note)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    location = excluded.location,
                    note = excluded.note
                """,
                (brewery.brewery, brewery.location, brewery.note),
            )
            brewery_id = conn.execute(
                "SELECT id FROM breweries WHERE name = ?",
                (brewery.brewery,),
            ).fetchone()[0]

            for beer in brewery.beers:
                conn.execute(
                    """
                    INSERT INTO beers(brewery_id, name, style, abv, ibu, rating, location, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(brewery_id, name) DO UPDATE SET
                        style = excluded.style,
                        abv = excluded.abv,
                        ibu = excluded.ibu,
                        rating = excluded.rating,
                        location = excluded.location,
                        description = excluded.description
                    """,
                    (
                        brewery_id,
                        beer.name,
                        beer.style,
                        beer.abv,
                        beer.ibu,
                        beer.rating,
                        beer.location,
                        beer.description,
                    ),
                )

                beer_id = conn.execute(
                    "SELECT id FROM beers WHERE brewery_id = ? AND name = ?",
                    (brewery_id, beer.name),
                ).fetchone()[0]

                for s in beer.serving_options:
                    conn.execute(
                        """
                        INSERT INTO serving_options(beer_id, size, package, price_pln, price_eur, raw_text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(beer_id, raw_text) DO UPDATE SET
                            size = excluded.size,
                            package = excluded.package,
                            price_pln = excluded.price_pln,
                            price_eur = excluded.price_eur
                        """,
                        (
                            beer_id,
                            s.size,
                            s.package,
                            s.price_pln,
                            s.price_eur,
                            s.raw_text,
                        ),
                    )

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert WBF dump to JSON and SQLite.")
    parser.add_argument("input_file", help="Path to raw text dump file")
    parser.add_argument("--json-out", default="wbf_dump.json", help="Output JSON file")
    parser.add_argument("--sqlite-out", default="wbf_dump.db", help="Output SQLite file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    json_path = Path(args.json_out)
    sqlite_path = Path(args.sqlite_out)

    text = input_path.read_text(encoding="utf-8", errors="replace")
    breweries = parse_dump(text)

    jsonable = breweries_to_jsonable(breweries)
    json_path.write_text(
        json.dumps(jsonable, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
    )

    save_to_sqlite(breweries, sqlite_path)

    brewery_count = len(breweries)
    beer_count = sum(len(b.beers) for b in breweries)
    serving_count = sum(len(b.serving_options) for br in breweries for b in br.beers)

    print(f"[+] Parsed breweries: {brewery_count}")
    print(f"[+] Parsed beers: {beer_count}")
    print(f"[+] Parsed serving options: {serving_count}")
    print(f"[+] Exchange rate used: 1 PLN = {PLN_TO_EUR:.2f} EUR")
    print(f"[+] JSON written to: {json_path}")
    print(f"[+] SQLite written to: {sqlite_path}")


if __name__ == "__main__":
    main()
