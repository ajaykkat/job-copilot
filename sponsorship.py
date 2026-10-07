"""
Sponsorship intelligence — "will this company sponsor me?"

Two signals, combined into one verdict per job:
  1. H-1B history — public DOL LCA disclosure data, imported into a local
     SQLite file by scripts/build_sponsor_db.py (data/sponsors.db).
  2. The job description itself — explicit "will sponsor" / "no sponsorship"
     language, plus E-Verify mentions (required for STEM OPT employers).

Everything here is offline and fast; no API calls.
"""

import os
import re
import sqlite3
import statistics
import threading
from collections import Counter

ROOT    = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("XHR_SPONSOR_DB", os.path.join(ROOT, "data", "sponsors.db"))

# Legal suffixes and filler words dropped when normalizing employer names,
# so "Google LLC", "Google, Inc." and "google" all compare equal.
_SUFFIXES = {
    "inc", "incorporated", "llc", "corp", "corporation", "co", "company",
    "ltd", "limited", "lp", "llp", "plc", "pc", "pllc", "na", "the", "usa", "us",
}

# Seniority / level words ignored when matching job titles
_TITLE_NOISE = {
    "senior", "sr", "junior", "jr", "lead", "staff", "principal", "associate",
    "i", "ii", "iii", "iv", "1", "2", "3", "4", "level", "entry", "mid",
    "remote", "hybrid", "onsite", "contract", "fulltime", "full", "time",
    "the", "a", "an", "of", "and", "for", "with", "to", "in", "at",
}

POSITIVE_JD = [
    "will sponsor", "sponsorship available", "visa sponsorship available",
    "sponsorship is available", "h1b sponsorship", "h-1b sponsorship",
    "h1b transfer", "h-1b transfer", "open to sponsorship", "can sponsor",
    "willing to sponsor", "sponsorship provided", "we sponsor", "opt/cpt",
    "opt candidates", "stem opt", "f1 opt", "f-1 opt",
]

NEGATIVE_JD = [
    "no sponsorship", "no visa sponsorship", "cannot sponsor", "can not sponsor", "will not sponsor",
    "won't sponsor", "unable to sponsor", "not able to sponsor",
    "sponsorship not available", "sponsorship is not available",
    "not offering sponsorship", "does not sponsor", "do not sponsor",
    "without sponsorship", "without the need for sponsorship",
    "without requiring sponsorship", "us citizens only", "u.s. citizens only",
    "must be a us citizen", "must be a u.s. citizen", "citizenship required",
    "gc or us citizen", "green card or us citizen", "usc or gc", "usc/gc",
    "gc/usc", "no h1b", "no h-1b", "no opt", "no cpt", "no c2c",
    "security clearance required", "active clearance",
]

EVERIFY_JD = ["e-verify", "everify", "e verify"]

VERDICT_LABELS = {
    "likely":     "Sponsors",
    "possible":   "May sponsor",
    "unlikely":   "Won't sponsor",
    "unknown":    "No H-1B record",
    "not_needed": "Not needed",
}

_WAGE_MULT = {"year": 1, "hour": 2080, "week": 52, "bi-weekly": 26, "biweekly": 26, "month": 12}


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


def title_tokens(title: str) -> set:
    s = re.sub(r"[^a-z0-9+#]+", " ", (title or "").lower())
    return {w for w in s.split() if w not in _TITLE_NOISE}


_ACRONYMS = {"qa", "ui", "ux", "api", "aws", "sap", "etl", "it", "sre", "ml", "ai", "bi",
             "dba", "sql", "erp", "crm", "hr", "vp", "cto", "ios", "net", "ii", "iii", "iv"}


def display_title(title: str) -> str:
    """Readable job title: DOL rows are often ALL CAPS ("SR. QA ANALYST")."""
    t = " ".join((title or "").split())
    if not t.isupper():
        return t
    words = []
    for w in t.split(" "):
        core = re.sub(r"[^A-Za-z]", "", w).lower()
        words.append(w if core in _ACRONYMS else w.capitalize())
    return " ".join(words)


