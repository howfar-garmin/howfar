# HowFar

**How long to the next checkpoint?** A free data field for Garmin watches that tells trail and ultra runners the time to the next checkpoint of their course, learned from how they climb and descend.

**[Website and demo](https://howfar-garmin.github.io/howfar/)** ([IT](https://howfar-garmin.github.io/howfar/it/) · [FR](https://howfar-garmin.github.io/howfar/fr/) · [DE](https://howfar-garmin.github.io/howfar/de/)) · **[Race prep](https://howfar-garmin.github.io/howfar/prepare.html)** · **[Send feedback](https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml)** · **License:** MIT

**Beta.** Made for long trail runs and ultras with real climbs and descents, where your average pace says little about the climb ahead; not for a flat 5 or 10 km, where the average already works. Try it and [tell us how it did](https://github.com/howfar-garmin/howfar/issues/new?template=feedback.yml): the more feedback, the better.

![HowFar on a watch](store/images/hero-1440x720.png)

## What it shows

While you follow a course:

- **the next checkpoint**, with **P** when it knows every climb and descent to it, or **~** when it only knows the height difference
- **the time to get there** while you keep moving (time stopped at aid stations isn't counted), with a coloured dot for how far off it may be
- **the time of day you'll arrive**

On a data screen of its own, with a course profile, it also lists the points around the checkpoint in the order you meet them: minor points on the way (climb tops, huts, your own) with their time from now, and the next main checkpoints with each leg's moving time. On a smaller field it shows just the countdown.

Nothing to set up: it learns your pace on every slope while you run and keeps learning all race long, following you as your day goes. It remembers your past runs, and they count less and less as today's kilometres add up. It works best on trail runs of 25 km or more with real climbs and descents, where it was tested.

## Install

Free in the **[Garmin Connect IQ Store](https://apps.garmin.com/apps/e34840a9-6cd4-4ea6-96b0-051edeb0db73)**: search for *HowFar* in the Connect IQ Store in the Garmin Connect app (or the Connect IQ app), install, and sync your watch. Then add it to a data screen of your Trail Run activity.

Works on the **fēnix 5 Plus**, **5X** and **5X Plus**, **fēnix 6 Pro** (6S and 6X too), **fēnix 7**, **8** and **9** (Pro and Solar too), **fēnix E**, **epix (Gen 2)** and **epix Pro (Gen 2)**, **Enduro 2**, **3** and **4**, **Forerunner 945**, **955**, **965** and **970**, **MARQ** and **Venu X1**. Older watches with less memory get a **lite version**, without the course profile: the first **Enduro**, **fēnix 5**, **5S**, **6** and **6S**, **Forerunner 935** and **Instinct 2** (2S, 2X and Crossover too). Other Forerunner, vívoactive, Venu and Instinct models don't give apps the course's next point, so HowFar can't run on them. Without the store, the [latest release](https://github.com/howfar-garmin/howfar/releases/latest) has a file per watch to copy over USB (that way it has no settings).

## Prepare a race (optional)

The [race prep page](https://howfar-garmin.github.io/howfar/prepare.html) turns the race's course file into a text you paste into HowFar's settings in Garmin Connect, so it knows every climb and descent ahead. You can also add points (the top and bottom of every big climb, huts and villages, your own), each one a main checkpoint to count down to or a minor point shown on the way. It runs in your browser; your files never leave your device.

## Privacy

HowFar collects nothing. What it learns stays on your watch, and the race prep page works without uploading anything. Its optional "Add huts and villages" button asks OpenStreetMap what's around your course, sending only the corners of a rectangle around it.

## Developers

Building, testing, the algorithm and how it was chosen: see [DEVELOPMENT.md](DEVELOPMENT.md).

Not affiliated with Garmin.
