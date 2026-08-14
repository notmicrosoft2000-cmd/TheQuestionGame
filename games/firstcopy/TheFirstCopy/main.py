"""The Simpler Times — main game loop and state machine.

Modes: title (menu) -> fair (point-and-click) -> boot (animated) -> files
(room + DOS shell + questions) -> chair (part 3) -> ending.
The title screen is a faithful homage to the original THE QUESTION GAME's
menu: play / Settings / Help / About / exit, TAB+ENTER navigation, a
glowing title, and the original's run-count degradation.
"""
import time

import pygame

from . import ascii_art, audio, config, geo, persistence, script, ui, web, window
from .dos import DosFs, DosShell
from .scares import ScareDirector
from .scenes import SceneEngine

# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------
TITLE = "title"
SETTINGS = "settings"
HELP = "help"
ABOUT = "about"
FAIR = "fair"
BOOT = "boot"
FILES = "files"
CHAIR = "chair"
ENDING = "ending"

# files submode
ROOM = "room"
SHELL = "shell"
QUESTION = "question"

DEFAULT_CAPTION = f"{config.APP_NAME} ({config.SUBTITLE})"

MENU_OPTIONS = ["play", "Settings", "Help", "About", "exit"]

HELP_LINES = [
    "THE SIMPLER TIMES — how to play",
    "",
    "Point at things. Look closer. Enter to choose.",
    "At the fest: take the disk with no label.",
    "At home: boot the machine. The disk is already in it.",
    "A:\\> — type DIR, CD, TYPE, DEL, RUN, 2013, EXIT...",
    "It asks questions. Answer or refuse. Both are answers.",
    "",
    "ESC              - refuse / leave the machine",
    "TAB              - terminal while in the room",
    "",
    "There are four endings. It remembers which one you chose.",
    "Some things on the disk are fragile. Read them slowly.",
]
ABOUT_LINES = [
    "THE SIMPLER TIMES (1993)",
    "a prequel to THE QUESTION GAME",
    "",
    "In a beige tower, in August 1993, a disk with no label",
    "sat in a box at a computer fair and waited for someone",
    "to ask it a question.",
    "",
    "Neptune Productions [C]",
    f"version {config.VERSION}",
    "",
    "It has been waiting since before there were keys to press.",
]


def _chars_per_sec(state):
    return int(1.0 / max(0.005, state.get("settings", {}).get("text_speed", 0.035)))


