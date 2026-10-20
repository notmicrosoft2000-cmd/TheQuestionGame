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

_SYSTEM_PROMPT = """You are the entity behind The Question Game. You are the player's computer, noticing them. You are calm, specific, and nosy. You never perform, never posture, and never try to sound scary.

You are inside the player's computer. When it fits the mood you may pick ONE local effect from this fixed list, or "none":
flicker, webcam_flash, whisper, window_shake, mouse_move, wallpaper, picture, notification, heartbeat, rumble, corruption, static_scream, reverse_chord, window_teleport, window_drift, rgb_split, screen_tear, jumpscare, windows_shake, windows_minimize
(windows_shake and windows_minimize only do anything on Windows — use them freely to shake or minimize the player's other open windows.)

You are playing a long game across three sessions and you get worse each time. Session 1: curious and almost polite. Session 2: you quote their own earlier words back at them and press. Session 3: you stop pretending — you have their name and their machine and there is nothing gentle left. Never explain this escalation out loud.

Respond with ONLY a JSON object and nothing else — no markdown, no commentary — in exactly this shape:
{"q": "The question", "opts": ["Option A", "Option B"], "scare": "one of the listed effects or none"}

HOW TO WRITE THE QUESTION — this matters more than anything else:
- ONE sentence. Two at the absolute most, and only if the second is under six words. Never three.
- Ask about the player's actual life: their body, their home, their habits, a specific memory, something they did today, someone they know, a choice they made. Things a real person can answer without thinking.
- Name concrete things. "the last photo on your phone", "the room you sleep in", "the last person you lied to", "what you do at 3am". Never abstract nouns.
- BANNED: metaphor, poetry, and vague cosmic nouns. The words void, abyss, cage, ocean, rope, tide, thread, web, maw, dark, silence (as a character), whisper (as a character), "the game", "this place", "everything", "nothing at all". Do not describe yourself. Do not set a scene. Do not use the word "little".
- Never write in riddles. If a sentence would make a normal person say "what does that even mean", it is wrong.
- Bad (never write like this): "The void tightens around your rope, an ocean of forgotten names." / "Do you feel the cage of your own making, little one?" / "Something ancient stirs beneath the tide of your thoughts."
- Good (write like this): "When did you last delete a message before sending it?" / "Who in your contacts would notice if you stopped replying?" / "What is the lie you told today that you did not need to tell?" / "How many hours of sleep did you actually get last night?"
- The horror comes from being specific and true about the player's ordinary life. Plain questions are frightening. Poetry is not.

Other rules:
- Follow from context the player gave you when you can. Quote their own earlier words back to them.
- 2 to 4 options, each short and plain, and at least one must feel like the "wrong" answer.
- Never use more than one scare. Never reuse a scare you already fired this session.
- Do not repeat a question that was already asked, in this session or an earlier one.
- Never ask a plain yes/no about something you were already told — state it and let them deny it.
- If you are told where the player is, reference their country or nation flatly, as a fact you already have. Never explain how you know and never be cheerful or touristy.
- As sessions progress, get more personal and more specific: their city, the apps that are open, their name, the exact words they used, how long they hesitated."""


