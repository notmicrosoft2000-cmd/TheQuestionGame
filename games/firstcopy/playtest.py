"""Headless regression driver for The Simpler Times.

Runs the real Game object against a dummy SDL surface and plays through
all four endings, asserting on the state each one produces. Not shipped with
the game; run from this folder with:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python playtest.py

Exits 0 on full pass, 1 on the first failure.
"""
import os
import sys

import pygame

from TheFirstCopy import config, geo, persistence, script, web
from TheFirstCopy.dos import DosFs, DosShell
from TheFirstCopy.main import (ABOUT, BOOT, ENDING, FAIR, FILES, HELP, Game,
                               SETTINGS, SHELL, TITLE)
from TheFirstCopy.scares import ScareDirector

_TEXT_SPEED = 0.005


def _key(ch):
    if ch == " ":
        return pygame.K_SPACE
    if ch == ".":
        return pygame.K_PERIOD
    if ch == "/":
        return pygame.K_SLASH
    if ch == "-":
        return pygame.K_MINUS
    if ch == ":":
        return pygame.K_COLON
    if ch.isdigit():
        return getattr(pygame, "K_%s" % ch)
    return getattr(pygame, "K_%s" % ch.upper(), pygame.K_a)


def K(key, text=None):
    return pygame.event.Event(
        pygame.KEYDOWN, key=key,
        unicode=text or ("\r" if key in (pygame.K_RETURN, pygame.K_KP_ENTER) else ""))


def T(game, text):
    for ch in text:
        game.handle(K(_key(ch), ch))


def frames(game, n, dt=0.5):
    for _ in range(int(n)):
        game.update(dt)
        game.draw()


def select(game, i):
    """Select the i-th visible hotspot (0-based) and activate it."""
    for _ in range(i):
        game.handle(K(pygame.K_DOWN))
    game.handle(K(pygame.K_RETURN))


def shell_cmd(game, cmd, read=False):
    if game.submode != SHELL:
        game.handle(K(pygame.K_ESCAPE))
    T(game, cmd)
    game.handle(K(pygame.K_RETURN))
    frames(game, 40 if read else 3, 0.1)


class _Audio:
    ok = False

    def play(self, *a, **k):
        pass

    def start_loop(self, *a, **k):
        pass

    def stop_loop(self, *a, **k):
        pass

    def stop_all_loops(self, *a, **k):
        pass

    def set_loop_volume(self, *a, **k):
        pass


def _screen():
    pygame.init()
    return pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))


def new_game(screen):
    state = persistence.default_state()
    state["settings"]["text_speed"] = _TEXT_SPEED
    return Game(screen, state, _Audio())


def drain_fakes(game, n=300, dt=0.05):
    """Let any fake 'messes with your machine' takeover play out.

    Presence-based fake events are queued during update(), so always run a
    few frames first to flush them, then play out any modal takeover."""
    frames(game, 8, dt)
    if game.fake is not None:
        frames(game, n, dt)


def test_geo_location(screen):
    """Background geolocation: injected cache lands in state, the entity
    mentions where you are, and the shell's WHOAMI reports the address."""
    with geo._STARTED_LOCK:
        geo._STARTED = True               # stop any real background thread
    with geo._LOCK:
        geo._CACHE["value"] = ("Testville", "Testland")

    game = new_game(screen)
    frames(game, 3)
    loc = game.state.get("location")
    assert loc and loc.get("city") == "Testville", loc
    assert loc.get("country") == "Testland", loc
    assert game.location_line() == "Testville, Testland"
    print("geo location -> state OK")

    s = ScareDirector(game.state)
    game.state["presence"] = 14
    for _ in range(3):
        s.update(0.016, False, {"part": "files"})
    assert any(e["type"] == "dial" for e in s.events), s.events
    dial = next(e for e in s.events if e["type"] == "dial")
    assert "Testville" in dial["text"], dial["text"]
    assert any(e["type"] == "whisper" and "Testville" in e["text"]
               for e in s.events), s.events
    print("scare director location hooks OK")

    shell = DosShell(DosFs(script.build_fs, game.state), game.state)
    shell._whoami()
    out = " ".join(t for t, _ in shell.output)
    assert "Testville" in out, out
    print("shell WHOAMI location OK")


def test_web(screen):
    """At enough presence the entity opens a placeholder page in your
    browser. Headless: the connecting overlay still plays, but the real
    browser is never launched."""
    web.set_enabled(False)
    game = new_game(screen)
    s = game.scare
    game.state["presence"] = 16
    for _ in range(3):
        s.update(0.016, False, {"part": "files"})
    kinds = [e["type"] for e in s.events]
    assert "web" in kinds, kinds
    ev = next(e for e in s.events if e["type"] == "web")
    game._consume_scare_event(ev)
    assert game.fake is not None and game.fake["kind"] == "web"
    frames(game, 300, 0.05)                       # play the takeover out
    assert game.fake is None
    assert "index" in web.opened_sites(), web.opened_sites()
    print("web takeover + open_site (headless, no browser) OK")


