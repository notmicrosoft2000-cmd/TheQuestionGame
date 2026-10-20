"""Session script builder.

Every session opens with a short human-authored block (the fixed opening),
then the scary AI writes the rest, with a guaranteed offline fallback. Each
run escalates: run 1 ends with a normal exit, run 2 puts the machine to sleep,
run 3 is the real ending that bricks the save.
"""
from . import config


def _step(q, opts, _id, action=None, scare=None, **extra):
    s = {"q": q, "type": "choice", "opts": list(opts), "_id": _id}
    if action:
        s["action"] = action
    if scare:
        s["scare"] = scare
    s.update(extra)
    return s


def _wait_step(q, seconds, action=None):
    s = {"q": q, "type": "wait", "time": seconds, "_id": "end"}
    if action:
        s["action"] = action
    return s


def _dynamic_step(_id, kind):
    """A question whose text is built from real machine state at show time.

    main.py resolves these in a worker thread (like the AI placeholders), so
    the probe never stalls the render loop. `kind` is one of location /
    processes / apps — see interjections.resolve_dynamic().
    """
    return {"q": None, "type": "dynamic_pending", "opts": [], "_id": _id, "_resolver": kind}


def _remembered_answers(game_state, limit=3):
    """Pull the player's own earlier words out of the save file.

    Returns short, quotable strings (e.g. "favorite color -> blue") used to
    make runs 2 and 3 feel like the machine actually kept notes on them.
    """
    answers = game_state.get("answers", {}) or {}
    pleasant = {
        "fav_color": "your color",
        "has_window": "the window",
        "alone": "being alone",
        "afraid_dark": "the dark",
        "siblings": "your siblings",
    }
    out = []
    for key, label in pleasant.items():
        val = answers.get(key)
        if val:
            out.append("%s: %s" % (label, val))
    return out[:limit]


def _build_fixed_opening(run_count, game_state):
    """Human-authored opening per run. Returns the fixed steps list.

    These carry Classic's personality: machine-aware dynamic questions,
    contradiction callbacks, conditional branches, and injected lore. The AI
    fills the spaces between them (see `_interleave`).
    """
    steps = []
    if run_count == 1:
        steps.append(_step(
            "This program has been waiting for you.\nIt does not know how long.\nIt does not care anymore.",
            ["I'm here", "...", "I'm not ready"], "intro"))
        steps.append(_step("Are you alone right now?", ["Yes", "No"], "alone"))
        steps.append(_step("Are you afraid of the dark?", ["Yes", "No"], "afraid_dark"))
        steps.append(_step("Have you ever hurt someone on purpose?", ["Yes", "No"], "hurt_someone"))
        steps.append(_step("Do you have siblings?", ["Yes", "No", "It's complicated"], "siblings"))
        steps.append(_step("Have you ever lied about something important?", ["Yes", "No"], "lied"))
        steps.append(_step("Is there a window in your room?", ["Yes", "No"], "has_window"))
        # Conditional: only if there is a window.
        steps.append(_step("Are the blinds open?", ["Yes", "No"], "blinds",
                           _condition=("has_window", "Yes")))
        steps.append(_step("Could someone be on the other side of the glass?\nAnswer slowly.",
                           ["Yes", "No"], "glass"))
        steps.append(_step(
            "What is your favorite color?",
            config.FAV_COLOR_OPTIONS, "fav_color", action="save_color"))
        # Machine-aware questions, built from what is actually running / where
        # you actually are. Resolved off-thread by main.py.
        steps.append(_dynamic_step("processes", "processes"))
        steps.append(_dynamic_step("location", "location"))
        # Classic turned the camera on and said so. Run 1 gets its own beat.
        steps.append(_step(
            "I am turning the camera on now.\nI would like to see who is answering.",
            ["Fine", "Turn it off"], "r1_camera", action="start_webcam"))
        steps.append(_step(
            "Do you know what this machine is doing right now?\nIt is watching you answer this.",
            ["No", "Don't tell me"], "machine_aware"))
        steps.append(_step("They told us you would say that.", ["Who?", "..."], "lore_they_said"))
        # "Are you alone?" asked a second time — then thrown back at you.
        steps.append(_step("Are you alone?", ["Yes", "No"], "alone2",
                           _contradiction_check="alone"))
    elif run_count == 2:
        remembered = _remembered_answers(game_state)
        if remembered:
            steps.append(_step(
                "We kept what you gave us:\n%s\n\nWe have been reading it back." % "\n".join(remembered),
                ["Delete it", "..."], "r2_kept_notes"))
        steps.append(_step("Why did you come back?", ["Curiosity", "I couldn't stop myself", "I don't know"], "r2_why_back"))
        steps.append(_step("We remember everything you said.", ["I know", "I forgot"], "r2_remember"))
        steps.append(_step("The wallpaper behind this window is your color now.", ["I see it", "Change it back"], "r2_wallpaper"))
        steps.append(_step("Your camera is active.", ["I see it", "Turn it off"], "r2_camera", action="start_webcam"))
        steps.append(_step("Have you told anyone you are playing this?", ["Yes", "No"], "r2_told"))
        # It makes you look at your own desktop while it names what it sees.
        steps.append(_step("Why is your desktop so cluttered?",
                           ["I have a reason", "Not your business."], "desktop_check",
                           action="desktop_check"))
        steps.append(_dynamic_step("apps", "apps"))
        steps.append(_step("This is not the first time we've spoken.",
                           ["I don't remember", "I know"], "lore_not_first"))
    elif run_count == 3:
        h = game_state.get("hesitation_count", 0)
        l = game_state.get("lie_count", 0)
        remembered = _remembered_answers(game_state, limit=5)
        name = ""
        try:
            from . import os_layer
            name = os_layer.get_cached_username() or ""
        except Exception:
            name = ""
        opener = "You were told not to return.\nAnd yet here you are."
        if name:
            opener = "You were told not to return, %s.\nAnd yet here you are." % name
        steps.append(_step(
            opener,
            ["I know", "I had to"], "r3_open", action="r3_intro_shake"))
        steps.append(_step(
            "We counted your hesitations.\nWe counted your contradictions.\nDo you want to know the numbers?",
            ["Yes", "No"], "r3_counts"))
        steps.append(_step(
            "You hesitated %d times.\nYou contradicted yourself %d times.\nWe have it all." % (h, l),
            ["...", "That's not right"], "r3_reveal_counts", action="r3_window_shake"))
        if remembered:
            steps.append(_step(
                "And we still have everything you told us the first time:\n%s" % "\n".join(remembered),
                ["...", "Delete it"], "r3_kept_notes"))
        steps.append(_step("We don't need permission anymore.", ["What?", "Stop"], "r3_no_permission", action="r3_open_webcam"))
        steps.append(_dynamic_step("processes", "processes"))
        steps.append(_step("You are doing exactly what the last one did.",
                           ["...", "The last one?"], "lore_last_one"))
    return steps


