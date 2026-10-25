#!/usr/bin/env python3
"""Builds the website in every language from the English pages in site/.

    .venv/bin/python tools/build_site.py            # writes docs/*.html and docs/{it,fr,de}/*.html
    .venv/bin/python tools/build_site.py --check    # fails if a translation is missing or docs/ is stale
    .venv/bin/python tools/build_site.py --missing it   # prints the texts Italian still lacks, as JSON

Edit only site/*.html (English). Each translatable piece of text is found automatically: the
content of an element that holds text and only inline markup (a paragraph, a list item, a
heading...), loose text next to other elements, and the title, alt, aria-label, placeholder
and description attributes. Its English, with whitespace collapsed, is the key into
site/i18n/<lang>.json. Elements with translate="no" are left alone.

The scripts' own messages are written _t("English text", {name: value}) in docs/js/*.js; their
translations live in the same files and are handed to each page as window.HOWFAR_T.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site"
OUT = ROOT / "docs"
I18N = SRC / "i18n"
PAGES = ["index.html", "prepare.html"]
LANGS = {"en": "English", "it": "Italiano", "fr": "Français", "de": "Deutsch"}
BASE = "https://howfar-garmin.github.io/howfar/"
JS_FILES = [OUT / "js" / "demo.js", OUT / "js" / "prepare.js"]

INLINE = {"a", "b", "i", "em", "strong", "span", "br", "small", "sup", "sub", "abbr", "code", "kbd", "s", "u", "mark"}
SKIP = {"script", "style", "svg", "pre", "textarea"}
# elements that can be one piece of text; containers (nav, div, ul...) are split into their children
TEXT = {"title", "h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "td", "th", "summary", "legend", "label", "button",
        "option", "figcaption", "caption"} | INLINE
ATTRS = ("title", "alt", "aria-label", "placeholder")
META = {("name", "description"), ("name", "keywords"), ("property", "og:title"), ("property", "og:description")}
PAGE_LINKS = ("./", "index.html", "prepare.html")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def wordy(s: str) -> bool:
    return any(c.isalpha() for c in s)


class Translator:
    def __init__(self, lang: str, catalog: dict[str, str]) -> None:
        self.lang, self.catalog = lang, catalog
        self.used: list[str] = []
        self.missing: list[str] = []

    def __call__(self, text: str) -> str:
        key = norm(text)
        if not wordy(key):
            return text
        self.used.append(key)
        if self.lang == "en":
            return text
        if key not in self.catalog:
            self.missing.append(key)
            return text
        return self.catalog[key]


def inner(el: Tag) -> str:
    return "".join(str(c) for c in el.contents)


def eligible(el: Tag) -> bool:
    """Holds text and nothing but inline markup: translate it as one piece."""
    if el.name not in TEXT or not wordy(el.get_text()):
        return False
    for d in el.descendants:
        if isinstance(d, Tag) and (d.name not in INLINE or d.get("translate") == "no"):
            return False
    return True


def translate_tree(el: Tag, tr: Translator) -> None:
    if el.name in SKIP or el.get("translate") == "no":
        return
    for a in ATTRS:
        if el.has_attr(a) and wordy(el[a]):
            el[a] = tr(el[a])
    if el.name == "meta":
        for attr, value in META:
            if el.get(attr) == value and el.has_attr("content"):
                el["content"] = tr(el["content"])
        return
    if el.name not in ("html", "head", "body") and eligible(el):
        new = tr(inner(el))
        if new is not inner(el) and norm(new) != norm(inner(el)):
            el.clear()
            for node in list(BeautifulSoup(new, "html.parser").contents):
                el.append(node)
        return
    for child in list(el.children):
        if isinstance(child, Comment) or isinstance(child, Doctype):
            continue
        if isinstance(child, NavigableString):
            if wordy(child):
                lead = child[: len(child) - len(child.lstrip())]
                tail = child[len(child.rstrip()):]
                new = tr(str(child))
                if norm(new) != norm(str(child)):
                    child.replace_with(lead + new.strip() + tail)
        elif isinstance(child, Tag):
            translate_tree(child, tr)


def page_url(lang: str, page: str) -> str:
    return BASE + ("" if lang == "en" else lang + "/") + ("" if page == "index.html" else page)


def rel_link(src_lang: str, dst_lang: str, page: str) -> str:
    target = "" if page == "index.html" else page
    if src_lang == dst_lang:
        return target or "./"
    up = "" if src_lang == "en" else "../"
    return up + ("" if dst_lang == "en" else dst_lang + "/") + target or "./"


def js_keys() -> list[str]:
    """Every _t("...") the scripts call."""
    keys = []
    for f in JS_FILES:
        src = f.read_text()
        for m in re.finditer(r'\b_t\(\s*"((?:[^"\\]|\\.)*)"', src):
            keys.append(json.loads('"' + m.group(1) + '"'))
    return list(dict.fromkeys(keys))


LANG_SCRIPT = """window.HOWFAR_LANG=%s;window.HOWFAR_T=%s;
window._t=function(s,v){var x=window.HOWFAR_T[s]||s;return v?x.replace(/\\{(\\w+)\\}/g,function(m,k){return k in v?v[k]:m}):x};
(function(){try{var k="howfar.lang";document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[data-lang]");if(a)localStorage.setItem(k,a.getAttribute("data-lang"))});%s}catch(e){}})();"""

# English pages send a first-time visitor whose browser speaks one of the other languages there
REDIRECT = """if(!localStorage.getItem(k)){var l=((navigator.languages&&navigator.languages[0])||navigator.language||"").slice(0,2).toLowerCase();if(%s.indexOf(l)>=0){localStorage.setItem(k,l);location.replace(l+"/"+location.pathname.split("/").pop()+location.hash)}}"""


def build_page(page: str, lang: str, catalog: dict[str, str], js_catalog: dict[str, str]) -> tuple[str, Translator]:
    soup = BeautifulSoup((SRC / page).read_text(), "html.parser")
    tr = Translator(lang, catalog)
    translate_tree(soup.html, tr)
    soup.html["lang"] = lang

    if lang != "en":  # one folder down: shared files are one level up, the two pages are next door
        for el in soup.find_all(True):
            for attr in ("href", "src"):
                v = el.get(attr)
                if not v or re.match(r"^(https?:|//|#|mailto:|data:)", v) or v.startswith(PAGE_LINKS) or v == "":
                    continue
                el[attr] = "../" + v

    head = soup.head
    for code in LANGS:
        head.append(soup.new_tag("link", rel="alternate", hreflang=code, href=page_url(code, page)))
    head.append(soup.new_tag("link", rel="alternate", hreflang="x-default", href=page_url("en", page)))
    script = soup.new_tag("script")
    others = json.dumps([c for c in LANGS if c != "en"])
    script.string = LANG_SCRIPT % (json.dumps(lang), json.dumps(js_catalog, ensure_ascii=False, sort_keys=True),
                                   REDIRECT % others if lang == "en" else "")
    head.append(script)

    nav = soup.new_tag("nav", attrs={"class": "lang-switch", "aria-label": tr("Language"), "translate": "no"})
    for code, name in LANGS.items():
        a = soup.new_tag("a", href=rel_link(lang, code, page), hreflang=code, lang=code, title=name)
        a["data-lang"] = code
        if code == lang:
            a["aria-current"] = "true"
        a.string = code.upper()
        nav.append(a)
    soup.select_one(".site-head .wrap").append(nav)
    return str(soup), tr


def catalogs() -> dict[str, dict[str, str]]:
    return {code: (json.loads((I18N / f"{code}.json").read_text()) if (I18N / f"{code}.json").exists() else {})
            for code in LANGS if code != "en"} | {"en": {}}


def build(check: bool) -> int:
    cats = catalogs()
    jkeys = js_keys()
    problems = 0
    for lang in LANGS:
        cat = cats[lang]
        js_cat = {k: cat[k] for k in jkeys if k in cat} if lang != "en" else {}
        missing_js = [k for k in jkeys if lang != "en" and k not in cat]
        for page in PAGES:
            html, tr = build_page(page, lang, cat, js_cat)
            out = OUT / page if lang == "en" else OUT / lang / page
            if tr.missing:
                problems += len(tr.missing)
                print(f"{lang}/{page}: {len(tr.missing)} texts not translated", file=sys.stderr)
            if check:
                if not out.exists() or out.read_text() != html:
                    print(f"{out.relative_to(ROOT)} is out of date: run tools/build_site.py", file=sys.stderr)
                    problems += 1
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(html)
        if missing_js:
            problems += len(missing_js)
            print(f"{lang}: {len(missing_js)} script messages not translated", file=sys.stderr)
    return 1 if problems else 0


def missing(lang: str) -> int:
    cat = catalogs()[lang]
    need: list[str] = []
    for page in PAGES:
        _, tr = build_page(page, lang, cat, {})
        need += tr.missing
    need += [k for k in js_keys() if k not in cat]
    print(json.dumps({k: "" for k in dict.fromkeys(need)}, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--missing", choices=[c for c in LANGS if c != "en"])
    args = ap.parse_args()
    if args.missing:
        return missing(args.missing)
    return build(args.check)


if __name__ == "__main__":
    sys.exit(main())
