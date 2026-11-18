#!/usr/bin/env python3
"""Tests for server/relay.py — no network, no key needed.

Run:  python server/test_relay.py
Exits non-zero on failure so CI can gate on it.
"""
import importlib.util
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s :: %s" % (name, extra))
        FAILS.append(name)


def load_relay(env):
    """Import relay.py fresh with a given environment."""
    for k, v in env.items():
        os.environ[k] = v
    spec = importlib.util.spec_from_file_location("relay_under_test", os.path.join(HERE, "relay.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print("== sanitisation (what a caller may and may not do) ==")
mod = load_relay({"RELAY_KEY": "dummy", "RELAY_MAX_TOKENS": "320", "RELAY_MODEL": "locked-model"})

payload, err = mod._sanitise({
    "model": "expensive-model",
    "max_tokens": 999999,
    "messages": [{"role": "user", "content": "hi"}],
    "tools": [{"type": "function"}],
    "functions": [1],
})
check("valid body accepted", err is None, err)
check("model is locked to the configured one", payload["model"] == "locked-model", payload.get("model"))
check("max_tokens is capped", payload["max_tokens"] == 320, payload.get("max_tokens"))
check("tools are dropped", "tools" not in payload)
check("functions are dropped", "functions" not in payload)
check("temperature clamped high", mod._sanitise(
    {"messages": [{"role": "user", "content": "x"}], "temperature": 99})[0]["temperature"] == 2.0)
check("temperature clamped low", mod._sanitise(
    {"messages": [{"role": "user", "content": "x"}], "temperature": -5})[0]["temperature"] == 0.0)

payload2, _ = mod._sanitise({"messages": [{"role": "user", "content": "x"}], "reasoning_effort": "extreme"})
check("bad reasoning_effort dropped", "reasoning_effort" not in payload2)
payload3, _ = mod._sanitise({"messages": [{"role": "user", "content": "x"}], "reasoning_effort": "low"})
check("valid reasoning_effort kept", payload3.get("reasoning_effort") == "low")

_, e1 = mod._sanitise({})
check("empty body rejected", e1 is not None, e1)
_, e2 = mod._sanitise({"messages": []})
check("empty messages rejected", e2 is not None, e2)
_, e3 = mod._sanitise({"messages": [{"role": "tool", "content": "x"}]})
check("unknown roles rejected", e3 is not None, e3)

long_msgs = [{"role": "user", "content": "x"} for _ in range(50)]
payload4, _ = mod._sanitise({"messages": long_msgs})
check("conversation truncated to 12", len(payload4["messages"]) == 12, len(payload4["messages"]))
huge, _ = mod._sanitise({"messages": [{"role": "user", "content": "a" * 20000}]})
check("message content capped", len(huge["messages"][0]["content"]) == 8000)

print("== rate limiting ==")
mod._hits.clear()
mod.RATE = 1000
mod.BURST = 3
results = [mod._rate_ok("1.2.3.4") for _ in range(5)]
check("burst limit enforced", results[:3] == [True, True, True] and results[3] is False, results)
check("limits are per-IP", mod._rate_ok("5.6.7.8") is True)

mod._hits.clear()
mod.RATE = 10
mod.BURST = 10
mod._hits["9.9.9.9"] = [time.time() for _ in range(10)]
check("minute limit enforced", mod._rate_ok("9.9.9.9") is False)

print("== live HTTP behaviour (against a stub, no upstream key) ==")
mod = load_relay({"RELAY_KEY": "", "RELAY_PORT": "8099", "RELAY_APP_TOKEN": "", "RELAY_RATE": "100", "RELAY_BURST": "50"})
srv = mod.ThreadingHTTPServer(("127.0.0.1", 8099), mod.Handler)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
time.sleep(0.3)

try:
    with urllib.request.urlopen("http://127.0.0.1:8099/health", timeout=5) as r:
        data = json.loads(r.read())
    check("health endpoint works", data.get("ok") is True, data)

    try:
        urllib.request.urlopen("http://127.0.0.1:8099/nope", timeout=5)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("unknown path 404s", code == 404, code)

    req = urllib.request.Request("http://127.0.0.1:8099/v1/chat/completions",
                                 data=json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("no key configured -> 503 (never calls upstream)", code == 503, code)
finally:
    srv.shutdown()

print("== app token gate ==")
mod = load_relay({"RELAY_KEY": "dummy", "RELAY_PORT": "8098", "RELAY_APP_TOKEN": "secret123",
                  "RELAY_RATE": "100", "RELAY_BURST": "50"})
srv = mod.ThreadingHTTPServer(("127.0.0.1", 8098), mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)
try:
    try:
        urllib.request.urlopen("http://127.0.0.1:8098/health", timeout=5)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("health stays open (for uptime checks)", code == 200, code)

    req = urllib.request.Request("http://127.0.0.1:8098/v1/chat/completions",
                                 data=b'{"messages":[{"role":"user","content":"x"}]}',
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("missing app token -> 403", code == 403, code)
finally:
    srv.shutdown()

print("== social: presence + hand-written questions ==")
mod = load_relay({"RELAY_KEY": "", "RELAY_PORT": "8097", "RELAY_APP_TOKEN": "",
                  "RELAY_RATE": "100", "RELAY_BURST": "50"})
srv = mod.ThreadingHTTPServer(("127.0.0.1", 8097), mod.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)


def post(path, body):
    req = urllib.request.Request(
        "http://127.0.0.1:8097" + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


try:
    code, a = post("/v1/presence", {"id": "aaaaaaaaaa", "name": "alice", "platform": "linux"})
    check("presence accepts a peer", code == 200 and a.get("ok") is True, (code, a))

    code, b = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    names = {p["name"] for p in b.get("online", [])}
    check("presence lists every peer", {"alice", "bob"} <= names, b.get("online"))

    code, c = post("/v1/presence", {"id": "bad id!", "name": "x"})
    check("bad peer id rejected", code == 400, (code, c))
    code, d = post("/v1/presence", {"id": "cccccccccc", "name": "   "})
    check("blank name rejected", code == 400, (code, d))

    code, e = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb",
        "q": "cake or death?", "opts": ["cake", "death"], "correct": 0,
    })
    check("question accepted", code == 200 and e.get("delivered") == ["bbbbbbbbbb"], (code, e))
    qid = e.get("id")

    code, f = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    box = f.get("inbox") or []
    check("question delivered to recipient", len(box) == 1 and box[0]["q"] == "cake or death?", box)
    check("sender name travels with it", box and box[0]["from_name"] == "alice", box[:1])
    check("correct index travels with it", box and box[0]["correct"] == 0, box[:1])

    code, g = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    check("inbox is cleared after delivery", g.get("inbox") == [], g.get("inbox"))

    code, h = post("/v1/answer", {"sender": "aaaaaaaaaa", "qid": qid, "by": "bob",
                                  "choice": "death", "correct": False})
    check("answer accepted", code == 200, (code, h))
    code, i = post("/v1/presence", {"id": "aaaaaaaaaa", "name": "alice"})
    results = i.get("results") or []
    check("result reaches the sender",
          len(results) == 1 and results[0]["by"] == "bob" and results[0]["correct"] is False,
          results)
    code, j = post("/v1/presence", {"id": "aaaaaaaaaa", "name": "alice"})
    check("results are cleared after delivery", j.get("results") == [], j.get("results"))

    code, k = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "doesnotexist", "q": "hi", "opts": ["a", "b"]})
    check("send to an unknown peer 404s", code == 404, (code, k))
    code, l = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "hi", "opts": ["only"]})
    check("single-option question rejected", code == 400, (code, l))
    code, m = post("/v1/send-question", {
        "from": "zzzzzzzzzz", "to": "bbbbbbbbbb", "q": "hi", "opts": ["a", "b"]})
    check("send without presence 403s", code == 403, (code, m))

    code, n = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "all", "q": "to everyone", "opts": ["a", "b"]})
    check("broadcast reaches everyone else",
          code == 200 and "bbbbbbbbbb" in (n.get("delivered") or []), (code, n))

    code, o = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb",
        "q": "x" * 1000, "opts": ["a" * 300, "b" * 300], "correct": 99})
    check("oversized question accepted", code == 200, (code, o))
    code, p = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    long_items = [q for q in (p.get("inbox") or []) if q["q"].startswith("xxx")]
    check("question text capped on the wire",
          bool(long_items) and len(long_items[0]["q"]) <= mod.SOCIAL_Q_MAX,
          long_items[:1])
    check("option text capped on the wire",
          bool(long_items) and all(len(o2) <= mod.SOCIAL_OPT_MAX for o2 in long_items[0]["opts"]),
          long_items[:1])
    check("out-of-range correct index dropped",
          bool(long_items) and long_items[0]["correct"] is None,
          long_items[:1])

    code, q = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb",
        "q": "pick", "opts": ["a", "b"], "correct": True})
    code, r = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    bool_items = [x for x in (r.get("inbox") or []) if x["q"] == "pick"]
    check("bool correct index dropped",
          bool(bool_items) and bool_items[0]["correct"] is None, bool_items[:1])

    # --- scare_triggers: the option -> scare rules ride with the question ---
    code, _ = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "triggers",
        "opts": ["A", "B", "C"],
        "scare_triggers": [
            {"option": 1, "effect": "jumpscare", "intensity": 1.5},
            {"option": 2, "effect": "eye jumpscare", "intensity": 99},
        ],
    })
    check("a question with scare triggers is accepted", code == 200, code)
    code, rr = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    trig_items = [x for x in (rr.get("inbox") or []) if x["q"] == "triggers"]
    check("scare triggers travel with the question",
          bool(trig_items) and len(trig_items[0].get("scare_triggers") or []) == 2,
          trig_items[:1])
    if trig_items:
        rules = {r["option"]: r for r in trig_items[0]["scare_triggers"]}
        check("the trigger's effect name survives",
              rules.get(1, {}).get("effect") == "jumpscare", rules)
        check("effect names with spaces are normalised",
              rules.get(2, {}).get("effect") == "eye_jumpscare", rules)
        check("trigger intensity is clamped on the wire",
              abs(rules.get(2, {}).get("intensity", 0) - 2.0) < 1e-9, rules)

    code, bad = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "bad trigger",
        "opts": ["A", "B"],
        "scare_triggers": [{"option": 0, "effect": "totally_not_a_scare"}],
    })
    check("an unknown trigger effect is refused", code == 400, (code, bad))
    code, bad = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "bad trigger 2",
        "opts": ["A", "B"],
        "scare_triggers": [{"option": 9, "effect": "jumpscare"}],
    })
    check("an out-of-range trigger option is refused", code == 400, (code, bad))
    code, bad = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "bad trigger 3",
        "opts": ["A", "B"],
        "scare_triggers": "jumpscare",
    })
    check("a non-list trigger field is refused", code == 400, (code, bad))

    code, _ = post("/v1/send-question", {
        "from": "aaaaaaaaaa", "to": "bbbbbbbbbb", "q": "plain",
        "opts": ["A", "B"],
    })
    code, pp = post("/v1/presence", {"id": "bbbbbbbbbb", "name": "bob"})
    plain_items = [x for x in (pp.get("inbox") or []) if x["q"] == "plain"]
    check("a plain question has no trigger field",
          bool(plain_items) and "scare_triggers" not in plain_items[0], plain_items[:1])
