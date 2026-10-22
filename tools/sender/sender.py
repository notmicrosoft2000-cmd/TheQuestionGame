#!/usr/bin/env python3
"""The Question Game — OPERATOR SENDER.

This is the *other half* of the game's online feature, and it is deliberately a
separate program:

  * the game (everyone's download) can only RECEIVE and answer questions;
  * only this app can WRITE them, because only this app holds the send token.

The relay enforces that split: /v1/send-question refuses any caller that does
not present RELAY_SEND_TOKEN as X-Send-Token before it even reads the body. This
app reads that secret from TQG_SEND_TOKEN and never ships with one baked in.

HOW IT WORKS, END TO END

    player's game            this app                   the relay
    -----------            --------                   --------
    polls /v1/presence  ->  polls /v1/presence      ->  keeps the room in memory
    shows ONLINE screen     sees who is playing       ->  expires idle peers
    plays a question        composes a question       ->  one-shot delivery:
    answers it              posts /v1/send-question        the item is cleared
                             (with X-Send-Token)            the moment it is
                             <- "delivered to N"             handed over
                            polls /v1/presence      <-  the player's answer comes
                             sees RIGHT / WRONG            back on the next poll

The player never needs to know any of this. From their side it is: the game
joins a room, and things arrive.

RUNNING IT

    TQG_SEND_TOKEN=... python tools/sender/sender.py

or with no environment at all: the app looks for the token in
<repo>/tqg-token.txt, then in the game's appdata folder, and if it still has
none it asks for one, checks it against the relay, and remembers it (0600).

    python tools/sender/sender.py        # then paste the token when asked

The token is the relay's RELAY_SEND_TOKEN. On the relay host it lives in
/opt/tqg-relay/relay.env, root-only:

    ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"

Nothing here touches the AI upstream or the Groq key.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

# Import the game package without installing it. The sender is meant to be run
# straight from a checkout: <repo>/tools/sender/sender.py -> <repo>/games/remastered
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_GAME_ROOT = os.path.join(_REPO, "games", "remastered")
if _GAME_ROOT not in sys.path:
    sys.path.insert(0, _GAME_ROOT)

import pygame  # noqa: E402

from TheQuestionGameRemastered import config, ui  # noqa: E402
from TheQuestionGameRemastered import social as social_mod  # noqa: E402

TITLE = "QUESTION TRANSMITTER"
SUBTITLE = "(OPERATOR ONLY)"

# The sender is a menu, not a game: cooler, dimmer, no window games.
COLOR_ACCENT = (200, 180, 90)
COLOR_GOOD = (90, 200, 90)
COLOR_BAD = (200, 80, 80)
COLOR_DIM = (110, 110, 110)
COLOR_DIMMER = (80, 80, 80)
COLOR_PANEL = (14, 14, 16)
COLOR_EDGE = (64, 64, 70)
COLOR_TEXT = (205, 205, 205)

WIN_W, WIN_H = 960, 700
FPS = 60

# The tab order. "to" is first so the recipient is always one key away.
FIELD_ORDER = ["to", "q", "o0", "o1", "o2", "o3", "correct", "send", "back"]
OPTION_KEYS = ["o0", "o1", "o2", "o3"]
OPTION_LETTERS = ["A", "B", "C", "D"]
TEXT_KEYS = ["q"] + OPTION_KEYS

TOKEN_FILE = os.path.join(config.APP_DATA_DIR, "sender_token")
REPO_TOKEN_FILE = os.path.join(_REPO, "tqg-token.txt")

HELP_STORY = [
    ("THE QUESTION GAME — OPERATOR SENDER", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("You are the operator. The game everyone", COLOR_TEXT),
    ("downloads is the RECEIVER: it joins the room,", COLOR_TEXT),
    ("plays what reaches it and answers back. Only", COLOR_TEXT),
    ("this program can WRITE — it holds the token.", COLOR_TEXT),
    ("", COLOR_DIM),
    ("THE RELAY — YES, THE HOME SERVER IS INVOLVED", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("Everything goes through one relay, and that", COLOR_DIM),
    ("relay is the maintainer's own machine on their", COLOR_DIM),
    ("home network at 192.168.99.56:", COLOR_DIM),
    ("  %s" % config.SOCIAL_URL, COLOR_ACCENT),
    ("That address is a Tailscale Funnel: the relay", COLOR_DIM),
    ("listens on 127.0.0.1:8090 at home and the", COLOR_DIM),
    ("funnel forwards it out. It is the SAME relay", COLOR_DIM),
    ("that answers the AI.", COLOR_DIM),
    ("", COLOR_DIM),
    ("Players poll /v1/presence every few seconds;", COLOR_DIM),
    ("you post to /v1/send-question with the token.", COLOR_DIM),
    ("Answers come back on the next poll.", COLOR_DIM),
    ("", COLOR_DIM),
    ("The room lives in memory only: no database, no", COLOR_DIM),
    ("accounts, no history. Restart it and it is empty.", COLOR_DIM),
    ("", COLOR_DIM),
    ("THE TOKEN", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("It is the relay's RELAY_SEND_TOKEN, in relay.env", COLOR_DIM),
    ("on the relay host:", COLOR_DIM),
    ("  ssh nept@192.168.99.56 \"sudo grep \\", COLOR_TEXT),
    ("    RELAY_SEND_TOKEN /opt/tqg-relay/relay.env\"", COLOR_TEXT),
    ("", COLOR_DIM),
    ("Paste it in; it is checked against the relay", COLOR_DIM),
    ("first, then stored with 0600. TQG_SEND_TOKEN and", COLOR_DIM),
    ("tqg-token.txt work as well.", COLOR_DIM),
]

HELP_KEYS = [
    ("KEYS", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("TAB / SHIFT+TAB   move between fields", COLOR_TEXT),
    ("ENTER            edit the field, or press it", COLOR_TEXT),
    ("UP / DOWN        pick who receives the question", COLOR_TEXT),
    ("1 2 3 4          set the correct option", COLOR_TEXT),
    ("MOUSE WHEEL      scroll the form", COLOR_TEXT),
    ("F1 or H          this help", COLOR_TEXT),
    ("ESC              quit", COLOR_TEXT),
    ("CTRL+X           forget the saved token", COLOR_TEXT),
    ("", COLOR_DIM),
    ("WHAT PRESSING SEND DOES", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("The question goes to the relay with your token.", COLOR_DIM),
    ("The relay hands it to everyone it was addressed", COLOR_DIM),
    ("to, once. The game shows it as the next question", COLOR_DIM),
    ("and the answer travels back to you.", COLOR_DIM),
    ("", COLOR_DIM),
    ("The DELIVERY panel says what the relay actually", COLOR_DIM),
    ("replied. QUEUED IS NOT DELIVERED. Read it.", COLOR_DIM),
    ("", COLOR_DIM),
    ("WHO IS IN THE ROOM", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("The room only knows about the games that are", COLOR_DIM),
    ("polling right now. A closed game is not in the", COLOR_DIM),
    ("room and cannot be reached.", COLOR_DIM),
]


# --- the token ----------------------------------------------------------------
# Where the token can come from, in order:
#
#   1. TQG_SEND_TOKEN in the environment (an explicitly empty one means
#      "no token" and stops the search — the tests rely on that).
#   2. <repo>/tqg-token.txt — a plain file with the token in it. Hand-made,
#      easy to edit, never written by the app, and gitignored.
#   3. <appdata>/sender_token — the copy the app saved itself, 0600.
#   4. Nothing: the app asks for it on the token screen.
#
# The token is the relay's RELAY_SEND_TOKEN. It is a secret: it must never be
# committed, never be baked into a build, and never be shipped with the game.


def _env_token():
    """The token from the environment. Present-but-empty means "no token"."""
    env = os.environ.get("TQG_SEND_TOKEN")
    if env is None:
        return ""
    return env.strip()


def _read_token_file(path):
    """Read a token out of a text file. Tolerates KEY=value lines."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError:
        return ""
    if not raw:
        return ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip().upper()
            if "TOKEN" in key and value.strip():
                return value.strip().strip("\"'")
            continue
        return line
    return ""


