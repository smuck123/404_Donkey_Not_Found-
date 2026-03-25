import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "warsaw_beer_festival.db")


class WBFRepository:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_user_tables()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_user_tables(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
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

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    def _normalize_whitespace(self, value: str | None) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip()

    def _looks_like_bad_brewery_name(self, value: str | None) -> bool:
        text = self._normalize_whitespace(value).lower()
        if not text:
            return True

        if len(text) > 80:
            return True

        bad_exact = {
            "more info ▸",
            "no items found",
        }
        if text in bad_exact:
            return True

        if text.startswith("displaying all "):
            return True

        if re.match(r"^(100|150|200|300|330|375|473|500|750)ml\b", text):
            return True
        if text.startswith("0.5l "):
            return True

        bad_markers = [
            " ipa",
            " stout",
            " porter",
            " sour",
            " lager",
            " pils",
            " pilsner",
            " gose",
            " hefeweizen",
            " smoothie",
            " draft",
            " bottle",
            " can",
            " zł",
            " pln",
            "%",
        ]
        if any(marker in text for marker in bad_markers):
            return True

        return False

    def _sanitize_brewery_name(self, brewery_name: str | None, location: str | None = None) -> str:
        name = self._normalize_whitespace(brewery_name)
        location_text = self._normalize_whitespace(location)

        if self._looks_like_bad_brewery_name(name):
            if location_text:
                left = re.split(r"\s{2,}|,", location_text, maxsplit=1)[0].strip()
                if left:
                    return left
            return "Unknown Brewery"

        return name

    def _row_to_beer_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["brewery"] = self._sanitize_brewery_name(
            data.get("brewery"),
            data.get("brewery_location"),
        )
        data.pop("brewery_location", None)
        return data

    def counts(self) -> dict[str, int]:
        with self._conn() as conn:
            beers = conn.execute("SELECT COUNT(*) AS c FROM beers").fetchone()["c"]
            breweries = conn.execute("SELECT COUNT(*) AS c FROM breweries").fetchone()["c"]
            serving_options = conn.execute("SELECT COUNT(*) AS c FROM serving_options").fetchone()["c"]

        return {
            "beers": beers,
            "events": 1,
            "exhibitors": breweries,
            "breweries": breweries,
            "serving_options": serving_options,
        }

    def _beer_select_sql(self, conn: sqlite3.Connection) -> str:
        beer_cols = self._table_columns(conn, "beers")
        brewery_cols = self._table_columns(conn, "breweries")
        serving_cols = self._table_columns(conn, "serving_options")

        select_parts = [
            "b.id",
            "b.name",
            "br.name AS brewery",
            "br.location AS brewery_location" if "location" in brewery_cols else "'' AS brewery_location",
            "b.style" if "style" in beer_cols else "'' AS style",
            "b.abv" if "abv" in beer_cols else "NULL AS abv",
            "b.description" if "description" in beer_cols else "'' AS description",
            (
                "MIN(CASE WHEN s.price_pln IS NOT NULL THEN s.price_pln END) AS cheapest_price_pln"
                if "price_pln" in serving_cols else
                "NULL AS cheapest_price_pln"
            ),
            (
                "MIN(CASE WHEN s.price_eur IS NOT NULL THEN s.price_eur END) AS cheapest_price_eur"
                if "price_eur" in serving_cols else
                "NULL AS cheapest_price_eur"
            ),
            (
                "GROUP_CONCAT(DISTINCT s.size) AS sizes"
                if "size" in serving_cols else
                "'' AS sizes"
            ),
            (
                "GROUP_CONCAT(DISTINCT s.package) AS packages"
                if "package" in serving_cols else
                "'' AS packages"
            ),
            (
                "GROUP_CONCAT(DISTINCT s.raw_text) AS serving_raw"
                if "raw_text" in serving_cols else
                "'' AS serving_raw"
            ),
        ]

        return f"""
        SELECT
            {", ".join(select_parts)}
        FROM beers b
        JOIN breweries br ON b.brewery_id = br.id
        LEFT JOIN serving_options s ON s.beer_id = b.id
        """

    def list_beers(
        self,
        query: str = "",
        style: str | list[str] | None = None,
        brewery: str | None = None,
        max_abv: float | None = None,
        min_abv: float | None = None,
        max_price_pln: float | None = None,
        package: str | None = None,
        size: str | None = None,
        sort_by: str = "name",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            beer_cols = self._table_columns(conn, "beers")
            serving_cols = self._table_columns(conn, "serving_options")

            where = []
            params: list[Any] = []

            if query.strip():
                q = f"%{query.strip().lower()}%"
                query_parts = [
                    "lower(b.name) LIKE ?",
                    "lower(br.name) LIKE ?",
                ]
                params.extend([q, q])

                if "style" in beer_cols:
                    query_parts.append("lower(COALESCE(b.style, '')) LIKE ?")
                    params.append(q)

                if "description" in beer_cols:
                    query_parts.append("lower(COALESCE(b.description, '')) LIKE ?")
                    params.append(q)

                where.append("(" + " OR ".join(query_parts) + ")")

            if style and "style" in beer_cols:
                if isinstance(style, (list, tuple)):
                    style_terms = [str(x).strip().lower() for x in style if str(x).strip()]
                    if style_terms:
                        where.append(
                            "(" + " OR ".join(
                                ["lower(COALESCE(b.style, '')) LIKE ?" for _ in style_terms]
                            ) + ")"
                        )
                        params.extend([f"%{term}%" for term in style_terms])
                else:
                    where.append("lower(COALESCE(b.style, '')) LIKE ?")
                    params.append(f"%{str(style).strip().lower()}%")

            if brewery:
                where.append("lower(br.name) LIKE ?")
                params.append(f"%{brewery.strip().lower()}%")

            if min_abv is not None and "abv" in beer_cols:
                where.append("b.abv IS NOT NULL AND b.abv >= ?")
                params.append(min_abv)

            if max_abv is not None and "abv" in beer_cols:
                where.append("b.abv IS NOT NULL AND b.abv <= ?")
                params.append(max_abv)

            if max_price_pln is not None and "price_pln" in serving_cols:
                where.append(
                    """
                    EXISTS (
                        SELECT 1
                        FROM serving_options sx
                        WHERE sx.beer_id = b.id
                          AND sx.price_pln IS NOT NULL
                          AND sx.price_pln <= ?
                    )
                    """
                )
                params.append(max_price_pln)

            if package and "package" in serving_cols:
                where.append(
                    """
                    EXISTS (
                        SELECT 1
                        FROM serving_options sp
                        WHERE sp.beer_id = b.id
                          AND lower(COALESCE(sp.package, '')) LIKE ?
                    )
                    """
                )
                params.append(f"%{package.strip().lower()}%")

            if size and "size" in serving_cols:
                where.append(
                    """
                    EXISTS (
                        SELECT 1
                        FROM serving_options ss
                        WHERE ss.beer_id = b.id
                          AND lower(COALESCE(ss.size, '')) LIKE ?
                    )
                    """
                )
                params.append(f"%{size.strip().lower()}%")

            sql = self._beer_select_sql(conn)

            if where:
                sql += " WHERE " + " AND ".join(where)

            sql += " GROUP BY b.id, br.id "

            if sort_by == "cheap" and "price_pln" in serving_cols:
                sql += """
                ORDER BY
                    CASE WHEN cheapest_price_pln IS NULL THEN 1 ELSE 0 END,
                    cheapest_price_pln ASC,
                    CASE WHEN b.abv IS NULL THEN 1 ELSE 0 END,
                    b.abv ASC,
                    b.name ASC
                """
            elif sort_by == "strong" and "abv" in beer_cols:
                sql += """
                ORDER BY
                    CASE WHEN b.abv IS NULL THEN 1 ELSE 0 END,
                    b.abv DESC,
                    b.name ASC
                """
            else:
                sql += " ORDER BY b.name ASC "

            sql += " LIMIT ? "
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_beer_dict(r) for r in rows]

    def cheapest_beers(
        self,
        limit: int = 20,
        style: str | list[str] | None = None,
        max_abv: float | None = None,
        max_price_pln: float | None = None,
        package: str | None = None,
        size: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_beers(
            style=style,
            max_abv=max_abv,
            max_price_pln=max_price_pln,
            package=package,
            size=size,
            sort_by="cheap",
            limit=limit,
        )

    def get_serving_options(self, beer_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, beer_id, size, package, price_pln, price_eur, raw_text
                FROM serving_options
                WHERE beer_id = ?
                ORDER BY
                    CASE WHEN price_pln IS NULL THEN 1 ELSE 0 END,
                    price_pln ASC,
                    size ASC
                """,
                (beer_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_beer_exact_or_like(self, name: str) -> dict[str, Any] | None:
        if not name.strip():
            return None

        rows = self.list_beers(query=name, limit=20)
        if not rows:
            return None

        exact = [r for r in rows if (r.get("name") or "").strip().lower() == name.strip().lower()]
        if exact:
            return exact[0]

        rows.sort(key=lambda r: len(r.get("name") or ""))
        return rows[0]

    def list_breweries(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        sql = """
        SELECT
            br.id,
            br.name,
            COUNT(DISTINCT b.id) AS beers,
            MIN(CASE WHEN s.price_pln IS NOT NULL AND s.price_pln > 0 THEN s.price_pln END) AS cheapest_beer_pln
        FROM breweries br
        LEFT JOIN beers b ON b.brewery_id = br.id
        LEFT JOIN serving_options s ON s.beer_id = b.id
        """
        params: list[Any] = []

        if query.strip():
            sql += " WHERE lower(br.name) LIKE ? "
            q = f"%{query.strip().lower()}%"
            params.append(q)

        sql += """
        GROUP BY br.id
        ORDER BY br.name ASC
        LIMIT ?
        """
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        out = []
        for row in rows:
            data = dict(row)
            data["name"] = self._sanitize_brewery_name(data.get("name"))
            out.append(data)
        return out

    def beer_shop_map_links(self, brewery_name: str) -> dict[str, str]:
        q = brewery_name.strip()
        if not q:
            return {}

        from urllib.parse import quote_plus

        return {
            "google_maps": f"https://www.google.com/maps/search/{quote_plus(q)}",
            "openstreetmap": f"https://www.openstreetmap.org/search?query={quote_plus(q)}",
        }

    def get_user_profile(self, chat_id: int) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE chat_id=?",
                (chat_id,),
            ).fetchone()

            if not row:
                conn.execute("INSERT INTO user_profiles(chat_id) VALUES(?)", (chat_id,))
                row = conn.execute(
                    "SELECT * FROM user_profiles WHERE chat_id=?",
                    (chat_id,),
                ).fetchone()

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
                ON CONFLICT(chat_id, beer_id) DO UPDATE SET
                    drank_at=excluded.drank_at,
                    rating=excluded.rating
                """,
                (chat_id, beer_id, datetime.utcnow().isoformat(), rating),
            )

    def history(self, chat_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    d.drank_at,
                    d.rating,
                    b.id,
                    b.name,
                    br.name AS brewery,
                    b.style,
                    b.abv
                FROM drank_beers d
                JOIN beers b ON b.id = d.beer_id
                JOIN breweries br ON br.id = b.brewery_id
                WHERE d.chat_id=?
                ORDER BY d.drank_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()

        out = []
        for row in rows:
            data = dict(row)
            data["brewery"] = self._sanitize_brewery_name(data.get("brewery"))
            out.append(data)
        return out

    def drank_beer_ids(self, chat_id: int) -> set[int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT beer_id FROM drank_beers WHERE chat_id=?",
                (chat_id,),
            ).fetchall()

        return {int(r["beer_id"]) for r in rows}
