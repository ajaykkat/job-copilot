from datetime import datetime

from openpyxl import Workbook

from conftest import HEADER


def test_xlsx_import_with_fiscal_year_from_decision_date(tmp_path):
    from build_sponsor_db import build
    from sponsorship import SponsorDB

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

    out = tmp_path / "s.db"
    assert build([str(src)], str(out)) == 2  # row with blank employer dropped

    h = SponsorDB(str(out)).lookup("initrode")
    assert h["filings"] == 2
    assert h["by_year"] == {2023: 1, 2024: 1}
    assert h["median_wage"] == 127_400       # median(130000, 60*2080)
    assert h["top_states"] == ["CA"]
