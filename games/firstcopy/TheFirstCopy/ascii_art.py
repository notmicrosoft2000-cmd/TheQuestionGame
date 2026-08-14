"""ASCII-art scene illustrations for The Simpler Times.

Each scene has a small monochrome block that renders above the description
like an old ANSI/ASCII splash. Lines prefixed with "@@" render in RED (the
entity's accent); everything else renders amber.

Width target: ~48 chars. Height target: <= 13 lines.
"""
from . import config, ui

SCENE_ART = {
    "fair_entrance": [
        "          ____  ____  ____  ____  ____  ____",
        "         |    ||    ||    ||    ||    ||    |",
        "   ______|____||____||____||____||____||____|_______",
        "  /  SOUTH COAST COMPUTER FEST '93                 /",
        " |   \"THE FUTURE IS PERSONAL COMPUTING\"           |",
        "  \\_______________________________________________/",
        "      |  ___  ___  ___  ___  ___  ___  ___  |",
        "      |  |   ||   ||   ||   ||   ||   ||   | |",
        "      |__|___||___||___||___||___||___||___|_|",
        "            \\           \\ /           /",
        "             \\_________/   \\_________/",
        "",
        "    @@@@  FIVE DOLLARS.  THE AIR IS TONER. @@@@",
    ],

    "main_floor": [
        "  .___     .___     .___     .___     .___     .___",
        "  |   |    |   |    |   |    |   |    |   |    |   |",
        "  |___|    |___|    |___|    |___|    |___|    |___|",
        "   GEMINI   MULTI    SHAREW    BBS     PRINTER   TAPE",
        "  ._._.    ._._.    ._._.    ._._.    ._._.    ._._.",
        "  |   |    |   |    |   |    |   |    |   |    |   |",
        "  |_._|    |_._|    |_._|    |_._|    |_._|    |_._|",
        "",
        "    the hum of a hundred fans in a wall of beige.",
        "    every screen asks the same thing: who are you?",
        "    @@@@ no one looks up. the screens blink first. @@@@",
    ],

    "gemini_stall": [
        "        ______________________________",
        "       /  G E M I N I  C O M P U T E R \\",
        "      |   FREE SOFTWARE -- TAKE ONE     |",
        "       \\______________________________/",
        "            [ ] [ ]    [ ] [ ] [ ]",
        "           [ ][ ][ ]  [ ][ ][ ]  ",
        "     ______[[[[[[[ ]]]]]]]______",
        "    /    NO SALESMAN TODAY     /\\",
        "   /__________________________/  \\",
        "   |                            |",
        "   \\  L. CARVER -- THE CHAIR    /",
        "    \\  IS EMPTY. THE COFFEE    /",
        "     \\________________________/",
    ],

    "closing_floor": [
        "   __________________  ______________________",
        "  |                  ||                      |",
        "  |   __             ||              __      |",
        "  |  |  |    ~~~     ||     ~~~     |  |     |",
        "  |  |__|            ||              |__|     |",
        "  |__________________||______________________|",
        "   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .",
        "    \\/   \\/   \\/   \\/   \\/   \\/   \\/   \\/",
        "",
        "    the tubes buzz half-lit. a cart comes around.",
        "    @@@@ STAY. IT WANTS TO SEE THE DARK WITH YOU. @@@@",
    ],

    "parking_out": [
        "                  __",
        "              ___|  |___",
        "             |  o     o  |",
        "             |___________|",
        "                  ||",
        "                  ||",
        "     _|_______|______________________",
        "    |   |   |  ____      ____       |",
        "    |   |   | |    |    |    |      |",
        "    |   |   | |____|    |____|      |",
        "    |   |   |       (the wagon)     |",
        "    |___|___|_______________________|",
        "    @@@@ the streetlight buzzes like a monitor. @@@@",
    ],

    "home_desk": [
        "   ___________________________________________",
        "  |      __ __ __ __ __ __      [ window ]     |",
        "  |     |__||__||__||__||__|     night out      |",
        "  |   ______________________    ________       |",
        "  |  |                      |  |        |      |",
        "  |  |  AMBER. IT IS AMBER. |  | 486DX/ |      |",
        "  |  |  YOU DID NOT SET IT  |  | 33     |      |",
        "  |  |______________________|  |________|      |",
        "  |      ___        A:\\> _  ___________        |",
        "  |     |   |   (a disk, no label, still       |",
        "  |     |___|    warm in your hand)            |",
        "  |___________________________________________|",
        "    @@@@ the drive is warm. it was not, a moment ago. @@@@",
    ],

    "disk_room": [
        "              ______________________",
        "             |                      |",
        "             |  A:\\> _              |",
        "             |                      |",
        "             |  @@ ? @@             |",
        "             |                      |",
        "             |  IT IS READING YOU.  |",
        "             |______________________|",
        "                   |       |",
        "                   |_______|",
        "                  /         \\",
        "                 /  A: 1.44  \\",
        "                /_____________\\",
        "    @@@@ the A: light is on. it has been on all night. @@@@",
    ],

    "corridor": [
        "   ______________________________________________",
        "  |                                              |",
        "  |   THE ANSWERS SCROLL. SOME OF IT IS WRONG.   |",
        "  |                                              |",
        "  |                  ____                        |",
        "  |                 |    |                       |",
        "  |                 |    |                       |",
        "  |                 |____|                       |",
        "  |                  |  |                        |",
        "  |                  |  |                        |",
        "  |                  |  |                        |",
        "  |  @@@@ IT KEEPS WHAT YOU GIVE IT. @@@@        |",
        "  |______________________________________________|",
    ],

    "chair_room": [
        "           ______________________________",
        "          |                              |",
        "          |                              |",
        "          |            ____              |",
        "          |           |    |             |",
        "          |           |____|             |",
        "          |            |  |              |",
        "          |            |  |              |",
        "          |            |  |              |",
        "          |           /____\\             |",
        "          |                              |",
        "          |   @@@@ it is just a chair. @@@@  |",
        "          |______________________________|",
    ],

    "phone_booth": [
        "           ______________________",
        "          |  __________________  |",
        "          | |   _  _  _  _      | |",
        "          | |  |_||_||_||_|     | |",
        "          | | 555-0134 2400     | |",
        "          | |   (the card is    | |",
        "          | |    still warm)    | |",
        "          | |__________________| |",
        "          |______________________|",
        "              /            \\",
        "             /   the booth  \\",
        "            /_______________\\",
        "    @@@@ UNION COUNTY BBS. SYSOP WANTED. @@@@",
    ],

    "bathroom": [
        "   ______________________________________",
        "  |      |      |      |      |     |     |",
        "  |      |  __  |      |  __  |     |     |",
        "  |      | |  | |      | |  | |     |     |",
        "  |      | |__| |      | |__| |     |     |",
        "  |      |  __  |      |  __  |  @@ @@    |",
        "  |      | |  | |      | |  | |   @@ @@   |",
        "  |______|_|__|_|______|_|__|_|___________|",
        "",
        "    the tiles are wet. the room is not.",
        "    @@@@ on the mirror: IT WAS NOT THE COMPUTER. @@@@",
    ],
}


def max_width(scene_id, font):
    """Pixel width of the widest line, for layout."""
    lines = SCENE_ART.get(scene_id) or []
    if not lines:
        return 0
    best = 0
    for ln in lines:
        if ln.startswith("@@"):
            ln = ln[2:]
        best = max(best, font.size(ln)[0])
    return best


def draw(screen, scene_id, x, y, size=12, base=None, hot=None):
    """Render a scene's ASCII art at (x, y). Returns the block height."""
    lines = SCENE_ART.get(scene_id)
    if not lines:
        return 0
    base = base or config.TEXT
    hot = hot or config.RED
    font = ui.get_font(size)
    lh = font.get_linesize()
    for i, ln in enumerate(lines):
        color = base
        if ln.startswith("@@"):
            ln = ln[2:]
            color = hot
        surf = font.render(ln, True, color)
        screen.blit(surf, (x, y + i * lh))
    return len(lines) * lh
