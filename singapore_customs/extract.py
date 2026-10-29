"""Run an extraction: download each configured table for each month and write CSV files."""

import csv
import json
import logging
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import requests

from singapore_customs.api import fetch_metadata, from_api_period, iter_month_rows
from singapore_customs.config import TABLE_IDS, Config, resolve_months
from singapore_customs.transform import (
    QUANTITY_COLUMNS,
    SOURCE_VALUE_UNIT,
    VALUE_COLUMNS,
    VALUE_UNIT,
    normalize_quantity_row,
    normalize_value_row,
)

MERGE_KEY = ("period", "trade_type", "partner", "hs_code")
MERGED_COLUMNS = [
    "period",
    "trade_type",
    "partner",
    "partner_is_aggregate",
    "hs_code",
    "hs_description",
    "value",
    "value_unit",
    "quantity",
    "quantity_unit",
]

logger = logging.getLogger(__name__)


def table_path(output_dir: Path, table: str, month: str) -> Path:
    """Return the CSV path of ``table`` (``value``, ``quantity`` or ``merged``) for ``month``."""
    return output_dir / table / f"{table}_{month}.csv"


def write_csv_atomically(
    path: Path, columns: list[str], records: Iterable[Mapping[str, Any]]
) -> int:
    """Write ``records`` to ``path`` and return the row count.

    Rows go to a ``.part`` file renamed at the end, so an interrupted run never leaves a
    truncated CSV that a later run would mistake for a complete month.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part_path = path.with_name(f"{path.name}.part")
    count = 0
    with part_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
            count += 1
    part_path.replace(path)
    return count


def extract_table_month(
    session: requests.Session,
    config: Config,
    table: str,
    month: str,
) -> int:
    """Download one table for one month, apply the configured filters and write its CSV."""
    rows = iter_month_rows(session, TABLE_IDS[table], month, config.http)
    if table == "value":
        records: Iterator[Mapping[str, Any]] = (
            record
            for record in map(normalize_value_row, rows)
            if record["hs_level"] in config.hs_levels
        )
        columns = VALUE_COLUMNS
    else:
        records = map(normalize_quantity_row, rows)
        columns = QUANTITY_COLUMNS
    if not config.include_aggregate_partners:
        records = (record for record in records if not record["partner_is_aggregate"])
    return write_csv_atomically(table_path(config.output_dir, table, month), columns, records)


def read_csv(path: Path, keep: Callable[[dict[str, str]], bool]) -> list[dict[str, str]]:
    """Return the rows of a CSV file that satisfy ``keep``."""
    with path.open(encoding="utf-8", newline="") as file:
        return [row for row in csv.DictReader(file) if keep(row)]


def merge_month(output_dir: Path, month: str) -> int:
    """Join the HS8 value and quantity rows of ``month`` into one CSV and return its row count.

    This is a full outer join on period, trade type, partner and HS8 code: a value without a
    quantity (or the reverse) keeps an empty cell for the missing figure. Both unit columns are
    always filled, since the units depend on the HS8 code only.
    """
    value_rows = read_csv(
        table_path(output_dir, "value", month), lambda row: row["hs_level"] == "8"
    )
    quantity_rows = read_csv(table_path(output_dir, "quantity", month), lambda _row: True)

    merged: dict[tuple[str, ...], dict[str, str]] = {}
    for row in value_rows:
        key = tuple(row[column] for column in MERGE_KEY)
        if key in merged:
            msg = f"duplicate value row for {key} in {month}"
            raise ValueError(msg)
        merged[key] = {column: row.get(column, "") for column in MERGED_COLUMNS}

    for row in quantity_rows:
        key = tuple(row[column] for column in MERGE_KEY)
        record = merged.get(key)
        if record is None:
            merged[key] = {**row, "value": "", "value_unit": VALUE_UNIT}
            continue
        if record["quantity"]:
            msg = f"duplicate quantity row for {key} in {month}"
            raise ValueError(msg)
        if row["quantity_unit"] != record["quantity_unit"]:
            msg = (
                f"quantity unit mismatch for {key} in {month}: "
                f"{record['quantity_unit']!r} vs {row['quantity_unit']!r}"
            )
            raise ValueError(msg)
        record["quantity"] = row["quantity"]

    records = (merged[key] for key in sorted(merged))
    return write_csv_atomically(table_path(output_dir, "merged", month), MERGED_COLUMNS, records)


def save_metadata(output_dir: Path, table: str, metadata: dict[str, Any]) -> None:
    """Keep the table metadata next to the extract, for traceability of the data release."""
    path = output_dir / "metadata" / f"{table}_{TABLE_IDS[table]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def run(config: Config, session: requests.Session) -> None:
    """Extract every configured table for every configured month."""
    available: set[str] | None = None
    for table in config.tables:
        metadata = fetch_metadata(session, TABLE_IDS[table], config.http)
        save_metadata(config.output_dir, table, metadata)
        logger.info(
            "%s (%s): %s, %s to %s, last updated %s",
            table,
            TABLE_IDS[table],
            metadata["title"],
            metadata["startPeriod"],
            metadata["endPeriod"],
            metadata["dataLastUpdated"],
        )
        if table == "value" and metadata["uoM"] != SOURCE_VALUE_UNIT:
            msg = f"value table unit is {metadata['uoM']!r}, expected {SOURCE_VALUE_UNIT!r}"
            raise ValueError(msg)
        periods = {from_api_period(period) for period in metadata["periods"]}
        available = periods if available is None else available & periods

    months = resolve_months(config.months, sorted(available or set()))
    logger.info("months to extract: %s", ", ".join(months))

    for month in months:
        written: list[str] = []
        for table in config.tables:
            path = table_path(config.output_dir, table, month)
            if path.exists() and not config.overwrite:
                logger.info("%s %s: already extracted (%s), skipping", table, month, path)
                continue
            started = time.monotonic()
            count = extract_table_month(session, config, table, month)
            written.append(table)
            logger.info(
                "%s %s: %d rows written to %s in %.0fs",
                table,
                month,
                count,
                path,
                time.monotonic() - started,
            )

        merged_path = table_path(config.output_dir, "merged", month)
        if config.merge and (written or config.overwrite or not merged_path.exists()):
            count = merge_month(config.output_dir, month)
            logger.info("merged %s: %d rows written to %s", month, count, merged_path)
