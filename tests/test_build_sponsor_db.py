from datetime import datetime

import pytest
from openpyxl import Workbook

from conftest import HEADER


def test_us_xlsx_import_with_fiscal_year_from_decision_date(tmp_path):
    from build_sponsor_db import build
    from regions.us import UnitedStates

    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    # Oct 2023 decision → FY2024; Sep 2023 → FY2023
    ws.append(["Certified", datetime(2023, 10, 5), "H-1B", "Software Engineer", "", "Initrode LLC",
               "ca", 130000, "Year", 120000, "Year", "III"])
    ws.append(["Certified - Withdrawn", datetime(2023, 9, 5), "H-1B", "QA Engineer", "", "Initrode, L.L.C.",
               "CA", 60, "Hour", 50, "Hour", "II"])
    ws.append(["Certified", datetime(2023, 9, 5), "H-1B", "QA Engineer", "", "", "CA", 1, "Year", 1, "Year", ""])
    src = tmp_path / "lca_export.xlsx"   # no FYxxxx in the name
    wb.save(src)

    out = tmp_path / "us.db"
    assert build("US", [str(src)], str(out)) == 2  # row with blank employer dropped

    region = UnitedStates(str(out))
    ev = region.lookup("initrode")
    assert ev["summary"] == "2 H-1B filings"
    assert ev["chart"]["bars"] == [["FY23", 1], ["FY24", 1]]
    assert ev["pay"] == "$127k"                    # median(130000, 60*2080)
    assert region.status()["detail"] == "FY2023–2024"


def test_build_rejects_countries_without_data(tmp_path):
    from build_sponsor_db import build
    with pytest.raises(SystemExit):
        build("DE", [], str(tmp_path / "x.db"))
    with pytest.raises(SystemExit):
        build("ZZ", [], str(tmp_path / "x.db"))
