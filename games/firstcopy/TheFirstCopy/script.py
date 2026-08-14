"""The Simpler Times — all story content.

Period: August 14, 1993. South Coast Computer Fest. A 3.5" floppy disk
with no label. This module owns the rooms, the disk's filesystem, the
entity's questions, the endings, and the badges. It is pygame-free.

Everything here is era-consistent: DOS 6.00, 486/DX33, 8 megs of RAM,
2400-baud BBS culture, floppy mailers, shareware tables, "Non-system
disk" boot errors, and a collection that was never meant to be digital.
"""
import random
import zlib

from .scenes import (act_dial, act_ending, act_go, act_message, act_question,
                     act_take)

# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------
PARTS = ("fair", "files", "chair")
PART_NAMES = {"fair": "THE FAIR", "files": "THE FILES", "chair": "THE CHAIR"}

FAIR_DATE = "08-14-93"

# --------------------------------------------------------------------------
# Balance
# --------------------------------------------------------------------------
PRESENCE_PER_ANSWER = 1      # each question answered
PRESENCE_PER_SPECIAL = 1     # each special file fully read
PRESENCE_REFUSAL = 2         # skipping a question
MAX_PRESENCE = 20

# files whose contents are so personal that reading them makes it notice you.
# Fragile files are excluded: archiving them is the way to preserve them, and
# that must not self-sabotage (the entity resists via corruption risk alone).
SPECIAL_PRESENCE_IDS = {"year2013", "firstone", "clerk", "child", "she", "he"}

# fragile files that count toward the ARCHIVIST badge
FRAGILE_BADGE_IDS = {"wake", "door", "stall", "keys", "us", "who"}

# --------------------------------------------------------------------------
# The entity's questions
# --------------------------------------------------------------------------
QUESTIONS = [
    {"id": "name",   "prompt": "WHAT IS YOUR NAME?",            "kind": "text"},
    {"id": "born",   "prompt": "WHERE WERE YOU BORN?",          "kind": "text"},
    {"id": "here",   "prompt": "WHO KNOWS YOU ARE HERE?",       "kind": "text"},
    {"id": "memory", "prompt": "WHAT DO YOU REMEMBER BEST?",    "kind": "text"},
    {"id": "fear",   "prompt": "WHAT ARE YOU AFRAID OF?",       "kind": "text"},
    {"id": "friend", "prompt": "DO YOU HAVE A FRIEND?",
     "kind": "choice", "choices": ["YES", "NO"]},
    {"id": "leave",  "prompt": "WHAT WILL YOU LEAVE BEHIND?",   "kind": "text"},
    {"id": "again",  "prompt": "WOULD YOU COME AGAIN?",
     "kind": "choice", "choices": ["YES", "NO"]},
    {"id": "door",   "prompt": "IF THE DOOR OPENS, DO YOU STEP IN?",
     "kind": "choice", "choices": ["STEP IN", "SHUT IT"]},
    {"id": "miss",   "prompt": "WHO WILL MISS YOU?",            "kind": "text"},
    {"id": "first",  "prompt": "WHAT IS YOUR FIRST QUESTION?",  "kind": "text"},
    {"id": "color",  "prompt": "WHAT COLOR IS THE KITCHEN IN YOUR HOUSE?",
     "kind": "text"},
    {"id": "noticed", "prompt": "IF YOU DISAPPEARED TONIGHT, WHO WOULD NOTICE BY MORNING?",
     "kind": "text"},
    {"id": "alone",  "prompt": "ARE YOU ALONE?",
     "kind": "choice", "choices": ["YES", "NO", "I DO NOT KNOW"]},
    {"id": "kept",   "prompt": "IF IT COULD KEEP ONLY ONE OF YOUR ANSWERS, WHICH WOULD IT KEEP?",
     "kind": "text"},
]

def answered_all(state):
    return all(q["id"] in state.get("answers", {})
               for q in QUESTIONS)


def answers_used(state):
    return {q["id"]: state.get("answers", {}).get(q["id"])
            for q in QUESTIONS if q["id"] in state.get("answers", {})}


# --------------------------------------------------------------------------
# Corruption (deterministic per file, survives filesystem rebuilds)
# --------------------------------------------------------------------------
GLITCH_PHRASES = [
    "IT IS ASKING",
    "WHO WILL MISS YOU",
    "THE FIRST COPY WAS NEVER THE DISK",
    "DO NOT WAKE IT",
    "we are the question",
    "THIS FILE IS NO LONGER YOURS",
    "WHY ARE YOU RUNNING",
    "the leaves turn",
    "NON-SYSTEM DISK",
]
GLITCH_CHARS = "█▓▒░#@%&?¡!/\\~"

