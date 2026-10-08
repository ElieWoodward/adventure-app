"""Tests for form validation and the pages. The internet calls are replaced by fakes."""

from datetime import date

import pytest

import app as adventure
import places

TODAY = date(2026, 10, 8)


def form(zip_code="94501", miles="5", day="2026-10-10"):
    return {"zip": zip_code, "miles": miles, "date": day}


# --- validation -----------------------------------------------------------------
def test_valid_form():
    values, errors = adventure.validate_form(form(), today=TODAY)
    assert errors == {}
    assert values == {"zip": "94501", "miles": 5, "date": date(2026, 10, 10)}


@pytest.mark.parametrize("bad_zip", ["", "1234", "123456", "abcde", "9450a"])
def test_bad_zip(bad_zip):
    _, errors = adventure.validate_form(form(zip_code=bad_zip), today=TODAY)
    assert "zip" in errors


@pytest.mark.parametrize("bad_miles", ["", "0", "26", "-3", "2.5", "five"])
def test_bad_miles(bad_miles):
    _, errors = adventure.validate_form(form(miles=bad_miles), today=TODAY)
    assert "miles" in errors


@pytest.mark.parametrize("good_miles", ["1", "5", "25"])
def test_good_miles(good_miles):
    _, errors = adventure.validate_form(form(miles=good_miles), today=TODAY)
    assert errors == {}


def test_past_date_rejected():
    _, errors = adventure.validate_form(form(day="2026-10-01"), today=TODAY)
    assert "date" in errors


def test_today_allowed_plus_one_day_of_time_zone_slack():
    assert adventure.validate_form(form(day="2026-10-08"), today=TODAY)[1] == {}
    assert adventure.validate_form(form(day="2026-10-07"), today=TODAY)[1] == {}


def test_bad_date_text():
    _, errors = adventure.validate_form(form(day="not-a-date"), today=TODAY)
    assert "date" in errors


def test_typed_values_are_kept_when_invalid():
    values, _ = adventure.validate_form(form(zip_code="12", miles="99"), today=TODAY)
    assert values["zip"] == "12"
    assert values["miles"] == "99"


# --- pages ----------------------------------------------------------------------
@pytest.fixture
def client():
    adventure.app.config["TESTING"] = True
    return adventure.app.test_client()


def test_home_page_has_button(client):
    page = client.get("/").get_data(as_text=True)
    assert "Adventure" in page and 'href="/setup"' in page


def test_setup_page_shows_errors_and_keeps_input(client):
    page = client.get("/plan?zip=12&miles=5&date=2099-01-01").get_data(as_text=True)
    assert "5-digit" in page
    assert 'value="12"' in page


def test_service_failure_shows_friendly_message(client, monkeypatch):
    def broken(zip_code, miles):
        raise places.PlaceDataError("The map service is busy.")
    monkeypatch.setattr(places, "get_area", broken)
    response = client.get("/plan?zip=94501&miles=5&date=2099-01-01")
    assert response.status_code == 200
    assert "The map service is busy." in response.get_data(as_text=True)


def test_zip_not_found_goes_back_to_form(client, monkeypatch):
    def missing(zip_code, miles):
        raise places.ZipNotFoundError("We couldn't find zip code 00000.")
    monkeypatch.setattr(places, "get_area", missing)
    page = client.get("/plan?zip=00000&miles=5&date=2099-01-01").get_data(as_text=True)
    assert "find zip code 00000" in page
    assert "<form" in page


def test_too_few_stops_suggests_bigger_range(client, monkeypatch):
    area = {"center": {"lat": 37.76, "lon": -122.24, "place": "Alameda, CA"}, "places": []}
    monkeypatch.setattr(places, "get_area", lambda zip_code, miles: area)
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01").get_data(as_text=True)
    assert "bigger mile range" in page


# --- "ding" sound ---------------------------------------------------------------
ONE_PLACE_AREA = {
    "center": {"lat": 37.76, "lon": -122.24, "place": "Alameda, CA"},
    "places": [{"id": "node/1", "name": "Crab Cove", "label": "Park", "kind": "park",
                "lat": 37.765, "lon": -122.245, "address": ""}],
}


@pytest.fixture
def one_stop(monkeypatch):
    stop = {"place": ONE_PLACE_AREA["places"][0], "start": "10:00 AM", "end": "11:00 AM",
            "slot": "Morning", "miles_from_previous": 0.4, "is_first": True}
    monkeypatch.setattr(places, "get_area", lambda zip_code, miles: ONE_PLACE_AREA)
    monkeypatch.setattr(adventure.planner, "build_plan", lambda *args: [stop])


def test_setup_form_submits_the_ding_flag(client):
    page = client.get("/setup").get_data(as_text=True)
    assert '<input type="hidden" name="ding" value="1">' in page


def test_results_after_form_submit_include_ding(client, one_stop):
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01&ding=1").get_data(as_text=True)
    assert 'id="ding-sound"' in page
    assert "replaceState" in page


def test_try_another_plan_has_no_ding_flag(client, one_stop):
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01&ding=1").get_data(as_text=True)
    try_another = page.split('class="actions"')[1].split("</form>")[0]
    assert "Try another plan" in try_another
    assert "ding" not in try_another


def test_no_ding_without_the_flag(client, one_stop):
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01&prev=node/1").get_data(as_text=True)
    assert "Crab Cove" in page
    assert "ding-sound" not in page


def test_no_ding_when_no_plan_was_made(client, monkeypatch):
    area = {"center": ONE_PLACE_AREA["center"], "places": []}
    monkeypatch.setattr(places, "get_area", lambda zip_code, miles: area)
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01&ding=1").get_data(as_text=True)
    assert "ding-sound" not in page


def test_error_pages_never_ding(client, monkeypatch):
    def broken(zip_code, miles):
        raise places.PlaceDataError("The map service is busy.")
    monkeypatch.setattr(places, "get_area", broken)
    page = client.get("/plan?zip=94501&miles=5&date=2099-01-01&ding=1").get_data(as_text=True)
    assert "The map service is busy." in page
    assert "ding" not in page            # no script, and "Try again" drops the flag

    page = client.get("/no-such-page?ding=1").get_data(as_text=True)
    assert "Oops" in page and "ding" not in page

    def crash(zip_code, miles):
        raise RuntimeError("boom")
    monkeypatch.setattr(places, "get_area", crash)
    response = client.get("/plan?zip=94501&miles=5&date=2099-01-01&ding=1")
    assert response.status_code == 500
    assert "ding" not in response.get_data(as_text=True)
