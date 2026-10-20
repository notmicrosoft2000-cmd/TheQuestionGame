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

print()
if FAILS:
    print("RELAY_FAIL: " + ", ".join(FAILS))
    sys.exit(1)
print("RELAY_OK")