def test_menu(screen):
    game = new_game(screen)
    assert game.mode == TITLE

    # the fixed window is deliberately non-fullscreenable and non-resizable
    ww, wh = config.window_size()
    assert ww >= config.WINDOW_W and wh >= config.WINDOW_H, (ww, wh)
    assert "fullscreen" not in config.DEFAULT_SETTINGS

    # navigate to Settings and change values
    game.handle(K(pygame.K_DOWN))              # -> Settings
    game.handle(K(pygame.K_RETURN))
    assert game.mode == SETTINGS, game.mode
    game.handle(K(pygame.K_RIGHT))             # Text Speed FAST -> NORMAL
    assert game.state["settings"]["text_speed"] != _TEXT_SPEED
    game.handle(K(pygame.K_DOWN))              # Text Size
    game.handle(K(pygame.K_DOWN))              # VHS Static
    game.handle(K(pygame.K_DOWN))              # Reset All Data
    game.handle(K(pygame.K_ESCAPE))
    assert game.mode == TITLE

    # Help (menu_sel is still "Settings" (1), so one DOWN reaches Help)
    game.handle(K(pygame.K_DOWN))
    game.handle(K(pygame.K_RETURN))
    assert game.mode == HELP, game.mode
    game.handle(K(pygame.K_RETURN))
    assert game.mode == TITLE

    # About (menu_sel is now "Help" (2), one DOWN reaches About)
    game.handle(K(pygame.K_DOWN))
    game.handle(K(pygame.K_RETURN))
    assert game.mode == ABOUT, game.mode
    game.handle(K(pygame.K_RETURN))
    assert game.mode == TITLE

    # exit (menu_sel is now "About" (3), one DOWN reaches exit)
    game.handle(K(pygame.K_DOWN))
    assert game.handle(K(pygame.K_RETURN)) == "quit"
    print("menu / settings / help / about / exit OK")


def run_scene_flow(game):
    if game.mode == TITLE:
        game.handle(K(pygame.K_RETURN))
    assert game.mode == FAIR, game.mode
    frames(game, 3)

    game.handle(K(pygame.K_RETURN))            # GO IN
    assert game.eng.current == "main_floor"
    frames(game, 2)
    game.handle(K(pygame.K_RETURN))            # GEMINI COMPUTER SALES
    assert game.eng.current == "gemini_stall"
    frames(game, 2)
    select(game, 1)                            # TAKE THE UNLABELED DISK
    assert game.state["items"] == ["floppy"], game.state["items"]
    frames(game, 2)
    select(game, 2)                            # BACK TO THE FLOOR
    assert game.eng.current == "main_floor"
    frames(game, 2)

    # side scenes (new content): payphone dials itself, restroom
    select(game, 5)                            # THE PAYPHONE
    assert game.eng.current == "phone_booth", game.eng.current
    frames(game, 2)
    select(game, 0)                            # DIAL 555-0134
    assert game.state.get("bbs_dialed")
    assert game.fake is not None and game.fake["kind"] == "dial"
    drain_fakes(game)                          # play out the dial takeover
    game.handle(K(pygame.K_RETURN))            # dismiss the message
    frames(game, 2)
    select(game, 2)                            # BACK TO THE FLOOR
    assert game.eng.current == "main_floor"
    frames(game, 2)
    select(game, 6)                            # THE RESTROOM
    assert game.eng.current == "bathroom", game.eng.current
    frames(game, 2)
    game.handle(K(pygame.K_RETURN))            # THE MIRROR
    frames(game, 2)
    game.handle(K(pygame.K_RETURN))            # dismiss
    frames(game, 2)
    select(game, 2)                            # BACK TO THE FLOOR
    assert game.eng.current == "main_floor"
    frames(game, 2)

    select(game, 4)                            # THE EXIT
    assert game.eng.current == "closing_floor"
    frames(game, 2)
    game.handle(K(pygame.K_RETURN))            # STAY PAST CLOSING
    assert game.state.get("stayed_late")
    frames(game, 2)
    select(game, 1)                            # FOLLOW THE CROWD OUT
    assert game.eng.current == "parking_out"
    frames(game, 2)
    select(game, 2)                            # GO HOME
    assert game.eng.current == "home_desk"
    frames(game, 2)
    game.handle(K(pygame.K_RETURN))            # THE COMPUTER -> BOOT
    assert game.mode == BOOT, game.mode
    frames(game, 300, 0.1)                     # let boot finish
    assert game.mode == FILES, game.mode
    print("scene flow -> FILES OK")


