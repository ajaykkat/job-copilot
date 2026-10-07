"""
Country pack base class + helpers shared by every region.

A Region answers one question for its country: "is this employer able and
willing to hire someone who needs a work permit?" Regions with public data
(US H-1B filings, UK sponsor register, …) subclass DataRegion and import that
data into a local SQLite file; every other country still gets the job-post
wording check.
"""

import os
import re
import sqlite3
import threading

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("XHR_DATA_DIR", os.path.join(ROOT, "data", "regions"))

# Legal suffixes and filler words dropped when normalizing employer names,
# so "Google LLC", "Google, Inc." and "Google Ltd" all compare equal.
_SUFFIXES = {
    "inc", "incorporated", "llc", "corp", "corporation", "co", "company",
    "ltd", "limited", "lp", "llp", "plc", "pc", "pllc", "na", "the", "usa", "us", "uk",
    "gmbh", "ag", "sa", "sas", "srl", "bv", "nv", "pty", "pvt", "private", "pte",
}


def normalize_company(name: str) -> str:
    """Lowercase, strip punctuation and legal suffixes."""
    # Drop periods first so "L.L.C." → "llc" and "N.A." → "na"
    s = (name or "").lower().replace(".", "").replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = s.split()
    while words and words[-1] in _SUFFIXES:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "CAD": "C$", "AUD": "A$", "INR": "₹",
                    "SGD": "S$", "AED": "AED ", "JPY": "¥", "BRL": "R$", "PHP": "₱", "NGN": "₦"}


def money(amount, currency: str = "USD") -> str:
    """Compact pay figure for display: 133000 → "$133k"."""
    if not amount:
        return "–"
    sym = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{sym}{round(amount / 1000)}k"


class Region:
    """A country with no imported data: verdicts come from job-post wording only."""

    code     = ""
    name     = ""
    currency = "USD"
    aliases: tuple = ()          # extra strings that identify the country in a job location
    data_source = None           # human description of the public dataset, if any
    data_setup  = None           # {"url": …, "file_hint": …} for the setup instructions

    def status(self) -> dict:
        return {"available": False, "has_data": False, "rows": 0, "detail": ""}

    def lookup(self, company: str, title: str = "") -> dict | None:
        """Evidence for this employer, or None. See DataRegion for the shape."""
        return None

    def not_found_reason(self) -> str:
        if self.data_source:
            return f"{self.data_source} not loaded"
        return f"No sponsorship data for {self.name} yet; checking the job post's wording"

    def authorized_by_status(self, profile: dict):
        """True if the profile's country-specific status already allows work here; None if unknown."""
        return None

    def info(self) -> dict:
        st = self.status()
        return {
            "code": self.code, "name": self.name, "currency": self.currency,
            "data_source": self.data_source, "data_setup": self.data_setup,
            "has_data": st["has_data"], "available": st["available"],
            "rows": st["rows"], "detail": st["detail"],
        }


class DataRegion(Region):
    """A country whose public employer data is imported into data/regions/<code>.db."""

    table = ""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(DATA_DIR, f"{self.code.lower()}.db")
        self._local = threading.local()

    @property
    def available(self) -> bool:
        return os.path.exists(self.path)

    def _conn(self) -> sqlite3.Connection:
        # One connection per thread: the agent runs in a worker thread.
        # Reconnect if the file was rebuilt (atomic replace → new inode).
        try:
            ino = os.stat(self.path).st_ino
        except OSError:
            ino = None
        conn = getattr(self._local, "conn", None)
        if conn is None or getattr(self._local, "ino", None) != ino:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            self._local.conn, self._local.ino = conn, ino
        return conn

    def _status_detail(self, conn) -> str:
        return ""

    def status(self) -> dict:
        base = {"available": False, "has_data": True, "rows": 0, "detail": ""}
        if not self.available:
            return base
        try:
            conn = self._conn()
            rows = conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0]
            return {**base, "available": True, "rows": rows, "detail": self._status_detail(conn)}
        except sqlite3.Error:
            return base

    def not_found_reason(self) -> str:
        if not self.available:
            return f"{self.data_source} not loaded"
        return f"Not found in {self.data_source}"

    def _match(self, sql_exact: str, sql_prefix: str, norm: str) -> list:
        """Exact normalized-name match, else a word-prefix match ("Amazon" → "amazon web services")."""
        rows = self._conn().execute(sql_exact, (norm,)).fetchall()
        if rows or len(norm) < 3:   # "hp %" would match unrelated employers
            return rows
        return self._conn().execute(sql_prefix, (norm + " %",)).fetchall()

    # Subclasses implement:
    #   lookup(company, title) -> {
    #       "strength": "strong" | "some",      # → verdict likely | possible
    #       "names":    [matched employer names],
    #       "reasons":  [short evidence lines],
    #       "stats":    [{"value": "1,725", "label": "H-1B filings"}, …],
    #       "chart":    {"title": …, "bars": [[label, count], …]} | None,
    #       "table":    {"title": …, "rows": [[text, count], …]} | None,
    #       "summary":  "1,725 H-1B filings",    # one line for the tracker
    #       "pay":      "$131k" | None,
    #   }
    #   build(paths, out) -> rows imported
