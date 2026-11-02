import io

import pytest
from openpyxl import Workbook

from mechman_bot.campaigns import parse_recipient_file, render_parameters


def test_csv_import_detects_phone_and_preserves_personalization_columns() -> None:
    result = parse_recipient_file(
        "recipients.csv",
        b"Customer Name,Mobile,City\nAsha,+91 98765 43210,Vadodara\nDev,919999999999,Surat\n",
    )
    assert result["phone_column"] == "Mobile"
    assert result["valid_phone_count"] == 2
    assert result["rows"][0]["Customer Name"] == "Asha"


def test_xlsx_import_and_case_insensitive_parameter_mapping() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Phone", "Name", "Product"])
    sheet.append([919876543210, "Asha", "PowerMill"])
    content = io.BytesIO()
    workbook.save(content)

    result = parse_recipient_file("recipients.xlsx", content.getvalue())
    assert result["row_count"] == 1
    assert result["phone_column"] == "Phone"
    assert render_parameters(["name", "PRODUCT"], result["rows"][0]) == [
        "Asha",
        "PowerMill",
    ]


def test_parameter_mapping_rejects_missing_values() -> None:
    with pytest.raises(ValueError, match="Missing value"):
        render_parameters(["name", "city"], {"name": "Asha", "city": ""})