def annualize(amount, unit: str):
    """Convert a wage to an annual figure; None if unusable."""
    try:
        val = float(str(amount).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    mult = _WAGE_MULT.get((unit or "year").strip().lower())
    if not mult or val <= 0:
        return None
    annual = val * mult
    # Guard against obviously broken rows (hourly rate tagged as yearly, etc.)
    return annual if 15_000 <= annual <= 1_500_000 else None


def _phrase_re(phrases: list) -> list:
    return [(p, re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])")) for p in phrases]


_POS_RE, _NEG_RE, _EV_RE = _phrase_re(POSITIVE_JD), _phrase_re(NEGATIVE_JD), _phrase_re(EVERIFY_JD)


_NEGATION = re.compile(r"\b(no|not|never|without|unable|cannot|can't|won't|don't|doesn't)\b")


def _affirmed(rx, text: str) -> bool:
    """True if the phrase appears at least once without a negation just before it."""
    for m in rx.finditer(text):
        before = text[max(0, m.start() - 25):m.start()]
        if not _NEGATION.search(before):
            return True
    return False


def scan_jd(jd: str) -> dict:
    """Find sponsorship-related phrases in a job description (whole words only)."""
    text = re.sub(r"\s+", " ", (jd or "").lower())
    return {
        "positive": [p for p, rx in _POS_RE if _affirmed(rx, text)],
        "negative": [p for p, rx in _NEG_RE if rx.search(text)],
        "everify":  any(rx.search(text) for _, rx in _EV_RE),
    }


# ── H-1B database ────────────────────────────────────────────────────────────

class SponsorDB:
    """Read-only access to the imported LCA data."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._local = threading.local()

    @property
    def available(self) -> bool:
        return os.path.exists(self.path)

    def _conn(self) -> sqlite3.Connection:
        # One connection per thread: the agent runs in a worker thread
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            self._local.conn = conn
        return conn

    def status(self) -> dict:
        if not self.available:
            return {"available": False, "rows": 0, "fy_min": None, "fy_max": None}
        try:
            rows, fy_min, fy_max = self._conn().execute(
                "SELECT COUNT(*), MIN(fy), MAX(fy) FROM filings"
            ).fetchone()
            return {"available": True, "rows": rows, "fy_min": fy_min, "fy_max": fy_max}
        except sqlite3.Error:
            return {"available": False, "rows": 0, "fy_min": None, "fy_max": None}

    def _rows_for(self, norm: str) -> list:
        cur = self._conn().execute(
            "SELECT employer, job_title, wage, pw, fy, state FROM filings "
            "WHERE employer_norm = ? AND status LIKE 'CERTIFIED%'",
            (norm,),
        )
        rows = cur.fetchall()
        if rows or len(norm) < 3:   # "hp %" / "a %" would match unrelated employers
            return rows
        # Fall back to "Amazon" → "amazon com services", "amazon web services", …
        cur = self._conn().execute(
            "SELECT employer, job_title, wage, pw, fy, state FROM filings "
            "WHERE employer_norm LIKE ? AND status LIKE 'CERTIFIED%'",
            (norm + " %",),
        )
        return cur.fetchall()

    def lookup(self, company: str, title: str = "") -> dict | None:
        """Aggregate certified LCA filings for a company (and optionally a role)."""
        norm = normalize_company(company)
        if not norm or not self.available:
            return None
        try:
            rows = self._rows_for(norm)
        except sqlite3.Error:
            return None
        if not rows:
            return None

        by_year  = Counter(r[4] for r in rows if r[4])
        names    = Counter(r[0] for r in rows)
        wages    = [r[2] for r in rows if r[2]]
        titles   = Counter(display_title(r[1]) for r in rows if r[1])
        states   = Counter(r[5] for r in rows if r[5])

        result = {
            "company":        company,
            "employer_names": [n for n, _ in names.most_common(3)],
            "filings":        len(rows),
            "by_year":        dict(sorted(by_year.items())),
            "last_fy":        max(by_year) if by_year else None,
            "median_wage":    round(statistics.median(wages)) if wages else None,
            "top_titles":     titles.most_common(5),
            "top_states":     [s for s, _ in states.most_common(3)],
            "title_match":    None,
        }

        want = title_tokens(title)
        if want:
            hits = [r for r in rows if want <= title_tokens(r[1])]
            if hits:
                hw  = [r[2] for r in hits if r[2]]
                hpw = [r[3] for r in hits if r[3]]
                result["title_match"] = {
                    "query":        title,
                    "filings":      len(hits),
                    "median_wage":  round(statistics.median(hw)) if hw else None,
                    "median_pw":    round(statistics.median(hpw)) if hpw else None,
                }
        return result


_db = None


def get_db() -> SponsorDB:
    global _db
    if _db is None:
        _db = SponsorDB()
    return _db


# ── Verdict ──────────────────────────────────────────────────────────────────

def needs_sponsorship(profile: dict) -> bool:
    from user_profile import get_immigration_answers
    imm = get_immigration_answers(profile or {})
    return imm.get("sponsor_now") == "Yes" or imm.get("sponsor_future") == "Yes"


def assess(company: str, title: str, jd: str, profile: dict, db: SponsorDB = None) -> dict:
    """
    Combine H-1B history and JD language into one verdict:
      likely | possible | unlikely | unknown | not_needed
    """
    db      = db or get_db()
    signals = scan_jd(jd)
    h1b     = db.lookup(company, title) if db.available else None
    reasons = []

    if h1b:
        tm = h1b["title_match"]
        reasons.append(f"{h1b['filings']:,} certified H-1B filings (last FY{h1b['last_fy']})")
        if tm:
            reasons.append(f"{tm['filings']} for a matching role")
    elif db.available:
        reasons.append("No H-1B filings found under this name")
    else:
        reasons.append("H-1B data not loaded")

    if signals["negative"]:
        reasons.append(f"JD says: “{signals['negative'][0]}”")
    if signals["positive"]:
        reasons.append(f"JD says: “{signals['positive'][0]}”")
    if signals["everify"]:
        reasons.append("Employer mentions E-Verify (needed for STEM OPT)")

    if not needs_sponsorship(profile):
        verdict = "not_needed"
    elif signals["negative"]:
        verdict = "unlikely"
    elif signals["positive"]:
        verdict = "likely"
    elif h1b and (h1b["title_match"] or h1b["filings"] >= 10):
        verdict = "likely"
    elif h1b:
        verdict = "possible"
    else:
        verdict = "unknown"

    return {
        "verdict":  verdict,
        "label":    VERDICT_LABELS[verdict],
        "reasons":  reasons,
        "signals":  signals,
        "h1b":      h1b,
    }


# Sponsor filter modes (Settings → Visa): which verdicts get skipped
SKIP_VERDICTS = {
    "off":      set(),
    "unlikely": {"unlikely"},
    "strict":   {"unlikely", "unknown"},
}


def sponsor_gate(company: str, title: str, jd: str, profile: dict) -> tuple:
    """
    Returns (assessment, skip_reason). skip_reason is None when the job should
    proceed, else a short message for the activity feed.
    """
    try:
        spons = assess(company, title, jd, profile)
    except Exception as e:  # never let a data problem stop an application run
        spons = {"verdict": "unknown", "label": VERDICT_LABELS["unknown"],
                 "reasons": [f"Sponsorship check failed: {e}"], "signals": {}, "h1b": None}
    mode  = (profile or {}).get("preferences", {}).get("sponsor_filter", "unlikely")
    if spons["verdict"] in SKIP_VERDICTS.get(mode, set()):
        return spons, f"{spons['label']} — {spons['reasons'][-1]}"
    return spons, None


def compact(spons: dict) -> dict:
    """Small summary stored in the tracker alongside an application."""
    if not spons:
        return {}
    h1b = spons.get("h1b") or {}
    return {
        "verdict": spons.get("verdict"),
        "filings": h1b.get("filings", 0),
        "median_wage": (h1b.get("title_match") or {}).get("median_wage") or h1b.get("median_wage"),
    }