def _build_ai_placeholders(run_count, count=None):
    """Placeholder steps filled lazily by main.py in background threads.

    v2 built every AI question up front (up to 12 blocking HTTP calls with
    30s timeouts — the startup stall). v3 shows THINKING dots and fetches
    each question while the player waits, and can even prefetch ahead.
    """
    steps = []
    total = count if count is not None else config.AI_QUESTION_COUNT.get(run_count, 8)
    for i in range(total):
        steps.append({
            "q": None,
            "type": "ai_pending",
            "opts": [],
            "_id": "ai_%d_%d" % (run_count, i),
        })
    return steps


def _interleave(fixed, ai_count, opens_at, every):
    """Weave AI placeholders through the authored opening.

    The first `opens_at` authored beats stay fixed (the human-written hook),
    then one AI question is dropped in after roughly every `every` authored
    beats. Anything left over trails the opening, so the AI gets the last word
    before the ending. This is what makes each playthrough feel newly written
    instead of replaying the same 16 questions.
    """
    ai_steps = _build_ai_placeholders(0, ai_count)
    if not ai_steps:
        return list(fixed)

    out = []
    pool = list(ai_steps)
    authored_seen = 0
    emitted = 0
    for idx, step in enumerate(fixed):
        out.append(step)
        emitted += 1
        # The very first AI question lands immediately after `opens_at` authored
        # beats; the rest alternate every `every` beats.
        if pool:
            if emitted == opens_at:
                out.append(pool.pop(0))
            else:
                authored_seen += 1
                if emitted > opens_at and authored_seen % max(1, every) == 0:
                    out.append(pool.pop(0))
    # Any AI questions that did not fit mid-script run after the opening.
    out.extend(pool)
    return out


def _build_ending(run_count):
    if run_count == 1:
        return [_wait_step(
            "We have what we need.\nFor now.\n\nRest.\n\n"
            "Now close this window.\nOpen it again when you are ready for the next session.",
            4.0, action="final_exit")]
    if run_count == 2:
        return [_wait_step(
            "We have collected everything we need.\nThank you for participating.\n\n"
            "Close this window.\nOpen it again. One session remains.",
            4.0, action="final_exit_sleep")]
    if run_count == 3:
        return [_wait_step(
            "Good.\nThat was always the answer.\n\n"
            "Now close it.\nAnd do not open this again.",
            5.0, action="r3_final_end")]
    return [_wait_step(
        "It is over.\nWe said goodbye.\n\n"
        "Close the window.\nLeave it closed.",
        5.0, action="final_exit")]


def build_session(game_state, ai=None):
    """Returns the full list of steps for the current run."""
    run_count = game_state.get("run_count", 1)
    if run_count >= 4:
        return _build_ending(run_count)

    fixed = _build_fixed_opening(run_count, game_state)
    ai_count = config.AI_QUESTION_COUNT.get(run_count, 8)
    opens_at = config.AI_OPENS_AT.get(run_count, 5)
    every = config.AI_INTERLEAVE_EVERY
    steps = _interleave(fixed, ai_count, opens_at, every)
    steps += _build_ending(run_count)
    return steps
