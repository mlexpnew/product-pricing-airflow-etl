from shelfwatch.baseline import NaivePipeline
from shelfwatch.insights import undercuts
from shelfwatch.monitor import Monitor
from shelfwatch.store import Store
from shelfwatch.synth import SynthRates, SynthSite, World


def day(store, w, site_f=None, primary=None, backup=None):
    return Monitor(store, SynthSite(w, site_f or {}), SynthRates(w, primary), SynthRates(w, backup)).run(
        w.today
    )


def setup(n=200):
    w, s = World(4, n=n), Store("sqlite:///:memory:")
    day(s, w)
    return w, s


def test_first_run_is_baseline_then_real_changes_alert():
    w, s = setup()
    p = w.products[5]
    p.price = round(p.price * 0.8, 2)
    w.step()
    r = day(s, w)
    assert r.status == "complete"
    assert any(a["kind"] == "price_change" and a["product_id"] == p.upc for a in r.alerts)


def test_timeouts_never_delist():
    w, s = setup()
    w.step()
    r = day(s, w, {"timeout": 3})
    assert r.status == "partial"
    assert not [a for a in r.alerts if a["kind"] == "delisted"]
    assert s.query("SELECT COUNT(*) AS n FROM products WHERE status = 'stale'")[0]["n"] >= 40


def test_currency_switch_is_converted_not_alerted():
    w, s = setup()
    w.step()
    r = day(s, w, {"currency": "EUR"})
    truth_changes = 0.05 * len(w.products)
    assert len([a for a in r.alerts if a["kind"] == "price_change"]) < truth_changes


def test_broken_rate_is_rejected():
    w, s = setup()
    w.step()
    r = day(s, w, primary="x100")
    assert abs(r.fx["GBP"] / w.gbp - 1) < 0.001
    w.step()
    r = day(s, w, primary="error", backup="error")
    assert r.fx["GBP"] > 0 and any("stale" in i for i in r.issues)


def test_unknown_layout_is_quarantined_and_keeps_yesterday():
    w, s = setup()
    before = s.query("SELECT COUNT(*) AS n FROM products WHERE status = 'active'")[0]["n"]
    w.step()
    r = day(s, w, {"layout_unknown": True})
    assert r.status == "quarantined" and not r.alerts
    assert s.query("SELECT COUNT(*) AS n FROM products WHERE status = 'active'")[0]["n"] == before


def test_rerun_same_day_is_idempotent():
    w, s = setup()
    w.step()
    day(s, w)
    n = s.query("SELECT COUNT(*) AS n FROM alerts")[0]["n"]
    r = day(s, w)
    assert r.issues == ["already ran"] and s.query("SELECT COUNT(*) AS n FROM alerts")[0]["n"] == n


def test_undercuts_skip_stale():
    w, s = setup(60)
    p = w.products[0]
    if not p.in_stock:
        p.in_stock = True
        w.step()
        day(s, w)
    mine = {p.upc: p.price * w.gbp * 1.2}
    rows = undercuts(s, "books.toscrape.com", mine, 0.05)
    assert rows and rows[0]["product_id"] == p.upc


def test_original_pipeline_loses_the_day_on_one_timeout():
    w = World(4, n=100)
    n = NaivePipeline()
    n.run(SynthSite(w), SynthRates(w), w.today)
    w.step()
    assert n.run(SynthSite(w, {"timeout": 1}), SynthRates(w), w.today) == []
