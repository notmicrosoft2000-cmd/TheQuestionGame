#!/usr/bin/env python3
"""The Question Game — AI relay.

The game ships with NO API key. It talks to this relay, the relay holds the key
and forwards the request to Groq. That means:

  * the key is never in a public build or a public repo,
  * the key can be rotated here without re-releasing the game,
  * one place to rate-limit, cap, and lock down what callers may ask for.

It is deliberately dependency-free (stdlib only) so it runs anywhere Python
does, and deliberately strict: it accepts ONE endpoint, ONE model, a capped token
budget, an optional shared app token, and a per-IP rate limit. If someone finds
the URL they still cannot use it as a free general-purpose LLM.

Configuration is read from the environment (see relay.env.example):

  RELAY_KEY        (required)  the Groq API key — never commit this
  RELAY_APP_TOKEN  (optional)  shared secret the game must send; empty = off
  RELAY_PORT       (default 8090)
  RELAY_MODEL      (default openai/gpt-oss-120b)
  RELAY_MAX_TOKENS (default 320)   hard ceiling on max_tokens
  RELAY_RATE       (default 30)    requests per minute per IP
  RELAY_BURST      (default 10)    allowed in a short spike

Endpoints:
  GET  /health                  -> {"ok": true}
  POST /v1/chat/completions     -> OpenAI-compatible pass-through, sanitised
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

RELAY_KEY = os.environ.get("RELAY_KEY", "").strip()
APP_TOKEN = os.environ.get("RELAY_APP_TOKEN", "").strip()
PORT = int(os.environ.get("RELAY_PORT", "8090"))
MODEL = os.environ.get("RELAY_MODEL", "openai/gpt-oss-120b")
MAX_TOKENS = int(os.environ.get("RELAY_MAX_TOKENS", "320"))
RATE = int(os.environ.get("RELAY_RATE", "30"))
BURST = int(os.environ.get("RELAY_BURST", "10"))
UPSTREAM_TIMEOUT = float(os.environ.get("RELAY_TIMEOUT", "20"))
# Groq's free tier enforces tokens-per-minute, so a short burst of questions can
# return 429 even though *we* are well inside our own per-IP window. A 429 there
# is transient and clears in a second or two; without a retry the game gives up
# and drops the player onto the offline bank mid-session, which reads as the AI
# being broken. Retry a couple of times, respecting Retry-After, then give up.
UPSTREAM_RETRIES = int(os.environ.get("RELAY_UPSTREAM_RETRIES", "2"))
UPSTREAM_RETRY_MAX_WAIT = float(os.environ.get("RELAY_RETRY_MAX_WAIT", "6"))

# Only these body fields are ever forwarded — everything else is dropped, so a
# caller cannot switch models, ask for 100k tokens, or attach tools/functions.
_ALLOWED_FIELDS = {"messages", "temperature", "max_tokens", "reasoning_effort"}

_hits = {}          # ip -> list[timestamp]
_hits_lock = threading.Lock()


def _retry_after_seconds(err):
    """How long to wait after a 429 — honour Retry-After, else a short default.

    Capped so a hostile or confused upstream cannot pin a handler thread for
    long; this is a latency tweak, not a queue.
    """
    raw = ""
    try:
        raw = (err.headers.get("Retry-After") or "").strip()
    except Exception:
        raw = ""
    wait = 1.0
    if raw:
        try:
            wait = float(raw)
        except ValueError:
            wait = 1.0
    return max(0.25, min(wait, UPSTREAM_RETRY_MAX_WAIT))


def _rate_ok(ip):
    """Sliding-window limiter: RATE requests/minute, at most BURST in a burst."""
    now = time.time()
    with _hits_lock:
        bucket = [t for t in _hits.get(ip, []) if now - t < 60.0]
        recent = [t for t in bucket if now - t < 3.0]
        if len(recent) >= BURST or len(bucket) >= RATE:
            _hits[ip] = bucket
            return False
        bucket.append(now)
        _hits[ip] = bucket
        return True


def _sanitise(body):
    """Build the upstream payload. Returns (payload, error_string)."""
    if not isinstance(body, dict):
        return None, "body must be a JSON object"
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return None, "messages must be a non-empty list"
    # Cap conversation size so the relay can't be used to move huge payloads.
    if len(msgs) > 12:
        msgs = msgs[-12:]
    clean = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role not in ("system", "user", "assistant"):
            continue
        if not isinstance(content, str):
            content = str(content)
        clean.append({"role": role, "content": content[:8000]})
    if not clean:
        return None, "no usable messages"

    payload = {"model": MODEL, "messages": clean}
    temp = body.get("temperature")
    if isinstance(temp, (int, float)):
        payload["temperature"] = max(0.0, min(2.0, float(temp)))
    want = body.get("max_tokens")
    payload["max_tokens"] = MAX_TOKENS if not isinstance(want, int) else max(1, min(MAX_TOKENS, want))
    effort = body.get("reasoning_effort")
    if effort in ("low", "medium", "high"):
        payload["reasoning_effort"] = effort
    return payload, None


class Handler(BaseHTTPRequestHandler):
    server_version = "TQGRelay/1.0"

    def log_message(self, *a):
        pass  # quiet by default; the journal would otherwise fill with noise

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _client_ip(self):
        # Behind Tailscale funnel the peer is localhost; the real client is in
        # X-Forwarded-For. Fall back to the socket peer.
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0]

    def do_GET(self):
        if self.path.split("?")[0] in ("/health", "/healthz"):
            self._send(200, {"ok": True, "model": MODEL})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/v1/chat/completions", "/"):
            self._send(404, {"error": "not found"})
            return

        if APP_TOKEN and self.headers.get("X-App-Token", "") != APP_TOKEN:
            self._send(403, {"error": "forbidden"})
            return

        if not RELAY_KEY:
            self._send(503, {"error": "relay has no upstream key configured"})
            return

        if not _rate_ok(self._client_ip()):
            self._send(429, {"error": "slow down"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
        except Exception:
            self._send(400, {"error": "bad json"})
            return

        payload, err = _sanitise(body)
        if err:
            self._send(400, {"error": err})
            return

        try:
            req = urllib.request.Request(
                GROQ_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": "Bearer " + RELAY_KEY,
                    "Content-Type": "application/json",
                    "User-Agent": "TQGRelay/1.0",
                },
                method="POST",
            )
            # Retry a transient upstream 429 (free-tier tokens/minute) a couple of
            # times before surfacing it — see UPSTREAM_RETRIES above.
            for attempt in range(UPSTREAM_RETRIES + 1):
                try:
                    with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
                        out = resp.read()
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429 or attempt >= UPSTREAM_RETRIES:
                        raise
                    wait = _retry_after_seconds(e)
                    print("[*] upstream 429, retrying in %.1fs (attempt %d/%d)"
                          % (wait, attempt + 1, UPSTREAM_RETRIES), flush=True)
                    time.sleep(wait)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            # Never leak our key or full upstream body; just the status.
            self._send(e.code if e.code in (400, 401, 403, 404, 429) else 502,
                       {"error": "upstream %d" % e.code, "detail": detail})
        except Exception:
            self._send(502, {"error": "upstream unreachable"})


def main():
    if not RELAY_KEY:
        print("[!] RELAY_KEY is not set — the relay will refuse every request.")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("[*] TQG relay on http://127.0.0.1:%d  model=%s  app_token=%s"
          % (PORT, MODEL, "set" if APP_TOKEN else "off"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
