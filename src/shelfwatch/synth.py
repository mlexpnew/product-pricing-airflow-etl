"""A simulated competitor catalogue in the books.toscrape.com layout, with known truth.

Each day the truth moves (price changes, sales, stock-outs, new and delisted products, title
fixes, exchange rates), and some days the crawl goes wrong the way real crawls do: pages time
out, a bot-check is served, prices show in another currency, a CSS class is renamed, or the
exchange-rate API returns nonsense. The truth never changes because of a fault.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

WORDS = (
    "light dark river city night garden secret house winter summer silent golden lost empire star sea "
    "stone fire last first little great hidden broken wild quiet north south paper glass iron song road "
    "heart time shadow island king queen year story world dream"
).split()
CATEGORIES = (
    "fiction mystery romance history travel poetry science business fantasy thriller classics "
    "biography philosophy music art childrens humor horror religion psychology"
).split()
PER_PAGE = 20
BASE = "https://books.toscrape.com/"


@dataclass
class Product:
    upc: str
    num: int
    title: str
    category: str
    price: float  # GBP
    in_stock: bool = True
    listed: bool = True
    was: float | None = None  # shown struck through while on sale

    @property
    def url(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")
        return f"{BASE}catalogue/{slug}_{self.num}/index.html"


@dataclass
class World:
    seed: int
    n: int = 1000
    start: date = date(2026, 1, 5)
    rng: random.Random = field(init=False)
    products: list[Product] = field(default_factory=list)
    gbp: float = 110.0
    eur_per_gbp: float = 1.17
    usd_per_gbp: float = 1.27
    day: int = 0

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        for _ in range(self.n):
            self._add(front=False)

    def _add(self, front: bool):
        r = self.rng
        num = len(self.products) + 1
        title = " ".join(r.choice(WORDS).capitalize() for _ in range(r.randint(3, 6)))
        upc = hashlib.md5(f"{self.seed}-{num}".encode()).hexdigest()[:16]
        p = Product(upc, num, title, r.choice(CATEGORIES), round(r.uniform(10, 60), 2), r.random() > 0.05)
        if front:
            self.products.insert(0, p)
        else:
            self.products.append(p)

    @property
    def today(self) -> date:
        return self.start + timedelta(days=self.day)

    def truth(self) -> dict[str, dict]:
        return {
            p.upc: {"title": p.title, "price": p.price, "in_stock": p.in_stock, "url": p.url}
            for p in self.products
            if p.listed
        }

    def step(self):
        r = self.rng
        self.day += 1
        self.gbp *= math.exp(r.gauss(0, 0.004))
        self.eur_per_gbp *= math.exp(r.gauss(0, 0.002))
        self.usd_per_gbp *= math.exp(r.gauss(0, 0.002))
        for p in self.products:
            if not p.listed:
                continue
            u = r.random()
            if u < 0.012:  # discount, often shown as a sale
                old = p.price
                p.price = round(old * r.uniform(0.70, 0.95), 2)
                p.was = old if r.random() < 0.5 else None
            elif u < 0.02:  # increase ends any sale
                p.price = round(p.price * r.uniform(1.05, 1.30), 2)
                p.was = None
            if p.in_stock and r.random() < 0.008:
                p.in_stock = False
            elif not p.in_stock and r.random() < 0.15:
                p.in_stock = True
            if r.random() < 0.0015:
                p.listed = False
            elif r.random() < 0.0008:  # a corrected title changes the product URL too
                p.title = p.title + " (Revised Edition)"
        for _ in range(sum(r.random() < 0.6 for _ in range(5))):
            self._add(front=True)

    def rate(self, currency: str) -> float:
        return {
            "INR": 1.0,
            "GBP": self.gbp,
            "EUR": self.gbp / self.eur_per_gbp,
            "USD": self.gbp / self.usd_per_gbp,
        }[currency]


SYM = {"GBP": "£", "EUR": "€", "USD": "$"}


def _money(amount: float, cur: str) -> str:
    return f"{SYM[cur]}{amount:,.2f}"


class SynthSite:
    """Serves the world's catalogue for one day, with that day's faults.

    faults: {"timeout": k, "block": k, "currency": "EUR", "layout": True, "layout_unknown": True,
             "stale_pages": k (served from an older snapshot)}
    """

    def __init__(self, world: World, faults: dict | None = None, older: list[Product] | None = None):
        self.w, self.f = world, faults or {}
        listed = [p for p in world.products if p.listed]
        self.listed = listed
        self.pages = max(1, math.ceil(len(listed) / PER_PAGE))
        rr = random.Random(world.seed * 1000 + world.day)
        pool = list(range(1, self.pages + 1))
        self.dead = set(rr.sample(pool, min(self.f.get("timeout", 0), len(pool))))
        rest = [x for x in pool if x not in self.dead]
        self.blocked = set(rr.sample(rest, min(self.f.get("block", 0), len(rest))))
        rest = [x for x in rest if x not in self.blocked]
        self.stale = set(rr.sample(rest, min(self.f.get("stale_pages", 0), len(rest)))) if older else set()
        self.older = older or []
        self.by_url = {p.url: p for p in world.products}
        self.calls = 0

    def get(self, url: str) -> tuple[int, str]:
        self.calls += 1
        m = re.search(r"catalogue/page-(\d+)\.html$", url)
        if m:
            n = int(m.group(1))
            if n in self.dead:
                return 503, "Service Unavailable"
            if n in self.blocked:
                return (
                    200,
                    "<html><body><h1>Access denied</h1><p>Please complete the captcha.</p></body></html>",
                )
            if n > self.pages:
                return 404, "Not found"
            src = self.older if n in self.stale else self.listed
            return 200, self._list_page(n, src[(n - 1) * PER_PAGE : n * PER_PAGE])
        p = self.by_url.get(url)
        if p is None:
            return 404, "Not found"
        return 200, self._product_page(p)

    def _list_page(self, n: int, items: list[Product]) -> str:
        cur = self.f.get("currency", "GBP")
        conv = 1.0 if cur == "GBP" else {"EUR": self.w.eur_per_gbp, "USD": self.w.usd_per_gbp}[cur]
        unknown = self.f.get("layout_unknown")
        price_cls = "price" if self.f.get("layout") else "price_color"
        arts = []
        for p in items:
            now = _money(p.price * conv, cur)
            shown = f"<del>{_money(p.was * conv, cur)}</del> {now}" if p.was else now
            stock = "In stock" if p.in_stock else "Out of stock"
            href = p.url.replace(BASE + "catalogue/", "")
            if unknown:
                arts.append(
                    f'<div class="product-card"><h2 class="name"><a href="{href}">{p.title}</a></h2>'
                    f'<span class="amount">{shown}</span><span class="avail">{stock}</span></div>'
                )
            else:
                arts.append(
                    f'<li class="col-xs-6"><article class="product_pod"><h3><a href="{href}" title="{p.title}">'
                    f'{p.title[:30]}</a></h3><div class="product_price"><p class="{price_cls}">{shown}</p>'
                    f'<p class="instock availability"><i class="icon-ok"></i> {stock}</p></div></article></li>'
                )
        nxt = f'<li class="next"><a href="page-{n + 1}.html">next</a></li>' if n < self.pages else ""
        return (
            f'<html><body><form class="form-horizontal"><strong>{len(self.listed)}</strong> results</form>'
            f'<ol class="row">{"".join(arts)}</ol><ul class="pager">{nxt}</ul></body></html>'
        )

    def _product_page(self, p: Product) -> str:
        return (
            f'<html><body><ul class="breadcrumb"><li><a href="../../index.html">Home</a></li>'
            f'<li><a href="#">Books</a></li><li><a href="#">{p.category.title()}</a></li>'
            f"<li>{p.title}</li></ul>"
            f'<h1>{p.title}</h1><table class="table table-striped"><tr><th>UPC</th><td>{p.upc}</td></tr>'
            f"<tr><th>Product Type</th><td>Books</td></tr></table></body></html>"
        )


class SynthRates:
    """Exchange rates from the world. glitch: "x100" (paise), "error", "jump" (10% off) or None."""

    def __init__(self, world: World, glitch: str | None = None):
        self.w, self.glitch = world, glitch

    def rate(self, currency: str, day: date) -> float:
        true = self.w.rate(currency)
        if self.glitch == "error":
            raise ConnectionError("rate API unavailable")
        if self.glitch == "x100":
            return true * 100
        if self.glitch == "jump":
            return true * 1.10
        return true
