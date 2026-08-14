"""Session script builder.

Every session opens with a short human-authored block (the fixed opening),
then the scary AI writes the rest, with a guaranteed offline fallback. Each
run escalates: run 1 ends with a normal exit, run 2 puts the machine to sleep,
run 3 is the real ending that bricks the save.
"""
from . import ai_client
from . import config


def _step(q, opts, _id, action=None, scare=None):
    s = {"q": q, "type": "choice", "opts": list(opts), "_id": _id}
    if action:
        s["action"] = action
    if scare:
        s["scare"] = scare
    return s


def _wait_step(q, seconds, action=None):
    s = {"q": q, "type": "wait", "time": seconds, "_id": "end"}
    if action:
        s["action"] = action
    return s


def _build_fixed_opening(run_count, game_state):
    """Human-authored opening per run. Returns the fixed steps list."""
    steps = []
    if run_count == 1:
        steps.append(_step(
            "This program has been waiting for you.\nIt does not know how long.\nIt does not care anymore.",
            ["I'm here", "...", "I'm not ready"], "intro"))
        steps.append(_step("Are you alone right now?", ["Yes", "No"], "alone"))
        steps.append(_step("Are you afraid of the dark?", ["Yes", "No"], "afraid_dark"))
        steps.append(_step("Have you ever hurt someone on purpose?", ["Yes", "No"], "hurt_someone"))
        steps.append(_step("Have you ever lied about something important?", ["Yes", "No"], "lied"))
        steps.append(_step(
            "What is your favorite color?",
            config.FAV_COLOR_OPTIONS, "fav_color", action="save_color"))
    elif run_count == 2:
        steps.append(_step("Why did you come back?", ["Curiosity", "I couldn't stop myself", "I don't know"], "r2_why_back"))
        steps.append(_step("We remember everything you said.", ["I know", "I forgot"], "r2_remember"))
        steps.append(_step("The wallpaper behind this window is your color now.", ["I see it", "Change it back"], "r2_wallpaper"))
        steps.append(_step("Your camera is active.", ["I see it", "Turn it off"], "r2_camera", action="start_webcam"))
        steps.append(_step("Have you told anyone you are playing this?", ["Yes", "No"], "r2_told"))
    elif run_count == 3:
        steps.append(_step(
            "You were told not to return.\nAnd yet here you are.",
            ["I know", "I had to"], "r3_open", action="r3_intro_shake"))
        steps.append(_step(
            "We counted your hesitations.\nWe counted your contradictions.\nDo you want to know the numbers?",
            ["Yes", "No"], "r3_counts"))
        h = game_state.get("hesitation_count", 0)
        l = game_state.get("lie_count", 0)
        steps.append(_step(
            "You hesitated %d times.\nYou contradicted yourself %d times.\nWe have it all." % (h, l),
            ["...", "That's not right"], "r3_reveal_counts", action="r3_window_shake"))
        steps.append(_step("We don't need permission anymore.", ["What?", "Stop"], "r3_no_permission", action="r3_open_webcam"))
    return steps


def _build_ai_steps(run_count, ai, history):
    steps = []
    total = config.AI_QUESTION_COUNT.get(run_count, 8)
    for i in range(total):
        step = ai_client.next_question(ai, run_count, history)
        step["_id"] = "ai_%d_%d" % (run_count, i)
        step["type"] = "choice"
        if step.get("scare"):
            step.pop("_source", None)
        else:
            step.pop("_source", None)
            step.pop("scare", None)
        steps.append(step)
        # A history stub for the next AI call (answer is only known later).
        history.append({"q": step["q"], "a": "(recorded)"})
    return steps


def _build_ending(run_count):
    if run_count == 1:
        return [_wait_step(
            "We have what we need.\nFor now.\n\nRest.\nYou will hear from us.",
            3.5, action="final_exit")]
    if run_count == 2:
        return [_wait_step(
            "We have collected everything we need.\nThank you for participating.\n\nRest now.",
            3.5, action="final_exit_sleep")]
    if run_count == 3:
        return [_wait_step(
            "Good.\nThat was always the answer.\n\nGoodbye.\nThis file will not open again.",
            5.0, action="r3_final_end")]
    return [_wait_step(
        "It is over.\nWe said goodbye.\nYou are not supposed to be here.",
        5.0, action="final_exit")]


def build_session(game_state, ai=None):
    """Returns the full list of steps for the current run."""
    run_count = game_state.get("run_count", 1)
    if run_count >= 4:
        return _build_ending(run_count)

    history = []
    steps = _build_fixed_opening(run_count, game_state)
    for s in steps:
        history.append({"q": s["q"], "a": "(recorded)"})
    steps += _build_ai_steps(run_count, ai, history)
    steps += _build_ending(run_count)
    return steps
