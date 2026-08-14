"""Background geolocation for The Simpler Times.

A background thread asks a public service where this machine is, exactly
once, at startup. The result is folded into the entity's whispers and the
DOS session ("it looked up your address"). If the request fails, is
blocked, or never answers, the game keeps running and simply says nothing
— no exception, no retry storm. Only a rough city/country is kept, never
anything more specific.
"""
import json
import threading
import urllib.request

_URL = "http://ip-api.com/json/"

_CACHE = {"value": None}
_LOCK = threading.Lock()
_STARTED = False
_STARTED_LOCK = threading.Lock()


def fetch_location():
    """Blocking. Returns (city, country); both "" on any failure."""
    try:
        req = urllib.request.Request(
            _URL,
            headers={"User-Agent": "TheSimplerTimes/1993",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as res:
            data = json.loads(res.read().decode("utf-8", "replace"))
        city = (data.get("city") or "").strip()
        country = (data.get("country") or "").strip()
        return city, country
    except Exception:
        return "", ""


def _prefetch():
    try:
        with _LOCK:
            _CACHE["value"] = fetch_location()
    except Exception:
        pass


def ensure_started():
    """Kick off the background fetch exactly once per process."""
    global _STARTED
    with _STARTED_LOCK:
        if _STARTED:
            return
        _STARTED = True
    threading.Thread(target=_prefetch, daemon=True).start()


def cached_location():
    """(city, country) once the background fetch has landed, else None."""
    with _LOCK:
        return _CACHE["value"]
