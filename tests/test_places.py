"""Tests for places.py that don't touch the internet (the fetching is faked)."""

import pytest

import config
import places

CENTER = {"lat": 37.77, "lon": -122.26, "place": "Alameda, CA"}


@pytest.fixture(autouse=True)
def empty_cache():
    places._cache.clear()
    yield
    places._cache.clear()


def fake_place(pid, groups):
    return {"id": f"node/{pid}", "name": "x", "label": "x", "groups": groups,
            "lat": CENTER["lat"], "lon": CENTER["lon"], "address": "", "opening_hours": None}


def one_of_everything(copies):
    groups = [["outdoor"], ["lunch", "dinner"], ["activity"], ["treat"]]
    return [fake_place(f"{i}-{n}", g) for n in range(copies) for i, g in enumerate(groups)]


def test_query_asks_for_named_places_in_a_box():
    query = places.build_query(37.77, -122.26, 5)
    assert "[bbox:" in query and '["name"]' in query
    assert "restaurant" in query and "ice_cream" in query
    assert f"[timeout:{config.OVERPASS_TIMEOUT_SECONDS}]" in query


def test_element_without_name_is_dropped():
    assert places.element_to_place({"type": "node", "id": 1, "lat": 1, "lon": 2,
                                    "tags": {"leisure": "park"}}) is None


def test_way_uses_its_center_and_gets_a_label():
    place = places.element_to_place({
        "type": "way", "id": 7, "center": {"lat": 1.5, "lon": 2.5},
        "tags": {"name": "Big Park", "leisure": "park",
                 "addr:housenumber": "12", "addr:street": "Oak St", "addr:city": "Alameda"},
    })
    assert place["label"] == "Park" and place["lat"] == 1.5
    assert place["address"] == "12 Oak St, Alameda"


def test_house_number_alone_is_not_shown():
    assert places._address({"addr:housenumber": "2528"}) == ""


def test_small_search_is_enough_in_a_busy_area(monkeypatch):
    calls = []
    monkeypatch.setattr(places, "lookup_zip", lambda z: CENTER)
    monkeypatch.setattr(places, "fetch_places",
                        lambda lat, lon, miles: calls.append(miles) or one_of_everything(5))
    places.get_area("94501", 25)
    assert calls == [config.FIRST_SEARCH_MILES]


def test_full_range_is_searched_when_small_search_is_thin(monkeypatch):
    calls = []
    monkeypatch.setattr(places, "lookup_zip", lambda z: CENTER)

    def fetch(lat, lon, miles):
        calls.append(miles)
        return one_of_everything(1 if miles == config.FIRST_SEARCH_MILES else 5)
    monkeypatch.setattr(places, "fetch_places", fetch)
    area = places.get_area("12345", 20)
    assert calls == [config.FIRST_SEARCH_MILES, 20]
    assert len(area["places"]) == 20


def test_results_are_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(places, "lookup_zip", lambda z: CENTER)
    monkeypatch.setattr(places, "fetch_places",
                        lambda lat, lon, miles: calls.append(miles) or one_of_everything(5))
    places.get_area("94501", 5)
    places.get_area("94501", 5)
    assert len(calls) == 1


# --- Windows certificates (truststore) must never stop the app ----------------------
def test_certificates_skip_quietly_when_truststore_is_missing(monkeypatch):
    monkeypatch.setattr(places.sys, "platform", "win32")
    monkeypatch.setitem(places.sys.modules, "truststore", None)  # makes "import truststore" fail
    assert places.use_windows_certificates() is False


def test_certificates_skip_quietly_when_truststore_errors(monkeypatch):
    class BrokenTruststore:
        @staticmethod
        def inject_into_ssl():
            raise RuntimeError("boom")
    monkeypatch.setattr(places.sys, "platform", "win32")
    monkeypatch.setitem(places.sys.modules, "truststore", BrokenTruststore)
    assert places.use_windows_certificates() is False


def test_certificates_not_changed_on_linux(monkeypatch):
    monkeypatch.setattr(places.sys, "platform", "linux")
    assert places.use_windows_certificates() is False
