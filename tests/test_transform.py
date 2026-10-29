from decimal import Decimal

import pytest

from singapore_customs.transform import (
    QuantityRecord,
    ValueRecord,
    normalize_quantity_row,
    normalize_value_row,
    parse_amount,
    split_hs_label,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (
            "01012100 - PURE BRED BREEDING HORSES (NMB)",
            ("01012100", "PURE BRED BREEDING HORSES", "NMB"),
        ),
        ("01 - LIVE ANIMALS", ("01", "LIVE ANIMALS", None)),
        ("98920022 - TRADE SAMPLES", ("98920022", "TRADE SAMPLES", None)),
        (
            "12345678 - WOOD (EXCL. BAMBOO) - OTHER (KGM)",
            ("12345678", "WOOD (EXCL. BAMBOO) - OTHER", "KGM"),
        ),
        ("12345678 - ARTICLES (OTHER)", ("12345678", "ARTICLES (OTHER)", None)),
    ],
)
def test_split_hs_label(label: str, expected: tuple[str, str, str | None]) -> None:
    assert split_hs_label(label) == expected


@pytest.mark.parametrize("label", ["LIVE ANIMALS", "AB - LIVE ANIMALS"])
def test_split_hs_label_rejects_unexpected_label(label: str) -> None:
    with pytest.raises(ValueError, match="unexpected HS label"):
        split_hs_label(label)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("23515", Decimal(23515)),
        ("1.25", Decimal("1.25")),
        ("1,234", Decimal(1234)),
        ("", None),
        ("na", None),
        ("-", None),
    ],
)
def test_parse_amount(text: str, expected: Decimal | None) -> None:
    assert parse_amount(text) == expected


def test_parse_amount_rejects_text() -> None:
    with pytest.raises(ValueError, match="unexpected amount"):
        parse_amount("abc")


def test_normalize_value_row_uses_deepest_hs_level() -> None:
    row = {
        "hs2Products": "01 - LIVE ANIMALS",
        "hs4Products": "0101 - LIVE HORSES ASSES MULES & HINNIES",
        "hs6Products": "010129 - OTHER LIVE HORSES",
        "hs8Products": "01012900 - OTHER LIVE HORSES (NMB)",
        "market": "JAPAN",
        "tradeType": "IMPORTS",
        "period": "2026 Sep",
        "value": "95",
    }

    assert normalize_value_row(row) == ValueRecord(
        period="2026-09",
        trade_type="IMPORTS",
        partner="JAPAN",
        partner_is_aggregate=False,
        hs_level=8,
        hs_code="01012900",
        hs_description="OTHER LIVE HORSES",
        value=Decimal(95),
        value_unit="THOUSAND SGD",
        quantity_unit="NMB",
    )


def test_normalize_value_row_hs2_aggregate_partner() -> None:
    row = {
        "hs2Products": "01 - LIVE ANIMALS",
        "hs4Products": "",
        "hs6Products": "",
        "hs8Products": "",
        "market": "WORLD",
        "tradeType": "DOMESTIC EXPORTS",
        "period": "2026 Jan",
        "value": "63",
    }

    assert normalize_value_row(row) == ValueRecord(
        period="2026-01",
        trade_type="DOMESTIC EXPORTS",
        partner="WORLD",
        partner_is_aggregate=True,
        hs_level=2,
        hs_code="01",
        hs_description="LIVE ANIMALS",
        value=Decimal(63),
        value_unit="THOUSAND SGD",
        quantity_unit=None,
    )


def test_normalize_quantity_row() -> None:
    row = {
        "hs8Products": "01012900 - OTHER LIVE HORSES (NMB)",
        "market": "ASEAN",
        "tradeType": "RE-EXPORTS",
        "period": "2026 Sep",
        "quantity": "7",
    }

    assert normalize_quantity_row(row) == QuantityRecord(
        period="2026-09",
        trade_type="RE-EXPORTS",
        partner="ASEAN",
        partner_is_aggregate=True,
        hs_code="01012900",
        hs_description="OTHER LIVE HORSES",
        quantity=Decimal(7),
        quantity_unit="NMB",
    )
