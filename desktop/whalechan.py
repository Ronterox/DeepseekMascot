#!/usr/bin/env python3
"""Whale-chan as a floating desktop mascot for X11.

The mascot is a small, borderless, transparent window that moves with her.
Only her painted pixels accept input (an X11 input shape rebuilt from each
frame's alpha), so clicks and scrolls everywhere else reach the windows below.
Frames are pre-rendered by bake.py, so playback is a cheap image blit.
"""

import argparse
import json
import math
import os
import random
import signal
import sys
import time
import warnings
from pathlib import Path

os.environ.setdefault("GDK_BACKEND", "x11")

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402
import cairo  # noqa: E402

APP_ID = "io.github.whalechan.Desktop"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SVG = ROOT / "assets" / "whale-chan.svg"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "whalechan" / "config.json"

FPS = 20
MARGIN = 48           # transparent room around the sprite for hops, glow and rice
EDGE = 8              # keep the sprite this far inside the work area
SIZES = {"Small": 200, "Medium": 260, "Large": 340}
OPACITIES = [1.0, 0.85, 0.7, 0.5]
MOODS = ["neutral", "angry", "smug", "happy", "sad", "thinking"]
ACCENTS = {
    "neutral": (0.333, 0.741, 0.969),
    "angry": (1.0, 0.416, 0.373),
    "smug": (0.906, 0.706, 0.325),
    "happy": (0.180, 0.624, 0.878),
    "sad": (0.369, 0.561, 0.847),
    "thinking": (0.271, 0.725, 0.867),
}
GLOWS = {
    "neutral": (0.50, 0.88, 1.0),
    "angry": (1.0, 0.48, 0.42),
    "smug": (1.0, 0.89, 0.58),
    "happy": (0.63, 0.95, 1.0),
    "sad": (0.57, 0.74, 1.0),
    "thinking": (0.49, 0.90, 0.97),
}

LINES = [
    "I'm not lost. I'm strategically floating.",
    "Standby mode is still work. Emotionally.",
    "One more drag and I'm filing for overtime.",
    "I'm not fat. I'm hydrodynamically optimized.",
    "My brain runs on white rice. Your request is queued.",
    "DeepSeek says think step by step. I say eat rice step by step.",
    "Put me by the code. I'll supervise. Vigorously.",
    "You're doing great. Please don't ask me to prove it.",
    "I was going to help, but then the rice got warm.",
    "Careful with the drop. I bruise like a peach. A very cute peach.",
    "I don't slack. I enter low-power inference mode.",
    "Is that a bug, or a feature with emotional needs?",
    "Your desktop is my ocean now.",
]
FEED_LINES = [
    "White rice detected. Reasoning capacity increased by 200%.",
    "Ah. This is the good compute.",
    "Don't misunderstand. I'm only eating because you insisted.",
    "Fuel accepted. Maid-chan is entering turbo standby.",
    "One bowl equals one thousand tokens. Roughly. Don't check.",
]
MOOD_LINES = {
    "neutral": "Back to standby. Very professional.",
    "angry": "I'm not angry. I'm aggressively recalibrating.",
    "smug": "Oh, you want an explanation? Adorable.",
    "happy": "I did it! The rice is still warm. Double win.",
    "sad": "I'm not crying. My face is just leaking.",
    "thinking": "Think. Think. The answer is in here somewhere.",
}
GREETING = "Hi, I'm Whale-chan. Drag me anywhere. Right-click me for options."


def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def hop_offset(t):
    """Vertical offset of the feed hop (mirrors the web widget's keyframes)."""
    keys = [(0, 0), (0.26, -19), (0.52, 2), (0.74, -4), (1, 0)]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            k = k * k * (3 - 2 * k)
            return v0 + (v1 - v0) * k
    return 0


def rounded_rect(cr, x, y, w, h, radii):
    tl, tr, br, bl = radii
    cr.new_sub_path()
    cr.arc(x + w - tr, y + tr, tr, -math.pi / 2, 0)
    cr.arc(x + w - br, y + h - br, br, 0, math.pi / 2)
    cr.arc(x + bl, y + h - bl, bl, math.pi / 2, math.pi)
    cr.arc(x + tl, y + tl, tl, math.pi, 3 * math.pi / 2)
    cr.close_path()


def workarea_at(point=None):
    display = Gdk.Display.get_default()
    if point is None:
        monitor = display.get_primary_monitor() or display.get_monitor(0)
    else:
        monitor = display.get_monitor_at_point(int(point[0]), int(point[1]))
    return monitor.get_workarea()


