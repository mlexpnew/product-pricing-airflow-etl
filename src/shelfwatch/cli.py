"""Command line.

shelfwatch run --db sqlite:///shelfwatch.db         # today's crawl of the live site
shelfwatch demo --db sqlite:///demo.db --days 30    # a simulated month, for the dashboard
shelfwatch alerts --db ... --since 2026-01-01 --out alerts.csv
shelfwatch undercut --db ... my_prices.csv --margin 0.05
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date

from .insights import alerts, undercuts
from .monitor import Monitor
from .parse import BOOKS
from .sources import Frankfurter, LiveSite, OpenErApi
from .store import Store

DB = os.getenv("SHELFWATCH_DB", "sqlite:///shelfwatch.db")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shelfwatch")
    ap.add_argument("--db", default=DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date", default=None)
    r.add_argument("--force", action="store_true")
    r.add_argument("--max-pages", type=int, default=500, help="for a quick trial")
    d = sub.add_parser("demo")
    d.add_argument("--days", type=int, default=30)
    a = sub.add_parser("alerts")
    a.add_argument("--since", default="")
    a.add_argument("--kind")
    a.add_argument("--out")
    u = sub.add_parser("undercut")
    u.add_argument("prices", help="CSV with product_id,my_price_inr")
    u.add_argument("--margin", type=float, default=0.0)
    x = ap.parse_args(argv)
    store = Store(x.db)
    if x.cmd == "run":
        day = date.fromisoformat(x.date) if x.date else date.today()
        res = Monitor(store, LiveSite(), Frankfurter(), OpenErApi(), max_pages=x.max_pages).run(
            day, force=x.force
        )
        print(
            json.dumps(
                {k: v for k, v in res.__dict__.items() if k != "alerts"} | {"alerts": len(res.alerts)}, indent=2
            )
        )
        return 0 if res.status != "quarantined" else 2
    if x.cmd == "demo":
        from .demo import build

        build(store, x.days)
        print(f"simulated {x.days} days into {x.db}")
        return 0
    if x.cmd == "alerts":
        rows = alerts(store, BOOKS.name, x.since, x.kind)
        w = csv.DictWriter(
            open(x.out, "w", newline="") if x.out else sys.stdout,
            fieldnames=rows[0].keys() if rows else ["run_date"],
        )
        w.writeheader()
        w.writerows(rows)
        return 0
    with open(x.prices) as f:
        mine = {row["product_id"]: float(row["my_price_inr"]) for row in csv.DictReader(f)}
    for row in undercuts(store, BOOKS.name, mine, x.margin):
        print(
            f"{row['product_id']}  {row['title'][:40]:40}  mine ₹{row['my_price_inr']:,.0f}  "
            f"theirs ₹{row['their_price_inr']:,.0f}  {row['gap']:+.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
