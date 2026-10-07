from conftest import IN_PROFILE, OPT_PROFILE, USC_PROFILE

from regions import detect_country, get_region
from regions.base import money, normalize_company
from regions.us import UnitedStates, annualize, display_title, title_tokens
from sponsorship import assess, needs_sponsorship, scan_jd


def test_normalize_company_strips_suffixes_and_punctuation():
    assert normalize_company("Acme Software, Inc.") == "acme software"
    assert normalize_company("ACME SOFTWARE INC") == "acme software"
    assert normalize_company("The Tiny Co. LLC") == "tiny"
    assert normalize_company("AT&T Services") == "at and t services"
    assert normalize_company("Bank of America, N.A.") == "bank of america"
    assert normalize_company("Initech, L.L.C.") == "initech"
    assert normalize_company("Globex Software Ltd") == "globex software"
    assert normalize_company("Siemens GmbH") == "siemens"
    assert normalize_company("Infosys Pvt. Ltd.") == "infosys"


def test_money_uses_country_currency():
    assert money(133_000, "USD") == "$133k"
    assert money(45_400, "GBP") == "£45k"
    assert money(None, "USD") == "–"


def test_annualize_units_and_garbage():
    assert annualize("50", "Hour") == 104_000
    assert annualize("$120,000.00", "Year") == 120_000
    assert annualize("10000", "Month") == 120_000
    assert annualize("", "Year") is None
    assert annualize("12", "Year") is None          # obviously broken row
    assert annualize("100", "Fortnight") is None


def test_title_helpers():
    assert title_tokens("Sr. Software Engineer II") == {"software", "engineer"}
    assert display_title("SR. QA ANALYST") == "Sr. QA Analyst"
    assert display_title("QA Analyst") == "QA Analyst"
    assert display_title("SOFTWARE ENGINEER  II") == "Software Engineer II"


def test_detect_country():
    assert detect_country("Bengaluru, Karnataka, India") == "IN"
    assert detect_country("London, England, United Kingdom") == "GB"
    assert detect_country("Remote (UK)") == "GB"
    assert detect_country("Austin, TX") == "US"
    assert detect_country("Austin, TX 78701") == "US"
    assert detect_country("New York, United States (Hybrid)") == "US"
    assert detect_country("Dubai, UAE") == "AE"
    assert detect_country("Toronto, Ontario, Canada") == "CA"
    assert detect_country("Berlin, Deutschland") == "DE"
    # last match wins: city named like a country, then the real country
    assert detect_country("Georgetown, Texas, United States") == "US"
    assert detect_country("Remote", default="GB") == "GB"
    assert detect_country("", default="US") == "US"
    # English words that are not countries
    assert detect_country("Join us in building", default=None) is None


def test_scan_jd_is_whole_word_and_handles_negation():
    assert scan_jd("We offer many options. No options trading experience needed.")["negative"] == []
    s = scan_jd("Unfortunately we cannot sponsor visas. US citizens only.")
    assert "cannot sponsor" in s["negative"] and "us citizens only" in s["negative"]
    s = scan_jd("H1B transfer welcome. Company participates in E-Verify.")
    assert s["positive"] == ["h1b transfer"] and s["everify"]
    s = scan_jd("There is no visa sponsorship available for this role.")
    assert s["negative"] and s["positive"] == []
    assert scan_jd("Note: we are not able to offer H-1B sponsorship.")["positive"] == []
    assert scan_jd("Applicants must have the right to work in the UK.")["negative"]
    assert scan_jd("We offer relocation and visa support.")["positive"] == ["relocation and visa support", "visa support"]


def test_us_lookup_aggregates_certified_filings(us_region):
    ev = us_region.lookup("Acme Software", "Senior Software Engineer")
    assert ev["summary"] == "12 H-1B filings"         # denied row excluded
    assert ev["chart"]["bars"] == [["FY24", 12]]      # FY taken from filename
    assert {"value": "3", "label": "for this role"} in ev["stats"]
    assert {"value": "$120k", "label": "median pay, role"} in ev["stats"]
    assert {"value": "$100k", "label": "prevailing wage"} in ev["stats"]
    assert ev["table"]["rows"][0] == ["Data Analyst", 9]
    assert ev["strength"] == "strong"