def _repo_token():
    """The token from <repo>/tqg-token.txt, if that file is there."""
    return _read_token_file(REPO_TOKEN_FILE)


def _saved_token():
    """The token the app saved for itself last time."""
    return _read_token_file(TOKEN_FILE)


def resolve_token():
    """(token, where it came from). The environment wins."""
    env = _env_token()
    if env:
        return env, "TQG_SEND_TOKEN"
    if os.environ.get("TQG_SEND_TOKEN") is not None:
        return "", ""             # explicitly empty: do not fall back
    repo = _repo_token()
    if repo:
        return repo, "tqg-token.txt"
    saved = _saved_token()
    if saved:
        return saved, "saved token"
    return "", ""


def _save_token(token):
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        tmp = TOKEN_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(token)
        os.chmod(tmp, 0o600)
        os.replace(tmp, TOKEN_FILE)
        return True
    except OSError:
        return False


def _forget_token():
    try:
        os.remove(TOKEN_FILE)
        return True
    except OSError:
        return False


def probe_token(token):
    """Ask the relay whether it would accept this token — without sending.

    The relay checks the token *before* it looks at the body, so an empty body
    is rejected by validation only after the token gate has already let us
    through: a 400 means the token is good, a 403 means it is not.
    """
    url = config.SOCIAL_URL.rstrip("/") + "/v1/send-question"
    req = urllib.request.Request(
        url, data=b"{}", method="POST",
        headers={"Content-Type": "application/json", "X-Send-Token": token or ""})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read(1024)
            return "ok", ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("error", "")
        except Exception:
            detail = ""
        if exc.code == 403:
            return "bad", detail or "sending is restricted"
        if exc.code in (400, 404, 405, 422):
            return "ok", ""          # we got past the token gate
        return "bad", detail or ("http %d" % exc.code)
    except Exception as exc:
        return "offline", type(exc).__name__


def _fit(text, font, max_w):
    """Shorten text with an ellipsis so it never spills out of its panel."""
    if max_w <= 0:
        return ""
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + "...")[0] > max_w:
        text = text[:-1]
    return (text + "...") if text else ""


def _wrap(text, font, max_w, max_lines=None):
    """Break text into lines that fit `max_w`.

    Words are kept whole where possible; a word longer than the panel is
    split hard, because a question must never be cut off mid-word with an
    ellipsis — the operator has to be able to read what they are sending.
    Returns (lines, hidden_count).
    """
    text = (text or "").rstrip()
    if not text:
        return [""], 0
    if max_w <= 0:
        return [text], 0

    def hard_split(word):
        """Break a word that cannot fit on a line of its own."""
        out = []
        cur = ""
        for ch in word:
            if cur and font.size(cur + ch)[0] > max_w:
                out.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    lines = []
    cur = ""
    for word in text.split(" "):
        if font.size(word)[0] > max_w:
            if cur:
                lines.append(cur)
                cur = ""
            pieces = hard_split(word)
            lines.extend(pieces[:-1])
            cur = pieces[-1]
            continue
        trial = word if not cur else cur + " " + word
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    if max_lines is not None and len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines]
        return lines, hidden
    return lines, 0