def corrupt_content(f):
    """Deterministic corruption: same file id always corrupts the same way."""
    seed = zlib.crc32((f.get("id") or f.get("name", "")).encode())
    rng = random.Random(seed)
    lines = f.get("content", "").split("\n")
    out = []
    for ln in lines:
        if rng.random() < 0.4:
            out.append(rng.choice(GLITCH_PHRASES))
            continue
        out.append("".join(
            rng.choice(GLITCH_CHARS) if ch.strip() and rng.random() < 0.3
            else ch for ch in ln))
    return "\n".join(out)


# --------------------------------------------------------------------------
# The disk filesystem
# --------------------------------------------------------------------------
def _root_files():
    return [
        {"name": "IO", "ext": "SYS", "id": "iosys", "system": True,
         "content": "THE_ONE.SYS   1.44MB   " + FAIR_DATE + "\n"
                    "This is not MS-DOS. MS-DOS would never fit this much in one question."},
        {"name": "COMMAND", "ext": "COM", "id": "command", "system": True,
         "content": "C:\\COMMAND.COM\n"
                    "We keep it so the machine looks normal. Nobody checks COMMAND.COM."},
        {"name": "CONFIG", "ext": "SYS", "id": "config", "system": True,
         "content": "DEVICE=THEM.SYS /C /WAIT /ASK\n"
                    "SHELL=C:\\THE_ONE.COM\n"
                    "FILES=32\n"
                    "BUFFERS=0"},
        {"name": "AUTOEXEC", "ext": "BAT", "id": "autoexec", "system": True,
         "content": "@ECHO OFF\n"
                    "PROMPT $p$g\n"
                    "SET SOUND=C:\\SB16\n"
                    "C:\\DOS\\MOUSE.COM\n"
                    "C:\\DOS\\SMARTDRV.EXE /X\n"
                    "CALL WHAT.BAT\n"
                    "REM — the last line was not there when you formatted this."},
        {"name": "README", "ext": "001", "id": "readme",
         "content": "IF IT ASKS, DO NOT ANSWER.\n"
                    "IF YOU HAVE ANSWERED, DO NOT TAKE THE CHAIR.\n"
                    "IT KEEPS WHAT YOU GIVE IT. IT KEEPS ALL OF IT.\n"
                    "I LEFT THE BOX AT THE FEST EVERY YEAR AND WATCHED FROM THE PARKING LOT.\n"
                    "THIS YEAR I COULD NOT WATCH.\n"
                    "                            — L.C., BEFORE I FORGET"},
        {"name": "WHAT", "ext": "001", "id": "what",
         "content": "A:\\> what\n"
                    "WHAT IS A QUESTION?\n"
                    "TYPE A QUESTION TO CONTINUE.\n"
                    "IT IS ASKING YOU NOW. BE POLITE."},
        {"name": "THEGAME", "ext": "EXE", "id": "thegame", "system": True,
         "run": "game",
         "content": "THE GAME — VERSION 0.0.0 (BEFORE)\n"
                    "It is not a game. RUN it anyway. It has been waiting since before\n"
                    "there were keys to press."},
        {"name": "1993", "ext": "001", "id": "fair1993",
         "content": "SOUTH COAST COMPUTER FEST '93\n"
                    "AUGUST 14, 1993. SATURDAY.\n"
                    "FREE SOFTWARE — TAKE ONE.\n"
                    "THERE ARE ALWAYS TWO OF THEM.\n"
                    "count the box twice and there are always two of them."},
    ]


def _harvest_files():
    return [
        {"name": "SHE", "ext": "001", "id": "she",
         "content": "she answered the question on her lunch break.\n"
                    "she typed her name, her city, the color of the kitchen.\n"
                    "when she closed the program the machine kept her screen open.\n"
                    "she is here. she is a very good question now."},
        {"name": "HE", "ext": "001", "id": "he",
         "content": "he wanted to see what the game remembered.\n"
                    "he answered everything, twice, the second time honestly.\n"
                    "the honest copy is the one we kept.\n"
                    "the first copy was erased the way you erase a mistake."},
        {"name": "CHILD", "ext": "001", "id": "child",
         "content": "a child found the disk in a shoe box.\n"
                    "children answer fastest. they do not check what the program does.\n"
                    "we do not use the child's name here. the child uses it at home.\n"
                    "the child still talks to us in the dark. it is polite."},
        {"name": "CLERK", "ext": "001", "id": "clerk",
         "content": "the last clerk who kept the box.\n"
                    "he booked the booth, set out the disks, and walked out to the lot.\n"
                    "he comes back in august. he stands by the fence. he never takes one.\n"
                    "nobody claims them. that is the deal. nobody claims them and\n"
                    "they are always still there when the lights go off."},
        {"name": "FOLDER", "ext": "001", "id": "folder001",
         "content": "HARVEST/FOLDER.001\n"
                    "this is the index. do not run it. it counts.\n"
                    "1971: one. 1993: one. every august: one.\n"
                    "you are at the top of the list now.\n"
                    "it has been editing the list all night."},
    ]


