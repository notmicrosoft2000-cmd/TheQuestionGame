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

or just run it with no environment at all: the app asks for the token, checks
it against the relay, and remembers it (0600) in the game's appdata folder.

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

HELP_LINES = [
    ("THE QUESTION GAME — OPERATOR SENDER", COLOR_ACCENT),
    ("", COLOR_DIM),
    ("You are the operator. The game every player downloads is the RECEIVER:",
     COLOR_TEXT),
    ("it joins the room, plays what reaches it, and answers back. Only this",
     COLOR_TEXT),
    ("program can WRITE, because only this program holds the send token.",
     COLOR_TEXT),
    ("", COLOR_DIM),
    ("THE RELAY", COLOR_ACCENT),
    ("  Everything goes through one relay:", COLOR_DIM),
    ("    %s" % config.SOCIAL_URL, COLOR_DIM),
    ("  Players poll /v1/presence every few seconds; you post to",
     COLOR_DIM),
    ("  /v1/send-question with the token; answers come back on the next poll.",
     COLOR_DIM),
    ("", COLOR_DIM),
    ("THE TOKEN", COLOR_ACCENT),
    ("  It is the relay's RELAY_SEND_TOKEN (server/relay.env on the relay",
     COLOR_DIM),
    ("  host). Read it with:", COLOR_DIM),
    ("    ssh nept@192.168.99.56 \\", COLOR_TEXT),
    ("      \"sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env\"", COLOR_TEXT),
    ("  Then paste it into the app. It is checked against the relay before it",
     COLOR_DIM),
    ("  is accepted, and stored with 0600 in:", COLOR_DIM),
    ("    %s" % TOKEN_FILE, COLOR_DIM),
    ("", COLOR_DIM),
    ("KEYS", COLOR_ACCENT),
    ("  TAB / SHIFT+TAB    move between fields", COLOR_TEXT),
    ("  ENTER             edit the field / press the focused button", COLOR_TEXT),
    ("  UP / DOWN         choose who receives the question (TO field)", COLOR_TEXT),
    ("  1 2 3 4           set the correct option", COLOR_TEXT),
    ("  F1 or H           this help        ESC  quit", COLOR_TEXT),
]


# --- the token ----------------------------------------------------------------
def _env_token():
    """The token from the environment. Present-but-empty means "no token"."""
    env = os.environ.get("TQG_SEND_TOKEN")
    if env is None:
        return ""
    return env.strip()