def test_us_lookup_prefix_fallback_and_misses(us_region, tmp_path):
    assert us_region.lookup("Globex")["summary"] == "1 H-1B filings"
    assert us_region.lookup("Initech") is None
    assert us_region.lookup("Ac") is None                  # too short to prefix-match
    missing = UnitedStates(str(tmp_path / "missing.db"))
    assert missing.lookup("Acme") is None
    assert missing.status()["available"] is False and missing.status()["has_data"] is True


def test_uk_lookup(uk_region):
    ev = uk_region.lookup("Globex Software Limited")
    assert ev["strength"] == "strong"
    assert "Licensed for Skilled Worker visas" in ev["reasons"]
    hooli = uk_region.lookup("Hooli Music")
    assert hooli["strength"] == "some" and "Creative Worker" in hooli["reasons"][1]
    assert uk_region.lookup("Initech") is None
    assert uk_region.status()["detail"] == "2 licensed employers"


def test_needs_sponsorship_per_country():
    assert needs_sponsorship(OPT_PROFILE, "US")
    assert not needs_sponsorship(USC_PROFILE, "US")
    assert needs_sponsorship(USC_PROFILE, "GB")          # US citizenship ≠ UK work rights
    assert not needs_sponsorship(IN_PROFILE, "IN")
    assert needs_sponsorship(IN_PROFILE, "GB")
    assert needs_sponsorship({}, "DE")


def test_verdicts_us(regions_with_data):
    jd = "Build things."
    v = lambda co, t, jd=jd, p=OPT_PROFILE: assess(co, t, jd, p, location="Austin, TX")["verdict"]
    assert v("Acme Software", "Software Engineer") == "likely"
    assert v("Tiny Co", "Product Manager") == "possible"
    assert v("Tiny Co", "Java Developer") == "likely"
    assert v("Initech", "Engineer") == "unknown"
    assert v("Acme Software", "Software Engineer", "We will not sponsor.") == "unlikely"
    assert v("Initech", "Engineer", "H-1B sponsorship available.") == "likely"
    assert v("Initech", "Engineer", p=USC_PROFILE) == "not_needed"


def test_verdicts_follow_the_job_location(regions_with_data):
    # Same employer name, but the job is in the UK → UK register decides
    a = assess("Globex Software", "Engineer", "", IN_PROFILE, location="London, United Kingdom")
    assert a["country"]["code"] == "GB" and a["verdict"] == "likely"
    assert a["source"] == "UK Register of Licensed Sponsors"
    # Location unknown → profile's job_country (GB)
    assert assess("Initech", "Engineer", "", IN_PROFILE)["country"]["code"] == "GB"
    # India job for someone who can already work in India
    assert assess("Initech", "Engineer", "", IN_PROFILE, location="Pune, India")["verdict"] == "not_needed"
    # A country without data falls back to the job post's wording
    de = assess("Initech", "Engineer", "EU Blue Card sponsorship offered.", IN_PROFILE, location="Berlin, Germany")
    assert de["verdict"] == "likely" and de["evidence"] is None
    assert de["reasons"][0].startswith("No sponsorship data for Germany yet")


def test_sponsor_gate_modes(regions_with_data):
    import sponsorship

    def gate(mode, company, jd="Build things."):
        profile = {**OPT_PROFILE, "preferences": {"sponsor_filter": mode}}
        return sponsorship.sponsor_gate(company, "Engineer", jd, profile, location="Austin, TX")[1]

    assert gate("off", "Acme", "We cannot sponsor.") is None
    assert gate("unlikely", "Acme", "We cannot sponsor.")
    assert gate("unlikely", "Initech") is None
    assert gate("strict", "Initech")
    assert gate("strict", "Acme Software") is None


def test_sponsor_gate_never_raises(monkeypatch):
    import sponsorship

    def boom(*a, **k):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(sponsorship, "assess", boom)
    spons, skip = sponsorship.sponsor_gate("X", "Y", "Z", {"preferences": {"sponsor_filter": "unlikely"}})
    assert spons["verdict"] == "unknown" and skip is None


def test_compact_summary(regions_with_data):
    from sponsorship import compact
    c = compact(assess("Acme Software", "Software Engineer", "", OPT_PROFILE, location="Austin, TX"))
    assert c == {"verdict": "likely", "country": "US", "summary": "12 H-1B filings", "pay": "$120k"}


def test_every_region_is_usable():
    from regions import list_regions
    for r in list_regions():
        info = r.info()
        assert info["code"] and info["name"] and info["currency"]
        assert get_region(r.code) is r
    # data-backed countries are listed first
    assert [r.code for r in list_regions()][:2] == ["GB", "US"]
