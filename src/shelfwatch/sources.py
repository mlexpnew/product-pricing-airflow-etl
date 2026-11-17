"""Where pages and exchange rates come from: the live web, or the simulator in synth.py."""

from __future__ import annotations

import time
from datetime import date
from typing import Protocol
from urllib import robotparser
from urllib.parse import urlparse

import requests


class PageSource(Protocol):
    def get(self, url: str) -> tuple[int, str]: ...


class RateSource(Protocol):
    def rate(self, currency: str, day: date) -> float:
        """Rupees per unit of `currency` on `day`. Raises on failure."""
        ...


class LiveSite:
    """Polite HTTP fetching: a real user agent, a delay between requests, retries with backoff."""

    def __init__(self, delay: float = 0.5, retries: int = 3, timeout: float = 15):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "ShelfWatch/1.0 (price monitoring; contact: set SHELFWATCH_CONTACT)"
        self.delay, self.retries, self.timeout = delay, retries, timeout

        self.robots: dict[str, robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        """Respect the site's robots.txt; if it cannot be read, assume allowed (as browsers and crawlers do)."""
        host = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if host not in self.robots:
            rp = robotparser.RobotFileParser(host + "/robots.txt")
            try:
                rp.read()
            except Exception:  # noqa: BLE001
                rp = None
            self.robots[host] = rp
        rp = self.robots[host]
        return rp is None or rp.can_fetch(self.s.headers["User-Agent"], url)

    def get(self, url: str) -> tuple[int, str]:
        if not self.allowed(url):
            return 403, "disallowed by robots.txt"
        last = (0, "")
        for attempt in range(self.retries):
            try:
                r = self.s.get(url, timeout=self.timeout)
                r.encoding = r.apparent_encoding or "utf-8"
                last = (r.status_code, r.text)
                if r.status_code < 500 and r.status_code != 429:
                    break
            except requests.RequestException:
                last = (0, "")
            time.sleep(self.delay * (2**attempt))
        time.sleep(self.delay)
        return last


class Frankfurter:
    """European Central Bank reference rates (no key needed)."""

    url = "https://api.frankfurter.app/{day}"

    def rate(self, currency: str, day: date) -> float:
        if currency == "INR":
            return 1.0
        r = requests.get(
            self.url.format(day=day.isoformat()), params={"from": currency, "to": "INR"}, timeout=10
        )
        r.raise_for_status()
        return float(r.json()["rates"]["INR"])


class OpenErApi:
    """Second opinion when the first source looks wrong (latest rate only)."""

    url = "https://open.er-api.com/v6/latest/{cur}"

    def rate(self, currency: str, day: date) -> float:
        if currency == "INR":
            return 1.0
        r = requests.get(self.url.format(cur=currency), timeout=10)
        r.raise_for_status()
        return float(r.json()["rates"]["INR"])
