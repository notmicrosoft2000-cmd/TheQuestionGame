#!/usr/bin/env python3
"""The Question Game — OPERATOR SENDER.

This is the *other half* of the game's online feature, and it is deliberately a
separate program:

  * the game (everyone's download) can only RECEIVE and answer questions;
  * only this app can WRITE them, because only this app holds the send token.

The relay enforces that split: /v1/send-question refuses any caller that does
not present RELAY_SEND_TOKEN as X-Send-Token before it even reads the body. This
app reads that secret from TQG_SEND_TOKEN and never ships with one baked in.

Run it with the token in the environment:

    TQG_SEND_TOKEN=... python tools/sender/sender.py

It talks to the same relay as the game (TQG_SOCIAL_URL, defaulting to the same
host as the game's TQG_RELAY_URL), joins the room under its own operator
identity, shows who is online, and lets you compose and fire off a question with
the mouse or the keyboard.

Nothing here touches the AI upstream or the Groq key.
"""
import os
import sys

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

WIN_W, WIN_H = 900, 680
FPS = 60

# Compose fields, in tab order. "correct" cycles, "send" fires.
FIELD_ORDER = ["q", "o0", "o1", "o2", "o3", "correct", "send", "back"]


def _token():
    """The send secret. Read fresh so a restart of the app picks up env edits."""
    return os.environ.get("TQG_SEND_TOKEN", "").strip()


