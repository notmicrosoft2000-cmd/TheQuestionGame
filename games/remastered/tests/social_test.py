#!/usr/bin/env python3
"""End-to-end test: two SocialClients talking through the real relay module.

Starts server/relay.py on a local port (no upstream key needed) and drives two
clients: presence, a question from alice to bob, bob answers, alice receives the
result. Also checks the failure paths the game relies on (offline relay, errors).

Run:  python games/remastered/tests/social_test.py
"""
import importlib.util
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)                    # games/remastered
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_ROOT))
sys.path.insert(0, PKG_ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from TheQuestionGameRemastered import social  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s :: %s" % (name, extra))
        FAILS.append(name)


def load_relay():
    path = os.path.join(REPO_ROOT, "server", "relay.py")
    spec = importlib.util.spec_from_file_location("relay_social_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wait_until(predicate, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return False


print("== two clients through a live relay ==")
mod = load_relay()
mod.RELAY_KEY = ""
mod.RELAY_APP_TOKEN = ""
port = 8093
srv = mod.ThreadingHTTPServer(("127.0.0.1", port), mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
base = "http://127.0.0.1:%d" % port

alice = social.SocialClient("aaaaaaaaaa", "alice", base_url=base, poll_secs=0.2,
                            timeout=2, enabled=True)
bob = social.SocialClient("bbbbbbbbbb", "bob", base_url=base, poll_secs=0.2,
                          timeout=2, enabled=True)
try:
    check("alice comes online", wait_until(lambda: alice.status() == "online", 5),
          alice.status())
    check("bob comes online", wait_until(lambda: bob.status() == "online", 5),
          bob.status())
    check("alice sees bob",
          wait_until(lambda: any(p["name"] == "bob" for p in alice.others()), 5),
          alice.others())
    check("bob sees alice",
          wait_until(lambda: any(p["name"] == "alice" for p in bob.others()), 5),
          bob.others())
    check("nobody appears twice",
          len([p for p in alice.online() if p["id"] == "aaaaaaaaaa"]) == 1,
          alice.online())

    bob_id = next(p["id"] for p in alice.others() if p["name"] == "bob")
    check("send_question queues", alice.send_question(
        bob_id, "cake or death?", ["cake", "death"], 0) is True)

    got = {}
    def _take():
        item = bob.take_question()
        if item:
            got.update(item)
            return True
        return False
    check("question reaches bob", wait_until(_take, 6), got)
    check("question text intact", got.get("q") == "cake or death?", got.get("q"))
    check("options intact", got.get("opts") == ["cake", "death"], got.get("opts"))
    check("correct index intact", got.get("correct") == 0, got.get("correct"))
    check("sender name intact", got.get("from_name") == "alice", got.get("from_name"))

    check("answer queues", bob.send_answer(got, "death", False) is True)

    results = {}
    def _result():
        items = alice.take_results()
        if items:
            results.update(items[0])
            return True
        return False
    check("result reaches alice", wait_until(_result, 6), results)
    check("result says who and whether right",
          results.get("by") == "bob" and results.get("correct") is False, results)

    # Rename propagates on the next poll.
    check("rename accepted", bob.set_name("robert") is True)
    check("rename propagates",
          wait_until(lambda: any(p["name"] == "robert" for p in alice.others()), 6),
          alice.others())

    # Broadcast reaches the other client but never ourselves.
    check("broadcast queues",
          alice.send_question("all", "everyone answer", ["a", "b"], None) is True)
    broadcast = {}
    def _take2():
        item = bob.take_question()
        if item:
            broadcast.update(item)
            return True
        return False
    check("broadcast reaches bob", wait_until(_take2, 6), broadcast)
    check("broadcast excludes the sender", alice.pending_questions() == 0,
          alice.pending_questions())

    # Sending while the relay is down must not raise, and must surface a note.
    alice.stop()
    bob.stop()
    srv.shutdown()
    time.sleep(0.2)

    offline = social.SocialClient("cccccccccc", "carol", base_url=base,
                                  poll_secs=0.2, timeout=0.5, enabled=True)
    check("offline client reports offline",
          wait_until(lambda: offline.status() == "offline", 6), offline.status())
    check("offline send does not raise",
          offline.send_question("aaaaaaaaaa", "anyone?", ["yes", "no"]) is True)
    check("offline send surfaces a failure note",
          wait_until(lambda: any(r.get("local") for r in offline.take_results()), 6))
    offline.stop()
finally:
    for client in (alice, bob):
        try:
            client.stop()
        except Exception:
            pass
    try:
        srv.shutdown()
    except Exception:
        pass

print("== the send gate: only an operator build may write questions ==")
# Same relay, but with RELAY_SEND_TOKEN set. Presence and answering stay open;
# only /v1/send-question needs the secret, and the game carries it per client.
mod2 = load_relay()
mod2.RELAY_KEY = ""
mod2.RELAY_APP_TOKEN = ""
mod2.SEND_TOKEN = "test-send-token"
srv2 = mod2.ThreadingHTTPServer(("127.0.0.1", 8094), mod2.Handler)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
time.sleep(0.2)
base2 = "http://127.0.0.1:8094"

operator = social.SocialClient("operator0001", "operator", base_url=base2,
                               poll_secs=0.2, timeout=2, enabled=True,
                               send_token="test-send-token")
player = social.SocialClient("player000001", "player", base_url=base2,
                             poll_secs=0.2, timeout=2, enabled=True,
                             send_token="")
try:
    check("operator joins the room", wait_until(lambda: operator.status() == "online", 5),
          operator.status())
    check("player joins the same room", wait_until(lambda: player.status() == "online", 5),
          player.status())
    check("player is visible to the operator",
          wait_until(lambda: any(p["name"] == "player" for p in operator.others()), 5),
          operator.others())
    check("an operator client can send", operator.can_send() is True)
    check("a public build cannot claim to send", player.can_send() is False)

    check("operator question queues",
          operator.send_question("player000001", "from the operator", ["a", "b"], 1) is True)

    got2 = {}
    def _take_op():
        item = player.take_question()
        if item:
            got2.update(item)
            return True
        return False
    check("player receives it", wait_until(_take_op, 6), got2)
    check("player answers without any token",
          player.send_answer(got2, "b", True) is True)
    check("answer reaches the operator",
          wait_until(lambda: any(r.get("by") == "player" for r in operator.take_results()), 6))

    # The public build tries to write a question: refused, and it is told so
    # rather than left believing it worked.
    player.send_question("operator0001", "i should not be able to send", ["a", "b"], 0)
    check("a public build's send is refused",
          wait_until(lambda: any(r.get("local") for r in player.take_results()), 6),
          player.take_results())
finally:
    operator.stop()
    player.stop()
    srv2.shutdown()

print()
if FAILS:
    print("SOCIAL_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("SOCIAL_OK")
