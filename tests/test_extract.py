import csv
from pathlib import Path

import pytest

from singapore_customs.extract import merge_month, table_path, write_csv_atomically
from singapore_customs.transform import QUANTITY_COLUMNS, VALUE_COLUMNS


def value_row(hs_code: str, value: str, unit: str = "KGM") -> dict[str, str]:
    return {
        "period": "2026-09",
        "trade_type": "IMPORTS",
        "partner": "JAPAN",
        "partner_is_aggregate": "False",
        "hs_level": str(len(hs_code)),
        "hs_code": hs_code,
        "hs_description": f"PRODUCT {hs_code}",
        "value": value,
        "value_unit": "THOUSAND SGD",
        "quantity_unit": unit if len(hs_code) == 8 else "",
    }


def quantity_row(hs_code: str, quantity: str, unit: str = "KGM") -> dict[str, str]:
    return {
        "period": "2026-09",
        "trade_type": "IMPORTS",
        "partner": "JAPAN",
        "partner_is_aggregate": "False",
        "hs_code": hs_code,
        "hs_description": f"PRODUCT {hs_code}",
        "quantity": quantity,
        "quantity_unit": unit,
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_write_csv_atomically_leaves_no_part_file(tmp_path: Path) -> None:
    path = tmp_path / "value" / "value_2026-09.csv"

    count = write_csv_atomically(path, VALUE_COLUMNS, [value_row("01", "5")])

    assert count == 1
    assert read_rows(path) == [value_row("01", "5")]
    assert list(path.parent.iterdir()) == [path]


def test_merge_month_full_outer_join_on_hs8(tmp_path: Path) -> None:
    write_csv_atomically(
        table_path(tmp_path, "value", "2026-09"),
        VALUE_COLUMNS,
        [value_row("01", "100"), value_row("01012900", "95"), value_row("02011000", "40")],
    )
    write_csv_atomically(
        table_path(tmp_path, "quantity", "2026-09"),
        QUANTITY_COLUMNS,
        [quantity_row("01012900", "7"), quantity_row("03011100", "12")],
    )

    count = merge_month(tmp_path, "2026-09")

    assert count == 3
    common = {"period": "2026-09", "trade_type": "IMPORTS", "partner": "JAPAN"}
    assert read_rows(table_path(tmp_path, "merged", "2026-09")) == [
        {
            **common,
            "partner_is_aggregate": "False",
            "hs_code": "01012900",
            "hs_description": "PRODUCT 01012900",
            "value": "95",
            "value_unit": "THOUSAND SGD",
            "quantity": "7",
            "quantity_unit": "KGM",
        },
        {
            **common,
            "partner_is_aggregate": "False",
            "hs_code": "02011000",
            "hs_description": "PRODUCT 02011000",
            "value": "40",
            "value_unit": "THOUSAND SGD",
            "quantity": "",
            "quantity_unit": "KGM",
        },
        {
            **common,
            "partner_is_aggregate": "False",
            "hs_code": "03011100",
            "hs_description": "PRODUCT 03011100",
            "value": "",
            "value_unit": "THOUSAND SGD",
            "quantity": "12",
            "quantity_unit": "KGM",
        },
    ]


def test_merge_month_rejects_unit_mismatch(tmp_path: Path) -> None:
    write_csv_atomically(
        table_path(tmp_path, "value", "2026-09"), VALUE_COLUMNS, [value_row("01012900", "95")]
    )
    write_csv_atomically(
        table_path(tmp_path, "quantity", "2026-09"),
        QUANTITY_COLUMNS,
        [quantity_row("01012900", "7", unit="NMB")],
    )

    with pytest.raises(ValueError, match="quantity unit mismatch"):
        merge_month(tmp_path, "2026-09")