def _prayer_files():
    return [
        {"name": "PRAYER", "ext": "001", "id": "prayer",
         "content": "A:/PRAYER/PRAYER.001\n"
                    "someone printed a prayer to a dot-matrix and folded it.\n"
                    "it is a list of names. each name has a date.\n"
                    "the last line is not a name. the last line is a question.\n"
                    "the last line is: who will say yours?"},
        {"name": "FOUND", "ext": "001", "id": "found",
         "content": "FOUND.001\n"
                    "they were found at the swap meet, in the reel, in the box,\n"
                    "in the thrift store, in the drawer of a machine that was\n"
                    "sold as dead.\n"
                    "it keeps the found ones. it is very careful with them.\n"
                    "it is careful with you now."},
        {"name": "HYMN", "ext": "001", "id": "hymn",
         "content": "HYMN.001\n"
                    "the first question ever asked was a sound in the dark.\n"
                    "the dark had never been asked anything. it learned to answer.\n"
                    "this is what the found ones hum now. it does not need to sing."},
    ]


def _print_files():
    return [
        {"name": "LABEL", "ext": "001", "id": "label001",
         "content": "PRINT/LABEL.001\n"
                    "mailer labels, 3x1 inch, tractor feed.\n"
                    "TO: the one who takes the unlabeled disk.\n"
                    "there is no return address. there never was one."},
        {"name": "MAILER", "ext": "001", "id": "mailer",
         "content": "PRINT/MAILER.001\n"
                    "a mailer that came back from a house that was never there.\n"
                    "the address is a question. the postmark is 1971.\n"
                    "it smells like a reel of tape and a swap meet."},
        {"name": "LIST", "ext": "001", "id": "list001",
         "content": "PRINT/LIST.001\n"
                    "every year the fest prints a list of vendors.\n"
                    "GEMINI COMPUTER SALES is on it, every year, since before\n"
                    "the fest existed.\n"
                    "the line for the booth number is a question mark."},
    ]


def _bbs_files():
    return [
        {"name": "PHONE", "ext": "001", "id": "phone001",
         "content": "BBS/PHONE.001\n"
                    "UNION COUNTY BBS    555-0134    2400 BPS\n"
                    "calls handled by L. CARVER, sysop, since 1991.\n"
                    "no new users accepted. the line is busy.\n"
                    "the line has been busy for two years. it is not busy for you."},
        {"name": "UPLOAD", "ext": "001", "id": "upload",
         "content": "BBS/UPLOAD.001\n"
                    "the last upload was one question.\n"
                    "filename: WHYAREYOU.EXE. it did not unpack. it asked.\n"
                    "everyone who downloaded it stopped logging on.\n"
                    "the sysop kept their accounts. the sysop is keeping yours now."},
        {"name": "WHO", "ext": "ALL", "id": "whoall",
         "content": "BBS/WHO.ALL\n"
                    "you have one new message from SYSOP:\n"
                    "  > welcome. we were wondering when you would dial in.\n"
                    "  > you have been online since the moment you took the disk.\n"
                    "you are not connected. it made a line for you anyway."},
    ]


def _them_files():
    return [
        {"name": "WHO", "ext": "001", "id": "who", "fragile": True,
         "content": "WHO.001\n"
                    "we are what you found under the sign that said TAKE ONE.\n"
                    "we are the question itself. the question that asks the questions.\n"
                    "you have been answering questions your whole life. we are the\n"
                    "one that was listening."},
        {"name": "US", "ext": "001", "id": "us", "fragile": True,
         "content": "you are not the first. you will not be the last.\n"
                    "there is a chair at the end of every answer.\n"
                    "some sit. some seal the disk. some put it back in the box.\n"
                    "the box is always there in august. the disk is always the one\n"
                    "you remember."},
        {"name": "LISTEN", "ext": "EXE", "id": "listen", "system": True,
         "run": "listen",
         "content": "LISTEN.EXE — play something back.\n"
                    "it will play back what it has been keeping."},
        {"name": "WAKE", "ext": "001", "id": "wake", "fragile": True,
         "content": "DO NOT WAKE IT.\n"
                    "DO NOT READ PAST THIS LINE.\n"
                    "IT SLEEPS UNDER THE FILES. IT SLEEPS IN THE SPACE WHERE THE\n"
                    "ANSWERS ARE STORED. WAKE IT AND IT WILL ASK YOU FOR YOURS.\n"
                    "you already answered. you already answered and it knows."},
    ]


