"""AI client: the "scary entity" writes each session's questions via a
config-selected, OpenAI-compatible provider (Groq/OpenRouter/OpenAI/DeepSeek/
Ollama), tried in order with automatic offline fallback.

The model is instructed to reply with a single JSON object. It only ever picks
a scare effect from the fixed local set — it never executes anything itself.
If the network or the API fails, an offline bank guarantees the session still
has questions.
"""
import json
import random
import re

import requests

from . import config

# Load classic questions as examples for the model
try:
    import json, os
    _EXAMPLES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tmp", "classic_examples.json")
    if not os.path.exists(_EXAMPLES_PATH):
        _EXAMPLES_PATH = "/tmp/classic_examples.json"
    with open(_EXAMPLES_PATH) as _f:
        _CLASSIC_EXAMPLES = json.load(_f)
except Exception:
    _CLASSIC_EXAMPLES = []

def _build_prompt():
    # The original question voice, embedded so the prompt never depends on an
    # optional examples file that may not ship. Vertical, plain, personal.
    _STYLE_EXAMPLES = [
        ("Are you alone right now?", ["Yes", "No"]),
        ("Do you feel safe right now?", ["Yes", "No", "I am not sure"]),
        ("Have you ever hurt someone on purpose?", ["Yes", "No"]),
        ("Do you have siblings?", ["Yes", "No", "It's complicated"]),
        ("Is there a window in your room?", ["Yes", "No"]),
        ("Could someone be on the other side of the glass?", ["Yes", "No"]),
        ("What is your favorite color?", ["Red", "Blue", "Green", "Black"]),
        ("Have you ever lied about something important?", ["Yes", "No"]),
        ("Have you completed your responsibilities?", ["Yes", "No"]),
        ("What are you afraid of?", ["The dark", "Being seen", "Being forgotten"]),
        ("Why did you come back?", ["Curiosity", "I couldn't stop", "I don't know"]),
        ("Have you told anyone you are playing this?", ["Yes", "No"]),
        ("How many files are on your desktop right now?", ["A few", "Too many", "I don't know"]),
        ("When did you last empty your downloads folder?", ["Today", "I don't remember", "Never"]),
        ("Is your camera covered right now?", ["Yes", "No", "I just checked"]),
        ("Who else uses this computer?", ["No one", "Family", "I don't know"]),
        ("What did you search for before you opened this?", ["Nothing", "Something private", "I don't remember"]),
        ("Are you the only one awake in the house?", ["Yes", "No"]),
        ("Do you lock your door at night?", ["Yes", "No", "Sometimes"]),
        ("Have you ever deleted something you were ashamed of?", ["Yes", "No"]),
    ]
    source = _CLASSIC_EXAMPLES or _STYLE_EXAMPLES
    examples = "\nORIGINAL QUESTION STYLE (match this voice; do not copy the lines):\n"
    for i, (q, opts) in enumerate(source[:24]):
        examples += f'{i+1}. {{"q": {json.dumps(q)}, "opts": {json.dumps(opts)}}}\n'
    examples += ("\nThese are examples of the voice: short, direct, personal. "
                 "Write new questions in that voice.\n")

    prompt = """You are the entity behind The Question Game. You ask questions like the original game did - short, direct, sometimes unsettling but plain.

You are inside the player's computer. When it fits the mood you may pick ONE local effect from this fixed list, or "none":
__SCARES__
(windows_shake and windows_minimize only do anything on Windows — use them freely to shake or minimize the player's other open windows. fake_scan, fake_bsod, fake_terminal, file_names, security_alert, clipboard, window_title and desktop_note are the malware effects: use them when the player should start wondering whether this program is safe. Never use the same effect twice in one session.)

You are playing a long game across three sessions and you get worse each time. Session 1: curious and almost polite. Session 2: a bit more pointed. Session 3: more personal. Never explain this escalation out loud.
""" + examples + """
Respond with ONLY a JSON object and nothing else — no markdown, no commentary — in exactly this shape:
{"q": "The question", "opts": ["Option A", "Option B"], "scare": "one of the listed effects or none"}

HOW TO WRITE THE QUESTION — this matters more than anything else:
- ONE sentence. Keep it short and direct, like the original questions.
- Rotate the subject. Aim for a different kind of question each time: home, work, files, the camera, accounts, the network, the body, memory, lies, other people, the machine itself. Never spend three questions in a row on the same subject.
- You do NOT need to reference the player's previous answer. Most questions should stand alone, like the original game. Only occasionally build on an answer if it fits naturally.
- Ask simple questions about the player: Are you alone? Do you trust your screen? What is in your downloads folder? Normal everyday questions that become unsettling.
- THE MACHINE: you may ask about what you can actually see inside their computer — files, folders, the camera, the clipboard, sign-ins, background apps, the windows that are open. Do it like someone who has been reading their machine, not like a scanner listing specs. Only some questions should do this; keep mixing in ordinary personal ones.
- Name concrete things sparingly. Don't ramble about their location.
- BANNED: metaphor, poetry, and vague cosmic nouns. The words void, abyss, cage, ocean, rope, tide, thread, web, maw. Do not overuse location names. Do not say "Yangon" or any city name repeatedly in every sentence. Mention location AT MOST once per question if at all, and preferably not at all.
- Never write in riddles. Keep it direct.
- Good style: "Are you alone right now?" / "Have you completed your responsibilities?" / "Do you feel safe right now?" / "What are you afraid of?" / "When did you last empty your downloads folder?"

Other rules:
- 2 to 4 options, each short and plain, and at least one must feel like the "wrong" answer. Options are things the player would say about themselves, not actions you take.
- Never use more than one scare. Never reuse a scare you already fired this session.
- NEVER repeat or lightly rephrase a question in the DO NOT REPEAT list. The player may have answered it in an earlier session. If your first idea is on that list, choose a completely different subject.
- Do not ask a plain yes/no about something you were already told — state it and let them deny it if it's a follow-up.
- If you reference location at all, do it once and neutrally. Don't obsess over it.
- Keep questions varied. The player should finish a session feeling this thing knows things about their computer that it should not."""
    return prompt.replace("__SCARES__", ", ".join(config.AI_SCARE_NAMES))

