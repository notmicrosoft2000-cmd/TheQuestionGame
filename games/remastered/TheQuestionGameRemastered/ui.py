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

# Font choices offered in Settings. Each maps to candidate names; the first that
# resolves wins. "Courier" prefers the bundled asset so packaged builds always
# have a face.
FONT_CHOICES = {
    "Courier":  ["__bundled__", "couriernew", "courier", "monospace"],
    "Terminal": ["consolas", "monospace", "couriernew", "courier"],
    "Mono":     ["dejavusansmono", "liberationmono", "notosansmono", "monospace"],
    "Sans":     ["dejavusans", "liberationsans", "arial", "verdana"],
    "Serif":    ["dejavuserif", "liberationserif", "timesnewroman", "georgia"],
    "Comic":    ["comicsansms", "comicsans", "fantasque", "chalkboard"],
}
DEFAULT_FONT = "Courier"

_font_path_cache = {}
_font_obj_cache = {}


def resolve_font_path(label):
    """Map a Settings font label to a usable font file (or None)."""
    key = label or DEFAULT_FONT
    if key in _font_path_cache:
        return _font_path_cache[key]
    path = None
    for cand in FONT_CHOICES.get(key, FONT_CHOICES[DEFAULT_FONT]):
        if cand == "__bundled__":
            try:
                p = config.asset_path("courier.ttf")
                if p and os.path.exists(p):
                    path = p
                    break
            except Exception:
                pass
            continue
        try:
            p = pygame.font.match_font(cand)
        except Exception:
            p = None
        if p:
            path = p
            break
    _font_path_cache[key] = path
    return path


def _font(label, size, bold=False):
    key = (label, size, bold)
    f = _font_obj_cache.get(key)
    if f is None:
        try:
            f = pygame.font.Font(resolve_font_path(label), size)
        except Exception:
            f = pygame.font.Font(FONT_NAME, size)
        try:
            f.set_bold(bold)
        except Exception:
            pass
        _font_obj_cache[key] = f
    return f


def get_scaled_fonts(game_state, w, h):
    base = min(w, h)
    s = game_state.get("settings", {})
    mult = s.get("text_size", 1.0)
    label = s.get("font", DEFAULT_FONT)
    large_sz = max(28, int(base * 0.09 * mult))
    med_sz = max(16, int(base * 0.052 * mult))
    small_sz = max(11, int(base * 0.033 * mult))
    return (
        _font(label, large_sz),
        _font(label, med_sz),
        _font(label, small_sz),
    )


def get_tiny_font(game_state, w, h, factor=0.027):
    """One extra, smaller font for the dense explanatory blocks.

    The ONLINE screen has to explain the room *and* list the room *and* offer
    its options inside an 800x600 window. The explanation gets this one.
    """
    base = min(w, h)
    s = game_state.get("settings", {})
    mult = s.get("text_size", 1.0)
    label = s.get("font", DEFAULT_FONT)
    size = max(10, int(base * factor * mult))
    return _font(label, size)


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


_scanline_cache = {}


def _get_scanline_overlay(w, h, step):
    """Pre-rendered horizontal scanline overlay, keyed by size + line spacing."""
    surf = _scanline_cache.get((w, h, step))
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, step):
            pygame.draw.line(surf, (5, 5, 5, 140), (0, y), (w, y), 1)
        try:
            surf = surf.convert_alpha()
        except Exception:
            pass
        _scanline_cache[(w, h, step)] = surf
    return surf


def apply_vhs_effects(surface, w, h, game_state):
    sset = game_state.get("settings", {}) or {}
    intensity = sset.get("vhs_intensity", 1.0)
    if intensity <= 0:
        return
    perf = str(sset.get("performance_mode", "Medium")).lower()
    crt_enabled = bool(sset.get("crt_enabled", True)) and perf != "low"
    scanlines_enabled = bool(sset.get("scanlines_enabled", True)) and crt_enabled
    tube_curvature_enabled = bool(sset.get("tube_curvature_enabled", True)) and crt_enabled
    phosphor_mask_enabled = bool(sset.get("phosphor_mask_enabled", True)) and crt_enabled
    c_int = float(sset.get("crt_intensity", 1.0))
    eff = intensity * c_int
    if eff <= 0:
        return
    if perf == "low":
        scanlines_enabled = False
        tube_curvature_enabled = False
        phosphor_mask_enabled = False
    bar_y = int(time.time() * 90) % h
    if random.random() < 0.12 * eff:
        pygame.draw.rect(surface, (15, 15, 15), (0, bar_y, w, random.randint(int(15 * eff), max(1, int(40 * eff)))))
    if scanlines_enabled:
        step = max(2, int(4 / eff)) if eff > 0 else 4
        surface.blit(_get_scanline_overlay(w, h, step), (0, 0))
    if eff >= 1.5 and random.random() < 0.06:
        gy = random.randint(0, h)
        pygame.draw.rect(surface, (30, 0, 0), (0, gy, w, random.randint(2, 8)))


_static_blob_cache = []


def _get_static_blobs():
    """Pre-generate 3 shadow-blob sprites once; triggers just blit a random one."""
    if not _static_blob_cache:
        for _ in range(3):
            sw = random.randint(60, 140)
            sh = random.randint(120, 240)
            shape = pygame.Surface((sw, sh), pygame.SRCALPHA)
            for _ in range(40):
                bx = random.randint(0, max(0, sw - 4))
                by = random.randint(0, max(0, sh - 4))
                shade = random.randint(10, 35)
                pygame.draw.rect(shape, (shade, shade, shade, 160), (bx, by, 4, 4))
            try:
                shape = shape.convert_alpha()
            except Exception:
                pass
            _static_blob_cache.append(shape)
    return _static_blob_cache