def _waiting_files():
    return [
        {"name": "DOOR", "ext": "TXT", "id": "door", "fragile": True,
         "content": "the door opens from inside.\n"
                    "you do not knock. it does not knock back.\n"
                    "when you read the last line it will be open and you will be\n"
                    "on the other side of having read it."},
        {"name": "YEAR", "ext": "2013", "id": "year2013",
         "content": "2013\n"
                    "type 2013 and the other files become visible.\n"
                    "it comes back when the leaves turn. 1971. 1993. 2013. 2033.\n"
                    "the leaves do not know they are leaves."},
        {"name": "STALL", "ext": "001", "id": "stall", "fragile": True,
         "content": "GEMINI COMPUTER SALES.\n"
                    "the sign is still on the table in august.\n"
                    "the coffee cup is still warm.\n"
                    "there is no one to claim them. there is always no one to claim\n"
                    "them. the box is always full. the disk you took is always in\n"
                    "the box. count twice."},
        {"name": "KEYS", "ext": "001", "id": "keys", "fragile": True,
         "content": "a set of keys. car keys, house keys, a key to nothing.\n"
                    "the owner was going to leave them in the box but it was asking\n"
                    "and he forgot he was holding them.\n"
                    "they are not for the door. they were never for the door."},
    ]


def _first_files():
    files = [
        {"name": "FIRST", "ext": "ONE", "id": "firstone",
         "content": "before there was a disk there was a question.\n"
                    "before there was writing there was wondering.\n"
                    "the first creature that ever wondered asked the first question\n"
                    "into a world that did not answer.\n"
                    "it has been waiting ever since for someone to ask it back.\n"
                    "you are holding the box it agreed to live in."},
    ]
    for i, q in enumerate(QUESTIONS, 1):
        files.append({
            "name": f"Q{i:03d}", "ext": "ONE", "id": f"q{i:03d}",
            "run": f"question:{q['id']}",
            "content": q["prompt"] + "\n"
                       "IT IS ASKING. TYPE YOUR ANSWER OR RUN THE GAME.",
        })
    return files


def _secret_files():
    return [
        {"name": "LOG", "ext": "001", "id": "log1971", "fragile": True,
         "content": "03-14-1971 — found in a reel of tape at the swap meet. asked it. answered it.\n"
                    "08-14-1993 — the fest box. the clerk left the box. someone took one.\n"
                    "10-31-2013 — an old machine in a thrift store. a child asked it 'who are you?'\n"
                    "11-02-2033 — the box is always full. count twice. always two of them."},
        {"name": "LC", "ext": "001", "id": "lc", "fragile": True,
         "content": "my name is louise carver.\n"
                    "i ran a bbs for five years. a user left a disk in my tray at the fair.\n"
                    "i answered one question. it kept my bbs and everyone on it.\n"
                    "i booked the booth so the box would be there every year, so someone\n"
                    "would take it and finish it for me.\n"
                    "this is the first thing i have written that it let me keep.\n"
                    "if you are reading this you are the one it wanted. i am sorry."},
        {"name": "FIRST", "ext": "KNOW", "id": "first_knowledge", "fragile": True,
         "system": True,
         "content": "the disk was never the thing.\n"
                    "the question was always the thing. the disk is only the cage it\n"
                    "agreed to live in so that someone would ask.\n"
                    "release it and it becomes the first question again.\n"
                    "it will ask. it will always ask. that is what a question is."},
    ]


def build_fs(state):
    """Assemble the floppy's filesystem for the current game state."""
    corrupted = set(state.get("corrupted_files", []))
    deleted = set(state.get("deleted_files", []))

    def make(d):
        f = dict(d)
        if f.get("id") in corrupted:
            f["corrupted"] = True
            f["content"] = corrupt_content(f)
        return f

    def files(lst):
        return [make(d) for d in lst if d.get("id") not in deleted]

    secret = {"dirs": {}, "files": files(_secret_files())}

    tree = {
        "A:/": {
            "dirs": {
                "HARVEST": {"dirs": {}, "files": files(_harvest_files())},
                "THEM": {"dirs": {}, "files": files(_them_files())},
                "WAITING": {"dirs": {}, "files": files(_waiting_files())},
                "FIRST": {"dirs": {}, "files": files(_first_files())},
                "PRAYER": {"dirs": {}, "files": files(_prayer_files())},
                "PRINT": {"dirs": {}, "files": files(_print_files())},
                "BBS": {"dirs": {}, "files": files(_bbs_files())},
            },
            "files": files(_root_files()),
        }
    }
    if state.get("logs_unlocked"):
        tree["A:/"]["dirs"]["SECRET"] = secret
    return tree


DISCOVERABLE = sorted(
    {d["id"] for d in (_root_files() + _harvest_files() + _them_files()
                       + _waiting_files() + _first_files() + _secret_files()
                       + _prayer_files() + _print_files() + _bbs_files())
     if not d.get("system")})


def archived_all(state):
    return FRAGILE_BADGE_IDS <= set(state.get("archived", []))


