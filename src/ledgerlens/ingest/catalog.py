"""Client for the filings.xbrl.org JSON:API (https://filings.xbrl.org/docs/api).

The service is a free community resource, so the client is deliberately polite: it sends an
identifying User-Agent, waits ``min_interval`` seconds between requests and backs off
exponentially on 429/5xx responses.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

BASE_URL = "https://filings.xbrl.org"
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_EN_SUFFIX = re.compile(r"[-_]en(?:[-_./]|$)", re.IGNORECASE)


class FilingRecord(BaseModel):
    """One ESEF filing as listed by filings.xbrl.org."""

    api_id: str
    filing_id: str
    lei: str
    period_end: date
    country: str
    error_count: int
    report_url: str | None
    json_url: str | None
    package_url: str | None
    processed: datetime | None

    @property
    def fiscal_year(self) -> int:
        return self.period_end.year

    @property
    def is_calendar_year_end(self) -> bool:
        return (self.period_end.month, self.period_end.day) == (12, 31)

    @property
    def looks_english(self) -> bool:
        """Heuristic from the file name; the language is confirmed after download."""
        return bool(self.report_url and _EN_SUFFIX.search(self.report_url.rsplit("/", 1)[-1]))


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _record_from_api(item: dict[str, Any], lei: str) -> FilingRecord:
    attrs = item["attributes"]
    return FilingRecord(
        api_id=item["id"],
        filing_id=attrs["fxo_id"],
        lei=lei,
        period_end=date.fromisoformat(attrs["period_end"]),
        country=attrs["country"],
        error_count=attrs.get("error_count") or 0,
        report_url=attrs.get("report_url"),
        json_url=attrs.get("json_url"),
        package_url=attrs.get("package_url"),
        processed=_parse_datetime(attrs.get("processed")),
    )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return isinstance(exc, httpx.TransportError)


class FilingsClient:
    """Thin, rate-limited wrapper around the filings.xbrl.org API."""

    def __init__(
        self,
        *,
        user_agent: str,
        base_url: str = BASE_URL,
        min_interval: float = 1.0,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
        self._headers = {"User-Agent": user_agent}
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self._retrying = Retrying(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential(multiplier=2, min=2, max=60),
            stop=stop_after_attempt(5),
            sleep=sleep,
            reraise=True,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FilingsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def url(self, path_or_url: str) -> str:
        return path_or_url if path_or_url.startswith("http") else f"{self.base_url}{path_or_url}"

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self.min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def get_json(self, path_or_url: str) -> dict[str, Any]:
        for attempt in self._retrying:
            with attempt:
                self._throttle()
                response = self._http.get(self.url(path_or_url), headers=self._headers)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        return payload

    def list_filings(self, lei: str) -> list[FilingRecord]:
        """All filings of one entity, following JSON:API pagination links."""
        records: list[FilingRecord] = []
        seen: set[str] = set()
        next_url: str | None = self.url(f"/api/entities/{lei}/filings")
        while next_url and next_url not in seen:  # guard against a looping "next" link
            seen.add(next_url)
            page = self.get_json(next_url)
            records.extend(_record_from_api(item, lei) for item in page.get("data", []))
            next_url = (page.get("links") or {}).get("next")
        return sorted(records, key=lambda r: (r.period_end, r.processed or datetime.min))


def select_annual_filings(
    records: list[FilingRecord], fiscal_years: list[int]
) -> dict[int, FilingRecord]:
    """Pick one annual (31 December) filing per fiscal year.

    Interim reports (e.g. Novo Nordisk files quarterly) are ignored. When a year has several
    filings (re-filings, language versions), English is preferred, then the latest processed.
    """
    chosen: dict[int, FilingRecord] = {}
    for rec in records:
        if not rec.is_calendar_year_end or rec.fiscal_year not in fiscal_years:
            continue
        if rec.report_url is None or rec.json_url is None:
            continue
        current = chosen.get(rec.fiscal_year)
        if current is None or _preference(rec) > _preference(current):
            chosen[rec.fiscal_year] = rec
    return dict(sorted(chosen.items()))


def _preference(rec: FilingRecord) -> tuple[bool, datetime]:
    return (rec.looks_english, rec.processed or datetime.min)
