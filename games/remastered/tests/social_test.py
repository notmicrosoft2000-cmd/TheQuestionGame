#!/usr/bin/env python3
"""End-to-end test: two SocialClients talking through the real relay module.

Starts server/relay.py on a local port (no upstream key needed) and drives two
clients: presence, a question from alice to bob, bob answers, alice receives the
result. Also checks the failure paths the game relies on (offline relay, errors).

Run:  python games/remastered/tests/social_test.py
"""
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

    # Scare triggers: a question can carry "if they pick option B, fire X"
    # rules. They must survive the client -> relay -> receiver round trip.
    check("send_question with triggers queues", alice.send_question(
        bob_id, "which door?", ["left", "right"],
        scare_triggers=[
            {"option": 1, "effect": "eye jumpscare", "intensity": 8.0},
            {"option": 99, "effect": "jumpscare"},          # invalid, dropped locally
        ]) is True)
    trig = {}
    def _take_trig():
        item = bob.take_question()
        if item and item.get("q") == "which door?":
            trig.update(item)
            return True
        return False
    check("a triggered question reaches bob", wait_until(_take_trig, 6), trig)
    rules = trig.get("scare_triggers") or []
    check("the valid trigger survives the round trip",
          len(rules) == 1 and rules[0]["effect"] == "eye_jumpscare"
          and rules[0]["option"] == 1, rules)
    check("the trigger intensity is clamped",
          rules and abs(rules[0]["intensity"] - 2.0) < 1e-9, rules)

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

print("== short operator messages end to end ==")
# Same gate as questions/effects, but the receiver has its own mailbox.
# Fresh relay on its own port so this cannot see any of the earlier state.
mod_msg = load_relay()
mod_msg.RELAY_KEY = ""
mod_msg.RELAY_APP_TOKEN = ""
mod_msg.SEND_TOKEN = "msg-token"
port_msg = 8211
srv_msg = mod_msg.ThreadingHTTPServer(("127.0.0.1", port_msg), mod_msg.Handler)
threading.Thread(target=srv_msg.serve_forever, daemon=True).start()
time.sleep(0.2)
base_msg = "http://127.0.0.1:%d" % port_msg

op_msg = social.SocialClient("operator0002", "operator", base_url=base_msg,
                             poll_secs=0.2, timeout=2, enabled=True,
                             send_token="msg-token")
pl_msg = social.SocialClient("player000002", "player", base_url=base_msg,
                             poll_secs=0.2, timeout=2, enabled=True, send_token="")
try:
    check("operator comes online for messages",
          wait_until(lambda: op_msg.status() == "online", 5), op_msg.status())
    check("player comes online for messages",
          wait_until(lambda: pl_msg.status() == "online", 5), pl_msg.status())
    check("the two message peers see each other",
          wait_until(lambda: any(p["name"] == "player" for p in op_msg.others())
                     and any(p["name"] == "operator" for p in pl_msg.others()), 5),
          (op_msg.others(), pl_msg.others()))
    pl_id = next(p["id"] for p in op_msg.others() if p["name"] == "player")
    op_id = next(p["id"] for p in pl_msg.others() if p["name"] == "operator")

    check("send_message queues", op_msg.send_message(pl_id, "hello player") is True)
    check("blank message is refused locally", op_msg.send_message(pl_id, "  ") is False)
    check("pending_messages sees the queue",
          wait_until(lambda: pl_msg.pending_messages() == 1, 6), pl_msg.pending_messages())
    got_msg = pl_msg.take_messages()
    check("take_messages returns the item", len(got_msg) == 1, got_msg)
    msg = got_msg[0] if got_msg else {}
    check("message text intact", msg.get("message") == "hello player", msg)
    check("message from field intact", msg.get("from") == "operator0002", msg.get("from"))
    check("message from_name field intact", msg.get("from_name") == "operator",
          msg.get("from_name"))
    check("messages do not become questions or effects",
          pl_msg.pending_questions() == 0 and pl_msg.pending_effects() == 0,
          (pl_msg.pending_questions(), pl_msg.pending_effects()))
    time.sleep(0.6)  # several poll cycles
    check("messages are one-shot", pl_msg.pending_messages() == 0,
          pl_msg.pending_messages())
    check("a second take returns nothing", pl_msg.take_messages() == [],
          pl_msg.take_messages())

    check("message broadcast queues", op_msg.send_message("all", "room note") is True)
    check("broadcast message reaches the player",
          wait_until(lambda: pl_msg.pending_messages() == 1, 6), pl_msg.pending_messages())
    check("broadcast message excludes the sender", op_msg.pending_messages() == 0,
          op_msg.pending_messages())
    broadcast_msg = pl_msg.take_messages()
    check("broadcast text intact",
          len(broadcast_msg) == 1 and broadcast_msg[0].get("message") == "room note",
          broadcast_msg)

    # A player has no send token: the relay refuses and the client is told.
    pl_msg.send_message(op_id, "players should not write")
    check("a player's message is refused by the relay",
          wait_until(lambda: any(r.get("local") for r in pl_msg.take_results()), 6))
finally:
    op_msg.stop()
    pl_msg.stop()
    srv_msg.shutdown()

print("== malformed incoming presence payloads never reach the game loop ==")
# Fake relay: one rich payload mixing good and bad items, then repeated bad
# top-level payloads. The client must sanitise at the boundary and stay online.
good_question = {"id": "q-ok", "from": "op0000000001", "from_name": "operator",
                 "q": "pick one", "opts": ["a", "b"], "correct": 1}