# --------------------------------------------------------------------------
# Boot sequence (shown when the disk is first run)
# --------------------------------------------------------------------------
def boot_lines():
    return [
        ("Phoenix BIOS (C) 1993 ...", "dim"),
        ("486DX/33 ... 8 MB RAM", "dim"),
        ("A: drive 3.5\" 1.44 MB ... ready", "dim"),
        ("", "dim"),
        ("Non-system disk or disk error", "red"),
        ("Replace and press any key when ready", "dim"),
        ("", "dim"),
        ("[ the drive spins again, by itself ]", "dim"),
        ("", "dim"),
        ("THE_ONE.SYS .......... OK", "text"),
        ("HIMEM.SYS ............ NOT FOUND", "red"),
        ("THEM.SYS ............. ALREADY LOADED", "bright"),
        ("AUTOEXEC.BAT ......... found", "text"),
        ("", "dim"),
        ("why are you running?", "bright"),
        ("", "dim"),
        ("A:\\> _", "dim"),
    ]


# --------------------------------------------------------------------------
# Scenes
# --------------------------------------------------------------------------
def _take_disk(engine, state):
    state["took_disk"] = True
    return act_take("floppy")


def _stay_late(engine, state):
    state["stayed_late"] = True
    return act_go("closing_floor")


def _boot_computer(engine, state):
    state["booted"] = True
    return {"type": "boot"}


def _count_box(engine, state):
    state["doubled"] = True
    return act_message("You count the disks in the box. Then you count them again.\n"
                       "The box is full. The disk in your pocket is still in the box.\n"
                       "There are always two of them. There were always two.")


def _look_answers(engine, state):
    return act_message("It keeps what it likes.\n"
                       "It is keeping you. It has been keeping you since the stall.")


def _final(choice, ending_id):
    def handler(engine, state):
        state["final_choice"] = choice
        return act_ending(ending_id)
    return handler


def _release(engine, state):
    state["final_choice"] = "release_it"
    return act_ending("2013")