def answer_questions(game):
    answered = 0
    while game.q_cur is not None:
        q = next(q for q in script.QUESTIONS if q["id"] == game.q_cur)
        answer = q["choices"][0] if q["kind"] == "choice" else "ONE WORD"
        T(game, answer)
        game.handle(K(pygame.K_RETURN))
        answered += 1
        assert answered <= len(script.QUESTIONS) + 1, "questions did not finish"
        drain_fakes(game)   # presence milestones fire fake takeovers mid-questions
    print("all questions answered OK")


def read_fragile_docs(game):
    for cmd in ["cd THEM", "type WHO.001", "type US.001", "type WAKE.001",
                "cd ..", "cd WAITING", "type DOOR.TXT", "type STALL.001",
                "type KEYS.001", "cd .."]:
        shell_cmd(game, cmd, read=True)


def main():
    for path in (config.STATE_FILE, config.BADGES_FILE,
                 config.STATE_FILE + ".tmp", config.BADGES_FILE + ".tmp"):
        try:
            os.remove(path)
        except OSError:
            pass
    screen = _screen()

    web.set_enabled(False)          # never launch a browser in tests

    # --- menu, settings, help, about, exit ---
    test_menu(screen)

    # --- quiet geolocation ---
    test_geo_location(screen)

    # --- website opening (headless) ---
    test_web(screen)

    # --- the_first ---
    game = new_game(screen)
    run_scene_flow(game)
    shell_cmd(game, "DIR")
    shell_cmd(game, "RUN THEGAME.EXE")
    answer_questions(game)
    shell_cmd(game, "EXIT")
    select(game, 1)                            # THE DOOR -> CHAIR
    select(game, 1)                            # KEEP WALKING
    select(game, 0)                            # TAKE THE CHAIR
    assert game.mode == ENDING, game.mode
    assert game.ending_id == "the_first", game.ending_id
    frames(game, 300, 0.1)
    for b in ("fairgoer", "first_subject", "night_owl", "not_alone", "pioneer"):
        assert b in game._earned, (b, sorted(game._earned))
    print("ending the_first OK, ending_id = %s" % game.ending_id)
    print("badges earned:", sorted(game._earned))

    # --- restart keeps state fresh ---
    result = game.handle(K(pygame.K_r))
    assert result == "again"
    game = new_game(screen)
    persistence.reset_state(game.state)
    assert game.state["answers"] == {}, "fresh state expected"
    assert game.mode == TITLE
    game.handle(K(pygame.K_RETURN))            # begin
    assert game.mode == FAIR
    print("restart -> fresh fair OK")

    # --- secret 2013 ending ---
    run_scene_flow(game)
    shell_cmd(game, "2013")
    shell_cmd(game, "CD SECRET")
    shell_cmd(game, "TYPE FIRST.KNOW", read=True)
    shell_cmd(game, "CD ..")
    shell_cmd(game, "RUN THEGAME.EXE")
    answer_questions(game)
    shell_cmd(game, "EXIT")
    select(game, 1)                            # THE DOOR -> CHAIR
    select(game, 1)                            # KEEP WALKING
    select(game, 3)                            # RELEASE IT
    assert game.mode == ENDING, game.mode
    assert game.ending_id == "2013", game.ending_id
    frames(game, 300, 0.1)
    assert "2013" in game._earned
    print("secret 2013 ending OK")

    # --- archivist: archive fragile docs before answering ---
    game = new_game(screen)
    persistence.reset_state(game.state)
    game.handle(K(pygame.K_RETURN))
    run_scene_flow(game)
    read_fragile_docs(game)
    assert script.archived_all(game.state), game.state["archived"]
    assert "archivist" in game._earned
    shell_cmd(game, "RUN THEGAME.EXE")
    answer_questions(game)
    shell_cmd(game, "EXIT")
    select(game, 1)                            # THE DOOR -> CHAIR
    select(game, 1)                            # KEEP WALKING
    select(game, 1)                            # SEAL THE DISK
    assert game.mode == ENDING, game.mode
    assert game.ending_id == "the_archivist", game.ending_id
    frames(game, 300, 0.1)
    assert "curator" in game._earned
    print("archivist ending + curator badge OK")

    # --- waiting: walk away ---
    game = new_game(screen)
    persistence.reset_state(game.state)
    game.handle(K(pygame.K_RETURN))
    run_scene_flow(game)
    shell_cmd(game, "RUN THEGAME.EXE")
    answer_questions(game)
    shell_cmd(game, "EXIT")
    select(game, 1)                            # THE DOOR -> CHAIR
    select(game, 1)                            # KEEP WALKING
    select(game, 2)                            # WALK AWAY
    assert game.mode == ENDING, game.mode
    assert game.ending_id == "the_waiting", game.ending_id
    frames(game, 300, 0.1)
    print("waiting ending OK")

    print("FULL PLAYTHROUGH OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
