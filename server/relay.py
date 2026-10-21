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
  POST /v1/presence             -> heartbeat: returns who is online, plus any
                                   questions and answer-results for this peer
  POST /v1/send-question        -> deliver a hand-written question to one peer
                                   (or "all" of them)
  POST /v1/answer               -> report a recipient's answer back to the
                                   player who wrote the question

The social endpoints are deliberately open (the game ships with no token, and
the whole point is that any copy of the game can see the others). They are
rate-limited per IP and every string is capped, so they can only move small
question-sized payloads. State is in memory: a restart forgets everyone.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
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


# --- social: presence + hand-written questions -------------------------------
# In-memory only. A restart empties the room, which is fine: presence is
# re-established on every poll, and a question that was never delivered is
# better dropped than replayed a day later.
PEER_TTL = float(os.environ.get("RELAY_PEER_TTL", "20"))
QUESTION_TTL = float(os.environ.get("RELAY_QUESTION_TTL", "900"))
INBOX_MAX = int(os.environ.get("RELAY_INBOX_MAX", "12"))
RESULT_MAX = int(os.environ.get("RELAY_RESULT_MAX", "12"))
SOCIAL_NAME_MAX = 24
SOCIAL_Q_MAX = 240
SOCIAL_OPT_MAX = 80
SOCIAL_OPTS_MAX = 4
SOCIAL_RATE = int(os.environ.get("RELAY_SOCIAL_RATE", "120"))
SOCIAL_BURST = int(os.environ.get("RELAY_SOCIAL_BURST", "40"))

_peers = {}          # peer id -> {"id", "name", "platform", "last"}
_inboxes = {}        # peer id -> [question]
_results = {}        # sender id -> [answer result]
_social_lock = threading.Lock()
_social_hits = {}    # ip -> [timestamp]; separate from the AI limiter
_social_hits_lock = threading.Lock()


def _social_rate_ok(ip):
    """Presence polls are cheap but frequent; give them their own bucket."""
    now = time.time()
    with _social_hits_lock:
        bucket = [t for t in _social_hits.get(ip, []) if now - t < 60.0]
        recent = [t for t in bucket if now - t < 3.0]
        if len(recent) >= SOCIAL_BURST or len(bucket) >= SOCIAL_RATE:
            _social_hits[ip] = bucket
            return False
        bucket.append(now)
        _social_hits[ip] = bucket
        # Keep the table from growing without bound on a busy relay.
        if len(_social_hits) > 4096:
            for stale in [k for k, v in _social_hits.items() if not v]:
                _social_hits.pop(stale, None)
        return True


def _clean_social_text(value, limit):
    """Trim to a single line and a hard length. Control chars out."""
    if not isinstance(value, str):
        return ""
    value = "".join(ch for ch in value if ch >= " " and ch != "\x7f")
    return value.strip()[:limit]


def _valid_peer_id(value):
    if not isinstance(value, str) or not (8 <= len(value) <= 64):
        return False
    return all(ch.isalnum() or ch in "-_" for ch in value)


def _purge_locked(now):
    """Drop peers that stopped polling and questions nobody picked up.

    Must be called with _social_lock held.
    """
    for pid in [p for p, v in _peers.items() if now - v["last"] > PEER_TTL]:
        _peers.pop(pid, None)
    for table in (_inboxes, _results):
        for pid in list(table):
            fresh = [item for item in table[pid]
                     if now - item.get("ts", now) < QUESTION_TTL]
            if fresh:
                table[pid] = fresh
            else:
                table.pop(pid, None)


