#!/usr/bin/env python3
"""Tests for the standalone operator sender.

Runs headless. Two halves, like every other suite here:

  * UI: the sender builds, draws, navigates and refuses to send without a
    token — no network at all.
  * Live: a real relay is started in-process and the sender actually fires a
    question at a real receiving client, which answers it, and the verdict
    comes back. This is the whole point of the app, so it is tested end to end.
"""
import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO, "tools", "sender"))
sys.path.insert(0, os.path.join(_REPO, "games", "remastered"))
os.environ["TQG_DATA_DIR"] = tempfile.mkdtemp()

FAILS = []


def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else " :: %s" % (extra,)))
    if not cond:
        FAILS.append(name)


def _action(screen, kind, idx=None):
    """Find a visible button recorded by the last draw."""
    for rect, k, i in screen.action_rects:
        if k == kind and (idx is None or i == idx):
            return rect
    return None


def _tap(screen, kind, idx=None):
    rect = _action(screen, kind, idx)
    if rect is None:
        return False
    screen.handle_click(rect.center)
    return True


def _no_key_hints(path):
    """Player-facing sender copy must not teach keys or shortcuts."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    pattern = re.compile(
        r"\[[A-Z0-9/]+\]|\bF[1-9]\b|\bENTER\b|\bESC\b|\bTAB\b|"
        r"\bUP/DOWN\b|\bLEFT/RIGHT\b|\bSPACE\b|\bCTRL\b|"
        r"\bARROW\b|\bpress\b", re.I)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings and pattern.search(n.value)]


def load_relay():
    path = os.path.join(_REPO, "server", "relay.py")
    spec = importlib.util.spec_from_file_location("relay_sender_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wait_until(pred, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


print("== sender: UI, no network ==")
import pygame  # noqa: E402
import sender as sender_mod  # noqa: E402
from TheQuestionGameRemastered import config  # noqa: E402

os.environ["TQG_SEND_TOKEN"] = ""
app = sender_mod.Sender()
app.now = 1.0
try:
    app.draw()
    check("sender draws while offline", True)
except Exception as exc:
    check("sender draws while offline", False, repr(exc))

check("every operation has a visible button",
      all(_action(app, kind) is not None for kind in
          ("help", "message", "effects", "triggers", "quit")),
      [(k, i) for _, k, i in app.action_rects])
check("no server token means no visible FORGET TOKEN button",
      _action(app, "forget") is None, app.action_rects)
_hints = _no_key_hints(sender_mod.__file__)
check("the sender never teaches a key or shortcut in its copy",
      not _hints, _hints)

check("no token means sending is refused up front", app._can_send_now() is False)
app.fields["q"] = "will not send"
app.fields["o0"] = "a"
app.fields["o1"] = "b"
app.fire()
check("fire() without a token warns instead of sending",
      app.toast is not None and "TOKEN" in app.toast["text"], app.toast)
check("fire() without a token queues nothing",
      app.sent_log == [], app.sent_log)

# Compose text is tracked and cleared by fire().
app.draw()
check("compose text is tracked", app.fields["q"] == "will not send")
app.fields["q"] = ""
app.fields["o0"] = ""

# The token can come from <repo>/tqg-token.txt as well as the environment.
_tok_file = sender_mod.REPO_TOKEN_FILE
_keep = None
try:
    if os.path.exists(_tok_file):
        with open(_tok_file, encoding="utf-8") as fh:
            _keep = fh.read()
    os.environ.pop("TQG_SEND_TOKEN", None)
    with open(_tok_file, "w", encoding="utf-8") as fh:
        fh.write("from-the-file-token\n")
    _tok, _src = sender_mod.resolve_token()
    check("a token is read from tqg-token.txt",
          _tok == "from-the-file-token" and _src == "tqg-token.txt", (_tok, _src))
    with open(_tok_file, "w", encoding="utf-8") as fh:
        fh.write("RELAY_SEND_TOKEN=key-value-token\n")
    _tok, _src = sender_mod.resolve_token()
    check("a KEY=value token file is understood too",
          _tok == "key-value-token", _tok)
    os.environ["TQG_SEND_TOKEN"] = "from-the-env"
    _tok, _src = sender_mod.resolve_token()
    check("the environment still wins", _tok == "from-the-env", _tok)
    os.environ["TQG_SEND_TOKEN"] = ""
    _tok, _src = sender_mod.resolve_token()
    check("an explicitly empty environment stops the search", _tok == "", _tok)
finally:
    os.environ.pop("TQG_SEND_TOKEN", None)
    try:
        if _keep is None:
            os.remove(_tok_file)
        else:
            with open(_tok_file, "w", encoding="utf-8") as fh:
                fh.write(_keep)
    except OSError:
        pass

# The token screen draws, and the help screen fits inside the window.
app.unlocking = True
try:
    app.draw()
    check("the token screen draws", True)
except Exception as exc:
    check("the token screen draws", False, repr(exc))
app.unlocking = False
app.help = True
try:
    app.draw()
    check("the help screen draws", True)
except Exception as exc:
    check("the help screen draws", False, repr(exc))
check("the help screen has its own visible BACK",
      _action(app, "back") is not None, app.action_rects)
check("the visible BACK leaves the help screen",
      _tap(app, "back") and app.help is False, app.help)

# The effects screen: the operator can fire a scare or glitch by hand. It must
# draw, the list must come from the game's own registry, and the keys must move
# the selection and the intensity without ever leaving the screen.
check("the effects list is loaded from the game",
      isinstance(app.effects, (list, tuple)) and len(app.effects) >= 10,
      len(app.effects))
check("the effects list contains real scares",
      "flicker" in app.effects and "whisper" in app.effects, app.effects[:5])
app.effects_screen = True
try:
    app.draw()
    check("the effects screen draws", True)
except Exception as exc:
    check("the effects screen draws", False, repr(exc))
check("the effects screen has visible pick, power, fire and BACK buttons",
      all(_action(app, kind, idx) is not None for kind, idx in
          (("effects_pick", 1), ("effects_power", 1), ("effects_fire", 0),
           ("back", 0))), app.action_rects)
check("an effect row is chosen by tapping it",
      _tap(app, "effects_pick", 1) and app.effect_index == 1, app.effect_index)
_power_before = app.effect_intensity
check("the power button changes the intensity",
      _tap(app, "effects_power", 1) and app.effect_intensity > _power_before,
      app.effect_intensity)

app.effect_index = 0
app.effect_intensity = 1.0
app._handle_effects_key(type("E", (), {"key": pygame.K_DOWN, "unicode": ""})())
check("down moves the effect selection", app.effect_index == 1, app.effect_index)
app._handle_effects_key(type("E", (), {"key": pygame.K_RIGHT, "unicode": ""})())
check("right raises the intensity", app.effect_intensity > 1.0,
      app.effect_intensity)
app._handle_effects_key(type("E", (), {"key": pygame.K_LEFT, "unicode": ""})())
check("left lowers the intensity", abs(app.effect_intensity - 1.0) < 1e-9,
      app.effect_intensity)
for _ in range(12):
    app._handle_effects_key(type("E", (), {"key": pygame.K_RIGHT, "unicode": ""})())
check("intensity is capped so a scare cannot be made absurd",
      app.effect_intensity <= 2.0, app.effect_intensity)
for _ in range(20):
    app._handle_effects_key(type("E", (), {"key": pygame.K_LEFT, "unicode": ""})())
check("intensity has a floor, it cannot reach zero",
      app.effect_intensity >= 0.5, app.effect_intensity)
app._handle_effects_key(type("E", (), {"key": pygame.K_ESCAPE, "unicode": ""})())
check("escape leaves the effects screen",
      app.effects_screen is False, app.effects_screen)
app.effects_screen = False

# --- scare triggers: bind a scare to an answer option (F3) -------------------
check("one empty trigger slot per option",
      isinstance(app.triggers, list) and len(app.triggers) == 4, app.triggers)
check("no rules are configured by default", app._trigger_rules() == [],
      app._trigger_rules())


def _tkey(key):
    return type("E", (), {"key": key, "unicode": ""})()


app.handle_key(_tkey(pygame.K_F3))
check("the trigger shortcut still opens the editor silently",
      app.triggers_screen is True)
try:
    app.draw()
    check("the trigger editor draws", True)
except Exception as exc:
    check("the trigger editor draws", False, repr(exc))
check("the trigger editor exposes visible slot, effect, power, clear and BACK",
      all(_action(app, kind, idx) is not None for kind, idx in
          (("trigger_slot", 1), ("trigger_cycle", 1), ("trigger_power", 1),
           ("trigger_clear", 0), ("back", 0))), app.action_rects)
check("an option slot is chosen by tapping it",
      _tap(app, "trigger_slot", 2) and app.trigger_slot == 2, app.trigger_slot)
check("the visible effect button creates a rule",
      _tap(app, "trigger_cycle", 1) and len(app._trigger_rules()) == 1
      and app._trigger_rules()[0]["option"] == 2, app._trigger_rules())
_power_before = app._trigger_rules()[0]["intensity"]
check("the visible power button raises a rule's power",
      _tap(app, "trigger_power", 1)
      and app._trigger_rules()[0]["intensity"] > _power_before,
      app._trigger_rules())
check("the visible CLEAR button removes the rule",
      _tap(app, "trigger_clear") and app._trigger_rules() == [],
      app._trigger_rules())

app.trigger_slot = 0
app._handle_triggers_key(_tkey(pygame.K_RIGHT))
_rules = app._trigger_rules()
check("picking an effect creates a rule for that option",
      len(_rules) == 1 and _rules[0]["option"] == 0, _rules)
check("the rule names a real effect",
      _rules[0]["effect"] == app.effects[0], _rules)
_before_power = _rules[0]["intensity"]
app._handle_triggers_key(_tkey(pygame.K_RIGHTBRACKET))
check("the bracket key raises a rule's power",
      app._trigger_rules()[0]["intensity"] > _before_power, app._trigger_rules())
app._handle_triggers_key(_tkey(pygame.K_DOWN))
check("down moves to the next option slot", app.trigger_slot == 1, app.trigger_slot)
app._handle_triggers_key(_tkey(pygame.K_BACKSPACE))
check("delete clears the selected (empty) slot without touching the other",
      len(app._trigger_rules()) == 1, app._trigger_rules())
app.trigger_slot = 0
app._handle_triggers_key(_tkey(pygame.K_DELETE))
check("delete clears a configured rule", app._trigger_rules() == [],
      app._trigger_rules())
app._handle_triggers_key(_tkey(pygame.K_F3))
check("the trigger shortcut still closes the editor silently",
      app.triggers_screen is False)

# The jumpscare shortcut still works, but nothing on screen names it.

app.sent_log = []
app.toast = None
app._fire_jumpscare()
check("the silent jumpscare shortcut queues an effect",
      any("JUMPSCARE" in str(e.get("q", "")).upper() for e in app.sent_log),
      app.sent_log)
check("the jumpscare is announced without naming a key",
      app.toast is not None and "JUMPSCARE" in app.toast["text"], app.toast)

# --- short operator transmissions -------------------------------------------
check("MESSAGE is a visible operation", _tap(app, "message")
      and app.message_screen is True, app.message_screen)
try:
    app.draw()
    check("the message composer draws", True)
except Exception as exc:
    check("the message composer draws", False, repr(exc))
check("the message composer has visible BACK and SEND MESSAGE buttons",
      _action(app, "back") is not None
      and _action(app, "message_send") is not None, app.action_rects)

app.message_text = ""
for ch in "DO NOT TRUST THE SILENCE":
    app._handle_message_key(type("E", (), {"key": 0, "unicode": ch})())
check("a short transmission can be typed",
      app.message_text == "DO NOT TRUST THE SILENCE", app.message_text)

app.sent_log = []
app.toast = None
check("the visible SEND MESSAGE button sends",
      _tap(app, "message_send"), app.action_rects)
check("a message without a token warns instead of queueing",
      app.toast is not None and "TOKEN" in app.toast["text"]
      and app.sent_log == [], (app.toast, app.sent_log))

check("the message composer's BACK button works",
      _tap(app, "back") and app.message_screen is False, app.message_screen)

# A long question wraps instead of being cut off with an ellipsis: every word
# of a 200-character question ends up on screen somewhere in the form.
app.fields["q"] = ("What is the airspeed velocity of an unladen swallow, and "
                   "does the answer change if the swallow is carrying a "
                   "coconut?")
app.fields["o0"] = "African or European?"
app.fields["o1"] = "It depends entirely on the coconut"
app.focus = 1
app.draw()
_wrapped = sender_mod._wrap(app.fields["q"], app.font_med,
                            app.rect_comp.width - 30)
check("a long question wraps over several lines", len(_wrapped[0]) >= 3, _wrapped)
check("wrapping keeps every word",
      " ".join(_wrapped[0]) == app.fields["q"], _wrapped)
check("no ellipsis in the wrapped question",
      "..." not in " ".join(_wrapped[0]), _wrapped)

app.social.stop()
pygame.quit()

print("== sender: the token gate ==")
# A token that does not match the relay must be refused, and it must be
# refused *by the relay*, not by a guess.
mod = load_relay()
mod.RELAY_KEY = ""
mod.RELAY_APP_TOKEN = ""
mod.SEND_TOKEN = "operator-secret"
srv = mod.ThreadingHTTPServer(("127.0.0.1", 8108), mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
config.SOCIAL_URL = "http://127.0.0.1:8108"

state, detail = sender_mod.probe_token("operator-secret")
check("the relay accepts the right token", state == "ok", (state, detail))
state, detail = sender_mod.probe_token("wrong-token")
check("the relay refuses a wrong token", state == "bad", (state, detail))
check("the refusal explains itself", "restricted" in (detail or ""), detail)

config.SOCIAL_URL = "http://127.0.0.1:9"      # nothing listening
state, detail = sender_mod.probe_token("operator-secret")
check("an unreachable relay is reported as offline", state == "offline", (state, detail))

config.SOCIAL_URL = "http://127.0.0.1:8108"
srv.shutdown()

print("== sender: end to end through a real relay ==")
os.environ["TQG_SEND_TOKEN"] = "operator-secret"
mod = load_relay()
mod.RELAY_KEY = ""
mod.RELAY_APP_TOKEN = ""
mod.SEND_TOKEN = "operator-secret"
srv = mod.ThreadingHTTPServer(("127.0.0.1", 8107), mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
os.environ["TQG_SOCIAL_URL"] = "http://127.0.0.1:8107"
# Rebuild config-derived values for the fresh URL.
import importlib  # noqa: E402
config.SOCIAL_URL = "http://127.0.0.1:8107"

import sender as sender_mod2  # noqa: E402
importlib.reload(sender_mod2)
from TheQuestionGameRemastered import social as social_mod  # noqa: E402

app = sender_mod2.Sender()
# The sender always joins as the operator identity from its own env.
player = social_mod.SocialClient("receiver0001", "receiver",
                                 base_url="http://127.0.0.1:8107",
                                 poll_secs=0.2, timeout=2, enabled=True,
                                 send_token="")
try:
    check("sender joins the room", wait_until(lambda: app.social.status() == "online", 5),
          app.social.status())
    check("receiver joins the room", wait_until(lambda: player.status() == "online", 5),
          player.status())
    check("sender can see the receiver",
          wait_until(lambda: any(p["id"] == "receiver0001" for p in app._others()), 5),
          app._others())
    check("sender holds the token", app._can_send_now() is True)
    check("the relay confirms the token",
          wait_until(lambda: app.token_state == "ok", 5), app.token_state)

    app.recipient = {"id": "receiver0001", "name": "RECEIVER"}
    app.fields["q"] = "what colour is the sky?"
    app.fields["o0"] = "blue"
    app.fields["o1"] = "green"
    app.fields["correct"] = 0
    app.fire()

    got = {}
    def _take():
        item = player.take_question()
        if item:
            got.update(item)
            return True
        return False
    check("receiver gets the sender's question", wait_until(_take, 6), got)
    check("question arrives intact",
          got.get("q") == "what colour is the sky?" and got.get("opts") == ["blue", "green"],
          got)
    check("the correct index survived", got.get("correct") == 0, got)

    # The send is only reported as delivered once the relay says so.
    check("the delivery log records it as delivered",
          wait_until(lambda: (app._harvest(),
                               app.sent_log and app.sent_log[0].get("state") == "DELIVERED")[1], 6),
          app.sent_log)
    check("the toast says it was delivered",
          wait_until(lambda: (app._harvest(),
                               app.toast and app.toast.get("tone") == "good")[1], 6),
          app.toast)
    check("the form was cleared after a send", app.fields["q"] == "", app.fields)

    check("receiver answers without any token", player.send_answer(got, "blue", True) is True)
    check("verdict reaches the sender",
          wait_until(lambda: any(r.get("by") == "receiver" for r in app.social.take_results()), 6),
          app.results)

    # The receiver's own connection test (the ONLINE screen's T option) hits
    # the same relay and must report a real answer in milliseconds.
    ok, detail, ms = player.test_connection()
    check("the receiver's connection test reaches the relay", ok is True, detail)
    check("the connection test reports a round trip", isinstance(ms, int) and ms >= 0,
          (detail, ms))
    check("the connection test keeps the room in sync",
          wait_until(lambda: any(p["id"] == "receiver0001" for p in player.online()), 3),
          player.online())

    # --- effects: firing a scare by hand ------------------------------------
    # The operator picks an effect and fires it at the receiver. It must arrive
    # through the same poll a question uses, carry the intensity, and leave the
    # question inbox untouched.
    app.recipient = {"id": "receiver0001", "name": "RECEIVER"}
    app.effects_screen = True
    app.effects = ["whisper", "screen_tear"]
    app.effect_index = 0
    app.effect_intensity = 1.75
    app._fire_effect()

    fired = {}
    def _take_effect():
        item = player.take_effect()
        if item:
            fired.update(item)
            return True
        return False
    check("receiver gets the fired effect", wait_until(_take_effect, 6), fired)
    check("the effect arrives by name", fired.get("effect") == "whisper", fired)
    check("the effect carries the intensity the operator set",
          abs(float(fired.get("intensity", 0)) - 1.75) < 0.01, fired)
    check("a fired effect is not delivered as a question",
          player.take_question() is None)
    check("the effects screen did not close after firing",
          app.effects_screen is True, app.effects_screen)
    app.effects_screen = False
    check("the delivery log records the effect",
          wait_until(lambda: (app._harvest(),
                              any("EFFECT" in str(e.get("q", ""))
                                  for e in app.sent_log))[1], 6),
          app.sent_log)

    # --- messages: a short transmission is not a question --------------------
    app.message_text = "DO NOT TRUST THE SILENCE"
    app.sent_log = []
    app.send_message()
    check("the operator can queue a message",
          any(str(e.get("q", "")).startswith("MESSAGE:")
              for e in app.sent_log), app.sent_log)
    got_msg = {}

    def _take_message():
        items = player.take_messages()
        if items:
            got_msg.update(items[0])
            return True
        return False

    check("receiver gets the operator's message", wait_until(_take_message, 6),
          got_msg)
    check("the message arrives intact",
          got_msg.get("message") == "DO NOT TRUST THE SILENCE", got_msg)
    check("the message carries the operator's name",
          bool(str(got_msg.get("from_name") or "").strip()), got_msg)
    check("a message is not delivered as a question",
          player.take_question() is None)
    check("a message is not delivered as an effect",
          player.take_effect() is None)
    check("the delivery log records the message",
          wait_until(lambda: (app._harvest(),
                              any(str(e.get("q", "")).startswith("MESSAGE:")
                                  and e.get("state") == "DELIVERED"
                                  for e in app.sent_log))[1], 6),
          app.sent_log)
    check("a delivered message clears its composer", app.message_text == "",
          app.message_text)

    # The receiver's reconnect logic: after the relay goes away and comes back,
    # the client must recover on its own and say so.
    _reconnect = social_mod.SocialClient("recon000001", "reconnector",
                                         base_url="http://127.0.0.1:8107",
                                         poll_secs=0.2, timeout=1, enabled=True,
                                         send_token="")
    try:
        check("a fresh client joins",
              wait_until(lambda: _reconnect.status() == "online", 5),
              _reconnect.status())
        _before = _reconnect.reconnects()
        check("a healthy client has no reconnects yet",
              _before == 0, _before)
    finally:
        _reconnect.stop()

    # A dead relay is reported as a failure, not as a success.
    _dead2 = social_mod.SocialClient("dead0002", "dead", base_url="http://127.0.0.1:9",
                                     poll_secs=0.2, timeout=1, enabled=True)
    try:
        check("a dead relay puts the client into reconnecting, not online",
              wait_until(lambda: _dead2.status() in ("reconnecting", "offline"), 4),
              _dead2.status())
        check("the client keeps trying rather than giving up",
              _dead2.status() != "disabled", _dead2.status())
    finally:
        _dead2.stop()

    # And a dead relay is reported as a failure, not as a success.
    _dead = social_mod.SocialClient("dead0001", "dead", base_url="http://127.0.0.1:9",
                                    poll_secs=30, timeout=1, enabled=False)
    _ok, _detail, _ms = _dead.test_connection(timeout=1)
    check("a dead relay fails the connection test", _ok is False, _detail)
    check("a dead relay is not reported as an empty room", _detail != "", _detail)
finally:
    try:
        app.social.stop()
    except Exception:
        pass
    player.stop()
    srv.shutdown()
    pygame.quit()

print()
if FAILS:
    print("SENDER_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("SENDER_OK")
