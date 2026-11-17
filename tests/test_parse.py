from shelfwatch.parse import parse_list, parse_price, parse_product
from shelfwatch.synth import SynthSite, World


def test_prices():
    assert parse_price("£51.77") == ("GBP", 51.77)
    assert parse_price("Â£51.77") == ("GBP", 51.77)
    assert parse_price("£12.99 £9.99") == ("GBP", 9.99)  # sale: old price first, current last
    assert parse_price("€1,299.00") == ("EUR", 1299.0)
    assert parse_price("₹ 499") == ("INR", 499.0)
    assert parse_price("Price on request", "GBP") == ("GBP", None)  # never invents a number


def test_list_page_and_layout_fallback():
    w = World(3, n=45)
    url = "https://books.toscrape.com/catalogue/page-1.html"
    page = parse_list(SynthSite(w).get(url)[1], url=url)
    assert len(page.listings) == 20 and page.total == 45 and page.next_url.endswith("page-2.html")
    renamed = parse_list(SynthSite(w, {"layout": True}).get(url)[1], url=url)  # price class renamed
    assert [x.price_text for x in renamed.listings] == [x.price_text for x in page.listings]


def test_bot_check_is_recognised():
    w = World(3, n=45)
    site = SynthSite(w, {"block": 3})
    pages = [parse_list(site.get(f"https://books.toscrape.com/catalogue/page-{n}.html")[1]) for n in (1, 2, 3)]
    assert all(p.looks_blocked and not p.listings for p in pages)


def test_product_page():
    w = World(3, n=5)
    p = w.products[0]
    info = parse_product(SynthSite(w).get(p.url)[1])
    assert info == {"product_id": p.upc, "category": p.category}


def test_trial_run_says_it_stopped_early():
    from shelfwatch.crawl import crawl

    c = crawl(SynthSite(World(3, n=100)), {}, max_pages=2)
    assert len(c.rows) == 40 and c.stopped_early and "page limit" in " ".join(c.problems)