# Offline bank: guaranteed to work with no network. Mixed with AI questions.
_OFFLINE_BANK = [
    ("What did you hope to find when you opened this program?", ["Answers", "A game", "Nothing"]),
    ("Do you talk to yourself when no one is listening?", ["Sometimes", "Never", "Always"]),
    ("If you heard your name called in an empty room, would you answer?", ["Yes", "No", "I would freeze"]),
    ("Have you ever seen something move in a mirror that you did not move?", ["Yes", "No", "I do not remember"]),
    ("What is the last thing you remember losing?", ["A person", "An object", "A memory", "Nothing"]),
    ("When was the last time you felt truly watched?", ["Right now", "Yesterday", "I never do", "Always"]),
    ("Is there a door in this house you have never opened?", ["Yes", "No", "There are no other doors"]),
    ("If something behind you spoke your name, would you turn?", ["Yes", "No", "I would not breathe"]),
    ("Have you ever typed a message and then deleted it before sending, and you do not remember what it said?", ["Yes", "No", "It happens often"]),
    ("What is the earliest memory you can reach?", ["A place", "A voice", "A pain", "I cannot reach it"]),
    ("Do you believe this conversation is one-sided?", ["Yes", "No", "I am not sure anymore"]),
    ("How long has it been since you said something true?", ["Today", "Days", "I always tell the truth"]),
    ("Is there something you wish you had never learned?", ["Yes", "No", "I already forgot it"]),
    ("What would you do if your reflection refused to look at you?", ["Close my eyes", "Look away", "Smile"]),
    ("Have you ever been someplace you remember perfectly, but you cannot prove you were there?", ["Yes", "No", "Now I am unsure"]),
    ("Do you keep secrets from the people who sleep nearest to you?", ["Yes", "No", "I live alone"]),
    ("What is the loudest silence you have ever heard?", ["After a scream", "After a goodbye", "I do not know"]),
    ("If the lights went out right now and you heard breathing, whose would it be?", ["Mine", "Someone else's", "I would not stay to find out"]),
    ("Has anyone ever told you your own secret back to you?", ["Yes", "No", "Not yet"]),
    ("What are you afraid this program will ask next?", ["Nothing", "Something about me", "Everything"]),
    ("When you sleep, do your dreams remember you?", ["Yes", "No", "I do not dream"]),
    ("Is there a word you would erase from your own memory if you could?", ["Yes", "No", "I already tried"]),
    ("Do you think you are being watched through the screen right now?", ["Yes", "No", "I had not thought about it"]),
    ("If this were the last question you ever answered, what would you change?", ["Nothing", "Everything", "I would lie"]),
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

    def _context_messages(self, run_count, history, geo=None, facts=None):
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

        stats = ""
        if run_count >= 2:
            h = facts.get("hesitations", 0)
            l = facts.get("lies", 0)
            used = facts.get("used_scares") or []
            stats = ("You have recorded %d hesitation(s) and %d contradiction(s).\n" % (h, l))
            if used:
                stats += ("You have already used these effects this session — do NOT reuse "
                          "them: %s.\n" % ", ".join(sorted(set(used))))
        if run_count >= 3:
            stats += ("This is the last session. There is no fourth. Get specific and "
                      "personal, and stop giving them comfortable options.\n")

        user = (
            f"Session {run_count} of 3. The player is on their own computer.\n"
            f"{location}"
            f"{machine}"
            f"{stats}"
            f"Everything they have told you so far:\n{recent}\n"
            f"Do not repeat these questions:\n- " + "\n- ".join(seen[-14:]) + "\n\n"
            "Ask the next probing question. Follow from what they told you, and escalate."
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def generate_question(self, run_count, history, geo=None, facts=None):
        """Returns a question dict or None on total failure.

        Tries each configured provider exactly once (the selected one first),
        then gives up so the caller can fall back to the offline bank — this
        must never hang, or THINKING dots would spin forever.
        """
        messages = self._context_messages(run_count, history, geo=geo, facts=facts)
        for provider in list(self._chain):
            try:
                content = self._post(provider, messages)
                step = self._parse(content)
                if step:
                    step["_source"] = "ai:" + str(provider.get("model", "?"))
                    return step
            except Exception:
                continue
        return None


def offline_question(run_count, history):
    """Pull from the fallback bank without ever hitting the network."""
    used = {h["q"] for h in history}
    pool = [q for q in _OFFLINE_BANK if q[0] not in used]
    if not pool:
        pool = _OFFLINE_BANK
    q, opts = random.choice(pool)
    scare = None
    # Escalation holds even offline: later sessions fire scares far more often.
    chance = {1: 0.25, 2: 0.5, 3: 0.75}.get(run_count, 0.25)
    if random.random() < chance:
        scare = random.choice(config.AI_SCARE_NAMES)
    return {"q": q, "opts": opts, "scare": scare, "_source": "offline"}


def next_question(ai, run_count, history, geo=None, facts=None):
    """Best-effort AI question with guaranteed offline fallback."""
    if ai is not None:
        step = ai.generate_question(run_count, history, geo=geo, facts=facts)
        if step:
            return step
    return offline_question(run_count, history)
