#!/usr/bin/env python3
"""Tests for the standalone operator sender.

Runs headless. Two halves, like every other suite here:

  * UI: the sender builds, draws, navigates and refuses to send without a
    token — no network at all.
  * Live: a real relay is started in-process and the sender actually fires a
    question at a real receiving client, which answers it, and the verdict
    comes back. This is the whole point of the app, so it is tested end to end.
"""
import importlib.util
import json
import os
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
app.help = False

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

    # And a dead relay is reported as a failure, not as a success.
    import importlib as _il  # noqa: E402
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
