#!/usr/bin/env python3
"""Update checker tests: version ordering, release selection, polling.

The network is faked, so this runs offline and never touches GitHub.

Run:  python games/remastered/tests/updater_test.py
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)            # games/remastered
sys.path.insert(0, PKG_ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from TheQuestionGameRemastered import updater  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s :: %s" % (name, extra))
        FAILS.append(name)


print("== version parsing and ordering ==")
check("alpha tags parse",
      updater.parse_version("v6.1-alpha-remastered") == ((6, 1, 0, 0), 0),
      updater.parse_version("v6.1-alpha-remastered"))
check("clean versions parse",
      updater.parse_version("6.1") == ((6, 1, 0, 0), 3),
      updater.parse_version("6.1"))
check("beta is older than final",
      updater.parse_version("6.1-beta") < updater.parse_version("6.1"))
check("a same-version remaster tag is not newer",
      not updater.is_newer("v6.1-alpha-remastered", "6.1-alpha"))
check("a later numeric version is newer",
      updater.is_newer("v6.2-alpha-remastered", "6.1-alpha"))
check("a beta of the same version is newer than alpha",
      updater.is_newer("v6.1-beta-remastered", "6.1-alpha"))
check("an older release is not newer",
      not updater.is_newer("v6.0-remastered", "6.1-alpha"))
check("junk releases never win",
      not updater.is_newer("nightly", "6.1-alpha"))

print("== platform assets ==")
release = {"assets": [
    {"name": "TheQuestionGameRemastered.zip", "browser_download_url": "win"},
    {"name": "TheQuestionGameRemastered-macOS.dmg", "browser_download_url": "mac"},
    {"name": "TheQuestionGameRemastered-linux.tar.gz", "browser_download_url": "linux"},
    {"name": "TheQuestionGameRemastered.apk", "browser_download_url": "android"},
]}
check("windows picks the zip", updater._asset_url(release, "Windows") == "win")
check("macos picks the dmg", updater._asset_url(release, "Darwin") == "mac")
check("linux picks the tarball", updater._asset_url(release, "Linux") == "linux")
check("android picks the apk", updater._asset_url(release, "Android") == "android")
check("a missing platform asset is empty",
      updater._asset_url({"assets": []}, "Linux") == "")

print("== release selection ==")
RELEASES = [
    {"tag_name": "v9.9-classic", "html_url": "classic",
     "assets": [], "draft": False},
    {"tag_name": "v6.3-alpha-remastered", "html_url": "draft",
     "assets": [], "draft": True},
    {"tag_name": "v6.2-alpha-remastered", "html_url": "https://example.test/v6.2",
     "published_at": "2026-10-01T00:00:00Z", "draft": False,
     "assets": [{"name": "TheQuestionGameRemastered-linux.tar.gz",
                 "browser_download_url": "https://example.test/game.tar.gz"}]},
    {"tag_name": "v6.1-alpha-remastered", "html_url": "https://example.test/v6.1",
     "assets": [], "draft": False},
]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


_orig_urlopen = updater.urllib.request.urlopen


def fake_urlopen(request, timeout=0):
    return FakeResponse(json.dumps(RELEASES))


updater.urllib.request.urlopen = fake_urlopen
try:
    checker = updater.UpdateChecker(current_version="6.1-alpha",
                                    timeout=0.1, interval=3600,
                                    state_path=None)
    info = checker.check_now()
    check("the newest remastered release wins", info and info["version"] == "6.2-alpha",
          info)
    check("a draft release is ignored", info and info["tag"] != "v6.3-alpha-remastered",
          info)
    check("the classic release is ignored", info and "classic" not in info["url"],
          info)
    check("the release page is offered", info and info["url"] == "https://example.test/v6.2",
          info)
    check("the platform download is resolved",
          info and info["download_url"] == "https://example.test/game.tar.gz", info)
    first = checker.poll()
    check("poll reports the update once", first and first["version"] == "6.2-alpha",
          first)
    check("poll is quiet afterwards", checker.poll() is None)

    current = updater.UpdateChecker(current_version="6.2-alpha",
                                    timeout=0.1, interval=3600,
                                    state_path=None)
    check("the current release is not offered again", current.check_now() is None)

    future = updater.UpdateChecker(current_version="6.2.1",
                                   timeout=0.1, interval=3600,
                                   state_path=None)
    check("a build newer than every release sees no update",
          future.check_now() is None)
finally:
    updater.urllib.request.urlopen = _orig_urlopen

print("== scheduling ==")
off = updater.UpdateChecker(enabled=False, state_path=None)
check("the check can be disabled", off.maybe_check(time.time()) is False)

with tempfile.TemporaryDirectory(prefix="tqg_update_test_") as tmp:
    path = os.path.join(tmp, "update_check.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"last_check": time.time()}, handle)
    recent = updater.UpdateChecker(state_path=path, interval=3600)
    check("a recent persisted check postpones the next one",
          recent.maybe_check(time.time()) is False)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"last_check": time.time() - 7200}, handle)
    stale = updater.UpdateChecker(state_path=path, interval=3600)
    stale._run_check = lambda: None       # never touch the network in tests
    check("an old persisted check is due",
          stale.maybe_check(time.time()) is True)
    stale._thread.join(timeout=2.0)

print()
if FAILS:
    print("UPDATER_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("UPDATER_OK")
