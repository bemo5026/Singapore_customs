from pathlib import Path

import pytest

from singapore_customs.config import (
    ConfigError,
    MonthSelection,
    load_config,
    resolve_months,
)

AVAILABLE = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_applies_defaults(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, "months:\n  last: 2\n"))

    assert config.months == MonthSelection(last=2)
    assert config.tables == ("value", "quantity")
    assert config.hs_levels == (2, 4, 6, 8)
    assert config.include_aggregate_partners is True
    assert config.merge is True
    assert config.overwrite is False
    assert config.output_dir == tmp_path / "output"
    assert config.http.max_retries == 5


def test_load_config_reads_range(tmp_path: Path) -> None:
    content = 'months:\n  start: "2025-12"\n  end: "2026-02"\ntables: [value]\nmerge: false\n'

    config = load_config(write_config(tmp_path, content))

    assert config.months == MonthSelection(start="2025-12", end="2026-02")
    assert config.tables == ("value",)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("overwrite: true\n", "months is required"),
        ('months:\n  start: "2026-01"\n  last: 2\n', "exactly one of"),
        ('months:\n  list: ["2026-13"]\n', "invalid month"),
        ('months:\n  start: "2026-03"\n  end: "2026-01"\n', "is before"),
        ("months:\n  last: 0\n", "positive integer"),
        ("months:\n  last: 1\ntables: [volume]\n", "tables must be"),
        ("months:\n  last: 1\nhs_levels: [3]\n", "hs_levels must be"),
        ("months:\n  last: 1\ntables: [value]\n", "merge requires both"),
        ("months:\n  last: 1\nhs_levels: [2]\n", "merge requires HS level 8"),
    ],
)
def test_load_config_rejects_invalid_values(tmp_path: Path, content: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, content))


def test_resolve_months_range_to_latest() -> None:
    selection = MonthSelection(start="2026-01", end="latest")

    assert resolve_months(selection, AVAILABLE) == ["2026-01", "2026-02", "2026-03"]


def test_resolve_months_range_across_years() -> None:
    selection = MonthSelection(start="2025-11", end="2026-01")

    assert resolve_months(selection, AVAILABLE) == ["2025-11", "2025-12", "2026-01"]


def test_resolve_months_last() -> None:
    assert resolve_months(MonthSelection(last=2), AVAILABLE) == ["2026-02", "2026-03"]


def test_resolve_months_list_is_sorted_and_deduplicated() -> None:
    selection = MonthSelection(months=("2026-03", "2025-11", "2026-03"))

    assert resolve_months(selection, AVAILABLE) == ["2025-11", "2026-03"]


def test_resolve_months_rejects_unpublished_month() -> None:
    selection = MonthSelection(start="2026-02", end="2026-04")

    with pytest.raises(ConfigError, match=r"not available in TableBuilder: \['2026-04'\]"):
        resolve_months(selection, AVAILABLE)