finally:
    srv.shutdown()

print("== social: sending can be restricted to the operator ==")
# A relay with RELAY_SEND_TOKEN set: everyone may join and answer, but only a
# caller holding the token may write questions.
for k in ("RELAY_SEND_TOKEN",):
    mod = load_relay({"RELAY_KEY": "", "RELAY_PORT": "8099", "RELAY_APP_TOKEN": "",
                      "RELAY_RATE": "100", "RELAY_BURST": "50",
                      "RELAY_SEND_TOKEN": "operator-secret"})
srv2 = mod.ThreadingHTTPServer(("127.0.0.1", 8099), mod.Handler)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
time.sleep(0.3)


def post2(path, body, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request("http://127.0.0.1:8099" + path,
                                 data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


try:
    code, a = post2("/v1/presence", {"id": "op0000000001", "name": "operator"})
    check("presence stays open with a send token set", code == 200 and a.get("ok"), (code, a))
    code, b = post2("/v1/presence", {"id": "player000001", "name": "player"})
    check("a plain player may still join the room", code == 200 and b.get("ok"), (code, b))

    code, c = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001",
        "q": "no token", "opts": ["a", "b"]})
    check("send without the token is refused", code == 403, (code, c))

    code, d = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001",
        "q": "wrong token", "opts": ["a", "b"]}, {"X-Send-Token": "guess"})
    check("send with a wrong token is refused", code == 403, (code, d))

    code, e = post2("/v1/send-question", {
        "from": "player000001", "to": "op0000000001",
        "q": "players cannot write", "opts": ["a", "b"]},
        {"X-Send-Token": "operator-secret"})
    check("the token itself is what grants sending, not the peer id",
          code == 200 and e.get("delivered") == ["op0000000001"], (code, e))

    # The recipient answers with no token at all — that path must stay open.
    code, f = post2("/v1/presence", {"id": "op0000000001", "name": "operator"})
    box = f.get("inbox") or []
    check("the operator receives it", len(box) == 1 and box[0]["q"] == "players cannot write", box)
    qid = box[0]["id"] if box else ""
    code, g = post2("/v1/answer", {"sender": "player000001", "qid": qid, "by": "operator",
                                   "choice": "a", "correct": True})
    check("answering needs no token", code == 200 and g.get("ok"), (code, g))
    code, h = post2("/v1/presence", {"id": "player000001", "name": "player"})
    check("the result reaches the sender without a token",
          len(h.get("results") or []) == 1, h.get("results"))

    # --- effects: the operator can fire a scare by hand ---------------------
    # An effect rides the same route and token gate as a question, but lands in
    # its own store, so the receiver plays it instead of showing it as text.
    code, i = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001", "effect": "flicker"})
    check("an effect without the token is refused", code == 403, (code, i))

    code, j = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001",
        "effect": "screen_tear", "intensity": 2.0},
        {"X-Send-Token": "operator-secret"})
    check("an effect with the token is delivered",
          code == 200 and j.get("delivered") == ["player000001"], (code, j))

    code, k = post2("/v1/presence", {"id": "player000001", "name": "player"})
    got = k.get("effects") or []
    check("the effect reaches the player on the next poll",
          len(got) == 1 and got[0].get("effect") == "screen_tear", got)
    check("the effect keeps the operator's intensity",
          got and abs(float(got[0].get("intensity", 0)) - 2.0) < 0.01, got)
    check("an effect is not smuggled into the question inbox",
          not (k.get("inbox") or []), k.get("inbox"))

    code, l = post2("/v1/presence", {"id": "player000001", "name": "player"})
    check("an effect is delivered once, like a question",
          not (l.get("effects") or []), l.get("effects"))

    code, m = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001", "effect": "not_a_scare"},
        {"X-Send-Token": "operator-secret"})
    check("an unknown effect name is refused, not silently dropped",
          code == 400 and "effect" in str(m.get("error", "")), (code, m))

    code, n = post2("/v1/send-question", {
        "from": "op0000000001", "to": "all", "effect": "whisper", "intensity": 0.5},
        {"X-Send-Token": "operator-secret"})
    check("an effect can be broadcast to the room",
          code == 200 and n.get("delivered") == ["player000001"], (code, n))

    code, o = post2("/v1/presence", {"id": "player000001", "name": "player"})
    check("the broadcast effect arrives",
          [e.get("effect") for e in (o.get("effects") or [])] == ["whisper"],
          o.get("effects"))
    check("a gentle intensity is carried through",
          (o.get("effects") or [{}])[0].get("intensity") == 0.5, o.get("effects"))

    code, p = post2("/v1/send-question", {
        "from": "op0000000001", "to": "player000001",
        "effect": "whisper", "intensity": 99},
        {"X-Send-Token": "operator-secret"})
    check("an absurd intensity is clamped, not passed on", code == 200, (code, p))
    code, q = post2("/v1/presence", {"id": "player000001", "name": "player"})
    check("the clamp lands at the ceiling",
          (q.get("effects") or [{}])[0].get("intensity") == 2.0, q.get("effects"))
