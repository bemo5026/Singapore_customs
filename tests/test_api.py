from typing import Any
from unittest.mock import MagicMock

import pytest

from singapore_customs.api import (
    BASE_URL,
    ApiError,
    from_api_period,
    iter_month_rows,
    to_api_period,
)
from singapore_customs.config import HttpSettings

HTTP = HttpSettings(timeout_seconds=10, max_retries=0, retry_backoff_seconds=0, pause_seconds=0)


def page(rows: list[dict[str, str]], *, is_more: bool, cursor: str | None = None) -> MagicMock:
    response = MagicMock()
    data: dict[str, Any] = {"rows": rows, "isMore": is_more, "nextCursor": cursor}
    response.json.return_value = {"Data": data, "StatusCode": 200, "Message": ""}
    return response


def test_period_conversions() -> None:
    assert to_api_period("2026-09") == "2026 Sep"
    assert from_api_period("2013 Jan") == "2013-01"


def test_iter_month_rows_follows_cursor() -> None:
    first = {"period": "2026 Sep", "value": "1"}
    second = {"period": "2026 Sep", "value": "2"}
    session = MagicMock()
    session.get.side_effect = [
        page([first], is_more=True, cursor="abc"),
        page([second], is_more=False),
    ]

    rows = list(iter_month_rows(session, "T010001", "2026-09", HTTP))

    assert rows == [first, second]
    url = f"{BASE_URL}/tabledata/T010001"
    assert [call.args for call in session.get.call_args_list] == [(url,), (url,)]
    assert [call.kwargs for call in session.get.call_args_list] == [
        {"params": {"timeFilter": "2026 Sep", "limit": 5000}, "timeout": 10},
        {"params": {"timeFilter": "2026 Sep", "limit": 5000, "cursor": "abc"}, "timeout": 10},
    ]


def test_iter_month_rows_rejects_repeated_cursor() -> None:
    row = {"period": "2026 Sep", "value": "1"}
    session = MagicMock()
    session.get.side_effect = [
        page([row], is_more=True, cursor="abc"),
        page([row], is_more=True, cursor="abc"),
    ]

    with pytest.raises(ApiError, match="invalid next cursor 'abc'"):
        list(iter_month_rows(session, "T010001", "2026-09", HTTP))


def test_iter_month_rows_rejects_other_period() -> None:
    session = MagicMock()
    session.get.side_effect = [page([{"period": "2026 Aug"}], is_more=False)]

    with pytest.raises(ApiError, match="received a row for period '2026 Aug'"):
        list(iter_month_rows(session, "T010001", "2026-09", HTTP))


def test_iter_month_rows_raises_on_body_error() -> None:
    response = MagicMock()
    response.json.return_value = {"Data": {}, "StatusCode": 420, "Message": "Data is not accepted"}
    session = MagicMock()
    session.get.side_effect = [response]

    with pytest.raises(ApiError, match="StatusCode 420: Data is not accepted"):
        list(iter_month_rows(session, "T010001", "2026-09", HTTP))
