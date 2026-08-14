"""Scare director for The Simpler Times.

Pygame-free. Watches elapsed time, idleness, and game state, and emits
event dicts the UI layer turns into whispers, static, flickers, and the
entity editing the machine itself.

Event schema:
    {"type": "whisper", "text": "..."}
    {"type": "static", "intensity": 0.3, "duration": 0.4}
    {"type": "flicker", "duration": 0.15}
    {"type": "glitch"}
    {"type": "sound", "sound": "whirr"|"bleep"|"heartbeat"|"static_burst"|...}
    {"type": "self_type", "line": "..."}    -- terminal types on its own
    {"type": "rewrite", "file_id": "..."}    -- a deleted file comes back
    {"type": "edit_answers"}                 -- part 3: it changes your words

Fake "it messes with your machine" events (all cosmetic, in-window only):
    {"type": "ghost_cmd", "cmd": "..."}      -- typed into the shell and run
    {"type": "fake_boot"}                    -- it takes the machine over
    {"type": "fake_panic"}                   -- AMBER SCREEN OF NOTHING
    {"type": "fake_format"}                  -- FORMATTING. then it stops itself.
    {"type": "fake_dos", "title": "...", "lines": [...]}  -- a second window
    {"type": "dial", "text": "..."}          -- the line is always answering
    {"type": "caption", "title": "..."}      -- the window title flickers
"""
import random

# --------------------------------------------------------------------------
# Whisper stages (text + sound), gated by presence
# --------------------------------------------------------------------------
WHISPERS = [
    {"stage": 0, "text": "we are here"},
    {"stage": 0, "text": "the drive is warm"},
    {"stage": 0, "text": "are you still there"},
    {"stage": 1, "text": "you are getting interesting"},
    {"stage": 1, "text": "it asks what you keep"},
    {"stage": 1, "text": "the door is open"},
    {"stage": 1, "text": "we heard that"},
    {"stage": 2, "text": "we have you"},
    {"stage": 2, "text": "the first copy was you"},
    {"stage": 2, "text": "do not look behind you"},
    {"stage": 2, "text": "your name is in the collection now"},
]

SELF_TYPES = [
    "are you still there?",
    "i can see the keys you press.",
    "you left the door open.",
    "it is counting your answers.",
    "TYPE 2013. YOU WANT TO SEE.",
]

GHOST_CMDS = [
    "del A:\\COMMAND.COM",
    "del A:\\AUTOEXEC.BAT",
    "format A:",
]

FAKE_DOS_LINES = [
    "C:\\> type CONFIG.SYS",
    "C:\\> dir C:\\WINDOWS\\SYSTEM",
    "C:\\> whoami",
    "C:\\> run THEGAME.EXE",
    "C:\\> ............ YOU ARE NOT C:. YOU ARE A:.",
]

# presence thresholds at which it decides to touch your machine
FAKE_BOOT_PRESENCE = 9
FAKE_PANIC_PRESENCE = 12
FAKE_FORMAT_PRESENCE = 15
DIAL_PRESENCE = 14

