import sys


def _dispatch():
    """The game binary can also run as the desktop-eye overlay.

    A second SDL window cannot live inside the game process (pygame owns one
    display), so the game re-executes itself with ``--eye-overlay`` and the
    overlay takes over instead of starting the game.
    """
    if "--eye-overlay" in sys.argv:
        from TheQuestionGameRemastered.eye_overlay import main as overlay_main
        return overlay_main()
    from TheQuestionGameRemastered.main import main
    return main()


if __name__ == "__main__":
    sys.exit(_dispatch() or 0)
