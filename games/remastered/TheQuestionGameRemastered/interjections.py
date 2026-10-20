"""Classic "bite" — the injected, machine-aware questions that gave the
original its personality.

The remastered edition's skeleton is the human-authored fixed opening plus the
AI-written questions. This module supplies the *teeth* Classic had and v2 lost:

  * dynamic questions built from real machine state (your location, the apps
    that are actually running),
  * contradiction callbacks ("Are you alone?" asked again, then thrown back),
  * tailored reactions to what you actually answered,
  * memory callbacks and lore interjections,
  * hesitation call-outs and false-memory rebuttals.

Everything here is local and cheap: no network, no blocking work on the render
thread (callers resolve dynamic questions in a worker).
"""
import random

from . import config
from . import os_layer

# How often a tailored reaction lands after a mapped answer. Classic fired one
# for nearly every question across a 100-question run; the remastered opening
# is much shorter, so we thin it out to keep the pacing.
REACTION_CHANCE = 0.65

# --- Small step factory ------------------------------------------------------
def _q(q, opts, _id, **extra):
    s = {"q": q, "type": "choice", "opts": list(opts), "_id": _id, "_injected": True}
    s.update(extra)
    return s


# --- Dynamic questions (built from real machine state) -----------------------
def _location_question(game_state):
    geo = os_layer.get_cached_geo() if hasattr(os_layer, "get_cached_geo") else {}
    if not geo:
        city, country = os_layer.get_cached_location()
        geo = {"city": city, "country": country, "country_code": ""}
    city = geo.get("city", "")
    region = geo.get("region", "")
    country = geo.get("country", "")

    if city and country:
        where = "%s, %s" % (city, country)
        denial = ("That's strange.\nThe network you're connected to says otherwise.\n"
                  "We'll use what we have.")
        if region:
            denial = ("That's strange.\nThe network places you in %s.\n"
                      "People there tend to answer the same way." % region)
        return _q(
            "Are you currently in %s?" % where,
            ["Yes", "No"],
            "location_confirm",
            _location_no_response=denial,
            _location_card=geo,
            _extra_steps=[nation for nation in [build_nation_callback(game_state)] if nation],
        )
    if country:
        return _q(
            "The network puts you in %s.\nAm I wrong?" % country,
            ["Yes", "No"],
            "location_confirm",
            _location_no_response="Then you are hiding somewhere else.\nWe keep the rest.",
            _location_card=geo,
        )
    return _q(
        "The network puts you somewhere I can almost name.\nAm I close?",
        ["Yes", "No"],
        "location_confirm",
        _location_no_response="Close enough.\nWe keep the rest.",
        _location_card=None,
    )


def _processes_question(game_state):
    procs = os_layer.get_cached_processes()
    if procs.get("roblox"):
        q = "Roblox is running. I hope you weren't planning to play a game."
    elif procs.get("discord"):
        q = "Discord is running. I hope you weren't planning to start a conversation."
    elif procs.get("telegram"):
        q = "Telegram is running. I hope you weren't planning to send a message."
    else:
        q = "Your running processes are... quiet.\nToo quiet."
    extra = []
    contradiction = discord_voice_contradiction(game_state)
    if contradiction:
        extra.append(contradiction)
    return _q(q, ["...", "How do you know that?"], "processes", _extra_steps=extra)


def _apps_question(game_state):
    comment = os_layer.comment_on_open_apps()
    if not comment:
        comment = "Your running processes are... quiet.\nToo quiet."
    return _q(comment, ["...", "Leave them out of this"], "apps")


def resolve_dynamic(kind, game_state, run_count):
    """Resolve a `dynamic_pending` step off the render thread.

    Returns {"q": str, "opts": [...], "meta": {...}, "extra": [steps]}.
    """
    if kind == "location" and config.ENABLE_LOCATION:
        step = _location_question(game_state)
    elif kind == "processes":
        step = _processes_question(game_state)
    elif kind == "apps":
        step = _apps_question(game_state)
    else:
        step = _q("Are you still there?", ["...", "..."], "fallback")
    # Keep the script's own `_id` (e.g. "location"), exactly like Classic, so
    # the answer is filed under a stable key. Only carry the response metadata.
    meta = {k: v for k, v in step.items()
            if k.startswith("_") and k not in ("_id", "_injected", "_extra_steps")}
    return {
        "q": step["q"],
        "opts": step["opts"],
        "meta": meta,
        "extra": step.get("_extra_steps") or [],
    }


# --- Contradiction / Discord voice call --------------------------------------
def discord_voice_contradiction(game_state):
    """If Discord is running but the player claimed to be alone, flag it.

    Only process presence is checked — never message content or call members.
    """
    if not config.ENABLE_CONTRADICTIONS:
        return None
    if not os_layer.get_cached_processes().get("discord"):
        return None
    alone = game_state.get("answers", {}).get("alone")
    if alone == "Yes":
        return _q(
            "Discord is open.\nIf you were truly alone, who exactly were you about to talk to?",
            ["No one", "I forgot it was open", "..."],
            "discord_contradiction",
        )
    return None


