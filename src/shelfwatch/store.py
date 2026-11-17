"""Storage on SQLite (local, tests) or PostgreSQL (production). Same SQL for both."""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlparse

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS runs (
        site TEXT, run_date TEXT, status TEXT, coverage REAL, items_seen INTEGER, expected INTEGER,
        fx TEXT, issues TEXT, PRIMARY KEY (site, run_date))""",
    """CREATE TABLE IF NOT EXISTS products (
        site TEXT, product_id TEXT, title TEXT, url TEXT, category TEXT, currency TEXT, price REAL,
        price_home REAL, price_inr REAL, in_stock INTEGER, status TEXT, first_seen TEXT, last_seen TEXT,
        last_checked TEXT, missing_runs INTEGER, PRIMARY KEY (site, product_id))""",
    """CREATE TABLE IF NOT EXISTS history (
        site TEXT, run_date TEXT, product_id TEXT, title TEXT, currency TEXT, price REAL, price_home REAL,
        price_inr REAL, in_stock INTEGER, PRIMARY KEY (site, run_date, product_id))""",
    """CREATE TABLE IF NOT EXISTS alerts (
        site TEXT, run_date TEXT, product_id TEXT, kind TEXT, old_value TEXT, new_value TEXT, detail TEXT)""",
    """CREATE TABLE IF NOT EXISTS fx (
        rate_date TEXT, currency TEXT, rate_inr REAL, status TEXT, PRIMARY KEY (rate_date, currency))""",
]

CURRENT_COLS = [
    "site",
    "product_id",
    "title",
    "url",
    "category",
    "currency",
    "price",
    "price_home",
    "price_inr",
    "in_stock",
    "status",
    "first_seen",
    "last_seen",
    "last_checked",
    "missing_runs",
]


class Store:
    def __init__(self, url: str = "sqlite:///shelfwatch.db"):
        u = urlparse(url)
        if u.scheme.startswith("postgres"):
            import psycopg2  # optional dependency

            self.conn = psycopg2.connect(url)
            self.ph = "%s"
        else:
            path = url.split("sqlite:///", 1)[-1] if url.startswith("sqlite") else url
            self.conn = sqlite3.connect(path or ":memory:")
            self.ph = "?"
        cur = self.conn.cursor()
        for s in SCHEMA:
            cur.execute(s)
        self.conn.commit()

    def _q(self, sql: str) -> str:
        return sql.replace("?", self.ph)

    def execute(self, sql: str, params=()):
        cur = self.conn.cursor()
        cur.execute(self._q(sql), params)
        return cur

    def many(self, sql: str, rows):
        cur = self.conn.cursor()
        cur.executemany(self._q(sql), rows)

    def query(self, sql: str, params=()) -> list[dict]:
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    def commit(self):
        self.conn.commit()

    # ---- domain helpers
    def current(self, site: str) -> dict[str, dict]:
        return {r["product_id"]: r for r in self.query("SELECT * FROM products WHERE site = ?", (site,))}

    def save_current(self, rows: list[dict]):
        cols = ", ".join(CURRENT_COLS)
        marks = ", ".join("?" * len(CURRENT_COLS))
        upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in CURRENT_COLS[2:])
        self.many(
            f"INSERT INTO products ({cols}) VALUES ({marks}) "
            f"ON CONFLICT (site, product_id) DO UPDATE SET {upd}",
            [tuple(r[c] for c in CURRENT_COLS) for r in rows],
        )

    def last_rate(self, currency: str, before: str) -> float | None:
        r = self.query(
            "SELECT rate_inr FROM fx WHERE currency = ? AND rate_date < ? AND status != 'rejected' "
            "ORDER BY rate_date DESC LIMIT 1",
            (currency, before),
        )
        return r[0]["rate_inr"] if r else None

    def save_rate(self, day: str, currency: str, rate: float, status: str):
        self.execute(
            "INSERT INTO fx VALUES (?, ?, ?, ?) ON CONFLICT (rate_date, currency) DO UPDATE SET "
            "rate_inr = EXCLUDED.rate_inr, status = EXCLUDED.status",
            (day, currency, rate, status),
        )

    def last_good_run(self, site: str) -> dict | None:
        r = self.query(
            "SELECT * FROM runs WHERE site = ? AND status = 'complete' ORDER BY run_date DESC LIMIT 1", (site,)
        )
        return r[0] if r else None

    def save_run(
        self,
        site: str,
        day: str,
        status: str,
        coverage: float,
        seen: int,
        expected: int,
        fx: dict,
        issues: list[str],
    ):
        self.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (site, run_date) DO UPDATE SET "
            "status = EXCLUDED.status, coverage = EXCLUDED.coverage, items_seen = EXCLUDED.items_seen, "
            "expected = EXCLUDED.expected, fx = EXCLUDED.fx, issues = EXCLUDED.issues",
            (site, day, status, coverage, seen, expected, json.dumps(fx), json.dumps(issues)),
        )