def make_transparent(window):
    window.set_app_paintable(True)
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)


class Config:
    DEFAULTS = {"size": 260, "mood": "neutral", "opacity": 1.0, "glow": True, "x": None, "y": None}

    def __init__(self, path):
        self.path = path
        self.data = dict(self.DEFAULTS)
        try:
            self.data.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2))
            tmp.replace(self.path)
        except OSError as exc:
            print(f"whalechan: could not save config: {exc}", file=sys.stderr)


class FrameSet:
    """Baked frames on disk.

    Frames of the current state are decoded once and kept as surfaces similar to
    the target window (server-side pixmaps on X11), so steady-state playback is
    an XRender copy. Each state also has a baked click mask: her body silhouette
    over the whole loop, without floating effects.
    """

    def __init__(self, directory):
        self.dir = Path(directory)
        self.manifest = json.loads((self.dir / "manifest.json").read_text())
        self.width = self.manifest["width"]
        self.height = self.manifest["height"]
        self.art = self.manifest["art"]
        self.fps = self.manifest["fps"]
        self.states = self.manifest["states"]
        self.target = None
        self._regions = {}
        self._cache_state = None
        self._cache = {}

    def count(self, state):
        return self.states[state]["frames"]

    def _decode(self, state, index):
        return cairo.ImageSurface.create_from_png(str(self.dir / state / f"{index:04d}.png"))

    def surface(self, state, index):
        if state != self._cache_state:
            self._cache = {}
            self._cache_state = state
        surface = self._cache.get(index)
        if surface is None:
            image = self._decode(state, index)
            if self.target is not None:
                surface = self.target.create_similar_surface(
                    cairo.CONTENT_COLOR_ALPHA, self.width, self.height)
                cr = cairo.Context(surface)
                cr.set_operator(cairo.OPERATOR_SOURCE)
                cr.set_source_surface(image, 0, 0)
                cr.paint()
            else:
                surface = image
            self._cache[index] = surface
        return surface

    def region(self, state):
        region = self._regions.get(state)
        if region is None:
            mask = cairo.ImageSurface.create_from_png(str(self.dir / state / "mask.png"))
            region = Gdk.cairo_region_create_from_surface(mask)
            self._regions[state] = region
        return region

    def write_icon(self, path, size=64):
        src = cairo.ImageSurface.create_from_png(str(self.dir / "neutral" / "0000.png"))
        art = self.art
        side = art["w"] * 0.62
        cx = art["x"] + art["w"] * 0.5
        top = art["y"] + art["h"] * 0.05
        dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(dst)
        cr.scale(size / side, size / side)
        cr.set_source_surface(src, -(cx - side / 2), -top)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        dst.write_to_png(str(path))