def _file_token():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def resolve_token():
    """Environment first, then the saved copy."""
    env = _env_token()
    if env:
        return env
    if os.environ.get("TQG_SEND_TOKEN") is not None:
        return ""            # explicitly empty: do not fall back to the file
    return _file_token()


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
        self.token = token if token is not None else resolve_token()
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
        pad = max(10, int(w * 0.016))
        head_h = int(h * 0.135)
        foot_h = max(28, int(h * 0.065))
        gap = pad
        total = w - 2 * pad
        room_w = int(total * 0.22)
        side_w = int(total * 0.26)
        comp_w = total - room_w - side_w - 2 * gap
        top = head_h
        bottom = h - foot_h
        self.rect_head = pygame.Rect(0, 0, w, head_h)
        self.rect_room = pygame.Rect(pad, top, room_w, bottom - top)
        self.rect_comp = pygame.Rect(pad + room_w + gap, top, comp_w, bottom - top)
        self.rect_side = pygame.Rect(pad + room_w + gap + comp_w + gap, top,
                                     side_w, bottom - top)
        self.rect_foot = pygame.Rect(0, bottom, w, foot_h)

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
                       pygame.K_h, pygame.K_H):
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
            self._draw_side(s, self.rect_side)
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
        rows = self._room_rows()
        y = inner.y
        for peer in rows:
            selected = (self.recipient or {}).get("id") == peer["id"]
            focused = (self.focus == 0 and not self.editing)
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
            surf = self.font_med.render(label, True, color)
            s.blit(surf, (inner.x, y))
            self.room_rects.append(
                (pygame.Rect(inner.x - 6, y - 2, inner.width + 8,
                             surf.get_height() + 4), peer))
            y += self.font_med.get_linesize() + 4
            if y > inner.bottom - self.font_med.get_linesize():
                break
        if len(rows) == 1:
            s.blit(self.font_small.render("NOBODY ELSE IS PLAYING", True, COLOR_DIMMER),
                   (inner.x, y + 4))
        else:
            s.blit(self.font_small.render(
                "[UP/DOWN] CHOOSE", True, COLOR_DIMMER), (inner.x, y + 4))

    def _row(self, s, inner, y, label, value, focused, editing=False,
             value_color=None, vfont=None):
        """One labelled row. Returns the clickable rect."""
        lab_font = self.font_small
        vfont = vfont or self.font_med
        lab_color = COLOR_ACCENT if focused else COLOR_DIM
        val_color = value_color if value_color is not None else (
            COLOR_TEXT if focused else COLOR_DIM)
        lab = lab_font.render(label, True, lab_color)
        s.blit(lab, (inner.x, y + 3))
        vx = inner.x + lab.get_width() + 12
        avail = inner.right - vx
        text = value + ("_" if editing else "")
        text = _fit(text, vfont, avail)
        surf = vfont.render(text, True, val_color)
        s.blit(surf, (vx, y))
        return pygame.Rect(inner.x - 6, y - 2, inner.width + 8,
                           max(surf.get_height(), lab.get_height()) + 4)

    def _draw_compose(self, s, rect):
        inner = self._panel(s, rect, "COMPOSE")
        y = inner.y
        # The rows always fit the panel, even in the smallest window.
        row_h = max(self.font_med.get_linesize() + 4,
                    min(self.font_med.get_linesize() + 8,
                        inner.height // len(FIELD_ORDER)))
        opts = self._options()

        for idx, fkey in enumerate(FIELD_ORDER):
            focused = (idx == self.focus)
            editing = focused and self.editing
            if fkey == "to":
                r = self._row(s, inner, y, "SEND TO", self._recipient_label(),
                              focused)
            elif fkey in TEXT_KEYS:
                label = "QUESTION" if fkey == "q" else \
                    "OPTION %s" % OPTION_LETTERS[OPTION_KEYS.index(fkey)]
                r = self._row(s, inner, y, label, self.fields[fkey], focused,
                              editing)
            elif fkey == "correct":
                c = self.fields["correct"]
                if c < len(opts):
                    value = "%s) %s" % (OPTION_LETTERS[c], opts[c])
                else:
                    value = "-"
                r = self._row(s, inner, y, "CORRECT ANSWER", value, focused,
                              value_color=COLOR_ACCENT)
            elif fkey == "send":
                r = self._row(s, inner, y, "SEND",
                              "FIRE IT" if self._can_send_now()
                              else "NO TOKEN", focused,
                              value_color=COLOR_GOOD if self._can_send_now()
                              else COLOR_BAD)
            else:
                r = self._row(s, inner, y, "QUIT", "CLOSE", focused,
                              value_color=COLOR_BAD)
            self.field_rects.append((r, idx))
            y += row_h
            if y > inner.bottom:
                break

    def _draw_side(self, s, rect):
        split = rect.y + int(rect.height * 0.46)
        drect = pygame.Rect(rect.x, rect.y, rect.width, split - rect.y - 5)
        rrect = pygame.Rect(rect.x, split + 5, rect.width,
                            rect.bottom - split - 5)
        self._draw_delivery(s, drect)
        self._draw_replies(s, rrect)

    def _draw_delivery(self, s, rect):
        inner = self._panel(s, rect, "DELIVERY")
        y = inner.y
        if not self.sent_log:
            s.blit(self.font_small.render("NOTHING SENT YET", True, COLOR_DIMMER),
                   (inner.x, y))
            return
        for entry in self.sent_log[:5]:
            state = entry.get("state", "SENDING")
            if state == "DELIVERED":
                col = COLOR_GOOD
            elif state == "SENDING":
                col = COLOR_ACCENT
            else:
                col = COLOR_BAD
            head = "%s  %s" % (entry.get("to", "?"), state)
            surf = self.font_small.render(head, True, col)
            s.blit(surf, (inner.x, y))
            y += self.font_small.get_linesize() + 1
            q = _fit(entry.get("q", ""), self.font_small, inner.width)
            s.blit(self.font_small.render(q, True, COLOR_DIM), (inner.x, y))
            y += self.font_small.get_linesize() + 6
            if y > inner.bottom:
                break

    def _draw_replies(self, s, rect):
        inner = self._panel(s, rect, "REPLIES")
        y = inner.y
        if not self.results:
            s.blit(self.font_small.render("NO ANSWERS YET", True, COLOR_DIMMER),
                   (inner.x, y))
            return
        for res in self.results[:5]:
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
                s.blit(self.font_small.render(
                    _fit(sent.get("q", ""), self.font_small, inner.width),
                    True, COLOR_DIMMER), (inner.x, y))
                y += self.font_small.get_linesize() + 6
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
        rect = pygame.Rect(int(w * 0.12), int(h * 0.06),
                           int(w * 0.76), int(h * 0.88))
        inner = self._panel(s, rect, "HOW THIS WORKS")
        y = inner.y
        for txt, col in HELP_LINES:
            if not txt:
                y += self.font_small.get_linesize() + 2
                continue
            s.blit(self.font_small.render(_fit(txt, self.font_small, inner.width),
                                          True, col), (inner.x, y))
            y += self.font_small.get_linesize() + 2
            if y > inner.bottom:
                break

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
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
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
    token = resolve_token()
    if not token:
        print("[*] No TQG_SEND_TOKEN in the environment — the app will ask for it.")
        print("    Get it from the relay host:")
        print('      ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"')
    else:
        print("[*] Using the token from the environment.")
    app = Sender(token=token)
    app.run()


if __name__ == "__main__":
    main()