def apply_shadow_static(surface, w, h, intensity=1.0):
    if random.random() < 0.02 * intensity:
        blobs = _get_static_blobs()
        shape = random.choice(blobs)
        sx = random.randint(int(w * 0.1), int(w * 0.8))
        sy = random.randint(int(h * 0.2), int(h * 0.6))
        surface.blit(shape, (sx, sy))
        if random.random() < 0.5:
            audio.play_static_burst()


_noise_tile_cache = {}


def _get_noise_tile(seed):
    """Pre-rendered white-noise tile; flicker blits it at random offsets."""
    tile = _noise_tile_cache.get(seed)
    if tile is None:
        rng = random.Random(seed)
        tile = pygame.Surface((128, 128))
        for y in range(0, 128, 2):
            for x in range(0, 128, 2):
                v = rng.choice([120, 200, 255])
                tile.set_at((x, y), (v, v, v))
        _noise_tile_cache[seed] = tile
    return tile


def apply_flicker(surface, w, h):
    """Full-screen white/black strobe flicker."""
    r = random.random()
    if r < 0.25:
        surface.fill((255, 255, 255))
    elif r < 0.35:
        surface.fill((0, 0, 0))
    else:
        tile = _get_noise_tile(random.randint(0, 3))
        for _ in range(3):
            surface.blit(tile, (random.randint(-64, w), random.randint(-64, h)))


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


# --- Ambient animations -----------------------------------------------------
# Pure visual dressing: a breathing vignette, drifting ash, a rolling scan
# band, a pulsing title bloom, and a blinking typewriter caret. Nothing here
# reads input, makes sound, or touches game state.

_vignette_profile = {}
_vignette_cache = {}
_dust_state = {}


def _get_vignette_profile(w, h):
    key = (w, h)
    p = _vignette_profile.get(key)
    if p is None:
        cx, cy = w / 2.0, h / 2.0
        max_d = math.hypot(cx, cy) or 1.0
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_d
        p = (np.clip(d, 0.0, 1.0) ** 2 * 255).astype(np.uint8)
        _vignette_profile[key] = p
    return p


def _get_vignette_surface(w, h):
    """Pre-rendered vignette at full strength; animate cheaply via set_alpha."""
    surf = _vignette_cache.get((w, h))
    if surf is None:
        profile = _get_vignette_profile(w, h)
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[:, :, 3] = profile
        surf = pygame.image.frombuffer(arr.tobytes(), (w, h), "RGBA").copy()
        try:
            surf = surf.convert_alpha()  # display format: ~16x faster blits
        except Exception:
            pass
        _vignette_cache[(w, h)] = surf
    return surf


def apply_vignette(surface, w, h, t=0.0, strong=False):
    """Breathing radial darkness — the room goes dim, then lets go."""
    base = 110 if strong else 80
    amt = int(max(24, min(210, base + 14 * math.sin(t * 1.1))))
    try:
        v = _get_vignette_surface(w, h)
        v.set_alpha(amt)
        surface.blit(v, (0, 0))
    except Exception:
        pass


def _get_dust(w, h):
    key = (w, h)
    d = _dust_state.get(key)
    if d is None:
        d = []
        for _ in range(28):
            d.append({
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "size": random.choice([1, 1, 1, 2, 2, 3]),
                "vx": random.uniform(-4, 4),
                "vy": random.uniform(-9, -3),
                "phase": random.uniform(0, 6.28),
                "b": random.uniform(30, 95),
                "red": random.random() < 0.16,
            })
        _dust_state[key] = d
    return d


_dot_sprite_cache = {}


