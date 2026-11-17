"""Turn catalogue HTML into listings, and price text into (currency, amount).

A site adapter is a set of CSS selectors with fallbacks, so a renamed class on the
competitor's site does not silently turn into zero prices.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD", "₹": "INR", "Rs": "INR"}
CODES = ("GBP", "EUR", "USD", "INR")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Site:
    """Selectors for one competitor site. Each field lists alternatives, tried in order."""

    name: str
    base: str
    start: str
    home_currency: str
    item: tuple[str, ...]
    title: tuple[str, ...]
    price: tuple[str, ...]
    availability: tuple[str, ...]
    next_page: tuple[str, ...]
    total: tuple[str, ...] = ()
    product_id: tuple[str, ...] = ()  # on the product page, e.g. UPC / ISBN / SKU
    category: tuple[str, ...] = ()
    product_id_label: str = "UPC"
    extra: dict = field(default_factory=dict)


BOOKS = Site(
    name="books.toscrape.com",
    base="https://books.toscrape.com/",
    start="catalogue/page-1.html",
    home_currency="GBP",
    item=("article.product_pod", "li.product", "[itemtype*='Product']"),
    title=("h3 a[title]", "h3 a", "[itemprop=name]"),
    price=("p.price_color", ".price", "[itemprop=price]"),
    availability=("p.availability", ".availability", ".stock"),
    next_page=("li.next a", "a[rel=next]"),
    total=("form.form-horizontal strong",),
    product_id=("table.table-striped tr",),
    category=("ul.breadcrumb li a",),
)


def _first(node, selectors):
    for s in selectors:
        hit = node.select_one(s)
        if hit is not None:
            return hit
    return None


def parse_price(text: str | None, default_currency: str | None = None) -> tuple[str | None, float | None]:
    """'£51.77' -> ('GBP', 51.77). 'Was £12.99 Now £9.99' -> ('GBP', 9.99). '€1,299.00' -> ('EUR', 1299.0).

    Returns (currency, None) when no amount can be read, never a made-up number.
    """
    if not text:
        return default_currency, None
    t = text.replace("\xa0", " ").replace("Â", "")
    cur = None
    for code in CODES:
        if code in t:
            cur = code
            break
    if cur is None:
        for sym, code in SYMBOLS.items():
            if sym in t:
                cur = code
                break
    nums = NUMBER.findall(t)
    if not nums:
        return cur or default_currency, None
    amount = float(nums[-1].replace(",", ""))  # sale prices list the old price first, the current one last
    return cur or default_currency, amount


@dataclass
class Listing:
    title: str
    url: str
    price_text: str | None
    in_stock: bool | None


@dataclass
class ListPage:
    listings: list[Listing]
    next_url: str | None
    total: int | None
    looks_blocked: bool


BLOCK_WORDS = ("captcha", "access denied", "are you a robot", "unusual traffic")


def parse_list(html: str, site: Site = BOOKS, url: str = "") -> ListPage:
    soup = BeautifulSoup(html, "lxml")
    items = []
    for sel in site.item:
        items = soup.select(sel)
        if items:
            break
    out = []
    for it in items:
        a = _first(it, site.title)
        if a is None:
            continue
        title = (a.get("title") or a.get_text()).strip()
        href = a.get("href") or ""
        p = _first(it, site.price)
        av = _first(it, site.availability)
        avail = av.get_text(" ", strip=True).lower() if av is not None else None
        in_stock = None if avail is None else ("in stock" in avail and "out of stock" not in avail)
        out.append(Listing(title, _join(site, url, href), p.get_text(" ", strip=True) if p else None, in_stock))
    nxt = _first(soup, site.next_page)
    total = None
    t = _first(soup, site.total) if site.total else None
    if t is not None and t.get_text(strip=True).isdigit():
        total = int(t.get_text(strip=True))
    text = soup.get_text(" ", strip=True).lower()[:2000]
    blocked = not out and any(w in text for w in BLOCK_WORDS)
    return ListPage(out, _join(site, url, nxt.get("href")) if nxt is not None else None, total, blocked)


def parse_product(html: str, site: Site = BOOKS) -> dict:
    soup = BeautifulSoup(html, "lxml")
    pid = None
    for row in soup.select(site.product_id[0]) if site.product_id else []:
        th, td = row.find("th"), row.find("td")
        if th is not None and td is not None and th.get_text(strip=True) == site.product_id_label:
            pid = td.get_text(strip=True)
    crumbs = soup.select(site.category[0]) if site.category else []
    category = crumbs[2].get_text(strip=True).lower() if len(crumbs) >= 3 else "unknown"
    return {"product_id": pid, "category": category}


def _join(site: Site, page_url: str, href: str) -> str:
    if href.startswith("http"):
        return href
    if not page_url:
        page_url = site.base + site.start
    base = page_url.rsplit("/", 1)[0] + "/"
    parts = (base + href).split("/")
    stack: list[str] = []
    for p in parts:
        if p == "..":
            if stack:
                stack.pop()
        elif p != ".":
            stack.append(p)
    return "/".join(stack)
