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

print("== the site resolves the newest published remastered release ==")
# The download buttons must follow whatever remastered release exists, so a
# release published while the page is live becomes the download immediately.
# The pinned REMASTER_TAG is only a floor; REMASTER_FALLBACK_TAG is the last
# release known to exist if the API cannot be reached at all.
check("main.js declares REMASTER_FALLBACK_TAG",
      re.search(r'REMASTER_FALLBACK_TAG\s*=\s*"([^"]+)"', mainjs) is not None)
fb_m = re.search(r'REMASTER_FALLBACK_TAG\s*=\s*"([^"]+)"', mainjs)
fallback_tag = fb_m.group(1) if fb_m else "?"
check("the fallback tag is not newer than the pinned tag",
      not fallback_tag.startswith("v") or fallback_tag <= rem_tag or
      fallback_tag.rsplit("-", 1)[0] <= rem_tag.rsplit("-", 1)[0],
      (fallback_tag, rem_tag))

check("a version parser exists", "function versionParts(" in mainjs)
check("a version comparison exists", "function higherVersion(" in mainjs)
check("the resolver exists", "async function resolveRemasterTag(" in mainjs)
check("the release list is read, not just the pinned tag",
      "const remTag = await resolveRemasterTag();" in mainjs)
check("the chosen tag lands in the fallback map",
      "FALLBACKS.remastered.tag = remTag;" in mainjs)
check("remastered releases are recognised by name", "isRemasterTag" in mainjs)
# The old behaviour pinned the downloads to REMASTER_TAG for ever; the resolver
# must be what loadRelease uses now.
check("loadRelease does not pin the remaster tag",
      "loadReleaseFromTag(REMASTER_TAG," not in mainjs)

print("== no API key is committed to the site ==")
check("js/config.js has no gsk_ key", "gsk_" not in read("js/config.js"))

print("== the VHS/3D remaster layers are wired end to end ==")
css = read("css/style.css")
# Markup, styling and behaviour must all three exist, or the effect is dead.
for cls in ("mask-rgb", "tracking", "dropout", "edge-bend"):
    check("index.html has the %s layer" % cls, ('class="%s"' % cls) in index)
    check("style.css defines .crt .%s" % cls, (".crt .%s" % cls) in css)
check("index.html has the VHS deck chrome", 'class="vhs-chrome"' in index)
# The 3D card tilt was removed on purpose: it tilted the cards under the
# cursor, so clicks landed beside the buttons. Guard against it creeping back.
check("no tilt driver in main.js", "tiltCards" not in mainjs)
# A leftover comment naming the old class is fine; a rule is not. Only count
# ".tilt-card" when it is followed by a declaration block.
check("no tilt rules survive in css",
      not any(".tilt-card" in line and "{" in line for line in css.splitlines()))
check("no tilt transforms survive in css", "perspective(" not in css)
check("main.js records why the tilt went", "card tilt" in mainjs.lower())
check("new layers are behind the no-fx switch",
      "body.no-fx .crt .tracking" in css and "body.no-fx .vhs-chrome" in css)

print("== the site does not repeat the disproven claims ==")
# The classic edition DOES open the camera and DOES call ip-api.com; claiming
# otherwise was a factual error on the page. Guard against it coming back.
check("no 'classic edition never activates a camera'",
      "never activates a camera" not in index)
check("no 'classic edition makes no network requests'",
      "makes no network requests" not in index)
check("the location lookup is disclosed", "IP-geolocation" in index)
check("the camera is disclosed as on by default",
      "on by default" in index and "camera" in index.lower())

print()
if FAILS:
    print("SITE_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("SITE_OK")
