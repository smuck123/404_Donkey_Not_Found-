import logging
import random
import re
from typing import Any

from wbf_repository import WBFRepository

LOG = logging.getLogger(__name__)

STYLE_ALIASES = {
    "ipa": ["ipa"],
    "neipa": ["ipa - new england", "new england ipa", "neipa", "hazy ipa"],
    "ddh": ["ddh ipa", "ipa"],
    "pale ale": ["pale ale"],
    "lager": ["lager", "helles"],
    "pils": ["pils", "pilsner", "czech pale", "světlé"],
    "pilsner": ["pilsner", "pils", "czech pale", "světlé"],
    "porter": ["porter", "baltic porter"],
    "stout": ["stout"],
    "imperial stout": ["imperial stout", "stout - imperial"],
    "sour": ["sour"],
    "gose": ["gose"],
    "berliner weisse": ["berliner weisse"],
    "pastry sour": ["pastry sour", "sour - smoothie", "sour - fruited"],
    "fruit ale": ["fruit beer", "fruit ale"],
    "wheat": ["wheat", "witbier"],
    "weizen": ["weizen", "hefeweizen"],
    "hefeweizen": ["hefeweizen"],
    "saison": ["saison", "farmhouse ale"],
    "barleywine": ["barleywine"],
    "tripel": ["tripel"],
    "dubbel": ["dubbel"],
    "kvass": ["kvass"],
    "non alcoholic": ["non-alcoholic", "alcohol free", "nolo", "free"],
    "alcohol free": ["non-alcoholic", "alcohol free", "nolo", "free"],
    "nolo": ["non-alcoholic", "alcohol free", "nolo", "free"],
    "wild": ["wild ale"],
    "lambic": ["lambic"],
    "mead": ["mead"],
    "cider": ["cider"],
    "schwarzbier": ["schwarzbier"],
    "grodziskie": ["grodziskie", "historical beer - grodziskie"],
}

STYLE_KEYS = sorted(STYLE_ALIASES.keys(), key=len, reverse=True)

STOPWORDS = {
    "cheap", "cheapest", "budget", "low", "price", "expensive",
    "strong", "strongest", "high", "abv",
    "under", "below", "less", "than", "over", "above", "more", "max", "min",
    "with", "and", "or",
    "random", "similar", "different", "something", "like", "last", "my", "new",
    "beer", "beers", "drink", "next", "recommend", "for", "please",
    "zl", "zł", "pln", "eur", "euro",
    "can", "draft", "bottle",
    "style", "brewery", "text", "find",
    "after", "id",
}

PACKAGE_WORDS = {"can", "draft", "bottle"}
SIZE_PATTERNS = ["100ml", "150ml", "200ml", "300ml", "330ml", "375ml", "473ml", "500ml", "0.5l", "750ml"]


