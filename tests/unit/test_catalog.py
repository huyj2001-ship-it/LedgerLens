import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from ledgerlens.ingest.catalog import FilingsClient, select_annual_filings

FIXTURES = Path(__file__).parents[1] / "fixtures" / "api"
ASML = "724500Y6DUVHQD6OXN27"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock: FakeClock) -> FilingsClient:
    return FilingsClient(user_agent="ledgerlens-test", sleep=clock.sleep, clock=clock)


@respx.mock
def test_list_filings_parses_real_response(client: FilingsClient) -> None:
    payload = json.loads((FIXTURES / "asml_filings.json").read_text(encoding="utf-8"))
    respx.get(f"https://filings.xbrl.org/api/entities/{ASML}/filings").respond(json=payload)

    records = client.list_filings(ASML)

    assert [r.fiscal_year for r in records] == [2021, 2022, 2023, 2024, 2025]
    fy24 = records[3]
    assert fy24.filing_id == f"{ASML}-2024-12-31-ESEF-NL-0"
    assert fy24.report_url is not None and fy24.report_url.endswith("asml-2024-12-31-en.xhtml")
    assert fy24.looks_english
    assert fy24.error_count == 0


@respx.mock
def test_follows_pagination_links(client: FilingsClient) -> None:
    item = json.loads((FIXTURES / "asml_filings.json").read_text(encoding="utf-8"))["data"][0]
    second = "https://filings.xbrl.org/api/entities/X/filings?page%5Bnumber%5D=2"
    route = respx.get(url__startswith="https://filings.xbrl.org/api/entities/X/filings").mock(
        side_effect=[
            httpx.Response(200, json={"data": [item], "links": {"next": second}}),
            httpx.Response(200, json={"data": [item], "links": {}}),
        ]
    )

    assert len(client.list_filings("X")) == 2
    assert route.calls[1].request.url == second


@respx.mock
def test_stops_on_self_referencing_next_link(client: FilingsClient) -> None:
    url = "https://filings.xbrl.org/api/entities/X/filings"
    respx.get(url).respond(json={"data": [], "links": {"next": url}})
    assert client.list_filings("X") == []


@respx.mock
def test_retries_on_server_error(client: FilingsClient) -> None:
    route = respx.get("https://filings.xbrl.org/api/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    assert client.get_json("/api/x") == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_does_not_retry_client_errors(client: FilingsClient) -> None:
    route = respx.get("https://filings.xbrl.org/api/missing").respond(404)
    with pytest.raises(httpx.HTTPStatusError):
        client.get_json("/api/missing")
    assert route.call_count == 1


@respx.mock
def test_requests_are_spaced_by_min_interval(client: FilingsClient, clock: FakeClock) -> None:
    respx.get("https://filings.xbrl.org/api/x").respond(json={})
    client.get_json("/api/x")
    clock.now += 0.25
    client.get_json("/api/x")
    assert clock.slept == [pytest.approx(0.75)]


def test_select_annual_prefers_english_and_skips_interim(client: FilingsClient) -> None:
    payload = json.loads((FIXTURES / "asml_filings.json").read_text(encoding="utf-8"))
    base = payload["data"][3]

    def variant(period_end: str, url: str, processed: str) -> dict:  # type: ignore[type-arg]
        attrs = {**base["attributes"], "period_end": period_end, "report_url": url}
        attrs["processed"] = processed
        return {**base, "attributes": attrs}

    items = [
        variant("2024-06-30", "/r/interim-en.xhtml", "2024-08-01 00:00:00"),
        variant("2024-12-31", "/r/report-nl.xhtml", "2025-03-09 00:00:00"),
        variant("2024-12-31", "/r/report-en.xhtml", "2025-03-01 00:00:00"),
    ]
    with respx.mock:
        respx.get("https://filings.xbrl.org/api/entities/Y/filings").respond(json={"data": items})
        records = client.list_filings("Y")

    chosen = select_annual_filings(records, [2024])
    assert list(chosen) == [2024]
    assert chosen[2024].period_end == date(2024, 12, 31)
    assert chosen[2024].report_url == "/r/report-en.xhtml"
