"""One daily run: crawl, check the crawl and the exchange rates before trusting them, then record
only real changes.

Run status:
  complete     every page loaded and parsed; products not seen count towards delisting
  partial      some pages failed or were blocked; unseen products are marked stale, never delisted
  quarantined  the crawl is not believable (nothing parsed, or most prices moved by the same ratio);
               nothing is written except the run record, and yesterday's data stays
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from .crawl import Crawl, crawl
from .parse import BOOKS, Site
from .sources import PageSource, RateSource
from .store import Store

ALERT_KINDS = ("price_change", "stock_out", "back_in_stock", "new", "delisted")


@dataclass
class Settings:
    price_change: float = 0.01  # alert on moves of 1% or more
    complete_coverage: float = 0.97
    fx_band: float = 0.03  # a daily rate move above 3% needs a second source to agree
    fx_agree: float = 0.005
    mass_change_share: float = 0.30  # 30%+ of prices moving at once ...
    mass_change_spread: float = 0.02  # ... by nearly the same ratio = a currency or unit problem
    delist_after: int = 2  # missing from this many complete runs in a row


@dataclass
class RunResult:
    day: str
    status: str
    coverage: float
    seen: int
    expected: int
    alerts: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    fx: dict = field(default_factory=dict)


class Monitor:
    def __init__(
        self,
        store: Store,
        source: PageSource,
        rates: RateSource,
        backup_rates: RateSource | None = None,
        site: Site = BOOKS,
        settings: Settings | None = None,
        max_pages: int = 500,
    ):
        self.store, self.source, self.rates, self.backup = store, source, rates, backup_rates
        self.site, self.s, self.max_pages = site, settings or Settings(), max_pages

    # ---------- exchange rates
    def rate(self, currency: str, day: date) -> tuple[float, str]:
        if currency == "INR":
            return 1.0, "ok"
        d = day.isoformat()
        last = self.store.last_rate(currency, d)

        def get(src):
            try:
                v = src.rate(currency, day) if src else None
                return v if v and v > 0 and math.isfinite(v) else None
            except Exception:  # noqa: BLE001 - any source failure means "no answer"
                return None

        def near(a, b, tol):
            return a is not None and b is not None and abs(a / b - 1) <= tol

        p = get(self.rates)
        if p is not None and (last is None or near(p, last, self.s.fx_band)):
            rate, status = p, "ok"
        else:
            b = get(self.backup)
            if near(p, b, self.s.fx_agree):
                rate, status = p, "confirmed by second source"
            elif b is not None and (last is None or near(b, last, self.s.fx_band)):
                rate, status = b, "second source (first failed or looked wrong)"
            elif last is not None:
                rate, status = last, "stale: kept the last accepted rate"
            else:
                raise RuntimeError(f"no believable {currency}/INR rate for {d}")
        self.store.save_rate(d, currency, rate, status)
        return rate, status

    # ---------- the run
    def run(self, day: date, force: bool = False) -> RunResult:
        d = day.isoformat()
        site = self.site.name
        done = self.store.query("SELECT * FROM runs WHERE site = ? AND run_date = ?", (site, d))
        if done and not force:
            r = done[0]
            return RunResult(
                d, r["status"], r["coverage"], r["items_seen"], r["expected"], issues=["already ran"]
            )
        state = self.store.current(site)
        listed = [p for p in state.values() if p["status"] != "delisted"]
        cache = {p["url"]: {"product_id": p["product_id"], "category": p["category"]} for p in state.values()}
        per_page = self.site.extra.get("per_page", 20)
        c: Crawl = crawl(
            self.source,
            cache,
            self.site,
            max_pages=self.max_pages,
            expected_pages=math.ceil(len(listed) / per_page) if listed else None,
        )
        home = self.site.home_currency
        currencies = {r.currency or home for r in c.rows} | {home}
        fx, fx_status = {}, {}
        for cur in sorted(currencies):
            fx[cur], fx_status[cur] = self.rate(cur, day)
        issues = c.problems + [f"{k}/INR: {v}" for k, v in fx_status.items() if v != "ok"]
        expected = c.total_claimed or len(listed)
        priced = [r for r in c.rows if r.price is not None]
        coverage = len(c.rows) / expected if expected else 1.0
        complete = (
            not c.pages_failed
            and not c.pages_blocked
            and not c.pages_empty
            and coverage >= self.s.complete_coverage
        )

        def home_price(r):
            return r.price * fx[r.currency or home] / fx[home]

        # mass-change guard: many prices moving by the same ratio is a currency or unit problem, not a market
        ratios = [
            home_price(r) / state[r.product_id]["price_home"]
            for r in priced
            if r.product_id in state and state[r.product_id]["price_home"]
        ]
        moved = [x for x in ratios if abs(x - 1) >= self.s.price_change]
        status = "complete" if complete else "partial"
        if not c.rows:
            status = "quarantined"
            issues.append("no products parsed: layout change or the site is down")
        elif len(ratios) >= 20 and len(moved) / len(ratios) >= self.s.mass_change_share:
            med = statistics.median(moved)
            close = sum(abs(x / med - 1) <= self.s.mass_change_spread for x in moved)
            if close / len(moved) >= 0.8:
                status = "quarantined"
                issues.append(
                    f"{len(moved)} of {len(ratios)} prices moved by the same ratio ({med:.3f}x): "
                    "currency or unit problem, not real changes"
                )
        result = RunResult(d, status, round(coverage, 4), len(c.rows), expected, issues=issues, fx=fx)
        if status != "quarantined":
            result.alerts = self._apply(d, c, state, fx, home, complete, home_price)
        self.store.save_run(site, d, status, coverage, len(c.rows), expected, fx, issues)
        self.store.commit()
        return result

    def _apply(self, d, c, state, fx, home, complete, home_price) -> list[dict]:
        site, alerts, out, hist = self.site.name, [], [], []

        def alert(pid, kind, old, new, detail=""):
            alerts.append(
                {
                    "site": site,
                    "run_date": d,
                    "product_id": pid,
                    "kind": kind,
                    "old_value": None if old is None else str(old),
                    "new_value": None if new is None else str(new),
                    "detail": detail,
                }
            )

        seen = set()
        for r in c.rows:
            seen.add(r.product_id)
            old = state.get(r.product_id)
            ph = home_price(r) if r.price is not None else None
            rec = (
                dict(old)
                if old
                else {
                    "site": site,
                    "product_id": r.product_id,
                    "first_seen": d,
                    "price": None,
                    "price_home": None,
                    "price_inr": None,
                    "in_stock": None,
                }
            )
            if old is None or old["status"] == "delisted":
                if state:  # the first run is the baseline, not 1,000 "new product" alerts
                    alert(r.product_id, "new", None, f"{ph:.2f} {home}" if ph else None, r.title)
            else:
                if (
                    ph is not None
                    and old["price_home"]
                    and abs(ph / old["price_home"] - 1) >= self.s.price_change
                ):
                    alert(
                        r.product_id,
                        "price_change",
                        round(old["price_home"], 2),
                        round(ph, 2),
                        f"{ph / old['price_home'] - 1:+.1%} {home}",
                    )
                if old["in_stock"] == 1 and r.in_stock is False:
                    alert(r.product_id, "stock_out", "in stock", "out of stock", r.title)
                if old["in_stock"] == 0 and r.in_stock is True:
                    alert(r.product_id, "back_in_stock", "out of stock", "in stock", r.title)
                if old["title"] != r.title:
                    alert(r.product_id, "title_change", old["title"], r.title)
            rec.update(
                title=r.title,
                url=r.url,
                category=r.category,
                status="active",
                last_seen=d,
                last_checked=d,
                missing_runs=0,
            )
            if r.in_stock is not None:
                rec["in_stock"] = int(r.in_stock)
            if ph is not None:  # an unreadable price keeps the last known one rather than inventing a number
                rec.update(currency=r.currency or home, price=r.price, price_home=ph, price_inr=ph * fx[home])
                hist.append(
                    (
                        site,
                        d,
                        r.product_id,
                        r.title,
                        rec["currency"],
                        r.price,
                        ph,
                        rec["price_inr"],
                        rec["in_stock"],
                    )
                )
            rec.setdefault("currency", r.currency or home)
            out.append(rec)
        for pid, old in state.items():
            if pid in seen or old["status"] == "delisted":
                continue
            rec = dict(old)
            rec["last_checked"] = d
            if complete:
                rec["missing_runs"] = (old["missing_runs"] or 0) + 1
                if rec["missing_runs"] >= self.s.delist_after:
                    rec["status"] = "delisted"
                    alert(
                        pid,
                        "delisted",
                        old["title"],
                        None,
                        f"missing from {rec['missing_runs']} complete crawls",
                    )
                else:
                    rec["status"] = "missing"
            else:
                rec["status"] = "stale"  # not seen because the crawl was incomplete: no conclusion drawn
            out.append(rec)
        self.store.save_current(out)
        self.store.many("INSERT INTO history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING", hist)
        self.store.many("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?)", [tuple(a.values()) for a in alerts])
        return alerts