class WarsawBeerFestivalAssistant:
    def __init__(self, repository: WBFRepository | None = None):
        self.repository = repository or WBFRepository()

    def ensure_data_loaded(self) -> dict[str, int]:
        return self.repository.counts()

    def _extract_style_keys(self, q: str) -> list[str]:
        hits: list[str] = []
        for key in STYLE_KEYS:
            if key in q:
                hits.append(key)
        return hits

    def _expand_style_aliases(self, style_keys: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for key in style_keys:
            for alias in STYLE_ALIASES.get(key, [key]):
                alias_l = alias.lower().strip()
                if alias_l not in seen:
                    seen.add(alias_l)
                    out.append(alias_l)
        return out

    def _clean_query_for_tokens(self, q: str) -> str:
        work = q.lower()

        for key in STYLE_KEYS:
            work = work.replace(key, " ")

        work = re.sub(r"--[a-z0-9\-]+", " ", work)
        work = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:%|abv|zl|zł|pln|eur|euro)\b", " ", work)
        work = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", work)

        for size in SIZE_PATTERNS:
            work = work.replace(size, " ")

        for word in PACKAGE_WORDS:
            work = work.replace(word, " ")

        work = re.sub(r"[^a-z0-9\-\+\s]", " ", work)
        work = re.sub(r"\s+", " ", work).strip()
        return work

    def _parse_query(self, query: str) -> dict[str, Any]:
        q = (query or "").strip().lower()

        style_keys = self._extract_style_keys(q)
        style_aliases = self._expand_style_aliases(style_keys)

        max_abv = None
        min_abv = None
        max_budget = None
        package = None
        size = None
        sort_by = "name"
        after_id = None
        random_count = 1

        m = re.search(r"(?:under|max|below|less than)\s*(\d+(?:[.,]\d+)?)\s*(?:abv|%)?", q)
        if m:
            max_abv = float(m.group(1).replace(",", "."))

        m = re.search(r"(?:over|min|above|more than)\s*(\d+(?:[.,]\d+)?)\s*(?:abv|%)?", q)
        if m:
            min_abv = float(m.group(1).replace(",", "."))

        m = re.search(r"(?:under|max|below|less than)\s*(\d+(?:[.,]\d+)?)\s*(?:zl|zł|pln)", q)
        if m:
            max_budget = float(m.group(1).replace(",", "."))

        m = re.search(r"--min-abv\s+(\d+(?:[.,]\d+)?)", q)
        if m:
            min_abv = float(m.group(1).replace(",", "."))

        m = re.search(r"--max-abv\s+(\d+(?:[.,]\d+)?)", q)
        if m:
            max_abv = float(m.group(1).replace(",", "."))

        m = re.search(r"--after-id\s+(\d+)", q)
        if m:
            after_id = int(m.group(1))

        if "cheap" in q or "cheapest" in q or "budget" in q or "low price" in q:
            sort_by = "cheap"
        elif "strongest" in q or "high abv" in q or "strong " in q or q.startswith("strong"):
            sort_by = "strong"
        elif "expensive" in q:
            sort_by = "name"

        if "can" in q:
            package = "can"
        elif "draft" in q:
            package = "draft"
        elif "bottle" in q:
            package = "bottle"

        for s in SIZE_PATTERNS:
            if s in q:
                size = s
                break

        want_random = "random" in q
        want_similar = any(x in q for x in ["similar", "like my last", "like last", "something like"])
        want_different = any(x in q for x in ["different", "other", "something else", "new style"])

        m = re.search(r"\brandom\s+(\d+)\b", q)
        if m:
            random_count = max(1, min(20, int(m.group(1))))

        token_source = self._clean_query_for_tokens(q)
        tokens = [
            t for t in re.findall(r"[a-z0-9\-\+]+", token_source)
            if len(t) >= 3 and t not in STOPWORDS
        ]

        return {
            "raw": q,
            "style_keys": style_keys,
            "style_aliases": style_aliases,
            "tokens": tokens,
            "max_abv": max_abv,
            "min_abv": min_abv,
            "max_budget": max_budget,
            "package": package,
            "size": size,
            "sort_by": sort_by,
            "want_random": want_random,
            "random_count": random_count,
            "want_similar": want_similar,
            "want_different": want_different,
            "after_id": after_id,
        }

    def _style_score(self, parsed: dict[str, Any], style_val: str) -> float:
        style_val = (style_val or "").lower().strip()
        if not style_val:
            return 0.0

        score = 0.0
        requested_keys = parsed["style_keys"]
        requested_aliases = parsed["style_aliases"]

        if not requested_keys:
            return score

        for key in requested_keys:
            if key == style_val:
                score += 8.0
            elif key in style_val:
                score += 4.0

        for alias in requested_aliases:
            if alias == style_val:
                score += 10.0
            elif alias in style_val:
                score += 6.0

        if "ipa" in requested_keys and "sour" not in requested_keys and "ipa - sour" in style_val:
            score -= 3.0
        if "sour" in requested_keys and "ipa" not in requested_keys and "ipa - sour" in style_val:
            score += 2.0
        if "lager" in requested_keys and "non-alcoholic" in style_val:
            score -= 1.5
        if "stout" in requested_keys and "porter" in style_val and "stout" not in style_val:
            score -= 1.0
        if "porter" in requested_keys and "stout" in style_val and "porter" not in style_val:
            score -= 1.0

        if "neipa" in requested_keys:
            if "new england" in style_val or "neipa" in style_val or "hazy ipa" in style_val:
                score += 5.0
            elif "ipa" in style_val:
                score += 1.0

        return score

    def recommend_beer(self, chat_id: int, query: str = "", random_mode: bool = False) -> dict | None:
        profile = self.repository.get_user_profile(chat_id)
        drank_ids = self.repository.drank_beer_ids(chat_id)
        parsed = self._parse_query(query)

        repository_style = parsed["style_aliases"] if parsed["style_aliases"] else None
        profile_max_abv = float(profile.get("max_abv", 99.0) or 99.0)

        all_beers = self.repository.list_beers(
            query=" ".join(parsed["tokens"]) if parsed["tokens"] else "",
            style=repository_style,
            max_abv=min(profile_max_abv, parsed["max_abv"]) if parsed["max_abv"] is not None else profile_max_abv,
            min_abv=parsed["min_abv"],
            max_price_pln=parsed["max_budget"],
            package=parsed["package"],
            size=parsed["size"],
            sort_by=parsed["sort_by"],
            limit=500,
        )

        if not all_beers:
            return None

        avoid_names = {x.lower() for x in profile.get("avoid_list", [])}
        pref_styles = [x.lower() for x in profile.get("style_preferences", [])]
        history = self.repository.history(chat_id, limit=5)
        last_beer = history[0] if history else None
        last_style = (last_beer.get("style") or "").lower() if last_beer else ""

        scored: list[tuple[float, dict[str, Any]]] = []

        for beer in all_beers:
            beer_id = int(beer.get("id", 0) or 0)
            name = (beer.get("name") or "").lower()
            brewery = (beer.get("brewery") or "").lower()
            style_val = (beer.get("style") or "").lower()
            desc = (beer.get("description") or "").lower()

            if beer_id in drank_ids:
                continue
            if name in avoid_names:
                continue
            if parsed["after_id"] is not None and beer_id <= parsed["after_id"]:
                continue

            score = random.random() * 0.15

            if pref_styles and any(pref in style_val for pref in pref_styles):
                score += 2.0

            score += self._style_score(parsed, style_val)

            if parsed["sort_by"] == "cheap" and beer.get("cheapest_price_pln") is not None:
                score += max(0, 15 - float(beer["cheapest_price_pln"])) * 0.35

            if parsed["sort_by"] == "strong" and beer.get("abv") is not None:
                score += float(beer["abv"]) * 0.35
                if "stout" in parsed["style_keys"] and "stout" in style_val:
                    score += 2.0

            if parsed["package"] and parsed["package"].lower() in (beer.get("packages") or "").lower():
                score += 1.5

            if parsed["size"] and parsed["size"].lower() in (beer.get("sizes") or "").lower():
                score += 1.0

            if parsed["want_similar"] and last_style and last_style in style_val:
                score += 2.5

            if parsed["want_different"] and last_style and last_style not in style_val:
                score += 2.0

            if parsed["tokens"]:
                token_hits = sum(1 for t in parsed["tokens"] if t in name or t in brewery or t in style_val or t in desc)
                score += min(token_hits * 0.5, 2.5)

            if parsed["raw"]:
                if parsed["raw"] == name:
                    score += 5.0
                elif parsed["raw"] == brewery:
                    score += 4.0

            scored.append((score, beer))

        if not scored:
            return None

        if random_mode or parsed["want_random"]:
            top = sorted(scored, key=lambda x: x[0], reverse=True)[: max(20, parsed["random_count"] * 5)]
            return random.choice([b for _, b in top])

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def random_beers(self, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        parsed = self._parse_query(query)
        beers = self.repository.list_beers(
            query=" ".join(parsed["tokens"]) if parsed["tokens"] else "",
            style=parsed["style_aliases"] if parsed["style_aliases"] else None,
            min_abv=parsed["min_abv"],
            max_abv=parsed["max_abv"],
            max_price_pln=parsed["max_budget"],
            package=parsed["package"],
            size=parsed["size"],
            limit=500,
        )
        if not beers:
            return []

        random.shuffle(beers)

        if parsed["after_id"] is not None:
            beers = [b for b in beers if int(b.get("id", 0) or 0) > parsed["after_id"]]

        return beers[: max(1, min(20, limit))]

    def cheapest_beers(
        self,
        style: str | list[str] | None = None,
        budget: float | None = None,
        package: str | None = None,
        size: str | None = None,
        limit: int = 15,
    ) -> list[dict]:
        style_filter = style
        if isinstance(style, str):
            style_key = style.strip().lower()
            style_filter = STYLE_ALIASES.get(style_key, [style_key])

        beers = self.repository.cheapest_beers(
            limit=limit,
            style=style_filter,
            max_price_pln=budget,
            package=package,
            size=size,
        )

        cleaned: list[dict[str, Any]] = []
        for beer in beers:
            price = beer.get("cheapest_price_pln")
            if price is not None and float(price) <= 0:
                continue
            cleaned.append(beer)
        return cleaned

    def mark_drank(self, chat_id: int, beer_name: str) -> dict | None:
        beer = self.repository.find_beer_exact_or_like(beer_name)
        if not beer:
            return None
        self.repository.mark_drank(chat_id, int(beer["id"]))
        return beer

    def rate_beer(self, chat_id: int, beer_name: str, rating: int) -> dict | None:
        beer = self.repository.find_beer_exact_or_like(beer_name)
        if not beer:
            return None
        self.repository.set_rating(chat_id, int(beer["id"]), rating)
        return beer

    def history(self, chat_id: int) -> list[dict]:
        return self.repository.history(chat_id, limit=50)

    def set_max_abv(self, chat_id: int, max_abv: float) -> dict:
        return self.repository.update_user_profile(chat_id, max_abv=max_abv)

    def set_location(self, chat_id: int, location: str) -> dict:
        return self.repository.update_user_profile(chat_id, current_location=location)

    def find_beers(self, name: str) -> list[dict]:
        parsed = self._parse_query(name)
        style_filter = parsed["style_aliases"] if parsed["style_aliases"] else None
        text_query = " ".join(parsed["tokens"]) if parsed["tokens"] else name
        return self.repository.list_beers(query=text_query, style=style_filter, limit=10)

    def find_breweries(self, name: str) -> list[dict]:
        return self.repository.list_breweries(query=name, limit=10)

    def serving_options(self, beer_name: str) -> tuple[dict | None, list[dict]]:
        beer = self.repository.find_beer_exact_or_like(beer_name)
        if not beer:
            return None, []
        return beer, self.repository.get_serving_options(int(beer["id"]))

    def brewery_map_links(self, brewery_name: str) -> dict[str, str]:
        return self.repository.beer_shop_map_links(brewery_name)


def format_beer(beer: dict) -> str:
    if not beer:
        return "No beer found."

    price = "n/a"
    if beer.get("cheapest_price_pln") is not None:
        eur = beer.get("cheapest_price_eur")
        if eur is not None:
            price = f"{beer['cheapest_price_pln']:.2f} PLN ({eur:.2f} EUR)"
        else:
            price = f"{beer['cheapest_price_pln']:.2f} PLN"

    parts = [
        f"🍺 {beer.get('name', 'Unknown')}",
        f"Brewery: {beer.get('brewery') or 'n/a'}",
        f"Style: {beer.get('style') or 'n/a'}",
        f"ABV: {beer.get('abv') if beer.get('abv') is not None else 'n/a'}",
        f"Cheapest: {price}",
    ]

    packages = beer.get("packages")
    sizes = beer.get("sizes")

    if packages:
        parts.append(f"Packages: {packages}")
    if sizes:
        parts.append(f"Sizes: {sizes}")

    return "\n".join(parts)


def format_serving_options(beer: dict, options: list[dict]) -> str:
    if not beer:
        return "Beer not found."

    lines = [format_beer(beer), "", "Serving options:"]
    if not options:
        lines.append("- no serving options found")
        return "\n".join(lines)

    for s in options:
        price_part = ""
        if s.get("price_pln") is not None:
            if s.get("price_eur") is not None:
                price_part = f" | {s['price_pln']:.2f} PLN ({s['price_eur']:.2f} EUR)"
            else:
                price_part = f" | {s['price_pln']:.2f} PLN"
        lines.append(f"- {s.get('size') or 'n/a'} | {s.get('package') or 'n/a'}{price_part}")

    return "\n".join(lines)