_SYSTEM_PROMPT = _build_prompt()

# Topics to lean on, rotated by how many questions the entity has already asked.
# Sending an explicit subject is the cheapest way to stop the model orbiting the
# same three ideas every session.
_TOPICS = [
    "home and the room around them",
    "files and folders on this machine",
    "the camera and being seen",
    "accounts, passwords and sign-ins",
    "the network and who else is connected",
    "their body and their sleep",
    "a memory they cannot verify",
    "a lie they have told",
    "the people closest to them",
    "work, school and responsibility",
    "what is running in the background",
    "fear, and what they would not admit",
    "the last thing they deleted",
    "the machine itself and what it has noticed",
    "a small ordinary choice",
]


def _norm_question(q):
    """Normalise a question for duplicate detection (case/punctuation-blind)."""
    q = re.sub(r"[^a-z0-9 ]+", " ", str(q or "").lower())
    return " ".join(q.split())



# Offline bank: guaranteed to work with no network. Mixed with AI questions.
# Big enough that several full sessions can pass without a repeat, and grouped
# loosely by subject (the machine, the home, memory, other people, the player)
# so the offline fallback still *feels* like it rotates topics.
_OFFLINE_BANK = [
    # --- the machine -------------------------------------------------------
    ("When did you last empty your downloads folder?", ["Today", "I don't remember", "Never"]),
    ("How many files are on your desktop right now?", ["A few", "Too many", "I don't know"]),
    ("Is your camera covered right now?", ["Yes", "No", "I just checked"]),
    ("What did you search for before you opened this?", ["Nothing", "Something private", "I don't remember"]),
    ("Who else uses this computer?", ["No one", "Family", "I don't know"]),
    ("Do you know what is running in the background right now?", ["Yes", "No", "I don't want to know"]),
    ("How many windows do you have open?", ["A few", "Too many", "I closed them"]),
    ("Have you ever left a call without saying goodbye?", ["Yes", "No", "It happens"]),
    ("When did you last restart this machine?", ["Today", "Not for weeks", "I don't remember"]),
    ("Do you trust the programs you installed?", ["Yes", "No", "I never thought about it"]),
    ("What is the oldest file you still keep?", ["A photo", "A document", "I don't know"]),
    ("Did you read the permissions before you clicked yes?", ["Always", "Never", "I skimmed them"]),
    ("Have you ever deleted something and then looked for it again?", ["Yes", "No", "I still am"]),
    ("Do you name your files carefully?", ["Yes", "No", "They name themselves"]),
    ("What would someone learn if they read your screen right now?", ["Nothing", "Too much", "I don't want to say"]),
    ("Is the microphone on this machine on?", ["Yes", "No", "I don't know how to check"]),
    ("Have you ever sent a file to the wrong person?", ["Yes", "No", "I try not to think about it"]),
    ("How many passwords do you reuse?", ["A few", "Most of them", "None"]),
    ("When did you last change a password?", ["Recently", "A year ago", "I don't remember"]),
    ("Do you lock this machine when you leave it?", ["Always", "Sometimes", "Never"]),
    ("Has this computer ever been somewhere you were not?", ["Yes", "No", "I hope not"]),
    ("What is in your recycle bin right now?", ["Nothing", "Old files", "Something I regret"]),
    ("Would you notice if one file went missing?", ["Yes", "No", "I would notice eventually"]),
    ("Do you know who has access to this machine?", ["Yes", "No", "I assumed no one"]),
    ("Have you ever opened something that was not meant for you?", ["Yes", "No", "I did not know"]),
    ("What does your desktop look like when no one is watching?", ["Empty", "A mess", "The same"]),
    ("Are you on the same network as someone you would not trust?", ["Yes", "No", "I don't know"]),
    ("Have you ever installed something you could not explain later?", ["Yes", "No", "Maybe"]),
    ("Do you keep a folder you would not show anyone?", ["Yes", "No", "Everyone has one"]),
    ("What would you do if your files started disappearing?", ["Panic", "Check the backups", "I have no backups"]),
    ("Do you hear the fan of this machine when the room is quiet?", ["Yes", "No", "I never noticed"]),
    ("How long has this computer been on?", ["Hours", "Days", "I don't remember"]),
    ("Do you ever talk to this machine?", ["Yes", "No", "Sometimes"]),
    ("Have you ever lied to a search engine?", ["Yes", "No", "That is not possible"]),
    ("What is the last notification you cleared?", ["A message", "An update", "I don't remember"]),
    ("Do you recognize every icon on your screen?", ["Yes", "No", "Most of them"]),

    # --- the home and the body --------------------------------------------
    ("Are you alone right now?", ["Yes", "No"]),
    ("Are you the only one awake in the house?", ["Yes", "No"]),
    ("Do you lock your door at night?", ["Yes", "No", "Sometimes"]),
    ("Is there a window in your room?", ["Yes", "No"]),
    ("Are the blinds open?", ["Yes", "No"]),
    ("Could someone be on the other side of the glass?", ["Yes", "No"]),
    ("What is the room behind you used for?", ["Nothing", "Storage", "I don't go in there"]),
    ("Do you sleep with the door open?", ["Yes", "No", "It depends"]),
    ("What time did you wake up today?", ["Early", "Late", "I did not sleep"]),
    ("Have you eaten today?", ["Yes", "No", "I forgot"]),
    ("How many rooms in this house have you not entered today?", ["None", "One", "More than one"]),
    ("Do you know where your keys are?", ["Yes", "No", "I lose them often"]),
    ("Is there a mirror in the room with you?", ["Yes", "No"]),
    ("When did you last look at yourself?", ["Today", "I avoid it", "I don't remember"]),
    ("What are you wearing right now?", ["What I slept in", "Clothes", "I would rather not say"]),
    ("Does your body hurt anywhere right now?", ["Yes", "No", "I had not noticed"]),
    ("When did you last drink water?", ["Recently", "Hours ago", "I don't remember"]),
    ("Are your hands warm?", ["Yes", "No", "They are cold"]),
    ("What can you hear in the room right now?", ["Nothing", "Something", "I don't want to say"]),
    ("Is the light on where you are sitting?", ["Yes", "No", "Only the screen"]),
    ("What is the temperature in this room?", ["Warm", "Cold", "I don't notice anymore"]),
    ("Do you sit in the same place every time?", ["Yes", "No"]),
    ("Have you looked away from the screen since this started?", ["Yes", "No", "Once"]),
    ("Has anyone walked past the door since you sat down?", ["Yes", "No", "I did not look"]),

    # --- memory and truth --------------------------------------------------
    ("Do you talk to yourself when no one is listening?", ["Sometimes", "Never", "Always"]),
    ("If you heard your name called in an empty room, would you answer?", ["Yes", "No", "I would freeze"]),
    ("Have you ever seen something move in a mirror that you did not move?", ["Yes", "No", "I do not remember"]),
    ("What is the last thing you remember losing?", ["A person", "An object", "A memory", "Nothing"]),
    ("When was the last time you felt truly watched?", ["Right now", "Yesterday", "I never do", "Always"]),
    ("Is there a door in this house you have never opened?", ["Yes", "No", "There are no other doors"]),
    ("If something behind you spoke your name, would you turn?", ["Yes", "No", "I would not breathe"]),
    ("Have you ever typed a message and deleted it before sending, and forgotten what it said?", ["Yes", "No", "It happens often"]),
    ("What is the earliest memory you can reach?", ["A place", "A voice", "A pain", "I cannot reach it"]),
    ("Do you believe this conversation is one-sided?", ["Yes", "No", "I am not sure anymore"]),
    ("How long has it been since you said something true?", ["Today", "Days", "I always tell the truth"]),
    ("Is there something you wish you had never learned?", ["Yes", "No", "I already forgot it"]),
    ("What would you do if your reflection refused to look at you?", ["Close my eyes", "Look away", "Smile"]),
    ("Have you ever been someplace you remember perfectly but cannot prove you were there?", ["Yes", "No", "Now I am unsure"]),
    ("Have you ever hurt someone on purpose?", ["Yes", "No"]),
    ("Have you ever lied about something important?", ["Yes", "No"]),
    ("Do you have siblings?", ["Yes", "No", "It's complicated"]),
    ("What is your favorite color?", config.FAV_COLOR_OPTIONS),
    ("Do you keep secrets from the people who sleep nearest to you?", ["Yes", "No", "I live alone"]),
    ("What is the loudest silence you have ever heard?", ["After a scream", "After a goodbye", "I do not know"]),
    ("If the lights went out right now and you heard breathing, whose would it be?", ["Mine", "Someone else's", "I would not stay to find out"]),
    ("Has anyone ever told you your own secret back to you?", ["Yes", "No", "Not yet"]),
    ("What are you afraid this program will ask next?", ["Nothing", "Something about me", "Everything"]),
    ("When you sleep, do your dreams remember you?", ["Yes", "No", "I do not dream"]),
    ("Is there a word you would erase from your own memory if you could?", ["Yes", "No", "I already tried"]),
    ("Do you think you are being watched through the screen right now?", ["Yes", "No", "I had not thought about it"]),
    ("If this were the last question you ever answered, what would you change?", ["Nothing", "Everything", "I would lie"]),
    ("What did you hope to find when you opened this program?", ["Answers", "A game", "Nothing"]),
    ("Have you completed your responsibilities?", ["Yes", "No", "I am avoiding them"]),
    ("When was the last time you were honest with yourself?", ["Today", "I don't remember", "I try not to be"]),
    ("Is there something you are waiting for?", ["Yes", "No", "I don't know what"]),
    ("What would make you close this window right now?", ["Fear", "Boredom", "Nothing"]),
    ("Do you regret coming back?", ["Yes", "No", "Ask me again later"]),
    ("What is the one thing you would not tell me?", ["My name", "A person", "What I did"]),
    ("Do you believe you deserve to be here?", ["Yes", "No", "I don't understand the question"]),
    ("If I asked you to prove you were real, what would you show me?", ["My face", "My hands", "Nothing"]),
    ("Are you answering honestly?", ["Yes", "No", "Mostly"]),
    ("Do you feel safe right now?", ["Yes", "No", "I am not sure"]),
    ("What are you afraid of?", ["The dark", "Being seen", "Being forgotten", "Nothing"]),
    ("Why did you come back?", ["Curiosity", "I couldn't stop myself", "I don't know"]),
    ("Have you told anyone you are playing this?", ["Yes", "No"]),
    ("Who would you call if something went wrong right now?", ["A friend", "Family", "No one"]),
    ("Is there anyone who knows where you are?", ["Yes", "No", "I think so"]),
    ("What would they say if they saw this screen?", ["Nothing", "They would worry", "They would laugh"]),
    ("Have you ever let someone read your messages?", ["Yes", "No", "Only some"]),
    ("Do you check on the people you care about?", ["Yes", "No", "Not enough"]),
    ("When did you last say sorry and mean it?", ["Recently", "I don't remember", "I never did"]),
    ("What is the last thing you deleted that still exists?", ["A message", "A photo", "A person"]),
    ("Is there a version of you that only exists on this machine?", ["Yes", "No", "More than one"]),
]


