# Adventure

Adventure plans a fun day out near you. You enter your **zip code**, **how far
you're willing to go** (1 to 25 miles), and a **date**. The app finds real places
nearby and builds a day from 10:00 AM to 8:00 PM, in an order that makes sense, with
each stop close to the last one:

| Time | Stop |
|---|---|
| 10:00 AM – 12:00 PM | Morning: park, garden, beach, viewpoint, playground… |
| 12:00 – 1:00 PM | Lunch: restaurant or cafe |
| 1:00 – 3:30 PM | Afternoon: museum, gallery, library, arcade, mini golf, zoo… |
| 3:30 – 4:30 PM | Treat: ice cream, bakery, dessert, or coffee |
| 4:30 – 6:00 PM | Late afternoon: another activity of a different kind |
| 6:00 – 8:00 PM | Dinner: restaurant |

Each stop shows the time, name, type, address (when known), distance from the previous
stop, and a link to open it in Google Maps. **Try another plan** builds a new random day
from the same inputs.

It uses two free services that need no API key:
[Zippopotam.us](https://api.zippopotam.us) (zip code → map location) and the
[OpenStreetMap Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) (places).

## How the plan is built

1. The zip code is turned into a map location (latitude and longitude).
2. One Overpass search gets every named place of the types we want. It searches the
   closest 5 miles first; only if that doesn't have enough choices for every part of
   the day does it search your whole range. Results are remembered for 10 minutes.
3. For each time slot, in order, the app looks at places of the right kind that are
   - inside your mile range,
   - not already in the plan,
   - not clearly closed on that day or at that time (using the place's opening hours
     from OpenStreetMap; if the hours are missing or unusual, the place is kept).
4. It prefers places within 2 miles of the previous stop (widening 2 miles at a time if
   nothing fits), prefers a type of activity not used yet, then picks randomly among
   the 10 nearest, so "Try another plan" gives plenty of variety.
5. A slot with no good choice is skipped. If fewer than 3 stops are found, the page
   suggests trying a bigger mile range.

All the settings (times, distances, place types, website addresses) are at the top of
`config.py`.

## Files

```
app.py            Web pages and form checking (Flask)
planner.py        Plan-building logic: distances, opening hours, choosing stops
places.py         Getting data from Zippopotam and Overpass, plus the 10-minute cache
config.py         All the settings
templates/        The HTML pages
static/style.css  The styles
tests/            Automated tests (no internet needed)
render.yaml       Hosting setup for Render
```

## Run it on your own computer (Windows)

1. **Install Python.** Go to <https://www.python.org/downloads/> and install Python 3
   (3.10 or newer). On the first installer screen, **tick "Add python.exe to PATH"**.
2. **Open a terminal in the project folder.** In File Explorer, open the folder that
   contains `app.py`, click the address bar, type `cmd`, and press Enter.
3. **Create a virtual environment** (a private space for this project's packages):
   ```
   python -m venv .venv
   ```
4. **Turn it on:**
   ```
   .venv\Scripts\activate
   ```
   You should now see `(.venv)` at the start of the line. Repeat this step every time
   you open a new terminal.
5. **Install the packages:**
   ```
   pip install -r requirements.txt
   ```
6. **Start the app:**
   ```
   python app.py
   ```
7. Open <http://127.0.0.1:5000> in your web browser. To stop the app, go back to the
   terminal and press **Ctrl + C**.

### If every search says "We couldn't reach the zip code service"

Check your internet connection first. If you have an antivirus that inspects secure
web traffic (Avast and AVG do this), the app already handles it on Windows: it uses
the `truststore` package (installed in step 5) so Python trusts the same
certificates Windows does. If you skipped step 5, run it now.

## Run the tests

With the virtual environment turned on (step 4 above):

```
pytest
```

The tests check the form checking, the distance math, the opening-hours reader, the
time window, and the stop-picking logic using made-up places, so they don't need the
internet.

## Put it online with Render (free)

1. **Put the code on GitHub.** Create a free account at <https://github.com>, make a new
   repository (e.g. `adventure`), and upload all the project files *except* the `.venv`
   folder. (Easiest way: on the new repository's page click **"uploading an existing
   file"** and drag the files and the `templates`, `static`, and `tests` folders in.)
2. **Create a Render account** at <https://render.com> (you can sign up with GitHub).
3. In the Render dashboard click **New + → Blueprint**, connect your GitHub account,
   and pick your repository. Render reads `render.yaml` and fills in everything.
   Click **Apply** / **Deploy**.
   - *If you'd rather set it up by hand:* choose **New + → Web Service**, pick the
     repository, and use these settings:
     - Language / Runtime: **Python 3**
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
     - Instance Type: **Free**
4. Wait for the build to finish (a few minutes). Render gives you a link like
   `https://adventure-xxxx.onrender.com`. That's the link to share with your teacher.

Notes about the free plan:

- The app "goes to sleep" after about 15 minutes with no visitors. The next visit
  takes up to a minute to wake it up, then it's fast again. Open the link yourself a
  minute before showing it to anyone.
- The app reads the port from the `PORT` setting that Render provides, so there's
  nothing else to configure.
- `gunicorn` (the web server Render uses) doesn't run on Windows. That's fine: on
  your computer you use `python app.py` instead.
