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
def sponsor_db(tmp_path, lca_csv):
    from build_sponsor_db import build
    from sponsorship import SponsorDB
    out = str(tmp_path / "sponsors.db")
    build([lca_csv], out)
    return SponsorDB(out)


OPT_PROFILE = {"personal": {"name": "Test"}, "immigration": {"status": "F1-OPT"}}
USC_PROFILE = {"personal": {"name": "Test"}, "immigration": {"status": "USC"}}
