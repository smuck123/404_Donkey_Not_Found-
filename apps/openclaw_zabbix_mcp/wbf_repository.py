import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "warsaw_beer_festival.db")


class WBFRepository:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS beers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    brewery TEXT,
                    style TEXT,
                    abv REAL,
                    zone TEXT,
                    stand TEXT,
                    source_url TEXT,
                    raw_json TEXT,
                    UNIQUE(name, brewery)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_ts TEXT,
                    end_ts TEXT,
                    location TEXT,
                    description TEXT,
                    source_url TEXT,
                    raw_json TEXT,
                    UNIQUE(title, start_ts)
                );

                CREATE TABLE IF NOT EXISTS exhibitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    zone TEXT,
                    stand TEXT,
                    floor TEXT,
                    source_url TEXT,
                    raw_json TEXT,
                    UNIQUE(name, stand)
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    chat_id INTEGER PRIMARY KEY,
                    max_abv REAL DEFAULT 99.0,
                    style_preferences TEXT DEFAULT '[]',
                    avoid_list TEXT DEFAULT '[]',
                    current_location TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS drank_beers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    beer_id INTEGER NOT NULL,
                    drank_at TEXT NOT NULL,
                    rating INTEGER,
                    UNIQUE(chat_id, beer_id)
                );
                """
            )

    def upsert_beers(self, beers: list[dict[str, Any]]) -> int:
        if not beers:
            return 0
        inserted = 0
        with self._conn() as conn:
            for beer in beers:
                conn.execute(
                    """
                    INSERT INTO beers(name, brewery, style, abv, zone, stand, source_url, raw_json)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name, brewery) DO UPDATE SET
                      style=excluded.style,
                      abv=excluded.abv,
                      zone=excluded.zone,
                      stand=excluded.stand,
                      source_url=excluded.source_url,
                      raw_json=excluded.raw_json
                    """,
                    (
                        beer.get("name", "").strip(),
                        beer.get("brewery", "").strip(),
                        beer.get("style", "").strip(),
                        beer.get("abv"),
                        beer.get("zone", "").strip(),
                        beer.get("stand", "").strip(),
                        beer.get("source_url", "").strip(),
                        json.dumps(beer, ensure_ascii=False),
                    ),
                )
                inserted += 1
        return inserted

    def upsert_events(self, events: list[dict[str, Any]]) -> int:
        if not events:
            return 0
        inserted = 0
        with self._conn() as conn:
            for event in events:
                conn.execute(
                    """
                    INSERT INTO events(title, start_ts, end_ts, location, description, source_url, raw_json)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(title, start_ts) DO UPDATE SET
                      end_ts=excluded.end_ts,
                      location=excluded.location,
                      description=excluded.description,
                      source_url=excluded.source_url,
                      raw_json=excluded.raw_json
                    """,
                    (
                        event.get("title", "").strip(),
                        event.get("start_ts"),
                        event.get("end_ts"),
                        event.get("location", "").strip(),
                        event.get("description", "").strip(),
                        event.get("source_url", "").strip(),
                        json.dumps(event, ensure_ascii=False),
                    ),
                )
                inserted += 1
        return inserted

    def upsert_exhibitors(self, exhibitors: list[dict[str, Any]]) -> int:
        if not exhibitors:
            return 0
        inserted = 0
        with self._conn() as conn:
            for exhibitor in exhibitors:
                conn.execute(
                    """
                    INSERT INTO exhibitors(name, zone, stand, floor, source_url, raw_json)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name, stand) DO UPDATE SET
                      zone=excluded.zone,
                      floor=excluded.floor,
                      source_url=excluded.source_url,
                      raw_json=excluded.raw_json
                    """,
                    (
                        exhibitor.get("name", "").strip(),
                        exhibitor.get("zone", "").strip(),
                        exhibitor.get("stand", "").strip(),
                        exhibitor.get("floor", "").strip(),
                        exhibitor.get("source_url", "").strip(),
                        json.dumps(exhibitor, ensure_ascii=False),
                    ),
                )
                inserted += 1
        return inserted

    def counts(self) -> dict[str, int]:
        with self._conn() as conn:
            beers = conn.execute("SELECT COUNT(*) AS c FROM beers").fetchone()["c"]
            events = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
            exhibitors = conn.execute("SELECT COUNT(*) AS c FROM exhibitors").fetchone()["c"]
        return {"beers": beers, "events": events, "exhibitors": exhibitors}

    def list_beers(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        q = f"%{query.strip().lower()}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM beers
                WHERE lower(name) LIKE ? OR lower(brewery) LIKE ? OR lower(style) LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (q, q, q, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_beer_exact_or_like(self, name: str) -> dict[str, Any] | None:
        if not name.strip():
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM beers WHERE lower(name)=lower(?) LIMIT 1", (name.strip(),)
            ).fetchone()
            if row:
                return dict(row)
            row = conn.execute(
                "SELECT * FROM beers WHERE lower(name) LIKE lower(?) ORDER BY length(name) ASC LIMIT 1",
                (f"%{name.strip()}%",),
            ).fetchone()
        return dict(row) if row else None

    def list_breweries(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        q = f"%{query.strip().lower()}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT brewery AS name, MIN(zone) AS zone, MIN(stand) AS stand, COUNT(*) AS beers
                FROM beers
                WHERE brewery IS NOT NULL AND brewery <> ''
                  AND lower(brewery) LIKE ?
                GROUP BY brewery
                ORDER BY brewery
                LIMIT ?
                """,
                (q, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_user_profile(self, chat_id: int) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE chat_id=?", (chat_id,)).fetchone()
            if not row:
                conn.execute("INSERT INTO user_profiles(chat_id) VALUES(?)", (chat_id,))
                row = conn.execute("SELECT * FROM user_profiles WHERE chat_id=?", (chat_id,)).fetchone()
        data = dict(row)
        data["style_preferences"] = json.loads(data.get("style_preferences") or "[]")
        data["avoid_list"] = json.loads(data.get("avoid_list") or "[]")
        return data

    def update_user_profile(self, chat_id: int, **updates) -> dict[str, Any]:
        current = self.get_user_profile(chat_id)
        merged = {**current, **updates}
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE user_profiles
                SET max_abv=?, style_preferences=?, avoid_list=?, current_location=?
                WHERE chat_id=?
                """,
                (
                    merged.get("max_abv", 99.0),
                    json.dumps(merged.get("style_preferences", []), ensure_ascii=False),
                    json.dumps(merged.get("avoid_list", []), ensure_ascii=False),
                    merged.get("current_location", ""),
                    chat_id,
                ),
            )
        return self.get_user_profile(chat_id)

    def mark_drank(self, chat_id: int, beer_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO drank_beers(chat_id, beer_id, drank_at)
                VALUES(?, ?, ?)
                ON CONFLICT(chat_id, beer_id) DO UPDATE SET drank_at=excluded.drank_at
                """,
                (chat_id, beer_id, datetime.utcnow().isoformat()),
            )

    def set_rating(self, chat_id: int, beer_id: int, rating: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO drank_beers(chat_id, beer_id, drank_at, rating)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(chat_id, beer_id) DO UPDATE SET rating=excluded.rating
                """,
                (chat_id, beer_id, datetime.utcnow().isoformat(), rating),
            )

    def history(self, chat_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT d.drank_at, d.rating, b.*
                FROM drank_beers d
                JOIN beers b ON b.id = d.beer_id
                WHERE d.chat_id=?
                ORDER BY d.drank_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def drank_beer_ids(self, chat_id: int) -> set[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT beer_id FROM drank_beers WHERE chat_id=?", (chat_id,)).fetchall()
        return {int(r["beer_id"]) for r in rows}

    def upcoming_events(self, now_iso: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE start_ts IS NOT NULL AND start_ts >= ?
                ORDER BY start_ts ASC
                LIMIT ?
                """,
                (now_iso, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def events_for_day(self, day_prefix: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE start_ts LIKE ?
                ORDER BY start_ts ASC
                """,
                (f"{day_prefix}%",),
            ).fetchall()
        return [dict(r) for r in rows]