rich_payload = {
    "ok": True,
    "online": [None, "x", 7, {"name": "no-id"}, {"id": "aaaaaaaaaa", "name": "alice"}],
    "inbox": [
        None, 42, "question", {},
        {"q": "", "opts": ["a", "b"]},
        {"q": "BAD missing opts"},
        {"q": "BAD one option", "opts": ["a"]},
        {"q": "BAD junk opts", "opts": ["a", 5, None]},
        good_question,
        {"id": "q-bool", "q": "bool correct", "opts": ["a", "b"], "correct": True},
        {"id": "q-high", "q": "high correct", "opts": ["a", "b"], "correct": 99},
        {"id": "q-neg", "q": "negative correct", "opts": ["a", "b"], "correct": -1},
        {"id": "q-str", "q": "string correct", "opts": ["a", "b"], "correct": "1"},
        {"id": "q-trig", "q": "triggers", "opts": ["a", "b", "c"], "correct": 0,
         "scare_triggers": [
             {"option": 1, "effect": "eye jumpscare", "intensity": "nan"},
             {"option": True, "effect": "jumpscare"},
             {"option": 99, "effect": "jumpscare"},
             "not-a-dict",
             {"option": "1", "effect": "jumpscare"},
         ]},
    ],
    "results": [None, "x", 7],
    "effects": [
        None, {}, {"effect": ""}, {"effect": 7},
        {"id": "e-ok", "from": "op0000000001", "effect": "flicker", "intensity": 0.5},
        {"id": "e-bad", "effect": "whisper", "intensity": "nope"},
    ],
    "messages": [
        None, {}, {"message": ""}, {"message": 9},
        {"id": "m-ok", "from": "op0000000001", "from_name": "operator",
         "message": "clean transmission"},
    ],
}
bad_payload = {"ok": True, "online": "not-a-list", "inbox": 7,
               "results": {"bad": True}, "effects": "nope", "messages": 3.5}
state = {"n": 0}
state_lock = threading.Lock()


class FuzzHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
        except Exception:
            pass
        with state_lock:
            idx = state["n"]
            state["n"] += 1
        obj = rich_payload if idx == 0 else bad_payload
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass


port_fuzz = 8212
srv_fuzz = ThreadingHTTPServer(("127.0.0.1", port_fuzz), FuzzHandler)
threading.Thread(target=srv_fuzz.serve_forever, daemon=True).start()
time.sleep(0.2)
fuzz = social.SocialClient("fuzzer00001", "fuzz",
                           base_url="http://127.0.0.1:%d" % port_fuzz,
                           poll_secs=0.05, timeout=2, enabled=True, send_token="")
try:
    arrived = wait_until(lambda: fuzz.status() == "online"
                         and fuzz.pending_questions() == 6
                         and fuzz.pending_effects() == 2
                         and fuzz.pending_messages() == 1, 6)
    check("the client consumes a mixed payload", arrived,
          (fuzz.status(), fuzz.pending_questions(), fuzz.pending_effects(),
           fuzz.pending_messages()))

    questions = []
    while fuzz.pending_questions():
        item = fuzz.take_question()
        if item:
            questions.append(item)
    by_id = {q.get("id"): q for q in questions}
    check("only well-formed questions survive", len(questions) == 6,
          [q.get("q") for q in questions])
    check("malformed question text never appears",
          not any("BAD" in (q.get("q") or "") for q in questions), questions)

    ok = by_id.get("q-ok", {})
    check("a correct integer index survives sanitization",
          ok.get("correct") == 1 and type(ok.get("correct")) is int, ok)
    for key in ("q-bool", "q-high", "q-neg", "q-str"):
        check("%s correct index is dropped" % key,
              by_id.get(key, {}).get("correct") is None, by_id.get(key))
    rules = by_id.get("q-trig", {}).get("scare_triggers") or []
    check("bad scare triggers are filtered out",
          len(rules) == 1 and rules[0]["option"] == 1
          and rules[0]["effect"] == "eye_jumpscare", rules)

    effects = []
    while fuzz.pending_effects():
        item = fuzz.take_effect()
        if item:
            effects.append(item)
    check("only well-formed effects survive", len(effects) == 2, effects)
    check("effect fields survive sanitization",
          any(e.get("id") == "e-ok" and e.get("effect") == "flicker"
              and abs(e.get("intensity", 0) - 0.5) < 1e-9 for e in effects), effects)
    check("a bad effect intensity falls back to 1.0",
          any(e.get("id") == "e-bad" and e.get("intensity") == 1.0 for e in effects),
          effects)

    messages = fuzz.take_messages()
    check("only well-formed messages survive", len(messages) == 1, messages)
    check("message text and from fields survive sanitization",
          bool(messages) and messages[0].get("message") == "clean transmission"
          and messages[0].get("from") == "op0000000001"
          and messages[0].get("from_name") == "operator", messages)
    check("no malformed result reaches the player", fuzz.take_results() == [],
          fuzz.take_results())

    time.sleep(0.4)  # several more polls of bad top-level payloads
    check("the client stays online through malformed payloads",
          fuzz.status() == "online", fuzz.status())
    check("nothing extra appeared after the malformed polls",
          fuzz.pending_questions() == 0 and fuzz.pending_effects() == 0
          and fuzz.pending_messages() == 0,
          (fuzz.pending_questions(), fuzz.pending_effects(), fuzz.pending_messages()))

    for fn in (social._clean_incoming_question, social._clean_incoming_effect,
               social._clean_incoming_message):
        junk = (None, 7, "x", [], {}, {"q": 1}, {"effect": []}, {"message": {}})
        check("%s shrugs off junk" % fn.__name__,
              all(fn(item) is None for item in junk), fn.__name__)
finally:
    fuzz.stop()
    srv_fuzz.shutdown()

print()
if FAILS:
    print("SOCIAL_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("SOCIAL_OK")