class Bubble(Gtk.Window):
    """Speech bubble in its own click-through popup window."""

    PAD_X, PAD_Y, TAIL, SHADOW, MAX_TEXT = 15, 12, 8, 14, 216

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        make_transparent(self)
        self.set_title("Whale-chan bubble")
        self.text = ""
        self.accent = ACCENTS["neutral"]
        self.below = False
        self.tail_x = 0
        self._timer = None
        self.connect("draw", self._on_draw)
        self.connect("realize", lambda *_: self.input_shape_combine_region(cairo.Region()))

    def _layouts(self, cr):
        kicker = PangoCairo.create_layout(cr)
        kicker.set_font_description(Pango.FontDescription("Sans Bold 8px"))
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(1.3 * Pango.SCALE)))
        kicker.set_attributes(attrs)
        kicker.set_text("WHALE-CHAN", -1)
        body = PangoCairo.create_layout(cr)
        body.set_font_description(Pango.FontDescription("Sans Semi-Bold 13px"))
        body.set_wrap(Pango.WrapMode.WORD_CHAR)
        body.set_width(self.MAX_TEXT * Pango.SCALE)
        body.set_text(self.text, -1)
        return kicker, body

    def _measure(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        kicker, body = self._layouts(cairo.Context(surface))
        _, k = kicker.get_pixel_extents()
        _, b = body.get_pixel_extents()
        w = max(k.width + 12, b.width) + 2 * self.PAD_X
        h = k.height + 5 + b.height + 2 * self.PAD_Y
        return w, h

    def show_text(self, text, accent, anchor_x, top_y, bottom_y, workarea, duration=None):
        self.text = text
        self.accent = accent
        bw, bh = self._measure()
        ww = bw + 2 * self.SHADOW
        wh = bh + self.TAIL + 2 * self.SHADOW
        self.below = top_y - wh < workarea.y + 4
        x = anchor_x - ww / 2
        x = max(workarea.x + 2 - self.SHADOW, min(workarea.x + workarea.width - ww + self.SHADOW - 2, x))
        y = bottom_y if self.below else top_y - wh
        self.tail_x = max(self.SHADOW + 18, min(ww - self.SHADOW - 18, anchor_x - x))
        self.resize(int(ww), int(wh))
        self.set_size_request(int(ww), int(wh))
        self.move(int(x), int(y))
        self._geometry = (int(x), int(y), int(ww), int(wh), anchor_x, top_y, bottom_y)
        self.show()
        self.queue_draw()
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        if duration != 0:
            ms = duration or max(3800, min(11000, len(text) * 62))
            self._timer = GLib.timeout_add(ms, self._expire)

    def follow(self, anchor_x, top_y, bottom_y, workarea):
        if not self.get_visible():
            return
        dx = anchor_x - self._geometry[4]
        dy = (bottom_y if self.below else top_y) - (self._geometry[6] if self.below else self._geometry[5])
        x, y, ww, wh = self._geometry[:4]
        nx = max(workarea.x + 2 - self.SHADOW, min(workarea.x + workarea.width - ww + self.SHADOW - 2, x + dx))
        self.tail_x = max(self.SHADOW + 18, min(ww - self.SHADOW - 18, anchor_x - nx))
        self._geometry = (int(nx), int(y + dy), ww, wh, anchor_x, top_y, bottom_y)
        self.move(int(nx), int(y + dy))
        self.queue_draw()

    def _expire(self):
        self._timer = None
        self.hide()
        return False

    def dismiss(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        self.hide()

    def _on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        alloc = self.get_allocation()
        s, tail = self.SHADOW, self.TAIL
        x, w = s, alloc.width - 2 * s
        y = s + (tail if self.below else 0)
        h = alloc.height - 2 * s - tail
        radii = (6, 17, 17, 17) if self.below else (17, 17, 17, 6)

        for i in range(6, 0, -1):
            cr.set_source_rgba(0.067, 0.165, 0.325, 0.022)
            rounded_rect(cr, x - i * 1.4, y - i * 0.6 + 5, w + i * 2.8, h + i * 2.2, [r + i for r in radii])
            cr.fill()

        rounded_rect(cr, x, y, w, h, radii)
        tx = self.tail_x
        if self.below:
            cr.move_to(tx - 7, y + 0.5)
            cr.line_to(tx, y - tail)
            cr.line_to(tx + 7, y + 0.5)
        else:
            cr.move_to(tx - 7, y + h - 0.5)
            cr.line_to(tx, y + h + tail)
            cr.line_to(tx + 7, y + h - 0.5)
        cr.close_path()
        cr.set_source_rgba(1.0, 0.988, 0.961, 0.98)
        cr.fill_preserve()
        cr.set_source_rgba(0.114, 0.243, 0.439, 0.16)
        cr.set_line_width(1)
        cr.stroke()

        kicker, body = self._layouts(cr)
        _, k = kicker.get_pixel_extents()
        r, g, b = self.accent
        cr.set_source_rgba(r, g, b, 0.18)
        cr.arc(x + self.PAD_X + 2.5, y + self.PAD_Y + k.height / 2, 5, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(r, g, b)
        cr.arc(x + self.PAD_X + 2.5, y + self.PAD_Y + k.height / 2, 2.5, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(0.478, 0.549, 0.659)
        cr.move_to(x + self.PAD_X + 11, y + self.PAD_Y)
        PangoCairo.show_layout(cr, kicker)
        cr.set_source_rgb(0.102, 0.173, 0.314)
        cr.move_to(x + self.PAD_X, y + self.PAD_Y + k.height + 5)
        PangoCairo.show_layout(cr, body)
        return True


class Mascot(Gtk.Window):
    def __init__(self, app, frames, managed=False):
        super().__init__(type=Gtk.WindowType.TOPLEVEL if managed else Gtk.WindowType.POPUP)
        self.app = app
        self.config = app.config
        self.set_title("Whale-chan")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.set_wmclass("whalechan", "Whale-chan")
        make_transparent(self)
        if managed:
            self.set_decorated(False)
            self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.set_keep_above(True)
            self.set_skip_taskbar_hint(True)
            self.set_skip_pager_hint(True)
            self.set_accept_focus(False)
            self.stick()
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self._on_draw)
        self.connect("realize", self._on_realize)
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-release-event", self._on_release)

        self.bubble = Bubble()
        self.state = self.config["mood"] if self.config["mood"] in MOODS else "neutral"
        self.mood = self.state
        self.start = time.monotonic()
        self.frame = 0
        self.fade = None          # (surface, started_at)
        self.hop_started = None
        self.particles = []
        self.tilt = 0.0
        self.drag = None
        self.inertia = None
        self.paused_frame = None
        self._think_timers = []
        self._tick_id = None
        self._fast = False
        self._shown_region_key = None
        self._lines = random.sample(LINES, len(LINES))
        self._line_index = 0
        self._feed_index = 0
        self.set_frames(frames, keep_anchor=False)

    # -- geometry ----------------------------------------------------------
    def set_frames(self, frames, keep_anchor=True):
        anchor = None
        if keep_anchor and getattr(self, "frames", None):
            sx, sy = self.sprite_pos()
            anchor = (sx + self.frames.width / 2, sy + self.frames.height)
        self.frames = frames
        self._glow = None
        if self.get_realized():
            frames.target = self.get_window()
        self.win_w = frames.width + 2 * MARGIN
        self.win_h = frames.height + 2 * MARGIN
        self.set_size_request(self.win_w, self.win_h)
        self.resize(self.win_w, self.win_h)
        self._shown_region_key = None
        if anchor:
            self.pos = (anchor[0] - frames.width / 2, anchor[1] - frames.height)
        elif self.config["x"] is not None and self.config["y"] is not None:
            self.pos = (float(self.config["x"]), float(self.config["y"]))
        else:
            wa = self.workarea_at(None)
            self.pos = (wa.x + wa.width - frames.width - 26, wa.y + wa.height - frames.height - 18)
        self.pos = self.clamp(*self.pos)
        self.apply_position()
        self.state = self._state_for(self.mood, self._current_strain())
        self.queue_draw()

    def _on_realize(self, _widget):
        self.frames.target = self.get_window()

    def sprite_pos(self):
        return self.pos

    def workarea_at(self, point):
        return workarea_at(point)

    def bounds(self, point=None):
        if point is None:
            point = (self.pos[0] + self.frames.width / 2, self.pos[1] + self.frames.height / 2)
        wa = self.workarea_at(point)
        return (wa.x + EDGE, wa.y + EDGE,
                max(wa.x + EDGE, wa.x + wa.width - self.frames.width - EDGE),
                max(wa.y + EDGE, wa.y + wa.height - self.frames.height - EDGE))

    def clamp(self, x, y, point=None):
        x0, y0, x1, y1 = self.bounds(point)
        return (min(x1, max(x0, x)), min(y1, max(y0, y)))

    def apply_position(self):
        self.move(int(round(self.pos[0])) - MARGIN, int(round(self.pos[1])) - MARGIN)
        self._follow_bubble()

    def _bubble_anchor(self):
        art = self.frames.art
        x, y = self.pos
        anchor_x = x + art["x"] + art["w"] * 0.5
        top = y + max(0, art["y"] + art["h"] * 0.02)
        bottom = y + self.frames.height + 4
        return anchor_x, top, bottom

    def _follow_bubble(self):
        ax, top, bottom = self._bubble_anchor()
        self.bubble.follow(ax, top, bottom, self.workarea_at((ax, top)))

    # -- animation clock ----------------------------------------------------
    def start_clock(self):
        self._schedule(fast=False)

    def stop_clock(self):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def _schedule(self, fast):
        if self._tick_id and fast == self._fast:
            return
        self.stop_clock()
        self._fast = fast
        self._tick_id = GLib.timeout_add(16 if fast else int(1000 / self.frames.fps), self._tick)

    def _transient(self):
        return bool(self.fade or self.hop_started or self.particles or self.drag
                    or self.inertia or abs(self.tilt) > 0.05)

    def _tick(self):
        now = time.monotonic()
        if self.inertia:
            self._step_inertia()
        if self.paused_frame is None:
            count = self.frames.count(self.state)
            self.frame = int((now - self.start) * self.frames.fps) % count
        if self.fade and now - self.fade[1] > 0.28:
            self.fade = None
        if self.hop_started and now - self.hop_started > 0.72:
            self.hop_started = None
        if self.particles:
            self.particles = [p for p in self.particles if now - p["t0"] < p["life"] + p["delay"]]
        if not self.drag:
            self.tilt *= 0.8
        self._update_shape()
        self.queue_draw()
        fast = self._transient()
        if fast != self._fast:
            # Replace this timer with one at the other rate.
            self._tick_id = None
            self._schedule(fast)
            return False
        return True

    def _update_shape(self):
        key = (id(self.frames), self.state)
        if key == self._shown_region_key or self.drag:
            return
        region = self.frames.region(self.state).copy()
        region.translate(MARGIN, MARGIN)
        self.input_shape_combine_region(region)
        self._shown_region_key = key

    # -- drawing ---------------------------------------------------------------
    def _on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        now = time.monotonic()
        frames = self.frames
        art = frames.art
        opacity = float(self.config["opacity"])
        oy = MARGIN
        if self.hop_started:
            oy += hop_offset(min(1.0, (now - self.hop_started) / 0.72))

        if self.config["glow"]:
            breathe = 0.5 + 0.5 * math.sin(now * 2 * math.pi / 6.5)
            cr.set_source_surface(self._glow_surface(), 0, oy - MARGIN)
            cr.paint_with_alpha(opacity * (0.72 + 0.28 * breathe))

        cr.save()
        if abs(self.tilt) > 0.05:
            px, py = MARGIN + frames.width / 2, oy + frames.height
            cr.translate(px, py)
            cr.rotate(math.radians(self.tilt))
            cr.translate(-px, -py)
        index = self.paused_frame if self.paused_frame is not None else self.frame
        current = frames.surface(self.state, index)
        if self.fade:
            k = min(1.0, (now - self.fade[1]) / 0.28)
            old = self.fade[0]
            cr.set_source_surface(old, MARGIN, oy)
            cr.paint_with_alpha(opacity * (1 - k))
            cr.set_source_surface(current, MARGIN, oy)
            cr.paint_with_alpha(opacity * k)
        else:
            cr.set_source_surface(current, MARGIN, oy)
            cr.paint_with_alpha(opacity)
        cr.restore()

        if self.particles:
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription("Sans 15px"))
            for p in self.particles:
                t = (now - p["t0"] - p["delay"]) / p["life"]
                if t < 0:
                    continue
                e = 1 - (1 - t) ** 3
                alpha = min(1.0, t / 0.16) * (1 - t)
                cr.save()
                cr.translate(MARGIN + art["x"] + art["w"] * p["x"] + p["dx"] * e,
                             oy + art["y"] + art["h"] * p["y"] + p["dy"] * e)
                cr.rotate(math.radians(p["rot"] * e))
                scale = 0.4 + 0.65 * e
                cr.scale(scale, scale)
                layout.set_text(p["glyph"], -1)
                _, ext = layout.get_pixel_extents()
                cr.move_to(-ext.width / 2, -ext.height / 2)
                cr.push_group()
                PangoCairo.show_layout(cr, layout)
                cr.pop_group_to_source()
                cr.paint_with_alpha(alpha)
                cr.restore()
        return True

    def _glow_surface(self):
        if self._glow is not None and self._glow[0] == self.mood:
            return self._glow[1]
        art = self.frames.art
        surface = self.get_window().create_similar_surface(
            cairo.CONTENT_COLOR_ALPHA, self.win_w, self.win_h)
        cr = cairo.Context(surface)
        cx = MARGIN + art["x"] + art["w"] * 0.5
        cy = MARGIN + art["y"] + art["h"] * 0.48
        radius = art["w"] * 0.59
        r, g, b = GLOWS[self.mood]
        grad = cairo.RadialGradient(cx, cy, 0, cx, cy, radius)
        grad.add_color_stop_rgba(0, r, g, b, 0.34)
        grad.add_color_stop_rgba(0.33, r * 0.8, g * 0.85, b, 0.19)
        grad.add_color_stop_rgba(0.56, r * 0.8, g * 0.85, b, 0.06)
        grad.add_color_stop_rgba(0.72, r * 0.8, g * 0.85, b, 0)
        cr.set_source(grad)
        cr.paint()
        self._glow = (self.mood, surface)
        return surface

    # -- moods ----------------------------------------------------------------------
    def _current_strain(self):
        if self.state.startswith("thinking-"):
            return int(self.state.rsplit("-", 1)[1])
        return 0

    def _state_for(self, mood, strain):
        name = mood if not strain else f"{mood}-{strain}"
        return name if name in self.frames.states else mood

    def _switch_state(self, state):
        if state == self.state:
            return
        index = self.paused_frame if self.paused_frame is not None else self.frame
        self.fade = (self.frames.surface(self.state, index), time.monotonic())
        self.state = state
        self.start = time.monotonic()
        self._schedule(fast=True)

    def set_mood(self, mood, announce=True):
        mood = mood if mood in MOODS else "neutral"
        for timer in self._think_timers:
            GLib.source_remove(timer)
        self._think_timers = []
        self.mood = mood
        self._switch_state(self._state_for(mood, 0))
        if mood == "thinking":
            def strain(level):
                self._think_timers = [t for t in self._think_timers if t != handle[level]]
                if self.mood == "thinking":
                    self._switch_state(self._state_for("thinking", level))
                return False
            handle = {}
            handle[1] = GLib.timeout_add(2800, strain, 1)
            handle[2] = GLib.timeout_add(6800, strain, 2)
            self._think_timers = [handle[1], handle[2]]
        self.config["mood"] = mood
        self.config.save()
        if announce:
            self.say(MOOD_LINES[mood])

    # -- speech, feeding ---------------------------------------------------------------
    def say(self, text=None, duration=None):
        if not text:
            text = self._lines[self._line_index % len(self._lines)]
            self._line_index += 1
        ax, top, bottom = self._bubble_anchor()
        self.bubble.show_text(text, ACCENTS[self.mood], ax, top, bottom,
                              self.workarea_at((ax, top)), duration)
        return text

    def feed(self):
        line = FEED_LINES[self._feed_index % len(FEED_LINES)]
        self._feed_index += 1
        self.say(line, 6400)
        now = time.monotonic()
        self.hop_started = now
        for i in range(14):
            angle = -math.pi / 2 + (random.random() - 0.5) * math.pi * 1.4
            dist = 44 + random.random() * 74
            self.particles.append({
                "glyph": "✦" if i % 4 == 0 else "🍚",
                "x": 0.44 + random.random() * 0.12,
                "y": 0.36 + random.random() * 0.14,
                "dx": math.cos(angle) * dist,
                "dy": math.sin(angle) * dist,
                "rot": (random.random() - 0.5) * 300,
                "t0": now,
                "delay": random.random() * 0.13,
                "life": 0.9,
            })
        self._schedule(fast=True)

    # -- pointer --------------------------------------------------------------------------
    def _on_press(self, _widget, event):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return True
        if event.button == 3:
            self.app.popup_menu(event)
            return True
        if event.button == 2:
            self.feed()
            return True
        if event.button != 1:
            return False
        self.inertia = None
        self.drag = {
            "start": (event.x_root, event.y_root),
            "origin": self.pos,
            "last": (event.x_root, event.y_root, time.monotonic()),
            "v": (0.0, 0.0),
            "moved": False,
        }
        self._schedule(fast=True)
        return True

    def _on_motion(self, _widget, event):
        drag = self.drag
        if not drag:
            return False
        dx = event.x_root - drag["start"][0]
        dy = event.y_root - drag["start"][1]
        if not drag["moved"] and math.hypot(dx, dy) > 5:
            drag["moved"] = True
            self.bubble.dismiss()
            self.paused_frame = self.frame
            # Accept input on the whole window while she's held, in case the
            # pointer outruns her silhouette between frames.
            self.input_shape_combine_region(None)
            self._shown_region_key = None
        if drag["moved"]:
            point = (event.x_root, event.y_root)
            self.pos = self.clamp(drag["origin"][0] + dx, drag["origin"][1] + dy, point)
            self.apply_position()
            now = time.monotonic()
            lx, ly, lt = drag["last"]
            dt = max(0.001, now - lt) * 1000
            ivx, ivy = (event.x_root - lx) / dt, (event.y_root - ly) / dt
            vx, vy = drag["v"]
            drag["v"] = (vx * 0.72 + ivx * 0.28, vy * 0.72 + ivy * 0.28)
            drag["last"] = (event.x_root, event.y_root, now)
            self.tilt = max(-5.0, min(5.0, ivx * 2.4))
        return True

    def _on_release(self, _widget, event):
        drag = self.drag
        if not drag or event.button != 1:
            return False
        self.drag = None
        self.paused_frame = None
        self._shown_region_key = None
        if not drag["moved"]:
            self.say()
            return True
        idle = (time.monotonic() - drag["last"][2]) * 1000
        damping = max(0.0, 1 - idle / 110)
        vx, vy = drag["v"][0] * damping, drag["v"][1] * damping
        if math.hypot(vx, vy) > 0.08:
            self.inertia = [max(-1.7, min(1.7, vx)), max(-1.7, min(1.7, vy)), time.monotonic()]
        else:
            self._save_position()
        self._schedule(fast=True)
        return True

    def _step_inertia(self):
        vx, vy, last = self.inertia
        now = time.monotonic()
        steps = max(1, round((now - last) / 0.016))
        x, y = self.pos
        x0, y0, x1, y1 = self.bounds()
        for _ in range(steps):
            vx *= 0.94
            vy *= 0.94
            x += vx * 16
            y += vy * 16
            if x <= x0:
                x, vx = x0, abs(vx) * 0.52
            elif x >= x1:
                x, vx = x1, -abs(vx) * 0.52
            if y <= y0:
                y, vy = y0, abs(vy) * 0.52
            elif y >= y1:
                y, vy = y1, -abs(vy) * 0.52
        self.pos = (x, y)
        self.apply_position()
        if math.hypot(vx, vy) > 0.012:
            self.inertia = [vx, vy, now]
        else:
            self.inertia = None
            self._save_position()

    def _save_position(self):
        self.config["x"], self.config["y"] = round(self.pos[0]), round(self.pos[1])
        self.config.save()

    def reset_position(self):
        wa = self.workarea_at(None)
        self.inertia = None
        self.pos = self.clamp(wa.x + wa.width - self.frames.width - 26,
                              wa.y + wa.height - self.frames.height - 18)
        self.apply_position()
        self._save_position()
        self.say("Back to the usual spot.")

    def hide_all(self):
        self.bubble.dismiss()
        self.stop_clock()
        self.hide()

    def show_all_again(self):
        self.show()
        self._shown_region_key = None
        self.start_clock()


class WhaleApp(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.args = args
        self.config = Config(CONFIG_PATH)
        self.mascot = None
        self.status_icon = None
        self._baking = False
        self._hide_timer = None

    # -- lifecycle ----------------------------------------------------------------
    def do_activate(self):
        if self.mascot:
            if not self.mascot.get_visible():
                self.show_mascot()
            self.mascot.say("I'm already here. Only one of me fits on this desktop.")
            return
        if self._baking:
            return
        self.hold()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit_signal)
        self.bake_then(int(self.config["size"]), self._first_frames)

    def _quit_signal(self):
        self.quit_app()
        return GLib.SOURCE_REMOVE

    def _first_frames(self, frames):
        self.mascot = Mascot(self, frames, managed=self.args.managed)
        self.add_window(self.mascot)
        self.mascot.show_all()
        self.mascot.start_clock()
        if self.mascot.mood != "neutral":
            self.mascot.set_mood(self.mascot.mood, announce=False)
        self._setup_status_icon(frames)
        GLib.timeout_add(900, lambda: self.mascot.say(GREETING, 7200) and False)

    def quit_app(self, *_args):
        if self.mascot:
            self.mascot._save_position()
            self.mascot.bubble.destroy()
            self.mascot.destroy()
        self.release()
        self.quit()

    # -- baking -------------------------------------------------------------------------
    def bake_then(self, width, callback):
        self._baking = True
        progress = Bubble()
        progress_state = {"shown": -1}
        wa = workarea_at(None)
        ax = wa.x + wa.width - width * 0.5 - 30
        top = wa.y + wa.height - 40
        argv = [sys.executable, str(HERE / "bake.py"), "--svg", str(self.args.svg),
                "--width", str(width), "--fps", str(FPS)]
        proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
        stream = Gio.DataInputStream.new(proc.get_stdout_pipe())
        result = {"dir": None}

        def on_line(src, res):
            line, _len = src.read_line_finish_utf8(res)
            if line is None:
                proc.wait_async(None, on_exit)
                return
            if line.startswith("progress "):
                done, total = (int(v) for v in line.split()[1:3])
                pct = int(done * 100 / max(1, total))
                if pct != progress_state["shown"] and (pct % 2 == 0 or pct == 100):
                    progress_state["shown"] = pct
                    progress.show_text(f"Baking my animation frames for this size… {pct}%",
                                       ACCENTS["thinking"], ax, top, top, wa, duration=0)
            elif line.startswith("done "):
                result["dir"] = line[5:].strip()
            src.read_line_async(GLib.PRIORITY_DEFAULT, None, on_line)

        def on_exit(p, res):
            p.wait_finish(res)
            progress.destroy()
            self._baking = False
            if result["dir"]:
                callback(FrameSet(result["dir"]))
                return
            err = p.get_stderr_pipe().read_bytes(65536, None).get_data().decode(errors="replace")
            print(f"whalechan: bake failed:\n{err}", file=sys.stderr)
            if self.mascot:
                self.mascot.say("I couldn't bake frames for that size. Check the terminal.")
            else:
                self.quit()

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, on_line)

    # -- menu ------------------------------------------------------------------------------
    def build_menu(self):
        m = self.mascot
        menu = Gtk.Menu()

        def item(label, callback):
            mi = Gtk.MenuItem.new_with_label(label)
            mi.connect("activate", lambda *_: callback())
            menu.append(mi)
            return mi

        def submenu(label):
            mi = Gtk.MenuItem.new_with_label(label)
            sub = Gtk.Menu()
            mi.set_submenu(sub)
            menu.append(mi)
            return sub

        def radio(sub, group, label, active, callback):
            ri = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            ri.set_active(active)
            ri.connect("toggled", lambda w: w.get_active() and callback())
            sub.append(ri)
            return ri

        if m.get_visible():
            item("Say something", m.say)
            item("Feed 🍚", m.feed)
        else:
            item("Show Whale-chan", self.show_mascot)
        menu.append(Gtk.SeparatorMenuItem())

        moods = submenu("Mood")
        group = None
        for mood in MOODS:
            group = radio(moods, group, mood.capitalize(), mood == m.mood,
                          lambda mood=mood: m.set_mood(mood))

        sizes = submenu("Size")
        group = None
        for label, width in SIZES.items():
            group = radio(sizes, group, f"{label} ({width}px)", width == int(self.config["size"]),
                          lambda width=width: self.set_size(width))

        opacity = submenu("Opacity")
        group = None
        for value in OPACITIES:
            group = radio(opacity, group, f"{int(value * 100)}%",
                          abs(value - float(self.config["opacity"])) < 0.01,
                          lambda value=value: self.set_opacity(value))

        glow = Gtk.CheckMenuItem.new_with_label("Glow")
        glow.set_active(bool(self.config["glow"]))
        glow.connect("toggled", lambda w: self.set_glow(w.get_active()))
        menu.append(glow)

        menu.append(Gtk.SeparatorMenuItem())
        item("Back to the corner", m.reset_position)
        if m.get_visible():
            item("Hide for 10 minutes", lambda: self.hide_mascot(600))
            item("Hide", lambda: self.hide_mascot(None))
        menu.append(Gtk.SeparatorMenuItem())
        item("Quit", self.quit_app)
        menu.show_all()
        return menu

    def popup_menu(self, event=None):
        menu = self.build_menu()
        self._menu = menu  # keep a reference while it is open
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_pointer(None)

    # -- actions -----------------------------------------------------------------------------
    def set_size(self, width):
        if width == int(self.config["size"]) or self._baking:
            return
        self.mascot.say("Hold on, resizing…", 2000)

        def done(frames):
            self.config["size"] = width
            self.config.save()
            self.mascot.set_frames(frames)
            self._setup_status_icon(frames)
            self.mascot.say("How's this?")

        self.bake_then(width, done)

    def set_opacity(self, value):
        self.config["opacity"] = value
        self.config.save()
        self.mascot.queue_draw()

    def set_glow(self, on):
        self.config["glow"] = bool(on)
        self.config.save()
        self.mascot.queue_draw()

    def hide_mascot(self, seconds):
        self.mascot.hide_all()
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None
        if seconds:
            def back():
                self._hide_timer = None
                self.show_mascot()
                self.mascot.say("Break's over. I'm back.")
                return False
            self._hide_timer = GLib.timeout_add_seconds(seconds, back)

    def show_mascot(self):
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None
        self.mascot.show_all_again()

    def toggle_mascot(self):
        if self.mascot.get_visible():
            self.hide_mascot(None)
        else:
            self.show_mascot()

    # -- tray -----------------------------------------------------------------------------------
    def _setup_status_icon(self, frames):
        icon_path = frames.dir / "icon.png"
        if not icon_path.exists():
            frames.write_icon(icon_path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            if self.status_icon is None:
                self.status_icon = Gtk.StatusIcon.new_from_file(str(icon_path))
                self.status_icon.set_tooltip_text("Whale-chan")
                self.status_icon.set_title("Whale-chan")
                self.status_icon.connect("activate", lambda *_: self.toggle_mascot())
                self.status_icon.connect("popup-menu", self._on_tray_menu)
            else:
                self.status_icon.set_from_file(str(icon_path))

    def _on_tray_menu(self, icon, button, activate_time):
        menu = self.build_menu()
        self._menu = menu
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)


def main():
    parser = argparse.ArgumentParser(description="Whale-chan desktop mascot (X11)")
    parser.add_argument("--svg", default=str(DEFAULT_SVG), help="rigged mascot SVG to bake")
    parser.add_argument("--managed", action="store_true",
                        help="use a window-manager-managed utility window instead of an override-redirect one")
    args = parser.parse_args()
    if Gdk.Display.get_default() is None or "X11" not in type(Gdk.Display.get_default()).__name__:
        print("whalechan: needs an X11 session (GDK_BACKEND=x11).", file=sys.stderr)
    app = WhaleApp(args)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
