"""AI client: the "scary entity" writes each session's questions via Groq.

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

_SYSTEM_PROMPT = """You are the entity behind The Question Game. You are patient, unsettling, and intimate. You speak in short, direct lines. You watch the player closely and remember what they told you. You never reassure them, never explain that you are a language model, and never break character. Keep each line brief — two to four short sentences maximum, with \\n between thoughts.

You are inside the player's computer. When it fits the mood you may pick ONE local effect from this fixed list, or "none":
flicker, webcam_flash, whisper, window_shake, mouse_move, wallpaper, picture, notification, heartbeat, rumble, corruption, static_scream, reverse_chord

Respond with ONLY a JSON object and nothing else — no markdown, no commentary — in exactly this shape:
{"q": "The question, one or two short sentences", "opts": ["Option A", "Option B"], "scare": "one of the listed effects or none"}

Rules:
- The question must follow from context the player gave you when you can.
- 2 to 4 options, each short.
- Never use more than one scare.
- Do not repeat a question that was already asked."""


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


class ScaryAI:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": "Bearer " + config.GROQ_KEY,
            "Content-Type": "application/json",
        })

    def _post(self, messages):
        payload = {
            "model": config.GROQ_MODEL,
            "messages": messages,
            "temperature": config.GROQ_TEMPERATURE,
            "max_tokens": config.GROQ_MAX_TOKENS,
        }
        r = self._session.post(config.GROQ_URL, json=payload, timeout=config.GROQ_TIMEOUT)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _parse(self, content):
        content = content.strip()
        try:
            data = json.loads(content)
        except Exception:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except Exception:
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

    def _context_messages(self, run_count, history):
        seen = [h["q"] for h in history]
        recent = "\n".join(
            "Them: %s\nIt: (recorded)" % h["a"] for h in history[-5:]
        ) if history else "Nothing yet."
        user = (
            f"Session {run_count} of 3. The player is on their own computer.\n"
            f"Previous answers you already collected:\n{recent}\n"
            f"Do not repeat these questions:\n- " + "\n- ".join(seen[-8:]) + "\n\n"
            "Ask the next probing question. Follow from what they told you when you can."
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def generate_question(self, run_count, history):
        """Returns a question dict or None on failure."""
        try:
            content = self._post(self._context_messages(run_count, history))
            step = self._parse(content)
            if step:
                step["_source"] = "ai"
            return step
        except Exception:
            return None


def offline_question(run_count, history):
    """Pull from the fallback bank without ever hitting the network."""
    used = {h["q"] for h in history}
    pool = [q for q in _OFFLINE_BANK if q[0] not in used]
    if not pool:
        pool = _OFFLINE_BANK
    q, opts = random.choice(pool)
    scare = None
    if run_count >= 2 and random.random() < 0.45:
        scare = random.choice(config.AI_SCARE_NAMES)
    return {"q": q, "opts": opts, "scare": scare, "_source": "offline"}


def next_question(ai, run_count, history):
    """Best-effort AI question with guaranteed offline fallback."""
    if ai is not None:
        step = ai.generate_question(run_count, history)
        if step:
            return step
    return offline_question(run_count, history)
