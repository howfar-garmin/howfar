# Developing HowFar

Everything needed to build, test and release HowFar. For what it does and how to use it, see the [README](README.md) and the [website](https://howfar-garmin.github.io/howfar/).

## How the prediction works

The field predicts the time to the next course point from your **speed at each slope grade**:

- **This run:** every 25 m it records the grade and speed over the last 60 m. You count as stopped when you cover less than 15 m in a minute; per-second speed isn't used, because on steep climbs it often dips to almost nothing.
- **Past runs with the field:** when an activity ends, what it learned is merged into a stored model. Older runs fade out gradually. During a run the past counts as at most 10 observations per grade bin, halving every 10 km of the run, so today's running soon takes over.
- **Pace, not speed:** each 2% grade bin averages pace (time per metre), because averaging speeds makes predicted times too short.
- **Grades not seen yet:** a bin with too little data takes the nearest known bin on each side, scaled by Tobler's hiking function, weighted by closeness. With no data at all, Tobler's curve at 2.8 m/s on the flat, scaled by the form factor.
- **Form factor:** today's pace against the past runs alone (0.6× to 1.6×; 0.25× to 3× with nothing remembered), following today with a weight of 0.06 per observation.
- **Fatigue:** this run's older observations gradually lose weight (half-life about 3.5 km), and a fatigue factor compares the last couple of km with the model.
- **Course vs. your distance:** the watch measures more distance than the course file has (about 15% on the Tor des Géants). The field learns that ratio while navigating and scales the remaining distance and grades by it.

For the slope ahead it uses a **course profile** when one is set and matches the course ("P" on the watch): the grade of every 25–400 m between course points. The watch gives a data field only the next point's name, distance and elevation, not the course's track, so the profile is made off the watch and pasted into the settings. Without it the field uses the average grade to the next point ("~").

The watch's next point is put **on the profile**, and the time is the profile's stretch that ends there and is `distanceToNextPoint` long:

- a point the profile has (by name, the first one ahead whose stretch fits where you are): the end of its entry;
- a point it doesn't have: where you are plus `distanceToNextPoint`, where you are being the profile's length minus `distanceToDestination` (or, without it, the last located point plus the distance run since).

The watch's course may be another version of the course, a bit longer or shorter than the profile's. At each point the profile has, the field compares how far both say the finish is and converts the watch's distances by that ratio. Profile points the watch's course lacks are simply crossed.

Course GPX files often carry every waypoint of the whole race; only those within 200 m of the course's track are kept, and a finish line the course passes by but doesn't end at is left out (the race prep page lists it unticked).

Profile points are **main or minor**: a minor point's name starts with `+` in the profile text. The field counts down to the **next main profile point**, which may be one the watch's course lacks, or the watch's next point when the profile doesn't know it. Points added on the race prep page (climb tops and bottoms, huts and villages from OpenStreetMap, your own) exist only in the profile and start as minor; you can switch any point. Where you are always comes from the watch's next point, so the watch's own checkpoints keep anchoring the position. The fourth line, on full-screen fields, is the next minor point on the way (`via …`) or else the main point after the next one (`then …`).

On the race prep page, `docs/js/extra-points.js` finds the added points: climbs as in UltraTrailMate (profile resampled every 40 m with a 50 m median, highs and lows standing out by the chosen D+, 900 m apart), places with one Overpass query for the course's bounding box (the only network request the page makes besides loading its libraries). It can also write the course as a FIT file with every ticked checkpoint as a course point, for runners who want the watch itself to know them.

**On the watch**, the time is shown only as precisely as it is known: `h:mm` in 30-minute steps from four hours out, 15-minute steps from two and 5-minute steps from one, whole minutes from 5 minutes out, `m:ss` in the last 5 minutes, each with its unit in small type (the number fonts have no letters); the arrival time is rounded the same way. For the first ~4 km of an activity (160 observations) the digits are grey and the arrival line says "(learning)": today's form is still a guess. How the error grows with the time left (`tools/research/error_by_time.py`, 4 out of 5 predictions within): about 17% of the time left on the four races with "P", about a third on long training runs with checkpoints where the runner stopped.

## Code layout

| Watch (Monkey C) | Python | Browser | What |
|---|---|---|---|
| `source/SpeedGradeModel.mc` | `tools/wpeta/model.py` | | grade bins, blending, filling unseen grades |
| `source/GradeTracker.mc` | `tools/wpeta/model.py` | | samples → (grade, speed) observations |
| `source/EtaEstimator.mc` | `tools/wpeta/model.py` | | form and fatigue factors, time over a grade list |
| `source/CourseProfile.mc` | `tools/wpeta/profile.py` | `docs/js/howfar-core.js` | the profile text; following the next course point |
| `source/WaypointEtaView.mc` | `tools/wpeta/field.py` | | per-second logic, drawing |
| | `tools/wpeta/readers.py` | `docs/js/howfar-core.js` | reading GPX and FIT |
| | | `docs/js/extra-points.js` | climb tops and bottoms, huts and villages, FIT course out (page only) |

They must agree: the watch reads the profile text the Python tools and the race prep page make, and the Python model is the watch's, line for line. If you change the logic, change all of them; the tests below check that they match.

## Setup (once)

1. Install the [Connect IQ SDK Manager](https://developer.garmin.com/connect-iq/sdk/), sign in, download the latest SDK and the device files.
2. Install VS Code and the **Monkey C** extension; run *Monkey C: Generate a Developer Key*. Keep a backup of the key: every update must be signed with it.
3. Python tools: `python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt`
4. Browser tests: `cd web-tests && npm install`

## Build and test

- **Watch code:** *Monkey C: Build for Device* in VS Code, or `monkeyc -f monkey.jungle -o bin/HowFar.prg -y developer_key -d enduro3`.
- **Watch unit tests:** `monkeyc -t …` then `monkeydo bin/tests.prg enduro3 -t`, or *Monkey C: Run Tests*.
- **Python:** `.venv/bin/python -m pytest tools/tests`
- **Browser vs. Python:** `.venv/bin/python tools/tests/make_web_fixtures.py [--private]`, then `cd web-tests && npm test`. With `--private` it also checks the race files in `courses/`, which are not in git.
- **Simulator:**
  - Next waypoint: *Simulation → Set Navigation Data*.
  - A recorded run: *Simulation → Activity Data*, source *FIT/GPX Playable File*, *Load File*, *Start*, play.
  - Field sizes: *Data Fields → Layout*, then run the field again.
  - Store screenshots: *File → Save Screen Capture*.
- **Website:** the pages are written in English in `site/` and built into `docs/` in English, Italian, French and German by `.venv/bin/python tools/build_site.py`; GitHub Pages serves `docs/` as it is. Every piece of text is found automatically and looked up, by its English, in `site/i18n/{it,fr,de}.json`; the scripts' messages are written `_t("English", {name: value})` and looked up the same way. After changing any text, run the build: it lists what has no translation yet (`--missing it` prints it as JSON to fill in), and the tests fail until `docs/` is rebuilt and complete. Mark text that must stay as it is with `translate="no"`. Locally: `python3 -m http.server 8781 --directory docs`.
- **Watch languages:** the field's few words and its settings' titles are in `resources/strings` (English) and `resources-ita`, `resources-fre`, `resources-deu`; the watch picks its own language.

## Command-line tools

```bash
.venv/bin/python tools/course_to_profile.py course.gpx               # course profile text
.venv/bin/python tools/replay.py run.gpx --course course.gpx -v      # how good the ETAs would have been
.venv/bin/python tools/replay.py run.gpx --past old1.fit old2.gpx    # ... as if the watch remembered those runs
```

## Releasing

- **GitHub release:** build a `.prg` per watch (`-r` for release) and attach them to a release; the website links to the latest one.
- **Connect IQ Store:** `HowFar.iq` is the public app (`monkey.jungle`, `manifest.xml`), reviewed by Garmin. `HowFar-beta.iq` is a private beta with its own app ID (`beta.jungle`, `manifest-beta.xml`). Keep both manifests' product lists the same. Listing text and upload steps: `store/listing.md`; images: `store/make_images.py` and `store/images/`.

## How the algorithm was chosen

`tools/research/` replays recorded races against their course files and scores the prediction with each part switched on or off. Each race learns its "past races" from the others. The score is the average error of all predictions made while the course point was at most an hour away, with stops left out.

```bash
.venv/bin/python tools/research/benchmark.py --out results.json            # exact times, for comparing methods
.venv/bin/python tools/research/benchmark.py --shown --out results.json    # rounded as the watch shows them, for the site
.venv/bin/python tools/research/demo_export.py --results results.json      # refreshes the site's demo data
```

On six races: Tor des Géants 2023 on the official 2026 course (legs where the route changed since are left out of the score), Abbots Way 2018 (no checkpoints in its file, so they go where the runner stopped), TORX100 2025 on the official 2026 course (every leg matches), TORX 2026 section 1, La Via di Annibale, STL25. Times are scored as the watch rounds them (`benchmark.py --shown`):

| Configuration | Average error | Within 5 min | Within 15 min |
|---|---|---|---|
| Distance left at the average moving pace so far (the usual watch estimate) | 8.9 min | 41% | 79% |
| Current race only | 6.7 min | 50% | 89% |
| + trail ahead (course profile) | 5.0 min | 60% | 96% |
| + race-day corrections: the field on a first race | 3.9 min | 73% | 96% |
| + past runs remembered (the other five races) | 3.9 min | 74% | 95% |

How good the times further ahead are (`tools/research/benchmark_ahead.py`, the six races, every moment, rounded as shown): the next checkpoint 7.8 min off on average (0.9 h out), the one after 19.8 min (2.1 h out), the one after that 30.5 min (3.2 h out); about 11–12% of the time to go each time, hence the coarser steps far out.

On the TORX100 the course profile adds little (3.0 min without it, 3.2 with it, but 4.2 → 3.6 min 2 km before a checkpoint): almost every checkpoint is a col or a hut, so each leg is a single climb or descent and the average grade already describes it.

When the profile and the watch's course don't list the same checkpoints (`tools/research/benchmark_missing.py`, the four races and 129 activities with checkpoints every 5 km), placing points on the profile beats the old name-only matching, which fell back to "~" for any point the profile lacked:

| Case | Name only | On the profile |
|---|---|---|
| Profile lacks every other checkpoint: error at those checkpoints, races / activities | 4.1 / 5.1 min | 2.7 / 3.8 min |
| Watch's course lacks every other checkpoint: all checkpoints, races / activities | 4.9 / 6.1 min | 3.8 / 5.3 min |
| As the first, with the watch's course 3% longer: those checkpoints, races / activities | 4.1 / 5.1 min | 2.7 / 3.8 min |

With the same checkpoints on both, nothing changes. Placing an unknown point by its altitude was tried as well and dropped: it didn't help.

The slope is measured over the last 60 m: 40, 100, 150 and 200 m were tested (`tools/research/test_window.py`) and none did better; 60 m was best on the 129 activities (4.56 min against 4.61–4.72) and within 0.05 min of the best on the five races.

A pasted "pace from past races" setting was dropped. Made from similar earlier activities (`tools/research/benchmark_similar_pace.py`) it helped in hours 1–4 of mountain races like them, but made the first half hour worse and hurt whenever the past runs were slower or different; weighing it less or letting it fade (`tools/research/tune_prior.py`) didn't make it reliably useful. What the watch remembers on its own stays, made to fade during the run (10 per bin, halving every 10 km) with a faster form factor (0.06), and missing grades are filled from both neighbours along Tobler's curve (`tools/research/test_shape.py`). Checked on every run (`tools/research/confirm_changes.py`, past runs as the watch would remember them): the five races 4.10 → 3.96 min, the 129 activities of 25 km or more 4.51 → 4.45, the 28 of 50 km or more with checkpoints where the runner stopped 5.37 → 5.14.

Tested and dropped, because none did better: predicting from your speed over the last stretch times how much faster or slower you usually are on each slope (`tools/research/test_anchor.py`: the level from the last 0.5–2 km, the slope ratios from Tobler's curve or from the field's own; 4.2–5.0 min on the races against 4.1, 4.5–5.1 on the 129 activities against 4.5: the recent speed is too noisy an anchor, and the per-slope speeds learned today hold more); carrying today's trend forward (`tools/research/benchmark_trend.py`: the slope of today's pace against a fixed reference over the last 60–120 minutes, extrapolated over the leg and capped at ±10–20%, also leaving out the first 1–2 km after each checkpoint: worse on the four races, the 28 long runs and the 129 activities alike, 3.54 → 3.66–4.06 min on the races at best, and it doesn't fix the long runs' shortfall either); taking a fixed share (5–15%) off the prediction after each checkpoint (`tools/research/bias_after_checkpoint.py`: on the four races the first minutes of a leg run only slightly long, +1–2%, while on long training runs the prediction is about 10% short all along, so a fixed cut helps one and hurts the other); not letting the stretch around each checkpoint (200–500 m) change today's form and recent slowdown, on the theory that walking through aid stations makes the next leg look slow (`tools/research/benchmark_quiet.py`; the four races, 129 activities, and the 28 of 50 km or more with checkpoints where the runner stopped: overall error unchanged, a little less in the first 15 min after a checkpoint, worse on some legs); a projection of the slowdown with effort; a self-check every 1–3 km correcting by the last stretch's ratio (3.8–4.3 min); personal Naismith-Langmuir; Tobler's hiking function; ITRA km-effort; Minetti's energy cost; gradient-boosted trees.

## Still to check on a real watch

- **`distanceToNextPoint` and `distanceToDestination`:** the profile logic assumes both are distances along the course, not straight lines.
- **Settings text length:** how long a text Garmin Connect accepts; the profile tools default to 4,000 characters.
- **`onTimerReset`:** runs for saved and discarded activities alike; the field learns from any activity with at least about 500 m of moving data.
