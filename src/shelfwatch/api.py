"""HTTP API for the seller's tools (pricing sheet, ERP, Slack bot).

uvicorn shelfwatch.api:app     # SHELFWATCH_DB, and SHELFWATCH_API_KEYS to require X-API-Key
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import insights
from .parse import BOOKS
from .store import Store

app = FastAPI(
    title="ShelfWatch",
    version="1.0.0",
    description="Competitor prices and stock, checked before they are trusted.",
)


def store() -> Store:
    return Store(os.getenv("SHELFWATCH_DB", "sqlite:///shelfwatch.db"))


def auth(x_api_key: str | None = Header(default=None)):
    keys = {k.strip() for k in os.getenv("SHELFWATCH_API_KEYS", "").split(",") if k.strip()}
    if keys and x_api_key not in keys:
        raise HTTPException(401, "missing or invalid X-API-Key")


class MyPrices(BaseModel):
    prices: dict[str, float] = Field(description="product id (ISBN/UPC/SKU) -> my price in rupees")
    margin: float = Field(0.0, ge=0, le=0.9)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/runs", dependencies=[Depends(auth)])
def runs(limit: int = 30):
    return insights.runs(store(), BOOKS.name, limit)


@app.get("/v1/alerts", dependencies=[Depends(auth)])
def alerts(since: str = "", kind: str | None = None):
    return insights.alerts(store(), BOOKS.name, since, kind)


@app.get("/v1/products/{product_id}/history", dependencies=[Depends(auth)])
def history(product_id: str):
    rows = insights.history(store(), BOOKS.name, product_id)
    if not rows:
        raise HTTPException(404, "unknown product")
    return rows


@app.post("/v1/undercuts", dependencies=[Depends(auth)])
def undercuts(body: MyPrices):
    return insights.undercuts(store(), BOOKS.name, body.prices, body.margin)
