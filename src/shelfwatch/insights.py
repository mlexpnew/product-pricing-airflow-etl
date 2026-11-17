"""Answers a seller asks: where is a competitor cheaper than me, and what changed."""

from __future__ import annotations

from .store import Store


def undercuts(store: Store, site: str, my_prices: dict[str, float], margin: float = 0.0) -> list[dict]:
    """Products where the competitor's rupee price is below mine by more than `margin` (0.05 = 5%).

    `my_prices` maps the shared product identifier (ISBN/UPC/SKU) to my selling price in rupees.
    Stale or delisted competitor prices are left out: no decision on a number that may be old.
    """
    out = []
    for pid, mine in my_prices.items():
        rows = store.query("SELECT * FROM products WHERE site = ? AND product_id = ?", (site, pid))
        if not rows or rows[0]["status"] != "active" or not rows[0]["price_inr"] or not rows[0]["in_stock"]:
            continue
        theirs = rows[0]["price_inr"]
        if theirs < mine * (1 - margin):
            out.append(
                {
                    "product_id": pid,
                    "title": rows[0]["title"],
                    "my_price_inr": round(mine, 2),
                    "their_price_inr": round(theirs, 2),
                    "gap": round(theirs / mine - 1, 4),
                    "checked": rows[0]["last_checked"],
                }
            )
    return sorted(out, key=lambda r: r["gap"])


def alerts(store: Store, site: str, since: str = "", kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM alerts WHERE site = ? AND run_date >= ?"
    params: list = [site, since]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    return store.query(sql + " ORDER BY run_date DESC", tuple(params))


def history(store: Store, site: str, product_id: str) -> list[dict]:
    return store.query(
        "SELECT run_date, price, currency, price_home, price_inr, in_stock FROM history "
        "WHERE site = ? AND product_id = ? ORDER BY run_date",
        (site, product_id),
    )


def runs(store: Store, site: str, limit: int = 60) -> list[dict]:
    return store.query("SELECT * FROM runs WHERE site = ? ORDER BY run_date DESC LIMIT ?", (site, limit))
