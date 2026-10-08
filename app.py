"""
Adventure: a Flask web app that plans a fun day out near a US zip code.

Run locally:   python app.py
Run on Render: gunicorn app:app   (see render.yaml)
"""

import logging
import os
import random
import re
import sys
from datetime import date, timedelta

from flask import Flask, render_template, request, url_for
from werkzeug.exceptions import HTTPException

import config
import places
import planner

app = Flask(__name__)
# Send log lines to standard output so they show up in Render's "Logs" tab.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)


def validate_form(form, today=None):
    """
    Check the setup form. Returns (values, errors):
      values = the cleaned inputs (or what the user typed, so we can show it again)
      errors = {field_name: friendly message}; empty if everything is fine
    """
    today = today or date.today()
    errors = {}
    zip_code = (form.get("zip") or "").strip()
    miles_text = (form.get("miles") or "").strip()
    date_text = (form.get("date") or "").strip()
    values = {"zip": zip_code, "miles": miles_text, "date": date_text}

    if not re.fullmatch(r"\d{5}", zip_code):
        errors["zip"] = "Please enter a 5-digit US zip code, like 94501."

    try:
        miles = int(miles_text)
        if not config.MIN_MILES <= miles <= config.MAX_MILES:
            raise ValueError
        values["miles"] = miles
    except ValueError:
        errors["miles"] = (
            f"Please enter a whole number of miles from {config.MIN_MILES} to {config.MAX_MILES}."
        )

    try:
        chosen = date.fromisoformat(date_text)
        # The server's clock (UTC on Render) can be a day ahead of the user's,
        # so "yesterday" by the server's clock is still allowed.
        if chosen < today - timedelta(days=1):
            errors["date"] = "Please pick today or a future date."
        else:
            values["date"] = chosen
    except ValueError:
        errors["date"] = "Please pick a date."

    return values, errors


def render_setup(values=None, errors=None, message=None):
    """Show the setup page, keeping whatever the user already typed."""
    today = date.today()
    values = values or {"zip": "", "miles": config.DEFAULT_MILES, "date": today.isoformat()}
    return render_template(
        "setup.html",
        values=values,
        errors=errors or {},
        message=message,
        min_date=(today - timedelta(days=1)).isoformat(),
        config=config,
    )


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/setup")
def setup():
    return render_setup()


@app.route("/plan")
def plan():
    values, errors = validate_form(request.args)
    if errors:
        return render_setup(request.args, errors)

    zip_code, miles, day = values["zip"], values["miles"], values["date"]
    try:
        area = places.get_area(zip_code, miles)
    except places.ZipNotFoundError as error:
        return render_setup(request.args, {"zip": str(error)})
    except places.PlaceDataError as error:
        # "Try again" repeats this request, minus the ding flag.
        retry_args = {key: value for key, value in request.args.items() if key != "ding"}
        return render_template("results.html", values=values, error=str(error),
                               retry_url=url_for("plan", **retry_args))

    # "Try another plan" sends the ids of the last plan; try a few times to get a different one.
    previous = request.args.get("prev", "")
    for _attempt in range(5):
        stops = planner.build_plan(area["places"], area["center"], miles, day.weekday(), random.Random())
        signature = ",".join(stop["place"]["id"] for stop in stops)
        if signature != previous:
            break

    return render_template(
        "results.html",
        values=values,
        nice_date=f"{day:%A, %B} {day.day}, {day.year}",   # e.g. "Saturday, October 10, 2026"
        area=area,
        stops=stops,
        signature=signature,
        too_few=len(stops) < config.MIN_STOPS,
        # Only the setup form sends ding=1; "Try another plan" doesn't.
        ding=request.args.get("ding") == "1" and bool(stops),
        config=config,
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="That page doesn't exist."), 404


@app.errorhandler(Exception)
def unexpected_error(error):
    """Last safety net: log the details, show the user a friendly page."""
    if isinstance(error, HTTPException):     # normal web errors (like 405) pass through
        return error
    app.logger.exception("Unexpected error: %s", error)
    return render_template("error.html", message="Something went wrong on our side. Please try again."), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
