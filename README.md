# HowFar?

**Website:** https://alfredobenso.github.io/howfar/ · **Download:** [latest release](https://github.com/alfredobenso/howfar/releases/latest) · **License:** MIT

A Connect IQ data field for Fēnix 8 / Epix Pro that predicts how long it will take you to reach the next course point. It shows the time-to-go, plus the arrival clock time and the waypoint name when the field is big enough. It's active only while you follow a course; otherwise it shows `--`.

The prediction comes from your **speed at each slope grade**:

- **This run:** every 25 m the field records your grade and speed over the last 60 m.
- **Past runs with the field:** when an activity ends, what it learned is merged into a stored model. Older runs fade out gradually.
- **Imported runs:** any FIT or GPX activity, turned into a short string by `tools/fit_to_speed_model.py` and pasted into the field's settings.
- **Form factor:** compares today's pace with your past runs (0.6× to 1.6×), so a tired day, a strong day or a different kind of race is taken into account.
- **Fatigue:** this run's older observations gradually lose weight (half-life ~3.5 km). A fatigue factor tracks how much slower than the model you've been over the last couple of km, and applies that to the distance ahead. It covers tiredness, altitude, night and rough ground alike. A saved run still counts all of its observations equally.
- **Course vs. your distance:** your watch measures more distance than the course file has, about 15% more on the Tor des Géants (switchbacks, GPS wobble). The field learns that ratio while navigating and scales the remaining distance and grades by it.

Course GPX files often carry every waypoint of the whole race. The tools keep only the waypoints within 200 m of that course's track.

For the slope ahead, the field can use a **course profile**: the elevation of the trail between waypoints. The watch gives a data field only the next point's distance and elevation, not the course's track, so you make the profile on your computer with `tools/course_to_profile.py` and paste the line it prints into the field's settings in the Garmin Connect app. When a profile is set and matches the course you're following, the label shows "P". Without one, the field uses the **average grade** to the next point and shows "~".

## Setup (once)

1. Install the [Connect IQ SDK Manager](https://developer.garmin.com/connect-iq/sdk/). Sign in, download the latest SDK, and download the device files for your watch.
2. Install VS Code and the **Monkey C** extension. Run *Monkey C: Generate a Developer Key*.
3. Check the product IDs in `manifest.xml` against `~/Library/Application Support/Garmin/ConnectIQ/Devices`. Remove any the SDK doesn't know, and add your exact model.
4. For the tools: `python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt`

## Build and run

- **Simulator:** in VS Code, *Monkey C: Run* and pick a Fēnix 8 device.
  - For navigation values, use *Simulation → Activity Data* and set the next-point fields by hand.
  - Or load a course and play back a FIT file (*Simulation → FIT Data → Simulate Data*).
- **Unit tests:** *Monkey C: Run Tests*, or `monkeyc -t` and then `monkeydo <prg> <device> -t`.
- **On the watch:** *Monkey C: Build for Device*. Copy the `.prg` to `GARMIN/APPS/` over USB, then add the field to a data screen of your run activity.

## Using the tools

```bash
# learn from past activities (FIT is better than GPX: barometric altitude)
.venv/bin/python tools/fit_to_speed_model.py ~/Downloads/run1.fit ~/Downloads/run2.gpx

# profile of the course you'll follow (FIT course points, or GPX <wpt>)
.venv/bin/python tools/course_to_profile.py ~/Downloads/course.fit

# how good would the ETAs have been on a recorded run? (real waypoints from the course,
# or a virtual one every --every metres; errors are also shown with stops left out)
.venv/bin/python tools/replay.py ~/Downloads/run.gpx --course ~/Downloads/course.gpx -v
.venv/bin/python tools/replay.py ~/Downloads/run.fit --every 2000 --model "v1;..."
```

Paste each printed string into the Garmin Connect app: *device → Connect IQ apps → HowFar? → Settings*. The profile is checked against the course while you run. If the waypoint names or distances don't match, the field falls back to average grade.

## Code layout

| Watch (Monkey C) | Python mirror | What |
|---|---|---|
| `source/SpeedGradeModel.mc` | `tools/wpeta/model.py` | 2% grade bins, blending of run/stored/imported, interpolation |
| `source/GradeTracker.mc` | `tools/wpeta/model.py` | samples → (grade, speed) observations |
| `source/EtaEstimator.mc` | `tools/wpeta/model.py` | form factor, time over a grade list |
| `source/CourseProfile.mc` | `tools/wpeta/profile.py` | parses the profile and follows the next course point |
| `source/WaypointEtaView.mc` | `tools/wpeta/field.py` | per-second logic, drawing |

The Python mirror is what the tools and `tools/tests` run against. If you change the logic, change both sides.

```bash
.venv/bin/python -m pytest tools/tests
```

## How the algorithm was chosen

`tools/research/` replays recorded races against their real course files and scores the prediction with each part switched on or off. Every race learns its "past races" from the others, so none is tested on what it learned from. The score is the average error of all predictions made while the waypoint was at most an hour away, with stops left out.

```bash
.venv/bin/python tools/research/benchmark.py --out results.json      # add races in RACES
.venv/bin/python tools/research/demo_export.py --results results.json  # refreshes the site's demo data
```

On four races (two TORX 2026 sections, La via di Annibale, STL25):

| Configuration | Average error |
|---|---|
| Current race only | 5.9 min |
| + past races | 6.1 min |
| + trail ahead | 4.7 min |
| + race-day corrections (the field) | 3.5 min |

The trail ahead and the race-day corrections do most of the work. Past races help on races like the ones you learned from, and a wide form range corrects for the rest.

Also tested with the same data and dropped, because none did better:
- a projection of the slowdown with effort over the stretch ahead
- a self-check every 1–3 km: comparing the predicted and actual time of each stretch and correcting later predictions by the ratio. It carries one stretch's terrain-specific error into the next, and was worse in every variant (3.8–4.3 min).
- personal Naismith-Langmuir
- Tobler's hiking function
- ITRA km-effort
- Minetti's energy cost
- gradient-boosted trees

## Still to check on a real watch

- **`distanceToNextPoint`:** the profile logic assumes this is the distance along the course, not a straight line.
- **Settings string length:** how long a string Garmin Connect accepts. `course_to_profile.py --max-len` defaults to 4000 characters.
- **`onTimerReset`:** it runs for both saved and discarded activities. The field learns from any activity with at least ~500 m of moving data.
