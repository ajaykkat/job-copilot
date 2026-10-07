"""
Sponsorship intelligence — "can this employer hire me where the job is?"

Two signals, combined into one verdict per job:
  1. Employer evidence from the job's country pack (regions/): US H-1B
     filings, the UK sponsor register, … imported locally by
     scripts/build_sponsor_db.py.
  2. The job description itself — explicit "will sponsor" / "no sponsorship"
     language, plus E-Verify mentions (US STEM OPT).

Everything here is offline and fast; no API calls.
"""

import re

from regions import DEFAULT_COUNTRY, detect_country, get_region

POSITIVE_JD = [
    "will sponsor", "sponsorship available", "visa sponsorship available",
    "sponsorship is available", "visa sponsorship provided", "sponsorship provided",
    "open to sponsorship", "can sponsor", "willing to sponsor", "we sponsor",
    "relocation and visa support", "visa support", "work permit support",
    "h1b sponsorship", "h-1b sponsorship", "h1b transfer", "h-1b transfer",
    "opt/cpt", "opt candidates", "stem opt", "f1 opt", "f-1 opt",
    "skilled worker visa sponsorship", "certificate of sponsorship",
    "blue card", "eu blue card", "lmia",
]

NEGATIVE_JD = [
    "no sponsorship", "no visa sponsorship", "cannot sponsor", "can not sponsor",
    "will not sponsor", "won't sponsor", "unable to sponsor", "not able to sponsor",
    "sponsorship not available", "sponsorship is not available",
    "not offering sponsorship", "does not sponsor", "do not sponsor",
    "without sponsorship", "without the need for sponsorship",
    "without requiring sponsorship", "no visa support",
    "must have the right to work", "must already have the right to work",
    "must have existing right to work", "must be eligible to work in",
    "citizens only", "citizenship required", "must be a citizen",
    "us citizens only", "u.s. citizens only", "must be a us citizen", "must be a u.s. citizen",
    "gc or us citizen", "green card or us citizen", "usc or gc", "usc/gc", "gc/usc",
    "no h1b", "no h-1b", "no opt", "no cpt", "no c2c",
    "security clearance required", "active clearance",
]

EVERIFY_JD = ["e-verify", "everify", "e verify"]

VERDICT_LABELS = {
    "likely":     "Sponsors",
    "possible":   "May sponsor",
    "unlikely":   "Won't sponsor",
    "unknown":    "No record",
    "not_needed": "Not needed",
}


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


# ── Who needs sponsorship where ──────────────────────────────────────────────

def job_country(profile: dict, location: str = "", country: str = None) -> str:
    """Explicit country > country detected from the job location > profile default."""
    if country:
        return get_region(country).code
    default = (profile or {}).get("preferences", {}).get("job_country") or DEFAULT_COUNTRY
    return detect_country(location, default=get_region(default).code)


def needs_sponsorship(profile: dict, country: str = DEFAULT_COUNTRY) -> bool:
    region = get_region(country)
    imm = (profile or {}).get("immigration", {})
    allowed = {str(c).upper() for c in imm.get("authorized_countries") or []}
    if region.code in allowed:
        return False
    if region.authorized_by_status(profile) is True:
        return False
    return True


# ── Verdict ──────────────────────────────────────────────────────────────────

def assess(company: str, title: str, jd: str, profile: dict,
           location: str = "", country: str = None, region=None) -> dict:
    """
    Combine the country's employer data and the job post's wording into one verdict:
      likely | possible | unlikely | unknown | not_needed
    """
    region   = region or get_region(job_country(profile, location, country))
    signals  = scan_jd(jd)
    evidence = region.lookup(company, title)
    reasons  = list(evidence["reasons"]) if evidence else [region.not_found_reason()]

    if signals["negative"]:
        reasons.append(f"Job post says: “{signals['negative'][0]}”")
    if signals["positive"]:
        reasons.append(f"Job post says: “{signals['positive'][0]}”")
    if signals["everify"] and region.code == "US":
        reasons.append("Employer mentions E-Verify (needed for STEM OPT)")

    if not needs_sponsorship(profile, region.code):
        verdict = "not_needed"
    elif signals["negative"]:
        verdict = "unlikely"
    elif signals["positive"]:
        verdict = "likely"
    elif evidence:
        verdict = "likely" if evidence["strength"] == "strong" else "possible"
    else:
        verdict = "unknown"

    return {
        "verdict":  verdict,
        "label":    VERDICT_LABELS[verdict],
        "reasons":  reasons,
        "signals":  signals,
        "country":  {"code": region.code, "name": region.name, "currency": region.currency},
        "source":   region.data_source,
        "evidence": evidence,
    }


# Sponsor filter modes (Settings → Visa): which verdicts get skipped
SKIP_VERDICTS = {
    "off":      set(),
    "unlikely": {"unlikely"},
    "strict":   {"unlikely", "unknown"},
}


def sponsor_gate(company: str, title: str, jd: str, profile: dict, location: str = "") -> tuple:
    """
    Returns (assessment, skip_reason). skip_reason is None when the job should
    proceed, else a short message for the activity feed.
    """
    try:
        spons = assess(company, title, jd, profile, location=location)
    except Exception as e:  # never let a data problem stop an application run
        spons = {"verdict": "unknown", "label": VERDICT_LABELS["unknown"],
                 "reasons": [f"Sponsorship check failed: {e}"], "signals": {},
                 "country": None, "source": None, "evidence": None}
    mode = (profile or {}).get("preferences", {}).get("sponsor_filter", "unlikely")
    if spons["verdict"] in SKIP_VERDICTS.get(mode, set()):
        return spons, f"{spons['label']} — {spons['reasons'][-1]}"
    return spons, None


def compact(spons: dict) -> dict:
    """Small summary stored in the tracker alongside an application."""
    if not spons:
        return {}
    ev = spons.get("evidence") or {}
    return {
        "verdict": spons.get("verdict"),
        "country": (spons.get("country") or {}).get("code"),
        "summary": ev.get("summary", ""),
        "pay":     ev.get("pay"),
    }