def _get_dot_sprite(size):
    """White dot sprite at full brightness; tinting uses a separate cache."""
    sprite = _dot_sprite_cache.get(size)
    if sprite is None:
        r = max(1, size // 2)
        sprite = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(sprite, (255, 255, 255, 255), (r, r), r)
        try:
            sprite = sprite.convert_alpha()
        except Exception:
            pass
        _dot_sprite_cache[size] = sprite
    return sprite


_tinted_dot_cache = {}


def _get_tinted_dot(size, color):
    """Pre-tinted dot. We must NOT fill the shared `_get_dot_sprite` result in
    place: BLEND_RGB_MULT would darken the cached sprite a little more every
    frame until the dust turned black."""
    key = (size, color)
    sprite = _tinted_dot_cache.get(key)
    if sprite is None:
        sprite = _get_dot_sprite(size).copy()
        sprite.fill(color, special_flags=pygame.BLEND_RGB_MULT)
        if len(_tinted_dot_cache) > 400:
            _tinted_dot_cache.clear()
        _tinted_dot_cache[key] = sprite
    return sprite


def draw_dust(surface, w, h, t):
    """Drifting ash — slow, weightless, wrong."""
    for p in _get_dust(w, h):
        x = (p["x"] + p["vx"] * t * 0.25) % w
        y = (p["y"] + p["vy"] * t * 0.25) % h
        tw = 0.5 + 0.5 * math.sin(t * 2.2 + p["phase"])
        b = int(max(8, min(200, p["b"] * (0.5 + 0.5 * tw))))
        b = (b // 8) * 8  # quantise so the tint cache stays small
        if p["red"]:
            color = (b, int(b * 0.55), int(b * 0.55))
        else:
            color = (b, b, b)
        sprite = _get_tinted_dot(p["size"], color)
        try:
            surface.blit(sprite, (int(x) - sprite.get_width() // 2,
                                  int(y) - sprite.get_height() // 2))
        except Exception:
            pass


_sweep_band_cache = {}


def _get_sweep_band(w):
    band = _sweep_band_cache.get(w)
    if band is None:
        band = pygame.Surface((w, 26), pygame.SRCALPHA)
        band.fill((255, 255, 255, 14))
        pygame.draw.line(band, (255, 255, 255, 70), (0, 13), (w, 13), 2)
        try:
            band = band.convert_alpha()
        except Exception:
            pass
        _sweep_band_cache[w] = band
    return band


def draw_scan_sweep(surface, w, h, t):
    """A pale band endlessly rolling down the screen."""
    y = int(t * 36) % (h + 80) - 40
    surface.blit(_get_sweep_band(w), (0, y))


def draw_glowing_text(surface, text, font, x, y, t, color=config.COLOR_WHITE, glow_color=config.COLOR_RED):
    """Title bloom — a red halo breathing behind the letterforms."""
    base = font.render(text, True, color)
    try:
        small = pygame.transform.smoothscale(base, (max(2, base.get_width() // 3), max(2, base.get_height() // 3)))
        glow = pygame.transform.smoothscale(small, (base.get_width() + 14, base.get_height() + 14))
        glow.fill(glow_color, special_flags=pygame.BLEND_RGB_MULT)
        pulse = 0.55 + 0.45 * math.sin(t * 2.2)
        glow.fill((255, 255, 255, int(255 * (0.3 + 0.4 * pulse))), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(glow, (x - 7, y - 7))
    except Exception:
        pass
    surface.blit(base, (x, y))


def wrap_cursor_pos(text, font, start_x, start_y, max_width):
    """The insertion point after `text`, following the same wrap rules."""
    words = text.split(" ")
    lines = 1
    current = ""
    for word in words:
        if "\n" in word:
            parts = word.split("\n")
            current = parts[1] + " "
            lines += 1
            continue
        test = current + word + " "
        if font.size(test)[0] < max_width:
            current = test
        else:
            lines += 1
            current = word + " "
    x = start_x + font.size(current)[0]
    y = start_y + (lines - 1) * (font.get_linesize() + 4)
    return x, y


# --- Cached text blocks ------------------------------------------------------
# Rendered line surfaces are cached per (text, font, color, width); sway and
# alpha pulsing are applied at blit time. This replaces per-frame glyph
# rendering, which was the single hottest path in the render loop.

_text_block_cache = {}


def _wrap_lines(text, font, max_width):
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
    return lines


def _get_cached_lines(text, font, color, max_width, outline=None, pad=0):
    key = (text, id(font), font.get_height(), color, max_width, outline, pad)
    entry = _text_block_cache.get(key)
    if entry is None:
        entry = []
        for line in _wrap_lines(text, font, max_width):
            line = line.strip()
            surf = font.render(line, True, color)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            if outline:
                # 1px dark halo so text stays legible over static/CRT noise.
                lw, lh = surf.get_size()
                halo = font.render(line, True, outline)
                out = pygame.Surface((lw + 4, lh + 4), pygame.SRCALPHA)
                for ox, oy in ((0, 1), (1, 0), (2, 1), (1, 2), (0, 2), (2, 0), (1, 1), (2, 2)):
                    out.blit(halo, (ox, oy))
                out.blit(surf, (2, 2))
                try:
                    out = out.convert_alpha()
                except Exception:
                    pass
                surf = out
            entry.append(surf)
        if len(_text_block_cache) > 400:
            _text_block_cache.clear()
        _text_block_cache[key] = entry
    return entry


def render_text_block(surface, text, font, color, start_x, start_y, max_width,
                      t=None, sway_amp=0, alpha_base=255, outline=None):
    """Cached text renderer. With t: per-line sway + alpha pulse at blit time."""
    lines = _get_cached_lines(text, font, color, max_width, outline=outline)
    line_h = font.get_linesize() + 4
    for i, surf in enumerate(lines):
        if t is not None:
            sway_x = int(math.sin(t * 0.8 + i * 0.6) * sway_amp) if sway_amp else 0
            pulse = 0.5 + 0.5 * math.sin(t * 1.2 + i * 0.9)
            a = int(max(0, min(255, alpha_base + int(pulse * 55))))
            surf.set_alpha(a)
            surface.blit(surf, (start_x + sway_x, start_y + i * line_h))
        else:
            surf.set_alpha(255)
            surface.blit(surf, (start_x, start_y + i * line_h))


def wrapped_line_count(text, font, color, max_width):
    """How many *visual* lines a block will occupy once wrapped.

    Layout code needs this: sizing a block by its hard `\\n` count undercounts
    any paragraph that soft-wraps, which is how answer options ended up drawn
    on top of the question. Shares `_get_cached_lines`'s cache, so the wrap is
    only computed once per (text, font, width).
    """
    try:
        return len(_get_cached_lines(text, font, color, max_width))
    except Exception:
        return max(1, text.count("\n") + 1)


# --- Readability helpers -----------------------------------------------------
# A soft dark wash plus a 1px halo under body text, so it stays legible on top
# of static, scanlines and curvature instead of dissolving into them.
_panel_cache = {}


def draw_readability_panel(surface, x, y, w, h, alpha=118):
    if w <= 0 or h <= 0:
        return
    key = (max(1, int(w)), max(1, int(h)), int(alpha))
    panel = _panel_cache.get(key)
    if panel is None:
        panel = pygame.Surface(key[:2], pygame.SRCALPHA)
        try:
            pygame.draw.rect(panel, (0, 0, 0, key[2]), panel.get_rect(), border_radius=10)
        except Exception:
            panel.fill((0, 0, 0, key[2]))
        try:
            panel = panel.convert_alpha()
        except Exception:
            pass
        if len(_panel_cache) > 24:
            _panel_cache.clear()
        _panel_cache[key] = panel
    surface.blit(panel, (int(x), int(y)))


def draw_text(surface, text, font, color, x, y, outline=None):
    """One line of text, optionally with a dark halo for readability."""
    if outline is None and config.TEXT_OUTLINE:
        outline = config.TEXT_OUTLINE_COLOR
    if outline:
        try:
            halo = font.render(text, True, outline)
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                surface.blit(halo, (x + ox, y + oy))
        except Exception:
            pass
    try:
        surf = font.render(text, True, color)
        surface.blit(surf, (x, y))
    except Exception:
        return
    return surf


# --- New v3 glitch effects ---------------------------------------------------

def apply_rgb_split(surface, w, h, amount=6):
    """Chromatic-aberration burst: R/B channels offset from G."""
    try:
        base = surface.copy()
        r = base.copy()
        r.fill((255, 0, 0), special_flags=pygame.BLEND_RGB_MULT)
        g = base.copy()
        g.fill((0, 255, 0), special_flags=pygame.BLEND_RGB_MULT)
        b = base.copy()
        b.fill((0, 0, 255), special_flags=pygame.BLEND_RGB_MULT)
        surface.fill((0, 0, 0))
        surface.blit(r, (-amount, 0), special_flags=pygame.BLEND_ADD)
        surface.blit(g, (0, 0), special_flags=pygame.BLEND_ADD)
        surface.blit(b, (amount, 0), special_flags=pygame.BLEND_ADD)
    except Exception:
        pass


def apply_screen_tear(surface, w, h):
    """Tear the frame into displaced horizontal slices."""
    y = 0
    while y < h:
        sh = random.randint(4, 20)
        if random.random() < 0.35:
            dx = random.randint(-40, 40)
            try:
                slice_surf = surface.subsurface(pygame.Rect(0, y, w, min(sh, h - y))).copy()
                surface.blit(slice_surf, (dx, y))
            except Exception:
                pass
        y += sh


# --- CRT finishing pass ------------------------------------------------------
# The whole frame is finished like a curved phosphor tube: an RGB triad mask,
# dark edge fall-off that fakes curvature, a soft rolling refresh bar, and a
# faint inner glow. Everything is pre-rendered once per window size and blitted
# (cheap overlays), so the CRT look costs a handful of blits per frame.
_crt_mask_cache = {}
_crt_bar_cache = {}


def _get_crt_mask(w, h):
    key = (w, h)
    surf = _crt_mask_cache.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # Phosphor triads: one faint R, G, B column per pixel column.
        triad = ((255, 40, 40, 22), (40, 255, 40, 22), (40, 40, 255, 22))
        for x in range(w):
            pygame.draw.line(surf, triad[x % 3], (x, 0), (x, h))
        # Edge fall-off (curvature illusion): darken toward all four borders.
        band_x = max(10, w // 10)
        for i in range(band_x):
            a = int(96 * (1 - i / band_x) ** 1.6)
            if a <= 0:
                continue
            pygame.draw.line(surf, (0, 0, 0, a), (i, 0), (i, h))
            pygame.draw.line(surf, (0, 0, 0, a), (w - 1 - i, 0), (w - 1 - i, h))
        band_y = max(8, h // 11)
        for i in range(band_y):
            a = int(84 * (1 - i / band_y) ** 1.6)
            if a <= 0:
                continue
            pygame.draw.line(surf, (0, 0, 0, a), (0, i), (w, i))
            pygame.draw.line(surf, (0, 0, 0, a), (0, h - 1 - i), (w, h - 1 - i))
        # Rounded tube corners: the square corners of the panel are blacked out
        # outside an inscribed circle, which is what sells the "3D" look.
        rr = max(0, min(int(getattr(config, "CRT_CORNER_ROUND", 0)), w // 2, h // 2))
        if rr > 0:
            limit = rr * rr
            for u in range(rr):
                for v in range(rr):
                    if (u - rr) ** 2 + (v - rr) ** 2 <= limit:
                        continue
                    for xx, yy in ((u, v), (w - 1 - u, v), (u, h - 1 - v), (w - 1 - u, h - 1 - v)):
                        surf.set_at((xx, yy), (0, 0, 0, 255))
        try:
            surf = surf.convert_alpha()
        except Exception:
            pass
        _crt_mask_cache[key] = surf
    return _crt_mask_cache[key]


def _get_crt_bar(w):
    band = _crt_bar_cache.get(w)
    if band is None:
        band = pygame.Surface((w, 30), pygame.SRCALPHA)
        band.fill((255, 255, 255, 9))
        pygame.draw.line(band, (255, 255, 255, 30), (0, 15), (w, 15), 2)
        try:
            band = band.convert_alpha()
        except Exception:
            pass
        _crt_bar_cache[w] = band
    return band


def apply_crt(surface, w, h, t=0.0, intensity=1.0):
    """Curved-tube finishing pass. `intensity` scales the effect (1.0 normal)."""
    if intensity <= 0:
        return
    try:
        bar = _get_crt_bar(w)
        y = int((t * (h + 30) / 3.0) % (h + 30)) - 30
        surface.blit(bar, (0, y))
    except Exception:
        pass
    try:
        mask = _get_crt_mask(w, h)
        if intensity < 1.0:
            mask.set_alpha(int(255 * intensity))
        else:
            mask.set_alpha(255)
        surface.blit(mask, (0, 0))
    except Exception:
        pass


# --- Website-style glitch text ----------------------------------------------
# The site's hero title stacks three copies — a base, a red copy clipped to the
# top band and a cyan copy clipped to the bottom band — and jitters them apart.
# Same idea here, over cached line surfaces so it stays cheap per frame.

_CYAN = (0, 216, 255)
_SCRAMBLE_GLYPHS = "#@%&?/\\!*+=<>$"


def scramble_text(text, t, amount=0.3):
    """Replace a trailing run of characters with junk glyphs, re-rolled a few
    times a second (the site's title scramble)."""
    n = len(text)
    if n <= 1:
        return text
    rng = random.Random(int(t * 9))
    k = int(n * amount)
    keep = rng.randint(max(0, n - k - 2), n)
    out = []
    for i, c in enumerate(text):
        if c == " " or i < keep:
            out.append(c)
        else:
            out.append(rng.choice(_SCRAMBLE_GLYPHS))
    return "".join(out)


def render_glitch_text(surface, text, font, x, y, t=0.0, color=config.COLOR_WHITE,
                       top_color=config.COLOR_RED, bottom_color=_CYAN, jitter=True,
                       outline=None):
    """One line with the site's red/cyan split + occasional jitter."""
    if outline is None and config.TEXT_OUTLINE:
        outline = config.TEXT_OUTLINE_COLOR
    base = font.render(text, True, color)
    w, h = base.get_size()
    jx = jy = 0
    if jitter and random.random() < 0.14:
        jx, jy = random.randint(-3, 3), random.randint(-2, 2)
    if outline:
        try:
            halo = font.render(text, True, outline)
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)):
                surface.blit(halo, (x + jx + ox, y + jy + oy))
        except Exception:
            pass
    try:
        top = font.render(text, True, top_color)
        bot = font.render(text, True, bottom_color)
        surface.blit(top, (x + jx - 3, y + jy - 2),
                     area=pygame.Rect(0, 0, w, max(1, int(h * 0.45))))
        surface.blit(bot, (x + jx + 3, y + jy + 2),
                     area=pygame.Rect(0, int(h * 0.55), w, max(1, h - int(h * 0.55))))
    except Exception:
        pass
    surface.blit(base, (x + jx, y + jy))


def render_glitch_block(surface, text, font, color, start_x, start_y, max_width,
                        t=0.0, sway_amp=0, jitter=True, alpha_base=255,
                        outline=None, ghost=True):
    """Wrapped text with the same split — used for the question body.

    The coloured fringes go *under* the crisp (optionally outlined) base copy so
    the words stay readable while the split is still visible at the edges.
    """
    if outline is None and config.TEXT_OUTLINE:
        outline = config.TEXT_OUTLINE_COLOR
    lines = _get_cached_lines(text, font, color, max_width, outline=outline)
    pad = 2 if outline else 0
    top_lines = _get_cached_lines(text, font, config.COLOR_RED, max_width)
    bot_lines = _get_cached_lines(text, font, _CYAN, max_width)
    line_h = font.get_linesize() + 4
    for i, surf in enumerate(lines):
        sway_x = int(math.sin(t * 0.8 + i * 0.6) * sway_amp) if sway_amp else 0
        x = start_x + sway_x
        y = start_y + i * line_h
        ox, oy = x + pad, y + pad
        if ghost:
            jx = jy = 0
            if jitter and random.random() < 0.12:
                jx, jy = random.randint(-2, 2), random.randint(-1, 2)
            try:
                if i < len(top_lines):
                    tl = top_lines[i]
                    th = tl.get_height()
                    surface.blit(tl, (ox + jx - 2, oy + jy - 1),
                                 area=pygame.Rect(0, 0, tl.get_width(), max(1, int(th * 0.45))))
                if i < len(bot_lines):
                    bl = bot_lines[i]
                    bh = bl.get_height()
                    surface.blit(bl, (ox + jx + 2, oy + jy + 1),
                                 area=pygame.Rect(0, int(bh * 0.55), bl.get_width(),
                                                  max(1, bh - int(bh * 0.55))))
            except Exception:
                pass
        try:
            surf.set_alpha(alpha_base)
        except Exception:
            pass
        surface.blit(surf, (x, y))


# --- VHS distortion pass -----------------------------------------------------
# Tracking slips, a drifting tracking bar, head-switching snow at the bottom,
# drifting static, tube curvature, then the CRT phosphor/edge mask. Everything
# uses cached assets; the only per-frame cost is the curvature slices.
_vhs_snow_cache = {}


def _get_vhs_snow(seed, size=96):
    key = (seed, size)
    tile = _vhs_snow_cache.get(key)
    if tile is None:
        rng = random.Random(seed)
        tile = pygame.Surface((size, size), pygame.SRCALPHA)
        for _ in range(size * 9):
            x = rng.randint(0, size - 1)
            y = rng.randint(0, size - 1)
            v = rng.choice((120, 180, 230, 255))
            a = rng.randint(30, 120)
            tile.set_at((x, y), (v, v, v, a))
        try:
            tile = tile.convert_alpha()
        except Exception:
            pass
        _vhs_snow_cache[key] = tile
    return tile


def apply_vhs_curvature(surface, w, h, amount=0.10, bands=26):
    """Bow the frame like a tube: slice it and width-scale each slice so the
    top/bottom pinch inward (a cheap fake barrel)."""
    if amount <= 0 or bands < 2:
        return
    try:
        src = surface.copy()
    except Exception:
        return
    surface.fill((0, 0, 0))
    for i in range(bands):
        y0 = i * h // bands
        y1 = (i + 1) * h // bands
        bh = y1 - y0
        if bh <= 0:
            continue
        ny = ((y0 + y1) / 2.0 - h / 2.0) / (h / 2.0)
        nw = max(2, int(w * (1.0 - amount * (ny * ny))))
        try:
            band = src.subsurface(pygame.Rect(0, y0, w, bh))
            scaled = pygame.transform.scale(band, (nw, bh))
        except Exception:
            continue
        surface.blit(scaled, ((w - nw) // 2, y0))


def apply_vhs_tracking(surface, w, h, t=0.0, intensity=1.0):
    """Horizontal slips, a drifting tracking bar, and head-switching snow."""
    slips = int(2 + 4 * intensity)
    for _ in range(slips):
        if random.random() > 0.6 * intensity:
            continue
        y = random.randint(0, max(0, h - 1))
        bh = random.randint(3, 16)
        dx = random.randint(-16, 16)
        try:
            band = surface.subsurface(pygame.Rect(0, y, w, min(bh, h - y))).copy()
            surface.blit(band, (dx, y))
        except Exception:
            pass
    if random.random() < 0.5 * intensity:
        by = int((t * 150) % h)
        pygame.draw.rect(surface, (16, 16, 16), (0, by, w, random.randint(3, 10)))
    if random.random() < 0.7 * intensity:
        strip = _get_vhs_snow(0)
        try:
            strip.set_alpha(140)
        except Exception:
            pass
        surface.blit(strip, (random.randint(-6, 6), h - random.randint(8, 16)))


def apply_vhs_static(surface, w, h, t=0.0, intensity=1.0):
    """Drifting tape snow — soft speckle blitted in a few places per frame."""
    if intensity <= 0:
        return
    n = int(1 + 3 * intensity)
    for _ in range(n):
        tile = _get_vhs_snow(random.randint(0, 3))
        try:
            tile.set_alpha(random.randint(12, 30))
        except Exception:
            pass
        surface.blit(tile, (random.randint(-96, max(0, w - 90)),
                            random.randint(-96, max(0, h - 90))))


_vhs_line_cache = {}


def _get_vhs_line(w):
    """A cached 2px full-width tape noise line (the VHS head line)."""
    line = _vhs_line_cache.get(w)
    if line is None:
        line = pygame.Surface((w, 2), pygame.SRCALPHA)
        for x in range(w):
            v = random.choice((0, 0, 0, 70, 120, 180, 255))
            line.set_at((x, 0), (v, v, v, random.randint(50, 150)))
            line.set_at((x, 1), (v, v, v, random.randint(20, 90)))
        try:
            line = line.convert_alpha()
        except Exception:
            pass
        _vhs_line_cache[w] = line
    return line


def draw_static_line(surface, w, h, t=0.0, intensity=1.0):
    """A faint tape head line drifting down the main screen. Deliberately
    *light* — it should read as tape, not as a distortion."""
    if intensity <= 0:
        return
    line = _get_vhs_line(w)
    y = int((t * 34) % h)
    for k, off in enumerate((0, 11, 37)):
        yy = (y + off) % h
        try:
            line.set_alpha(max(0, int((68 - k * 20) * intensity)))
        except Exception:
            pass
        surface.blit(line, (random.randint(-4, 4), yy))


def apply_vhs_pass(surface, w, h, t=0.0, intensity=1.0, game_state=None):
    """The full VHS stack. `intensity` 0..1+ scales everything."""
    if intensity <= 0:
        return
    sset = {}
    if game_state is not None:
        sset = game_state.get("settings", {}) or {}
    perf = str(sset.get("performance_mode", "Medium")).lower()
    crt_enabled = bool(sset.get("crt_enabled", True))
    if perf == "low":
        crt_enabled = False
    if not crt_enabled:
        return
    tube_curvature_enabled = bool(sset.get("tube_curvature_enabled", True))
    phosphor_mask_enabled = bool(sset.get("phosphor_mask_enabled", True))
    if perf == "low":
        tube_curvature_enabled = False
        phosphor_mask_enabled = False
    if config.VHS_TRACKING:
        apply_vhs_tracking(surface, w, h, t, intensity)
    apply_vhs_static(surface, w, h, t, intensity * config.VHS_STATIC)
    if config.CRT_CURVATURE > 0 and tube_curvature_enabled:
        # Stronger settings bow the tube a bit harder, but gently enough that the
        # text column never gets pinched out.
        amount = config.CRT_CURVATURE * min(1.35, 0.7 + 0.3 * float(intensity))
        apply_vhs_curvature(surface, w, h, amount, config.CRT_CURVE_BANDS)
    apply_crt(surface, w, h, t, intensity)


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
        try:
            shape = shape.convert_alpha()
        except Exception:
            pass
        sils.append({
            "surf": shape,
            "base_x": int(w * (0.62 + i * 0.13)),
            "base_y": int(h * (0.18 + i * 0.12)),
            "phase": random.uniform(0, 6.28),
        })
    return sils


def draw_menu_decorations(surface, w, h, current_time, font_small):
    global _menu_silhouettes
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
        r = random.randint(30, 70)
        blob = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i in range(3):
            alpha = int(30 / (i + 1))
            col = (120 + i * 30, 110 + i * 20, 200 - i * 40, alpha)
            pygame.draw.circle(blob, col, (r, r), int(r * (0.6 - i * 0.18)))
        try:
            blob = blob.convert_alpha()
        except Exception:
            pass
        galaxies.append({
            "x": random.randint(region_x + 30, max(region_x + 40, w - 120)),
            "y": random.randint(70, max(120, h - 180)),
            "r": r,
            "surf": blob,
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
        surface.blit(g["surf"], (g["x"] - g["r"], g["y"] - g["r"]))


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


def draw_social_toast(surface, w, h, text, shown_at, font_medium, font_small, now,
                      tone="info", slot=0, life=6.0):
    """A one-line notice (someone answered your question, a send failed...).

    Mirrors draw_badge_toast so the two never fight: the badge toast owns the
    bottom slot, these stack just above it.
    """
    age = now - shown_at
    if age > life:
        return False
    fade = max(0.0, min(1.0, life - age))
    alpha = int(255 * min(1.0, fade * 2.0))
    if tone == "good":
        border, head = (40, 110, 40), (90, 200, 90)
    elif tone == "bad":
        border, head = (120, 20, 20), (200, 70, 70)
    else:
        border, head = (70, 60, 20), (200, 180, 90)

    label = text if len(text) <= 96 else text[:93] + "..."
    body = font_small.render(label, True, (210, 210, 210))
    box_w = max(220, min(int(w * 0.7), body.get_width() + 32))
    box = pygame.Surface((box_w, 44), pygame.SRCALPHA)
    box.fill((10, 0, 0, 200))
    pygame.draw.rect(box, border + (255,), box.get_rect(), 2)
    tag = font_small.render("TRANSMISSION", True, head)
    box.blit(tag, (16, 5))
    box.blit(body, (16, 22))
    box.set_alpha(alpha)
    bx = int(w * 0.5 - box.get_width() / 2)
    by = int(h * 0.78) - 52 - slot * 50
    surface.blit(box, (bx, by))
    return True


# --- Webcam (cv2 worker thread) ----------------------------------------------
camera = None
webcam_surface = None
webcam_active = False
webcam_start_time = 0
_webcam_frame_queue = queue.Queue(maxsize=1)


def start_webcam_nonblocking():

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


def _distort_webcam(surf, elapsed):
    """Cheap numpy distortion on the live feed: rolling glitch bars and an
    occasional full-frame inversion, so the camera never feels trustworthy."""
    if not config.WEBCAM_DISTORTION or surf is None:
        return surf
    try:
        import numpy as _np
        arr = pygame.surfarray.array3d(surf)  # shape (w, h, 3)
        h = arr.shape[1]
        bands = 3 if random.random() < 0.5 else 2
        for _ in range(bands):
            y0 = random.randint(0, max(0, h - 14))
            y1 = min(h, y0 + random.randint(4, 14))
            shift = random.randint(-28, 28)
            arr[:, y0:y1] = _np.roll(arr[:, y0:y1], shift, axis=0)
        # Periodic inversion burst (about once every few seconds).
        if int(elapsed * 2) % 7 == 0 and random.random() < 0.5:
            arr = 255 - arr
        pygame.surfarray.blit_array(surf, arr.astype(_np.uint8))
    except Exception:
        pass
    return surf


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
        surf = _distort_webcam(surf, elapsed)
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
            # NOTE: no .convert_alpha() here — that needs the display and is not
            # thread-safe. We only load + scale (thread-safe), and send raw bytes
            # back; the main thread builds the final surface.
            img = pygame.image.load(path)
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
        surf = pygame.image.fromstring(raw, size, "RGBA")
        try:
            surf = surf.convert_alpha()  # main thread has the display
        except Exception:
            pass
        return surf
    except Exception:
        return None


# --- Country flag + location card -------------------------------------------
_flag_cache = {}


def _flag_path(cc):
    return os.path.join(config.get_appdata_dir(), "flags", cc + ".png")


def prefetch_flag(country_code):
    """Download the country flag PNG to disk. Pure network + file I/O (no
    pygame), so it is safe to call from a worker thread."""
    if not config.ENABLE_COUNTRY_FLAG or not country_code:
        return
    cc = str(country_code).strip().lower()
    if len(cc) != 2:
        return
    path = _flag_path(cc)
    if os.path.exists(path):
        return
    try:
        import requests
        r = requests.get("https://flagcdn.com/w80/%s.png" % cc, timeout=5)
        if r.status_code == 200 and r.content:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, path)  # atomic: readers never see a partial file
    except Exception:
        pass


def get_flag_surface(country_code):
    """Load the flag from disk once, on the calling (main) thread. A miss is
    NOT cached, so the card picks the flag up as soon as the download lands."""
    if not country_code:
        return None
    cc = str(country_code).strip().lower()
    if cc in _flag_cache:
        return _flag_cache[cc]
    surf = None
    try:
        path = _flag_path(cc)
        if os.path.exists(path):
            surf = pygame.image.load(path).convert_alpha()
    except Exception:
        surf = None
    if surf is not None:
        _flag_cache[cc] = surf
    return surf


_CARD_FONTS = {}
_card_cache = {}


def _card_fonts():
    if not _CARD_FONTS:
        _CARD_FONTS["big"] = pygame.font.SysFont("couriernew,courier,monospace", 24, bold=True)
        _CARD_FONTS["small"] = pygame.font.SysFont("couriernew,courier,monospace", 13)
    return _CARD_FONTS["big"], _CARD_FONTS["small"]


def build_location_card(geo):
    """Build (and cache) the 'LOCATED: City, Country' card surface."""
    if not geo:
        return None
    city = geo.get("city", "")
    region = geo.get("region", "")
    country = geo.get("country", "")
    cc = geo.get("country_code", "")
    if not (city or country):
        return None

    flag = get_flag_surface(cc)
    # Key includes whether the flag is present, so the card rebuilds once the
    # flag download completes.
    key = (city, region, country, cc, geo.get("lat"), geo.get("lon"), bool(flag))
    if key in _card_cache:
        return _card_cache[key]

    big, small = _card_fonts()
    place = ", ".join(p for p in (city, country) if p) or country
    lat, lon = geo.get("lat"), geo.get("lon")
    try:
        coords = ("%.4f, %.4f" % (float(lat), float(lon))) if (lat not in (None, "") and lon not in (None, "")) else ""
    except (TypeError, ValueError):
        coords = ""
    caption = coords or region or "located via your network"

    title = big.render("LOCATED: " + place, True, (255, 60, 60))
    sub = small.render(caption, True, (170, 170, 170))

    pad = 14
    flag_w = flag.get_width() if flag else 0
    text_w = max(title.get_width(), sub.get_width())
    box_w = text_w + flag_w + pad * 3
    box_h = title.get_height() + sub.get_height() + pad * 2 + 4

    box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    box.fill((0, 0, 0, 210))
    pygame.draw.rect(box, (120, 20, 20), box.get_rect(), 2)

    x = pad
    if flag:
        fy = (box_h - flag.get_height()) // 2
        box.blit(flag, (x, fy))
        x += flag_w + pad
    box.blit(title, (x, pad))
    box.blit(sub, (x, pad + title.get_height() + 4))

    if len(_card_cache) > 16:
        _card_cache.clear()
    _card_cache[key] = box
    return box


def draw_location_card(surface, geo, w, h, alpha=255):
    """Top-right 'located' card — clear of the question text and webcam feed."""
    box = build_location_card(geo)
    if box is None:
        return
    if alpha < 255:
        box.set_alpha(int(alpha))
    surface.blit(box, (w - box.get_width() - 20, 20))


# --- The watching eye -------------------------------------------------------
# A procedural eye drawn straight to the screen: sclera, iris, pupil, lid.
# No art assets, so it scales cleanly and can be animated per-frame.
#
# Behaviour:
#   * sits in a corner of the screen, avoiding the busy middle of the UI
#   * the pupil tracks the mouse cursor
#   * when a UI element is "selected", the pupil looks at that instead
#   * it blinks on a random timer
#   * when the cursor leaves the window (but the window still has focus) the
#     pupil slides to the edge of the iris and keeps staring that way
#
# The desktop overlay (Windows/macOS) lives in `eye_overlay.py`; this is the
# in-game half and runs on every platform.

_eye_geometry = {"radius": 0}


def eye_radius(w, h):
    """Eye size scales with the window but stays sane on tiny windows."""
    r = int(min(w, h) * 0.055)
    return max(24, min(72, r))


def eye_pupil_offset(cx, cy, r, target, max_frac=0.52):
    """Clamp a look-at vector into the iris."""
    if target is None:
        return (0, 0)
    tx, ty = target
    dx = tx - cx
    dy = ty - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (0, 0)
    max_off = r * max_frac
    if dist <= max_off:
        return (dx, dy)
    scale = max_off / dist
    return (dx * scale, dy * scale)


def draw_eye(surface, cx, cy, r, openness=1.0, pupil=(0.0, 0.0), angry=False,
             dilation=1.0, shade=1.0):
    """Draw the eye: sclera, iris, pupil, highlight.

    Barebone on purpose. The game is a black-and-white terminal, so the eye is
    drawn in the same language: a white almond, a black iris, a black pupil.
    Nothing else. When `angry` is set the iris goes red, which is what the eye
    does while something is happening.

    `openness` 1.0 = wide open, 0.0 = shut. `pupil` is the (x, y) offset of
    the iris centre from the eye centre, already clamped by
    `eye_pupil_offset`. `dilation` scales the iris and pupil together: below
    1.0 the pupil shrinks (constriction), above 1.0 it swells. `shade`
    dims the white, so an eye can sit back behind the glass.
    """
    openness = max(0.03, min(1.0, float(openness)))
    ry = max(1, int(r * 0.56 * openness))
    px, py = pupil
    try:
        dil = max(0.35, min(2.0, float(dilation)))
    except (TypeError, ValueError):
        dil = 1.0
    try:
        shade = max(0.0, min(1.0, float(shade)))
    except (TypeError, ValueError):
        shade = 1.0
    white = (int(238 * shade), int(238 * shade), int(234 * shade))
    crease = (int(235 * shade), int(235 * shade), int(235 * shade))

    iris_col = (168, 12, 12) if angry else (14, 12, 12)
    iris_edge = (60, 4, 4) if angry else (0, 0, 0)

    # --- socket --------------------------------------------------------------
    # A hard black ring so the eye reads as a drawn shape, not a blur.
    pygame.draw.ellipse(surface, (0, 0, 0),
                         (cx - r - 2, cy - ry - 2, (r + 2) * 2, (ry + 2) * 2))

    if openness <= 0.06:
        # Fully shut: a lid crease, nothing else.
        pygame.draw.line(surface, crease,
                         (cx - r, cy), (cx + r, cy), max(1, r // 10))
        return

    # --- sclera --------------------------------------------------------------
    pygame.draw.ellipse(surface, white,
                         (cx - r, cy - ry, r * 2, ry * 2))

    # --- iris ----------------------------------------------------------------
    ir = max(3, int(r * 0.54 * dil))
    # The iris never grows past the sclera, and it always leaves a rim of
    # sclera showing so a dilated pupil still reads as an iris.
    ir = min(ir, int(r * 0.80))
    pygame.draw.ellipse(surface, iris_col,
                         (cx + px - ir, cy + py - ir, ir * 2, ir * 2))
    if not angry:
        # A single white speck, so the black iris is not a dead hole.
        sp = max(1, int(ir * 0.16))
        pygame.draw.ellipse(surface, white,
                             (cx + px - sp - int(ir * 0.30),
                              cy + py - sp - int(ir * 0.34), sp * 2, sp * 2))
    pygame.draw.ellipse(surface, iris_edge,
                         (cx + px - ir, cy + py - ir, ir * 2, ir * 2), 1)

    # --- pupil ---------------------------------------------------------------
    pr = max(2, int(ir * 0.50 * min(1.25, dil)))
    pygame.draw.ellipse(surface, (0, 0, 0),
                         (cx + px - pr, cy + py - pr, pr * 2, pr * 2))

    # --- lid shadow ----------------------------------------------------------
    if openness < 0.98:
        lid = int(r * 0.56 * (1.0 - openness))
        if lid > 0:
            pygame.draw.ellipse(surface, (0, 0, 0),
                                 (cx - r, cy - ry, r * 2, lid * 2))
