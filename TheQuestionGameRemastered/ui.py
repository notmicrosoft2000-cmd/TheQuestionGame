"""Rendering helpers: scaled fonts, wrapped text, VHS/static/corruption
overlays, starfield, menu silhouettes, webcam feed, and badge toast."""
import math
import os
import queue
import random
import threading
import time

import numpy as np
import pygame

from . import audio
from . import config
from . import persistence

FONT_NAME = pygame.font.match_font("courier")


def get_scaled_fonts(game_state, w, h):
    base = min(w, h)
    mult = game_state.get("settings", {}).get("text_size", 1.0)
    large_sz = max(28, int(base * 0.09 * mult))
    med_sz = max(16, int(base * 0.052 * mult))
    small_sz = max(11, int(base * 0.033 * mult))
    return (
        pygame.font.Font(FONT_NAME, large_sz),
        pygame.font.Font(FONT_NAME, med_sz),
        pygame.font.Font(FONT_NAME, small_sz),
    )


def render_wrapped_text(surface, text, font, color, start_x, start_y, max_width, angle=0):
    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        if "\n" in word:
            parts = word.split("\n")
            current_line += parts[0]
            lines.append(current_line)
            current_line = parts[1] + " "
        else:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
    lines.append(current_line)
    for i, line in enumerate(lines):
        surf = font.render(line.strip(), True, color)
        if angle != 0:
            surf = pygame.transform.rotate(surf, angle)
        surface.blit(surf, (start_x, start_y + i * (font.get_linesize() + 4)))


def render_animated_wrapped_text(surface, text, font, color, start_x, start_y, max_width, t, sway_amp=2, alpha_base=200):
    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        if "\n" in word:
            parts = word.split("\n")
            current_line += parts[0]
            lines.append(current_line)
            current_line = parts[1] + " "
        else:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
    lines.append(current_line)
    for i, line in enumerate(lines):
        sway_x = int(math.sin(t * 0.8 + i * 0.6) * sway_amp)
        pulse = 0.5 + 0.5 * math.sin(t * 1.2 + i * 0.9)
        a = int(max(0, min(255, alpha_base + int(pulse * 55))))
        surf = font.render(line.strip(), True, color)
        try:
            surf.set_alpha(a)
        except Exception:
            pass
        surface.blit(surf, (start_x + sway_x, start_y + i * (font.get_linesize() + 4)))


def apply_vhs_effects(surface, w, h, game_state):
    intensity = game_state.get("settings", {}).get("vhs_intensity", 1.0)
    if intensity <= 0:
        return
    bar_y = int(time.time() * 90) % h
    if random.random() < 0.12 * intensity:
        pygame.draw.rect(surface, (15, 15, 15), (0, bar_y, w, random.randint(int(15 * intensity), max(1, int(40 * intensity)))))
    step = max(2, int(4 / intensity)) if intensity > 0 else 4
    for y in range(0, h, step):
        pygame.draw.line(surface, (5, 5, 5), (0, y), (w, y), 1)
    if intensity >= 1.5 and random.random() < 0.06:
        gy = random.randint(0, h)
        pygame.draw.rect(surface, (30, 0, 0), (0, gy, w, random.randint(2, 8)))


def apply_shadow_static(surface, w, h, intensity=1.0):
    if random.random() < 0.02 * intensity:
        sx = random.randint(int(w * 0.1), int(w * 0.8))
        sy = random.randint(int(h * 0.2), int(h * 0.6))
        sh = random.randint(int(h * 0.25), int(h * 0.4))
        sw = max(20, int(sh * 0.35))
        shape = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for _ in range(40):
            bx = random.randint(0, sw - 4)
            by = random.randint(0, sh - 4)
            shade = random.randint(10, 35)
            pygame.draw.rect(shape, (shade, shade, shade, 160), (bx, by, 4, 4))
        surface.blit(shape, (sx, sy))
        if random.random() < 0.5:
            audio.play_static_burst()


def apply_flicker(surface, w, h):
    """Full-screen white/black strobe flicker."""
    r = random.random()
    if r < 0.25:
        surface.fill((255, 255, 255))
    elif r < 0.35:
        surface.fill((0, 0, 0))
    else:
        for _ in range(int(w * h / 9000)):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            surface.set_at((x, y), (random.choice([120, 200, 255]), random.choice([120, 200, 255]), random.choice([120, 200, 255])))


