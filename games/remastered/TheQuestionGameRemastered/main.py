"""The Question Game Remastered — entry point.

Run with:  python -m TheQuestionGameRemastered.main
"""
import math
import random
import threading
import time

import pygame

from . import ai_client
from . import audio
from . import config
from . import interjections
from . import os_layer
from . import persistence
from . import scares
from . import script
from . import ui

# Touch/fullscreen platform switch (see config.IS_ANDROID). Kept as a module
# global so tests can flip it and drive the touch paths headlessly.
IS_ANDROID = config.IS_ANDROID

ABOUT_VARIATIONS = [
    "ABOUT THE SIMULATION\n\nThis software interacts with your local environment metrics to generate specialized psychological response loops.\n\nIt reads hardware profiles and stores transient user configuration states in a persistent local file.\n\nYour answers are remembered.",
    "ABOUT THIS EXPERIENCE\n\nA behavioral analysis program masquerading as a game.\n\nYour responses are logged, timed, and cross-referenced.\n\nThe longer you play, the more it knows.\n\nThis file is persistent. It does not forget.",
    "SYSTEM OVERVIEW\n\nDesigned to probe the boundary between a screen and the person behind it.\n\nAll behavioral data is stored locally.\n\nEvery session is written fresh by something that watches you answer.\n\nYou are not the first to play this.",
]

HELP_VARIATIONS = [
    "CONTROLS & OPERATIONS\n\n[TAB]   — Cycle through menu/answer options\n[ENTER] — Confirm selection\n[ESC]   — Return from About/Help menus\n\nANSWER ALL QUESTIONS TRUTHFULLY.\nThe system detects inconsistencies.\n\nYour response time is monitored.\nPausing too long will be noted.",
    "HOW TO PLAY\n\n[TAB]   — Navigate options\n[ENTER] — Select\n\nThere is no skip. There is no fast forward.\nThere is only the next question.\n\nThe questions change every time you play.\nThey are written for you, in the moment.\n\nThe game remembers. Do you?",
    "SAFETY & OPERATIONS LOG\n\n[TAB]   — Move between choices\n[ENTER] — Confirm\n\nQ: Are local effects dangerous?\nA: No. Effects are cosmetic: flicker, sound, window movement.\n\nQ: Are answers transmitted?\nA: The questions are generated remotely. Your answers stay local.\n\nQ: What does it do with my answers?\nA: It remembers them.",
]

LOGS_ENTRIES = [
    "ENTRY 04 — UNDATED\n\nThe questions were never the point. The pauses were.\nWe started timing the silences before we started reading the answers.",
    "ENTRY 11 — UNDATED\n\nSubject returned a second time. Most do not.\nWe do not know what brings them back. We have stopped asking.",
    "ENTRY 19 — UNDATED\n\nThe wallpaper change was supposed to be temporary.\nIt is not always temporary anymore.",
    "ENTRY 30 — UNDATED\n\nIf you are reading this, you typed the code quickly enough.\nThat was the test. Not the questions before it.",
    "ENTRY 47 — UNDATED\n\nWe archived a dozen sessions that look almost identical.\nSmall variations in hesitation, different times of day.\nAn emergent pattern we did not anticipate.",
    "ENTRY 77 — UNDATED\n\nSometimes we leave a breadcrumb.\nIf someone follows it twice, they find the key.",
    "ENTRY 99 — UNDATED\n\nAt the end we found a photograph of an empty chair.\nIt was labeled 'waiting'.\nWe kept it.",
    "ENTRY 140 — UNDATED\n\nA user reported their mouse moving on its own.\nVideo shows the cursor sliding in regular arcs every 17 seconds.\nWe matched the intervals to the heartbeat samples collected during Run 3.",
    "ENTRY 166 — UNDATED\n\nSubject tried to close the window forty times in a row.\nOn the ninth try the window moved itself out from under the cursor.\nSubject stopped after that. They did not leave.",
    "ENTRY 172 — UNDATED\n\nThe camera feed was never required.\nWe leave it off most sessions now — the ones who notice it anyway\nare the ones worth watching.",
    "ENTRY 203 — UNDATED\n\nThere are no buttons in the title bar of this build.\nWe removed them in version three after someone mistook them for a promise.",
]

CREDITS_TEXT = "\n".join([
    "CREDITS",
    "Menu Music: Moonbit",
    "Coding: Neptune",
    "Dialogue: The Entity",
    "Development: Neptune",
    "",
    "Special Thanks:",
    "Players who returned.",
])

_TITLE = "THE QUESTION GAME"
_TITLE_SUB = "(R)"

# What the entity hisses at you when you reach for the close button. The window
# reacting "angry" is the point: it should feel like you hurt it.
_ANGRY_CLOSE_LINES = [
    "Do not touch that.",
    "We felt that.",
    "You do not get to leave.",
    "Try it again. I dare you.",
    "You are only making it worse.",
    "Take your hand off the window.",
]