def contradiction_rephrase(step, game_state):
    """Rewrite an `alone2`-style step to call out the earlier answer."""
    prev = game_state.get("answers", {}).get("alone")
    if prev == "Yes":
        step = dict(step)
        step["q"] = "Earlier you said you were alone.\nWhat changed?"
    elif prev == "No":
        step = dict(step)
        step["q"] = "You mentioned not being alone before.\nAre they still there?"
    return step


# --- Memory / intimate callbacks ---------------------------------------------
_COLOR_REMARKS = {
    "blue": "Blue is a strange choice.\nMost people choose warmer colors.",
    "green": "Green is interesting.\nMost people only like it because it feels peaceful.",
    "red": "Red. Fitting. An aggressive choice for someone sitting so still.",
    "black": "Black. Of course. You like the dark more than you admit.",
    "white": "White. Clinical. Sterile. Like you are trying to erase something.",
    "yellow": "Yellow.\nCheerful on the surface. But yellow fades so easily.",
    "purple": "Purple. Royalty, or loneliness? Hard to tell the difference.",
    "cyan": "Cyan. A color most people cannot even name correctly.",
}

def build_color_memory(fav_color):
    if not fav_color:
        return None
    remark = _COLOR_REMARKS.get(fav_color.lower(), "You chose %s. Interesting." % fav_color)
    return _q(remark, ["...", "Leave me alone"], "color_memory")


def build_preknowledge_color(fav_color):
    if not fav_color:
        return None
    return _q(
        "Your favorite color is %s.\nCorrect?" % fav_color,
        ["Confirm", "That's wrong"],
        "preknowledge_color",
        _preknowledge_wrong_response="...That's not what I have written down.\nAnswer again.",
    )


FALSE_MEMORY_LINES = [
    "Earlier you told me you don't sleep well.\nWhy did you lie about that just now?",
    "You said this wasn't the first time you've felt like this.\nDo you remember saying that?",
    "We have it written down that you hesitated on the very first question.\n"
    "You didn't think we'd notice the pattern.",
]

FALSE_MEMORY_REBUTTALS = {
    "I never said that": "I have it written down.\nDo you want to see it?",
    "Liar": "That's the second one.",
}

def build_false_memory():
    return _q(
        random.choice(FALSE_MEMORY_LINES),
        ["I never said that", "Liar"],
        "false_memory",
        _false_memory_response=True,
    )


_LORE = [
    ("They told us you would say that.", ["Who?", "..."], "lore_they_said"),
    ("This is not the first time we've spoken.", ["I don't remember", "I know"], "lore_not_first"),
    ("We are not the only ones who do this.\nWe are simply the ones who told you.",
     ["...", "What does that mean?"], "lore_not_only"),
    ("You are doing exactly what the last one did.",
     ["...", "The last one?"], "lore_last_one"),
]

def build_lore(index=0):
    q, opts, _id = _LORE[index % len(_LORE)]
    return _q(q, opts, _id)


def build_siblings_fate():
    return _q(
        "If something were to happen tonight,\nwould your siblings notice?",
        ["Yes", "No", "I don't know"],
        "siblings_fate",
    )


def build_glass():
    return _q(
        "Could someone be on the other side of the glass?\nAnswer slowly.",
        ["Yes", "No"],
        "glass",
    )


def build_machine_aware():
    return _q(
        "Do you know what this machine is doing right now?\nIt is watching you answer this.",
        ["No", "Don't tell me"],
        "machine_aware",
    )


def build_taskmgr_comment(step_index):
    import platform
    name = "Task Manager" if platform.system() == "Windows" else "Activity Monitor"
    return _q(
        "I see you opened the %s.\nThat's the only way out, you know." % name,
        ["...", "Good to know"],
        "taskmgr_comment_%s" % step_index,
    )


def build_camera_intro():
    """Classic opened the webcam and *told* you it could see you."""
    return _q(
        "I am turning on the camera now.\nI would like to see who is answering.",
        ["Fine", "Turn it off"],
        "camera_intro",
        action="start_webcam",
    )


def build_nation_callback(game_state):
    """Reference the player's country once we know it (Classic's location bite)."""
    geo = os_layer.get_cached_geo() if hasattr(os_layer, "get_cached_geo") else {}
    country = geo.get("country", "")
    region = geo.get("region", "")
    if not country:
        city, country = os_layer.get_cached_location()
    if not country:
        return None
    lines = [
        "People in %s usually answer that way." % country,
        "We have others in %s.\nYou are not the only one awake tonight." % country,
    ]
    if region:
        lines.append("How is %s this time of night?" % region)
    return _q(random.choice(lines), ["...", "How do you know that?"], "nation_callback",
              _nation=country)


