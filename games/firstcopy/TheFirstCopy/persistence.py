"""Persistence and badge system for The Simpler Times (1993)."""
import json
import os
import threading

from . import config

BADGE_CATALOG = {
    "fairgoer":      {"name": "The Fairgoer",    "desc": "Took the disk with no label."},
    "archivist":     {"name": "The Archivist",   "desc": "Archived every fragile file before it corrupted."},
    "patient_one":   {"name": "Patient One",     "desc": "Read every document on the disk."},
    "not_alone":     {"name": "Not Alone",       "desc": "It noticed you."},
    "curator":       {"name": "The Curator",     "desc": "Archived everything, then sealed the disk."},
    "first_subject": {"name": "The First Subject","desc": "Answered every question it asked."},
    "night_owl":     {"name": "Night Owl",       "desc": "Stayed at the fest past closing."},
    "pioneer":       {"name": "Pioneer",         "desc": "First to run it on this machine."},
    "2013":          {"name": "2013",            "desc": "Typed 2013. Found the truth."},
}

_lock = threading.Lock()


def _load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return fallback


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def default_state():
    return {
        "part": 1,
        "scene_id": "fair_room",
        "ending": None,
        "answers": {},
        "hesitations": {},
        "hesitation_count": 0,
        "presence": 0,          # how much it has noticed you
        "discovered": [],       # document ids read
        "archived": [],         # document ids archived uncorrupted
        "visited": {},          # scene_id -> times visited
        "items": [],            # inventory: ["disk", ...]
        "logs_unlocked": False,  # 2013 code
        "last_close_time": 0,
        "run_count": 1,
        "first_run_done": False,
        "settings": dict(config.DEFAULT_SETTINGS),
    }


_state = None
_badges = None


def load_state():
    global _state
    data = _load_json(config.STATE_FILE, None)
    d = default_state()
    if isinstance(data, dict):
        for k in d:
            if k in data:
                d[k] = data[k]
        if isinstance(d.get("settings"), dict):
            d["settings"].update(config.DEFAULT_SETTINGS)
    _state = d
    return _state


def save_state():
    if _state is not None:
        _save_json(config.STATE_FILE, _state)


def state():
    if _state is None:
        load_state()
    return _state


def reset_state(state_dict=None):
    """Replace the cached game state (used when starting a new run)."""
    global _state
    _state = state_dict if isinstance(state_dict, dict) else default_state()
    _save_json(config.STATE_FILE, _state)


def load_badges():
    global _badges
    data = _load_json(config.BADGES_FILE, None)
    _badges = data if isinstance(data, dict) and isinstance(data.get("earned"), list) \
        else {"earned": []}
    return _badges


def badges():
    if _badges is None:
        load_badges()
    return _badges


def award_badge(badge_id):
    """Award a badge if not already earned. Returns True if newly earned."""
    if badge_id not in BADGE_CATALOG:
        return False
    if badge_id in badges()["earned"]:
        return False
    badges()["earned"].append(badge_id)
    _save_json(config.BADGES_FILE, badges())
    return True


def has_badge(badge_id):
    return badge_id in badges().get("earned", [])


def save_badges(data):
    """Replace the earned-badge list (used by the game's badge engine)."""
    global _badges
    _badges = data if isinstance(data, dict) and isinstance(
        data.get("earned"), list) else {"earned": []}
    _save_json(config.BADGES_FILE, _badges)


def save_settings(settings):
    st = state()
    st["settings"].update(settings)
    save_state()
