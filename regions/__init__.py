"""
Country packs.

  get_region("GB")            → the United Kingdom pack
  detect_country("Leeds, England, United Kingdom")  → "GB"
  list_regions()              → every supported country, data-backed first

Adding a country with public employer data: subclass DataRegion (see us.py /
uk.py) and register it below. Countries without data still work — their
verdicts come from the job post's wording.
"""

import re

from regions.base import Region
from regions.uk import UnitedKingdom
from regions.us import US_STATES, UnitedStates


def _simple(code, name, currency, *aliases):
    return type(f"Region{code}", (Region,), {
        "code": code, "name": name, "currency": currency, "aliases": aliases,
    })()


_REGIONS = {r.code: r for r in [
    UnitedStates(),
    UnitedKingdom(),
    _simple("CA", "Canada", "CAD"),
    _simple("IE", "Ireland", "EUR"),
    _simple("DE", "Germany", "EUR", "deutschland"),
    _simple("NL", "Netherlands", "EUR", "the netherlands", "nederland"),
    _simple("FR", "France", "EUR"),
    _simple("IN", "India", "INR"),
    _simple("SG", "Singapore", "SGD"),
    _simple("AE", "United Arab Emirates", "AED", "uae", "dubai", "abu dhabi"),
    _simple("AU", "Australia", "AUD"),
    _simple("JP", "Japan", "JPY"),
    _simple("PH", "Philippines", "PHP"),
    _simple("NG", "Nigeria", "NGN"),
    _simple("BR", "Brazil", "BRL", "brasil"),
]}

DEFAULT_COUNTRY = "US"


def get_region(code: str) -> Region:
    return _REGIONS.get((code or "").upper()) or _REGIONS[DEFAULT_COUNTRY]


def is_supported(code: str) -> bool:
    return (code or "").upper() in _REGIONS


def list_regions() -> list:
    return sorted(_REGIONS.values(), key=lambda r: (r.data_source is None, r.name))


def _alias_patterns():
    pats = []
    for r in _REGIONS.values():
        for a in (r.name.lower(), *r.aliases):
            pats.append((r.code, re.compile(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])")))
    return pats


_PATTERNS = _alias_patterns()
_US_STATE = re.compile(r",\s*(" + "|".join(sorted(US_STATES)) + r")\b(?:\s+\d{5})?\s*(?:\(|$|,)")


def detect_country(location: str, default: str = None) -> str | None:
    """
    Country code for a job location string, e.g.
      "Bengaluru, Karnataka, India" → "IN",  "Austin, TX" → "US".
    The match closest to the end wins (locations run city → country).
    """
    loc = (location or "").strip()
    if not loc:
        return default
    low = loc.lower()
    best, best_pos = None, -1
    for code, rx in _PATTERNS:
        for m in rx.finditer(low):
            if m.start() > best_pos:
                best, best_pos = code, m.start()
    if best:
        return best
    if _US_STATE.search(loc):
        return "US"
    return default
