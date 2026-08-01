"""The Question Game Remastered — entry point.

Run with:  python -m TheQuestionGameRemastered.main
"""
import random
import threading
import time

import pygame

from . import ai_client
from . import audio
from . import config
from . import os_layer
from . import persistence
from . import scares
from . import script
from . import ui

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
_TITLE_SUB = "R E M A S T E R E D"


class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        self.screen = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H), pygame.RESIZABLE)
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
        self.wait_start_time = 0
        self.pending_exit = False
        self.exit_message_at = 0
        self.local_image = None
        self.captured_window_title = ""

        self.fx = {
            "flicker_until": 0.0,
            "corrupt_until": 0.0,
            "webcam_flash_until": 0.0,
            "whisper_text": None,
            "whisper_until": 0.0,
        }

        self.menu_options = ["PLAY", "SETTINGS", "HELP", "ABOUT", "EXIT"]
        self.selected_option = 0
        self.settings_options = ["Text Speed", "VHS Effects", "Text Sway", "Text Size", "Reset All Data", "< Back"]
        self.settings_selected = 0
        self.settings_idx = self._load_settings_idx()
        self.about_selected = 0
        self.credits_scroll_y = 0

        self.fade = {"active": False, "dir": "in", "start": 0, "dur": 0.25, "alpha": 255, "target": None}

        self.badge_toast_id = None
        self.badge_toast_at = 0
        self.close_msg_until = 0
        self.idle_tracker = {"focused": True, "lost_at": 0, "last_away": 0, "pending": False}
        self.shake_x, self.shake_y = 0, 0

        self._cheat_buffer = []
        self._cheat_last = 0
        self._CHEAT_CODE = [pygame.K_2, pygame.K_0, pygame.K_1, pygame.K_3]

        self.about_text = random.choice(ABOUT_VARIATIONS)
        self.help_text = random.choice(HELP_VARIATIONS)

        self.starfield = ui.build_starfield(config.WINDOW_W, config.WINDOW_H)
        self.clock = pygame.time.Clock()
        self.running = True

        audio.build_sound_cache()
        audio.start_ambience()
        os_layer.start_background_prefetch()
        self._startup_badges()
        self._begin_session()

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
        if size <= 0.8:
            idx["Text Size"] = 0
        elif size >= 1.2:
            idx["Text Size"] = 2
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
        self.current_step = 0
        self._reset_question_state()

    def _reset_question_state(self):
        self.typing_state = "THINKING"
        self.thinking_timer = self.now
        self.typing_index = 0
        self.selected_answer = 0
        self.question_start_time = self.now
        self.wait_start_time = 0

    def _apply_settings(self):
        s = self.game_state.setdefault("settings", {})
        s["text_speed"] = config.SETTING_MAPS["Text Speed"][self.settings_idx["Text Speed"]]
        s["vhs_intensity"] = config.SETTING_MAPS["VHS Effects"][self.settings_idx["VHS Effects"]]
        s["sway_intensity"] = config.SETTING_MAPS["Text Sway"][self.settings_idx["Text Sway"]]
        s["text_size"] = config.SETTING_MAPS["Text Size"][self.settings_idx["Text Size"]]
        persistence.save_game_state(self.game_state)

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
        if self.state == "LOGS":
            audio.start_logs_music()
        elif self.state == "PLAYING":
            self._begin_session()
        elif self.state == "TITLE":
            audio.stop_logs_music()

    def _draw_fade(self):
        if self.fade["active"] and self.fade["alpha"] > 0:
            overlay = pygame.Surface(self.screen.get_size())
            overlay.fill((0, 0, 0))
            overlay.set_alpha(max(0, min(255, int(self.fade["alpha"]))))
            self.screen.blit(overlay, (0, 0))

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
        answer = step["opts"][self.selected_answer]
        persistence.save_answer(self.game_state, step["_id"], answer, self.now - self.question_start_time)
        result = self.handle_step_action(step.get("action"), step)
        scare = step.get("scare")
        if scare:
            scares.apply_scare(self, scare)
        if result == "EXIT":
            self.pending_exit = True
            self.exit_message_at = self.now
            return
        self.current_step += 1
        self._reset_question_state()

    # --- input ---------------------------------------------------------------
    def _handle_key(self, key):
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
                os_layer.attempt_close_with_warning()
                self.close_msg_until = self.now + 2.5
        elif key == pygame.K_ESCAPE:
            os_layer.attempt_close_with_warning()
            self.close_msg_until = self.now + 2.5

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
            step = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                step = -1
            opts = step["opts"]
            self.selected_answer = (self.selected_answer + step) % len(opts)
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            audio.play_ui_select_sound()
            self._confirm_answer()

    # --- update ---------------------------------------------------------------
    def _update(self):
        self.now = time.time()
        self._update_fade()
        self._update_idle()
        if self.state in ("PLAYING", "EXITFADE") and not self.pending_exit:
            self._update_playing()

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
        text = step["q"]
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
            if self.game_state.get("settings", {}).get("vhs_intensity", 1.0) > 0:
                pass

    # --- drawing --------------------------------------------------------------
    def _fonts(self):
        return ui.get_scaled_fonts(self.game_state, *self.screen.get_size())

    def _draw(self):
        self.screen.fill(config.COLOR_BLACK)
        w, h = self.screen.get_size()

        if self.run_count >= 3 and self.state in ("PLAYING", "EXITFADE"):
            self.shake_x, self.shake_y = random.randint(-8, 8), random.randint(-8, 8)
        else:
            self.shake_x, self.shake_y = 0, 0

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
            font_med, font_small = self._fonts()[1], self._fonts()[2]
            msg = os_layer.get_close_intercept_message()
            surf = font_small.render(msg, True, config.COLOR_RED)
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h - 50))

        if self.badge_toast_id and self.badge_toast_at:
            still = ui.draw_badge_toast(self.screen, w, h, self.badge_toast_id, self.badge_toast_at,
                                        self._fonts()[1], self._fonts()[2], self.now)
            if not still:
                self.badge_toast_id = None

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

    def _draw_title(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.draw_starfield(self.screen, w, h, self.now, self.starfield)
        ui.draw_menu_decorations(self.screen, w, h, self.now, font_small)

        title = font_large.render(_TITLE, True, config.COLOR_RED)
        sub = font_med.render(_TITLE_SUB, True, (150, 0, 0))
        self.screen.blit(title, (int(w * 0.08), int(h * 0.10)))
        self.screen.blit(sub, (int(w * 0.08), int(h * 0.10) + font_large.get_height() + 6))

        run_label = font_small.render("SESSION %d / 3" % self.run_count, True, (120, 40, 40))
        self.screen.blit(run_label, (int(w * 0.08), int(h * 0.28)))

        start_y = int(h * 0.36)
        for i, option in enumerate(self.menu_options):
            color = config.COLOR_WHITE if i == self.selected_option else (110, 110, 110)
            if i == self.selected_option:
                prefix = "> "
            else:
                prefix = "  "
            surf = font_med.render(prefix + option, True, color)
            self.screen.blit(surf, (int(w * 0.08), start_y + i * (font_med.get_linesize() + 10)))

        hint = font_small.render("[TAB/UP/DOWN] NAVIGATE    [ENTER] SELECT", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 70))
        note = font_small.render("YOUR ANSWERS ARE REMEMBERED", True, (100, 0, 0))
        self.screen.blit(note, (int(w * 0.08), h - 46))
        ver = font_small.render("v" + config.VERSION, True, (60, 60, 60))
        self.screen.blit(ver, (w - ver.get_width() - 12, h - ver.get_height() - 8))

    def _draw_settings(self, w, h):
        font_large, font_med, font_small = self._fonts()
        title = font_large.render("SETTINGS", True, config.COLOR_RED)
        self.screen.blit(title, (int(w * 0.08), int(h * 0.08)))
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
        hint = font_small.render("[ENTER] CHANGE    [ESC] BACK", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))

    def _draw_about(self, w, h):
        font_large, font_med, font_small = self._fonts()
        title = font_large.render("ABOUT", True, config.COLOR_RED)
        self.screen.blit(title, (int(w * 0.08), int(h * 0.06)))
        options = ["About Info", "Credits", "< Back"]
        for i, option in enumerate(options):
            color = config.COLOR_WHITE if i == self.about_selected else (110, 110, 110)
            prefix = "> " if i == self.about_selected else "  "
            surf = font_small.render(prefix + option, True, color)
            self.screen.blit(surf, (int(w * 0.08), int(h * 0.16) + i * (font_small.get_linesize() + 6)))

        if self.about_selected == 0:
            ui.render_wrapped_text(self.screen, self.about_text, font_small, config.COLOR_WHITE,
                                   int(w * 0.08), int(h * 0.30), int(w * 0.8))
        elif self.about_selected == 1:
            ui.render_wrapped_text(self.screen, CREDITS_TEXT, font_small, config.COLOR_WHITE,
                                   int(w * 0.08), int(h * 0.30), int(w * 0.8))

    def _draw_help(self, w, h):
        font_large, font_med, font_small = self._fonts()
        title = font_large.render("HELP", True, config.COLOR_RED)
        self.screen.blit(title, (int(w * 0.08), int(h * 0.08)))
        ui.render_wrapped_text(self.screen, self.help_text, font_small, config.COLOR_WHITE,
                               int(w * 0.08), int(h * 0.22), int(w * 0.8))
        hint = font_small.render("[ESC] BACK", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))

    def _draw_logs(self, w, h):
        font_large, font_med, font_small = self._fonts()
        title = font_large.render("LOGS", True, config.COLOR_RED)
        self.screen.blit(title, (int(w * 0.08), int(h * 0.06)))
        y = int(h * 0.16)
        for entry in LOGS_ENTRIES:
            lines = entry.split("\n")
            for line in lines:
                if y > h - 40:
                    break
                color = (90, 90, 90) if line.startswith("ENTRY") else config.COLOR_WHITE
                surf = font_small.render(line, True, color)
                self.screen.blit(surf, (int(w * 0.08), y))
                y += font_small.get_linesize() + 4
            y += 8
        hint = font_small.render("[ESC] BACK", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))

    def _draw_playing(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.update_webcam_surface()

        if self.pending_exit or self.current_step >= len(self.active_script):
            overlay = pygame.Surface((w, h))
            overlay.fill((0, 0, 0))
            self.screen.blit(overlay, (0, 0))
            if self.pending_exit and self.now - self.exit_message_at > 2.0:
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
            ui.render_animated_wrapped_text(self.screen, text, font_med, config.COLOR_WHITE,
                                            base_x, base_y, max_width, self.now)
            prompt = font_small.render(". . .", True, config.COLOR_DIM_RED)
            self.screen.blit(prompt, (base_x, h - int(h * 0.18)))
        else:
            text = step["q"]
            if self.typing_state == "THINKING":
                dots = ["...", "....", ".....", "......"][int(self.now * 2) % 4]
                surf = font_med.render(dots, True, config.COLOR_DIM_RED)
                self.screen.blit(surf, (base_x, base_y))
            elif self.typing_state == "TYPING":
                partial = text[:self.typing_index]
                ui.render_wrapped_text(self.screen, partial, font_med, config.COLOR_WHITE,
                                       base_x, base_y, max_width)
            elif self.typing_state == "WAITING":
                ui.render_wrapped_text(self.screen, text, font_med, config.COLOR_WHITE,
                                       base_x, base_y, max_width)
                opts = step["opts"]
                opts_x = base_x
                opts_y = base_y + len(text.split("\n")) * (font_med.get_linesize() + 4) + 40
                for i, option in enumerate(opts):
                    color = config.COLOR_GREEN if i == self.selected_answer else (110, 110, 110)
                    prefix = "> " if i == self.selected_answer else "  "
                    surf = font_med.render(prefix + option, True, color)
                    self.screen.blit(surf, (opts_x, opts_y + i * (font_med.get_linesize() + 10)))

        # whisper reaction line
        if self.fx["whisper_text"] and self.fx["whisper_until"] > self.now:
            surf = font_small.render(self.fx["whisper_text"], True, (150, 0, 0))
            self.screen.blit(surf, (base_x, h - int(h * 0.28)))

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

        # overlays
        if self.fx["corrupt_until"] > self.now:
            ui.apply_corruption(self.screen, w, h, self.now)
        if self.fx["flicker_until"] > self.now:
            ui.apply_flicker(self.screen, w, h)
        if self.fx["webcam_flash_until"] > self.now:
            ui.apply_shadow_static(self.screen, w, h, intensity=1.5)

        ui.apply_vhs_effects(self.screen, w, h, self.game_state)
        ui.apply_shadow_static(self.screen, w, h,
                               intensity=1.5 if self.run_count >= 3 else 1.0)

    # --- main loop ------------------------------------------------------------
    def run(self):
        while self.running:
            dt = self.clock.tick(config.FRAMERATE) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    os_layer.attempt_close_with_warning()
                    self.close_msg_until = self.now + 2.5
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F4 and (event.mod & pygame.KMOD_ALT):
                        os_layer.attempt_close_with_warning()
                        self.close_msg_until = self.now + 2.5
                    else:
                        self._handle_key(event.key)
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

            os_layer.update_window_anim()
            os_layer.update_mouse_anim()
            os_layer.nudge_mouse_from_close()
            ui.poll_picture_result()

            if self.state == "PLAYING":
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
