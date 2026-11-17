"""Benchmark: ShelfWatch vs the original pipeline on a simulated competitor catalogue with known truth.

    python -m shelfwatch.evaluate --gate

Both pipelines crawl the same catalogue every day. Some days the crawl goes wrong (pages time out,
a bot-check page, prices in another currency, a renamed CSS class, a broken exchange-rate API).
Scored every day against the truth:
  - wrong prices in the warehouse: listed products whose stored rupee price is more than 1% off, or
    that are missing or marked delisted; "silent" when nothing marks them as doubtful
  - change alerts (price change, stock-out, back in stock, new, delisted): found within 2 days, and false
Dev: two catalogues. Held-out: a different catalogue, different fault rates, and fault types never
seen in dev (an unknown page layout, pages served from a stale cache, both rate APIs down), run once.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

from .baseline import NaivePipeline
from .monitor import ALERT_KINDS, Monitor
from .store import Store
from .synth import SynthRates, SynthSite, World

DEV = {
    "seeds": [1, 2],
    "days": 40,
    "p_fault": 0.30,
    "faults": ["timeout", "block", "currency_eur", "layout", "fx_x100", "fx_error", "fx_jump"],
}
HELD_OUT = {
    "seeds": [21],
    "days": 40,
    "p_fault": 0.35,
    "faults": [
        "timeout",
        "block",
        "currency_usd",
        "layout",
        "fx_x100",
        "fx_jump",
        "layout_unknown",
        "stale_pages",
        "fx_both_down",
    ],
}


def day_faults(kind: str | None, rng: random.Random):
    site, primary, backup = {}, None, None
    if kind == "timeout":
        site["timeout"] = rng.randint(1, 3)
    elif kind == "block":
        site["block"] = rng.randint(1, 5)
    elif kind == "currency_eur":
        site["currency"] = "EUR"
    elif kind == "currency_usd":
        site["currency"] = "USD"
    elif kind in ("layout", "layout_unknown"):
        site[kind] = True
    elif kind == "stale_pages":
        site["stale_pages"] = rng.randint(2, 6)
    elif kind == "fx_x100":
        primary = "x100"
    elif kind == "fx_error":
        primary = "error"
    elif kind == "fx_jump":
        primary = "jump"
    elif kind == "fx_both_down":
        primary = backup = "error"
    return site, primary, backup


def changes(prev: dict, now: dict) -> list[tuple[str, str]]:
    out = []
    for upc, t in now.items():
        o = prev.get(upc)
        if o is None:
            out.append((upc, "new"))
            continue
        if abs(t["price"] / o["price"] - 1) >= 0.01:
            out.append((upc, "price_change"))
        if o["in_stock"] and not t["in_stock"]:
            out.append((upc, "stock_out"))
        if not o["in_stock"] and t["in_stock"]:
            out.append((upc, "back_in_stock"))
    out += [(upc, "delisted") for upc in prev if upc not in now]
    return out


def score_alerts(truth: list[tuple], alerts: list[tuple], last_day: int, lag: int = 2, late: int = 7) -> dict:
    """A change is caught if alerted within `lag` days. An alert is false if no such change happened in the
    `late` days before it (a correct but late alert counts as late, not false). Changes in the final `lag`
    days are not scored, since no system had the chance to confirm them."""
    by_key: dict = {}
    for d, upc, k in alerts:
        by_key.setdefault((upc, k), []).append(d)
    t_key: dict = {}
    for d, upc, k in truth:
        t_key.setdefault((upc, k), []).append(d)
    scored = [x for x in truth if x[0] <= last_day - lag]

    def hit(t, u, k, window):
        return any(t <= d <= t + window for d in by_key.get((u, k), []))

    found = sum(hit(*x, lag) for x in scored)
    late_found = sum(hit(*x, late) for x in scored) - found
    true_alerts = sum(any(t <= d <= t + late for t in t_key.get((u, k), [])) for d, u, k in alerts)
    kinds = {}
    for kind in ALERT_KINDS:
        tk = [x for x in scored if x[2] == kind]
        kinds[kind] = f"{sum(hit(*x, lag) for x in tk)}/{len(tk)}"
    return {
        "changes": len(scored),
        "found": found,
        "late": late_found,
        "alerts": len(alerts),
        "false_alerts": len(alerts) - true_alerts,
        "by_kind": kinds,
    }


def run_catalogue(seed: int, cfg: dict) -> dict:
    w = World(seed)
    rng = random.Random(seed + 7)
    store = Store("sqlite:///:memory:")
    naive = NaivePipeline()
    snapshots = [copy.deepcopy([p for p in w.products if p.listed])]
    title_to_upc: dict[str, str] = {}
    res = {"days": cfg["days"], "products": len(w.truth()), "faults": Counter()}
    truth_log, sw_alerts, nv_alerts = [], [], []
    wrong = {"shelfwatch": [0, 0], "original": [0, 0]}  # [silent, flagged]
    checked = 0
    statuses = Counter()
    for day in range(cfg["days"] + 1):
        if day:
            w.step()
            snapshots.append(copy.deepcopy([p for p in w.products if p.listed]))
        kind = rng.choice(cfg["faults"]) if day and rng.random() < cfg["p_fault"] else None
        if kind:
            res["faults"][kind] += 1
        site_f, prim, back = day_faults(kind, rng)
        older = snapshots[max(0, len(snapshots) - 4)] if site_f.get("stale_pages") else None
        for p in w.products:
            title_to_upc[p.title] = p.upc
        truth = w.truth()
        if day:
            truth_log += [(day, u, k) for u, k in changes(prev_truth, truth)]  # noqa: F821 - set below
        # ShelfWatch
        mon = Monitor(store, SynthSite(w, site_f, older), SynthRates(w, prim), SynthRates(w, back))
        r = mon.run(w.today)
        statuses[r.status] += 1
        if day:
            sw_alerts += [(day, a["product_id"], a["kind"]) for a in r.alerts if a["kind"] in ALERT_KINDS]
        # original
        na = naive.run(SynthSite(w, site_f, older), SynthRates(w, prim), w.today)
        if day:
            nv_alerts += [(day, title_to_upc.get(a["title"], a["title"]), a["kind"]) for a in na]
        # warehouse accuracy at the end of the day
        cur = store.current(mon.site.name)
        if day:
            for upc, t in truth.items():
                true_inr = t["price"] * w.gbp
                checked += 1
                c = cur.get(upc)
                if (
                    c is None
                    or c["status"] == "delisted"
                    or c["price_inr"] is None
                    or abs(c["price_inr"] / true_inr - 1) > 0.01
                ):
                    wrong["shelfwatch"][1 if c is not None and c["status"] in ("stale", "missing") else 0] += 1
                n = naive.warehouse.get(hashlib.md5(t["title"].encode()).hexdigest())
                if n is None or abs(n["price_inr"] / true_inr - 1) > 0.01:
                    wrong["original"][0] += 1
        prev_truth = truth  # noqa: F841
    res["product_days"] = checked
    res["statuses"] = dict(statuses)
    res["faults"] = dict(res["faults"])
    for name, alerts in (("shelfwatch", sw_alerts), ("original", nv_alerts)):
        res[name] = {
            "wrong_silent": wrong[name][0],
            "wrong_flagged": wrong[name][1],
            **score_alerts(truth_log, alerts, cfg["days"]),
        }
    return res


def run(cfg: dict) -> dict:
    cats = [run_catalogue(s, cfg) for s in cfg["seeds"]]
    out = {
        "catalogues": len(cats),
        "product_days": sum(c["product_days"] for c in cats),
        "faults": sum((Counter(c["faults"]) for c in cats), Counter()),
        "statuses": sum((Counter(c["statuses"]) for c in cats), Counter()),
    }
    for name in ("original", "shelfwatch"):
        tot = Counter()
        kinds: dict = {}
        for c in cats:
            tot.update({k: v for k, v in c[name].items() if isinstance(v, int)})
            for k, v in c[name]["by_kind"].items():
                a, b = map(int, v.split("/"))
                x = kinds.setdefault(k, [0, 0])
                x[0] += a
                x[1] += b
        out[name] = {
            **tot,
            "recall": round(tot["found"] / max(tot["changes"], 1), 4),
            "precision": round((tot["alerts"] - tot["false_alerts"]) / max(tot["alerts"], 1), 4),
            "by_kind": {k: f"{a}/{b}" for k, (a, b) in kinds.items()},
        }
    out["faults"], out["statuses"] = dict(out["faults"]), dict(out["statuses"])
    return out


def report(r: dict) -> str:
    d, h = r["dev"], r["held_out"]
    lines = [
        "| dev / held-out | Wrong prices, silent | Changes caught within 2 days | False alerts |",
        "|---|---|---|---|",
    ]
    for k, label in (("original", "Original pipeline"), ("shelfwatch", "**ShelfWatch**")):
        a, b = d[k], h[k]
        lines.append(
            f"| {label} | {a['wrong_silent']:,} / {b['wrong_silent']:,} | "
            f"{a['found']:,}/{a['changes']:,} ({a['recall']:.0%}) / {b['found']:,}/{b['changes']:,} "
            f"({b['recall']:.0%}) | {a['false_alerts']:,} / {b['false_alerts']:,} |"
        )
    lines += [
        "",
        f"Product-days checked: {d['product_days']:,} dev, {h['product_days']:,} held-out. "
        f"ShelfWatch flagged (not silent) wrong: {d['shelfwatch']['wrong_flagged']:,} / "
        f"{h['shelfwatch']['wrong_flagged']:,}.",
        f"Run status dev {d['statuses']}, held-out {h['statuses']}.",
        f"Faults dev {d['faults']}, held-out {h['faults']}.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark ShelfWatch")
    ap.add_argument("--out", default="eval_results")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--dev-only", action="store_true")
    a = ap.parse_args(argv)
    r = {"dev": run(DEV)}
    if a.dev_only:
        print(json.dumps(r, indent=1))
        return 0
    r["held_out"] = run(HELD_OUT)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(r, indent=2))
    md = report(r)
    (out / "report.md").write_text(md)
    print(md)
    if a.gate:
        s, o = r["dev"]["shelfwatch"], r["dev"]["original"]
        if (
            s["wrong_silent"] > o["wrong_silent"] * 0.1
            or s["recall"] < 0.95
            or s["false_alerts"] > o["false_alerts"] * 0.1
        ):
            print("gate failed", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
