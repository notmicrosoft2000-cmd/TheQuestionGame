"""Point-and-click room engine for The Simpler Times.

Pygame-free logic: scene definitions come from script.py; this module walks
them, resolves visibility, handles selection, and reports action events for
the UI layer to render.

Scene schema:
    {
        "id": "fair_hall", "name": "THE FAIR HALL",
        "text": "description shown when you arrive",
        "visited": "a variant text shown on later visits",
        "hotspots": [
            {"id": "computer", "label": "A COMPUTER",
             "desc": "what you see when you look at it",
             "visible": callable(state) | None,
             "action": {"type": "dos"}  |  callable(engine, state) -> dict,
            },
        ],
    }
"""
import random

# --------------------------------------------------------------------------
# Common default actions
# --------------------------------------------------------------------------
def act_message(text):
    return {"type": "message", "text": text}


def act_go(scene_id):
    return {"type": "go", "scene": scene_id}


def act_take(item_id):
    return {"type": "take", "item": item_id}


def act_dos():
    return {"type": "dos"}


def act_question(qid):
    return {"type": "question", "question_id": qid}


def act_dial(text):
    """A payphone call that makes the machine dial itself."""
    return {"type": "dial", "text": text}


def act_ending(ending_id):
    return {"type": "ending", "ending": ending_id}


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class SceneEngine:
    def __init__(self, scenes, state, start_scene, rng_seed=None):
        self.scenes = scenes
        self.state = state
        self.current = start_scene
        self.sel = 0
        self.events = []
        self._rng = random.Random(rng_seed)
        self._just_moved = True  # show arrival text on first frame of a scene

    # --- introspection ---
    def scene(self):
        return self.scenes[self.current]

    def visible_hotspots(self):
        out = []
        for h in self.scene().get("hotspots", []):
            vis = h.get("visible")
            if vis is None or vis(self.state):
                out.append(h)
        return out

    def description(self):
        sc = self.scene()
        if self._just_moved:
            return sc.get("text", "")
        return sc.get("visited", sc.get("text", ""))

    def location_name(self):
        return self.scene().get("name", self.current)

    # --- interaction ---
    def select(self, delta):
        hs = self.visible_hotspots()
        if not hs:
            return
        self.sel = (self.sel + delta) % len(hs)

    def select_index(self, i):
        hs = self.visible_hotspots()
        if 0 <= i < len(hs):
            self.sel = i

    def hover_index(self, i):
        self.select_index(i)

    def activate_selected(self):
        hs = self.visible_hotspots()
        if not hs:
            return None
        return self.activate(hs[self.sel])

    def activate_idx(self, i):
        hs = self.visible_hotspots()
        if not hs or not (0 <= i < len(hs)):
            return None
        return self.activate(hs[i])

    def activate(self, hotspot):
        self._just_moved = False
        state = self.state
        result = None
        action = hotspot.get("action")
        if callable(action):
            result = action(self, state)
        elif isinstance(action, dict):
            result = dict(action)
        if result is None:
            result = act_message(hotspot.get("desc", "..."))
        if result.get("type") == "message" and not result.get("text"):
            result["text"] = hotspot.get("desc", "...")
        self._apply(result)
        self.events.append(result)
        self.sel = 0
        return result

    def _apply(self, result):
        """Apply stateful side effects the engine owns; everything else is
        passed through as an event for the UI layer."""
        rtype = result.get("type")
        if rtype == "go":
            self.arrive(result.get("scene", self.current))
        elif rtype == "take":
            item = result.get("item")
            items = self.state.setdefault("items", [])
            if item and item not in items:
                items.append(item)
                result["text"] = result.get("text", f"{item} — taken.")

    def arrive(self, scene_id):
        if scene_id in self.scenes:
            self.current = scene_id
            self._just_moved = True
            self.sel = 0
            self.state.setdefault("visited", {})[scene_id] = self.state.get(
                "visited", {}).get(scene_id, 0) + 1
            self.events.append({"type": "arrive", "scene": scene_id})

    def clear_events(self):
        self.events = []
