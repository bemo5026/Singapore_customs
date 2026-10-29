"""Load and validate the YAML configuration that drives an extraction run."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TABLE_IDS = {"value": "T010001", "quantity": "T010002"}
HS_LEVELS = (2, 4, 6, 8)
_MONTH_NUMBERS = frozenset(f"{number:02d}" for number in range(1, 13))


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


@dataclass(frozen=True)
class MonthSelection:
    """Months to extract: an explicit list, a start/end range, or the last N available months.

    Months use the ``YYYY-MM`` format. ``end`` may be ``"latest"``.
    """

    months: tuple[str, ...] = ()
    start: str | None = None
    end: str | None = None
    last: int | None = None


@dataclass(frozen=True)
class HttpSettings:
    """HTTP behavior when calling the TableBuilder API."""

    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    pause_seconds: float


@dataclass(frozen=True)
class Config:
    """Validated extraction configuration."""

    months: MonthSelection
    tables: tuple[str, ...]
    hs_levels: tuple[int, ...]
    include_aggregate_partners: bool
    merge: bool
    output_dir: Path
    overwrite: bool
    http: HttpSettings


def load_config(path: Path) -> Config:
    """Read the YAML file at ``path`` and return the validated configuration.

    Relative ``output_dir`` values are resolved against the folder holding the config file.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{path} must contain a YAML mapping"
        raise ConfigError(msg)

    tables = tuple(raw.get("tables", list(TABLE_IDS)))
    unknown_tables = set(tables) - set(TABLE_IDS)
    if not tables or unknown_tables:
        msg = f"tables must be a non-empty subset of {list(TABLE_IDS)}, got {list(tables)}"
        raise ConfigError(msg)

    hs_levels = tuple(raw.get("hs_levels", HS_LEVELS))
    if not hs_levels or set(hs_levels) - set(HS_LEVELS):
        msg = f"hs_levels must be a non-empty subset of {list(HS_LEVELS)}, got {list(hs_levels)}"
        raise ConfigError(msg)

    merge = bool(raw.get("merge", True))
    if merge and set(tables) != set(TABLE_IDS):
        msg = "merge requires both the value and quantity tables"
        raise ConfigError(msg)
    if merge and 8 not in hs_levels:  # noqa: PLR2004
        msg = "merge requires HS level 8 in hs_levels, the only level of the quantity table"
        raise ConfigError(msg)

    output_dir = Path(raw.get("output_dir", "output"))
    if not output_dir.is_absolute():
        output_dir = path.parent / output_dir

    return Config(
        months=_parse_months(raw.get("months")),
        tables=tables,
        hs_levels=hs_levels,
        include_aggregate_partners=bool(raw.get("include_aggregate_partners", True)),
        merge=merge,
        output_dir=output_dir,
        overwrite=bool(raw.get("overwrite", False)),
        http=_parse_http(raw.get("http", {})),
    )


def _parse_months(raw: Any) -> MonthSelection:  # noqa: ANN401
    """Validate the ``months`` section."""
    if not isinstance(raw, dict):
        msg = "months is required: use 'list', 'start'/'end' or 'last'"
        raise ConfigError(msg)
    modes = [key for key in ("list", "start", "last") if key in raw]
    if len(modes) != 1:
        msg = f"months must use exactly one of 'list', 'start'/'end' or 'last', got {list(raw)}"
        raise ConfigError(msg)

    if "list" in raw:
        months = tuple(str(month) for month in raw["list"])
        for month in months:
            validate_month(month)
        if not months:
            msg = "months.list must not be empty"
            raise ConfigError(msg)
        return MonthSelection(months=months)

    if "last" in raw:
        last = raw["last"]
        if not isinstance(last, int) or last < 1:
            msg = f"months.last must be a positive integer, got {last!r}"
            raise ConfigError(msg)
        return MonthSelection(last=last)

    start = validate_month(str(raw["start"]))
    end = str(raw.get("end", "latest"))
    if end != "latest" and validate_month(end) < start:
        msg = f"months.end ({end}) is before months.start ({start})"
        raise ConfigError(msg)
    return MonthSelection(start=start, end=end)


def _parse_http(raw: dict[str, Any]) -> HttpSettings:
    """Validate the ``http`` section, applying defaults."""
    return HttpSettings(
        timeout_seconds=float(raw.get("timeout_seconds", 120)),
        max_retries=int(raw.get("max_retries", 5)),
        retry_backoff_seconds=float(raw.get("retry_backoff_seconds", 5)),
        pause_seconds=float(raw.get("pause_seconds", 0.5)),
    )


def validate_month(month: str) -> str:
    """Return ``month`` when it is a valid ``YYYY-MM`` string, raise ``ConfigError`` otherwise."""
    year, _, month_number = month.partition("-")
    if not (len(year) == 4 and year.isdigit() and month_number in _MONTH_NUMBERS):  # noqa: PLR2004
        msg = f"invalid month {month!r}, expected YYYY-MM"
        raise ConfigError(msg)
    return month


def resolve_months(selection: MonthSelection, available: list[str]) -> list[str]:
    """Turn the month selection into the sorted list of ``YYYY-MM`` months to extract.

    ``available`` holds the months the API serves. Requesting a month it does not serve is an
    error, so a typo or a month not yet published never results in a silently empty extract.
    """
    available_sorted = sorted(available)
    if selection.last is not None:
        return available_sorted[-selection.last :]

    if selection.months:
        requested = sorted(set(selection.months))
    else:
        end = available_sorted[-1] if selection.end == "latest" else selection.end
        requested = _month_range(selection.start or "", end or "")

    missing = sorted(set(requested) - set(available_sorted))
    if missing:
        msg = (
            f"months not available in TableBuilder: {missing} "
            f"(available {available_sorted[0]} to {available_sorted[-1]})"
        )
        raise ConfigError(msg)
    return requested


def _month_range(start: str, end: str) -> list[str]:
    """Return every ``YYYY-MM`` month from ``start`` to ``end`` inclusive."""
    year, month = int(start[:4]), int(start[5:])
    months = []
    while f"{year:04d}-{month:02d}" <= end:
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)  # noqa: PLR2004
    return months