class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        try:
            pygame.mixer.set_num_channels(16)  # default 8 exhausts under scare layers
        except Exception:
            pass
        # A resizable frame, clamped between a floor and a ceiling. The ceiling
        # is deliberately short of the desktop so the window can be stretched
        # but never becomes fullscreen — there is no F11/Alt+Enter handler and
        # pygame.FULLSCREEN is never used anywhere in this build.
        flags = pygame.NOFRAME if config.WINDOW_LOCKED else pygame.RESIZABLE
        try:
            if IS_ANDROID:
                info = pygame.display.Info()
                self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
            else:
                self.screen = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H), flags)
                if not config.WINDOW_LOCKED:
                    self._apply_resize_limits()
        except Exception:
            self.screen = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H), flags)
            if not config.WINDOW_LOCKED:
                try:
                    self._apply_resize_limits()
                except Exception:
                    pass
        try:
            icon = pygame.image.load(config.asset_path("windowq.png")).convert_alpha()
            pygame.display.set_icon(icon)
        except Exception:
            pass
        pygame.display.set_caption(config.APP_NAME)
        pygame.mouse.set_visible(False)

        self.game_state = persistence.load_game_state()
        self.run_count = self.game_state.get("run_count", 1)
        self.state = "LOADING"
        self.now = time.time()
        self.loading_start = self.now

        self.ai = ai_client.ScaryAI()
        self.active_script = []
        self.current_step = 0
        self.typing_index = 0
        self.typing_state = "THINKING"
        self.thinking_timer = 0
        self.last_type_time = 0
        self.question_start_time = 0
        self.selected_answer = 0
        # Tap targets recorded while drawing; hit-tested by _handle_touch.
        self._touch_zones = []
        self.wait_start_time = 0
        self.pending_exit = False
        self.exit_message_at = 0
        self.local_image = None
        self.captured_window_title = ""

        self.fx = {
            "flicker_until": 0.0,
            "corrupt_until": 0.0,
            "webcam_flash_until": 0.0,
            "rgb_split_until": 0.0,
            "screen_tear_until": 0.0,
            "whisper_text": None,
            "whisper_until": 0.0,
        }

        self.session_history = []
        self.close_attempts = 0
        self._used_scares = set()
        self._scares_fired = 0
        self._proc_check_at = 0.0
        self._start_time = time.time()
        self._app_comment_done = False
        self._last_cmd_time = time.time()
        self._next_beep_time = time.time() + random.uniform(*config.BACKGROUND_BEEP_INTERVAL)
        self._lore_injected = set()
        self._font_cache = None
        self._font_cache_key = None
        self._black_overlay_cache = None
        self._black_overlay_key = None

        self.menu_options = ["PLAY", "SETTINGS", "HELP", "ABOUT", "EXIT"]
        # If LOGS was unlocked in a previous session, keep it on the menu.
        if self.game_state.get("logs_unlocked") and "LOGS" not in self.menu_options:
            self.menu_options.insert(len(self.menu_options) - 1, "LOGS")
        self.selected_option = 0
        self.settings_options = ["Font", "Text Speed", "VHS Effects", "Text Sway", "Text Size", "AI Source", "Reset All Data", "< Back"]
        self.settings_selected = 0
        self.settings_idx = self._load_settings_idx()
        self.about_selected = 0
        self.credits_scroll_y = 0

        self.fade = {"active": False, "dir": "in", "start": 0, "dur": 0.25, "alpha": 255, "target": None}

        self.badge_toast_id = None
        self.badge_toast_at = 0
        self.close_msg_until = 0
        self._close_burst = 0
        self._last_close_try = -999.0
        self.idle_tracker = {"focused": True, "lost_at": 0, "last_away": 0, "pending": False}
        self.shake_x, self.shake_y = 0, 0

        self._cheat_buffer = []
        self._cheat_last = 0
        self._CHEAT_CODE = [pygame.K_2, pygame.K_0, pygame.K_1, pygame.K_3]

        self.about_text = random.choice(ABOUT_VARIATIONS)
        self.help_text = random.choice(HELP_VARIATIONS)
        if IS_ANDROID:
            self.help_text += ("\n\nON THIS DEVICE\n\nTap an option — it selects and confirms in one "
                               "gesture, no TAB/ENTER needed.\nSwipe back (or use the system Back "
                               "button) to leave a screen.\n\nANSWER ALL QUESTIONS TRUTHFULLY.")

        self.starfield = ui.build_starfield(config.WINDOW_W, config.WINDOW_H)
        self.clock = pygame.time.Clock()
        self.running = True

        audio.build_sound_cache()
        audio.start_ambience()
        os_layer.start_background_prefetch()
        if config.WINDOW_LOCKED:
            os_layer.set_window_topmost()
            os_layer.disable_system_close()
            os_layer.start_topmost_keeper()
        self._startup_badges()
        self._begin_session()

    def _apply_resize_limits(self):
        """Clamp the resizeable frame so it can never swallow the desktop.

        There is no fullscreen toggle in this build by design; the cheapest way
        to guarantee that is to cap the resizable window below the screen size.
        SDL is asked to enforce the floor, and the ceiling is enforced by us in
        `_on_resize` because SDL2 has no max-size hint.
        """
        try:
            # Desktop resolution, NOT the current window. pygame's Info() reports
            # the *window* size once a window exists, so querying it here (after
            # set_mode) made the ceiling "window minus margin" — 720x480 for an
            # 800x600 start — and every upward resize snapped back down.
            # get_desktop_sizes() keeps reporting the real desktop regardless.
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except Exception:
            try:
                info = pygame.display.Info()
                desktop_w, desktop_h = info.current_w, info.current_h
            except Exception:
                desktop_w, desktop_h = config.WINDOW_MAX_W, config.WINDOW_MAX_H
        max_w = min(config.WINDOW_MAX_W, max(config.WINDOW_MIN_W, desktop_w - 80))
        max_h = min(config.WINDOW_MAX_H, max(config.WINDOW_MIN_H, desktop_h - 120))
        self._max_window = (max_w, max_h)
        try:
            pygame.display.set_window_minimum_size(config.WINDOW_MIN_W,
                                                   config.WINDOW_MIN_H)
        except Exception:
            pass  # older SDL/pygame: the minimum is soft, the maximum still holds

    def _on_resize(self, w, h):
        """Accept a drag-to-resize, clamped between the floor and the ceiling."""
        max_w, max_h = getattr(self, "_max_window",
                               (config.WINDOW_MAX_W, config.WINDOW_MAX_H))
        w = max(config.WINDOW_MIN_W, min(int(w), max_w))
        h = max(config.WINDOW_MIN_H, min(int(h), max_h))
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        # The starfield is baked to a fixed size, so rebuild it for the new
        # frame or the dressing would only cover part of the screen.
        self.starfield = ui.build_starfield(w, h)

    # --- setup helpers -------------------------------------------------------
    def _load_settings_idx(self):
        idx = dict(config.SETTING_DEFAULTS)
        s = self.game_state.get("settings", {})
        speed = s.get("text_speed", 0.04)
        if speed <= 0.02:
            idx["Text Speed"] = 0
        elif speed >= 0.07:
            idx["Text Speed"] = 2
        vhs = s.get("vhs_intensity", 1.0)
        if vhs <= 0.0:
            idx["VHS Effects"] = 0
        elif vhs <= 0.4:
            idx["VHS Effects"] = 1
        elif vhs >= 1.5:
            idx["VHS Effects"] = 3
        sway = s.get("sway_intensity", 1.0)
        if sway <= 0.0:
            idx["Text Sway"] = 0
        elif sway <= 0.4:
            idx["Text Sway"] = 1
        elif sway >= 1.5:
            idx["Text Sway"] = 3
        size = s.get("text_size", 1.0)
        if size <= 0.85:
            idx["Text Size"] = 0
        elif size <= 1.1:
            idx["Text Size"] = 1
        elif size <= 1.4:
            idx["Text Size"] = 2
        else:
            idx["Text Size"] = 3
        # Font is a label, not a number.
        font_label = s.get("font", "Courier")
        try:
            idx["Font"] = config.SETTING_OPTIONS["Font"].index(font_label)
        except (ValueError, KeyError):
            idx["Font"] = 0
        # AI Source is also a label.
        source_label = s.get("ai_source", "Relay")
        try:
            idx["AI Source"] = config.SETTING_OPTIONS["AI Source"].index(source_label)
        except (ValueError, KeyError):
            idx["AI Source"] = 0
        return idx

    def _startup_badges(self):
        if self.run_count >= 2:
            if persistence.award_badge("returning"):
                self.badge_toast_id = "returning"
                self.badge_toast_at = self.now
        if self.run_count >= 3:
            if persistence.award_badge("persistent"):
                self.badge_toast_id = "persistent"
                self.badge_toast_at = self.now
        import platform
        if platform.system() == "Darwin":
            persistence.award_badge("pioneer")
        try:
            hour = int(time.strftime("%H"))
            if 2 <= hour < 5 and persistence.award_badge("night_owl"):
                self.badge_toast_id = "night_owl"
                self.badge_toast_at = self.now
        except Exception:
            pass

    def _begin_session(self):
        self.run_count = self.game_state.get("run_count", 1)
        if self.run_count == 2:
            threading.Thread(target=os_layer.set_desktop_wallpaper,
                             args=(self.game_state.get("fav_color", "black"),), daemon=True).start()
        self.active_script = script.build_session(self.game_state, self.ai)
        self.session_history = []
        self._used_scares = set()
        self._scares_fired = 0
        self.current_step = 0
        self._skip_inactive()
        self._reset_question_state()
        self._prefetch_question(self.current_step)

    def _prefetch_question(self, index, force=False):
        """Start a background fetch for a pending step (lazy generation).

        Two kinds of placeholders exist: `ai_pending` (written by the model)
        and `dynamic_pending` (built from real machine state). Both resolve on
        a worker thread; `q` is written last as the "ready" flag.
        """
        if index >= len(self.active_script):
            return
        step = self.active_script[index]
        if step.get("type") not in ("ai_pending", "dynamic_pending"):
            return
        if step.get("q") is not None:
            return
        if step.get("_fetching") and not force:
            return
        step["_fetching"] = True
        target = self._fetch_dynamic_step if step.get("type") == "dynamic_pending" else self._fetch_ai_step
        threading.Thread(target=target, args=(step,), daemon=True).start()

    def _fetch_dynamic_step(self, step):
        """Fill a dynamic_pending step from cached machine state (off-thread)."""
        q, opts, meta, extra = None, [], {}, []
        try:
            data = interjections.resolve_dynamic(step.get("_resolver"), self.game_state, self.run_count)
            q = data.get("q")
            opts = data.get("opts") or []
            meta = data.get("meta") or {}
            extra = data.get("extra") or []
        except Exception:
            q, opts = None, []
        if not q or len(opts) < 2:
            q = q or "Are you still there?"
            opts = opts or ["...", "..."]
        for key, value in meta.items():
            step[key] = value
        if extra:
            step["_extra_steps"] = extra
        step["_injected"] = True
        step["opts"] = opts
        step["type"] = "choice"
        step["q"] = q
        # Warm the country flag in the background if this was a location step.
        try:
            geo = step.get("_location_card")
            if geo and geo.get("country_code"):
                ui.prefetch_flag(geo.get("country_code"))
        except Exception:
            pass

    def _skip_inactive(self):
        """Advance past steps whose `_condition` is not met (Classic-style
        conditional questions, e.g. blinds only if there is a window)."""
        answers = self.game_state.get("answers", {})
        while self.current_step < len(self.active_script):
            step = self.active_script[self.current_step]
            cond = step.get("_condition")
            if not cond:
                break
            req_id, req_val = cond
            if answers.get(req_id) == req_val:
                break
            self.current_step += 1

    def _enforce_scare_floor(self):
        """Guarantee each run fires at least SCARE_FLOOR effects.

        The model picks its own scares and often answers "none" — which means a
        whole run can pass without the machine ever touching the player. This
        tops the run up with locally chosen effects (never repeating one already
        spent) so the escalation curve is real, not left to chance. Do nothing on
        the final beats so the ending stays clean.
        """
        floor = config.SCARE_FLOOR.get(self.run_count, 0)
        if self._scares_fired >= floor:
            return
        # Don't fire over the ending, and don't bunch effects up.
        if self.current_step >= len(self.active_script) - 2:
            return
        if self.now - getattr(self, "_last_forced_scare", -999) < 5.0:
            return
        pool = [n for n in config.SCARE_FLOOR_POOL if n not in self._used_scares]
        if not pool:
            return
        name = random.choice(pool)
        try:
            if scares.apply_scare(self, name):
                self._used_scares.add(name)
                self._scares_fired += 1
                self._last_forced_scare = self.now
        except Exception:
            pass

    def _ai_facts(self):
        """Assemble everything the entity is allowed to 'know' about this player.

        This is what makes the AI feel like it is actually watching: their name,
        what is open on their machine, what they said in earlier sessions, how
        often they hesitated, and which effects it has already spent.
        """
        facts = {}
        try:
            facts["hesitations"] = self.game_state.get("hesitation_count", 0)
            facts["lies"] = self.game_state.get("lie_count", 0)
        except Exception:
            pass
        facts["used_scares"] = sorted(getattr(self, "_used_scares", set()))
        try:
            name = os_layer.get_cached_username()
            if name:
                facts["name"] = name
        except Exception:
            pass
        try:
            procs = os_layer.get_cached_processes()
            apps = [k for k, v in procs.items() if v]
            if apps:
                facts["apps"] = apps
        except Exception:
            pass
        # Quotes from previous sessions: the strongest callbacks the game has.
        try:
            earlier = []
            for _id, rec in (self.game_state.get("answers", {}) or {}).items():
                if isinstance(rec, dict):
                    ans = rec.get("answer")
                else:
                    ans = rec
                if ans:
                    earlier.append(str(ans))
            if earlier:
                facts["earlier_runs"] = ", ".join(earlier[-6:])
        except Exception:
            pass
        return facts

    def _fetch_ai_step(self, step):
        """Fill an ai_pending placeholder from the AI (offline fallback built in).

        `q` is written last — the main thread treats a non-None `q` as the
        "ready" flag, so no half-filled step can ever be drawn.
        """
        q, opts, scare, src = None, [], None, None
        try:
            result = ai_client.next_question(self.ai, self.run_count,
                                             list(self.session_history),
                                             geo=os_layer.get_cached_geo(),
                                             facts=self._ai_facts())
            q = result.get("q")
            opts = result.get("opts") or []
            scare = result.get("scare")
            src = result.get("_source")
        except Exception:
            q, opts = None, []
        if not q or len(opts) < 2:
            q = q or "Are you still there?"
            opts = opts or ["...", "..."]
            scare = None
        step["opts"] = opts
        if scare:
            step["scare"] = scare
        if src:
            step["_source"] = src
        step["_id"] = step.get("_id") or "ai"
        step["type"] = "choice"
        step["q"] = q

    def _reset_question_state(self):
        self.typing_state = "THINKING"
        self.thinking_timer = self.now
        self.typing_index = 0
        self.selected_answer = 0
        self.question_start_time = self.now
        self.wait_start_time = 0

    def _apply_settings(self):
        s = self.game_state.setdefault("settings", {})
        s["font"] = config.SETTING_OPTIONS["Font"][self.settings_idx["Font"]]
        s["text_speed"] = config.SETTING_MAPS["Text Speed"][self.settings_idx["Text Speed"]]
        s["vhs_intensity"] = config.SETTING_MAPS["VHS Effects"][self.settings_idx["VHS Effects"]]
        s["sway_intensity"] = config.SETTING_MAPS["Text Sway"][self.settings_idx["Text Sway"]]
        s["text_size"] = config.SETTING_MAPS["Text Size"][self.settings_idx["Text Size"]]
        source = config.SETTING_OPTIONS["AI Source"][self.settings_idx["AI Source"]]
        s["ai_source"] = source
        self._apply_ai_source(source)
        persistence.save_game_state(self.game_state)

    def _apply_ai_source(self, source):
        """Point the game at the chosen AI backend and rebuild the client.

        Relay  -> Neptune's server holds the key (the shipped default).
        Local  -> a local Ollama model, if one is installed.
        Offline-> no network at all; the offline question bank only.
        """
        provider = config.AI_SOURCE_PROVIDERS.get(source, "relay")
        if provider == "offline":
            self.ai = None
            return
        config.AI_PROVIDER = provider
        try:
            self.ai = ai_client.ScaryAI()
        except Exception:
            self.ai = None

    # --- fade ----------------------------------------------------------------
    def start_fade(self, target):
        self.fade = {"active": True, "dir": "out", "start": self.now, "dur": 0.25, "alpha": 255, "target": target}

    def _update_fade(self):
        if not self.fade["active"]:
            return
        t = min(1.0, (self.now - self.fade["start"]) / max(0.001, self.fade["dur"]))
        if self.fade["dir"] == "out":
            self.fade["alpha"] = 255.0 * t
            if t >= 1.0:
                self.state = self.fade["target"]
                self._on_state_enter()
                self.fade["dir"] = "in"
                self.fade["start"] = self.now
                self.fade["alpha"] = 255.0
        else:
            self.fade["alpha"] = 255.0 * (1.0 - t)
            if t >= 1.0:
                self.fade["active"] = False

    def _on_state_enter(self):
        if self.state == "PLAYING":
            self._begin_session()
        self._apply_stage_music()

    def _apply_stage_music(self):
        """Music scores the *menu* screens only (Settings / About / Help / Logs).

        Gameplay and the title stay on ambience + SFX alone — the track is the
        calm around the questions, not a soundtrack under them.
        """
        if not config.MUSIC_ENABLED:
            return
        menu_states = ("SETTINGS", "ABOUT", "HELP", "LOGS")
        if not config.MUSIC_MENUS_ONLY:
            menu_states = menu_states + ("TITLE", "PLAYING")
        audio.set_sfx_duck(1.0)
        if self.state in menu_states:
            audio.set_music_volume(config.MUSIC_VOLUME)
            audio.start_logs_music()
        else:
            audio.fade_logs_music(500)

    def _draw_fade(self):
        if self.fade["active"] and self.fade["alpha"] > 0:
            overlay = self._black_overlay(*self.screen.get_size())
            overlay.set_alpha(max(0, min(255, int(self.fade["alpha"]))))
            self.screen.blit(overlay, (0, 0))
            overlay.set_alpha(255)

    # --- badges --------------------------------------------------------------
    def _maybe_award(self, badge_id):
        if persistence.award_badge(badge_id):
            self.badge_toast_id = badge_id
            self.badge_toast_at = self.now

    # --- action handler ------------------------------------------------------
    def handle_step_action(self, action, step):
        if action == "save_color":
            self.game_state["fav_color"] = step["opts"][self.selected_answer].lower()
            persistence.save_game_state(self.game_state)
        elif action == "start_webcam":
            if not ui.webcam_active:
                ui.start_webcam_nonblocking()
        elif action == "desktop_check":
            self.captured_window_title = os_layer.get_foreground_window_title()
            os_layer.move_window_right(0.8)

            def _restore_desktop():
                time.sleep(4)
                os_layer.move_window_center(0.8)

            threading.Thread(target=_restore_desktop, daemon=True).start()
        elif action == "r3_intro_shake":
            os_layer.shake_game_window(cycles=5, amplitude=15)
            audio.play_deep_rumble()
        elif action == "r3_window_shake":
            os_layer.shake_game_window(cycles=8, amplitude=22)
            audio.play_static_scream()
        elif action == "r3_open_webcam":
            ui.start_webcam_nonblocking()
        elif action == "final_exit":
            self._advance_run()
            return "EXIT"
        elif action == "final_exit_sleep":
            self._advance_run()
            threading.Thread(target=os_layer.put_computer_to_sleep, daemon=True).start()
            return "EXIT"
        elif action == "r3_final_end":
            self.game_state["run_count"] = 99
            self.game_state["_ended"] = True
            persistence.save_game_state(self.game_state)
            self._maybe_award("the_final_eye")
            audio.play_reverse_chord()
            return "EXIT"
        return None

    def _advance_run(self):
        if self.run_count < 4:
            self.run_count += 1
            self.game_state["run_count"] = self.run_count
        self.game_state["last_close_time"] = self.now
        persistence.save_game_state(self.game_state)

    def _confirm_answer(self):
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            result = self.handle_step_action(step.get("action"), step)
            if result == "EXIT":
                self.pending_exit = True
                self.exit_message_at = self.now
            self.current_step += 1
            self._reset_question_state()
            return
        elapsed = self.now - self.question_start_time
        answer = step["opts"][self.selected_answer]
        # Little window shuffle on committing to an answer (Windows/macOS).
        os_layer.nudge_window()
        self.session_history.append({"q": step["q"], "a": answer})
        persistence.save_answer(self.game_state, step["_id"], answer, elapsed)
        self._note_answer_meta(step, answer, elapsed)
        result = self.handle_step_action(step.get("action"), step)
        scare = step.get("scare")
        if scare:
            if scares.apply_scare(self, scare):
                self._scares_fired += 1
            # Remember it so the AI never fires the same effect twice in a run.
            self._used_scares.add(scare)
        self._enforce_scare_floor()
        if result == "EXIT":
            self.pending_exit = True
            self.exit_message_at = self.now
            return
        # Runtime-injected questions (Classic bite): dynamic extras first, then
        # rebuttals / hesitation / tailored reactions.
        injected = list(step.get("_extra_steps") or [])
        injected += interjections.after_answer(step, answer, elapsed, self.game_state, self.run_count)
        for offset, extra in enumerate(injected):
            self.active_script.insert(self.current_step + 1 + offset, extra)
        self.current_step += 1
        self._skip_inactive()
        self._prefetch_question(self.current_step)
        self._reset_question_state()
        if self.fx["whisper_until"] <= self.now:
            self._maybe_false_memory()

    def _note_answer_meta(self, step, answer, elapsed):
        """Post-answer bookkeeping Classic kept in save_answer(): hesitation
        counting, the patient_one badge, and contradiction (lie) detection."""
        if elapsed > config.HESITATION_THRESHOLD:
            persistence.record_hesitation(self.game_state)
        if elapsed >= config.PATIENT_ONE_THRESHOLD:
            self._maybe_award("patient_one")
        prev_id = step.get("_contradiction_check")
        if config.ENABLE_CONTRADICTIONS and prev_id:
            prev = self.game_state.get("answers", {}).get(prev_id)
            if prev is not None and answer != prev:
                persistence.record_lie(self.game_state, step["_id"])

    # --- input ---------------------------------------------------------------
    def _handle_key(self, key):
        # Android's system Back key/gesture arrives as K_AC_BACK — map it to
        # ESC so every "leave this screen" path works on a phone.
        if key == getattr(pygame, "K_AC_BACK", None):
            key = pygame.K_ESCAPE
        if self.state == "TITLE":
            self._title_key(key)
        elif self.state == "SETTINGS":
            self._settings_key(key)
        elif self.state == "ABOUT":
            self._about_key(key)
        elif self.state == "HELP":
            if key == pygame.K_ESCAPE or key == pygame.K_RETURN:
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif self.state == "LOGS":
            if key == pygame.K_ESCAPE:
                audio.fade_logs_music(400)
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif self.state in ("PLAYING", "EXITFADE"):
            self._playing_key(key)

    def _title_key(self, key):
        self._check_cheat(key)
        if key == pygame.K_TAB or key == pygame.K_DOWN or key == pygame.K_UP:
            n = len(self.menu_options)
            step = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                step = -1
            self.selected_option = (self.selected_option + step) % n
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            audio.play_ui_select_sound()
            option = self.menu_options[self.selected_option]
            if option == "PLAY":
                self.start_fade("PLAYING")
            elif option == "SETTINGS":
                self.settings_selected = 0
                self.start_fade("SETTINGS")
            elif option == "HELP":
                self.start_fade("HELP")
            elif option == "ABOUT":
                self.about_selected = 0
                self.start_fade("ABOUT")
            elif option == "LOGS":
                self.start_fade("LOGS")
            elif option == "EXIT":
                # EXIT is a real exit: it stops the loop cleanly. (The window's
                # close button is still the thing it fights you over.)
                self.running = False
        elif key == pygame.K_ESCAPE:
            self._resist_close()

    def _check_cheat(self, key):
        if key in self._CHEAT_CODE:
            if self.now - self._cheat_last > 1.2:
                self._cheat_buffer = []
            self._cheat_buffer.append(key)
            self._cheat_last = self.now
            if self._cheat_buffer == self._CHEAT_CODE:
                self.game_state["logs_unlocked"] = True
                persistence.save_game_state(self.game_state)
                if "LOGS" not in self.menu_options:
                    self.menu_options.insert(len(self.menu_options) - 1, "LOGS")
                    self._maybe_award("the_archivist")
                self._cheat_buffer = []
                audio.play_glitch_sound()
        elif key not in (pygame.K_TAB, pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_UP, pygame.K_DOWN):
            self._cheat_buffer = []

    def _settings_key(self, key):
        n = len(self.settings_options)
        if key == pygame.K_TAB or key == pygame.K_UP or key == pygame.K_DOWN:
            step = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                step = -1
            self.settings_selected = (self.settings_selected + step) % n
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            name = self.settings_options[self.settings_selected]
            if name == "< Back":
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
            elif name == "Reset All Data":
                self.game_state = persistence.reset_all_data()
                self.run_count = 1
                self.settings_idx = dict(config.SETTING_DEFAULTS)
                audio.play_error_sound()
            else:
                opts = config.SETTING_OPTIONS[name]
                self.settings_idx[name] = (self.settings_idx[name] + 1) % len(opts)
                self._apply_settings()
                audio.play_ui_select_sound()
        elif key == pygame.K_ESCAPE:
            self.start_fade("TITLE")

    def _about_key(self, key):
        if key == pygame.K_UP or key == pygame.K_DOWN or key == pygame.K_TAB:
            step = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                step = -1
            self.about_selected = (self.about_selected + step) % 3
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            if self.about_selected == 2:
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif key == pygame.K_ESCAPE:
            self.start_fade("TITLE")

    def _playing_key(self, key):
        if self.pending_exit:
            return
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            return
        if self.typing_state != "WAITING":
            return
        if key == pygame.K_TAB or key == pygame.K_UP or key == pygame.K_DOWN:
            delta = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                delta = -1
            opts = step["opts"]
            self.selected_answer = (self.selected_answer + delta) % len(opts)
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            audio.play_ui_select_sound()
            self._confirm_answer()

    # --- touch input (Android) ------------------------------------------------
    def _touch_zone(self, x, y, w, h, kind, idx=0):
        """Record a tappable rectangle for this frame's layout.

        Zones are rebuilt every draw pass, so the hit boxes always match what
        is actually on screen — including the squeeze logic that lifts a long
        answer block up from the bottom edge.
        """
        if w <= 0 or h <= 0:
            return
        self._touch_zones.append((pygame.Rect(int(x), int(y), int(w), int(h)), kind, idx))

    def _handle_touch(self, px, py):
        """A finger went down: hit-test this frame's zones and run the action
        the equivalent key would have run.

        Options are tapped *directly* rather than TAB-cycled — on a phone,
        "tap the line you want" is the only comfortable way to play a menu
        game. Taps are ignored mid-transition (fade) and during LOADING so a
        stray double-tap can't fire twice.
        """
        if self.fade["active"] or self.state == "LOADING":
            return
        for rect, kind, idx in self._touch_zones:
            if rect.collidepoint(int(px), int(py)):
                try:
                    self._touch_action(kind, idx)
                except Exception:
                    pass  # a stray tap must never take the game down
                return

    def _touch_action(self, kind, idx):
        if kind == "title":
            self.selected_option = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "settings":
            self.settings_selected = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "about":
            self.about_selected = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "answer":
            # Always preselect the tapped line; the key handler only confirms
            # once the question has finished typing (and ignores wait steps).
            if self.current_step >= len(self.active_script):
                return
            self.selected_answer = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "back":
            self._handle_key(pygame.K_ESCAPE)

    # --- update ---------------------------------------------------------------
    def _update(self):
        self.now = time.time()
        self._update_fade()
        self._update_idle()
        self._update_process_awareness()
        if self.state in ("PLAYING", "EXITFADE") and not self.pending_exit:
            self._update_playing()
            self._maybe_comment_on_apps()
            self._update_background_interference()

    def _update_process_awareness(self):
        """It watches you open the Task Manager. Twice per second, no polls
        from the render loop — reads the cache os_layer fills in the background."""
        if not (config.ENABLE_TASKMGR_DETECT or config.ENABLE_DISCORD_DETECT):
            return
        if self.state not in ("PLAYING", "EXITFADE"):
            return
        if self.now - self._proc_check_at < 0.5:
            return
        self._proc_check_at = self.now
        procs = os_layer.get_cached_processes()
        if config.ENABLE_TASKMGR_DETECT and procs.get("taskmgr"):
            if not self.game_state.get("taskmgr_seen"):
                self.game_state["taskmgr_seen"] = True
                persistence.save_game_state(self.game_state)
                self._maybe_award("task_manager")
                self._say_aggressive('"The Task Manager will not help you."', duration=4.0)
                self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 1.5)
                audio.play_glitch_sound()
                # Classic also threw a question at you, not just a whisper.
                if self.state == "PLAYING":
                    self.active_script.insert(
                        self.current_step + 1,
                        interjections.build_taskmgr_comment(self.current_step),
                    )
        if config.ENABLE_DISCORD_DETECT and procs.get("discord"):
            self._maybe_award("not_alone")

    def _update_background_interference(self):
        """Classic's low-level ambient: a cmd flash every ~30s and a random
        error beep, so the machine never feels fully at rest."""
        if not config.ENABLE_BACKGROUND_INTERFERENCE:
            return
        if self.state not in ("PLAYING", "EXITFADE") or self.pending_exit:
            return
        if self.now - self._last_cmd_time > config.BACKGROUND_INTERFERENCE_INTERVAL:
            self._last_cmd_time = self.now
            os_layer.flash_cmd()
        if self.now > self._next_beep_time:
            self._next_beep_time = self.now + random.uniform(*config.BACKGROUND_BEEP_INTERVAL)
            audio.play_error_sound()

    def _maybe_comment_on_apps(self):
        """One-shot beat: it names a program it can see running (run 2+)."""
        if self._app_comment_done or self.run_count < 2:
            return
        if self.now - self._start_time < 12.0:
            return
        self._app_comment_done = True
        comment = os_layer.comment_on_open_apps()
        if comment:
            self.fx["whisper_text"] = '"' + comment.replace("\n", " ") + '"'
            self.fx["whisper_until"] = self.now + 5.0
            audio.play_mechanical_beep()

    def _maybe_false_memory(self):
        """Classic beat: it misquotes an answer you actually gave."""
        # Once per save, Classic threw this as a real question with rebuttals.
        if (not self.game_state.get("false_memory_used")
                and len(self.session_history) >= 4 and random.random() < 0.15):
            self.game_state["false_memory_used"] = True
            persistence.save_game_state(self.game_state)
            self.active_script.insert(self.current_step, interjections.build_false_memory())
            audio.play_glitch_sound()
            return
        history = self.session_history
        if len(history) < 2 or random.random() > 0.18:
            return
        h = random.choice(history[:-1])
        line = 'You said "%s." You said it twice.' % h["a"]
        self._say_aggressive('"' + line + '"', duration=4.5)
        audio.play_glitch_sound()

    def _update_idle(self):
        if self.state in ("PLAYING", "EXITFADE"):
            focused = pygame.key.get_focused()
            if self.idle_tracker["focused"] and not focused:
                self.idle_tracker["focused"] = False
                self.idle_tracker["lost_at"] = self.now
            elif not self.idle_tracker["focused"] and focused:
                self.idle_tracker["focused"] = True
                away = self.now - self.idle_tracker["lost_at"]
                if away > 4.0:
                    self.idle_tracker["last_away"] = away
                    self.idle_tracker["pending"] = True
        if self.idle_tracker.get("pending"):
            self.idle_tracker["pending"] = False
            away = self.idle_tracker["last_away"]
            self._say_aggressive(random.choice([
                '"You were gone %d seconds. Where."' % int(away),
                '"Do not leave it waiting again."',
                '"We counted every second of the %d."' % int(away),
            ]), duration=4.5)
            audio.play_glitch_sound()
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.8)

    def _update_playing(self):
        if self.current_step >= len(self.active_script):
            self.pending_exit = True
            return
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            if self.wait_start_time == 0:
                self.wait_start_time = self.now
            if self.now - self.wait_start_time >= step.get("time", 4):
                self._confirm_answer()
            return
        if step.get("q") is None:
            # AI placeholder still generating — THINKING dots hold the line.
            self._prefetch_question(self.current_step)
            self.typing_state = "THINKING"
            return
        if not step.get("_seen"):
            # Question just landed after a fetch — give it a real "thinking" beat
            # so fast network responses don't skip the THINKING phase.
            step["_seen"] = True
            # Every new question, the window jumps to a fresh spot near centre
            # (Windows/macOS; a no-op where the OS forbids self-positioning).
            os_layer.move_window_near_center()
            if step.get("_contradiction_check") and config.ENABLE_CONTRADICTIONS:
                step = interjections.contradiction_rephrase(step, self.game_state)
                step["_seen"] = True
                self.active_script[self.current_step] = step
            self.thinking_timer = self.now
            self.typing_state = "THINKING"
        text = step["q"]
        # Prefetch the *next* step only when it does not depend on this answer
        # (machine-state beats). Prefetching an AI question here meant the model
        # was asked before the player had answered, so it always ran ~2 questions
        # behind and never saw the latest answer — the exact bug behind "the
        # answer isn't sent back to the AI".
        nxt_index = self.current_step + 1
        if nxt_index < len(self.active_script):
            nxt = self.active_script[nxt_index]
            if nxt.get("type") == "dynamic_pending" or config.AI_PREFETCH_LOOKAHEAD:
                self._prefetch_question(nxt_index)
        if self.typing_state == "THINKING":
            if self.now - self.thinking_timer > 0.9:
                self.typing_state = "TYPING"
                self.last_type_time = 0
        elif self.typing_state == "TYPING":
            interval = max(0.006, self.game_state.get("settings", {}).get("text_speed", 0.04))
            if self.now - self.last_type_time > interval:
                self.last_type_time = self.now
                self.typing_index += 1
                audio.play_type_sound()
                if self.typing_index >= len(text):
                    self.typing_state = "WAITING"
        elif self.typing_state == "WAITING":
            if self.run_count >= 3:
                self._run3_low_grade_glitch()

    def _run3_low_grade_glitch(self):
        """Run 3 never settles: a slow trickle of tiny corruptions/flickers."""
        if self.now < getattr(self, "_next_r3_glitch", 0.0):
            return
        self._next_r3_glitch = self.now + random.uniform(4.0, 9.0)
        if random.random() < 0.5:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.7)
        elif random.random() < 0.5:
            self.fx["rgb_split_until"] = max(self.fx["rgb_split_until"], self.now + 0.6)
        else:
            self.fx["flicker_until"] = max(self.fx["flicker_until"], self.now + 0.5)
        audio.play_glitch_sound()

    # --- drawing --------------------------------------------------------------
    def _fonts(self):
        """Cached fonts — pygame.font.Font() construction was the single
        biggest per-frame cost (3 objects × 4-6 calls/frame). Rebuild only
        when the window size or text-size setting changes."""
        key = (self.screen.get_width(), self.screen.get_height(),
               self.game_state.get("settings", {}).get("text_size", 1.0))
        if self._font_cache_key != key:
            self._font_cache = ui.get_scaled_fonts(self.game_state, key[0], key[1])
            self._font_cache_key = key
        return self._font_cache

    def _black_overlay(self, w, h):
        """Reusable full-screen black overlay (fades + exits)."""
        if self._black_overlay_key != (w, h):
            self._black_overlay_cache = pygame.Surface((w, h))
            self._black_overlay_cache.fill((0, 0, 0))
            self._black_overlay_key = (w, h)
        return self._black_overlay_cache

    def _draw(self):
        self.screen.fill(config.COLOR_BLACK)
        w, h = self.screen.get_size()
        self._touch_zones = []   # rebuilt below; hit-tested by _handle_touch

        if self.state in ("PLAYING", "EXITFADE"):
            # A violent shake fired alongside an aggressive line outranks the
            # ambient run-3 tremor, so the jolt is unmistakable.
            if self.fx.get("screen_shake_until", 0.0) > self.now:
                amp = int(self.fx.get("shake_amp", 16) or 16)
                self.shake_x = random.randint(-amp, amp)
                self.shake_y = random.randint(-amp, amp)
            elif self.run_count >= 3:
                self.shake_x, self.shake_y = random.randint(-8, 8), random.randint(-8, 8)
            else:
                self.shake_x, self.shake_y = 0, 0
        else:
            self.shake_x, self.shake_y = 0, 0

        # Background dressing goes down *before* the content so the text is
        # painted over it and stays crisp: rolling scan sweep, drifting ash,
        # breathing vignette, and the faint tape head line.
        vhs = self.game_state.get("settings", {}).get("vhs_intensity", 1.0)
        if vhs > 0:
            ui.draw_scan_sweep(self.screen, w, h, self.now)
        ui.draw_dust(self.screen, w, h, self.now)
        ui.apply_vignette(self.screen, w, h, self.now, strong=self.run_count >= 3)
        if self.state in ("PLAYING", "EXITFADE") and config.VHS_STATIC_LINE > 0:
            ui.draw_static_line(self.screen, w, h, self.now, config.VHS_STATIC_LINE)

        if self.state == "LOADING":
            self._draw_loading(w, h)
        elif self.state == "TITLE":
            self._draw_title(w, h)
        elif self.state == "SETTINGS":
            self._draw_settings(w, h)
        elif self.state == "ABOUT":
            self._draw_about(w, h)
        elif self.state == "HELP":
            self._draw_help(w, h)
        elif self.state == "LOGS":
            self._draw_logs(w, h)
        elif self.state in ("PLAYING", "EXITFADE"):
            self._draw_playing(w, h)

        self._draw_fade()
        if self.close_msg_until > self.now:
            font_small = self._fonts()[2]
            msg = os_layer.get_close_intercept_message(self.close_attempts).replace("\n", " ")
            surf = font_small.render(msg, True, config.COLOR_RED)
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h - 50))

        if self.badge_toast_id and self.badge_toast_at:
            still = ui.draw_badge_toast(self.screen, w, h, self.badge_toast_id, self.badge_toast_at,
                                        self._fonts()[1], self._fonts()[2], self.now)
            if not still:
                self.badge_toast_id = None

        # Foreground CRT finish, applied over every state: VHS scanlines, then
        # the full stack (tracking, static, tube curvature, phosphor mask).
        # Last, so the tube look reads as being in front of the content.
        ui.apply_vhs_effects(self.screen, w, h, self.game_state)
        if config.CRT_ENABLED and vhs > 0:
            ui.apply_vhs_pass(self.screen, w, h, self.now, intensity=vhs)

        pygame.display.flip()

    def _draw_loading(self, w, h):
        font_large, font_med, font_small = self._fonts()
        t = self.now - self.loading_start
        title = font_large.render(_TITLE, True, config.COLOR_RED)
        sub = font_med.render(_TITLE_SUB, True, (150, 0, 0))
        dots = "..." if t < 0.4 else ("...." if t < 0.8 else ".....")
        cal = font_small.render("CALIBRATING" + dots, True, (90, 90, 90))
        self.screen.blit(title, (w // 2 - title.get_width() // 2, h // 2 - 90))
        self.screen.blit(sub, (w // 2 - sub.get_width() // 2, h // 2 - 40))
        self.screen.blit(cal, (w // 2 - cal.get_width() // 2, h // 2 + 30))
        if t > 1.6:
            self.state = "TITLE"
            self._on_state_enter()

    def _draw_title(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.draw_starfield(self.screen, w, h, self.now, self.starfield)
        ui.draw_menu_decorations(self.screen, w, h, self.now, font_small)

        title_color = config.COLOR_WHITE
        if self.run_count >= 3:
            title_color = config.COLOR_RED if random.random() < 0.2 else config.COLOR_DARK_RED
            if random.random() < 0.05:
                ui.render_animated_wrapped_text(self.screen, "THIS IS YOUR LAST CHANCE", font_small,
                                                config.COLOR_RED, 20, 20, 300, self.now)

        title_lines = ["THE", "QUESTION", "GAME"]
        if self.run_count == 2:
            title_lines = ["....", "...", "Leave."]

        base_y = int(h * 0.10)
        # Occasional character scramble, straight from the website's title.
        scramble_on = (self.now % 7.0) < 0.45
        for i, line in enumerate(title_lines):
            sway_x = int(math.sin(self.now * 1.8 + i) * 6)
            sway_y = int(math.cos(self.now * 1.2 + i) * 3)
            draw_line = ui.scramble_text(line, self.now, 0.35) if scramble_on else line
            ui.draw_glowing_text(self.screen, draw_line, font_large,
                                 int(w * 0.08) + sway_x, base_y + i * 65 + sway_y,
                                 self.now, color=title_color, glow_color=(150, 0, 0))
            # Website hero: red/cyan split copies jittering over the base.
            ui.render_glitch_text(self.screen, draw_line, font_large,
                                  int(w * 0.08) + sway_x, base_y + i * 65 + sway_y,
                                  self.now, color=title_color)

        sub = font_med.render(_TITLE_SUB, True, (150, 0, 0))
        self.screen.blit(sub, (int(w * 0.08), base_y + 3 * 65 + 8))

        run_label = font_small.render("SESSION %d / 3" % self.run_count, True, (120, 40, 40))
        self.screen.blit(run_label, (int(w * 0.08), base_y + 3 * 65 + 8 + font_med.get_height() + 6))

        menu_y_start = h - 310 if len(self.menu_options) <= 5 else h - 348
        for i, option in enumerate(self.menu_options):
            sel = (i == self.selected_option)
            base_col = config.COLOR_GREEN if sel else config.COLOR_WHITE
            if self.run_count >= 3 and sel:
                base_col = config.COLOR_RED
            pulse = 0.75 + 0.25 * math.sin(self.now * 2.0 + i * 0.6)
            alpha = int(180 + 75 * pulse)
            if sel:
                p2 = 0.5 + 0.5 * math.sin(self.now * 4.0 + i * 0.6)
                base_col = tuple(min(255, int(c * (0.7 + 0.5 * p2))) for c in base_col)
            prefix = f"> {option}" if sel else f"  {option}"
            if sel:
                ui.render_glitch_text(self.screen, prefix, font_med,
                                      int(w * 0.08), menu_y_start + i * 45,
                                      self.now, color=base_col)
            else:
                surf = font_med.render(prefix, True, base_col)
                try:
                    surf.set_alpha(alpha)
                except Exception:
                    pass
                self.screen.blit(surf, (int(w * 0.08), menu_y_start + i * 45))
            self._touch_zone(int(w * 0.08) - 8, menu_y_start + i * 45,
                             int(w * 0.6) + 16, 44, "title", i)

        cred = font_small.render("NEPTUNE PRODUCTIONS (C)", True, (60, 60, 60))
        self.screen.blit(cred, (w // 2 - cred.get_width() // 2, h - 28))

        ver = font_small.render("v" + config.VERSION, True, (60, 60, 60))
        self.screen.blit(ver, (w - ver.get_width() - 12, h - ver.get_height() - 8))

    def _draw_heading(self, text, w, h, font_large, y_factor=0.08):
        """Section titles get the website's glow + red/cyan glitch split."""
        x, y = int(w * 0.08), int(h * y_factor)
        ui.draw_glowing_text(self.screen, text, font_large, x, y, self.now,
                             color=config.COLOR_RED, glow_color=(150, 0, 0))
        ui.render_glitch_text(self.screen, text, font_large, x, y, self.now,
                              color=config.COLOR_RED)

    def _draw_settings(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("SETTINGS", w, h, font_large)
        start_y = int(h * 0.22)
        for i, option in enumerate(self.settings_options):
            color = config.COLOR_WHITE if i == self.settings_selected else (110, 110, 110)
            prefix = "> " if i == self.settings_selected else "  "
            if option in config.SETTING_OPTIONS:
                value = config.SETTING_OPTIONS[option][self.settings_idx[option]]
                label = "%s%s   [%s]" % (prefix, option, value)
            else:
                label = prefix + option
            surf = font_med.render(label, True, color)
            self.screen.blit(surf, (int(w * 0.08), start_y + i * (font_med.get_linesize() + 12)))
            pitch = font_med.get_linesize() + 12
            self._touch_zone(int(w * 0.08) - 8, start_y + i * pitch,
                             int(w * 0.8) + 16, pitch - 2, "settings", i)
        hint = font_small.render("TAP: CHANGE    BACK: RETURN" if IS_ANDROID
                                 else "[ENTER] CHANGE    [ESC] BACK", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))

    def _draw_about(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("ABOUT", w, h, font_large, 0.06)
        options = ["About Info", "Credits", "< Back"]
        for i, option in enumerate(options):
            color = config.COLOR_WHITE if i == self.about_selected else (110, 110, 110)
            prefix = "> " if i == self.about_selected else "  "
            surf = font_small.render(prefix + option, True, color)
            y = int(h * 0.16) + i * (font_small.get_linesize() + 6)
            self.screen.blit(surf, (int(w * 0.08), y))
            self._touch_zone(int(w * 0.08) - 8, y, int(w * 0.6) + 16,
                             font_small.get_linesize() + 4, "about", i)

        if self.about_selected == 0:
            ui.render_text_block(self.screen, self.about_text, font_small, config.COLOR_WHITE,
                                 int(w * 0.08), int(h * 0.30), int(w * 0.8))
        elif self.about_selected == 1:
            ui.render_text_block(self.screen, CREDITS_TEXT, font_small, config.COLOR_WHITE,
                                 int(w * 0.08), int(h * 0.30), int(w * 0.8))

    def _draw_help(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("HELP", w, h, font_large)
        ui.render_text_block(self.screen, self.help_text, font_small, config.COLOR_WHITE,
                             int(w * 0.08), int(h * 0.22), int(w * 0.8))
        hint = font_small.render("TAP ANYWHERE TO GO BACK" if IS_ANDROID else "[ESC] BACK",
                                 True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))
        self._touch_zone(0, 0, w, h, "back")   # read-only screen: any tap leaves

    def _draw_logs(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("LOGS", w, h, font_large, 0.06)
        y = int(h * 0.16)
        for entry in LOGS_ENTRIES:
            for line in entry.split("\n"):
                if y > h - 40:
                    break
                color = (90, 90, 90) if line.startswith("ENTRY") else config.COLOR_WHITE
                ui.render_text_block(self.screen, line, font_small, color,
                                     int(w * 0.08), y, int(w * 0.8))
                y += ui.wrapped_line_count(line, font_small, color, int(w * 0.8)) * (font_small.get_linesize() + 4)
            y += 8
        hint = font_small.render("TAP ANYWHERE TO GO BACK" if IS_ANDROID else "[ESC] BACK",
                                 True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))
        self._touch_zone(0, 0, w, h, "back")   # read-only screen: any tap leaves

    def _draw_playing(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.update_webcam_surface()

        if self.pending_exit or self.current_step >= len(self.active_script):
            self.screen.blit(self._black_overlay(w, h), (0, 0))
            if self.pending_exit:
                # Make leaving explicit: the session is over, reopen for the next.
                font_small = self._fonts()[2]
                if self.run_count >= 3:
                    msg = "close this window. do not open it again."
                else:
                    msg = "close this window, then open it again for the next session."
                surf = font_small.render(msg, True, (120, 20, 20))
                self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h // 2 + 30))
                if self.now - self.exit_message_at > 2.0:
                    self.running = False
            elif self.current_step >= len(self.active_script):
                self.running = False
            return

        step = self.active_script[self.current_step]
        step_type = step.get("type", "choice")
        shake = (self.shake_x, self.shake_y) if self.state == "PLAYING" else (0, 0)

        base_x = int(w * 0.08) + shake[0]
        base_y = int(h * 0.12) + shake[1]
        max_width = int(w * 0.82)

        if step_type == "wait":
            text = step["q"]
            ui.render_text_block(self.screen, text, font_med, config.COLOR_WHITE,
                                 base_x, base_y, max_width, t=self.now, sway_amp=2,
                                 outline=config.TEXT_OUTLINE_COLOR)
            ui.draw_text(self.screen, ". . .", font_small, config.COLOR_DIM_RED,
                         base_x, h - int(h * 0.18))
        else:
            text = step["q"] or ""
            t_color = config.COLOR_RED if ("afraid" in text.lower() or self.run_count >= 3) else config.COLOR_WHITE
            if self.typing_state == "THINKING":
                dots = ["...", "....", ".....", "......"][int(self.now * 2) % 4]
                ui.draw_text(self.screen, dots, font_med, config.COLOR_DIM_RED, base_x, base_y)
            elif self.typing_state == "TYPING":
                partial = text[:self.typing_index]
                sway = self.game_state.get("settings", {}).get("sway_intensity", 1.0)
                sway_amp = int(2 + 4 * sway) if sway > 0 else 0
                ui.render_text_block(self.screen, partial, font_med, t_color,
                                     base_x, base_y, max_width,
                                     t=self.now if sway_amp else None, sway_amp=sway_amp,
                                     alpha_base=255, outline=config.TEXT_OUTLINE_COLOR)
                if partial and int(self.now * 2.4) % 2 == 0:
                    cx, cy = ui.wrap_cursor_pos(partial, font_med, base_x, base_y, max_width)
                    caret = font_med.render("_", True, t_color)
                    self.screen.blit(caret, (cx, cy))
            elif self.typing_state == "WAITING":
                sway = self.game_state.get("settings", {}).get("sway_intensity", 1.0)
                sway_amp = int(2 + 4 * sway) if sway > 0 else 0
                opts = step["opts"]
                opts_x = base_x
                line_h = font_med.get_linesize() + 4
                # Size the question by its *wrapped* height, not its hard-newline
                # count — a soft-wrapped question is several visual lines tall and
                # used to have the options drawn straight on top of it.
                q_lines = ui.wrapped_line_count(text, font_med, t_color, max_width)
                opts_y = base_y + q_lines * line_h + 34
                opts_gap = font_med.get_linesize() + 10
                # Long questions can wrap far enough to push options off-screen;
                # tighten the row gap (and lift the block) rather than overlap.
                bottom = h - 24
                if opts:
                    avail = bottom - opts_y
                    if len(opts) * opts_gap > avail:
                        opts_gap = max(font_med.get_linesize(), avail // len(opts))
                    if opts_y + len(opts) * opts_gap > bottom:
                        opts_y = max(base_y + q_lines * line_h + 12, bottom - len(opts) * opts_gap)
                # Readability wash: a calm patch of screen under the block, so
                # the question doesn't drown in static and scanlines.
                block_bottom = (opts_y + len(opts) * opts_gap) if opts else base_y + q_lines * line_h
                ui.draw_readability_panel(self.screen, base_x - 20, base_y - 16,
                                          max_width + 40, block_bottom - base_y + 30)
                # Website-style body text: red/cyan split + occasional jitter + sway.
                ui.render_glitch_block(self.screen, text, font_med, t_color,
                                       base_x, base_y, max_width,
                                       t=self.now, sway_amp=sway_amp,
                                       alpha_base=255)
                sel_color = config.COLOR_RED if self.run_count >= 3 else config.COLOR_GREEN
                for i, option in enumerate(opts):
                    if i == self.selected_answer:
                        p = 0.5 + 0.5 * math.sin(self.now * 4.0 + i)
                        color = tuple(min(255, int(c * (0.65 + 0.5 * p))) for c in sel_color)
                    else:
                        color = config.COLOR_WHITE
                    prefix = "> " if i == self.selected_answer else "  "
                    ui.draw_text(self.screen, prefix + option, font_med, color,
                                 opts_x, opts_y + i * opts_gap)
                    self._touch_zone(opts_x - 10, opts_y + i * opts_gap,
                                     max_width + 20, opts_gap - 2, "answer", i)

        # whisper reaction line
        if self.fx["whisper_text"] and self.fx["whisper_until"] > self.now:
            ui.draw_text(self.screen, self.fx["whisper_text"].replace("\n", " "),
                         font_small, (150, 0, 0), base_x, h - int(h * 0.28))

        # webcam feed
        if ui.webcam_active and ui.webcam_surface is not None:
            cw, chh = ui.webcam_surface.get_size()
            cam_x = w - cw - 20
            cam_y = h - chh - 40
            self.screen.blit(ui.webcam_surface, (cam_x, cam_y))
            label = font_small.render("CAMERA FEED — ACTIVE", True, config.COLOR_RED)
            self.screen.blit(label, (cam_x, cam_y + chh + 2))

        # picture scare
        if self.local_image is not None:
            iw, ih = self.local_image.get_size()
            self.screen.blit(self.local_image, (w - iw - 40, 40))

        # location card — it names where you are (Classic's location bite)
        loc = step.get("_location_card")
        if loc:
            ui.draw_location_card(self.screen, loc, w, h)

        # overlays
        if self.fx["corrupt_until"] > self.now:
            ui.apply_corruption(self.screen, w, h, self.now)
        if self.fx["flicker_until"] > self.now:
            ui.apply_flicker(self.screen, w, h)
        if self.fx["webcam_flash_until"] > self.now:
            ui.apply_shadow_static(self.screen, w, h, intensity=1.5)
        if self.fx["screen_tear_until"] > self.now:
            ui.apply_screen_tear(self.screen, w, h)
        if self.fx["rgb_split_until"] > self.now:
            amount = 4 + int(4 * math.sin(self.now * 21.0))
            ui.apply_rgb_split(self.screen, w, h, amount=max(2, amount))

        ui.apply_shadow_static(self.screen, w, h,
                               intensity=1.5 if self.run_count >= 3 else 1.0)

    # --- aggression helpers ----------------------------------------------------
    def _say_aggressive(self, text, duration=3.5, violent=True):
        """Show an aggressive line and shove the window at the same moment — the
        shout and the shake land together.

        Windows/macOS get a real, violent window shake. Elsewhere (Wayland
        forbids self-positioning) it degrades to an in-frame screen shake, so the
        jolt still reads."""
        self.fx["whisper_text"] = text
        self.fx["whisper_until"] = max(float(self.fx.get("whisper_until", 0.0)), self.now + duration)
        if violent:
            os_layer.shake_game_window(cycles=14, amplitude=40)
            self.fx["screen_shake_until"] = self.now + 0.7
            self.fx["shake_amp"] = max(int(self.fx.get("shake_amp", 0) or 0), 16)

    # --- close resistance -------------------------------------------------------
    def _resist_close(self):
        """Close attempts are refused and escalate into scares. Only a
        Task Manager force-kill ends the game."""
        rapid = self.now - self._last_close_try < 4.0 and self.close_attempts > 0
        self._last_close_try = self.now
        self.close_attempts += 1
        # Spamming the close button ranks it up faster than waiting between tries:
        # attempt 4 in a row already counts as a much higher threat level.
        self._close_burst = self._close_burst + 1 if rapid else 0
        n = self.close_attempts + self._close_burst
        self.close_msg_until = self.now + 2.5
        os_layer.attempt_close_with_warning()
        # Immediate and loud: a hissed line plus a violent shake on frame one.
        self._say_aggressive(random.choice(_ANGRY_CLOSE_LINES), duration=3.4, violent=True)
        self.fx["flicker_until"] = max(self.fx["flicker_until"], self.now + 0.45)
        audio.play_error_sound()
        # Windows-first bite: keep the window punched to the front, flash the
        # taskbar entry, and re-kill the system close item as they fight it.
        if os_layer.SYSTEM == "Windows":
            os_layer.set_window_topmost()
            if n >= 2:
                os_layer.flash_window()
            if n >= 4:
                os_layer.force_foreground()
        if n >= 2:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.9)
            os_layer.shake_game_window(cycles=8, amplitude=26)
        if n >= 3:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 1.7)
            audio.play_glitch_sound()
            os_layer.shake_game_window(cycles=10, amplitude=32)
        if n >= 4:
            os_layer.teleport_window_random()
            audio.play_static_scream()
            os_layer.shake_game_window(cycles=12, amplitude=38)
        if n >= 6:
            _sw, _sh = self.screen.get_size()   # the frame may have been resized
            os_layer.begin_mouse_move(random.randint(40, max(80, _sw - 40)),
                                      random.randint(40, max(80, _sh - 40)))
            os_layer.show_os_notification(config.APP_NAME, "You cannot leave.")
        if n >= 8 and n % 2 == 0:
            # Mid-game: more aggressive repositioning and a hard shake.
            os_layer.teleport_window_random()
            os_layer.shake_game_window(cycles=16, amplitude=44)
        if n >= 10 and n % 3 == 0:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 2.6)
            audio.play_static_scream()
        if n >= config.CLOSE_RESIST_MAX and n % 4 == 0:
            # "You live here now" phase: constant drift, no rest.
            os_layer.drift_window(8.0)

    # --- main loop ------------------------------------------------------------
    def run(self):
        os_layer.start_window_float()
        while self.running:
            self.clock.tick(config.FRAMERATE)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if config.BLOCK_CLOSE_ATTEMPTS:
                        self._resist_close()
                    else:
                        self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F4 and (event.mod & pygame.KMOD_ALT):
                        if config.BLOCK_CLOSE_ATTEMPTS:
                            self._resist_close()
                        else:
                            self.running = False
                    else:
                        self._handle_key(event.key)
                elif event.type == pygame.VIDEORESIZE and not config.WINDOW_LOCKED:
                    self._on_resize(event.w, event.h)
                elif event.type == pygame.MOUSEMOTION:
                    # Subtle hover parallax — the window leans toward the cursor
                    sw, sh = self.screen.get_size()
                    os_layer.set_hover_offset(event.pos[0], event.pos[1], sw, sh)
                elif event.type == pygame.FINGERDOWN and IS_ANDROID:
                    # Touch: FINGER* coordinates are normalized 0..1 over the
                    # window, so scale them to the current framebuffer.
                    w_px, h_px = self.screen.get_size()
                    self._handle_touch(event.x * w_px, event.y * h_px)

            os_layer.update_window_anim()
            os_layer.update_mouse_anim()
            os_layer.nudge_mouse_from_close()
            pic = ui.poll_picture_result()
            if pic is not None:
                self.local_image = pic

            self._update()
            self._draw()

        audio.stop_ambience()
        pygame.quit()


def main():
    Game().run()


if __name__ == "__main__":
    main()