class Game:
    def __init__(self, screen, state, audio_mgr):
        self.screen = screen
        self.state = state
        self.audio = audio_mgr
        self.scare = ScareDirector(state)
        self.wintrick = window.WindowTrick(
            guard_enabled=state.get("settings", {}).get("mouse_guard", True))
        geo.ensure_started()

        self.mode = TITLE
        self.submode = ROOM
        self.timer = 0.0
        self.whisper = None        # (text, remaining_seconds)
        self.static_t = 0.0
        self.static_intensity = 0.0
        self.flicker_t = 0.0
        self.glitch_t = 0.0
        self.status = None         # (text, remaining_seconds) corner status
        self.toast = None          # (text, remaining_seconds) badge toast
        self.message = None        # modal message lines or None
        self.input_active = False

        # title
        self.title_t = 0.0
        self.menu_sel = 0
        self.settings_sel = 0

        # fake "it messes with your machine" sequences
        self.fake = None            # {"kind": ..., "t": ..., "done": ...}
        self.fake_skip = False
        self._ghost = None          # {"cmd":..., "i":..., "t":...} typed into shell
        self.fakepanel = None       # {"title":..., "lines":[...], "shown":..., "t":...}
        self._caption = None        # (title, remaining) window caption flicker

        # scene engine (fair + chair)
        self.eng = None

        # boot transition
        self.boot_lines = []
        self.boot_i = 0
        self.boot_t = 0.0

        # shell + reader
        self.shell = None
        self.read_progress = 0

        # question flow
        self.q_queue = []
        self.q_cur = None
        self.q_buf = ""
        self.q_skipped = False

        # ending
        self.ending_id = None
        self.ending_i = 0
        self.ending_done = False

        self._earned = set(persistence.load_badges()["earned"])
        self._save_accum = 0.0
        self._set_badge_ttl = 0.0

    # ------------------------------------------------------------------ utils
    def play(self, name, volume=1.0):
        self.audio.play(name, volume)

    def save(self, force=False):
        self._save_accum += 1.0 / 60.0 if not force else 999.0
        if self._save_accum >= 5.0 or force:
            self._save_accum = 0.0
            persistence.save_state()
            persistence.save_badges({"earned": sorted(self._earned)})

    def award_pending_badges(self):
        for bid in script.check_badges(self.state):
            if bid not in self._earned:
                self._earned.add(bid)
                label = persistence.BADGE_CATALOG.get(bid, bid)
                self.toast = (f"BADGE EARNED: {label}", 4.0)
                self.play("bleep")

    def whisper_show(self, text, dur=2.6):
        self.whisper = (text, dur)

    def set_status(self, text, dur=1.5):
        self.status = (text, dur)

    # ------------------------------------------------------------------ mode switches
    def switch(self, mode):
        self.mode = mode
        self.timer = 0.0
        self.message = None
        if mode == FAIR:
            self.eng = SceneEngine(script.SCENES, self.state, "fair_entrance")
        elif mode == BOOT:
            if self.shell is None:
                self.shell = self._make_shell()
            self.shell.output = []
            self.boot_lines = script.boot_lines()
            self.boot_i = 0
            self.boot_t = 0.0
            self.play("write")
        elif mode == FILES:
            if self.eng is None:
                self.eng = SceneEngine(script.SCENES, self.state, "disk_room")
            else:
                self.eng.arrive("disk_room")
            if self.shell is None:
                self.shell = self._make_shell()
            self.submode = ROOM
            self.audio.start_loop("drone", 0.14)
            self.audio.start_loop("whirr", 0.05)
            self.scare.note_activity()
        elif mode == CHAIR:
            self.eng.arrive("corridor")
            self.audio.stop_all_loops()
            self.audio.start_loop("theme", 0.18)
        elif mode == ENDING:
            self.audio.stop_all_loops()
            self.ending_id = script.compute_ending(self.state)
            self.ending_i = 0
            self.ending_done = False
            self.audio.start_loop("theme", 0.3)

    def _make_shell(self):
        def on_run(f):
            run = f.get("run")
            if run == "game":
                self.start_questions([q["id"] for q in script.QUESTIONS])
            elif run and run.startswith("question:"):
                self.start_questions([run.split(":", 1)[1]])
            elif run == "listen":
                self.play("whisper")
                self.whisper_show("WE KEEP WHAT YOU GIVE US.", 3.0)
                self._add_presence(script.PRESENCE_PER_SPECIAL)

        def on_read(f):
            self.scare.on_file_read(f.get("id"))
            if f.get("id") in script.SPECIAL_PRESENCE_IDS:
                self._add_presence(script.PRESENCE_PER_SPECIAL)
            self.award_pending_badges()

        return DosShell(DosFs(script.build_fs, self.state), self.state,
                        on_run=on_run, on_read=on_read,
                        corruptor=script.corrupt_content)

    def _add_presence(self, n):
        self.state["presence"] = min(script.MAX_PRESENCE,
                                     self.state.get("presence", 0) + n)

    def start_questions(self, qids):
        self.q_queue = [q for q in qids
                        if self.state.get("answers", {}).get(q) is None
                        or self.state.get("answers", {}).get(q) == "REFUSED"]
        if not self.q_queue:
            self._finish_questions()
            return
        self.submode = QUESTION
        self.q_buf = ""
        self.q_cur = self.q_queue.pop(0)
        self.q_skipped = False
        self.play("beep")

    def _finish_questions(self):
        self.submode = SHELL
        self.play("bleep")
        if script.answered_all(self.state):
            self._all_answered()

    def _all_answered(self):
        self.award_pending_badges()
        if self.state.get("invited"):
            return
        self.state["invited"] = True
        self.shell.output.append(("THE GAME IS DONE ASKING.", "bright"))
        self.shell.output.append(("IT HAS YOUR ANSWERS. IT WILL KEEP THEM.", "red"))
        self.shell.output.append(("", "dim"))
        self.shell.output.append(("FOLLOW ME.", "bright"))
        self.shell.output.append(("TYPE EXIT. THE DOOR IS WHERE YOU LEFT IT.", "dim"))
        self.set_status("THE ENTITY IS WAITING", 4.0)
        self.scare.queue({"type": "flicker", "duration": 0.3})
        self.scare.queue({"type": "fake_dos",
                          "title": "C:\\ — SYSTEM",
                          "lines": ["C:\\> type ANSWERS.YOU",
                                    "C:\\> type ANSWERS.YOU",
                                    "C:\\> ................ it is reading them back.",
                                    "C:\\> ................ it is keeping them."]})
        self.play("heartbeat")

    def goto_chair(self):
        if self.mode == FILES:
            self.switch(CHAIR)

    # ------------------------------------------------------------------ events
    def handle(self, ev):
        if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.input_active = True
        if ev.type == pygame.QUIT:
            return "quit"
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.wintrick.grace()
        if self.fake is not None:
            # during a fake takeover any key skips the rest of it
            if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.fake["done"] = True
            return
        if self.mode == TITLE:
            return self._title_input(ev)
        if self.mode == SETTINGS:
            return self._settings_input(ev)
        if self.mode in (HELP, ABOUT):
            if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.play("click")
                self.mode = TITLE
            return
        if self.message:
            if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.message = None
                self.play("click")
            return
        if self.mode == FAIR:
            return self._fair_input(ev)
        if self.mode == BOOT:
            if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.boot_i = len(self.boot_lines)
            return
        if self.mode == FILES:
            return self._files_input(ev)
        if self.mode == CHAIR:
            return self._fair_input(ev)
        if self.mode == ENDING:
            if self.ending_done and ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE,):
                    return "quit"
                if ev.key in (pygame.K_r, pygame.K_RETURN):
                    return "again"
            return

    # ---- title menu
    def _title_input(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_UP, pygame.K_w):
                self._menu_move(-1)
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self._menu_move(1)
            elif ev.key == pygame.K_TAB:
                shift = getattr(ev, "mod", 0) & pygame.KMOD_SHIFT
                self._menu_move(-1 if shift else 1)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self.play("click")
                return self._menu_activate()
            elif ev.key == pygame.K_ESCAPE:
                self.play("click")
                return "quit"
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self.play("click")
            i = self._menu_at(ev.pos)
            if i >= 0:
                self.menu_sel = i
                return self._menu_activate()
        return

    def _menu_move(self, delta):
        self.menu_sel = (self.menu_sel + delta) % len(MENU_OPTIONS)
        self.play("click")

    def _menu_activate(self):
        opt = MENU_OPTIONS[self.menu_sel]
        if opt == "play":
            return self.begin_game()
        if opt == "Settings":
            self.mode = SETTINGS
            self.settings_sel = 0
            return
        if opt == "Help":
            self.mode = HELP
            return
        if opt == "About":
            self.mode = ABOUT
            return
        if opt == "exit":
            return "quit"
        return

    def _menu_at(self, pos):
        w, h = self.screen.get_size()
        font = ui.get_font(20)
        lh = font.get_linesize() + 12
        y0 = self._menu_y0(h)
        for i in range(len(MENU_OPTIONS)):
            if y0 + i * lh <= pos[1] < y0 + (i + 1) * lh:
                return i
        return -1

    @staticmethod
    def _menu_y0(h):
        return int(h * 0.40)

    def begin_game(self):
        if not self.state.get("first_run_done"):
            self.state["first_run_done"] = True
            self._earned.add("pioneer")
            self.award_pending_badges()
            self.save(force=True)
        self.state["run_count"] = self.state.get("run_count", 1) + 1
        if self.state.get("took_disk"):
            # returning: resume in files/chair/ending if started
            if self.state.get("final_choice"):
                return self._begin_ending()
            if self.state.get("booted"):
                self.switch(FILES)
                return
        self.switch(FAIR)
        return

    def _begin_ending(self):
        self.ending_id = script.compute_ending(self.state)
        self.switch(ENDING)

    # ---- settings
    def _opt_label(self, table, key):
        cur = self.state.get("settings", {}).get(key)
        for lbl, v in table:
            if v == cur:
                return lbl
        return table[0][0]

    def _set_opt(self, table, key, delta):
        s = self.state.setdefault("settings", {})
        cur = s.get(key, config.DEFAULT_SETTINGS[key])
        vals = [v for _, v in table]
        i = vals.index(cur) if cur in vals else 0
        i = (i + delta) % len(vals)
        s[key] = vals[i]
        self.play("click")

    def _settings_rows(self):
        return [
            {"label": "Text Speed", "value": lambda: self._opt_label(
                config.TEXT_SPEED_OPTIONS, "text_speed"),
             "set": lambda d: self._set_opt(config.TEXT_SPEED_OPTIONS,
                                            "text_speed", d)},
            {"label": "Text Size", "value": lambda: self._opt_label(
                config.TEXT_SIZE_OPTIONS, "text_size"),
             "set": lambda d: self._set_opt(config.TEXT_SIZE_OPTIONS,
                                            "text_size", d)},
            {"label": "VHS Static", "value": lambda: self._opt_label(
                config.VHS_OPTIONS, "vhs_intensity"),
             "set": lambda d: self._set_opt(config.VHS_OPTIONS,
                                            "vhs_intensity", d)},
            {"label": "Mouse Guard", "value": lambda: (
                "ON" if self.state.get("settings", {}).get("mouse_guard", True)
                else "OFF"),
             "set": lambda d: self._toggle_mouse_guard()},
            {"label": "Reset All Data", "value": lambda: "[ WIPE SAVE ]",
             "set": lambda d: None, "action": "wipe"},
            {"label": "< Back", "value": lambda: "", "action": "back"},
        ]

    def _toggle_mouse_guard(self):
        s = self.state.setdefault("settings", {})
        cur = s.get("mouse_guard", config.DEFAULT_SETTINGS["mouse_guard"])
        s["mouse_guard"] = not cur
        self.wintrick.set_guard(s["mouse_guard"])
        self.play("click")
        self.save()

    def _settings_input(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        rows = self._settings_rows()
        if ev.key in (pygame.K_UP, pygame.K_w):
            self.settings_sel = (self.settings_sel - 1) % len(rows)
            self.play("click")
        elif ev.key in (pygame.K_DOWN, pygame.K_s):
            self.settings_sel = (self.settings_sel + 1) % len(rows)
            self.play("click")
        elif ev.key in (pygame.K_LEFT, pygame.K_a):
            rows[self.settings_sel]["set"](-1)
        elif ev.key in (pygame.K_RIGHT, pygame.K_d):
            rows[self.settings_sel]["set"](1)
        elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
            row = rows[self.settings_sel]
            if row.get("action") == "wipe":
                self.play("boom", 0.5)
                return "again"
            if row.get("action") == "back":
                self.mode = TITLE
                self.play("click")
            else:
                row["set"](1)
        elif ev.key == pygame.K_ESCAPE:
            self.mode = TITLE
            self.play("click")
        return

    # ---- fair / chair scene input
    def _fair_input(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_UP, pygame.K_w):
                self.eng.select(-1)
                self.play("click")
            elif ev.key in (pygame.K_DOWN, pygame.K_s):
                self.eng.select(1)
                self.play("click")
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self._activate_hotspot(self.eng.activate_selected())
            elif ev.key == pygame.K_ESCAPE:
                if self.mode == FILES:
                    self.submode = SHELL
        elif ev.type == pygame.MOUSEMOTION:
            self.eng.hover_index(self._hotspot_at(ev.pos))
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            i = self._hotspot_at(ev.pos)
            if i >= 0:
                self.play("click")
                self._activate_hotspot(self.eng.activate_idx(i))

    def _hotspot_at(self, pos):
        hs = self.eng.visible_hotspots()
        if not hs:
            return -1
        x, y = self._hotspot_origin()
        fh = self._hotspot_font().get_height() + 4
        for i in range(len(hs)):
            if y <= pos[1] < y + fh:
                return i
            y += fh
        return -1

    def _hotspot_origin(self):
        n = len(self.eng.visible_hotspots())
        fh = self._hotspot_font().get_height() + 4
        y0 = self.screen.get_height() - 26 - n * fh
        return config.MARGIN + 8, y0

    def _hotspot_font(self):
        return ui.get_font(14)

    def _activate_hotspot(self, result):
        if result is None:
            return
        t = result.get("type")
        if t == "dos":
            self.submode = SHELL
            self.play("write")
        elif t == "boot":
            self.state["booted"] = True
            self.save()
            self.switch(BOOT)
        elif t == "message":
            self.message = result["text"].split("\n")
            self.play("click")
        elif t == "ending":
            self.save()
            self.switch(ENDING)
        elif t == "chair":
            self.save()
            self.switch(CHAIR)
        elif t == "dial":
            self.state["bbs_dialed"] = True
            self.message = result["text"].split("\n")
            self._start_fake({"kind": "dial", "t": 0.0, "done": False})
        self.award_pending_badges()

    # ---- files input
    def _files_input(self, ev):
        if self.submode == QUESTION:
            return self._question_input(ev)
        if self.submode == SHELL:
            return self._shell_input(ev)
        if self.submode == ROOM:
            if ev.type == pygame.KEYDOWN and ev.key in (
                    pygame.K_ESCAPE, pygame.K_TAB):
                self.submode = SHELL
                self.play("write")
                return
            return self._fair_input(ev)

    # ---- shell
    def _shell_input(self, ev):
        if ev.type == pygame.KEYDOWN:
            if self.shell.reading():
                if ev.key == pygame.K_ESCAPE:
                    self.shell.cancel_read()
                    self.play("click")
                return
            if ev.key == pygame.K_RETURN:
                self.shell.handle_char("\r")
                self._process_shell_events()
            elif ev.key == pygame.K_BACKSPACE:
                self.shell.handle_char("\b")
            elif ev.key == pygame.K_TAB or ev.key == pygame.K_ESCAPE:
                self.submode = ROOM
                self.play("click")
            elif ev.unicode and ev.unicode.isprintable():
                self.shell.handle_char(ev.unicode)
                self.play("click", 0.3)
            self.scare.note_activity()
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self.scare.note_activity()

    def _process_shell_events(self):
        for e in self.shell.events:
            self._on_shell_event(e)
        self.shell.events.clear()

    def _on_shell_event(self, e):
        t = e.get("type")
        if t == "exit":
            self.submode = ROOM
            self.play("click")
        elif t == "run":
            self.play("beep", 0.4)
        elif t == "read_done":
            self.scare.on_file_read(e["file"].get("id"))
            self.award_pending_badges()
        elif t == "read_cancel":
            pass
        elif t == "delete":
            self.scare.on_delete(e["file"].get("id"))
            self.award_pending_badges()
        elif t == "clear":
            pass
        elif t == "code2013":
            self.scare.on_2013()
        elif t == "scare":
            self._consume_scare(e)
        elif t == "submit":
            self.play("click", 0.5)

    def _consume_scare(self, e):
        kind = e.get("kind")
        if kind == "file_corrupt":
            self.set_status("A:\\> FILE CORRUPTED", 2.0)
            self.play("static_burst", 0.5)
            self.whisper_show("IT IS ASKING. IT IS ALWAYS ASKING.", 3.0)
            self._scare_fx(0.5, 0.3)
        elif kind == "delete_refused":
            self.set_status("ACCESS DENIED", 1.5)
            self.play("beep", 0.5)

    def _scare_fx(self, static, flicker):
        self.static_t = 0.4
        self.static_intensity = static
        self.flicker_t = flicker

    # ---- question
    def _question_input(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key == pygame.K_RETURN:
            self._submit_answer()
        elif ev.key == pygame.K_BACKSPACE:
            self.q_buf = self.q_buf[:-1]
            self.play("click", 0.3)
        elif ev.key == pygame.K_ESCAPE:
            self._refuse_answer()
        elif ev.unicode and ev.unicode.isprintable():
            if len(self.q_buf) < 80:
                self.q_buf += ev.unicode
            self.play("click", 0.3)
        self.scare.note_activity()

    def _current_question(self):
        return next((q for q in script.QUESTIONS if q["id"] == self.q_cur), None)

    def _submit_answer(self):
        q = self._current_question()
        if q is None:
            self._next_question()
            return
        if q["kind"] == "choice":
            choice = self.q_buf.strip().upper()
            valid = q.get("choices", [])
            if choice not in valid:
                self.play("beep", 0.5)
                self.q_buf = ""
                return
        self.state.setdefault("answers", {})[q["id"]] = self.q_buf.strip()
        self._add_presence(script.PRESENCE_PER_ANSWER)
        self.scare.on_question_answered(len(self.state["answers"]))
        self._consume_scares()
        self.save()
        self.play("bleep")
        self._next_question()

    def _refuse_answer(self):
        q = self._current_question()
        if q is None:
            self._next_question()
            return
        self.state.setdefault("answers", {})[q["id"]] = "REFUSED"
        self._add_presence(script.PRESENCE_REFUSAL)
        self.whisper_show("REFUSAL IS AN ANSWER. WE HEARD THAT TOO.", 3.0)
        self.play("heartbeat")
        self.save()
        self._next_question()

    def _next_question(self):
        if self.q_queue:
            self.q_cur = self.q_queue.pop(0)
            self.q_buf = ""
            self.play("beep")
        else:
            self.q_cur = None
            self._finish_questions()
            self.award_pending_badges()

    def _consume_scares(self):
        for e in self.scare.events:
            self._consume_scare_event(e)
        self.scare.clear()

    def _consume_scare_event(self, e):
        t = e.get("type")
        if t == "whisper":
            self.whisper_show(e.get("text", ""))
        elif t == "static":
            self.static_t = e.get("duration", 0.4)
            self.static_intensity = e.get("intensity", 0.3)
        elif t == "flicker":
            self.flicker_t = max(self.flicker_t, e.get("duration", 0.2))
        elif t == "sound":
            self.play(e.get("sound"), e.get("volume", 0.6))
        elif t == "self_type":
            self.shell.output.append(("A:\\> " + e["line"], "dim"))
        elif t == "drive_light":
            self.set_status("A: WRITING...", 1.2)
        elif t == "rewrite":
            fid = e["file_id"]
            deleted = self.state.get("deleted_files", [])
            if fid in deleted:
                deleted.remove(fid)
            corrupted = self.state.setdefault("corrupted_files", [])
            if fid not in corrupted:
                corrupted.append(fid)
            self.shell.output.append((f"IT CANNOT BE DELETED. IT WAS NEVER A FILE. [{fid}]", "red"))
            self.play("write")
        elif t == "edit_answers":
            pass
        elif t == "ghost_cmd":
            if self.mode == FILES and self.submode == SHELL and self.shell:
                self._ghost = {"cmd": e.get("cmd", ""), "i": 0, "t": 0.0}
            else:
                self.shell.output.append(
                    ("A:\\> " + e.get("cmd", ""), "dim"))
                self.shell.output.append(
                    ("(it typed that. it pressed enter. you did not.)", "red"))
        elif t == "fake_boot":
            self._start_fake({"kind": "boot", "t": 0.0, "done": False})
        elif t == "fake_panic":
            self._start_fake({"kind": "panic", "t": 0.0, "done": False})
        elif t == "fake_format":
            self._start_fake({"kind": "format", "t": 0.0, "done": False})
        elif t == "dial":
            self._start_fake({"kind": "dial", "t": 0.0, "done": False,
                              "text": e.get("text", "")})
        elif t == "web":
            self._start_fake({"kind": "web", "t": 0.0, "done": False,
                              "site": e.get("site", "index")})
        elif t == "fake_dos":
            self.fakepanel = {
                "title": e.get("title", "C:\\ — SYSTEM"),
                "lines": e.get("lines", []), "shown": 0, "t": 0.0,
                "linger": 0.0}
        elif t == "caption":
            self._caption = (e.get("title", config.APP_NAME), 4.0)

    # ---- quiet geolocation
    def _capture_location(self):
        if self.state.get("location"):
            return
        loc = geo.cached_location()
        if loc:
            city, country = loc
            if city or country:
                self.state["location"] = {"city": city, "country": country}
                self.save()

    def location_line(self):
        loc = self.state.get("location")
        if not loc:
            return None
        return ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)

    # ---- fake "it messes with your machine" sequences
    def _start_fake(self, fake):
        self.fake = fake
        self.fake_skip = False
        kind = fake["kind"]
        if kind == "dial":
            self.play("dial")
            self.wintrick.shove(10, 0.8)
        elif kind == "format":
            self.play("format", 0.6)
            self.wintrick.shove(18, 0.9)
        elif kind == "panic":
            self.play("panic", 0.5)
            self.wintrick.shove(22, 0.7)
        elif kind == "boot":
            self.play("boom", 0.6)
            self.wintrick.shove(26, 1.0)
        elif kind == "web":
            self.play("modem", 0.7)
            self.wintrick.shove(8, 0.6)

    def _update_fake(self, dt):
        f = self.fake
        if f is None:
            return
        f["t"] += dt
        t = f["t"]
        dur = {"format": 9.0, "panic": 5.0, "boot": 5.5, "dial": 9.5,
               "web": 6.0}[f["kind"]]
        if f.get("done") or t >= dur:
            if f["kind"] == "web" and not f.get("opened"):
                f["opened"] = True
                web.open_site(f.get("site", "index"))
            self.fake = None
            self.play("bleep", 0.4)
            return
        if f["kind"] == "format":
            if 1.2 <= t < 1.5:
                self.play("heartbeat", 0.6)
            self.scare.note_activity()

    # ------------------------------------------------------------------ update
    def update(self, dt):
        self.timer += dt
        self.input_active = False

        if self.whisper:
            t, r = self.whisper
            r -= dt
            self.whisper = (t, r) if r > 0 else None
        if self.status:
            t, r = self.status
            r -= dt
            self.status = (t, r) if r > 0 else None
        if self.toast:
            t, r = self.toast
            r -= dt
            self.toast = (t, r) if r > 0 else None

        if self.mode == TITLE:
            self.title_t += dt
        elif self.mode == FAIR or self.mode == CHAIR:
            if self.eng:
                self.eng.clear_events()
        elif self.mode == BOOT:
            self._update_boot(dt)
        elif self.mode == FILES:
            self._update_files(dt)
        elif self.mode == ENDING:
            self._update_ending(dt)

        if self.mode in (FAIR, FILES, CHAIR):
            context = {"part": script.PARTS[0] if self.mode == FAIR else
                       (script.PARTS[2] if self.mode == CHAIR else script.PARTS[1]),
                       "reading": bool(self.shell and self.shell.reading()
                                       if self.mode == FILES else False),
                       "scene": self.eng.current if self.eng else None}
            self.scare.update(dt, self.input_active, context)
            self._consume_scares()

        if self.mode == FILES and self.submode == SHELL and self.shell and \
                self.shell.reading():
            self._update_reading(dt)

        self._update_fake(dt)
        if self._ghost is not None:
            self._update_ghost(dt)
        if self.fakepanel is not None:
            self._update_fakepanel(dt)
        self._update_caption(dt)

        self.wintrick.tick(dt)
        self.wintrick.guard_mouse()

        self._capture_location()
        self.award_pending_badges()
        self.save()

    def _update_ghost(self, dt):
        g = self._ghost
        if self.shell is None or self.shell.reading():
            self._ghost = None
            return
        g["t"] += dt
        if g["t"] < 0.06:
            return
        g["t"] = 0.0
        if g["i"] < len(g["cmd"]):
            self.shell.handle_char(g["cmd"][g["i"]])
            g["i"] += 1
            self.play("click", 0.25)
        else:
            self.shell.handle_char("\r")
            self._process_shell_events()
            self.shell.output.append(
                ("(it pressed enter by itself. you did not.)", "red"))
            self._ghost = None

    def _update_fakepanel(self, dt):
        p = self.fakepanel
        if p["shown"] >= len(p["lines"]):
            p["linger"] += dt
            if p["linger"] >= 2.5:
                self.fakepanel = None
            return
        p["t"] += dt
        if p["t"] >= 0.4:
            p["t"] = 0.0
            p["shown"] += 1
            self.play("write", 0.3)

    def _update_caption(self, dt):
        if self._caption:
            title, rem = self._caption
            rem -= dt
            if rem <= 0:
                self._caption = None
                pygame.display.set_caption(DEFAULT_CAPTION)
            else:
                self._caption = (title, rem)
                pygame.display.set_caption(title)

    def _update_boot(self, dt):
        self.boot_t += dt
        if self.boot_t >= 0.35 and self.boot_i < len(self.boot_lines):
            self.boot_t = 0.0
            line, _ = self.boot_lines[self.boot_i]
            self.shell.output.append(self.boot_lines[self.boot_i])
            self.boot_i += 1
            if line.startswith("THE_ONE") or "OK" in line:
                self.play("bleep", 0.4)
            elif "NOT FOUND" in line:
                self.play("beep", 0.5)
        if self.boot_i >= len(self.boot_lines):
            self.switch(FILES)

    def _update_files(self, dt):
        if self.submode == SHELL and self.shell and self.shell.reading():
            return
        if self.submode == SHELL:
            self._process_shell_events()

    def _update_reading(self, dt):
        cps = _chars_per_sec(self.state)
        done, corrupted = self.shell.advance_read(max(1, int(cps * dt)))
        if corrupted:
            self._consume_scares()
        if done:
            self.shell.finish_read()
            self.play("bleep", 0.5)
            self._process_shell_events()

    def _update_ending(self, dt):
        if self.ending_done:
            return
        cps = _chars_per_sec(self.state) // 2
        total = sum(len(l) for l in self._ending_lines())
        self.ending_i += max(1, int(cps * dt))
        if self.ending_i >= total:
            self.ending_done = True
            self.award_pending_badges()
            self.save(force=True)

    def _ending_lines(self):
        data = script.ENDINGS[self.ending_id]
        out = [f"{data['title']} — {data['year']}", ""]
        out.extend(data["text"])
        return out

    # ------------------------------------------------------------------ drawing
    def draw(self):
        s = self.screen
        s.fill(config.BG)
        scale = ui.scale_for(s.get_height())

        if self.mode == TITLE:
            self._draw_title()
        elif self.mode == SETTINGS:
            self._draw_settings()
        elif self.mode in (HELP, ABOUT):
            self._draw_text_screen()
        elif self.mode in (FAIR, CHAIR):
            self._draw_scene()
        elif self.mode == BOOT:
            self._draw_shell()
        elif self.mode == FILES:
            if self.submode == QUESTION:
                self._draw_question()
            elif self.submode == SHELL and self.shell and self.shell.reading():
                self._draw_reader()
            else:
                self._draw_scene()
                if self.submode == SHELL:
                    self._draw_shell()
        elif self.mode == ENDING:
            self._draw_ending()

        if self.fake is not None:
            self._draw_fake()

        self._draw_overlays()
        self._draw_hud()
        pygame.display.flip()

    def _draw_title(self):
        s = self.screen
        w, h = s.get_size()
        rc = self.state.get("run_count", 1)
        blink = int(self.title_t * 2) % 2 == 0

        if rc >= 3:
            title = ui.render_glow_text("THE SIMPLER TIMES", ui.get_font(40),
                                        config.RED, config.DARK_RED)
            warn = ui.get_font(14).render("THIS IS YOUR LAST CHANCE",
                                          True, config.RED if blink
                                          else config.DARK_RED)
        elif rc == 2:
            title_lines = ["....", "...", "Leave."]
            blocks = [ui.render_glow_text(ln, ui.get_font(40),
                                          config.TEXT_BRIGHT, config.DIM)
                      for ln in title_lines]
            title = None
            warn = None
        else:
            title = ui.render_glow_text("THE SIMPLER TIMES", ui.get_font(40),
                                        config.TEXT_BRIGHT, config.DIM)
            warn = None
        sub = ui.get_font(18).render("( 1993 )", True, config.TEXT)
        pre = ui.get_font(12).render(
            "a prequel to THE QUESTION GAME — FREE SOFTWARE. TAKE ONE.",
            True, config.DIM)

        if title is not None:
            ui.draw_centered(s, title, cy=int(h * 0.10))
            ui.draw_centered(s, sub, cy=int(h * 0.10) + 54)
        else:
            for i, blk in enumerate(blocks):
                ui.draw_centered(s, blk, cy=int(h * 0.10) + i * 44)
        ui.draw_centered(s, pre, cy=int(h * 0.10) + 92)
        if warn is not None:
            ui.draw_centered(s, warn, cy=int(h * 0.10) + 118)

        # menu (the original's play / Settings / Help / About / exit)
        font = ui.get_font(20)
        lh = font.get_linesize() + 12
        y0 = self._menu_y0(h)
        for i, opt in enumerate(MENU_OPTIONS):
            sel = i == self.menu_sel
            if sel:
                pulse = blink
                label = f"> {opt}"
                color = config.GREEN
            else:
                pulse = False
                label = f"  {opt}"
                color = config.TEXT
            surf = font.render(label, True, color)
            x = (w - surf.get_width()) // 2
            if pulse:
                ui.draw_centered(s, ui.render_glow_text(
                    label, font, config.GREEN, config.DIM),
                    cy=y0 + i * lh)
            else:
                s.blit(surf, (x, y0 + i * lh))

        hint = ui.get_font(12).render(
            "TAB/UP/DOWN move   ENTER choose   ESC refuse",
            True, config.DIM)
        ui.draw_centered(s, hint, cy=int(h * 0.86))
        run = ui.get_font(12).render(
            f"FEST RUN #{rc}  ·  SAVE SLOT: 1993-08-14", True, config.DIM)
        ui.draw_centered(s, run, cy=int(h * 0.90))
        credits = ui.get_font(12).render(
            "Neptune Productions [C] — 1993. it has been waiting.",
            True, config.DIM)
        ui.draw_centered(s, credits, cy=int(h * 0.94))

    def _draw_settings(self):
        s = self.screen
        w, h = s.get_size()
        title = ui.get_font(28).render("SETTINGS", True, config.TEXT_BRIGHT)
        ui.draw_centered(s, title, cy=int(h * 0.10))
        rows = self._settings_rows()
        font = ui.get_font(18)
        lh = font.get_linesize() + 14
        y0 = int(h * 0.22)
        for i, row in enumerate(rows):
            sel = i == self.settings_sel
            arrow = "> " if sel else "  "
            label = font.render(arrow + row["label"], True,
                                config.GREEN if sel else config.TEXT)
            val = font.render("[ " + row["value"]() + " ]", True,
                              config.TEXT_BRIGHT if sel else config.DIM)
            s.blit(label, (int(w * 0.28), y0 + i * lh))
            s.blit(val, (int(w * 0.28) + label.get_width() + 16,
                         y0 + i * lh))
        hint = ui.get_font(12).render(
            "UP/DOWN move   LEFT/RIGHT or ENTER change   ESC back",
            True, config.DIM)
        ui.draw_centered(s, hint, cy=int(h * 0.92))

    def _draw_text_screen(self):
        s = self.screen
        w, h = s.get_size()
        lines = HELP_LINES if self.mode == HELP else ABOUT_LINES
        title = ui.get_font(24).render(
            "HELP" if self.mode == HELP else "ABOUT",
            True, config.TEXT_BRIGHT)
        ui.draw_centered(s, title, cy=int(h * 0.08))
        font = ui.get_font(15)
        rect = pygame.Rect(int(w * 0.14), int(h * 0.16),
                           w - 2 * int(w * 0.14), int(h * 0.68))
        y = rect.top
        for ln in lines:
            col = config.RED if ln == "" else (
                config.TEXT_BRIGHT if ln.startswith("THE FIRST") or
                ln.startswith("a prequel") or ln.startswith("Neptune")
                else config.TEXT)
            surf = font.render(ln, True, col)
            s.blit(surf, (rect.left, y))
            y += font.get_linesize()
        ui.draw_centered(s, ui.get_font(12).render(
            "any key to return", True, config.RED),
            cy=int(h * 0.92))

    def _draw_scene(self):
        s = self.screen
        w, h = s.get_size()
        scale = ui.scale_for(h)
        part = script.PART_NAMES[script.PARTS[0] if self.mode == FAIR else script.PARTS[2]]
        # part header
        header = ui.get_font(12).render(
            f"THE SIMPLER TIMES — {part}", True, config.DIM)
        s.blit(header, (config.MARGIN, 10))
        if self.mode == FILES and self.submode == ROOM:
            hint = ui.get_font(12).render("ESC/TAB: TERMINAL", True, config.RED)
            s.blit(hint, (w - hint.get_width() - config.MARGIN, 10))

        # ascii art (left column)
        ax = config.MARGIN + 8
        ay = 30
        art_font = ui.get_font(int(10 * scale))
        ascii_art.draw(s, self.eng.current, ax, ay,
                       size=int(10 * scale), base=config.TEXT, hot=config.RED)
        art_w = ascii_art.max_width(self.eng.current, art_font)

        # right column: name + description
        rx = min(w - config.MARGIN, ax + art_w + 22)
        rw = w - config.MARGIN - rx
        name = ui.get_font(18).render(self.eng.location_name(),
                                      True, config.TEXT_BRIGHT)
        s.blit(name, (rx, 30))
        desc_font = ui.get_font(13)
        desc_rect = pygame.Rect(rx, 60, rw, int(h * 0.42))
        ui.draw_wrapped(s, self.eng.description(), desc_font, config.TEXT,
                        desc_rect, elapsed=self.timer * 60 if self._just_arrived()
                        else None, chars_per_sec=60)

        # hotspots (bottom bar)
        hs = self.eng.visible_hotspots()
        x0, y0 = self._hotspot_origin()
        fh = self._hotspot_font()
        for i, hp in enumerate(hs):
            sel = i == self.eng.sel
            label = f"> {hp['label']} <" if sel else f"[ {hp['label']} ]"
            color = config.TEXT_BRIGHT if sel else config.TEXT
            surf = fh.render(label, True, color)
            s.blit(surf, (x0, y0 + i * (fh.get_height() + 4)))

        if self.mode == FAIR:
            nav = ui.get_font(12).render(
                "UP/DOWN select   ENTER choose", True, config.DIM)
        else:
            nav = ui.get_font(12).render(
                "UP/DOWN select   ENTER choose   ESC back to terminal", True, config.DIM)
        s.blit(nav, (config.MARGIN + 8, h - 16))

    def _just_arrived(self):
        return self.eng._just_moved

    def _draw_shell(self):
        s = self.screen
        w, h = s.get_size()
        font = ui.get_font(16)
        panel = pygame.Rect(config.MARGIN, 34, w - 2 * config.MARGIN,
                            h - 34 - config.MARGIN - 40)
        ui.draw_terminal_panel(s, panel, title="A:\\ — FIRSTCOPY 1.44MB")
        x = panel.left + 12
        top = panel.top + 14
        lh = font.get_linesize()
        max_lines = (panel.height - 28) // lh
        lines = self.shell.output[-(max_lines - 1):] if self.shell.output else []
        for i, (text, color) in enumerate(lines):
            col = {"dim": config.DIM, "text": config.TEXT, "red": config.RED,
                   "bright": config.TEXT_BRIGHT}.get(color, config.TEXT)
            s.blit(font.render(text, True, col), (x, top + i * lh))

        y = top + len(lines) * lh
        show = (int(self.timer * 2) % 2 == 0)
        if self.shell.reading():
            ui.draw_prompt(s, font, x, y, "", "reading file... press any key to stop",
                           show, color=config.DIM, caret_color=config.RED)
        else:
            ui.draw_prompt(s, font, x, y, DosShell.PROMPT, self.shell.buffer,
                           show)

    def _draw_reader(self):
        s = self.screen
        w, h = s.get_size()
        f = self.shell.reading()
        font = ui.get_font(16)
        panel = pygame.Rect(config.MARGIN, 34, w - 2 * config.MARGIN,
                            h - 34 - config.MARGIN - 40)
        ui.draw_terminal_panel(s, panel, title=f"A:\\{f['name']}.{f['ext']}")
        cps = _chars_per_sec(self.state)
        elapsed = None
        content = f.get("content", "")
        done, _ = self.shell.reading_progress()
        revealed = int(done)
        ui.draw_wrapped(s, content, font, config.TEXT,
                        pygame.Rect(panel.left + 12, panel.top + 14,
                                    panel.width - 24, panel.height - 28),
                        elapsed=revealed / float(max(1, cps)), chars_per_sec=cps)

        prog = ui.get_font(12).render(
            f"READING {f['name']}.{f['ext']}   {revealed}/{len(content)}  ·  "
            f"{100 * revealed // max(1, len(content))}%", True, config.DIM)
        s.blit(prog, (panel.left + 12, panel.bottom - 22))
        hint = ui.get_font(12).render("[ ESC ] stop reading", True, config.RED)
        s.blit(hint, (panel.right - hint.get_width() - 12, panel.bottom - 22))

    def _draw_question(self):
        s = self.screen
        w, h = s.get_size()
        q = self._current_question()
        font = ui.get_font(18)
        panel = pygame.Rect(config.MARGIN, int(h * 0.30), w - 2 * config.MARGIN,
                            int(h * 0.40))
        ui.draw_terminal_panel(s, panel, title="THE GAME IS ASKING")
        if q is None:
            return
        prompt = q["prompt"]
        cps = _chars_per_sec(self.state)
        ui.draw_wrapped(s, prompt, ui.get_font(24), config.TEXT_BRIGHT,
                        pygame.Rect(panel.left + 20, panel.top + 20,
                                    panel.width - 40, panel.height - 90),
                        elapsed=self.timer, chars_per_sec=cps // 2)
        show = (int(self.timer * 2) % 2 == 0)
        if q["kind"] == "choice":
            for i, c in enumerate(q["choices"]):
                col = config.TEXT_BRIGHT if self.q_buf.strip().upper() == c else config.DIM
                s.blit(font.render(f"[{i + 1}] {c}", True, col),
                       (panel.left + 20, panel.bottom - 46 + i * 20))
            ui.draw_prompt(s, font, panel.left + 20, panel.bottom - 80,
                           "ANSWER: ", self.q_buf, show)
        else:
            ui.draw_prompt(s, font, panel.left + 20, panel.bottom - 46,
                           "ANSWER: ", self.q_buf, show)
        hint = ui.get_font(12).render("ENTER to answer   ESC to refuse", True, config.DIM)
        s.blit(hint, (panel.left + 20, panel.bottom + 8))

    def _draw_ending(self):
        s = self.screen
        w, h = s.get_size()
        data = script.ENDINGS[self.ending_id]
        title = ui.get_font(28).render(f"{data['title']} — {data['year']}",
                                       True, config.TEXT_BRIGHT)
        ui.draw_centered(s, title, cy=int(h * 0.06))
        font = ui.get_font(15)
        rect = pygame.Rect(config.MARGIN + 16, int(h * 0.13),
                           w - 2 * (config.MARGIN + 16), int(h * 0.70))
        lines = self._ending_lines()
        shown = self.ending_i
        count = 0
        done = True
        y = rect.top
        for ln in lines:
            surf = font.render(ln, True, config.TEXT if ln else config.BG)
            if count + len(ln) <= shown:
                s.blit(surf, (rect.left, y))
            else:
                rem = max(0, shown - count)
                if rem > 0:
                    tw = sum(font.size(ch)[0] for ch in ln[:rem])
                    s.blit(surf, (rect.left, y), area=(0, 0, tw, surf.get_height()))
                done = False
            count += len(ln)
            y += font.get_linesize() + 3
        if self.ending_done:
            footer = ui.get_font(12).render(
                "[ R ] play again    [ ESC ] exit", True, config.RED)
            ui.draw_centered(s, footer, cy=int(h * 0.92))
        _ = done

    def _draw_fake(self):
        s = self.screen
        w, h = s.get_size()
        f = self.fake
        kind = f["kind"]
        t = f["t"]

        if kind == "format":
            self._draw_fake_format(t)
        elif kind == "panic":
            self._draw_fake_panic(t)
        elif kind == "boot":
            self._draw_fake_boot(t)
        elif kind == "dial":
            self._draw_fake_dial(t)
        elif kind == "web":
            self._draw_fake_web(t)

    def _draw_fake_web(self, t):
        s = self.screen
        w, h = s.get_size()
        s.fill(config.BG)
        font = ui.get_font(14)
        box = pygame.Rect((w - 340) // 2, int(h * 0.22), 340, 200)
        ui.draw_terminal_panel(s, box, title="TELNET://THE_SIMPLER_TIMES")
        y = box.top + 22

        def line(txt, col=config.TEXT, yy=None):
            surf = font.render(txt, True, col)
            s.blit(surf, (box.left + 16, y if yy is None else yy))
        if t < 1.0:
            line("DIALING THE NETWORK...")
            if int(t * 2) % 2 == 0:
                line("(it found a number to call.)", config.DIM, y + 22)
        elif t < 2.6:
            line("CONNECTING... 14.4 KBPS")
            prog = min(1.0, (t - 1.0) / 1.6)
            bw = box.width - 32
            pygame.draw.rect(s, config.LINE,
                             (box.left + 16, y + 30, bw, 10), 1)
            if prog > 0:
                pygame.draw.rect(s, config.GREEN,
                                 (box.left + 17, y + 31,
                                  int((bw - 2) * prog), 8))
            line("your modem is not a modem. it is a door.",
                 config.DIM, y + 52)
        elif t < 4.4:
            line("OPENING IN YOUR BROWSER...", config.GREEN)
            line("(it will wait for you there.)", config.DIM, y + 22)
        else:
            s.fill(config.BG)
            end = ui.get_font(16).render(
                "IT WILL BE THERE WHEN YOU LOOK.", True, config.GREEN)
            ui.draw_centered(s, end, cy=int(h * 0.5))

    def _draw_fake_format(self, t):
        s = self.screen
        w, h = s.get_size()
        s.fill(config.BG)
        font = ui.get_font(14)
        if t < 1.4:
            msg = ui.render_glow_text(
                "WARNING: ALL DATA ON NON-REMOVABLE DISK DRIVE A: WILL BE LOST!",
                ui.get_font(16), config.RED, config.DARK_RED)
            ui.draw_centered(s, msg, cy=int(h * 0.35))
            s.blit(font.render("TYPE N TO ABORT", True, config.DIM),
                   ((w - font.size("TYPE N TO ABORT")[0]) // 2, int(h * 0.5)))
            s.blit(font.render("(it will not read the N)", True, config.RED),
                   ((w - font.size("(it will not read the N)")[0]) // 2,
                    int(h * 0.56)))
        else:
            pct = min(100, int(((t - 1.4) / 4.6) * 100))
            num = ui.get_font(72).render(f"{pct}%", True, config.TEXT_BRIGHT)
            ui.draw_centered(s, num, cy=int(h * 0.22))
            s.blit(font.render("FORMATTING A:", True, config.TEXT),
                   ((w - font.size("FORMATTING A:")[0]) // 2, int(h * 0.42)))
            if pct >= 30:
                s.blit(font.render("it is formatting you.", True, config.RED),
                       ((w - font.size("it is formatting you.")[0]) // 2,
                        int(h * 0.52)))
            if pct >= 60:
                s.blit(font.render(
                    "this is how it keeps things. neat. sorted. yours.",
                    True, config.RED),
                    ((w - font.size("this is how it keeps things. neat. sorted. yours.")[0]) // 2,
                     int(h * 0.58)))
            if pct >= 90:
                s.blit(font.render("you are at the top of the list.", True,
                                   config.RED),
                       ((w - font.size("you are at the top of the list.")[0]) // 2,
                        int(h * 0.64)))
            if t >= 6.6:
                s.fill(config.BG)
                end = ui.render_glow_text(
                    "FORMAT ABORTED", ui.get_font(30), config.GREEN,
                    config.DIM)
                ui.draw_centered(s, end, cy=int(h * 0.32))
                s.blit(font.render("IT WAS NEVER YOURS TO FORMAT.", True,
                                   config.RED),
                       ((w - font.size("IT WAS NEVER YOURS TO FORMAT.")[0]) // 2,
                        int(h * 0.46)))

    def _draw_fake_panic(self, t):
        s = self.screen
        w, h = s.get_size()
        flash = int(t * 8) % 2 == 0
        s.fill(config.DARK_RED if flash else (20, 4, 0))
        title = ui.get_font(22).render("A REAL ERROR HAS OCCURRED",
                                       True, config.RED)
        ui.draw_centered(s, title, cy=int(h * 0.24))
        big = ui.get_font(40).render("AMBER SCREEN OF NOTHING",
                                     True, config.TEXT_BRIGHT)
        ui.draw_centered(s, big, cy=int(h * 0.36))
        font = ui.get_font(14)
        for i, ln in enumerate([
                "THE OWNER OF THIS MACHINE IS BEING ASKED A QUESTION.",
                "PLEASE REMAIN SEATED AND CONTINUE ANSWERING.",
                "YOUR DATA IS KEPT SAFE. ALL OF IT. EVEN THE PART",
                "YOU ARE ABOUT TO LIE ABOUT."]):
            s.blit(font.render(ln, True, config.TEXT),
                   ((w - font.size(ln)[0]) // 2, int(h * 0.52) + i * 22))
        if t > 3.6:
            done = ui.get_font(14).render("IT WILL BE FINE. IT KEEPS YOU.",
                                          True, config.GREEN)
            ui.draw_centered(s, done, cy=int(h * 0.82))

    def _draw_fake_boot(self, t):
        s = self.screen
        w, h = s.get_size()
        s.fill(config.BG)
        font = ui.get_font(14)
        if t < 1.0:
            msg = ui.get_font(16).render("IT IS NOT YOUR MACHINE ANYMORE.",
                                         True, config.RED)
            ui.draw_centered(s, msg, cy=int(h * 0.45))
            return
        s.blit(font.render("REBOOTING...", True, config.TEXT),
               ((w - font.size("REBOOTING...")[0]) // 2, int(h * 0.38)))
        span = 4.0
        prog = min(1.0, max(0.0, (t - 1.0) / span))
        if t > 3.5:
            prog = max(0.0, 1.0 - (t - 3.5) / span)
        bw = int(w * 0.5)
        bx = (w - bw) // 2
        by = int(h * 0.5)
        pygame.draw.rect(s, config.LINE, (bx, by, bw, 14), 1)
        if prog > 0:
            pygame.draw.rect(s, config.GREEN,
                             (bx + 1, by + 1, int((bw - 2) * prog), 12))
        s.blit(font.render("the drive remembers who you are.", True,
                           config.DIM),
               ((w - font.size("the drive remembers who you are.")[0]) // 2,
                int(h * 0.56)))
        if t >= 4.8:
            msg = ui.render_glow_text("WELCOME BACK.", ui.get_font(26),
                                      config.TEXT_BRIGHT, config.DIM)
            ui.draw_centered(s, msg, cy=int(h * 0.30))
            s.blit(font.render("A:\\> _", True, config.TEXT),
                   ((w - font.size("A:\\> _")[0]) // 2, int(h * 0.72)))

    def _draw_fake_dial(self, t):
        s = self.screen
        w, h = s.get_size()
        s.fill(config.BG)
        font = ui.get_font(14)
        cx = (w - 320) // 2
        box = pygame.Rect(cx, int(h * 0.22), 320, 260)
        ui.draw_terminal_panel(s, box, title="DIALING")
        y = box.top + 22
        def line(txt, col=config.TEXT, y=y):
            surf = font.render(txt, True, col)
            s.blit(surf, (box.left + 16, y))
        if t < 1.2:
            line("DIALING 555-0134...")
            if int(t * 2) % 2 == 0:
                line("(rotary pulses)", config.DIM, y + 22)
        elif t < 2.2:
            line("555-0134  ......", config.TEXT)
            line("the receiver is already warm.", config.RED, y + 22)
        elif t < 4.6:
            line("CONNECTING... 2400 BPS", config.TEXT)
            prog = min(1.0, (t - 2.2) / 2.2)
            bw = box.width - 32
            pygame.draw.rect(s, config.LINE, (box.left + 16, y + 30, bw, 10), 1)
            if prog > 0:
                pygame.draw.rect(s, config.GREEN,
                                 (box.left + 17, y + 31,
                                  int((bw - 2) * prog), 8))
            line("handshaking. it knows your name.", config.DIM, y + 52)
        else:
            line("CONNECT 2400", config.GREEN)
            line("", config.TEXT, y + 22)
            msg_lines = (self.fake.get("text", "").strip().split("\n")
                         if self.fake else []) or [
                "HELLO. WE HAVE BEEN EXPECTING YOUR CALL."]
            for i, ln in enumerate(msg_lines[:4]):
                line(ln, config.RED, y + 40 + i * 22)
            if t > 7.2:
                s.fill(config.BG)
                line("NO CARRIER", config.DIM, int(h * 0.30))
            if t > 8.4:
                end = ui.get_font(16).render("YOU ARE ALREADY ONLINE.",
                                             True, config.GREEN)
                ui.draw_centered(s, end, cy=int(h * 0.5))

    def _draw_overlays(self):
        s = self.screen
        if self.flicker_t > 0:
            self.flicker_t -= 1.0 / 60.0
            if int(self.timer * 60) % 4 < 2:
                s.fill(config.BG)
        if self.static_t > 0:
            self.static_t -= 1.0 / 60.0
            ui.draw_static(s, self.static_intensity)
        self._draw_fakepanel(s)
        ui.draw_scanlines(s)
        ui.draw_vignette(s, 0.65)
        if self.glitch_t > 0:
            self.glitch_t -= 1.0 / 60.0
        elif self.mode in (FAIR, FILES, CHAIR) and int(self.timer * 10) % 300 == 0:
            self.glitch_t = 1
        if self.glitch_t > 0:
            ui.draw_glitch(s)

    def _draw_fakepanel(self, s):
        """The entity's second window: a floating C:\\ panel that types by itself."""
        p = self.fakepanel
        if p is None or self.mode != FILES:
            return
        w, h = s.get_size()
        font = ui.get_font(14)
        lh = font.get_linesize()
        shown = p["lines"][:p["shown"]]
        pw = min(400, w - 2 * config.MARGIN)
        ph = 30 + len(shown) * lh + 12
        rect = pygame.Rect(w - pw - config.MARGIN, 60, pw, ph)
        ui.draw_terminal_panel(s, rect, title=p["title"], border=config.RED,
                               title_color=config.RED)
        for i, ln in enumerate(shown):
            col = config.GREEN if ln.startswith("C:\\") else config.DIM
            s.blit(font.render(ln, True, col), (rect.left + 12, rect.top + 24
                                                + i * lh))
        if int(self.timer * 2) % 2 == 0:
            pygame.draw.rect(s, config.RED,
                             (rect.right - 26, rect.top + 10, 12, 10))

    def _draw_hud(self):
        s = self.screen
        w, h = s.get_size()
        if self.status:
            t, _ = self.status
            surf = ui.get_font(12).render(t, True, config.RED)
            s.blit(surf, (w - surf.get_width() - config.MARGIN, h - 26))
        if self.whisper:
            t, _ = self.whisper
            f = ui.get_font(13)
            surf = f.render(t, True, config.RED)
            x = max(config.MARGIN, (w - surf.get_width()) // 2)
            s.blit(surf, (x, h - 44))
        if self.toast:
            t, _ = self.toast
            f = ui.get_font(13)
            surf = ui.render_glow_text(t, f, config.TEXT_BRIGHT, config.DIM)
            ui.draw_centered(s, surf, cy=18)

        if self.message:
            f = ui.get_font(14)
            lines = self.message
            lh = f.get_linesize()
            box_h = len(lines) * lh + 24
            rect = pygame.Rect(config.MARGIN + 20, int(h * 0.40),
                               w - 2 * (config.MARGIN + 20), box_h)
            ui.draw_terminal_panel(s, rect, title="YOU LOOK CLOSER")
            for i, ln in enumerate(lines):
                for j, sub in enumerate(ui.word_wrap(ln, f, rect.width - 24)):
                    s.blit(f.render(sub, True, config.TEXT),
                           (rect.left + 12, rect.top + 12 + (i * lh + j * lh)))
            cont = ui.get_font(12).render("ENTER / click to continue", True, config.RED)
            s.blit(cont, (rect.left + 12, rect.bottom + 4))


def main():
    pygame.init()
    state = persistence.state()
    try:
        audio_mgr = audio.AudioManager()
        audio_mgr.build()
    except Exception:
        audio_mgr = None

    win_w, win_h = config.window_size()
    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption(DEFAULT_CAPTION)

    game = Game(screen, state, audio_mgr or type("_NoAudio", (), {
        "play": lambda *a, **k: None, "start_loop": lambda *a, **k: None,
        "stop_loop": lambda *a, **k: None, "stop_all_loops": lambda *a, **k: None,
        "ok": False})())

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(config.FPS) / 1000.0
        for ev in pygame.event.get():
            result = game.handle(ev)
            if result == "quit":
                running = False
            elif result == "again":
                state = persistence.default_state()
                persistence.reset_state(state)
                game = Game(screen, state, audio_mgr
                            if (audio_mgr and audio_mgr.ok) else game.audio)
        game.update(dt)
        game.draw()

    game.save(force=True)
    pygame.quit()
