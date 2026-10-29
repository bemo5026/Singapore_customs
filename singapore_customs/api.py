"""Client for the SingStat TableBuilder API (https://tablebuilder.singstat.gov.sg)."""

import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from singapore_customs.config import HttpSettings

BASE_URL = "https://tablebuilder.singstat.gov.sg/api/table"
# The API firewall rejects the default python-requests User-Agent and requests without Accept.
HEADERS = {
    "User-Agent": "singapore-customs-extractor/1.0",
    "Accept": "application/json",
}
# The API caps a page at 5,000 rows whatever the requested limit.
PAGE_SIZE = 5000
RETRY_STATUSES = (429, 500, 502, 503, 504)

logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Raised when the API returns an unexpected response."""


def create_session(http: HttpSettings) -> requests.Session:
    """Return a session that sends the required headers and retries transient failures."""
    retry = Retry(
        total=http.max_retries,
        backoff_factor=http.retry_backoff_seconds,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def get_data(
    session: requests.Session,
    path: str,
    params: dict[str, str | int],
    http: HttpSettings,
) -> dict[str, Any]:
    """Call ``BASE_URL/path`` and return the ``Data`` member of the response.

    The API reports some errors in the body (``StatusCode``) rather than in the HTTP status.
    """
    response = session.get(f"{BASE_URL}/{path}", params=params, timeout=http.timeout_seconds)
    response.raise_for_status()
    body = response.json()
    if body.get("StatusCode") != 200:  # noqa: PLR2004
        msg = f"{response.url} returned StatusCode {body.get('StatusCode')}: {body.get('Message')}"
        raise ApiError(msg)
    return body["Data"]


def fetch_metadata(session: requests.Session, table_id: str, http: HttpSettings) -> dict[str, Any]:
    """Return the metadata of a table: title, unit, periods, markets, HS labels, trade types."""
    return get_data(session, f"metadata/{table_id}", {}, http)["records"]


def to_api_period(month: str) -> str:
    """Convert ``2026-09`` to the API period label ``2026 Sep``."""
    return datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC).strftime("%Y %b")


def from_api_period(period: str) -> str:
    """Convert the API period label ``2026 Sep`` to ``2026-09``."""
    return datetime.strptime(period, "%Y %b").replace(tzinfo=UTC).strftime("%Y-%m")


def iter_month_rows(
    session: requests.Session,
    table_id: str,
    month: str,
    http: HttpSettings,
) -> Iterator[dict[str, str]]:
    """Yield every row of ``table_id`` for ``month`` (``YYYY-MM``), following the cursor pages."""
    period = to_api_period(month)
    params: dict[str, str | int] = {"timeFilter": period, "limit": PAGE_SIZE}
    seen_cursors: set[str] = set()
    page = 0
    while True:
        data = get_data(session, f"tabledata/{table_id}", params, http)
        page += 1
        rows = data["rows"]
        for row in rows:
            if row["period"] != period:
                msg = f"{table_id} {month}: received a row for period {row['period']!r}"
                raise ApiError(msg)
            yield row
        logger.debug("%s %s page %d: %d rows", table_id, month, page, len(rows))

        if not data["isMore"]:
            return
        cursor = data["nextCursor"]
        if not cursor or cursor in seen_cursors:
            msg = f"{table_id} {month}: invalid next cursor {cursor!r} after page {page}"
            raise ApiError(msg)
        seen_cursors.add(cursor)
        params = {**params, "cursor": cursor}
        time.sleep(http.pause_seconds)
