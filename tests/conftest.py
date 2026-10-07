import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# Column layout of the DOL LCA disclosure files (subset the importer reads)
HEADER = ["CASE_STATUS", "DECISION_DATE", "VISA_CLASS", "JOB_TITLE", "SOC_TITLE",
          "EMPLOYER_NAME", "WORKSITE_STATE", "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY",
          "PREVAILING_WAGE", "PW_UNIT_OF_PAY", "PW_WAGE_LEVEL"]

ROWS = [
    # Acme Software: 12 certified filings, 3 for "Software Engineer"
    *[["Certified", "2024-03-01", "H-1B", "Software Engineer", "Software Developers",
       "Acme Software, Inc.", "TX", "120000", "Year", "100000", "Year", "II"] for _ in range(3)],
    *[["Certified", "2023-11-15", "H-1B", "Data Analyst", "Data Scientists",
       "ACME SOFTWARE INC", "TX", "50", "Hour", "45", "Hour", "I"] for _ in range(9)],
    ["Denied", "2024-01-10", "H-1B", "Software Engineer", "Software Developers",
     "Acme Software Inc.", "TX", "90000", "Year", "100000", "Year", "I"],
    # Tiny Co: 2 filings
    *[["Certified", "2024-05-01", "H-1B", "Java Developer", "Software Developers",
       "Tiny Co LLC", "NJ", "95000", "Year", "88000", "Year", "II"] for _ in range(2)],
    # Prefix-match family: "Globex" → "Globex Cloud Services LLC"
    ["Certified", "2024-02-02", "H-1B", "Senior Software Engineer", "Software Developers",
     "Globex Cloud Services LLC", "WA", "150000", "Year", "130000", "Year", "III"],
]


@pytest.fixture
def lca_csv(tmp_path):
    path = tmp_path / "LCA_Disclosure_Data_FY2024_Q4.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(ROWS)
    return str(path)


@pytest.fixture
def us_region(tmp_path, lca_csv):
    from build_sponsor_db import build
    from regions.us import UnitedStates
    out = str(tmp_path / "us.db")
    build("US", [lca_csv], out)
    return UnitedStates(out)


UK_HEADER = ["Organisation Name", "Town/City", "County", "Type & Rating", "Route"]
UK_ROWS = [
    ["Globex Software Ltd", "London", "", "Worker (A rating)", "Skilled Worker"],
    ["Globex Software Ltd", "London", "", "Worker (A rating)", "Global Business Mobility: Senior or Specialist Worker"],
    ["Hooli Music Limited", "Leeds", "West Yorkshire", "Temporary Worker (A rating)", "Creative Worker"],
]


@pytest.fixture
def uk_region(tmp_path):
    from build_sponsor_db import build
    from regions.uk import UnitedKingdom
    src = tmp_path / "Worker_and_Temporary_Worker.csv"
    with open(src, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(UK_HEADER)
        w.writerows(UK_ROWS)
    out = str(tmp_path / "gb.db")
    build("GB", [str(src)], out)
    return UnitedKingdom(out)


@pytest.fixture
def regions_with_data(monkeypatch, us_region, uk_region):
    """Swap the registry's US and GB packs for ones backed by the test data."""
    import regions
    monkeypatch.setitem(regions._REGIONS, "US", us_region)
    monkeypatch.setitem(regions._REGIONS, "GB", uk_region)
    return regions


OPT_PROFILE = {"personal": {"name": "Test"}, "immigration": {"status": "F1-OPT"}}
USC_PROFILE = {"personal": {"name": "Test"}, "immigration": {"status": "USC"}}
# Can work in India without a visa, searching UK jobs
IN_PROFILE  = {"personal": {"name": "Test"},
               "immigration": {"authorized_countries": ["IN"]},
               "preferences": {"job_country": "GB"}}