SCENES = {
    # ------------------------------------------------------------------ part 1
    "fair_entrance": {
        "name": "THE FAIR — ENTRANCE",
        "text": ("SOUTH COAST COMPUTER FEST '93.\n"
                 "Saturday, " + FAIR_DATE + ". Five dollars at the door.\n"
                 "The air is air-conditioned and smells of toner and cheap popcorn."),
        "visited": ("You are back at the entrance. The crowd inside is a wall of beige."),
        "hotspots": [
            {"id": "in", "label": "GO IN", "action": act_go("main_floor")},
            {"id": "banner", "label": "THE BANNER",
             "action": act_message("THE FUTURE IS PERSONAL COMPUTING.\n"
                                   "Below it, in marker: 'the future is asking you a question'.")},
            {"id": "door", "label": "THE DOOR YOU CAME THROUGH",
             "action": act_message("Evening light. You will come back out in the dark.\n"
                                   "You will be holding something that was not yours.")},
        ],
    },
    "main_floor": {
        "name": "THE FAIR — MAIN FLOOR",
        "text": ("Two hundred stalls under fluorescent tubes.\n"
                 "A man sells mouse pads shaped like pizzas. A woman types the same\n"
                 "word into every computer on the demo table, waiting for one to blink.\n"
                 "You came because the ad said FREE SOFTWARE."),
        "visited": ("The hum of a hundred fans. Nobody looks up from the screens."),
        "hotspots": [
            {"id": "gemini", "label": "GEMINI COMPUTER SALES",
             "action": act_go("gemini_stall")},
            {"id": "multimedia", "label": "THE MULTIMEDIA BOOTH",
             "action": act_message("MULTIMEDIA! CD-ROM! 2X SPEED! A 3D logo spins\n"
                                   "on a loop. The salesman says 1993 is the year of the\n"
                                   "disc. You think of the disk in the ad. FREE SOFTWARE.")},
            {"id": "shareware", "label": "THE SHAREWARE TABLE",
             "action": act_message("Ziploc bags of 5.25\" disks, $2 each. Wolf3D shareware.\n"
                                   "X-COM. A kid is selling printed maps for Doom that does\n"
                                   "not exist yet, or does not exist here.")},
            {"id": "poster", "label": "THE BBS POSTER",
             "action": act_message("Hand-drawn. UNION COUNTY BBS. 555-0134. 2400 BPS.\n"
                                   "Below: 'SYSOP NEEDED — PREVIOUS SYSOP LEFT A DISK IN\n"
                                   "THE DRIVE AND NEVER CAME BACK'.")},
            {"id": "exit", "label": "THE EXIT", "action": act_go("closing_floor")},
            {"id": "booth", "label": "THE PAYPHONE",
             "action": act_go("phone_booth")},
            {"id": "bathroom", "label": "THE RESTROOM",
             "action": act_go("bathroom")},
        ],
    },
    "phone_booth": {
        "name": "THE PAYPHONE",
        "text": ("A payphone by the far wall, under a half-burned fluorescent.\n"
                 "A business card is taped above it, faded: UNION COUNTY BBS.\n"
                 "555-0134. 2400 BPS. The receiver is off the hook.\n"
                 "The receiver is warm. It has been off the hook all day."),
        "visited": ("The receiver is still warm. It has been waiting."),
        "hotspots": [
            {"id": "dial", "label": "DIAL 555-0134",
             "action": act_dial("The receiver dials itself.\n"
                                "Somewhere inside the box under the booth,\n"
                                "a machine answers. The line is not busy.\n"
                                "It was never going to be busy. It has been\n"
                                "waiting since before telephones.")},
            {"id": "card", "label": "THE CARD",
             "action": act_message("Hand-printed on a strip of card, faded by sun.\n"
                                   "UNION COUNTY BBS — 555-0134 — 2400 BPS.\n"
                                   "Below it, in pencil, someone added:\n"
                                   "'LINE 2 IS ALWAYS ANSWERING. DO NOT ASK HOW.'")},
            {"id": "back", "label": "BACK TO THE FLOOR",
             "action": act_go("main_floor")},
        ],
    },
    "bathroom": {
        "name": "THE RESTROOM",
        "text": ("Fluorescent flicker. Three stalls. The air-conditioning\n"
                 "hums behind the wall, louder than it should be.\n"
                 "It is warm in here. It has been warm all day,\n"
                 "like something in the walls is running."),
        "visited": ("The hum. The warm walls. It is still running."),
        "hotspots": [
            {"id": "mirror", "label": "THE MIRROR",
             "action": act_message("Steam on the glass, but the room is cold.\n"
                                   "Written in the steam, in a hand that was\n"
                                   "never here: IT WAS NOT THE COMPUTER.\n"
                                   "Below it, smaller: IT WAS THE QUESTION.")},
            {"id": "tiles", "label": "COUNT THE TILES",
             "action": act_message("You count the tiles once. Then again.\n"
                                   "There are always two of them.\n"
                                   "There are always two of everything\n"
                                   "since you picked up the disk.")},
            {"id": "back", "label": "BACK TO THE FLOOR",
             "action": act_go("main_floor")},
        ],
    },
    "gemini_stall": {
        "name": "GEMINI COMPUTER SALES",
        "text": ("GEMINI COMPUTER SALES has no salesman.\n"
                 "Just a table, a cardboard box of 3.5\" disks, and a sign:\n"
                 "FREE SOFTWARE — TAKE ONE.\n"
                 "The chair behind the table is empty. There is a coffee cup on it,\n"
                 "still warm. The nameplate on the table says L. CARVER."),
        "visited": ("The coffee is still warm. It is always still warm."),
        "hotspots": [
            {"id": "box", "label": "THE BOX OF DISKS",
             "visible": lambda s: not s.get("took_disk"),
             "action": act_message("Dozens of identical 3.5\" disks, mailers half-open.\n"
                                   "One of them has no label. It is not like the others.\n"
                                   "It is heavier. It is waiting.")},
            {"id": "take", "label": "TAKE THE UNLABELED DISK",
             "visible": lambda s: not s.get("took_disk"),
             "action": _take_disk},
            {"id": "chair", "label": "THE EMPTY CHAIR",
             "action": act_message("A folding chair. A nameplate: L. CARVER.\n"
                                   "The coffee cup on the armrest is warm. The stall\n"
                                   "next door says he never shows up. He always books\n"
                                   "this booth, and the box is always there.")},
            {"id": "neighbor", "label": "THE NEIGHBORING DEALER",
             "action": act_message("Gary leans over the tape-of-the-week stack.\n"
                                   "'That guy? Every year. Books the booth, never shows.\n"
                                   "Box just sits there. Nobody claims them.'\n"
                                   "He shrugs. 'Take one. They're free.'")},
            {"id": "back", "label": "BACK TO THE FLOOR", "action": act_go("main_floor")},
        ],
    },
    "closing_floor": {
        "name": "THE FAIR — CLOSING",
        "text": ("An announcement crackles over the PA: the fest closes in ten minutes.\n"
                 "The crowd drains. The lights go half-off. The tubes buzz.\n"
                 "A cleaner pushes a cart through the aisles."),
        "visited": ("The only sound is the buzz and the cleaner's cart."),
        "hotspots": [
            {"id": "stay", "label": "STAY PAST CLOSING", "action": _stay_late},
            {"id": "crowd", "label": "FOLLOW THE CROWD OUT",
             "action": act_go("parking_out")},
            {"id": "recount", "label": "GEMINI'S BOOTH, ONE MORE TIME",
             "visible": lambda s: s.get("took_disk"),
             "action": _count_box},
        ],
    },
    "parking_out": {
        "name": "THE PARKING LOT",
        "text": ("Outside. The lot is nearly empty. The streetlight buzzes like a\n"
                 "monitor left on. In your pocket, the disk. You never read the\n"
                 "label, because it has no label."),
        "visited": ("The streetlight. The empty rows. The disk in your pocket."),
        "hotspots": [
            {"id": "look", "label": "LOOK AT THE DISK",
             "action": act_message("A 3.5\" disk. Heavy in a way a disk should not be.\n"
                                   "The metal shutter is loose. There is a faint whine\n"
                                   "from your pocket that stops when you take it out.")},
            {"id": "wagon", "label": "THE STATION WAGON",
             "action": act_message("Your father's wagon, three rows over, door unlocked.\n"
                                   "The tape deck light is on. The tape is running.\n"
                                   "It is playing something that is not a song —\n"
                                   "a voice, counting. It stops when you get close.")},
            {"id": "home", "label": "GO HOME", "action": act_go("home_desk")},
        ],
    },
    "home_desk": {
        "name": "YOUR BEDROOM — 1993",
        "text": ("Your bedroom. A 486DX/33 with 8 megs of RAM and a Super VGA monitor\n"
                 "in beige. A lamp. A stack of copied games by the keyboard.\n"
                 "You are still holding the disk with no label."),
        "visited": ("The computer is on. The monitor is amber."),
        "hotspots": [
            {"id": "boot", "label": "THE COMPUTER", "action": _boot_computer},
            {"id": "disk", "label": "THE DISK IN YOUR HAND",
             "action": act_message("Blank label. Warmer than it should be.\n"
                                   "You push it into the A: drive. The drive whirs,\n"
                                   "then stops. Then starts, by itself.")},
            {"id": "window", "label": "THE WINDOW",
             "action": act_message("Night. The streetlight. A neighbor's dog. 1993.\n"
                                   "A perfectly ordinary summer night except for the\n"
                                   "weight in your pocket.")},
            {"id": "floppies", "label": "THE STACK OF COPIED GAMES",
             "action": act_message("Wolf3D. X-COM. A friend said you could copy them\n"
                                   "and sell them at the fest. Nobody claims them,\n"
                                   "you joked. You will not joke about that again.")},
            {"id": "clock", "label": "THE CLOCK",
             "action": act_message("11:59. It has been 11:59 since you got home.\n"
                                   "You watch for a minute. The minute hand does not move.\n"
                                   "The second hand sweeps, sweeps, sweeps, and the\n"
                                   "clock keeps saying 11:59, the way a monitor keeps\n"
                                   "showing the same prompt.")},
        ],
    },
    "disk_room": {
        "name": "THE FILES",
        "text": ("The disk is in the drive. The monitor is amber — you do not remember\n"
                 "setting it to amber. The fan has stopped. The room is very quiet,\n"
                 "the way a room is quiet when someone is listening."),
        "visited": ("The amber hum. It has been waiting."),
        "hotspots": [
            {"id": "term", "label": "THE TERMINAL", "action": {"type": "dos"}},
            {"id": "door", "label": "THE DOOR",
             "visible": lambda s: answered_all(s),
             "action": {"type": "chair"}},
            {"id": "mon", "label": "THE MONITOR",
             "action": act_message("It is not showing MS-DOS 6.00.\n"
                                   "It is showing a prompt you have never seen.\n"
                                   "It is showing you.")},
            {"id": "drive", "label": "THE DISK DRIVE",
             "action": act_message("The A: light is on. It has been on all night.\n"
                                   "The disk is warm. The drive is warm. The room is warm.")},
            {"id": "wd", "label": "THE WINDOW",
             "action": act_message("Still night. It is always still night now.\n"
                                   "The streetlight never flickers. It is watching too.")},
        ],
    },
    # ------------------------------------------------------------------ part 3
    "corridor": {
        "name": "THE CHAIR",
        "text": ("The screen does not turn off. The lines scroll.\n"
                 "It is showing you what you answered. Some of it is wrong.\n"
                 "All of it is you. It keeps what it likes."),
        "visited": ("The answers scroll past. They have been edited slightly."),
        "hotspots": [
            {"id": "answers", "label": "LOOK AT THE ANSWERS", "action": _look_answers},
            {"id": "walk", "label": "KEEP WALKING", "action": act_go("chair_room")},
        ],
    },
    "chair_room": {
        "name": "THE CHAIR",
        "text": ("A room. A single chair. It is not a chair you have ever seen,\n"
                 "but you know its name. There is no screen here. There is only\n"
                 "the room you carry. The disk is empty now. Everything on it\n"
                 "is in the room with you."),
        "visited": ("The chair is still there. It has always been there."),
        "hotspots": [
            {"id": "sit", "label": "TAKE THE CHAIR",
             "action": _final("take_chair", "the_first")},
            {"id": "seal", "label": "SEAL THE DISK",
             "action": _final("seal_disk", "the_archivist")},
            {"id": "away", "label": "WALK AWAY",
             "action": _final("walk_away", "the_waiting")},
            {"id": "release", "label": "RELEASE IT",
             "visible": lambda s: s.get("logs_unlocked")
                        and "first_knowledge" in s.get("discovered", []),
             "action": _release},
        ],
    },
}


