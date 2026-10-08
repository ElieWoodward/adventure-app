"""
Tests for how places.py talks to Overpass servers: logging, trying mirrors in order,
retrying once when busy, and the overall time budget. The servers are faked.
"""

import json
import logging

import pytest
import requests

import config
import places


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return json.loads(self.text)


OK = FakeResponse(200, {"elements": [{"type": "node", "id": 1, "lat": 37.74, "lon": -122.17,
                                      "tags": {"name": "Ice Cream Spot", "amenity": "ice_cream"}}]})


@pytest.fixture
def server(monkeypatch):
    """
    Replace requests.post. Set server.replies to a list of FakeResponse objects or
    exceptions, used in order. Every call is recorded in server.calls.
    """
    class Server:
        replies = []
        calls = []
        sleeps = []

    def fake_post(url, data, headers, timeout):
        Server.calls.append({"url": url, "headers": headers, "timeout": timeout})
        reply = Server.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(places.requests, "post", fake_post)
    monkeypatch.setattr(places.time, "sleep", lambda seconds: Server.sleeps.append(seconds))
    return Server


def hosts(server):
    return [call["url"].split("/")[2] for call in server.calls]


def test_user_agent_is_descriptive_with_contact(server):
    server.replies = [OK]
    places.fetch_places(37.74, -122.17, 5)
    user_agent = server.calls[0]["headers"]["User-Agent"]
    assert "AdventureApp" in user_agent and "github.com/ElieWoodward" in user_agent


def test_success_is_logged_with_server_and_time(server, caplog):
    server.replies = [OK]
    with caplog.at_level(logging.INFO, logger="places"):
        found = places.fetch_places(37.74, -122.17, 5)
    assert [p["name"] for p in found] == ["Ice Cream Spot"]
    assert "Overpass request -> overpass-api.de" in caplog.text
    assert "HTTP 200 in" in caplog.text and "1 elements" in caplog.text


def test_server_error_logs_status_and_body_then_tries_next_mirror(server, caplog):
    body = "<html>500 Internal Server Error " + "x" * 500 + "</html>"
    server.replies = [FakeResponse(500, body), OK]
    with caplog.at_level(logging.INFO, logger="places"):
        places.fetch_places(37.74, -122.17, 5)
    assert hosts(server) == [config.OVERPASS_URLS[0].split("/")[2], config.OVERPASS_URLS[1].split("/")[2]]
    assert "HTTP 500" in caplog.text
    assert "500 Internal Server Error" in caplog.text
    assert "x" * 300 not in caplog.text            # only the first 200 characters are logged
    assert server.sleeps == []                     # a plain error is not retried


def test_busy_429_waits_and_retries_once_on_same_server(server, caplog):
    server.replies = [FakeResponse(429, "Too Many Requests"), OK]
    with caplog.at_level(logging.INFO, logger="places"):
        places.fetch_places(37.74, -122.17, 5)
    first_host = config.OVERPASS_URLS[0].split("/")[2]
    assert hosts(server) == [first_host, first_host]
    assert server.sleeps == [config.BUSY_RETRY_WAIT_SECONDS]
    assert "HTTP 429" in caplog.text and "retrying once" in caplog.text


def test_too_busy_message_counts_as_busy(server):
    too_busy = FakeResponse(504, "Dispatcher_Client::request_read_and_idx::timeout. "
                                 "The server is probably too busy to handle your request.")
    server.replies = [too_busy, OK]
    places.fetch_places(37.74, -122.17, 5)
    assert len(set(hosts(server))) == 1 and len(server.calls) == 2


def test_busy_twice_moves_on_instead_of_a_third_try(server):
    busy = FakeResponse(429, "Too Many Requests")
    server.replies = [busy, busy, OK]
    places.fetch_places(37.74, -122.17, 5)
    names = hosts(server)
    assert names[0] == names[1] != names[2]


def test_timeout_and_connection_errors_are_logged(server, caplog):
    server.replies = [requests.Timeout("read timed out"),
                      requests.ConnectionError("name resolution failed"), OK]
    with caplog.at_level(logging.INFO, logger="places"):
        places.fetch_places(37.74, -122.17, 5)
    assert "timed out after" in caplog.text
    assert "connection error" in caplog.text and "name resolution failed" in caplog.text
    assert len(server.calls) == 3


def test_server_side_timeout_remark_is_logged(server, caplog):
    remark = {"elements": [], "remark": "runtime error: Query timed out in \"query\" at line 3"}
    server.replies = [FakeResponse(200, remark), OK]
    with caplog.at_level(logging.INFO, logger="places"):
        places.fetch_places(37.74, -122.17, 5)
    assert "remark: runtime error: Query timed out" in caplog.text


def test_all_mirrors_failing_is_logged_and_shows_friendly_error(server, caplog):
    server.replies = [FakeResponse(500, "broken")] * len(config.OVERPASS_URLS)
    with caplog.at_level(logging.INFO, logger="places"):
        with pytest.raises(places.PlaceDataError, match="busy or not responding"):
            places.fetch_places(37.74, -122.17, 5)
    assert len(server.calls) == len(config.OVERPASS_URLS)
    assert "All Overpass servers failed" in caplog.text


def test_time_budget_is_respected(server, monkeypatch):
    # Pretend the budget is already used up: no request may be sent.
    with pytest.raises(places.PlaceDataError):
        places.fetch_places(37.74, -122.17, 5, deadline=places.time.monotonic() - 1)
    assert server.calls == []


def test_request_timeout_never_exceeds_remaining_budget(server):
    server.replies = [OK]
    places.fetch_places(37.74, -122.17, 5, deadline=places.time.monotonic() + 10)
    assert server.calls[0]["timeout"] <= 10


def test_budget_fits_inside_gunicorn_timeout():
    with open("render.yaml", encoding="utf-8") as f:
        assert "--timeout 120" in f.read()
    assert config.ZIP_TIMEOUT_SECONDS + config.OVERPASS_TOTAL_SECONDS < 120


def test_zip_lookup_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(places.requests, "get",
                        lambda url, headers, timeout: FakeResponse(503, "Service Unavailable"))
    with caplog.at_level(logging.INFO, logger="places"):
        with pytest.raises(places.PlaceDataError):
            places.lookup_zip("94603")
    assert "Zip lookup 94603: HTTP 503" in caplog.text and "Service Unavailable" in caplog.text
