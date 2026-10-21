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

# Compose text is tracked and cleared by fire().
app.draw()
check("compose text is tracked", app.fields["q"] == "will not send")
app.fields["q"] = ""
app.fields["o0"] = ""
app.fields["o1"] = ""
app.social.stop()
pygame.quit()

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

    app.recipient = {"id": "receiver0001", "name": "RECEIVER"}
    app.fields["q"] = "what colour is the sky?"
    app.fields["o0"] = "blue"
    app.fields["o1"] = "green"
    app.fields["correct"] = 0
    app.fire()
    check("sender reports a successful send",
          app.toast is not None and app.toast["tone"] == "good", app.toast)
    check("sender clears the form after a send", app.fields["q"] == "", app.fields)

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

    check("receiver answers without any token", player.send_answer(got, "blue", True) is True)
    check("verdict reaches the sender",
          wait_until(lambda: any(r.get("by") == "receiver" for r in app.social.take_results()), 6),
          app.results)
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
