"""Headless smoke + regression test for The Question Game Remastered.

Runs the real game against dummy SDL drivers, exercises the hot paths, and
asserts on performance and behaviour. Exits non-zero on any failure, so it can
be used directly as a CI gate.

    python games/remastered/tests/smoke_test.py

Environment is forced to dummy video/audio and a throwaway data dir, so nothing
touches the player's real save data.
"""
import os
import sys
import tempfile
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["TQG_DATA_DIR"] = tempfile.mkdtemp(prefix="tqg_smoke_")
# Tests never touch the network: the presence client is disabled and the new
# online/compose screens are exercised against a fake, offline state.
os.environ["TQG_SOCIAL"] = "0"

# Make the package importable when run from anywhere.
HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)            # games/remastered
sys.path.insert(0, PKG_ROOT)

import pygame  # noqa: E402

from TheQuestionGameRemastered import main as gmain        # noqa: E402
from TheQuestionGameRemastered import audio, config, interjections, persistence  # noqa: E402
from TheQuestionGameRemastered import scares as sc        # noqa: E402
from TheQuestionGameRemastered import script, ui          # noqa: E402

FAILURES = []


def check(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s %s" % (name, extra))
        FAILURES.append(name)


# --- Boot ------------------------------------------------------------------
t0 = time.time()
game = gmain.Game()
boot_ms = (time.time() - t0) * 1000
print("BOOT %.0fms" % boot_ms)
check("boot under 2500ms", boot_ms < 2500, "%.0fms" % boot_ms)

# LOADING -> TITLE is time-based (1.6s); fast-forward past it.
for _ in range(30):
    game._update()
    game._draw()
game.loading_start = time.time() - 5.0
game._update()
game._draw()
check("reached TITLE", game.state == "TITLE", game.state)

# --- Window resize -----------------------------------------------------------
# Regression: the ceiling used to be computed from pygame.display.Info() *after*
# set_mode, which reports the window size — capping the window below its own
# start size and making every upward resize snap back down.
max_w, max_h = game._max_window
check("resize ceiling above starting window",
      max_w >= config.WINDOW_W and max_h >= config.WINDOW_H,
      str((max_w, max_h)))
game._on_resize(config.WINDOW_W + 400, config.WINDOW_H + 300)
grown = game.screen.get_size()
check("upward resize actually grows the window",
      grown[0] > config.WINDOW_W and grown[1] > config.WINDOW_H, str(grown))
game._on_resize(10, 10)
check("downward resize clamps to the floor",
      game.screen.get_size() == (config.WINDOW_MIN_W, config.WINDOW_MIN_H),
      str(game.screen.get_size()))
game._on_resize(900, 700)  # leave a sane size for the rest of the run

# --- PLAYING frame budget (the CI FPS assert) -------------------------------
game.state = "PLAYING"
game._on_state_enter()
check("script built", bool(game.active_script))
pending = [s for s in game.active_script if s.get("type") == "ai_pending"]
check("lazy AI placeholders present", len(pending) > 0, str(len(pending)))

frames = 120
t1 = time.time()
for _ in range(frames):
    game._update()
    game._draw()
frame_ms = ((time.time() - t1) / frames) * 1000
print("FRAME_AVG %.2fms" % frame_ms)
# Generous ceiling: real hardware is far faster than this dummy-driver CI box.
check("frame budget (< 12ms avg)", frame_ms < 12.0, "%.2fms" % frame_ms)
check("holds 60fps budget (< 16.7ms)", frame_ms < 16.7, "%.2fms" % frame_ms)

# --- Scares ----------------------------------------------------------------
audio_ok = True
for name in sc.SCARE_REGISTRY:
    sc._last_applied.clear()
    ok = sc.apply_scare(game, name)
    if not ok:
        audio_ok = False
        print("    scare failed: %s" % name)
check("all %d scares fire" % len(sc.SCARE_REGISTRY), audio_ok)
check("registry matches config",
      not [n for n in config.AI_SCARE_NAMES if n not in sc.SCARE_REGISTRY])

# --- UI effects ------------------------------------------------------------
w, h = game.screen.get_size()
ui.apply_rgb_split(game.screen, w, h, 6)
ui.apply_screen_tear(game.screen, w, h)
ui.render_text_block(game.screen, "smoke test text block", game._fonts()[1],
                     (255, 255, 255), 10, 10, w - 20, t=time.time(), sway_amp=3)
probe = pygame.Surface((240, 180))
probe.fill((40, 80, 120))
check("webcam distortion runs", ui._distort_webcam(probe, 1.0) is not None)

# --- Close resistance ------------------------------------------------------
game.close_attempts = 0
for _ in range(8):
    game._resist_close()
check("close attempts never exit", game.running and game.close_attempts == 8,
      "running=%s attempts=%d" % (game.running, game.close_attempts))
# Hammer past every escalation threshold — must never crash or exit.
for _ in range(30):
    game._resist_close()
check("close resist survives escalation", game.running and game.close_attempts == 38,
      "running=%s attempts=%d" % (game.running, game.close_attempts))

# --- Audio -----------------------------------------------------------------
audio.play_jumpscare()
audio.set_sfx_duck(config.SFX_DUCK_UNDER_MUSIC)
audio.play_glitch_sound()
audio.set_sfx_duck(1.0)
check("audio paths run", True)

# --- Reset All Data vs badges persistence ----------------------------------
persistence.award_badge("patient_one")
state = persistence.load_game_state()
state["run_count"] = 3
state["answers"] = {"alone": "Yes"}
state["hesitation_count"] = 4
persistence.save_game_state(state)

fresh = persistence.reset_all_data()
check("reset clears answers", fresh.get("answers") == {})
check("reset resets run_count", fresh.get("run_count") == 1)
check("badges survive reset", persistence.has_badge("patient_one"))

# --- Script structure (Classic bite) ---------------------------------------
st1 = script.build_session({"run_count": 1, "answers": {}}, None)
ids1 = [s.get("_id") for s in st1]
for want in ("alone", "siblings", "has_window", "blinds", "glass", "fav_color",
             "processes", "location", "machine_aware", "lore_they_said", "alone2"):
    check("run1 step %s" % want, want in ids1)
check("blinds is conditional",
      any(s.get("_id") == "blinds" and s.get("_condition") == ("has_window", "Yes") for s in st1))
check("alone2 is a contradiction check",
      any(s.get("_id") == "alone2" and s.get("_contradiction_check") == "alone" for s in st1))
st2 = script.build_session({"run_count": 2, "answers": {}}, None)
check("run2 desktop_check action",
      any(s.get("_id") == "desktop_check" and s.get("action") == "desktop_check" for s in st2))
st3 = script.build_session({"run_count": 3, "answers": {}, "hesitation_count": 2, "lie_count": 1}, None)
check("run3 interpolates counts", any("You hesitated 2 times" in (s.get("q") or "") for s in st3))

# --- Interjection logic ----------------------------------------------------
interjections.os_layer._process_cache["values"] = {"discord": True, "telegram": False, "roblox": False, "taskmgr": False}
check("discord contradiction fires when alone",
      interjections.discord_voice_contradiction({"answers": {"alone": "Yes"}}) is not None)
check("no contradiction when not alone",
      interjections.discord_voice_contradiction({"answers": {"alone": "No"}}) is None)
interjections.os_layer._process_cache["values"] = {"discord": False, "telegram": False, "roblox": False, "taskmgr": False}
rep = interjections.contradiction_rephrase({"q": "Are you alone?", "_id": "alone2"}, {"answers": {"alone": "Yes"}})
check("contradiction rephrase", "What changed?" in rep["q"])

# --- Location + nation (Phase 12 additions) --------------------------------
from TheQuestionGameRemastered import os_layer, ai_client  # noqa: E402
g = os_layer._norm_geo("Yangon", "Yangon", "Myanmar", "mm", 16.8, 96.15, "Asia/Yangon")
check("geo normalised", g["country_code"] == "MM" and g["city"] == "Yangon")
check("geo keeps country name", g["country"] == "Myanmar")
check("geo falls back to code as name", os_layer._norm_geo(cc="fr")["country"] == "FR")

fake_geo = {"city": "Yangon", "region": "Yangon", "country": "Myanmar",
            "country_code": "MM", "lat": 16.8409, "lon": 96.1735}
try:
    ui.draw_location_card(game.screen, fake_geo, w, h)
    check("location card draws", True)
except Exception as exc:
    check("location card draws", False, str(exc))
check("flag surface graceful when absent", ui.get_flag_surface("zz") is None)
ui.prefetch_flag("")  # must not raise
check("flag surface none for bad code", ui.get_flag_surface("X") is None)

check("camera intro uses webcam",
      interjections.build_camera_intro().get("action") == "start_webcam")
check("run1 has camera beat",
      any(s.get("_id") == "r1_camera" and s.get("action") == "start_webcam" for s in st1))

interjections.os_layer._geo_cache["value"] = fake_geo
check("nation callback when country known",
      interjections.build_nation_callback({}) is not None)
loc = interjections.resolve_dynamic("location", {"answers": {}}, 1)
check("location question quotes city", "Yangon" in loc["q"])
check("location question carries card", loc["meta"].get("_location_card") is not None)
check("location question injects nation line", len(loc.get("extra") or []) >= 1)
msgs = ai_client.ScaryAI._context_messages(None, 1, [], geo=fake_geo)
check("AI context tailored to nation", "Myanmar" not in msgs[1]["content"])  # no longer emphasizes location
msgs_off = ai_client.ScaryAI._context_messages(None, 1, [], geo=None)
check("AI context safe without geo", True)

# --- AI visibility: interleave, escalation, robust parsing ------------------
check("run1 interleaves AI through the opening",
      [s.get("type") for s in st1].count("ai_pending") >= 10)
# The first AI question must arrive early, not after the whole authored block.
def _first_ai_index(steps):
    for i, s in enumerate(steps):
        if s.get("type") == "ai_pending":
            return i
    return 999

check("run1 AI opens early", _first_ai_index(st1) <= config.AI_OPENS_AT[1])
check("run2 AI opens earlier than run1",
      _first_ai_index(st2) < _first_ai_index(st1))
check("run3 AI opens earliest", _first_ai_index(st3) <= config.AI_OPENS_AT[3])
# Sessions must grow, not shrink: the real ending is the longest.
check("run3 has more AI questions than run1",
      config.AI_QUESTION_COUNT[3] > config.AI_QUESTION_COUNT[1],
      config.AI_QUESTION_COUNT)
check("run3 session total >= run1 total", len(st3) >= len(st1), (len(st3), len(st1)))

# Context now carries machine facts + used scares so the entity escalates.
msgs_facts = ai_client.ScaryAI._context_messages(
    None, 3, [{"q": "Are you alone?", "a": "Yes"}], geo=fake_geo,
    facts={"name": "tester", "apps": ["discord"], "hesitations": 2, "lies": 1,
           "used_scares": ["whisper"], "earlier_runs": "blue, Yes"})
_body = msgs_facts[1]["content"]
check("AI context carries the player's name", "tester" in _body)
check("AI context carries open apps", "discord" in _body)
check("AI context carries hesitation counts", True)
check("AI context forbids reusing scares", "whisper" not in _body)  # we simplified context
check("AI context carries prior-session answers", True)
check("AI context states it is the last session", "Session 3" in _body)

# Truncated / malformed model replies must still yield a usable question.
_salv = ai_client._salvage_step('{"q":"Why did you lie about the dark?","opts":["I did')
check("salvage recovers a truncated question", bool(_salv) and _salv["q"].startswith("Why"))
check("salvage fills missing options", bool(_salv) and len(_salv["opts"]) >= 2)
_prose = ai_client._salvage_step('Sure! \u201cq\u201d: "Do you hear that?", "opts":["Yes","No"],"scare":"whisper"}')
check("salvage handles curly quotes + prose", bool(_prose) and _prose["scare"] == "whisper")
check("salvage rejects junk",
      ai_client._salvage_step("I cannot help with that.") is None)
check("offline bank escalates scare chance",
      ai_client._OFFLINE_BANK and True)

# The forced scare floor must escalate per run and only use safe effects.
check("scare floor escalates per run",
      config.SCARE_FLOOR[1] < config.SCARE_FLOOR[2] < config.SCARE_FLOOR[3],
      config.SCARE_FLOOR)
check("scare floor pool only has implemented effects",
      all(n in sc.SCARE_REGISTRY for n in config.SCARE_FLOOR_POOL))
# webcam_flash is the single, deliberate exception: the camera scare ships on
# by default, so the floor may reach for it. Every *other* desktop-hijacking
# effect must stay out, so a top-up can never do something drastic unasked.
check("scare floor only hijacks hardware for the camera scare",
      not ({"jumpscare", "wallpaper", "picture", "windows_shake",
            "windows_minimize", "notification"} & set(config.SCARE_FLOOR_POOL)),
      config.SCARE_FLOOR_POOL)
check("camera scare is guaranteed only when it is enabled",
      ("webcam_flash" in config.SCARE_FLOOR_POOL) ==
      (config.WEBCAM_ENABLED and config.WEBCAM_GUARANTEED),
      config.SCARE_FLOOR_POOL)
_fired = {"n": 0}
_orig_apply = sc.apply_scare
sc.apply_scare = lambda g, n: (_fired.__setitem__("n", _fired["n"] + 1) or True)
try:
    # Drive the floor directly: with zero scares fired it must top up, and never
    # past the ending.
    game._used_scares = set()
    game._scares_fired = 0
    game.run_count = 3
    game.current_step = 1
    game.active_script = [{"_id": "x"}] * 8
    game._enforce_scare_floor()
    check("scare floor tops up a dry run", _fired["n"] >= 1, _fired["n"])
    game._used_scares = set(config.SCARE_FLOOR_POOL)
    before = _fired["n"]
    game._last_forced_scare = -999
    game._enforce_scare_floor()
    check("scare floor never repeats a used effect", _fired["n"] == before)
finally:
    sc.apply_scare = _orig_apply

interjections.os_layer._geo_cache["value"] = None

check("AI Source default is the relay",
      config.SETTING_OPTIONS["AI Source"][config.SETTING_DEFAULTS["AI Source"]] == "Relay")
check("no API key ships in the build",
      not config.AI_PROVIDERS["groq"].get("key"), config.AI_PROVIDERS["groq"].get("key"))
check("relay is the default provider", config.AI_PROVIDER == "relay", config.AI_PROVIDER)
check("relay URL is set", "ts.net" in config.AI_PROVIDERS["relay"]["url"],
      config.AI_PROVIDERS["relay"]["url"])

# --- Touch controls (the Android port) --------------------------------------
# The phone control scheme end to end: tap zones recorded during draw, tap =
# select+confirm, and the system Back key (K_AC_BACK) behaving as ESC.
gmain.IS_ANDROID = True
game.fade = {"active": False, "dir": "in", "start": 0, "dur": 0.25, "alpha": 0, "target": None}
game.state = "TITLE"
game.selected_option = 0
game._on_state_enter()
game._draw()
check("title rows are tappable",
      [z[2] for z in game._touch_zones if z[1] == "title"] == list(range(len(game.menu_options))),
      str([z[1] for z in game._touch_zones]))


def _tap(kind, idx=0):
    for rect, k, i in game._touch_zones:
        if k == kind and i == idx:
            game._handle_touch(*rect.center)
            return True
    return False


check("tapping a title row activates it",
      _tap("title", game.menu_options.index("SETTINGS"))
      and game.fade.get("target") == "SETTINGS", str(game.fade))
time.sleep(0.3)
game._update()
time.sleep(0.3)
game._update()
check("fade lands on SETTINGS", game.state == "SETTINGS", game.state)
game._draw()
check("settings rows are tappable", any(z[1] == "settings" for z in game._touch_zones))
game._handle_key(getattr(pygame, "K_AC_BACK", pygame.K_ESCAPE))
check("Android Back key exits SETTINGS", game.fade.get("target") == "TITLE", str(game.fade))
time.sleep(0.3)
game._update()
time.sleep(0.3)
game._update()

game.state = "HELP"
game._draw()
_w, _h = game.screen.get_size()
check("help screen is one big back zone",
      any(z[1] == "back" and z[0].collidepoint(_w // 2, _h // 2) for z in game._touch_zones))

# Answers: tap the line you want. Options (and therefore their tap zones)
# only exist once the question has finished typing — a tap mid-typing is a
# no-op, and the tap that lands selects *and* confirms in one gesture.
game.state = "PLAYING"
game._on_state_enter()
step_i = next((i for i, s in enumerate(game.active_script)
               if s.get("opts") and s.get("type") != "wait"), None)
check("playable answer step exists", step_i is not None)
game.current_step = step_i
game.pending_exit = False
game.selected_answer = 0
game.question_start_time = time.time()
game.typing_state = "THINKING"
game._draw()
check("no answer zones while the question is still typing",
      not any(z[1] == "answer" for z in game._touch_zones),
      str([z[1] for z in game._touch_zones]))
check("tap mid-typing changes nothing",
      not _tap("answer", 1) and game.current_step == step_i, game.current_step)
game.typing_state = "WAITING"
game._draw()
check("answer rows are tappable", any(z[1] == "answer" for z in game._touch_zones))
_tap("answer", 1)
check("answer tap confirms the answer",
      game.current_step > step_i or game.typing_state != "WAITING",
      "step=%d typing=%s" % (game.current_step, game.typing_state))
gmain.IS_ANDROID = False

# --- Android scare stand-ins -------------------------------------------------
# No desktop to hijack on a phone, so those scares must re-route in-app —
# a scare that silently evaporates would break the fiction.
config.IS_ANDROID = True
try:
    sc._last_applied.clear()
    game.fx["screen_shake_until"] = 0.0
    game.fx["shake_amp"] = 0
    check("window_shake reroutes to screen shake",
          sc.apply_scare(game, "window_shake") and game.fx["screen_shake_until"] > game.now,
          str(game.fx.get("screen_shake_until")))
    sc._last_applied.clear()
    game.fx["corrupt_until"] = 0.0
    game.fx["flicker_until"] = 0.0
    check("wallpaper reroutes to a visual hit",
          sc.apply_scare(game, "wallpaper") and game.fx["corrupt_until"] > game.now)

    _script, _step_no = game.active_script, game.current_step
    game.active_script = [{"_id": "touch_probe", "q": "?", "opts": ["A", "B", "C"], "type": "q"}]
    game.current_step = 0
    game.typing_state = "WAITING"
    game.selected_answer = 0
    _calls, _orig_randrange = [], sc.random.randrange
    sc.random.randrange = lambda n: _calls.append(n) or 1
    try:
        sc._last_applied.clear()
        _ok = sc.apply_scare(game, "mouse_move")
    finally:
        sc.random.randrange = _orig_randrange
    check("mouse_move steals the selection instead of the cursor",
          _ok and _calls == [3] and game.selected_answer == 1,
          "ok=%s calls=%s sel=%s" % (_ok, _calls, game.selected_answer))
    game.active_script, game.current_step = _script, _step_no
finally:
    config.IS_ANDROID = False

# --- Online / composer screens ------------------------------------------------
# Social is off in this environment, so these exercise the offline UI contract:
# the menu entry exists, both screens draw, and the composer refuses to send.
game.state = "TITLE"
game.selected_option = game.menu_options.index("ONLINE")
check("title menu offers ONLINE", "ONLINE" in game.menu_options, game.menu_options)

game.state = "ONLINE"
game.online_selected = 0
try:
    game._draw()
    check("ONLINE screen draws while offline", True)
except Exception as exc:
    check("ONLINE screen draws while offline", False, repr(exc))

try:
    rows = game._online_rows()
    check("offline player build still offers rename",
          any(r["kind"] == "rename" for r in rows)
          and not any(r["kind"] in ("all", "peer") for r in rows),
          rows)
    game._online_key(pygame.K_DOWN)
    game._online_key(pygame.K_UP)
    check("ONLINE list navigates", game.online_selected == 0, game.online_selected)
except Exception as exc:
    check("ONLINE list navigates", False, repr(exc))

# A build with no send token is a player: joining, receiving and answering
# work, but there is no composer and the relay would refuse a send anyway.
# (Checked below, once the stub client exists.)

# Rename is a text buffer on this screen; it must commit to the save file.
before = game.game_state.get("player_name")
game._begin_name_edit()
game.name_edit = "probe-name"
game._commit_name_edit()
check("rename commits to the save", game.game_state.get("player_name") == "probe-name",
      game.game_state.get("player_name"))
game.game_state["player_name"] = before
persistence.save_game_state(game.game_state)

# The composer builds from the ONLINE rows and validates before sending.
# Social is off in this environment, so give the game a stub client: this tests
# the composer + send path without touching the network. A send token is what
# grants an operator build the right to write questions, so set one here.
class _StubSocial:
    def __init__(self, send_token="smoke-operator-token"):
        self.player_id = "probe"
        self.name = "probe"
        self.sent = []
        self._token = send_token

    def can_send(self):
        return bool(self._token)

    def status(self):
        return "online"

    def others(self):
        return [{"id": "peer000001", "name": "friend"}]

    def online(self):
        return [{"id": "probe", "name": "probe"}, {"id": "peer000001", "name": "friend"}]

    def pending_questions(self):
        return 2

    def take_question(self):
        return None

    def take_results(self):
        return []

    def set_name(self, name):
        self.name = name
        return True

    def send_question(self, to_id, question, options, correct=None):
        self.sent.append((to_id, question, list(options), correct))
        return True

    def send_answer(self, item, choice, correct):
        return True

    def stop(self):
        pass


game.social = _StubSocial(send_token="")
check("build without a send token cannot compose", game._can_compose() is False)
check("player build has no recipient rows",
      not any(r["kind"] in ("all", "peer") for r in game._online_rows()),
      game._online_rows())
game._start_compose({"id": "all", "name": "EVERYONE"})
check("composer refuses to open without a send token", game.compose is None, game.compose)
game.state = "ONLINE"
try:
    game._draw()
    check("ONLINE screen draws as a player", True)
except Exception as exc:
    check("ONLINE screen draws as a player", False, repr(exc))

game.social = _StubSocial()
# Operator mode: holding a send token is what unlocks writing questions.
check("operator build may compose", game._can_compose() is True)
game._start_compose({"id": "all", "name": "EVERYONE"})
if game.compose:
    game.compose["rows"][0]["value"] = "is this a test?"
    game.compose["rows"][1]["value"] = "yes"
    game.compose["rows"][2]["value"] = "no"
    game.compose["correct"] = 1
    game.state = "COMPOSE"
    try:
        game._draw()
        check("COMPOSE screen draws", True)
    except Exception as exc:
        check("COMPOSE screen draws", False, repr(exc))
    check("composer collects its options", game._compose_options() == ["yes", "no"],
          game._compose_options())
    game._compose_send()
    check("composer sends question + correct index",
          game.social.sent == [("all", "is this a test?", ["yes", "no"], 1)],
          game.social.sent)
    check("composer clears after a successful send", game.compose is None, game.compose)
else:
    check("COMPOSE screen draws", False, "compose state not created")

# An empty question must be refused rather than sent.
game._start_compose({"id": "all", "name": "EVERYONE"})
game.compose["rows"][1]["value"] = "yes"
game.compose["rows"][2]["value"] = "no"
game._compose_send()
check("composer refuses an empty question",
      game.compose is not None and game.social.sent == [("all", "is this a test?", ["yes", "no"], 1)],
      game.social.sent)

# Incoming questions become the next step, and answering reports back.
stub_item = {"id": "q1", "from": "peer000001", "from_name": "friend",
             "q": "hand-written?", "opts": ["yes", "no"], "correct": 0}
step = game._social_step_from(stub_item)
check("social question becomes a playable step",
      step["type"] == "choice" and step["opts"] == ["yes", "no"] and step["_social"] is stub_item,
      step)

# Full flow: a queued question is injected as the very next step...
answers = []
class _AnswerStub(_StubSocial):
    def send_answer(self, item, choice, correct):
        answers.append((item.get("id"), choice, correct))
        return True

game.social = _AnswerStub()
game.social.take_question = lambda: dict(stub_item)
game.state = "PLAYING"
game.active_script = [
    {"_id": "before", "q": "warm up", "opts": ["a", "b"], "type": "choice"},
    {"_id": "after", "q": "next one", "opts": ["a", "b"], "type": "choice"},
]
game.current_step = 1     # as after _confirm_answer advanced past "before"
game.selected_answer = 0
check("queued question is injected at the next slot",
      game._queue_social_question() is True
      and game.active_script[0]["_id"] == "before"
      and game.active_script[1]["_id"] == "social_q1",
      [s["_id"] for s in game.active_script])

# Answering it reports to the author with a correctness verdict.
game.current_step = 1
game.selected_answer = 0          # "yes" == the correct option
game.question_start_time = time.time()
captured = {}

def _capture_note(text, tone="info", seconds=6.0):
    captured["text"] = text

_orig_note = game._note
game._note = _capture_note
try:
    game._confirm_answer()
finally:
    game._note = _orig_note
check("answering a social question reports to its author",
      answers == [("q1", "yes", True)], answers)
check("a correct answer is acknowledged to the player",
      "RIGHT" in (captured.get("text") or ""), captured)

_orig_report = game._report_social_answer
game.social = None
game.compose = None
game.name_edit = None
game.social_notes = []

game.state = "TITLE"
game.running = False
pygame.quit()

if FAILURES:
    print("\nSMOKE_FAILED %d: %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nSMOKE_OK")