class Sender:
    def __init__(self):
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

        # The room client. `enabled` False just means the thread never starts —
        # handy for offline UI work. Sending still requires the token.
        token = _token()
        self.social = social_mod.SocialClient(
            self.operator_id, self.operator_name,
            send_token=token, enabled=True)

        self.recipient = {"id": "all", "name": "EVERYONE"}
        self.room_selected = 0
        self.toast = None                # {"text","at","tone"}
        self.results = []                # last few verdicts, newest first
        self.sent_log = []               # local record of what we fired off

        # Compose state.
        self.fields = {
            "q": "", "o0": "", "o1": "", "o2": "", "o3": "",
            "correct": 0,
        }
        self.focus = 1                   # start on the question field
        self.editing = False

        self._layout()

    # --- layout -------------------------------------------------------------
    def _layout(self):
        self.room_rects = []
        self.field_rects = []
        w, h = self.screen.get_size()
        self.font_large, self.font_med, self.font_small = ui.get_scaled_fonts(
            {"settings": {}}, w, h)

    # --- helpers ------------------------------------------------------------
    def note(self, text, tone="info", seconds=6.0):
        self.toast = {"text": text, "at": self.now, "tone": tone,
                      "until": self.now + seconds}

    def _options(self):
        return [self.fields[k] for k in ("o0", "o1", "o2", "o3")
                if self.fields[k].strip()]

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

    def _can_send_now(self):
        return bool(_token())

    # --- sending ------------------------------------------------------------
    def fire(self):
        if not self._can_send_now():
            self.note("NO SEND TOKEN — SET TQG_SEND_TOKEN", "bad")
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
            self.sent_log.insert(0, {"to": to.get("name", "EVERYONE"),
                                     "q": question, "at": self.now})
            del self.sent_log[8:]
            self.note("SENT TO " + str(to.get("name", "EVERYONE")).upper(), "good")
            # Clear the form, keep the recipient so a burst is quick to fire.
            for k in ("q", "o0", "o1", "o2", "o3"):
                self.fields[k] = ""
            self.fields["correct"] = 0
            self.focus = 1
            self.editing = False
        else:
            self.note("SEND FAILED — RELAY OFFLINE OR REFUSED", "bad")

    # --- input --------------------------------------------------------------
    def handle_key(self, event):
        key = event.key
        unicode = event.unicode
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

        if key in (pygame.K_TAB, pygame.K_DOWN):
            self._move(1)
        elif key == pygame.K_UP:
            self._move(-1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._activate(self.focus)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT) and FIELD_ORDER[self.focus] == "correct":
            n = max(2, len(self._options()))
            step = 1 if key == pygame.K_RIGHT else -1
            self.fields["correct"] = (self.fields["correct"] + step) % n

    def _move(self, step):
        self.focus = (self.focus + step) % len(FIELD_ORDER)

    def _activate(self, idx):
        fkey = FIELD_ORDER[idx]
        if fkey in ("q", "o0", "o1", "o2", "o3"):
            self.editing = True
            audio_noop = None  # no SFX dependency here; keep it standalone
        elif fkey == "correct":
            n = max(2, len(self._options()))
            self.fields["correct"] = (self.fields["correct"] + 1) % n
        elif fkey == "send":
            self.fire()
        elif fkey == "back":
            self.running = False

    def handle_click(self, pos):
        for rect, idx in self.field_rects:
            if rect.collidepoint(pos):
                if idx == FIELD_ORDER.index("send"):
                    self.fire()
                elif idx == FIELD_ORDER.index("back"):
                    self.running = False
                else:
                    self.focus = idx
                    if FIELD_ORDER[idx] in ("q", "o0", "o1", "o2", "o3"):
                        self.editing = True
                    else:
                        self._activate(idx)
                return
        for rect, peer in self.room_rects:
            if rect.collidepoint(pos):
                self.recipient = peer
                self.room_selected = 0
                return

    # --- update -------------------------------------------------------------
    def update(self):
        self.now = pygame.time.get_ticks() / 1000.0
        if self.toast and self.now > self.toast.get("until", 0):
            self.toast = None
        try:
            for res in self.social.take_results():
                self.results.insert(0, res)
                del self.results[6:]
        except Exception:
            pass

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

        # Header
        title = self.font_large.render(TITLE, True, config.COLOR_RED)
        s.blit(title, (int(w * 0.06), int(h * 0.045)))
        s.blit(self.font_small.render(SUBTITLE, True, COLOR_DIM),
               (int(w * 0.06), int(h * 0.045) + title.get_height()))

        status = self._status()
        if not self._can_send_now():
            sl, sc = "NO SEND TOKEN — READ ONLY", COLOR_BAD
        elif status == "online":
            sl, sc = "RELAY: ONLINE", COLOR_GOOD
        elif status == "connecting":
            sl, sc = "RELAY: CONNECTING...", COLOR_ACCENT
        else:
            sl, sc = "RELAY: OFFLINE", COLOR_BAD
        s.blit(self.font_small.render(sl, True, sc), (int(w * 0.06), int(h * 0.045) + title.get_height() + self.font_small.get_linesize() + 2))

        self._draw_room(w, h)
        self._draw_compose(w, h)
        self._draw_toast(w, h)

        try:
            ui.apply_vhs_effects(s, w, h, {"settings": {"vhs_intensity": 0.7}})
        except Exception:
            pass
        pygame.display.flip()

    def _draw_room(self, w, h):
        s = self.screen
        x = int(w * 0.06)
        y = int(h * 0.235)
        s.blit(self.font_small.render("THE ROOM", True, config.COLOR_DIM_RED), (x, y))
        y += self.font_small.get_linesize() + 4

        rows = [{"id": "all", "name": "EVERYONE"}] + [
            {"id": p.get("id", ""), "name": str(p.get("name", "?")).upper()}
            for p in self._others()
        ]
        for peer in rows:
            selected = (self.recipient or {}).get("id") == peer["id"]
            color = COLOR_ACCENT if selected else COLOR_DIM
            prefix = "> " if selected else "  "
            label = ("BROADCAST  " if peer["id"] == "all" else "") + peer["name"]
            surf = self.font_med.render(prefix + label, True, color)
            s.blit(surf, (x, y))
            rect = pygame.Rect(x - 6, y - 2, int(w * 0.4), surf.get_height() + 4)
            self.room_rects.append((rect, peer))
            y += self.font_med.get_linesize() + 6

        if len(rows) == 1:
            s.blit(self.font_small.render("  NOBODY ELSE YET", True, COLOR_DIMMER),
                   (x, y))

    def _draw_compose(self, w, h):
        s = self.screen
        x = int(w * 0.06)
        y = int(h * 0.44)
        s.blit(self.font_small.render("COMPOSE", True, config.COLOR_DIM_RED), (x, y))
        y += self.font_small.get_linesize() + 6

        labels = {
            "q": "QUESTION",
            "o0": "OPTION 1",
            "o1": "OPTION 2",
            "o2": "OPTION 3 (OPTIONAL)",
            "o3": "OPTION 4 (OPTIONAL)",
        }
        opts = self._options()
        for idx, fkey in enumerate(FIELD_ORDER):
            focused = (idx == self.focus)
            prefix = "> " if focused else "  "
            if fkey in labels:
                val = self.fields[fkey]
                if focused and self.editing:
                    val += "_"
                text = "%s%-20s %s" % (prefix, labels[fkey], val)
                color = config.COLOR_WHITE if focused else COLOR_DIM
            elif fkey == "correct":
                c = self.fields["correct"]
                name = opts[c] if c < len(opts) else "-"
                text = "%s%-20s [%d] %s" % (prefix, "CORRECT ANSWER", c + 1, name)
                color = COLOR_ACCENT if focused else COLOR_DIM
            elif fkey == "send":
                text = "%sSEND" % prefix
                color = COLOR_GOOD if focused else COLOR_DIM
            else:
                text = "%sQUIT" % prefix
                color = COLOR_BAD if focused else COLOR_DIM

            surf = self.font_med.render(text, True, color)
            s.blit(surf, (x, y))
            rect = pygame.Rect(x - 6, y - 2, int(w * 0.88), surf.get_height() + 4)
            self.field_rects.append((rect, idx))
            y += self.font_med.get_linesize() + 4

        to = (self.recipient or {}).get("name", "EVERYONE")
        s.blit(self.font_small.render("SENDING TO: " + str(to).upper(), True, COLOR_ACCENT),
               (x, h - self.font_small.get_linesize() * 2 - 8))
        s.blit(self.font_small.render(
            "[TAB] FIELD  [ENTER] EDIT/ACT  [ESC] QUIT   —   OR CLICK ANYTHING",
            True, COLOR_DIMMER), (x, h - self.font_small.get_linesize() - 6))

        # Verdicts from players who answered.
        if self.results:
            rx = int(w * 0.56)
            ry = int(h * 0.235)
            self.screen.blit(self.font_small.render("REPLIES", True, config.COLOR_DIM_RED),
                             (rx, ry))
            ry += self.font_small.get_linesize() + 4
            for res in self.results[:5]:
                who = str(res.get("by") or "?").upper()
                verdict = res.get("correct")
                if verdict is True:
                    vtext, vcol = "RIGHT", COLOR_GOOD
                elif verdict is False:
                    vtext, vcol = "WRONG", COLOR_BAD
                else:
                    vtext, vcol = "ANSWERED", COLOR_DIM
                self.screen.blit(self.font_small.render(
                    "%s: %s" % (who, vtext), True, vcol), (rx, ry))
                ry += self.font_small.get_linesize() + 2

    def _draw_toast(self, w, h):
        if not self.toast:
            return
        tone = self.toast.get("tone", "info")
        color = {"good": COLOR_GOOD, "bad": COLOR_BAD}.get(tone, COLOR_ACCENT)
        surf = self.font_med.render(self.toast["text"], True, color)
        self.screen.blit(surf, (int(w * 0.06), int(h * 0.19)))

    # --- run ----------------------------------------------------------------
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
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
    if not _token():
        print("[!] TQG_SEND_TOKEN is not set — this app cannot write questions.")
        print("    Set it to the relay's RELAY_SEND_TOKEN and run again:")
        print("    TQG_SEND_TOKEN=... python tools/sender/sender.py")
        # Still start, in read-only mode, so the room can be inspected.
    app = Sender()
    app.run()


if __name__ == "__main__":
    main()
