import json
import os
import time
import threading

from . import config

BADGE_CATALOG = {
    "pioneer": ("Pioneer", "Ran it on a machine it has never met."),
    "night_owl": ("Night Owl", "Played in the deepest hours."),
    "returning": ("Returning", "Came back for a second session."),
    "persistent": ("Persistent", "Came back a third time."),
    "photographer": ("Photographer", "Let it look at your pictures."),
    "the_final_eye": ("The Final Eye", "Reached the real ending."),
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


def load_game_state():
    with _lock:
        state = dict(config.DEFAULT_STATE)
        loaded = _load_json(config.STATE_FILE, {})
        state.update(loaded)
        state["answers"] = dict(loaded.get("answers", {}))
        state["answer_times"] = dict(loaded.get("answer_times", {}))
        settings = dict(config.DEFAULT_STATE["settings"])
        settings.update(loaded.get("settings", {}))
        state["settings"] = settings
        return state


def save_game_state(state):
    with _lock:
        _save_json(config.STATE_FILE, state)


def load_badges():
    data = _load_json(config.BADGES_FILE, {})
    earned = data.get("earned", [])
    return earned if isinstance(earned, list) else []


def save_badges(earned):
    _save_json(config.BADGES_FILE, {"earned": earned})


def has_badge(badge_id):
    return badge_id in load_badges()


def award_badge(badge_id):
    """Award a badge if not already earned. Returns True if newly earned."""
    if badge_id not in BADGE_CATALOG:
        return False
    earned = load_badges()
    if badge_id in earned:
        return False
    earned.append(badge_id)
    save_badges(earned)
    return True


def save_answer(state, step_id, answer, elapsed_time):
    state["answers"][step_id] = answer
    state["answer_times"][step_id] = round(elapsed_time, 3)
    save_game_state(state)


def get_answer(state, step_id):
    return state.get("answers", {}).get(step_id)


def reset_all_data():
    state = dict(config.DEFAULT_STATE)
    state["answers"] = {}
    state["answer_times"] = {}
    state["settings"] = dict(config.DEFAULT_STATE["settings"])
    save_game_state(state)
    return state


def record_lie(state, step_id):
    state.setdefault("lie_ids", []).append(step_id)
    state["lie_count"] = len(state["lie_ids"])
    save_game_state(state)


def record_hesitation(state):
    state["hesitation_count"] = state.get("hesitation_count", 0) + 1
    save_game_state(state)