class Sender:
    def __init__(self, token=None):
        pygame.init()
        pygame.display.set_caption("%s %s" % (TITLE, SUBTITLE))
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        pygame.key.set_repeat(400, 40)
        try:
            icon = pygame.image.load(config.asset_path("windowq.png")).convert_alpha()
            pygame.display.set_icon(icon)
        except Exception:
            pass

        self.now = 0.0
        self.running = True
        self.starfield = ui.build_starfield(WIN_W, WIN_H)

        self.operator_id = "operator-%s" % os.urandom(4).hex()
        self.operator_name = os.environ.get("TQG_SENDER_NAME", "OPERATOR")

        # --- the token ------------------------------------------------------
        if token is None:
            token, source = resolve_token()
        else:
            source = "given"
        self.token = token or ""
        self.token_source = source
        self.token_state = "checking" if self.token else "missing"
        self.token_detail = ""
        self.token_input = ""
        self.unlocking = not self.token

        # The room client. `enabled` False just means the thread never starts —
        # handy for offline UI work. Sending still requires the token.
        self.social = social_mod.SocialClient(
            self.operator_id, self.operator_name,
            send_token=self.token, enabled=True)

        self.recipient = {"id": "all", "name": "EVERYONE"}
        self.toast = None                # {"text","at","tone","until"}
        self.results = []                # last few verdicts, newest first
        self.sent_log = []               # local record of what we fired off
        self.sent_by_qid = {}            # qid -> the question we sent
        self.help = False

        # Compose state.
        self.fields = {
            "q": "", "o0": "", "o1": "", "o2": "", "o3": "",
            "correct": 0,
        }
        self.focus = 1                   # start on the question field
        self.editing = False

        self.room_rects = []
        self.field_rects = []
        self.compose_scroll = 0
        self.compose_focus = -1
        self._layout()
        if self.token:
            self._validate_async(self.token)

    # --- token ---------------------------------------------------------------
    def _validate_async(self, token):
        """Check the token against the relay without blocking the UI."""
        def work():
            state, detail = probe_token(token)
            self.token_state = state
            self.token_detail = detail
            if state == "bad":
                self.unlocking = True
        threading.Thread(target=work, daemon=True).start()

    def _unlock(self):
        """Take the typed token, check it, and keep it if the relay agrees."""
        token = self.token_input.strip()
        if not token:
            self.note("TYPE THE TOKEN FIRST", "bad")
            return
        self.token_state = "checking"
        self.token_detail = ""
        self.note("CHECKING THE TOKEN...", "info", 2.0)

        def work():
            state, detail = probe_token(token)
            self.token_state = state
            self.token_detail = detail
            if state == "ok":
                self.token = token
                try:
                    self.social.set_send_token(token)
                except Exception:
                    pass
                _save_token(token)
                self.unlocking = False
                self.token_input = ""
                self.note("TOKEN ACCEPTED — YOU CAN WRITE", "good", 8.0)
            elif state == "bad":
                self.note("TOKEN REFUSED — " + str(detail or "").upper(), "bad", 10.0)
            else:
                self.note("RELAY UNREACHABLE — " + str(detail or "").upper(), "bad", 10.0)
        threading.Thread(target=work, daemon=True).start()

    def _forget(self):
        """Throw the token away (and the saved copy) and ask again."""
        self.token = ""
        self.token_state = "missing"
        self.token_detail = ""
        self.token_input = ""
        self.unlocking = True
        try:
            self.social.set_send_token("")
        except Exception:
            pass
        _forget_token()
        self.note("TOKEN CLEARED", "info", 4.0)

    # --- layout -------------------------------------------------------------
    def _layout(self):
        w, h = self.screen.get_size()
        # A slightly smaller text size than the game uses: this is a form, and
        # the operator has to see a whole question at once.
        self.font_large, self.font_med, self.font_small = ui.get_scaled_fonts(
            {"settings": {"text_size": 0.85}}, w, h)
        # The help screen has a lot to say; it gets its own, smaller font so
        # that nothing is clipped and nothing has to be cut off at the bottom.
        self.font_help = ui.get_scaled_fonts(
            {"settings": {"text_size": 0.55}}, w, h)[2]
        pad = max(10, int(w * 0.016))
        gap = pad
        head_h = int(h * 0.125)
        foot_h = max(26, int(h * 0.058))
        strip_h = max(90, int(h * 0.20))
        total_w = w - 2 * pad
        room_w = int(total_w * 0.24)
        # The body: the room on the left, the form on the right. The form gets
        # the room it needs — a question is 200 characters and it has to be
        # readable, not clipped.
        body_h = h - head_h - foot_h - strip_h - 2 * gap
        top = head_h
        body_bottom = top + body_h
        strip_top = body_bottom + gap

        self.rect_head = pygame.Rect(0, 0, w, head_h)
        self.rect_room = pygame.Rect(pad, top, room_w, body_h)
        self.rect_comp = pygame.Rect(pad + room_w + gap, top,
                                     total_w - room_w - gap, body_h)
        half = (total_w - gap) // 2
        self.rect_delivery = pygame.Rect(pad, strip_top, half, strip_h)
        self.rect_replies = pygame.Rect(pad + half + gap, strip_top,
                                        total_w - half - gap, strip_h)
        self.rect_foot = pygame.Rect(0, h - foot_h, w, foot_h)
        # Kept for the older helpers: the right-hand strip as a whole.
        self.rect_side = pygame.Rect(pad, strip_top, total_w, strip_h)

    # --- helpers ------------------------------------------------------------
    def note(self, text, tone="info", seconds=6.0):
        # Use the real clock, not the last frame's stamp: a note written
        # between frames must not look expired the moment it appears.
        now = pygame.time.get_ticks() / 1000.0
        self.now = max(self.now, now)
        self.toast = {"text": text, "at": self.now, "tone": tone,
                      "until": self.now + seconds}

    def _options(self):
        return [self.fields[k] for k in OPTION_KEYS if self.fields[k].strip()]

    def _status(self):
        try:
            return self.social.status()
        except Exception:
            return "offline"

    def _others(self):
        try:
            return self.social.others()
        except Exception:
            return []

    def _room_rows(self):
        rows = [{"id": "all", "name": "EVERYONE", "tag": "BROADCAST"}]
        for p in self._others():
            rows.append({"id": p.get("id", ""),
                         "name": str(p.get("name", "?")).upper(), "tag": ""})
        return rows

    def _can_send_now(self):
        return bool(self.token)

    def _recipient_label(self):
        to = self.recipient or {"id": "all", "name": "EVERYONE"}
        name = str(to.get("name", "EVERYONE")).upper()
        if to.get("id") == "all":
            return name + "  (BROADCAST)"
        return name

    # --- sending ------------------------------------------------------------
    def fire(self):
        if not self._can_send_now():
            self.note("NO SEND TOKEN — PRESS F1 FOR HOW TO GET ONE", "bad", 8.0)
            return
        question = self.fields["q"].strip()
        opts = self._options()
        if not question:
            self.note("THE QUESTION IS EMPTY", "bad")
            return
        if len(opts) < 2:
            self.note("NEEDS AT LEAST TWO OPTIONS", "bad")
            return
        correct = self.fields.get("correct", 0)
        if correct >= len(opts):
            correct = 0
        to = self.recipient or {"id": "all", "name": "EVERYONE"}
        ok = False
        try:
            ok = self.social.send_question(to.get("id", "all"), question,
                                           opts, correct)
        except Exception:
            ok = False
        if ok:
            # Queued, not delivered. The relay's answer arrives in update().
            self.sent_log.insert(0, {
                "to": str(to.get("name", "EVERYONE")).upper(),
                "q": question, "at": self.now, "state": "SENDING", "n": 0})
            del self.sent_log[8:]
            self.note("SENDING TO " + str(to.get("name", "EVERYONE")).upper()
                      + " ...", "info", 3.0)
        else:
            self.note("COULD NOT QUEUE THE QUESTION", "bad")

    def _apply_outcome(self, out):
        """Turn the relay's answer about a queued send into something honest."""
        q = out.get("q", "")
        state = out.get("state", "")
        if out.get("ok"):
            n = len(out.get("delivered") or [])
            state = "DELIVERED"
            if n == 1:
                self.note("DELIVERED TO 1 PLAYER", "good", 6.0)
            else:
                self.note("DELIVERED TO %d PLAYERS" % n, "good", 6.0)
        else:
            err = str(out.get("error") or "offline").lower()
            if "restricted" in err:
                state = "REFUSED"
                self.note("THE RELAY REFUSED IT — THE TOKEN IS WRONG", "bad", 10.0)
            elif "nobody" in err:
                state = "NOBODY"
                self.note("NOBODY TO SEND TO — IS ANYONE PLAYING?", "bad", 8.0)
            elif "presence" in err:
                state = "NOT SEEN"
                self.note("THE RELAY HAS NOT SEEN YOU YET — TRY AGAIN", "bad", 8.0)
            else:
                state = "FAILED"
                self.note("SEND FAILED — " + str(out.get("error", "")).upper(),
                          "bad", 8.0)
        for entry in self.sent_log:
            if entry.get("q") == q and entry.get("state") == "SENDING":
                entry["state"] = state
                entry["n"] = len(out.get("delivered") or [])
                if state == "DELIVERED":
                    # Only now is the question really gone. If the send was
                    # refused, the form keeps it, so nothing has to be retyped.
                    if self.fields.get("q", "").strip() == q.strip():
                        for k in TEXT_KEYS:
                            self.fields[k] = ""
                        self.fields["correct"] = 0
                        self.focus = 1
                        self.editing = False
                break
        if out.get("qid"):
            self.sent_by_qid[out["qid"]] = {"q": q, "to": out.get("to", "all")}

    # --- input --------------------------------------------------------------
    def handle_key(self, event):
        key = event.key
        unicode = event.unicode

        if key == pygame.K_F1:
            self.help = not self.help
            return
        if self.help:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER,
                       pygame.K_h):
                self.help = False
            return
        if self.unlocking:
            self._handle_unlock_key(event)
            return

        if key == pygame.K_ESCAPE:
            if self.editing:
                self.editing = False
            else:
                self.running = False
            return

        if self.editing:
            fkey = FIELD_ORDER[self.focus]
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                self.editing = False
                if key == pygame.K_TAB:
                    self._move(1)
            elif key == pygame.K_BACKSPACE:
                self.fields[fkey] = self.fields[fkey][:-1]
            elif unicode and unicode.isprintable() and unicode not in "\t\r\n":
                limit = config.SOCIAL_Q_MAX if fkey == "q" else config.SOCIAL_OPT_MAX
                if len(self.fields[fkey]) < limit:
                    self.fields[fkey] += unicode
            return

        fkey = FIELD_ORDER[self.focus]
        if key in (pygame.K_TAB, pygame.K_DOWN) and fkey != "to":
            self._move(1)
        elif key in (pygame.K_UP,) and fkey != "to":
            self._move(-1)
        elif key == pygame.K_TAB and fkey == "to":
            self._move(1)
        elif key in (pygame.K_UP, pygame.K_DOWN) and fkey == "to":
            self._move_recipient(1 if key == pygame.K_DOWN else -1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._activate(self.focus)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT) and fkey == "correct":
            n = max(2, len(self._options()))
            step = 1 if key == pygame.K_RIGHT else -1
            self.fields["correct"] = (self.fields["correct"] + step) % n
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            idx = key - pygame.K_1
            if idx < len(self._options()):
                self.fields["correct"] = idx

    def _handle_unlock_key(self, event):
        key = event.key
        unicode = event.unicode
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._unlock()
        elif key == pygame.K_BACKSPACE:
            self.token_input = self.token_input[:-1]
        elif key == pygame.K_ESCAPE:
            self.running = False
        elif unicode and unicode.isprintable() and unicode not in "\t\r\n":
            if len(self.token_input) < 200:
                self.token_input += unicode

    def _move(self, step):
        self.focus = (self.focus + step) % len(FIELD_ORDER)

    def _move_recipient(self, step):
        rows = self._room_rows()
        if not rows:
            return
        ids = [r["id"] for r in rows]
        cur = (self.recipient or {}).get("id", "all")
        try:
            idx = ids.index(cur)
        except ValueError:
            idx = 0
        idx = (idx + step) % len(rows)
        self.recipient = rows[idx]

    def _activate(self, idx):
        fkey = FIELD_ORDER[idx]
        if fkey in TEXT_KEYS:
            self.editing = True
        elif fkey == "to":
            self._move_recipient(1)
        elif fkey == "correct":
            n = max(2, len(self._options()))
            self.fields["correct"] = (self.fields["correct"] + 1) % n
        elif fkey == "send":
            self.fire()
        elif fkey == "back":
            self.running = False

    def handle_click(self, pos):
        if self.help:
            self.help = False
            return
        if self.unlocking:
            return
        for rect, idx in self.field_rects:
            if rect.collidepoint(pos):
                self.focus = idx
                if FIELD_ORDER[idx] in TEXT_KEYS:
                    self.editing = True
                else:
                    self._activate(idx)
                return
        for rect, peer in self.room_rects:
            if rect.collidepoint(pos):
                self.recipient = peer
                self.focus = 0
                return

    # --- update -------------------------------------------------------------
    def _harvest(self):
        """Take everything the worker thread produced since the last look."""
        try:
            for res in self.social.take_results():
                self.results.insert(0, res)
                del self.results[6:]
        except Exception:
            pass
        try:
            for out in self.social.take_send_outcomes():
                self._apply_outcome(out)
        except Exception:
            pass

    def update(self):
        self.now = pygame.time.get_ticks() / 1000.0
        if self.toast and self.now > self.toast.get("until", 0):
            self.toast = None
        self._harvest()

    # --- draw ---------------------------------------------------------------
    def draw(self):
        s = self.screen
        w, h = s.get_size()
        s.fill(config.COLOR_BLACK)
        self.room_rects = []
        self.field_rects = []
        try:
            ui.draw_starfield(s, w, h, self.now, self.starfield)
        except Exception:
            pass

        self._draw_header(s, w, h)
        if self.help:
            self._draw_help(s, w, h)
        else:
            self._draw_room(s, self.rect_room)
            if self.unlocking:
                self._draw_unlock(s, self.rect_comp)
            else:
                self._draw_compose(s, self.rect_comp)
            self._draw_delivery(s, self.rect_delivery)
            self._draw_replies(s, self.rect_replies)
        self._draw_footer(s, w, h)

        try:
            ui.apply_vhs_effects(s, w, h, {"settings": {"vhs_intensity": 0.55}})
        except Exception:
            pass
        pygame.display.flip()

    def _panel(self, s, rect, title):
        pygame.draw.rect(s, COLOR_PANEL, rect)
        pygame.draw.rect(s, COLOR_EDGE, rect, 1)
        t = self.font_small.render(title, True, config.COLOR_DIM_RED)
        s.blit(t, (rect.x + 10, rect.y + 7))
        line_y = rect.y + 9 + t.get_height()
        pygame.draw.line(s, COLOR_EDGE, (rect.x + 1, line_y),
                         (rect.x + rect.width - 2, line_y), 1)
        return pygame.Rect(rect.x + 10, line_y + 6,
                           rect.width - 20, rect.bottom - line_y - 12)

    def _draw_header(self, s, w, h):
        title = self.font_large.render(TITLE, True, config.COLOR_RED)
        s.blit(title, (20, int(h * 0.03)))
        s.blit(self.font_small.render(SUBTITLE, True, COLOR_DIM),
               (24, int(h * 0.03) + title.get_height() + 2))

        st = self._status()
        if st == "online":
            relay_txt, relay_col = "RELAY: ONLINE", COLOR_GOOD
        elif st == "connecting":
            relay_txt, relay_col = "RELAY: CONNECTING", COLOR_ACCENT
        elif st == "disabled":
            relay_txt, relay_col = "RELAY: DISABLED", COLOR_DIM
        else:
            relay_txt, relay_col = "RELAY: OFFLINE", COLOR_BAD

        if self.token_state == "ok":
            tok_txt, tok_col = "TOKEN: ACCEPTED", COLOR_GOOD
        elif self.token_state == "checking":
            tok_txt, tok_col = "TOKEN: CHECKING", COLOR_ACCENT
        elif self.token_state == "bad":
            tok_txt, tok_col = "TOKEN: REFUSED", COLOR_BAD
        elif self.token_state == "offline":
            tok_txt, tok_col = "TOKEN: RELAY UNREACHABLE", COLOR_BAD
        else:
            tok_txt, tok_col = "TOKEN: MISSING", COLOR_BAD

        n = len(self._others())
        lines = [
            (relay_txt, relay_col),
            (tok_txt, tok_col),
            ("%d PLAYER%s ONLINE" % (n, "" if n == 1 else "S"),
             COLOR_TEXT if n else COLOR_DIM),
        ]
        y = int(h * 0.03)
        for txt, col in lines:
            surf = self.font_small.render(txt, True, col)
            s.blit(surf, (w - surf.get_width() - 20, y))
            y += self.font_small.get_linesize() + 3

    def _draw_room(self, s, rect):
        inner = self._panel(s, rect, "THE ROOM")
        y = inner.y
        rows = self._room_rows()
        focused = (self.focus == 0 and not self.editing)
        s.blit(self.font_small.render(
            "PICK WHO GETS IT", True, COLOR_DIMMER), (inner.x, y))
        y += self.font_small.get_linesize() + 6

        for peer in rows:
            selected = (self.recipient or {}).get("id") == peer["id"]
            if selected:
                color = COLOR_ACCENT
                prefix = "> "
            elif focused:
                color = COLOR_TEXT
                prefix = "  "
            else:
                color = COLOR_DIM
                prefix = "  "
            label = prefix + peer["name"]
            if peer.get("tag"):
                label += "  (" + peer["tag"] + ")"
            label = _fit(label, self.font_med, inner.width)
            surf = self.font_med.render(label, True, color)
            if selected:
                # a filled bar so the current recipient is obvious at a glance
                bar = pygame.Rect(inner.x - 6, y - 2, inner.width + 4,
                                  surf.get_height() + 4)
                pygame.draw.rect(s, COLOR_EDGE, bar)
            s.blit(surf, (inner.x, y))
            self.room_rects.append(
                (pygame.Rect(inner.x - 6, y - 2, inner.width + 8,
                             surf.get_height() + 4), peer))
            y += self.font_med.get_linesize() + 4
            if y > inner.bottom - self.font_med.get_linesize():
                break

        n = len(self._others())
        if n == 0:
            s.blit(self.font_small.render("NOBODY ELSE IS PLAYING",
                                          True, COLOR_DIMMER), (inner.x, y + 4))
        else:
            s.blit(self.font_small.render(
                "%d PLAYER%s PLAYING" % (n, "" if n == 1 else "S"),
                True, COLOR_DIMMER), (inner.x, y + 4))
            s.blit(self.font_small.render("[UP/DOWN] CHOOSE", True, COLOR_DIMMER),
                   (inner.x, y + 4 + self.font_small.get_linesize() + 2))

    def _compose_rows(self):
        """The rows of the compose panel: label, value, and a colour hint."""
        opts = self._options()
        rows = [{"key": "to", "label": "SEND TO",
                 "value": self._recipient_label(), "color": None}]
        rows.append({"key": "q", "label": "QUESTION",
                     "value": self.fields["q"], "color": None})
        for i, okey in enumerate(OPTION_KEYS):
            rows.append({"key": okey, "label": "OPTION %s" % OPTION_LETTERS[i],
                         "value": self.fields[okey], "color": None})
        c = self.fields["correct"]
        if c < len(opts):
            value = "%s) %s" % (OPTION_LETTERS[c], opts[c])
        else:
            value = "-"
        rows.append({"key": "correct", "label": "CORRECT ANSWER",
                     "value": value, "color": COLOR_ACCENT})
        rows.append({"key": "send", "label": "SEND",
                     "value": "FIRE IT" if self._can_send_now() else "NO TOKEN",
                     "color": COLOR_GOOD if self._can_send_now() else COLOR_BAD})
        rows.append({"key": "back", "label": "QUIT", "value": "CLOSE",
                     "color": COLOR_BAD})
        return rows

    def _draw_compose(self, s, rect):
        """The form.

        The values are wrapped, never truncated: a question is 200 characters
        and the operator has to be able to read every word of what they are
        sending. When the form is taller than the panel it scrolls, and the
        scroll follows whatever field is focused.
        """
        inner = self._panel(s, rect, "COMPOSE")
        lab_font = self.font_small
        val_font = self.font_med
        rows = self._compose_rows()
        label_w = max(lab_font.size(r["label"])[0] for r in rows) + 16
        vx = inner.x + label_w
        avail = max(60, inner.right - vx - 6)

        # Wrap first, so every row can be as tall as its text needs.
        laid = []
        total = 0
        for idx, r in enumerate(rows):
            focused = (idx == self.focus)
            editing = focused and self.editing
            text = r["value"] + ("_" if editing else "")
            lines, hidden = _wrap(text, val_font, avail)
            h = max(lab_font.get_linesize(),
                    len(lines) * val_font.get_linesize())
            laid.append({"r": r, "lines": lines, "hidden": hidden, "h": h,
                         "focused": focused, "y": total})
            total += h + 7
        total = max(0, total - 7)

        # Keep the focused row on screen.
        view_h = inner.height
        max_scroll = max(0, total - view_h)
        if self.compose_focus != self.focus:
            self.compose_focus = self.focus
            cur = laid[min(max(self.focus, 0), len(laid) - 1)]
            off = self.compose_scroll
            if cur["y"] < off:
                off = cur["y"]
            elif cur["y"] + cur["h"] > off + view_h:
                off = cur["y"] + cur["h"] - view_h + 6
            self.compose_scroll = max(0, min(off, max_scroll))
        off = max(0, min(self.compose_scroll, max_scroll))
        self.compose_scroll = off
        self.compose_overflow = max_scroll

        for idx, item in enumerate(laid):
            y = inner.y + item["y"] - off
            if y + item["h"] < inner.y - 4 or y > inner.bottom + 4:
                continue
            r = item["r"]
            color = r.get("color") or (
                COLOR_TEXT if item["focused"] else COLOR_DIM)
            lab_color = COLOR_ACCENT if item["focused"] else COLOR_DIM
            lab = lab_font.render(r["label"], True, lab_color)
            s.blit(lab, (inner.x, y + 3))
            ly = y
            for line in item["lines"]:
                s.blit(val_font.render(line, True, color), (vx, ly))
                ly += val_font.get_linesize()
            if item["hidden"]:
                s.blit(self.font_small.render(
                    "+%d MORE LINES" % item["hidden"], True, COLOR_DIMMER),
                    (vx, ly))
                ly += self.font_small.get_linesize()
            self.field_rects.append((pygame.Rect(inner.x - 6, y - 3,
                                                 inner.width + 8,
                                                 max(item["h"], ly - y) + 6),
                                     idx))

        # A scrollbar, so it is obvious that there is more form below.
        if max_scroll > 0:
            bar_h = max(24, int(view_h * view_h / max(1, total)))
            bar_y = inner.y + int((view_h - bar_h) * (off / float(max_scroll)))
            pygame.draw.rect(s, COLOR_EDGE,
                             pygame.Rect(inner.right - 4, inner.y, 3, view_h))
            pygame.draw.rect(s, COLOR_ACCENT,
                             pygame.Rect(inner.right - 4, bar_y, 3, bar_h))

    def _scroll_compose(self, delta):
        """The mouse wheel scrolls the form."""
        self.compose_scroll = max(0, self.compose_scroll + delta)

    def _draw_side(self, s, rect):
        """Kept for callers that still ask for the whole bottom strip."""
        half = (rect.width - 10) // 2
        self._draw_delivery(s, pygame.Rect(rect.x, rect.y, half, rect.height))
        self._draw_replies(s, pygame.Rect(rect.x + half + 10, rect.y,
                                          rect.width - half - 10, rect.height))

    def _draw_delivery(self, s, rect):
        inner = self._panel(s, rect, "DELIVERY")
        y = inner.y
        if not self.sent_log:
            s.blit(self.font_small.render("NOTHING SENT YET", True, COLOR_DIMMER),
                   (inner.x, y))
            return
        for entry in self.sent_log[:4]:
            state = entry.get("state", "SENDING")
            if state == "DELIVERED":
                col = COLOR_GOOD
            elif state == "SENDING":
                col = COLOR_ACCENT
            else:
                col = COLOR_BAD
            head = "%s  %s" % (entry.get("to", "?"), state)
            s.blit(self.font_small.render(_fit(head, self.font_small,
                                               inner.width), True, col),
                   (inner.x, y))
            y += self.font_small.get_linesize() + 1
            lines, hidden = _wrap(entry.get("q", ""), self.font_small,
                                   inner.width, max_lines=2)
            for line in lines:
                s.blit(self.font_small.render(line, True, COLOR_DIM),
                       (inner.x, y))
                y += self.font_small.get_linesize()
            if hidden:
                s.blit(self.font_small.render("+%d MORE LINES" % hidden, True,
                                              COLOR_DIMMER), (inner.x, y))
                y += self.font_small.get_linesize()
            y += 5
            if y > inner.bottom:
                break

    def _draw_replies(self, s, rect):
        inner = self._panel(s, rect, "REPLIES")
        y = inner.y
        if not self.results:
            s.blit(self.font_small.render("NO ANSWERS YET", True, COLOR_DIMMER),
                   (inner.x, y))
            return
        for res in self.results[:4]:
            who = str(res.get("by") or "?").upper()
            verdict = res.get("correct")
            if verdict is True:
                vtext, vcol = "RIGHT", COLOR_GOOD
            elif verdict is False:
                vtext, vcol = "WRONG", COLOR_BAD
            else:
                vtext, vcol = "ANSWERED", COLOR_DIM
            choice = str(res.get("choice") or "")
            line = "%s  %s%s" % (who, vtext,
                                 ("  (" + choice + ")") if choice else "")
            s.blit(self.font_small.render(_fit(line, self.font_small, inner.width),
                                          True, vcol), (inner.x, y))
            y += self.font_small.get_linesize() + 1
            sent = self.sent_by_qid.get(res.get("qid"))
            if sent:
                lines, hidden = _wrap(sent.get("q", ""), self.font_small,
                                      inner.width, max_lines=2)
                for qline in lines:
                    s.blit(self.font_small.render(qline, True, COLOR_DIMMER),
                           (inner.x, y))
                    y += self.font_small.get_linesize()
                if hidden:
                    s.blit(self.font_small.render("+%d MORE LINES" % hidden, True,
                                                  COLOR_DIMMER), (inner.x, y))
                    y += self.font_small.get_linesize()
                y += 4
            if y > inner.bottom:
                break

    def _draw_unlock(self, s, rect):
        inner = self._panel(s, rect, "OPERATOR TOKEN REQUIRED")
        y = inner.y
        lines = [
            ("The relay only lets a holder of the send token write.", COLOR_TEXT),
            ("Everything else — the room, the players — already works.", COLOR_DIM),
            ("", COLOR_DIM),
            ("Read the token off the relay host:", COLOR_TEXT),
            ("  ssh nept@192.168.99.56 \\", COLOR_ACCENT),
            ("    \"sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env\"",
             COLOR_ACCENT),
            ("", COLOR_DIM),
        ]
        for txt, col in lines:
            if not txt:
                y += self.font_small.get_linesize() + 2
                continue
            s.blit(self.font_small.render(_fit(txt, self.font_small, inner.width),
                                          True, col), (inner.x, y))
            y += self.font_small.get_linesize() + 2

        y += 6
        shown = "*" * len(self.token_input)
        s.blit(self.font_small.render("TOKEN", True, COLOR_DIM), (inner.x, y + 3))
        s.blit(self.font_med.render(shown + "_", True, COLOR_TEXT),
               (inner.x + 60, y))
        y += self.font_med.get_linesize() + 10

        if self.token_state == "checking":
            s.blit(self.font_small.render("CHECKING...", True, COLOR_ACCENT),
                   (inner.x, y))
        elif self.token_state == "bad":
            s.blit(self.font_small.render(
                "REFUSED — " + str(self.token_detail or "").upper(), True, COLOR_BAD),
                (inner.x, y))
        elif self.token_state == "offline":
            s.blit(self.font_small.render(
                "THE RELAY IS UNREACHABLE", True, COLOR_BAD), (inner.x, y))

        s.blit(self.font_small.render(
            "[ENTER] AUTHENTICATE      [F1] HOW THIS WORKS", True, COLOR_DIMMER),
            (inner.x, inner.bottom - self.font_small.get_linesize()))

    def _draw_help(self, s, w, h):
        """The help screen: two columns, so nothing is cut off.

        The columns have a minimum width. On a window too small for two of
        them, the right column moves below the left one instead of over it.
        """
        rect = pygame.Rect(int(w * 0.05), int(h * 0.03),
                           int(w * 0.90), int(h * 0.94))
        inner = self._panel(s, rect, "HOW THIS WORKS")
        gap = 26
        stacked = inner.width < 2 * 360 + gap
        col_w = (inner.width - gap) // 2 if not stacked else inner.width
        x2 = inner.x + col_w + gap
        y2 = inner.y

        def draw(lines, x, y):
            for txt, col in lines:
                if not txt:
                    y += self.font_help.get_linesize() + 1
                    continue
                s.blit(self.font_help.render(_fit(txt, self.font_help, col_w),
                                              True, col), (x, y))
                y += self.font_help.get_linesize() + 1
                if y > inner.bottom:
                    break
            return y

        if stacked:
            y2 = draw(HELP_STORY, inner.x, inner.y) + 10
            draw(HELP_KEYS, inner.x, y2)
        else:
            draw(HELP_STORY, inner.x, inner.y)
            draw(HELP_KEYS, x2, y2)

    def _draw_footer(self, s, w, h):
        if self.toast:
            tone = self.toast.get("tone", "info")
            color = {"good": COLOR_GOOD, "bad": COLOR_BAD}.get(tone, COLOR_ACCENT)
            txt = _fit(self.toast["text"], self.font_med, w - 40)
            s.blit(self.font_med.render(txt, True, color), (20, h - 62))
        hints = "[TAB] FIELD  [ENTER] EDIT/ACT  [1-4] CORRECT  [F1] HELP  [ESC] QUIT"
        s.blit(self.font_small.render(hints, True, COLOR_DIMMER),
               (20, h - self.font_small.get_linesize() - 10))
        if self.token:
            s.blit(self.font_small.render("[CTRL+X] FORGET TOKEN", True, COLOR_DIMMER),
                   (w - 200, h - self.font_small.get_linesize() - 10))

    # --- run ----------------------------------------------------------------
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if (event.key == pygame.K_x and
                            event.mod & pygame.KMOD_CTRL):
                        self._forget()
                    else:
                        self.handle_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 4:
                        self._scroll_compose(-48)
                    elif event.button == 5:
                        self._scroll_compose(48)
                    elif event.button == 1:
                        self.handle_click(event.pos)
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (max(640, event.w), max(480, event.h)), pygame.RESIZABLE)
                    self.starfield = ui.build_starfield(*self.screen.get_size())
                    self._layout()
            self.update()
            self.draw()
            clock.tick(FPS)
        try:
            self.social.stop()
        except Exception:
            pass
        pygame.quit()


def main():
    token, source = resolve_token()
    if not token:
        print("[*] No token found — the app will ask for one.")
        print("    It looks, in order, at: TQG_SEND_TOKEN, %s," % REPO_TOKEN_FILE)
        print("    and the copy it saved in %s." % TOKEN_FILE)
        print("    To get it off the relay host:")
        print('      ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"')
    else:
        print("[*] Using the token from %s." % source)
    app = Sender(token=token)
    app.run()


if __name__ == "__main__":
    main()
