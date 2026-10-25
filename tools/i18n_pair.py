#!/usr/bin/env python3
"""Pairs a translation written as a list (site/i18n/<lang>.list.json, in the order of the
English texts printed by `build_site.py --missing <lang>`) with those texts, checks that each
keeps the English one's placeholders and HTML tags, and merges it into site/i18n/<lang>.json.

    .venv/bin/python tools/i18n_pair.py KEYS.json it
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "site" / "i18n"


def shape(s: str) -> tuple[list[str], list[str]]:
    holes = sorted(re.findall(r"\{\w+\}", s))
    tags = sorted(re.findall(r"</?\w+(?:\s[^>]*)?>", s))
    return holes, tags


def main() -> int:
    keys = json.loads(Path(sys.argv[1]).read_text())
    lang = sys.argv[2]
    values = json.loads((I18N / f"{lang}.list.json").read_text())
    if len(keys) != len(values):
        print(f"{len(keys)} English texts but {len(values)} translations", file=sys.stderr)
        for i, (k, v) in enumerate(zip(keys, values)):
            if shape(k) != shape(v):
                print(f"first shape difference at {i}: {k[:60]!r} / {v[:60]!r}", file=sys.stderr)
                break
        return 1
    bad = [(k, v) for k, v in zip(keys, values) if shape(k) != shape(v)]
    for k, v in bad:
        print(f"placeholders or tags differ:\n  en: {k}\n  {lang}: {v}", file=sys.stderr)
    if bad:
        return 1
    path = I18N / f"{lang}.json"
    cat = json.loads(path.read_text()) if path.exists() else {}
    cat.update(dict(zip(keys, values)))
    path.write_text(json.dumps(cat, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    (I18N / f"{lang}.list.json").unlink()
    print(f"{lang}: {len(values)} texts merged, {len(cat)} in all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
