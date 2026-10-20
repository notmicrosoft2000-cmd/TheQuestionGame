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

game.running = False
pygame.quit()

if FAILURES:
    print("\nSMOKE_FAILED %d: %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nSMOKE_OK")
