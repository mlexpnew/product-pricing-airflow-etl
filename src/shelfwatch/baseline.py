"""The original pipeline's logic, kept as the baseline to beat.

Follow "next" links with raise_for_status (a failed page fails the run), read price_color and strip
everything that is not a digit or a dot, assume pounds, convert with whatever the rate API returns,
key products by a hash of the title, upsert, and call anything missing since the last run delisted.
One kindness over the original: a price that cannot be read skips that product instead of crashing
the whole run.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from bs4 import BeautifulSoup

from .parse import BOOKS


class NaivePipeline:
    def __init__(self):
        self.warehouse: dict[str, dict] = {}  # id -> {title, price_gbp, price_inr, in_stock}
        self.last_ids: set[str] | None = None

    def run(self, source, rates, day: date) -> list[dict]:
        try:
            rate = rates.rate("GBP", day)
            products = []
            url = BOOKS.base + BOOKS.start
            while url:
                status, html = source.get(url)
                if status != 200:
                    raise RuntimeError(f"HTTP {status} for {url}")
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("article.product_pod"):
                    title = a.h3.a["title"].strip()
                    try:
                        price = float(re.sub(r"[^\d.]", "", a.select_one("p.price_color").text))
                    except (AttributeError, ValueError):
                        continue
                    avail = a.select_one(".availability")
                    in_stock = (
                        avail is not None
                        and "in stock" in avail.text.lower()
                        and "out of" not in avail.text.lower()
                    )
                    products.append((title, price, in_stock))
                nxt = soup.select_one("li.next a")
                url = BOOKS.base + "catalogue/" + nxt["href"] if nxt else None
        except Exception:  # noqa: BLE001 - the task fails; Airflow retries, then the day is lost
            return []
        alerts, ids = [], set()
        for title, price, in_stock in products:
            pid = hashlib.md5(title.encode()).hexdigest()
            ids.add(pid)
            old = self.warehouse.get(pid)
            if self.last_ids is not None:
                if old is None:
                    alerts.append({"title": title, "kind": "new"})
                else:
                    if abs(price / old["price_gbp"] - 1) >= 0.01:
                        alerts.append({"title": title, "kind": "price_change"})
                    if old["in_stock"] and not in_stock:
                        alerts.append({"title": title, "kind": "stock_out"})
                    if not old["in_stock"] and in_stock:
                        alerts.append({"title": title, "kind": "back_in_stock"})
            self.warehouse[pid] = {
                "title": title,
                "price_gbp": price,
                "price_inr": price * rate,
                "in_stock": in_stock,
            }
        if self.last_ids is not None:
            for pid in self.last_ids - ids:
                alerts.append({"title": self.warehouse[pid]["title"], "kind": "delisted"})
        self.last_ids = ids
        return alerts
