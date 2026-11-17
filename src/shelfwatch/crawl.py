"""Crawl a competitor catalogue and say how complete the crawl was."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .parse import BOOKS, Site, parse_list, parse_price, parse_product
from .sources import PageSource


@dataclass
class Row:
    product_id: str
    title: str
    url: str
    category: str
    currency: str | None
    price: float | None
    in_stock: bool | None


@dataclass
class Crawl:
    rows: list[Row] = field(default_factory=list)
    pages_ok: int = 0
    pages_failed: list[str] = field(default_factory=list)
    pages_blocked: list[str] = field(default_factory=list)
    pages_empty: list[str] = field(default_factory=list)
    total_claimed: int | None = None
    unparsed_prices: int = 0
    product_pages_fetched: int = 0
    stopped_early: bool = False

    @property
    def problems(self) -> list[str]:
        p = []
        if self.pages_failed:
            p.append(f"{len(self.pages_failed)} pages failed to load")
        if self.pages_blocked:
            p.append(f"{len(self.pages_blocked)} pages served a bot-check instead of products")
        if self.pages_empty:
            p.append(f"{len(self.pages_empty)} pages had no products the parser recognised")
        if self.stopped_early:
            p.append("stopped at the page limit (trial run)")
        if self.unparsed_prices:
            p.append(f"{self.unparsed_prices} prices could not be read")
        return p


def crawl(
    source: PageSource,
    cache: dict[str, dict],
    site: Site = BOOKS,
    max_pages: int = 500,
    expected_pages: int | None = None,
) -> Crawl:
    """`cache` maps product URL -> {product_id, category}; product pages are fetched only for new URLs.

    Pages are numbered on this site, so one failed page does not end the crawl: the page count
    comes from the catalogue total on page 1, and the crawl carries on past a failure.
    """
    c = Crawl()
    pattern = site.extra.get("page_pattern", "catalogue/page-{n}.html")
    per_page = site.extra.get("per_page", 20)
    n, last_page = 1, expected_pages  # from the last good run, in case page 1 itself fails
    url = site.base + site.start
    while url and n <= max_pages:
        status, html = source.get(url)
        page = parse_list(html, site, url) if status == 200 else None
        if page is None:
            c.pages_failed.append(url)
        elif page.looks_blocked:
            c.pages_blocked.append(url)
        elif not page.listings:
            c.pages_empty.append(url)
        else:
            c.pages_ok += 1
            if page.total and c.total_claimed is None and n == 1:
                c.total_claimed = page.total
                last_page = math.ceil(page.total / per_page)
            for li in page.listings:
                info = cache.get(li.url)
                if info is None or not info.get("product_id"):
                    s2, h2 = source.get(li.url)
                    c.product_pages_fetched += 1
                    info = parse_product(h2, site) if s2 == 200 else {"product_id": None, "category": "unknown"}
                    if info.get("product_id"):
                        cache[li.url] = info
                if not info.get("product_id"):
                    continue
                cur, amount = parse_price(li.price_text, None)
                if amount is None:
                    c.unparsed_prices += 1
                c.rows.append(
                    Row(
                        info["product_id"],
                        li.title,
                        li.url,
                        info.get("category", "unknown"),
                        cur,
                        amount,
                        li.in_stock,
                    )
                )
        n += 1
        if last_page is not None:
            url = site.base + pattern.format(n=n) if n <= last_page else None
        elif page is not None and page.next_url:
            url = page.next_url
        else:
            url = None
    c.stopped_early = bool(url) and n > max_pages
    # the same product can appear twice if a page shifts while crawling; keep the first
    seen, rows = set(), []
    for r in c.rows:
        if r.product_id not in seen:
            seen.add(r.product_id)
            rows.append(r)
    c.rows = rows
    return c
