"""
United Kingdom — Home Office Register of Licensed Sponsors (workers).

Only employers on this register can sponsor a Skilled Worker visa, so it is
an authoritative yes/no. Download the CSV from
https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers
and import it with: python scripts/build_sponsor_db.py --country GB <file.csv>
"""

import os
import sqlite3
from collections import Counter

from regions.base import DataRegion, normalize_company
from regions.us import read_rows

SCHEMA = """
CREATE TABLE sponsors (
    name_norm TEXT NOT NULL, name TEXT, town TEXT, county TEXT, rating TEXT, route TEXT
);
"""
INDEX = "CREATE INDEX idx_sponsor_norm ON sponsors(name_norm);"

COLUMNS = {
    "name":   ["ORGANISATION NAME", "ORGANIZATION NAME"],
    "town":   ["TOWN/CITY", "TOWN", "CITY"],
    "county": ["COUNTY"],
    "rating": ["TYPE & RATING", "TYPE AND RATING", "RATING"],
    "route":  ["ROUTE"],
}

# Routes that let an employer hire a foreign worker into an ordinary job
SKILLED_ROUTES = ("skilled worker", "senior or specialist worker", "health and care")


def _pick(row: dict, key: str):
    for col in COLUMNS[key]:
        if col in row and row[col] not in (None, ""):
            return str(row[col]).strip()
    return ""


class UnitedKingdom(DataRegion):
    code, name, currency = "GB", "United Kingdom", "GBP"
    aliases = ("united kingdom", "uk", "u.k.", "great britain", "england", "scotland",
               "wales", "northern ireland")
    data_source = "UK Register of Licensed Sponsors"
    data_setup  = {
        "url": "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers",
        "file_hint": "the “Worker and Temporary Worker” register (.csv)",
    }
    table = "sponsors"

    def _status_detail(self, conn) -> str:
        n = conn.execute("SELECT COUNT(DISTINCT name_norm) FROM sponsors").fetchone()[0]
        return f"{n:,} licensed employers"

    def lookup(self, company: str, title: str = "") -> dict | None:
        norm = normalize_company(company)
        if not norm or not self.available:
            return None
        cols = "name, town, rating, route"
        try:
            rows = self._match(f"SELECT {cols} FROM sponsors WHERE name_norm = ?",
                               f"SELECT {cols} FROM sponsors WHERE name_norm LIKE ?", norm)
        except sqlite3.Error:
            return None
        if not rows:
            return None

        names   = Counter(r[0] for r in rows)
        towns   = Counter(r[1] for r in rows if r[1])
        routes  = Counter(r[3] for r in rows if r[3])
        skilled = any(any(s in rt.lower() for s in SKILLED_ROUTES) for rt in routes)

        reasons = ["On the UK Register of Licensed Sponsors"]
        reasons.append("Licensed for Skilled Worker visas" if skilled
                       else "Licensed only for: " + ", ".join(list(routes)[:2]))

        return {
            "strength": "strong" if skilled else "some",
            "names":    [n for n, _ in names.most_common(3)],
            "reasons":  reasons,
            "stats":    [
                {"value": "Yes" if skilled else "No", "label": "Skilled Worker licence"},
                {"value": f"{len(routes)}", "label": "visa routes"},
                {"value": towns.most_common(1)[0][0] if towns else "–", "label": "registered town"},
            ],
            "chart":    None,
            "table":    {"title": "Licensed routes", "rows": [[rt, ""] for rt, _ in routes.most_common(6)]},
            "summary":  "Licensed sponsor" + (" (Skilled Worker)" if skilled else ""),
            "pay":      None,
        }

    def build(self, paths: list, out: str) -> int:
        conn = sqlite3.connect(out)
        conn.executescript(SCHEMA)
        total = 0
        for path in paths:
            batch = []
            for row in read_rows(path):
                name = _pick(row, "name")
                norm = normalize_company(name)
                if not norm:
                    continue
                batch.append((norm, name, _pick(row, "town"), _pick(row, "county"),
                              _pick(row, "rating"), _pick(row, "route")))
            conn.executemany("INSERT INTO sponsors VALUES (?,?,?,?,?,?)", batch)
            print(f"  {os.path.basename(path)}: {len(batch):,} rows")
            total += len(batch)
        conn.executescript(INDEX)
        conn.commit()
        conn.close()
        return total