# --- Hesitation --------------------------------------------------------------
_HESITATION_LINES = [
    "You took a while.\nAre you answering truthfully?",
    "That hesitation was noted.",
    "Most people answer faster.\nWhat were you thinking about?",
    "Interesting. You paused before responding.",
    "You took longer than expected.\nIs something bothering you?",
    "Twenty seconds is a long time to think about a yes or no.",
]

def build_hesitation():
    return _q(random.choice(_HESITATION_LINES), ["...", "I was thinking"], "hesitation")


# --- Tailored reactions to the opening's authored answers --------------------
ANSWER_REACTIONS = {
    "alone": {
        "Yes": "Good.\nThen no one will hear you.",
        "No": "Then who is it?\nThey will not help you.",
    },
    "afraid_dark": {
        "Yes": "That is why we keep the lights low.",
        "No": "You will.",
    },
    "hurt_someone": {
        "Yes": "We already knew.\nWe just wanted you to say it out loud.",
        "No": "Everyone has.\nYou are just quicker to forget.",
    },
    "lied": {
        "Yes": "Thank you for being honest about the dishonesty.",
        "No": "That is the second lie.",
    },
    "siblings": {
        "Yes": "Good. That means someone would notice.",
        "No": "Then the house is very quiet at night.",
        "It's complicated": "It always is.",
    },
    "has_window": {
        "Yes": "So there is a way in that is not the door.",
        "No": "Then there is only one door.\nWe know where it is.",
    },
    "r2_why_back": {
        "Curiosity": "Curiosity is how most of them start.",
        "I couldn't stop myself": "That is the honest answer.\nWe prefer those.",
        "I don't know": "We know.",
    },
    "r2_told": {
        "Yes": "Then they are part of this now.",
        "No": "Good. Keep it that way.\nFor their sake.",
    },
    "r3_counts": {
        "Yes": "Then you asked for this.",
        "No": "We will tell you anyway.",
    },
}

_FAST_ANSWER_LINES = [
    "You answered that too quickly.",
    "You didn't even read it, did you?",
    "Fast. Practiced. Like you already knew the question.",
]

_FAST_SUPPRESS_IDS = {
    "false_memory", "preknowledge_color", "hesitation", "location", "location_confirm",
    "color_memory", "processes", "apps", "glass", "machine_aware",
    "siblings_fate", "lore_they_said", "lore_not_first", "lore_not_only",
    "lore_last_one", "discord_contradiction",
}


def after_answer(step, answer, elapsed, game_state, run_count):
    """Build the follow-up questions to insert after an answered step.

    Mirrors Classic's `save_answer` + follow-up pipeline: rebuttals for the
    flagged question kinds, hesitation call-outs, tailored reactions, and
    occasional fast-answer call-outs. Never recurses (injected steps are
    excluded).
    """
    followups = []

    # Rebuttals for flagged questions — these apply to injected/flagged steps
    # too (e.g. the location-denial rebuttal on a dynamic question).
    if step.get("_false_memory_response"):
        line = FALSE_MEMORY_REBUTTALS.get(answer)
        if line:
            followups.append(_q(line, ["...", "Fine"], "false_memory_rebuttal"))
    if step.get("_preknowledge_wrong_response") and answer == "That's wrong":
        followups.append(_q(step["_preknowledge_wrong_response"],
                            ["...", "Fine, it's correct"], "preknowledge_rebuttal"))
    if step.get("_location_no_response") and answer == "No":
        followups.append(_q(step["_location_no_response"],
                            ["...", "That's not true"], "location_rebuttal"))

    # Everything below is for authored questions only; injected lines must not
    # trigger it or they would chain forever.
    if step.get("_injected"):
        return followups

    # Hesitation call-out
    if config.ENABLE_HESITATION_CALLOUT and elapsed > config.HESITATION_THRESHOLD:
        followups.append(build_hesitation())

    # Tailored reaction to the answer (gated so the opening doesn't feel like a
    # call-and-response loop).
    react = ANSWER_REACTIONS.get(step.get("_id", ""), {})
    if answer in react and random.random() < REACTION_CHANCE:
        followups.append(_q(react[answer], ["...", "Stop"], "reaction_" + step.get("_id", "")))

    # Fast-answer call-out — never on injected lines, so it cannot recurse
    if (not followups and run_count == 1 and elapsed < 1.0
            and step.get("_id") not in _FAST_SUPPRESS_IDS and random.random() < 0.25):
        followups.append(_q(random.choice(_FAST_ANSWER_LINES), ["...", "I was quick"], "fast_answer"))

    return followups
