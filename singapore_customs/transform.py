"""Normalize raw TableBuilder rows into flat records with separate HS code, description and unit."""

from decimal import Decimal, InvalidOperation
from typing import TypedDict

from singapore_customs.api import from_api_period

# Regional groupings published next to the countries. Allowlisted here because the API does not
# flag them: a new group published by SingStat would be reported as a country until added.
AGGREGATE_PARTNERS = frozenset(
    {
        "WORLD",
        "APEC",
        "ASEAN",
        "CARRIBBEAN",
        "CENTRAL ASIA",
        "CLMV",
        "EAST ASIA + TAIWAN",
        "EUROPEAN UNION",
        "GCC",
        "LATIN AMERICA",
        "MIDDLE EAST",
        "NAFTA",
        "SOUTH ASIA",
    }
)
HS_COLUMNS = {2: "hs2Products", 4: "hs4Products", 6: "hs6Products", 8: "hs8Products"}
UNIT_CODE_LENGTH = 3
# Unit of the value table as reported by the API metadata, and as written in the output.
SOURCE_VALUE_UNIT = "Thousand Dollars"
VALUE_UNIT = "THOUSAND SGD"


class ValueRecord(TypedDict):
    """One row of the value table."""

    period: str
    trade_type: str
    partner: str
    partner_is_aggregate: bool
    hs_level: int
    hs_code: str
    hs_description: str
    value: Decimal | None
    value_unit: str
    quantity_unit: str | None


class QuantityRecord(TypedDict):
    """One row of the quantity table."""

    period: str
    trade_type: str
    partner: str
    partner_is_aggregate: bool
    hs_code: str
    hs_description: str
    quantity: Decimal | None
    quantity_unit: str | None


VALUE_COLUMNS = list(ValueRecord.__annotations__)
QUANTITY_COLUMNS = list(QuantityRecord.__annotations__)


def split_hs_label(label: str) -> tuple[str, str, str | None]:
    """Split ``"01012100 - PURE BRED BREEDING HORSES (NMB)"`` into code, description and unit.

    HS8 labels end with a UN/ECE unit code in parentheses; other levels and a few special
    codes have none, in which case the unit is ``None``.
    """
    code, separator, description = label.partition(" - ")
    if not separator or not code.isdigit():
        msg = f"unexpected HS label {label!r}"
        raise ValueError(msg)

    unit = None
    head, _, tail = description.rpartition(" (")
    candidate = tail.removesuffix(")")
    if head and tail.endswith(")") and len(candidate) == UNIT_CODE_LENGTH and candidate.isupper():
        description, unit = head, candidate
    return code, description, unit


def parse_amount(text: str) -> Decimal | None:
    """Parse an API amount, keeping its exact decimal value. Empty or ``na`` means missing."""
    if text.strip().lower() in {"", "na", "-"}:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation as error:
        msg = f"unexpected amount {text!r}"
        raise ValueError(msg) from error


def hs_level_of(row: dict[str, str]) -> int:
    """Return the HS level (2, 4, 6 or 8) of a value-table row: its deepest non-empty HS column."""
    return max(level for level, column in HS_COLUMNS.items() if row[column])


def normalize_value_row(row: dict[str, str]) -> ValueRecord:
    """Normalize one row of the value table (T010001)."""
    level = hs_level_of(row)
    code, description, unit = split_hs_label(row[HS_COLUMNS[level]])
    return ValueRecord(
        period=from_api_period(row["period"]),
        trade_type=row["tradeType"],
        partner=row["market"],
        partner_is_aggregate=row["market"] in AGGREGATE_PARTNERS,
        hs_level=level,
        hs_code=code,
        hs_description=description,
        value=parse_amount(row["value"]),
        value_unit=VALUE_UNIT,
        quantity_unit=unit,
    )


def normalize_quantity_row(row: dict[str, str]) -> QuantityRecord:
    """Normalize one row of the quantity table (T010002), which only has HS8 codes."""
    code, description, unit = split_hs_label(row["hs8Products"])
    return QuantityRecord(
        period=from_api_period(row["period"]),
        trade_type=row["tradeType"],
        partner=row["market"],
        partner_is_aggregate=row["market"] in AGGREGATE_PARTNERS,
        hs_code=code,
        hs_description=description,
        quantity=parse_amount(row["quantity"]),
        quantity_unit=unit,
    )