finally:
    srv2.shutdown()

print("== social: short operator messages ==")
# Messages share the token-gated send route but land in their own one-shot
# mailbox, so none of the question/effect checks above should ever see them.
mod = load_relay({"RELAY_KEY": "", "RELAY_PORT": "8213", "RELAY_APP_TOKEN": "",
                  "RELAY_RATE": "100", "RELAY_BURST": "50",
                  "RELAY_SEND_TOKEN": "msg-secret"})
srv3 = mod.ThreadingHTTPServer(("127.0.0.1", 8213), mod.Handler)
threading.Thread(target=srv3.serve_forever, daemon=True).start()
time.sleep(0.2)


def post3(path, body, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request("http://127.0.0.1:8213" + path,
                                 data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


try:
    code, _ = post3("/v1/presence", {"id": "opmessage01", "name": "operator"})
    check("operator joins for messages", code == 200, code)
    code, _ = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    check("player joins for messages", code == 200, code)
    code, _ = post3("/v1/presence", {"id": "thirdmsg001", "name": "third"})
    check("third peer joins for messages", code == 200, code)

    code, a = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "no token"})
    check("message without the token is refused", code == 403, (code, a))
    code, b = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "wrong token"},
        {"X-Send-Token": "guess"})
    check("message with a wrong token is refused", code == 403, (code, b))

    token = {"X-Send-Token": "msg-secret"}
    code, c = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "hello there"}, token)
    check("message with the token is accepted",
          code == 200 and c.get("delivered") == ["playermsg01"], (code, c))
    mid = c.get("id")

    code, d = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    box = d.get("messages") or []
    check("message reaches only the recipient",
          len(box) == 1 and box[0].get("message") == "hello there", box)
    check("message carries sender identity",
          bool(box) and box[0].get("from") == "opmessage01"
          and box[0].get("from_name") == "operator" and box[0].get("id") == mid, box)
    check("message is not a question or an effect",
          bool(box) and "q" not in box[0] and "opts" not in box[0]
          and "effect" not in box[0], box)
    check("message does not leak into the question inbox",
          not (d.get("inbox") or []), d.get("inbox"))
    check("message does not leak into the effect inbox",
          not (d.get("effects") or []), d.get("effects"))

    code, e = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    check("message pickup is one-shot", not (e.get("messages") or []), e.get("messages"))
    code, f = post3("/v1/presence", {"id": "opmessage01", "name": "operator"})
    check("the sender never receives their own message",
          not (f.get("messages") or []), f.get("messages"))

    code, g = post3("/v1/send-question", {
        "from": "opmessage01", "to": "all", "message": "room broadcast"}, token)
    check("a message can be broadcast",
          code == 200 and set(g.get("delivered") or []) == {"playermsg01", "thirdmsg001"},
          (code, g))
    check("broadcast excludes the sender",
          "opmessage01" not in (g.get("delivered") or []), g.get("delivered"))
    code, h = post3("/v1/presence", {"id": "opmessage01", "name": "operator"})
    check("broadcast does not bounce back to the sender",
          not (h.get("messages") or []), h.get("messages"))
    code, i = post3("/v1/presence", {"id": "thirdmsg001", "name": "third"})
    check("the other peer gets the broadcast",
          [m.get("message") for m in (i.get("messages") or [])] == ["room broadcast"],
          i.get("messages"))
    code, j = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    check("the intended peer also gets the broadcast",
          [m.get("message") for m in (j.get("messages") or [])] == ["room broadcast"],
          j.get("messages"))

    raw_long = "  " + ("a\x01b" * 200) + "  "
    code, k = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": raw_long}, token)
    check("an oversized message is accepted", code == 200, (code, k))
    code, l = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    longs = [m.get("message", "") for m in (l.get("messages") or [])]
    check("message text is capped on the wire",
          bool(longs) and len(longs[0]) <= mod.SOCIAL_MESSAGE_MAX, longs[:1])
    check("message text is trimmed and single-line",
          bool(longs) and longs[0] == longs[0].strip() and "\x01" not in longs[0], longs[:1])

    for bad in (123, None, ["hello"], {"text": "hello"}):
        code, _ = post3("/v1/send-question", {
            "from": "opmessage01", "to": "playermsg01", "message": bad}, token)
        check("non-string message is rejected (%s)" % type(bad).__name__, code == 400, code)
    code, blank = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "   \t  "}, token)
    check("blank message is rejected", code == 400, (code, blank))
    code, m = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    check("rejected messages were never queued",
          not (m.get("messages") or []), m.get("messages"))

    # Idle peers and uncollected messages expire exactly like questions do.
    mod.PEER_TTL = 0.2
    mod.QUESTION_TTL = 0.2
    post3("/v1/presence", {"id": "opmessage01", "name": "operator"})
    post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    code, n = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "will expire"}, token)
    check("message accepted just before idle timeout", code == 200, (code, n))
    time.sleep(0.5)
    post3("/v1/presence", {"id": "observer01", "name": "observer"})
    code, o = post3("/v1/presence", {"id": "playermsg01", "name": "player"})
    check("an uncollected message is purged when idle",
          not (o.get("messages") or []), o.get("messages"))
    code, p = post3("/v1/send-question", {
        "from": "opmessage01", "to": "playermsg01", "message": "after purge"}, token)
    check("an idle sender was purged too", code == 403, (code, p))
finally:
    srv3.shutdown()

print()
if FAILS:
    print("RELAY_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("RELAY_OK")
