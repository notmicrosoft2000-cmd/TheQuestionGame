import os
import sys
import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from TheFirstCopy import persistence, ui, script
from TheFirstCopy.main import Game, TITLE, SETTINGS, FAIR, FILES, CHAIR, QUESTION, ENDING


class _NoAudio:
    def play(self, *a, **k): pass
    def start_loop(self, *a, **k): pass
    def stop_loop(self, *a, **k): pass
    def stop_all_loops(self, *a, **k): pass
    def set_loop_volume(self, *a, **k): pass
    ok = False


def main():
    pygame.init()
    state = persistence.default_state()
    screen = pygame.display.set_mode((800, 600))
    ui.clear_font_cache()
    game = Game(screen, state, _NoAudio())
    out_dir = sys.argv[1]

    def snap(name, frames=12, after=None):
        for _ in range(frames):
            game.update(1.0 / 60.0)
        if after:
            after()
            game.update(1.0 / 60.0)
        game.draw()
        pygame.image.save(screen, os.path.join(out_dir, name))
        print("saved", name)

    # 1. title
    game.switch(TITLE)
    snap("shot-title.png", 90)

    # 2. settings
    game.switch(SETTINGS)
    snap("shot-settings.png", 20)

    # 3. fair entrance scene
    game.switch(FAIR)
    snap("shot-fair.png", 40)

    # 4. files desk
    game.switch(FILES)
    snap("shot-files.png", 40)

    # 5. question panel
    game.switch(FILES)
    qids = [q["id"] for q in script.QUESTIONS[:3]]
    game.start_questions(qids)
    snap("shot-question.png", 60)

    # 6. ending
    game.switch(ENDING)
    snap("shot-ending.png", 90)

    pygame.quit()
    print("DONE")


if __name__ == "__main__":
    main()
