"""Online presence and hand-written questions, through the same relay as the AI.

The relay keeps the room in memory: every player polls `/v1/presence` every few
seconds with an id and a name, and gets back the current online list plus any
questions addressed to them and any results for questions they sent. Delivery is
one-shot: the server clears an item the moment it hands it over.

This module must never make the game feel slower or break it:

  * one daemon thread does all network I/O, with short timeouts;
  * every failure is swallowed and turns into a visible "OFFLINE" status;
  * the main thread only ever reads snapshots under a lock.

The client is deliberately transport-thin: no auth, no discovery, no game logic.
Identity (`player_id`, `player_name`) is owned by main.py and persisted with the
save file.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request

from . import config


def _clean(value, limit):
    """Same trimming rules as the relay, so what we send is what we show."""
    if not isinstance(value, str):
        return ""
    value = "".join(ch for ch in value if ch >= " " and ch != "\x7f")
    return value.strip()[:limit]


def _platform_label():
    if getattr(config, "IS_ANDROID", False):
        return "android"
    return (sys.platform or "desktop")[:16]


class SocialClient:
    """Threaded presence + question mailbox. Safe to call from the main thread."""

    def __init__(self, player_id, name, base_url=None, enabled=None,
                 poll_secs=None, timeout=None, send_token=None):
        self.player_id = player_id
        self._name = _clean(name, config.SOCIAL_NAME_MAX) or "guest"
        self._base = (base_url or config.SOCIAL_URL).rstrip("/")
        self._poll_secs = float(poll_secs or config.SOCIAL_POLL_SECS)
        self._timeout = float(timeout or config.SOCIAL_TIMEOUT)
        # Captured at construction: the right to write questions belongs to the
        # build, not to whoever reads config last.
        tok = send_token
        if tok is None:
            tok = getattr(config, "SOCIAL_SEND_TOKEN", "") or ""
        self._send_token = tok
        if enabled is None:
            enabled = config.SOCIAL_ENABLED

        self._lock = threading.Lock()
        self._online = []
        self._inbox = []
        self._results = []
        self._send_outcomes = []      # what the relay said about a queued send
        self._status = "connecting"
        self._last_ok = 0.0
        self._last_error = ""
        self._sent = 0
        self._received = 0

        self._stop = threading.Event()
        self._wake = threading.Event()
        self._outbox = []
        self._thread = None
        if enabled:
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="tqg-social")
            self._thread.start()
        else:
            self._status = "disabled"

    # --- main-thread API ----------------------------------------------------
    @property
    def name(self):
        with self._lock:
            return self._name

    def can_send(self):
        """True when this client holds a send token (i.e. an operator build)."""
        return bool(self._send_token)

    def set_send_token(self, token):
        """Give this client the right to write questions (operator app only).

        The shipped game never calls this: it has no token and no code path
        that could obtain one. The operator's sender app calls it once the
        token has been typed in and checked against the relay.
        """
        with self._lock:
            self._send_token = (token or "").strip()
        return bool(self._send_token)

    def status(self):
        """'online' / 'offline' / 'connecting' / 'disabled'."""
        with self._lock:
            return self._status

    def online(self):
        """Everyone the relay currently knows about, including us."""
        with self._lock:
            return [dict(p) for p in self._online]

    def others(self):
        """Everyone except us — that's the list you can send to."""
        with self._lock:
            return [dict(p) for p in self._online if p.get("id") != self.player_id]

    def pending_questions(self):
        with self._lock:
            return len(self._inbox)

    def take_question(self):
        """Pop the oldest question addressed to us, or None."""
        with self._lock:
            if not self._inbox:
                return None
            self._received += 1
            return self._inbox.pop(0)

    def take_results(self):
        """Pop all answer-results for questions we sent."""
        with self._lock:
            out = self._results
            self._results = []
            return out

    def take_send_outcomes(self):
        """Pop what the relay said about the questions we queued.

        Queueing is not delivery: the relay can still refuse ("sending is
        restricted", "nobody to send to", "join presence first") or be down.
        The operator UI shows these, so a failed send never looks like a
        successful one.
        """
        with self._lock:
            out = self._send_outcomes
            self._send_outcomes = []
            return out

    def sent_count(self):
        with self._lock:
            return self._sent

    def set_name(self, name):
        clean = _clean(name, config.SOCIAL_NAME_MAX)
        if not clean:
            return False
        with self._lock:
            self._name = clean
        self._wake.set()
        return True

    def send_question(self, to_id, question, options, correct=None):
        """Queue a question for one peer id (or 'all'). Returns the local count.

        The UI treats queueing as success; a relay-side failure surfaces as a
        result note from `_run` ("could not deliver").
        """
        question = _clean(question, config.SOCIAL_Q_MAX)
        opts = [_clean(o, config.SOCIAL_OPT_MAX) for o in (options or [])]
        opts = [o for o in opts if o][:config.SOCIAL_OPTS_MAX]
        if not question or len(opts) < 2:
            return False
        if not (isinstance(correct, int) and not isinstance(correct, bool)
                and 0 <= correct < len(opts)):
            correct = None
        payload = {
            "from": self.player_id,
            "to": to_id or "all",
            "q": question,
            "opts": opts,
            "correct": correct,
        }
        with self._lock:
            self._outbox.append(("send", payload))
            self._sent += 1
        self._wake.set()
        return True

    def send_answer(self, item, choice, correct):
        """Report the answer to a question taken from `take_question()`."""
        if not isinstance(item, dict):
            return False
        payload = {
            "sender": item.get("from") or "",
            "qid": item.get("id") or "",
            "by": self.name,
            "choice": _clean(choice, config.SOCIAL_OPT_MAX),
            "correct": correct if isinstance(correct, bool) else None,
        }
        if not payload["sender"] or not payload["qid"]:
            return False
        with self._lock:
            self._outbox.append(("answer", payload))
        self._wake.set()
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    # --- worker -------------------------------------------------------------
    def _post(self, path, payload):
        url = self._base + path
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "TQG/1.0"}
        if config.RELAY_TOKEN:
            headers["X-App-Token"] = config.RELAY_TOKEN
        # Sending questions is gated separately; this build usually has no token
        # and simply never sends one (see config.SOCIAL_SEND_TOKEN).
        if path == "/v1/send-question" and self._send_token:
            headers["X-Send-Token"] = self._send_token
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read(65536)
            parsed = json.loads(body or b"{}")
            if not isinstance(parsed, dict):
                return False, {}
            return True, parsed
        except urllib.error.HTTPError as exc:
            # A 4xx is an answer, not a network failure: the send really did
            # fail ("nobody to send to", "join presence first"). Surface it.
            detail = ""
            try:
                detail = json.loads(exc.read() or b"{}").get("error", "")
            except Exception:
                detail = ""
            self._last_error = detail or ("http %d" % exc.code)
            return False, {"_error": self._last_error, "_code": exc.code}
        except Exception as exc:
            self._last_error = type(exc).__name__
            return False, {"_error": self._last_error, "_code": 0}

    def _drain_outbox(self):
        while True:
            with self._lock:
                if not self._outbox:
                    return
                kind, payload = self._outbox.pop(0)
            path = "/v1/send-question" if kind == "send" else "/v1/answer"
            ok, data = self._post(path, payload)
            if kind == "send":
                # Record what the relay actually said. The UI must not claim a
                # question was sent just because it was queued.
                outcome = {
                    "ok": ok,
                    "to": payload.get("to", "all"),
                    "q": payload.get("q", ""),
                    "qid": data.get("id") or "",
                    "delivered": data.get("delivered") or [],
                    "error": "" if ok else (data.get("_error") or "offline"),
                }
                with self._lock:
                    self._send_outcomes.append(outcome)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._drain_outbox()
                with self._lock:
                    name = self._name
                ok, data = self._post("/v1/presence", {
                    "id": self.player_id,
                    "name": name,
                    "platform": _platform_label(),
                })
                now = time.time()
                with self._lock:
                    if ok and data.get("ok"):
                        self._status = "online"
                        self._last_ok = now
                        self._last_error = ""
                        self._online = data.get("online") or []
                        self._inbox.extend(data.get("inbox") or [])
                        if len(self._inbox) > config.SOCIAL_INBOX_MAX:
                            del self._inbox[:-config.SOCIAL_INBOX_MAX]
                        self._results.extend(data.get("results") or [])
                    else:
                        self._status = "offline"
                        # Keep the last known list briefly: a single dropped
                        # poll should not make the room flicker empty.
                        if now - self._last_ok > max(15.0, self._poll_secs * 3):
                            self._online = []
            except Exception:
                with self._lock:
                    self._status = "offline"
            self._wake.wait(self._poll_secs)
            self._wake.clear()