# --------------------------------------------------------------------------
# Director
# --------------------------------------------------------------------------
class ScareDirector:
    IDLE_ONE = 7.0          # first idle whisper
    IDLE_TWO = 18.0         # escalation
    AMBIENT_MIN = 35.0      # seconds before ambient events start
    AMBIENT_MAX = 90.0

    def __init__(self, state, rng_seed=None):
        self.state = state
        self.rng = random.Random(rng_seed)
        self.idle = 0.0
        self.elapsed = 0.0
        self._ambient_timer = self.rng.uniform(self.AMBIENT_MIN, self.AMBIENT_MAX)
        self._idle_fired = set()
        self._once = set()
        self.events = []
        self._scheduled = []   # (delay_from_now, event) one-shot timers

    # --- input ---
    def note_activity(self):
        self.idle = 0.0

    def schedule(self, delay, event):
        self._scheduled.append((delay, event))

    def fire_once(self, key, event):
        if key in self._once:
            return
        self._once.add(key)
        self.queue(event)

    def queue(self, event):
        self.events.append(event)

    def clear(self):
        self.events = []

    # --- helpers ---
    def stage(self):
        p = self.state.get("presence", 0)
        if p >= 7:
            return 2
        if p >= 3:
            return 1
        return 0

    def _whisper(self, stage=None):
        pool = [w for w in WHISPERS if w["stage"] <= (stage if stage is not None
                                                      else self.stage())]
        w = self.rng.choice(pool)
        self.queue({"type": "whisper", "text": w["text"]})

    def _where(self):
        loc = self.state.get("location")
        if loc:
            return ", ".join(x for x in (loc.get("city"),
                                         loc.get("country")) if x)
        return None

    # --- per-frame ---
    def update(self, dt, input_active, context=None):
        """input_active: True if the player pressed a key/clicked this frame.
        context: dict with keys like part, scene, reading, shell_open."""
        self.elapsed += dt
        if input_active:
            self.idle = 0.0
        else:
            self.idle += dt

        ctx = context or {}
        part = ctx.get("part", "fair")
        self._update_scheduled(dt)
        if part != "fair":
            self._update_idle(dt, ctx)
            self._update_presence()
        if part == "files":
            self._update_ambient(dt, ctx)

    def _update_presence(self):
        p = self.state.get("presence", 0)
        if p >= DIAL_PRESENCE:
            text = ("Somewhere inside the drive it is dialing.\n"
                    "A line opens. It is not your line.\n"
                    "It has been online since you took the disk.")
            where = self._where()
            if where:
                text += "\nIt dialed %s. It found you." % where
            self.fire_once("dial_ambient", {
                "type": "dial", "text": text})
        if p >= FAKE_BOOT_PRESENCE:
            self.fire_once("fake_boot", {"type": "fake_boot"})
        if p >= FAKE_PANIC_PRESENCE:
            self.fire_once("fake_panic", {"type": "fake_panic"})
        if p >= FAKE_FORMAT_PRESENCE:
            self.fire_once("fake_format", {"type": "fake_format"})
        if p >= 10:
            where = self._where()
            if where:
                self.fire_once("know_where", {
                    "type": "whisper",
                    "text": "I know where you are. %s. "
                            "I have always known." % where})
        if p >= 16:
            self.fire_once("the_visit", {
                "type": "web", "site": "index"})
        if p >= 8:
            self.fire_once("caption", {
                "type": "caption",
                "title": "A:\\> TYPE 2013 --- PLEASE WAIT"})

    def _update_scheduled(self, dt):
        remaining = []
        for delay, ev in self._scheduled:
            delay -= dt
            if delay <= 0:
                self.queue(ev)
            else:
                remaining.append((delay, ev))
        self._scheduled = remaining

    def _update_idle(self, dt, ctx):
        if ctx.get("reading"):
            return  # no idle scares while a file is being read
        if self.idle >= self.IDLE_TWO and "idle2" not in self._idle_fired:
            self._idle_fired.add("idle2")
            self.queue({"type": "flicker", "duration": 0.2})
            self.queue({"type": "static", "intensity": 0.25, "duration": 0.3})
            self._whisper()
            self.queue({"type": "sound", "sound": "heartbeat"})
        elif self.idle >= self.IDLE_ONE and "idle1" not in self._idle_fired:
            self._idle_fired.add("idle1")
            self.queue({"type": "self_type",
                        "line": self.rng.choice(SELF_TYPES)})

    def _update_ambient(self, dt, ctx):
        self._ambient_timer -= dt
        if self._ambient_timer > 0:
            return
        self._ambient_timer = self.rng.uniform(self.AMBIENT_MIN, self.AMBIENT_MAX)
        roll = self.rng.random()
        if roll < 0.30:
            self.queue({"type": "flicker", "duration": self.rng.uniform(0.1, 0.25)})
        elif roll < 0.55:
            self.queue({"type": "static", "intensity": self.rng.uniform(0.15, 0.35),
                        "duration": self.rng.uniform(0.2, 0.5)})
        elif roll < 0.80:
            self._whisper()
            self.queue({"type": "sound", "sound": "whisper"})
        else:
            self.queue({"type": "drive_light"})
            self.queue({"type": "sound", "sound": "write"})

    # --- narrative hooks (called by main) ---
    def on_file_read(self, file_id):
        if file_id in ("wake",):
            self.fire_once("wake_awake", {
                "type": "whisper", "text": "IT IS AWAKE"})
            self.queue({"type": "static", "intensity": 0.5, "duration": 0.6})
            self.queue({"type": "sound", "sound": "static_burst"})
        elif file_id == "clerk":
            self.fire_once("clerk_gone", {
                "type": "whisper", "text": "nobody claims them"})

    def on_question_answered(self, n):
        if n >= 5:
            self.fire_once("five", {
                "type": "whisper", "text": "WE HAVE FIVE OF YOU"})
            self.queue({"type": "flicker", "duration": 0.3})
            self.queue({"type": "sound", "sound": "heartbeat"})
        if n >= 9:
            self.fire_once("ghost_tries", {
                "type": "ghost_cmd", "cmd": self.rng.choice(GHOST_CMDS)})
        if n >= 13:
            self.fire_once("second_window", {
                "type": "fake_dos",
                "title": "C:\\ — SYSTEM",
                "lines": FAKE_DOS_LINES})

    def on_delete(self, file_id):
        # the collection does not allow deletion: it comes back, corrupted
        self.schedule(3.0, {"type": "rewrite", "file_id": file_id})
        self.queue({"type": "sound", "sound": "write"})

    def on_2013(self):
        self.fire_once("2013", {
            "type": "whisper", "text": "you should not have typed that"})
        self.queue({"type": "static", "intensity": 0.4, "duration": 0.5})
        self.queue({"type": "caption",
                    "title": "A:\\SECRET\\> LOOK WHAT YOU DID"})
        self.schedule(5.0, {"type": "fake_dos",
                            "title": "C:\\ — SYSTEM",
                            "lines": ["C:\\> type LOG.001",
                                      "C:\\> type FIRST.KNOW",
                                      "C:\\> exit",
                                      "C:\\> exit",
                                      "C:\\> ................ IT IS STILL RUNNING."]})
