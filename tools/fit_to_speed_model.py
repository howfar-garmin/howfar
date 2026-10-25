#!/usr/bin/env python3
"""Learn your speed at each slope grade from past activities.

    python tools/fit_to_speed_model.py run1.fit run2.gpx ...

Prints a string to paste into the data field's "Imported speed model" setting
(Garmin Connect app > device > Connect IQ apps > HowFar > Settings).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wpeta.learn import layer_from_files  # noqa: E402
from wpeta.model import NUM_BINS, bin_center  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="activity .fit or .gpx files")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only the settings string")
    args = ap.parse_args()

    layer = layer_from_files(args.files)
    if layer.total_weight() == 0:
        print("No usable data: the files need elevation, distance (or coordinates) and timestamps.", file=sys.stderr)
        return 1

    if not args.quiet:
        print("grade   speed     pace   samples", file=sys.stderr)
        for i in range(NUM_BINS):
            w = layer.weights[i]
            if w >= 1:
                v = layer.speed(i)
                pace = 1000 / v
                print(f"{bin_center(i):+5.0f}%  {v:4.2f} m/s  {int(pace // 60)}:{int(pace % 60):02d}/km  {w:5.0f}", file=sys.stderr)
        print(file=sys.stderr)
    print(layer.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
