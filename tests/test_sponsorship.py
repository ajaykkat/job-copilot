from conftest import OPT_PROFILE, USC_PROFILE

from sponsorship import (SponsorDB, annualize, assess, normalize_company,
                         scan_jd, title_tokens)


def test_normalize_company_strips_suffixes_and_punctuation():
    assert normalize_company("Acme Software, Inc.") == "acme software"
    assert normalize_company("ACME SOFTWARE INC") == "acme software"
    assert normalize_company("The Tiny Co. LLC") == "tiny"
    assert normalize_company("AT&T Services") == "at and t services"
    # "America" is part of real names, not a suffix
    assert normalize_company("Bank of America, N.A.") == "bank of america"
    assert normalize_company("Initech, L.L.C.") == "initech"


def test_annualize_units_and_garbage():
    assert annualize("50", "Hour") == 104_000
    assert annualize("$120,000.00", "Year") == 120_000
    assert annualize("10000", "Month") == 120_000
    assert annualize("", "Year") is None
    assert annualize("12", "Year") is None          # obviously broken row
    assert annualize("100", "Fortnight") is None


def test_title_tokens_ignore_seniority():
    assert title_tokens("Sr. Software Engineer II") == {"software", "engineer"}


def test_scan_jd_is_whole_word():
    s = scan_jd("We offer many options. No options trading experience needed.")
    assert s["negative"] == []
    s = scan_jd("Unfortunately we cannot sponsor visas. US citizens only.")
    assert "cannot sponsor" in s["negative"] and "us citizens only" in s["negative"]
    s = scan_jd("H1B transfer welcome. Company participates in E-Verify.")
    assert s["positive"] == ["h1b transfer"] and s["everify"]
    # "no visa sponsorship available" must not count as positive-only
    s = scan_jd("There is no visa sponsorship available for this role.")
    assert s["negative"] and s["positive"] == []
    s = scan_jd("Note: we are not able to offer H-1B sponsorship.")
    assert s["positive"] == []


def test_lookup_aggregates_certified_filings(sponsor_db):
    h = sponsor_db.lookup("Acme Software", "Senior Software Engineer")
    assert h["filings"] == 12                      # denied row excluded
    assert h["by_year"] == {2024: 12}              # FY taken from filename
    assert h["title_match"]["filings"] == 3
    assert h["title_match"]["median_wage"] == 120_000
    assert h["title_match"]["median_pw"] == 100_000
    assert h["top_titles"][0] == ("Data Analyst", 9)


def test_lookup_prefix_fallback_and_miss(sponsor_db):
    assert sponsor_db.lookup("Globex")["filings"] == 1
    assert sponsor_db.lookup("Initech") is None


def test_lookup_without_db(tmp_path):
    db = SponsorDB(str(tmp_path / "missing.db"))
    assert not db.available
    assert db.lookup("Acme") is None
    assert db.status()["available"] is False


def test_verdicts(sponsor_db):
    jd = "Build things."
    assert assess("Acme Software", "Software Engineer", jd, OPT_PROFILE, sponsor_db)["verdict"] == "likely"
    assert assess("Tiny Co", "Product Manager", jd, OPT_PROFILE, sponsor_db)["verdict"] == "possible"
    assert assess("Tiny Co", "Java Developer", jd, OPT_PROFILE, sponsor_db)["verdict"] == "likely"
    assert assess("Initech", "Engineer", jd, OPT_PROFILE, sponsor_db)["verdict"] == "unknown"
    # JD language beats history
    no = assess("Acme Software", "Software Engineer", "We will not sponsor.", OPT_PROFILE, sponsor_db)
    assert no["verdict"] == "unlikely"
    yes = assess("Initech", "Engineer", "H-1B sponsorship available.", OPT_PROFILE, sponsor_db)
    assert yes["verdict"] == "likely"
    # Citizens don't need it
    assert assess("Initech", "Engineer", jd, USC_PROFILE, sponsor_db)["verdict"] == "not_needed"


def test_sponsor_gate_modes(monkeypatch, sponsor_db):
    import sponsorship
    monkeypatch.setattr(sponsorship, "_db", sponsor_db)

    def gate(mode, company, jd="Build things."):
        profile = {**OPT_PROFILE, "preferences": {"sponsor_filter": mode}}
        return sponsorship.sponsor_gate(company, "Engineer", jd, profile)[1]

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


def test_display_title_keeps_acronyms():
    from sponsorship import display_title
    assert display_title("SR. QA ANALYST") == "Sr. QA Analyst"
    assert display_title("QA Analyst") == "QA Analyst"
    assert display_title("SOFTWARE ENGINEER  II") == "Software Engineer II"


def test_short_names_do_not_prefix_match(sponsor_db):
    assert sponsor_db.lookup("Ac") is None