def apply_corruption(surface, w, h, t):
    """Glitchy glyph burst — scrambles horizontal strips and drops noise."""
    if random.random() < 0.5:
        y = random.randint(0, h - 1)
        slice_h = random.randint(2, 10)
        src = pygame.Rect(0, y, w, slice_h)
        dx = random.choice([-40, -20, 20, 40, 0])
        dest = src.move(dx, 0)
        try:
            region = surface.subsurface(src).copy()
            if dx < 0:
                surface.blit(region, (max(0, dest.x), dest.y))
            else:
                surface.blit(region, (min(w - region.get_width(), dest.x), dest.y))
        except Exception:
            pass
    for _ in range(30):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        c = random.choice([(200, 0, 0), (0, 200, 0), (0, 0, 200), (255, 255, 255)])
        surface.set_at((x, y), c)


# --- Menu decoration --------------------------------------------------------
_MENU_LOGO_MARKS = ["NEPTUNE", "AXIOM", "GRAYLINE", "VESTIGE", "HOLLOWCO", "OBSIDIAN SYS"]
_menu_silhouettes = None
_menu_logo_state = {"mark": None, "shown_at": 0, "x": 0, "y": 0, "next_at": 0}


def _build_menu_silhouettes(w, h):
    sils = []
    for i in range(3):
        sh = random.randint(int(h * 0.32), int(h * 0.5))
        sw = max(24, int(sh * 0.3))
        shape = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for _ in range(90):
            bx = random.randint(0, sw - 3)
            by = random.randint(0, sh - 3)
            shade = random.randint(8, 22)
            shape.fill((shade, shade, shade, 130), (bx, by, 3, 3))
        sils.append({
            "surf": shape,
            "base_x": int(w * (0.62 + i * 0.13)),
            "base_y": int(h * (0.18 + i * 0.12)),
            "phase": random.uniform(0, 6.28),
        })
    return sils


def draw_menu_decorations(surface, w, h, current_time, font_small):
    global _menu_silhouettes, _menu_logo_state
    if _menu_silhouettes is None or len(_menu_silhouettes) == 0:
        _menu_silhouettes = _build_menu_silhouettes(w, h)

    for sil in _menu_silhouettes:
        dx = int(math.sin(current_time * 0.4 + sil["phase"]) * 14)
        dy = int(math.cos(current_time * 0.3 + sil["phase"]) * 8)
        surface.blit(sil["surf"], (sil["base_x"] + dx, sil["base_y"] + dy))

    if _menu_logo_state["next_at"] == 0:
        _menu_logo_state["next_at"] = current_time + random.uniform(2.0, 5.0)
    if current_time >= _menu_logo_state["next_at"] and _menu_logo_state["mark"] is None:
        _menu_logo_state["mark"] = random.choice(_MENU_LOGO_MARKS)
        _menu_logo_state["shown_at"] = current_time
        _menu_logo_state["x"] = random.randint(int(w * 0.6), max(int(w * 0.6) + 1, w - 160))
        _menu_logo_state["y"] = random.randint(int(h * 0.15), int(h * 0.75))
    if _menu_logo_state["mark"] is not None:
        if current_time - _menu_logo_state["shown_at"] < 0.25:
            color = (random.randint(60, 110), 0, 0)
            surf = font_small.render(_menu_logo_state["mark"], True, color)
            surface.blit(surf, (_menu_logo_state["x"], _menu_logo_state["y"]))
        else:
            _menu_logo_state["mark"] = None
            _menu_logo_state["next_at"] = current_time + random.uniform(2.0, 5.0)


def build_starfield(w, h):
    region_x = int(w * 0.6)
    stars = []
    count = 60
    for _ in range(count):
        stars.append({
            "x": random.randint(region_x, max(region_x + 6, w - 12)),
            "y": random.randint(40, h - 60),
            "size": random.choice([1, 1, 1, 2]),
            "phase": random.uniform(0, 6.28),
            "b": random.uniform(90, 170),
        })
    galaxies = []
    for _ in range(2):
        galaxies.append({
            "x": random.randint(region_x + 30, max(region_x + 40, w - 120)),
            "y": random.randint(70, max(120, h - 180)),
            "r": random.randint(30, 70),
        })
    return {"stars": stars, "galaxies": galaxies}


def draw_starfield(surface, w, h, t, starfield):
    for s in starfield["stars"]:
        tw = 0.5 + 0.5 * math.sin(t * 2.0 + s["phase"])
        b = int(max(80, min(255, s["b"] * (0.6 + 0.4 * tw))))
        c2 = int(min(255, int(b * 1.1)))
        color = (int(b), int(b), c2)
        if s["size"] <= 1:
            try:
                surface.set_at((s["x"], s["y"]), color)
            except Exception:
                pass
        else:
            pygame.draw.circle(surface, color, (s["x"], s["y"]), s["size"])
    for g in starfield["galaxies"]:
        for r in range(3):
            alpha = int(30 / (r + 1))
            col = (120 + r * 30, 110 + r * 20, 200 - r * 40, alpha)
            blob = pygame.Surface((g["r"] * 2, g["r"] * 2), pygame.SRCALPHA)
            pygame.draw.circle(blob, col, (g["r"], g["r"]), int(g["r"] * (0.6 - r * 0.18)))
            surface.blit(blob, (g["x"] - g["r"], g["y"] - g["r"]))


