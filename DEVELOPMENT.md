# Developing HowFar?

Everything needed to build, test and release HowFar?. For what it does and how to use it, see the [README](README.md) and the [website](https://howfar-garmin.github.io/howfar/).

## How the prediction works

The field predicts the time to the next course point from your **speed at each slope grade**:

- **This run:** every 25 m it records the grade and speed over the last 60 m. You count as stopped when you cover less than 15 m in a minute; per-second speed isn't used, because on steep climbs it often dips to almost nothing.
- **Past runs with the field:** when an activity ends, what it learned is merged into a stored model. Older runs fade out gradually.
- **Imported runs:** a speed model made from any activities (race prep page, or `tools/fit_to_speed_model.py`) and pasted into the settings.
- **Pace, not speed:** each 2% grade bin averages pace (time per metre), because averaging speeds makes predicted times too short.
- **Form factor:** today's pace against past runs (0.6× to 1.6×).
- **Fatigue:** this run's older observations gradually lose weight (half-life about 3.5 km), and a fatigue factor compares the last couple of km with the model.
- **Course vs. your distance:** the watch measures more distance than the course file has (about 15% on the Tor des Géants). The field learns that ratio while navigating and scales the remaining distance and grades by it.

For the slope ahead it uses a **course profile** when one is set and matches the course ("P" on the watch): the grade of every 25–400 m between course points. The watch gives a data field only the next point's name, distance and elevation, not the course's track, so the profile is made off the watch and pasted into the settings. Without it the field uses the average grade to the next point ("~").

Course GPX files often carry every waypoint of the whole race; only those within 200 m of the course's track are kept.

## Code layout

| Watch (Monkey C) | Python | Browser | What |
|---|---|---|---|
| `source/SpeedGradeModel.mc` | `tools/wpeta/model.py` | `docs/js/howfar-core.js` | grade bins, blending, interpolation |
| `source/GradeTracker.mc` | `tools/wpeta/model.py` | `docs/js/howfar-core.js` | samples → (grade, speed) observations |
| `source/EtaEstimator.mc` | `tools/wpeta/model.py` | | form and fatigue factors, time over a grade list |
| `source/CourseProfile.mc` | `tools/wpeta/profile.py` | `docs/js/howfar-core.js` | the profile text; following the next course point |
| `source/WaypointEtaView.mc` | `tools/wpeta/field.py` | | per-second logic, drawing |
| | `tools/wpeta/readers.py` | `docs/js/howfar-core.js` | reading GPX and FIT |

The three must agree: the watch reads the texts the Python tools and the race prep page make. If you change the logic, change all of them; the tests below check that they match.

## Setup (once)

1. Install the [Connect IQ SDK Manager](https://developer.garmin.com/connect-iq/sdk/), sign in, download the latest SDK and the device files.
2. Install VS Code and the **Monkey C** extension; run *Monkey C: Generate a Developer Key*. Keep a backup of the key: every update must be signed with it.
3. Python tools: `python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt`
4. Browser tests: `cd web-tests && npm install`

## Build and test

- **Watch code:** *Monkey C: Build for Device* in VS Code, or `monkeyc -f monkey.jungle -o bin/HowFar.prg -y developer_key -d enduro3`.
- **Watch unit tests:** `monkeyc -t …` then `monkeydo bin/tests.prg enduro3 -t`, or *Monkey C: Run Tests*.
- **Python:** `.venv/bin/python -m pytest tools/tests`
- **Browser vs. Python:** `.venv/bin/python tools/tests/make_web_fixtures.py [--private]`, then `cd web-tests && npm test`. With `--private` it also checks the race files in `samples/` and `courses/`, which are not in git.
- **Simulator:**
  - Next waypoint: *Simulation → Set Navigation Data*.
  - A recorded run: *Simulation → Activity Data*, source *FIT/GPX Playable File*, *Load File*, *Start*, play.
  - Field sizes: *Data Fields → Layout*, then run the field again.
  - Store screenshots: *File → Save Screen Capture*.
- **Website:** `docs/` is served as-is by GitHub Pages. Locally: `python3 -m http.server 8781 --directory docs`.

## Command-line tools

```bash
.venv/bin/python tools/fit_to_speed_model.py run1.fit run2.gpx      # speed model text
.venv/bin/python tools/course_to_profile.py course.gpx               # course profile text
.venv/bin/python tools/replay.py run.gpx --course course.gpx -v      # how good the ETAs would have been
```

## Releasing

- **GitHub release:** build a `.prg` per watch (`-r` for release) and attach them to a release; the website links to the latest one.
- **Connect IQ Store:** `HowFar.iq` is the public app (`monkey.jungle`, `manifest.xml`), reviewed by Garmin. `HowFar-beta.iq` is a private beta with its own app ID (`beta.jungle`, `manifest-beta.xml`). Keep both manifests' product lists the same. Listing text and upload steps: `store/listing.md`; images: `store/make_images.py` and `store/images/`.

## How the algorithm was chosen

`tools/research/` replays recorded races against their course files and scores the prediction with each part switched on or off. Each race learns its "past races" from the others. The score is the average error of all predictions made while the course point was at most an hour away, with stops left out.

```bash
.venv/bin/python tools/research/benchmark.py --out results.json
.venv/bin/python tools/research/demo_export.py --results results.json   # refreshes the site's demo data
```

On four races (two TORX 2026 sections, La via di Annibale, STL25):

| Configuration | Average error |
|---|---|
| Current race only | 5.9 min |
| + past races | 6.1 min |
| + trail ahead | 4.7 min |
| + race-day corrections (the field) | 3.5 min |

Tested and dropped, because none did better: a projection of the slowdown with effort; a self-check every 1–3 km correcting by the last stretch's ratio (3.8–4.3 min); personal Naismith-Langmuir; Tobler's hiking function; ITRA km-effort; Minetti's energy cost; gradient-boosted trees.

## Still to check on a real watch

- **`distanceToNextPoint`:** the profile logic assumes it is the distance along the course, not a straight line.
- **Settings text length:** how long a text Garmin Connect accepts; the profile tools default to 4,000 characters.
- **`onTimerReset`:** runs for saved and discarded activities alike; the field learns from any activity with at least about 500 m of moving data.
