"""ShelfWatch desk screen. streamlit run app.py   (SHELFWATCH_DB, or a simulated month if empty)"""

import os

import pandas as pd
import streamlit as st

from shelfwatch import insights
from shelfwatch.parse import BOOKS
from shelfwatch.store import Store

st.set_page_config(page_title="ShelfWatch", layout="wide")
st.title("ShelfWatch")
st.caption(
    "Competitor prices and stock in rupees. Every crawl is checked before it is trusted: incomplete crawls "
    "never delist products, odd exchange rates need a second source, and currency or layout problems are "
    "quarantined."
)


@st.cache_resource
def get_store():
    s = Store(os.getenv("SHELFWATCH_DB", "sqlite:///:memory:"))
    if not s.query("SELECT 1 FROM runs LIMIT 1"):
        from shelfwatch.demo import build

        build(s, 30)
    return s


s = get_store()
site = BOOKS.name
runs = pd.DataFrame(insights.runs(s, site, 60))
c1, c2, c3, c4 = st.columns(4)
last = runs.iloc[0]
c1.metric("Last run", last.run_date, last.status)
c2.metric("Products seen", int(last.items_seen), f"coverage {last.coverage:.0%}")
cur = pd.DataFrame(s.query("SELECT * FROM products WHERE site = ?", (site,)))
c3.metric("Active products", int((cur.status == "active").sum()))
c4.metric("Runs needing a look", int((runs.status != "complete").sum()))

st.subheader("Runs")
st.dataframe(
    runs[["run_date", "status", "coverage", "items_seen", "expected", "issues"]],
    hide_index=True,
    use_container_width=True,
)

st.subheader("Alerts")
al = pd.DataFrame(insights.alerts(s, site))
kinds = st.multiselect(
    "Show", sorted(al.kind.unique()), default=[k for k in sorted(al.kind.unique()) if k != "title_change"]
)
st.dataframe(
    al[al.kind.isin(kinds)][["run_date", "kind", "product_id", "old_value", "new_value", "detail"]],
    hide_index=True,
    use_container_width=True,
)

st.subheader("One product")
pid = st.selectbox(
    "Product",
    cur.sort_values("title").product_id,
    format_func=lambda p: cur.set_index("product_id").title[p][:60],
)
h = pd.DataFrame(insights.history(s, site, pid))
if len(h):
    st.line_chart(h.set_index("run_date")[["price_inr"]])

st.subheader("Where am I more expensive?")
up = st.file_uploader("My prices (CSV: product_id,my_price_inr)", type="csv")
margin = st.slider("Only show gaps above", 0, 30, 5, format="%d%%") / 100
if up:
    mine = pd.read_csv(up)
    rows = insights.undercuts(s, site, dict(zip(mine.product_id, mine.my_price_inr, strict=True)), margin)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
else:
    st.caption("Upload your price list to see where this competitor undercuts you.")
