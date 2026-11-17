"""Fill a database with a simulated month of monitoring, for the dashboard and API demo."""

from __future__ import annotations

import random

from .evaluate import day_faults
from .monitor import Monitor
from .store import Store
from .synth import SynthRates, SynthSite, World


def build(store: Store, days: int = 30, seed: int = 5) -> World:
    w = World(seed)
    rng = random.Random(seed)
    kinds = ["timeout", "block", "currency_eur", "layout", "fx_x100"]
    for day in range(days + 1):
        if day:
            w.step()
        kind = rng.choice(kinds) if day and rng.random() < 0.25 else None
        site_f, prim, back = day_faults(kind, rng)
        Monitor(store, SynthSite(w, site_f), SynthRates(w, prim), SynthRates(w, back)).run(w.today)
    return w
