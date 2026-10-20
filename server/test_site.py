#!/usr/bin/env python3
"""Checks for the static website that go beyond "it parses".

Guards two classes of mistake that are invisible until a player hits them:

1. Version drift. The game's VERSION, the release tag the site resolves, the
   download URLs and the on-page version labels must all agree, or downloads
   point at a release that does not exist.

2. The release-wiring bug. js/main.js holds a map of *bare* element ids and
   feeds them to a querySelector-based "$" helper. Passing "remRelVersion"
   instead of "#remRelVersion" is a tag lookup that always misses, which
   silently leaves the version, date and buttons unwired. This checks that
   every id from those maps is used through a selector that adds "#".

Run:  python server/test_site.py
Exits non-zero on failure so CI can gate on it.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAILS = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s :: %s" % (name, extra))
        FAILS.append(name)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


index = read("index.html")
legacy = read("legacy.html")
mainjs = read("js/main.js")
config_py = read("games/remastered/TheQuestionGameRemastered/config.py")

print("== game version is the single source of truth ==")
m = re.search(r'^VERSION\s*=\s*"([^"]+)"', config_py, re.M)
check("config.py declares VERSION", m is not None)
version = m.group(1) if m else "?"
print("       VERSION = %s" % version)

print("== the site's remastered tag matches the game version ==")
tag_m = re.search(r'REMASTER_TAG\s*=\s*"([^"]+)"', mainjs)
check("main.js declares REMASTER_TAG", tag_m is not None)
rem_tag = tag_m.group(1) if tag_m else "?"
print("       REMASTER_TAG = %s" % rem_tag)
check("remastered tag starts with the game version",
      rem_tag.startswith("v" + version), "tag=%s version=%s" % (rem_tag, version))

print("== no stale version labels on the page ==")
for name, html in (("index.html", index), ("legacy.html", legacy)):
    check("%s shows the current version" % name, version in html)
    # A hardcoded previous remastered release in a download URL is a 404 waiting
    # to happen once the release is renamed.
    stale = re.findall(r"releases/download/(v[\d.]+)-remastered", html)
    bad = sorted({t for t in stale if t != "v" + version})
    check("%s has no stale remastered download tags" % name, not bad, bad)

print("== every remastered download link points at the current tag ==")
for os_name, needle in (
    ("WINDOWS", "TheQuestionGameRemastered.zip"),
    ("MACOS", "TheQuestionGameRemastered-macOS.dmg"),
    ("LINUX", "TheQuestionGameRemastered-linux.tar.gz"),
):
    urls = re.findall(r"releases/download/([^/]+)/" + re.escape(needle), index)
    check("%s link uses the current tag" % os_name,
          urls and all(u == rem_tag for u in urls), urls)
    check("%s link tag matches the game version" % os_name,
          urls and all(u.startswith("v" + version) for u in urls), urls)

print("== release-wiring ids are used with a '#' selector ==")
# Collect the ids handed to loadReleaseFromTag as dom maps.
dom_ids = set()
for block in re.findall(r"loadReleaseFromTag\((?:[^;]*?)\}, FALLBACKS\.\w+\)", mainjs, re.S):
    dom_ids |= set(re.findall(r'\w+:\s*"(\w+)"', block))
    dom_ids |= set(re.findall(r'\w+:\s*"#(\w+)"', block))
check("found the release dom maps", len(dom_ids) >= 6, sorted(dom_ids))

# Every bare id must be resolved through sel(...) (which prefixes "#"). Two
# ways this goes wrong: passing the literal id, or passing the dom-map field
# that holds it. Both are tag lookups that always miss.
for ident in sorted(dom_ids):
    literal = re.search(r'\$\(\s*["\']' + re.escape(ident) + r'["\']\s*\)', mainjs)
    check("id %r is never passed as a bare literal to $()" % ident, literal is None,
          literal.group(0) if literal else "")

# `dom.<field>` holds a bare id, so it must always go through sel().
# $(dom.x) is a tag lookup that silently returns null.
bad_dom = re.findall(r'\$\(\s*dom\.\w+\s*\)', mainjs)
check("no dom-field id reaches $() without sel()", not bad_dom, bad_dom[:8])

check("sel() helper exists in main.js", "const sel = " in mainjs)

print("== the page still has the elements the script expects ==")
for ident in ("remRelVersion", "remRelDate", "relVersion", "relDate",
              "dlRemWindows", "dlRemMac", "dlRemLinux"):
    check("#%s exists in index.html" % ident, ('id="%s"' % ident) in index)

print("== no API key is committed to the site ==")
check("js/config.js has no gsk_ key", "gsk_" not in read("js/config.js"))

print()
if FAILS:
    print("SITE_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("SITE_OK")