def draw_badge_toast(surface, w, h, badge_id, shown_at, font_medium, font_small, now):
    age = now - shown_at
    if age > 4.5:
        return False
    alpha = int(255 * max(0, min(1, 4.5 - age)))
    if badge_id not in persistence.BADGE_CATALOG:
        return True
    name, desc = persistence.BADGE_CATALOG[badge_id]
    box = pygame.Surface((max(200, int(w * 0.5)), 76), pygame.SRCALPHA)
    box.fill((10, 0, 0, 200))
    pygame.draw.rect(box, (80, 0, 0, 255), box.get_rect(), 2)
    t1 = font_small.render("BADGE EARNED", True, (150, 0, 0))
    t2 = font_medium.render(name, True, (200, 200, 200))
    t3 = font_small.render(desc, True, (120, 120, 120))
    for surf, (x, y) in ((t1, (16, 8)), (t2, (16, 24)), (t3, (16, 52))):
        box.blit(surf, (x, y))
    box.set_alpha(alpha)
    bx = int(w * 0.5 - box.get_width() / 2)
    by = int(h * 0.78)
    surface.blit(box, (bx, by))
    return True


# --- Webcam (cv2 worker thread) ----------------------------------------------
camera = None
webcam_surface = None
webcam_active = False
webcam_start_time = 0
_webcam_frame_queue = queue.Queue(maxsize=1)


def start_webcam_nonblocking():
    global camera, webcam_active, webcam_start_time

    def _open():
        global camera, webcam_active, webcam_start_time
        try:
            import cv2
            cam = cv2.VideoCapture(0)
            if cam.isOpened():
                camera = cam
                webcam_active = True
                webcam_start_time = time.time()
                threading.Thread(target=_webcam_capture_loop, args=(cam,), daemon=True).start()
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def _webcam_capture_loop(cam):
    global webcam_active
    try:
        import cv2
        import numpy as _np
        while webcam_active and cam is not None:
            if time.time() - webcam_start_time > config.WEBCAM_DURATION:
                break
            try:
                ret, frame = cam.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = cv2.resize(frame, (240, 180))
                    frame[:, :, 1] = _np.clip(frame[:, :, 1].astype(_np.int32) + 30, 0, 255).astype(_np.uint8)
                    raw = _np.transpose(frame, (1, 0, 2)).tobytes()
                    size = (frame.shape[0], frame.shape[1])
                    if _webcam_frame_queue.full():
                        try:
                            _webcam_frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    _webcam_frame_queue.put((raw, size))
            except Exception:
                pass
            time.sleep(1 / 30)
    except Exception:
        pass
    if cam is not None:
        try:
            cam.release()
        except Exception:
            pass


def update_webcam_surface():
    global webcam_surface, camera, webcam_active
    if not webcam_active or camera is None:
        return
    if time.time() - webcam_start_time > config.WEBCAM_DURATION:
        webcam_active = False
        try:
            camera.release()
        except Exception:
            pass
        camera = None
        webcam_surface = None
        return
    try:
        raw, size = _webcam_frame_queue.get_nowait()
    except queue.Empty:
        return
    try:
        surf = pygame.image.fromstring(raw, size, "RGB")
        elapsed = time.time() - webcam_start_time
        if elapsed > config.WEBCAM_DURATION - 2:
            alpha = int(255 * (config.WEBCAM_DURATION - elapsed) / 2)
        else:
            alpha = 255
        surf.set_alpha(max(0, alpha))
        webcam_surface = surf
    except Exception:
        pass


# --- Async picture display ---------------------------------------------------
_picture_result_queue = queue.Queue()


def request_picture_scaled_async(path, max_w, max_h):
    def _worker():
        try:
            img = pygame.image.load(path).convert_alpha()
            iw, ih = img.get_size()
            if iw == 0 or ih == 0:
                _picture_result_queue.put(None)
                return
            scale = min(max_w / iw, max_h / ih)
            new_w, new_h = max(1, int(iw * scale)), max(1, int(ih * scale))
            scaled = pygame.transform.smoothscale(img, (new_w, new_h))
            raw = pygame.image.tostring(scaled, "RGBA")
            _picture_result_queue.put((raw, (new_w, new_h)))
        except Exception:
            _picture_result_queue.put(None)

    threading.Thread(target=_worker, daemon=True).start()


def poll_picture_result():
    try:
        result = _picture_result_queue.get_nowait()
    except queue.Empty:
        return None
    if result is None:
        return None
    raw, size = result
    try:
        return pygame.image.fromstring(raw, size, "RGBA")
    except Exception:
        return None