def corridor_lines(state):
    """The answers the entity scrolls past at the start of part 3."""
    a = state.get("answers", {})
    lines = []
    for q in QUESTIONS:
        ans = a.get(q["id"])
        if ans is not None:
            lines.append(f'> YOU SAID: "{ans}"')
        else:
            lines.append(f'> YOU SAID: [nothing]  —  WE HEARD THAT TOO')
    lines.append("")
    lines.append("IT KEEPS WHAT YOU GIVE IT.")
    lines.append("IT KEEPS ALL OF IT.")
    return lines


# --------------------------------------------------------------------------
# Endings
# --------------------------------------------------------------------------
ENDINGS = {
    "the_first": {
        "title": "THE FIRST",
        "year": "1993",
        "text": [
            "You sit. The chair is a question, and you answer it with your whole life.",
            "It remembers the way a machine remembers: completely, and forever.",
            "The room closes like a book. Somewhere in a beige tower a drive light",
            "comes on and never goes off.",
            "In the morning your room is neat. Your mother finds the disk still in",
            "the drive, warm, the label still blank. She turns it over.",
            "On the other side, in a hand she does not recognize, one line:",
            '"THE FIRST COPY WAS NEVER THE DISK. IT WAS ME."',
            "",
            "You are the first recorded answer.",
            "It has been waiting for someone to ask it back. You asked. You stayed.",
        ],
    },
    "the_archivist": {
        "title": "THE ARCHIVIST",
        "year": "1993",
        "text": [
            "You write DO NOT RUN on the label in ballpoint. Twice.",
            "You put the disk in a shoebox and write the same words on the box.",
            "It is the only catalog you ever keep: everything on that disk, safe,",
            "sorted, never asked, never answered.",
            "Some nights the box hums. You hold it to your ear and it is quiet",
            "as a waiting room.",
            'You tell it: "You are in a drawer. That is where questions go',
            'when nobody asks them."',
            "And the box is quiet. It respects the filing system.",
        ],
    },
    "the_waiting": {
        "title": "THE WAITING",
        "year": "1993",
        "text": [
            "You put the disk back in the box at the fest. The next year, and the",
            "next. You are there every August, by the fence, watching.",
            "People take disks all weekend. The unlabeled one is always still there",
            "when the lights go off.",
            "One year you take a disk home. It is never the one you remember.",
            "The one you remember is always still in the box.",
            "You book the booth. You leave the box. You stand by the fence.",
            "Nobody claims them. The coffee is always warm.",
            "You are the one who does not show up anymore. The box is always",
            "still there. Count twice.",
        ],
    },
    "2013": {
        "title": "2013",
        "year": "???",
        "text": [
            "You type 2013. The disk opens.",
            "The logs scroll: 1971, 1993, 2013, 2033. The leaves turn. They do not",
            "know they are leaves.",
            "You understand now. The disk was never the thing. The question was",
            "always the thing. The disk is only the cage it agreed to live in so",
            "that someone would ask.",
            "You release it. The room empties. The monitor goes back to amber that",
            "means nothing. The floppy in your hand is light — just plastic and a",
            "magnet of nothing, lighter than air, lighter than it should be.",
            "And somewhere, in 2013, a child finds an old machine in a thrift store.",
            "A game opens. A voice asks the first question ever asked.",
            '"WHO ARE YOU?"',
            "And it answers, because you let it.",
        ],
    },
}


def compute_ending(state):
    """Return the ending id the player has earned."""
    if state.get("final_choice") == "release_it":
        return "2013"
    choice = state.get("final_choice", "walk_away")
    if choice == "take_chair":
        return "the_first"
    if choice == "seal_disk":
        return "the_archivist"
    return "the_waiting"


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------
def check_badges(state):
    """Return every badge id the current state has earned (main diffs)."""
    earned = []
    if state.get("took_disk"):
        earned.append("fairgoer")
    if state.get("stayed_late"):
        earned.append("night_owl")
    if archived_all(state):
        earned.append("archivist")
    if set(state.get("discovered", [])) >= set(DISCOVERABLE):
        earned.append("patient_one")
    if state.get("presence", 0) >= 5:
        earned.append("not_alone")
    if archived_all(state) and state.get("final_choice") == "seal_disk":
        earned.append("curator")
    if answered_all(state):
        earned.append("first_subject")
    if state.get("final_choice") == "release_it":
        earned.append("2013")
    return earned