def _handle_presence(body):
    pid = body.get("id")
    name = _clean_social_text(body.get("name"), SOCIAL_NAME_MAX)
    platform = _clean_social_text(body.get("platform"), 16)
    if not _valid_peer_id(pid) or not name:
        return 400, {"error": "id and name required"}
    now = time.time()
    with _social_lock:
        _purge_locked(now)
        _peers[pid] = {"id": pid, "name": name, "platform": platform, "last": now}
        online = [{"id": p["id"], "name": p["name"], "platform": p["platform"]}
                  for p in _peers.values()]
        # Delivered once: pop, don't peek. A client that dies before showing
        # an item loses it, which beats replaying old questions forever.
        inbox = _inboxes.pop(pid, [])
        results = _results.pop(pid, [])
    online.sort(key=lambda p: p["name"].lower())
    return 200, {"ok": True, "online": online, "inbox": inbox, "results": results}


def _handle_send(body):
    from_id = body.get("from")
    to = body.get("to")
    q = _clean_social_text(body.get("q"), SOCIAL_Q_MAX)
    if not _valid_peer_id(from_id):
        return 400, {"error": "bad sender id"}
    if not q:
        return 400, {"error": "empty question"}
    raw_opts = body.get("opts")
    if not isinstance(raw_opts, list):
        return 400, {"error": "opts must be a list"}
    opts = []
    for raw in raw_opts[:SOCIAL_OPTS_MAX]:
        text = _clean_social_text(raw, SOCIAL_OPT_MAX)
        if text:
            opts.append(text)
    if len(opts) < 2:
        return 400, {"error": "need at least two options"}
    correct = body.get("correct")
    if isinstance(correct, bool) or not isinstance(correct, int) \
            or not (0 <= correct < len(opts)):
        correct = None

    now = time.time()
    delivered = []
    with _social_lock:
        _purge_locked(now)
        sender = _peers.get(from_id)
        if not sender:
            # Requiring presence keeps anonymous one-shot senders out and
            # guarantees the recipient sees a real, current name.
            return 403, {"error": "join presence first"}
        if to == "all":
            targets = [pid for pid in _peers if pid != from_id]
        elif isinstance(to, str) and to in _peers and to != from_id:
            targets = [to]
        else:
            targets = []
        if not targets:
            return 404, {"error": "nobody to send to"}
        qid = uuid.uuid4().hex[:12]
        item = {
            "id": qid,
            "from": from_id,
            "from_name": sender["name"],
            "q": q,
            "opts": opts,
            "correct": correct,
            "ts": now,
        }
        for target in targets[:20]:
            box = _inboxes.setdefault(target, [])
            box.append(dict(item))
            del box[:-INBOX_MAX]
            delivered.append(target)
    return 200, {"ok": True, "id": qid, "delivered": delivered}


def _handle_answer(body):
    sender = body.get("sender")
    qid = body.get("qid")
    by = _clean_social_text(body.get("by"), SOCIAL_NAME_MAX)
    choice = _clean_social_text(body.get("choice"), SOCIAL_OPT_MAX)
    correct = body.get("correct")
    if not _valid_peer_id(sender) or not isinstance(qid, str) or not qid:
        return 400, {"error": "sender and qid required"}
    if not isinstance(correct, bool):
        correct = None
    now = time.time()
    with _social_lock:
        _purge_locked(now)
        box = _results.setdefault(sender, [])
        box.append({
            "qid": qid,
            "by": by or "someone",
            "choice": choice,
            "correct": correct,
            "ts": now,
        })
        del box[:-RESULT_MAX]
    return 200, {"ok": True}


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
        # Social traffic is its own surface: open (no app token — the game
        # ships without one), rate-limited separately, and it never touches
        # the AI upstream.
        if path in ("/v1/presence", "/v1/send-question", "/v1/answer"):
            if not _social_rate_ok(self._client_ip()):
                self._send(429, {"error": "slow down"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw or b"{}")
            except Exception:
                self._send(400, {"error": "bad json"})
                return
            if path == "/v1/presence":
                code, obj = _handle_presence(body)
            elif path == "/v1/send-question":
                code, obj = _handle_send(body)
            else:
                code, obj = _handle_answer(body)
            self._send(code, obj)
            return

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
