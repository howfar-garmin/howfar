# Connect IQ Store listing

Text to paste into the Connect IQ developer site when uploading, and how to upload.

## Two packages

| Package | App ID | Store visibility | Review |
|---|---|---|---|
| `HowFar-beta.iq` (build with `beta.jungle`) | its own (`manifest-beta.xml`) | only the developer's account | none |
| `HowFar.iq` (build with `monkey.jungle`) | the public one (`manifest.xml`) | everyone, once approved | Garmin reviews it |

A beta must use a different app ID from the public app; that is what keeps it private. Keep the product lists of the two manifests the same.

```bash
SDK="$(cat "$HOME/Library/Application Support/Garmin/ConnectIQ/current-sdk.cfg")"
"$SDK/bin/monkeyc" -e -f beta.jungle -o bin/release/HowFar-beta.iq -y developer_key -r
"$SDK/bin/monkeyc" -e -f monkey.jungle -o bin/release/HowFar.iq -y developer_key -r
```

## Upload the private beta

1. Sign in at https://apps.garmin.com/developer/upload with your Garmin account and upload `HowFar-beta.iq`.
2. Mark it as a beta app. Garmin validates the package; a beta is not reviewed.
3. Add the description below. A beta has no public page, so screenshots are optional.
4. Install it from your developer dashboard at apps.garmin.com: open the app and use its download/install button. It reaches the watch at the next sync of the Garmin Connect app, with no file copying.
5. Its Settings then appear in the Garmin Connect app (your watch → Connect IQ apps → HowFar? beta → Settings).

## Submit the public app (later)

Upload `HowFar.iq` the same way, without the beta option. While Garmin reviews it, it stays out of the store but you can preview and download it for testing; once approved it appears publicly. See https://developer.garmin.com/connect-iq/submit-an-app/ and Garmin's App Review Guidelines.

## App name

HowFar?

## Category

Data fields

## Short description

Time to the next checkpoint of your course, learned from how you climb and descend.

## Description

How many times have you wanted to know how long to the next checkpoint? You asked a volunteer, then got angry at how far off they were.

HowFar? puts the answer on your wrist. While you follow a course, it shows:
- the name of the next checkpoint
- the time to get there, while you keep moving
- the time of day you'll arrive

It learns how fast you go on every slope, from steep descents to steep climbs, and keeps learning during the race. It corrects for how your day is going and for your watch measuring more distance than the course map.

Optional: paste two texts into the settings to make it accurate from the first kilometre: your pace from past races, and the course profile with every climb and descent between checkpoints. The website explains how, step by step.

Works without a phone or signal during the race. Time spent stopped at aid stations is not counted.

Free and open source. Not affiliated with Garmin.

#ultratrail #trailrunning #ultrarunning #skyrunning #mountainrunning

## What's new (0.1.0, beta)

First version: next checkpoint, time to it and arrival time; learns your pace by slope; optional speed model and course profile in the settings.

## Links

- Website: https://alfredobenso.github.io/howfar/
- Source: https://github.com/alfredobenso/howfar
