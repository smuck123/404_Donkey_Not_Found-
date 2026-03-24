import random
from datetime import datetime
from zoneinfo import ZoneInfo

from wbf_data_importer import WBFDataImporter
from wbf_repository import WBFRepository

WARSAW_TZ = ZoneInfo("Europe/Warsaw")


class WarsawBeerFestivalAssistant:
    def __init__(self, repository: WBFRepository | None = None, importer: WBFDataImporter | None = None):
        self.repository = repository or WBFRepository()
        self.importer = importer or WBFDataImporter()

    def ensure_data_loaded(self) -> dict[str, int]:
        counts = self.repository.counts()
        if counts["beers"] > 0 and counts["events"] > 0 and counts["exhibitors"] > 0:
            return counts

        try:
            beers = self.importer.import_beers()
            self.repository.upsert_beers(beers)
        except Exception:
            pass
        try:
            events = self.importer.import_events()
            self.repository.upsert_events(events)
        except Exception:
            pass
        try:
            exhibitors = self.importer.import_exhibitors_from_pdf()
            self.repository.upsert_exhibitors(exhibitors)
        except Exception:
            pass
        return self.repository.counts()

    def recommend_beer(self, chat_id: int, query: str = "", random_mode: bool = False) -> dict | None:
        profile = self.repository.get_user_profile(chat_id)
        drank_ids = self.repository.drank_beer_ids(chat_id)

        all_beers = self.repository.list_beers(query=query, limit=400)
        if not all_beers:
            all_beers = self.repository.list_beers(limit=400)

        want_similar = "similar" in query.lower()
        want_different = "different" in query.lower() or "other" in query.lower()

        target_style = ""
        if query and (want_similar or want_different):
            probe = query.replace("similar", "").replace("different", "").strip()
            target = self.repository.find_beer_exact_or_like(probe)
            if target:
                target_style = (target.get("style") or "").lower()

        scored = []
        for beer in all_beers:
            beer_name = (beer.get("name") or "").lower()
            style = (beer.get("style") or "").lower()
            if int(beer.get("id", 0)) in drank_ids:
                continue
            if beer_name in {x.lower() for x in profile.get("avoid_list", [])}:
                continue
            abv = beer.get("abv")
            if abv is not None and float(abv) > float(profile.get("max_abv", 99.0)):
                continue

            score = random.random()
            if profile.get("style_preferences"):
                if any(pref.lower() in style for pref in profile["style_preferences"]):
                    score += 2.0
            if profile.get("current_location"):
                zone = (beer.get("zone") or "").lower()
                if profile["current_location"].lower() in zone:
                    score += 1.2
            if target_style:
                if want_similar and target_style and target_style in style:
                    score += 2.5
                if want_different and target_style and target_style not in style:
                    score += 2.5

            scored.append((score, beer))

        if not scored:
            return None
        if random_mode:
            return random.choice([b for _, b in scored])
        return max(scored, key=lambda x: x[0])[1]

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

    def next_event(self) -> dict | None:
        now_iso = datetime.now(WARSAW_TZ).isoformat()
        events = self.repository.upcoming_events(now_iso, limit=1)
        return events[0] if events else None

    def events_today(self) -> list[dict]:
        today = datetime.now(WARSAW_TZ).date().isoformat()
        return self.repository.events_for_day(today)

    def beer_and_event(self, chat_id: int, query: str = "") -> tuple[dict | None, dict | None]:
        return self.recommend_beer(chat_id, query=query), self.next_event()

    def find_beers(self, name: str) -> list[dict]:
        return self.repository.list_beers(query=name, limit=10)

    def find_breweries(self, name: str) -> list[dict]:
        return self.repository.list_breweries(query=name, limit=10)


def format_beer(beer: dict) -> str:
    if not beer:
        return "No beer found."
    return (
        f"🍺 {beer.get('name', 'Unknown')}\n"
        f"Brewery: {beer.get('brewery') or 'n/a'}\n"
        f"Style: {beer.get('style') or 'n/a'}\n"
        f"ABV: {beer.get('abv') if beer.get('abv') is not None else 'n/a'}\n"
        f"Zone: {beer.get('zone') or 'n/a'} Stand: {beer.get('stand') or 'n/a'}"
    )


def format_event(event: dict) -> str:
    if not event:
        return "No upcoming events found in structured data."
    return (
        f"🎤 {event.get('title', 'Event')}\n"
        f"Start: {event.get('start_ts') or 'n/a'}\n"
        f"End: {event.get('end_ts') or 'n/a'}\n"
        f"Location: {event.get('location') or 'n/a'}"
    )