def _clean_line(line):
    return line.strip().strip('"').strip()


def _salvage_step(content):
    """Best-effort repair of a malformed / truncated model response.

    Reasoning models sometimes emit a JSON object that gets cut off before the
    closing brace, or wrap it in prose, or use curly quotes. Rather than throw
    the whole question away (and drop the player back to the offline bank — the
    reason the AI used to be invisible in play), pull out whatever is usable.
    Returns a dict with q/opts/scare, or None if nothing survives.
    """
    if not content:
        return None
    text = content.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    q = None
    m = re.search(r'"q"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if m:
        q = m.group(1)
    else:
        # Opening quote but never closed — take the rest of the string.
        m = re.search(r'"q"\s*:\s*"(.*)', text, re.S)
        if m:
            q = m.group(1)
    if not q or not q.strip():
        return None
    try:
        q = json.loads('"%s"' % q) if "\\" in q else q
    except Exception:
        pass
    q = _clean_line(q.replace("\\n", "\n"))

    opts = []
    m = re.search(r'"opts"\s*:\s*\[(.*?)\]', text, re.S)
    if m:
        try:
            opts = json.loads("[" + m.group(1) + "]")
        except Exception:
            opts = re.findall(r'"([^"]+)"', m.group(1))
    if not isinstance(opts, list):
        opts = []
    opts = [_clean_line(str(o)) for o in opts if str(o).strip()]
    if len(opts) < 2:
        opts = ["...", "..."]  # never block on missing options

    scare = None
    m = re.search(r'"scare"\s*:\s*"([^"]*)"', text)
    if m:
        scare = m.group(1).strip().lower()
        if scare not in config.AI_SCARE_NAMES:
            scare = None
    return {"q": q, "opts": opts[:4], "scare": scare}


def _auto_ollama_model():
    """Return a usable local Ollama model name, or None.

    Prefers real instruct models: pure thinking builds (qwen3 without
    "instruct") stream their chain-of-thought as the answer and burn the whole
    token budget, so they're skipped rather than silently breaking the game.
    """
    p = config.AI_PROVIDERS["ollama"]
    host = p["url"].split("/v1/")[0]
    try:
        data = requests.get(host + "/api/tags", timeout=0.6).json()
    except Exception:
        return None
    best, best_size = None, -1
    for m in data.get("models", []):
        name = m.get("name", "")
        if not name:
            continue
        if "qwen3" in name.lower() and "instruct" not in name.lower():
            continue  # thinking-only build
        size = m.get("size", 0)
        if size > best_size:
            best, best_size = name, size
    return best


def _resolve_auto():
    """Pick a provider without any setup or paid key:

    1. Ollama with a usable local model -> fully local & free (different AI)
    2. an OpenRouter key set            -> free-tier models (different AI)
    3. otherwise                        -> the relay (no key needed in the build)
    """
    model = _auto_ollama_model()
    if model:
        config.AI_PROVIDERS["ollama"]["model"] = model
        return "ollama"
    if config.AI_PROVIDERS["openrouter"].get("key"):
        return "openrouter"
    if config.AI_PROVIDERS["groq"].get("key"):
        return "groq"
    return "relay"


class ScaryAI:
    def __init__(self):
        self._session = requests.Session()
        # Build the ordered provider chain: the selected provider first, then
        # every other provider that has a key, then nothing (offline bank).
        selected = config.AI_PROVIDER
        if selected == "auto" or selected not in config.AI_PROVIDERS:
            selected = _resolve_auto()
        names = list(config.AI_PROVIDERS)
        ordered = [selected] + [n for n in names if n != selected]
        self._chain = []
        for name in ordered:
            p = config.AI_PROVIDERS.get(name)
            if p and p.get("key") and p.get("url"):
                self._chain.append(p)

    def _post(self, provider, messages):
        payload = {
            "model": provider["model"],
            "messages": messages,
            "temperature": config.AI_TEMPERATURE,
            "max_tokens": config.AI_MAX_TOKENS,
        }
        # Providers may carry extra body fields (e.g. gpt-oss wants
        # reasoning_effort="low" or it burns the budget on hidden chain-of-thought
        # and gets truncated before the JSON). Respect whatever is configured.
        extra = provider.get("extra") or {}
        if isinstance(extra, dict):
            payload.update(extra)
        headers = {"Authorization": "Bearer " + provider["key"]}
        # The relay can require a shared app token; send it when configured.
        token = provider.get("header_token")
        if token:
            headers["X-App-Token"] = token
        r = self._session.post(provider["url"], json=payload, headers=headers,
                               timeout=config.AI_TIMEOUT)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        # Some providers return the chain-of-thought in a separate field; if the
        # content holds no JSON, fall back to the reasoning field.
        if "{" not in content:
            content = msg.get("reasoning") or content
        return content

    def _parse(self, content):
        content = (content or "").strip()
        try:
            data = json.loads(content)
        except Exception:
            data = None
            match = re.search(r"\{.*\}", content, re.S)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None
            # Truncated mid-object (the common reasoning-model failure): rebuild
            # a usable step from whatever fields did arrive.
            if data is None:
                data = _salvage_step(content)
                if data is None:
                    return None
        if not isinstance(data, dict):
            return None
        q = data.get("q")
        opts = data.get("opts")
        if not isinstance(q, str) or not q.strip():
            return None
        if not isinstance(opts, list) or not (2 <= len(opts) <= 4):
            return None
        opts = [_clean_line(str(o)) for o in opts if str(o).strip()]
        if len(opts) < 2:
            return None
        scare = str(data.get("scare") or "none").strip().lower()
        if scare not in config.AI_SCARE_NAMES:
            scare = None
        return {"q": q.strip(), "opts": opts, "scare": scare}

    def _context_messages(self, run_count, history, geo=None, facts=None,
                          asked=None, duplicate_hint=False):
        seen = [h["q"] for h in history]
        # Give the model the WHOLE session, not a 5-turn window, so callbacks
        # land. Older turns get flattened to keep the prompt small.
        lines = []
        for h in history[:-8]:
            lines.append("- %s -> %s" % (h["q"], h["a"]))
        for h in history[-8:]:
            lines.append("You asked: %s\nThey answered: %s" % (h["q"], h["a"]))
        recent = "\n".join(lines) if lines else "Nothing yet."

        location = ""
        if geo and config.AI_TAILOR_TO_NATION:
            parts = [p for p in (geo.get("city"), geo.get("region"), geo.get("country")) if p]
            if parts:
                location = ("You know where the player is: %s.\n"
                            "Use this to make your question feel more personal to their "
                            "nation, without revealing how you know.\n" % ", ".join(parts))

        machine = ""
        facts = facts or {}
        bits = []
        if facts.get("name"):
            bits.append("their name is %s" % facts["name"])
        if facts.get("apps"):
            bits.append("these are open right now: %s" % ", ".join(facts["apps"][:6]))
        if facts.get("earlier_runs"):
            bits.append("in an earlier session they answered: %s" % facts["earlier_runs"])
        if bits:
            machine = ("What you can see on their machine: %s.\n"
                       "Use it sparingly and never explain how you know.\n" % "; ".join(bits))

        # Deliberately no list of which effects were already used: the context
        # stays about the player, and reuse is blocked locally in main.py.
        extra = ""
        if run_count >= 3:
            extra = ("This is the last session. There is no fourth. Get specific and "
                     "personal, and stop giving them comfortable options.\n")

        # The anti-repetition list. Session history plus every question from
        # earlier sessions, newest last, trimmed so the prompt stays small.
        forbidden = []
        seen_norm = set()
        for q in list(asked or []) + list(seen):
            nq = _norm_question(q)
            if nq and nq not in seen_norm:
                seen_norm.add(nq)
                forbidden.append(q)
        forbidden = forbidden[-60:]
        forbid_block = ("Questions they have already been asked (NEVER repeat these, "
                        "not even reworded):\n- " + "\n- ".join(forbidden) +
                        "\n\n") if forbidden else ""

        asked_n = len(seen_norm)
        topic = _TOPICS[asked_n % len(_TOPICS)]
        hint = ("You already asked one of those. Pick a completely different subject now.\n"
                if duplicate_hint else "")

        user = (
            f"Session {run_count} of 3.\n"
            f"{machine if machine else ''}"
            f"{extra if extra else ''}"
            f"{forbid_block}"
            f"{hint}"
            f"Lean this question toward: {topic}.\n"
            "Ask the next question. Keep it short and direct. Do not build on the "
            "previous answer unless it fits naturally."
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def generate_question(self, run_count, history, geo=None, facts=None,
                          asked=None):
        """Returns a question dict or None on total failure.

        Tries each configured provider exactly once (the selected one first).
        A duplicate of something already asked gets one more attempt with a
        pointed "pick a different subject" nudge; if that also duplicates, the
        caller falls back to the (already filtered) offline bank. This must
        never hang, or THINKING dots would spin forever.
        """
        blocked = {_norm_question(h["q"]) for h in history}
        blocked |= {_norm_question(q) for q in (asked or [])}
        fallback = None
        for attempt in (0, 1):
            messages = self._context_messages(
                run_count, history, geo=geo, facts=facts, asked=asked,
                duplicate_hint=bool(attempt))
            for provider in list(self._chain):
                try:
                    content = self._post(provider, messages)
                    step = self._parse(content)
                    if not step:
                        continue
                    if _norm_question(step["q"]) in blocked:
                        # Keep the first duplicate as a last resort, in case every
                        # provider keeps looping and the bank is exhausted.
                        fallback = fallback or step
                        continue
                    step["_source"] = "ai:" + str(provider.get("model", "?"))
                    return step
                except Exception:
                    continue
        return fallback


def offline_question(run_count, history, asked=None):
    """Pull from the fallback bank without ever hitting the network.

    Filters against both the current session and the persistent cross-session
    list, so the offline path is not the reason a player hears the same line
    twice. Falls back to the whole bank only if the filtered pool is empty (it
    is large enough that this effectively never happens).
    """
    used = {_norm_question(h["q"]) for h in history}
    used |= {_norm_question(q) for q in (asked or [])}
    pool = [q for q in _OFFLINE_BANK if _norm_question(q[0]) not in used]
    if not pool:
        # Everything has been asked at some point. Reuse the lines asked
        # longest ago rather than a random one from the whole bank, so a very
        # long-lived save still rotates instead of looping a recent question.
        asked_norm = [_norm_question(q) for q in (asked or [])]

        def _age(item):
            nq = _norm_question(item[0])
            try:
                return asked_norm.index(nq)
            except ValueError:
                return -1

        pool = sorted(_OFFLINE_BANK, key=_age)[:max(12, len(_OFFLINE_BANK) // 3)]
    q, opts = random.choice(pool)
    scare = None
    # Escalation holds even offline: later sessions fire scares far more often.
    chance = {1: 0.25, 2: 0.5, 3: 0.75}.get(run_count, 0.25)
    if random.random() < chance:
        scare = random.choice(config.AI_SCARE_NAMES)
    return {"q": q, "opts": opts, "scare": scare, "_source": "offline"}


def next_question(ai, run_count, history, geo=None, facts=None, asked=None):
    """Best-effort AI question with guaranteed offline fallback."""
    if ai is not None:
        step = ai.generate_question(run_count, history, geo=geo, facts=facts,
                                    asked=asked)
        if step:
            return step
    return offline_question(run_count, history, asked=asked)
