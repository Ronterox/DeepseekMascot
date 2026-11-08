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
import re
import signal
import subprocess
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

from protocol import EVENTS, MOOD_REGISTRY, MOODS, normalize_event, parse_plain, socket_path, strains  # noqa: E402

try:
    from x11watch import X11Watch  # noqa: E402
except ImportError:  # python-xlib missing: no window/idle awareness
    X11Watch = None

APP_ID = "io.github.whalechan.Desktop"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SVG = ROOT / "assets" / "whale-chan.svg"
SCRIPTS_PATH = ROOT / "scripts"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "whalechan" / "config.json"

FPS = 20
MARGIN = 64           # transparent room around the sprite for hops, glow, rice and poofs
EDGE = 8              # keep the sprite this far inside the work area
SIZES = {"Small": 200, "Medium": 260, "Large": 340, "X-Large": 440}
OPACITIES = [1.0, 0.85, 0.7, 0.5]
# Restarting is a hand-off: this helper waits for the old process to release the
# Gtk.Application D-Bus name, then execs a fresh mascot with the same arguments.
RESTART_HELPER = """
import os, sys, time
pid = int(sys.argv[1])
def running(pid):
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            data = f.read().rsplit(b")", 1)[1]
    except (OSError, IndexError):
        return False
    return data.split()[:1] != [b"Z"]
deadline = time.monotonic() + 15
while running(pid) and time.monotonic() < deadline:
    time.sleep(0.05)
os.execv(sys.argv[2], sys.argv[2:])
"""

RUNNING_PROCS: dict[str, subprocess.Popen[bytes]] = {}


class _ByMood(dict):
    """Per-mood values from assets/moods.json; moods without one get the default mood's."""

    def __init__(self, get, fallback):
        super().__init__((m["name"], get(m)) for m in MOOD_REGISTRY if get(m))
        default = next((m["name"] for m in MOOD_REGISTRY if m.get("default")), "neutral")
        self.fallback = self.get(default, fallback)

    def __missing__(self, mood):
        return self.fallback


def _theme_rgb(key):
    return lambda mood: tuple(float(c) for c in (mood.get("theme") or {}).get(key) or ()) or None


ACCENTS = _ByMood(_theme_rgb("desktopAccent"), (0.333, 0.741, 0.969))
GLOWS = _ByMood(_theme_rgb("desktopGlow"), (0.50, 0.88, 1.0))
MOOD_LABELS = {m["name"]: m.get("label") or m["name"].capitalize() for m in MOOD_REGISTRY}
STRAINS = {m["name"]: strains(m) for m in MOOD_REGISTRY}

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
MOOD_LINES = _ByMood(lambda mood: mood.get("line"), "Back to standby. Very professional.")
REACT_LINES = {
    "working": [
        "On it. Thinking very hard. Please admire my focus.",
        "Processing. Do not disturb the genius.",
        "Working… I'll pretend this is easy.",
    ],
    "success": [
        "Done! Flawless, obviously.",
        "It worked! I'll accept payment in rice.",
        "Success. You may now praise me.",
    ],
    "failure": [
        "It failed. I'm not crying, my face is just leaking.",
        "That didn't work. Can we pretend it did?",
        "Broken. I blame the compiler. And the moon.",
    ],
    "error": [
        "Error?! Who did this. Was it you.",
        "Something exploded. I'm aggressively recalibrating.",
        "Unacceptable. Fix it before my rice gets cold.",
    ],
    "attention": [
        "Hey! Over here. You're needed.",
        "Psst. Someone's waiting on you.",
        "Excuse me, your input is requested. Politely. For now.",
    ],
}
WAKE_LINES = [
    "I wasn't sleeping! I was… optimizing.",
    "Huh? Oh. You're back. I was guarding the desktop. With my eyes closed.",
    "Five more minutes… fine, I'm up.",
]
SLEEP_LINE = "Nobody's around… I'll just rest my eyes. Zzz."

# Comments when you switch apps: (field, regex, mood flash or None, lines).
# Title rules come first so browser tabs win over the browser itself.
APP_RULES = [
    ("title", r"youtube", "smug", ["YouTube? For research, I'm sure.", "One video. I'm counting."]),
    ("title", r"deepseek", "happy", ["Ooh, visiting my people? Say hi from me."]),
    ("title", r"chatgpt|claude|gemini|copilot", "smug",
     ["Asking another AI? I'm right here, you know.", "Another model? Bold. I'll remember this."]),
    ("title", r"stack ?overflow", "thinking", ["Stack Overflow. Copy responsibly."]),
    ("title", r"github", None, ["GitHub! Star something cute today."]),
    ("class", r"code|codium|cursor|zed|jetbrains|sublime|kate|neovide|nvim|vi|vim", "thinking",
     ["Coding time. I'll supervise. Vigorously.", "Write good code. I'm watching. Lovingly."]),
    ("class", r"kitty|terminal|alacritty|wezterm|konsole|tilix|xterm|foot", None,
     ["Terminal time. Type fast, I'm judging.", "Ah, the hacker screen. Very cool."]),
    ("class", r"blender|godot|krita|gimp|inkscape|aseprite|magica|pico-?8|picotron", "happy",
     ["Making art? Draw me next. All my sides are good sides.", "Ooh, creative mode. I'll hold still. Mostly."]),
    ("class", r"steam|lutris|heroic", "happy", ["Games? Five minutes. I'm counting. In rice."]),
    ("class", r"discord|slack|telegram|signal|element|vesktop", None, ["Chatting? Tell them Whale-chan says hi."]),
    ("class", r"spotify|rhythmbox|ytm", "happy", ["Music! Is it whale songs? It should be whale songs."]),
]
APP_COMMENT_COOLDOWN = 180       # seconds between any two app comments
APP_RULE_COOLDOWN = 20 * 60      # seconds before the same rule fires again
GRAVITY = 2600                   # px/s²
# Moods marked "slow" in the registry, with their strain variants.
SLOW_STATES = {f"{m['name']}-{level}" if level else m["name"]
               for m in MOOD_REGISTRY if m.get("slow") for level in [0, *strains(m)]}
PERCH_SNAP = 36                  # how close her feet must be to a window top to perch

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


POOF_TIME = 0.6      # seconds a mood-change poof lasts


def squash(t, strength):
    """Squash-and-stretch scale (sx, sy) t seconds into a poof."""
    keys = [(0, 1, 1), (0.07, 1.12, 0.86), (0.18, 0.93, 1.09), (0.3, 1.03, 0.97), (0.42, 1, 1)]
    for (t0, x0, y0), (t1, x1, y1) in zip(keys, keys[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            k = k * k * (3 - 2 * k)
            sx, sy = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            return 1 + (sx - 1) * strength, 1 + (sy - 1) * strength
    return 1.0, 1.0


def star_path(cr, r, inner=0.3):
    for i in range(8):
        a = math.radians(i * 45 - 90)
        rr = r if i % 2 == 0 else r * inner
        (cr.move_to if i == 0 else cr.line_to)(rr * math.cos(a), rr * math.sin(a))
    cr.close_path()


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
    DEFAULTS = {"size": 260, "mood": "neutral", "opacity": 1.0, "glow": True, "x": None, "y": None,
                "follow": True, "perch": True, "comments": True, "sleep": True, "sleep_after": 240,
                "fullscreen_hide": False,
                # agent work: chin-tap thinking, then harder after 5 min, stressed after 10
                "think_harder_after": 300, "think_stressed_after": 600}

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
        self._caches = {}          # state -> {index: surface}, most recent last
        self._feet = None

    def count(self, state):
        return self.states[state]["frames"]

    def _decode(self, state, index):
        return cairo.ImageSurface.create_from_png(str(self.dir / state / f"{index:04d}.png"))

    @property
    def feet(self):
        """Distance from the frame top to the soles of her feet (neutral pose)."""
        if self._feet is None:
            ext = self.region("neutral").get_extents()
            self._feet = ext.y + ext.height - 3
        return self._feet

    def surface(self, state, index):
        cache = self._caches.pop(state, None)
        if cache is None:
            cache = {}
            while len(self._caches) >= 2:  # current state + the one we fade or glance from
                self._caches.pop(next(iter(self._caches)))
        self._caches[state] = cache
        surface = cache.get(index)
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
            cache[index] = surface
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
        self.gaze = None          # None (straight ahead) or look-l / look-r / look-ul / look-ur
        self._gaze_candidate = (None, 0.0)
        self._gaze_changed = 0.0
        self._pointer = (None, None, 0.0)
        self.sleeping = False
        self.slept_at = 0.0
        self.speed = 1.0
        self.perch = None         # {"xid": client window, "dx": offset from its left edge}
        self.falling = None       # {"vy": px/s, "t": last step}
        self.entrance = None      # (started, initial y offset)
        self.poof = None          # smoke puffs + squash on mood changes, appearing and vanishing
        self._vanish_timer = None
        self._think_timers = []
        self._revert_timer = None
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
        dy = 0
        if self.entrance:
            k = min(1.0, (time.monotonic() - self.entrance[0]) / 0.55)
            dy = self.entrance[1] * (1 - ease_out_back(k))
        self.move(int(round(self.pos[0])) - MARGIN, int(round(self.pos[1] + dy)) - MARGIN)
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
        interval = 16 if fast else int(1000 * self._frame_step() / (self.frames.fps * self.speed))
        self._tick_id = GLib.timeout_add(interval, self._tick)

    def _frame_step(self):
        """Slow states play every other baked frame (10 fps) to save CPU."""
        return 2 if self.state in SLOW_STATES else 1

    def _transient(self):
        return bool(self.fade or self.hop_started or self.particles or self.drag
                    or self.inertia or self.falling or self.entrance or self.poof
                    or abs(self.tilt) > 0.05)

    def _tick(self):
        now = time.monotonic()
        if self.inertia:
            self._step_inertia()
        if self.falling:
            self._step_fall(now)
        if self.entrance:
            self.apply_position()
            if now - self.entrance[0] > 0.55:
                self.entrance = None
        if self.paused_frame is None:
            count = self.frames.count(self.state)
            n = int((now - self.start) * self.frames.fps * self.speed)
            self.frame = (n - n % self._frame_step()) % count
        if self.fade and now - self.fade[1] > self.fade[2]:
            self.fade = None
        if self.poof and now - self.poof["t0"] > POOF_TIME:
            self.poof = None
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

        poof = self.poof
        sprite_alpha = 1.0
        if poof:
            pt = now - poof["t0"]
            if poof["vanish"]:
                sprite_alpha = max(0.0, 1 - pt / 0.16)
            elif poof["appear"]:
                sprite_alpha = min(1.0, pt / 0.12)
        opacity_all = opacity
        opacity *= sprite_alpha

        if self.config["glow"]:
            breathe = 0.5 + 0.5 * math.sin(now * 2 * math.pi / 6.5)
            cr.set_source_surface(self._glow_surface(), 0, oy - MARGIN)
            cr.paint_with_alpha(opacity * (0.72 + 0.28 * breathe))

        if poof:
            self._draw_puffs(cr, now, oy, front=False, opacity=opacity_all)

        cr.save()
        if abs(self.tilt) > 0.05:
            px, py = MARGIN + frames.width / 2, oy + frames.height
            cr.translate(px, py)
            cr.rotate(math.radians(self.tilt))
            cr.translate(-px, -py)
        if poof and not poof["vanish"]:
            sx, sy = squash(now - poof["t0"], poof["strength"])
            px, py = MARGIN + frames.width / 2, oy + frames.feet
            cr.translate(px, py)
            cr.scale(sx, sy)
            cr.translate(-px, -py)
        index = self.paused_frame if self.paused_frame is not None else self.frame
        current = frames.surface(self.state, index)
        if self.fade:
            k = min(1.0, (now - self.fade[1]) / self.fade[2])
            old = self.fade[0]
            cr.set_source_surface(old, MARGIN, oy)
            cr.paint_with_alpha(opacity * (1 - k))
            cr.set_source_surface(current, MARGIN, oy)
            cr.paint_with_alpha(opacity * k)
        else:
            cr.set_source_surface(current, MARGIN, oy)
            cr.paint_with_alpha(opacity)
        cr.restore()

        if poof:
            self._draw_puffs(cr, now, oy, front=True, opacity=opacity_all)

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

    def start_poof(self, strength=1.0, appear=False, vanish=False):
        """Anime smoke poof: puffs around her, sparkles in the mood colour, squash bounce."""
        art = self.frames.art
        scale = art["w"] / 260
        cx, cy = art["x"] + art["w"] * 0.5, art["y"] + art["h"] * 0.56
        rx, ry = art["w"] * 0.33, art["h"] * 0.35
        count = 10 if strength >= 1 else 6
        puffs = []
        for i in range(count):
            a = 2 * math.pi * i / count + random.uniform(-0.25, 0.25)
            puffs.append({
                "x": cx + math.cos(a) * rx, "y": cy + math.sin(a) * ry,
                "dx": math.cos(a), "dy": math.sin(a),
                "r": random.uniform(13, 19) * scale * (0.7 + 0.3 * strength),
                "delay": random.uniform(0, 0.06), "life": random.uniform(0.42, 0.56),
                "front": i % 2 == 0, "spin": random.uniform(-1, 1),
            })
        sparks = []
        for _ in range(5 if strength >= 1 else 3):
            a = random.uniform(0, 2 * math.pi)
            sparks.append({"dx": math.cos(a), "dy": math.sin(a) * 0.9,
                           "dist": random.uniform(60, 96) * scale, "size": random.uniform(6, 9) * scale,
                           "delay": random.uniform(0.02, 0.1), "rot": random.uniform(-2, 2)})
        self.poof = {"t0": time.monotonic(), "strength": strength, "puffs": puffs, "sparks": sparks,
                     "center": (cx, cy), "accent": ACCENTS[self._look()],
                     "appear": appear, "vanish": vanish}
        self._schedule(fast=True)

    def _draw_puffs(self, cr, now, oy, front, opacity):
        poof = self.poof
        scale = self.frames.art["w"] / 260
        circles = []
        for p in poof["puffs"]:
            if p["front"] != front:
                continue
            t = (now - poof["t0"] - p["delay"]) / p["life"]
            if not 0 <= t <= 1:
                continue
            e = 1 - (1 - t) ** 2
            x = MARGIN + p["x"] + p["dx"] * 22 * scale * e
            y = oy + p["y"] + p["dy"] * 22 * scale * e - 6 * scale * e
            # pop out fast, stay solid white, then shrink away while fading
            grow = min(1.0, t / 0.3)
            r = p["r"] * (0.35 + 0.75 * (1 - (1 - grow) ** 2)) * (1 - 0.35 * max(0.0, (t - 0.55) / 0.45))
            alpha = min(1.0, (1 - t) / 0.45) * opacity
            lobes = [(x, y, r)]
            for k in (-1, 1):
                ang = p["spin"] + k * 1.1
                lobes.append((x + math.cos(ang) * r * 0.62, y + math.sin(ang) * r * 0.4 + r * 0.2, r * 0.66))
            circles.append((lobes, alpha))
        # outlines first, then white fills on top, so overlapping lobes read as one cloud
        for lobes, alpha in circles:
            cr.set_source_rgba(0.62, 0.71, 0.86, alpha * 0.9)
            for x, y, r in lobes:
                cr.new_sub_path()
                cr.arc(x, y, r + 1.6, 0, 2 * math.pi)
            cr.fill()
        for lobes, alpha in circles:
            cr.set_source_rgba(1, 1, 1, alpha)
            for x, y, r in lobes:
                cr.new_sub_path()
                cr.arc(x, y, r, 0, 2 * math.pi)
            cr.fill()
        if not front:
            return
        cx, cy = poof["center"]
        r, g, b = poof["accent"]
        for sp in poof["sparks"]:
            t = (now - poof["t0"] - sp["delay"]) / 0.45
            if not 0 <= t <= 1:
                continue
            e = 1 - (1 - t) ** 3
            cr.save()
            cr.translate(MARGIN + cx + sp["dx"] * sp["dist"] * e, oy + cy + sp["dy"] * sp["dist"] * e)
            cr.rotate(sp["rot"] * e)
            size = sp["size"] * math.sin(math.pi * min(1.0, t * 1.2))
            star_path(cr, max(0.1, size))
            cr.set_source_rgba(r, g, b, (1 - t * 0.6) * opacity)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, (1 - t) * opacity)
            cr.set_line_width(1.2)
            cr.stroke()
            cr.restore()

    def _glow_surface(self):
        look = self._look()
        if self._glow is not None and self._glow[0] == look:
            return self._glow[1]
        art = self.frames.art
        surface = self.get_window().create_similar_surface(
            cairo.CONTENT_COLOR_ALPHA, self.win_w, self.win_h)
        cr = cairo.Context(surface)
        cx = MARGIN + art["x"] + art["w"] * 0.5
        cy = MARGIN + art["y"] + art["h"] * 0.48
        radius = art["w"] * 0.59
        r, g, b = GLOWS[look]
        grad = cairo.RadialGradient(cx, cy, 0, cx, cy, radius)
        grad.add_color_stop_rgba(0, r, g, b, 0.34)
        grad.add_color_stop_rgba(0.33, r * 0.8, g * 0.85, b, 0.19)
        grad.add_color_stop_rgba(0.56, r * 0.8, g * 0.85, b, 0.06)
        grad.add_color_stop_rgba(0.72, r * 0.8, g * 0.85, b, 0)
        cr.set_source(grad)
        cr.paint()
        self._glow = (look, surface)
        return surface

    def _look(self):
        """The mood she visibly shows (a nap shows as sleepy over neutral)."""
        return "sleepy" if self.sleeping else self.mood

    # -- moods ----------------------------------------------------------------------
    def _current_strain(self):
        tail = self.state[len(self.mood) + 1:]
        if self.state.startswith(f"{self.mood}-") and tail.isdigit():
            return int(tail)
        return 0

    def _state_for(self, mood, strain):
        states = self.frames.states
        if mood == "neutral" and not strain:
            if self.sleeping and "sleepy" in states:
                return "sleepy"
            if self.gaze and f"neutral-{self.gaze}" in states:
                return f"neutral-{self.gaze}"
        name = mood if not strain else f"{mood}-{strain}"
        return name if name in states else mood

    def _switch_state(self, state, fade=0.28, keep_phase=False, poof=0.0):
        """Crossfade to another baked state.

        keep_phase continues the frame clock, for states baked with the same loop
        period (neutral and its gaze variants), so only the eyes and head move.
        """
        if state == self.state:
            return
        index = self.paused_frame if self.paused_frame is not None else self.frame
        if poof:
            fade = min(fade, 0.14)  # swap during the squash, hidden by the smoke
            self.start_poof(poof)
        self.fade = (self.frames.surface(self.state, index), time.monotonic(), fade)
        self.state = state
        if not keep_phase:
            self.start = time.monotonic()
        self._schedule(fast=True)

    # -- gaze ---------------------------------------------------------------------------
    def update_gaze(self, px, py):
        """Glance toward the pointer (neutral mood only; baked gaze variants)."""
        now = time.monotonic()
        lx, ly, moved = self._pointer
        if lx is None or abs(px - lx) + abs(py - ly) > 3:
            moved = now
        self._pointer = (px, py, moved)
        target = None
        if (self.config["follow"] and self.mood == "neutral" and not self.sleeping
                and not self.drag and now - moved < 6):
            art = self.frames.art
            fx = self.pos[0] + art["x"] + art["w"] * 0.5
            fy = self.pos[1] + art["y"] + art["h"] * 0.3
            dx, dy = px - fx, py - fy
            if math.hypot(dx, dy) > art["w"] * 0.45:
                angle = math.degrees(math.atan2(-dy, dx))   # 0 = right, 90 = up
                if 25 < angle < 155:
                    target = "look-ul" if dx < 0 else "look-ur"
                elif -60 < angle <= 25:
                    target = "look-r"
                elif angle >= 155 or angle < -120:
                    target = "look-l"
        if target != self._gaze_candidate[0]:
            self._gaze_candidate = (target, now)
            return
        if (target != self.gaze and now - self._gaze_candidate[1] >= 0.2
                and now - self._gaze_changed >= 0.5):
            self.gaze = target
            self._gaze_changed = now
            if self.mood == "neutral" and not self.sleeping:
                self._switch_state(self._state_for("neutral", 0), fade=0.18, keep_phase=True)

    # -- sleep ---------------------------------------------------------------------------
    def sleep(self):
        if self.sleeping or self.mood != "neutral" or "sleepy" not in self.frames.states:
            return
        self.sleeping = True
        self.slept_at = time.monotonic()
        self.gaze = None
        self.bubble.dismiss()
        self.say(SLEEP_LINE, 3500)
        self._switch_state("sleepy", fade=0.8)

    def wake(self, announce=True):
        if not self.sleeping:
            return
        self.sleeping = False
        self._switch_state(self._state_for(self.mood, 0), fade=0.25, poof=1.0)
        if announce and time.monotonic() - self.slept_at > 20:
            self.say(random.choice(WAKE_LINES))

    # -- standing on windows ----------------------------------------------------------------
    def _center_x(self):
        art = self.frames.art
        return self.pos[0] + art["x"] + art["w"] * 0.5

    def _surfaces(self):
        x11 = self.app.x11
        return x11.surfaces() if x11 else []

    def _perchable(self, rect, info, wa):
        x, y, w, _h = rect
        cx = self._center_x()
        return (not info.fullscreen and not info.maximized and x + 12 <= cx <= x + w - 12
                and y - self.frames.feet >= wa.y + EDGE)

    def try_perch(self):
        """After a drop: stand on the window top edge under her feet, if close enough."""
        if not self.config["perch"]:
            return False
        feet = self.pos[1] + self.frames.feet
        cx = self._center_x()
        wa = self.workarea_at((cx, feet))
        for xid, rect, info in self._surfaces():
            x, y, w, h = rect
            if abs(feet - y) <= PERCH_SNAP and self._perchable(rect, info, wa):
                self._land_on(xid, rect)
                return True
            if x <= cx <= x + w and y <= feet <= y + h:
                break  # her feet are in front of this window's body; lower windows are hidden
        return False

    def _land_on(self, xid, rect):
        self.perch = {"xid": xid, "dx": self.pos[0] - rect[0]}
        self.pos = (self.pos[0], rect[1] - self.frames.feet)
        self.apply_position()
        self.hop()
        self._save_position()

    def on_windows_changed(self):
        """Follow the window she stands on; fall when it moves away, closes or maximizes."""
        if not self.perch or self.drag:
            return
        for xid, rect, info in self._surfaces():
            if xid == self.perch["xid"]:
                break
        else:
            self.fall()
            return
        wa = self.workarea_at((self._center_x(), rect[1]))
        x = rect[0] + self.perch["dx"]
        y = rect[1] - self.frames.feet
        if info.fullscreen or info.maximized or y < wa.y + EDGE - 1:
            self.fall()
            return
        self.pos = self.clamp(x, y)
        if abs(self.pos[1] - y) > 2:
            self.fall()
            return
        self.apply_position()

    def fall(self):
        self.perch = None
        self.inertia = None
        if not self.falling:
            self.falling = {"vy": 0.0, "t": time.monotonic()}
            self._schedule(fast=True)

    def _step_fall(self, now):
        f = self.falling
        dt = min(0.05, now - f["t"])
        f["t"] = now
        f["vy"] += GRAVITY * dt
        old_feet = self.pos[1] + self.frames.feet
        y = self.pos[1] + f["vy"] * dt
        new_feet = y + self.frames.feet
        cx = self._center_x()
        wa = self.workarea_at((cx, old_feet))
        if self.config["perch"]:
            for xid, rect, info in self._surfaces():
                x, top, w, h = rect
                if old_feet - 1 <= top <= new_feet and self._perchable(rect, info, wa):
                    self.falling = None
                    self._land_on(xid, rect)
                    return
        x0, y0, x1, y1 = self.bounds()
        if y >= y1:
            self.falling = None
            self.pos = (self.pos[0], y1)
            self.apply_position()
            self.hop()
            self._save_position()
            return
        self.pos = (self.pos[0], y)
        self.apply_position()

    # -- workspace switch ------------------------------------------------------------------
    def swim_in(self, direction):
        """Glide in after a workspace switch (Pop!_OS workspaces stack vertically)."""
        self.entrance = (time.monotonic(), 90 * (1 if direction > 0 else -1))
        self.apply_position()
        self._schedule(fast=True)

    def set_mood(self, mood, announce=True, strain=0, escalate=(2.8, 6.8), revert_after=None,
                 persist=True):
        """Change mood.

        Moods with strain variants (`thinking`) escalate through them after the
        `escalate` delays (seconds);
        pass escalate=None to hold `strain`. With `revert_after`, she drops back to
        neutral after that many seconds. Only persistent, non-temporary moods are
        saved as the startup mood.
        """
        mood = mood if mood in MOODS else "neutral"
        changed = mood != self.mood or self.sleeping
        self.sleeping = False
        for timer in self._think_timers:
            GLib.source_remove(timer)
        self._think_timers = []
        if self._revert_timer:
            GLib.source_remove(self._revert_timer)
            self._revert_timer = None
        self.mood = mood
        levels = STRAINS.get(mood, [])
        strain = max(0, min(levels[-1], int(strain or 0))) if levels else 0
        self._switch_state(self._state_for(mood, strain), poof=1.0 if changed else 0.0)
        if levels and escalate:
            def escalate_to(level):
                self._think_timers = [t for t in self._think_timers if t != handles.get(level)]
                if self.mood == mood:
                    self._switch_state(self._state_for(mood, level), poof=0.6)
                return False
            handles = {}
            for level, delay in zip(levels, escalate):
                if level > strain:
                    handles[level] = GLib.timeout_add(int(delay * 1000), escalate_to, level)
            self._think_timers = list(handles.values())
        if revert_after:
            def revert():
                self._revert_timer = None
                self.set_mood("neutral", announce=False, persist=False)
                return False
            self._revert_timer = GLib.timeout_add(int(revert_after * 1000), revert)
        elif persist:
            self.config["mood"] = mood
            self.config.save()
        if announce:
            self.say(MOOD_LINES[mood])

    def react(self, event, text=None, quiet=False):
        """Mood + line for an external event (see protocol.EVENTS)."""
        mood, revert = EVENTS[event]
        if event == "working":
            # Long-running work: chin-tap first, thinking harder after a while,
            # the overthinking meltdown only when it really drags on.
            escalate = (float(self.config["think_harder_after"]), float(self.config["think_stressed_after"]))
            self.set_mood("thinking", announce=False, escalate=escalate, persist=False)
        elif mood:
            self.set_mood(mood, announce=False, revert_after=revert, persist=False)
        if event == "attention":
            self.hop()
        lines = REACT_LINES.get(event)
        if text or (lines and not quiet):
            self.say(text or random.choice(lines))

    # -- speech, feeding ---------------------------------------------------------------
    def say(self, text=None, duration=None):
        if not text:
            text = self._lines[self._line_index % len(self._lines)]
            self._line_index += 1
        ax, top, bottom = self._bubble_anchor()
        self.bubble.show_text(text, ACCENTS[self._look()], ax, top, bottom,
                              self.workarea_at((ax, top)), duration)
        return text

    def hop(self):
        self.hop_started = time.monotonic()
        self._schedule(fast=True)

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
        return line

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
        if self.sleeping:
            self.wake()
        self.inertia = None
        self.falling = None
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
            self.perch = None
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
        elif not self.try_perch():
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
            if not self.try_perch():
                self._save_position()

    def _save_position(self):
        self.config["x"], self.config["y"] = round(self.pos[0]), round(self.pos[1])
        self.config.save()

    def move_to(self, x, y):
        """Place her sprite's top-left at (x, y), then perch if she lands on a window top."""
        self.inertia = None
        self.falling = None
        self.perch = None
        self.pos = self.clamp(float(x), float(y))
        self.apply_position()
        if not self.try_perch():
            self._save_position()

    def reset_position(self):
        wa = self.workarea_at(None)
        self.inertia = None
        self.perch = None
        self.falling = None
        self.pos = self.clamp(wa.x + wa.width - self.frames.width - 26,
                              wa.y + wa.height - self.frames.height - 18)
        self.apply_position()
        self._save_position()
        self.say("Back to the usual spot.")

    def hide_all(self, animate=True):
        self.bubble.dismiss()
        if self._vanish_timer:
            return
        if animate and self.get_visible():
            self.start_poof(1.0, vanish=True)
            self._vanish_timer = GLib.timeout_add(int(POOF_TIME * 1000), self._finish_hide)
        else:
            self._finish_hide()

    def _finish_hide(self):
        self._vanish_timer = None
        self.poof = None
        self.stop_clock()
        self.hide()
        return False

    def is_shown(self):
        """Visible and not in the middle of poofing away."""
        return self.get_visible() and self._vanish_timer is None

    def show_all_again(self):
        if self._vanish_timer:
            GLib.source_remove(self._vanish_timer)
            self._vanish_timer = None
        self.show()
        self._shown_region_key = None
        self.start_clock()
        self.start_poof(1.0, appear=True)


class ControlServer:
    """Line-based JSON control socket (see protocol.py) on the GTK main loop."""

    def __init__(self, path, handler):
        self.path = Path(path)
        self.handler = handler
        self.service = None
        self._clients = set()

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists() or self.path.is_symlink():
            self.path.unlink()  # stale: Gtk.Application already guarantees one instance
        self.service = Gio.SocketService()
        self.service.add_address(Gio.UnixSocketAddress.new(str(self.path)),
                                 Gio.SocketType.STREAM, Gio.SocketProtocol.DEFAULT, None)
        os.chmod(self.path, 0o600)
        self.service.connect("incoming", self._on_incoming)
        self.service.start()

    def stop(self):
        if self.service:
            self.service.stop()
            self.service.close()
            self.service = None
        try:
            self.path.unlink()
        except OSError:
            pass

    def _on_incoming(self, _service, connection, _source):
        reader = Gio.DataInputStream.new(connection.get_input_stream())
        client = (connection, reader)
        self._clients.add(client)
        reader.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line, client)
        return True

    def _on_line(self, reader, result, client):
        connection = client[0]
        try:
            line, _length = reader.read_line_finish_utf8(result)
        except GLib.Error:
            line = None
        if line is None:
            self._clients.discard(client)
            connection.close(None)
            return
        line = line.strip()
        if line:
            try:
                request = json.loads(line) if line.startswith("{") else parse_plain(line)
                reply = self.handler(request if isinstance(request, dict) else {})
            except Exception as exc:  # noqa: BLE001
                reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            data = (json.dumps(reply) + "\n").encode()
            try:
                connection.get_output_stream().write_all(data, None)
            except GLib.Error:
                pass
        reader.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line, client)


class WhaleApp(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.args = args
        self.config = Config(CONFIG_PATH)
        self.mascot = None
        self.control = None
        self._recent_keys = {}
        self.status_icon = None
        self._baking = False
        self._hide_timer = None
        self.x11 = None
        self.user_hidden = False
        self.auto_hidden = False      # hidden because a fullscreen app is active
        self._last_comment = 0.0
        self._rule_times = {}
        self._last_active = None
        self._no_sleep_until = 0.0

    # -- lifecycle ----------------------------------------------------------------
    def do_activate(self):
        if self.mascot:
            if not self.mascot.is_shown():
                self.show_mascot()
            self.mascot.say("I'm already here. Only one of me fits on this desktop.")
            return
        if self._baking:
            return
        self.hold()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit_signal)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit_signal)
        self.control = ControlServer(socket_path(), self.handle_request)
        try:
            self.control.start()
        except GLib.Error as exc:
            print(f"whalechan: control socket unavailable: {exc.message}", file=sys.stderr)
            self.control = None
        self.bake_then(int(self.config["size"]), self._first_frames)

    def _quit_signal(self):
        self.quit_app()
        return GLib.SOURCE_REMOVE

    def _first_frames(self, frames):
        self.mascot = Mascot(self, frames, managed=self.args.managed)
        self.add_window(self.mascot)
        self.mascot.show_all()
        self.mascot.start_clock()
        self.mascot.start_poof(1.0, appear=True)
        if self.mascot.mood != "neutral":
            self.mascot.set_mood(self.mascot.mood, announce=False)
        self._setup_status_icon(frames)
        GLib.timeout_add(900, lambda: self.mascot.say(GREETING, 7200) and False)
        if X11Watch is not None:
            try:
                self.x11 = X11Watch(on_windows=self._on_windows, on_active=self._on_active,
                                    on_desktop=self._on_desktop)
            except Exception as exc:  # noqa: BLE001
                print(f"whalechan: desktop awareness disabled: {exc}", file=sys.stderr)
        GLib.timeout_add(100, self._poll_pointer)
        GLib.timeout_add(1000, self._poll_idle)
        if self.x11:
            self._last_active = self._active_key(self.x11.active())
            self._on_active(self.x11.active(), comment=False)

    # -- desktop awareness --------------------------------------------------------------
    def _poll_pointer(self):
        m = self.mascot
        if m is None:
            return False
        if m.is_shown() and (self.config["follow"] or m.gaze):
            pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
            _screen, x, y = pointer.get_position()
            m.update_gaze(x, y)
        return True

    def _poll_idle(self):
        m = self.mascot
        if m is None:
            return False
        idle = self.x11.idle_ms() if self.x11 else None
        if idle is None:
            return True
        now = time.monotonic()
        if m.sleeping and idle < 2000:
            m.wake()
            self._no_sleep_until = now + 30
        elif (self.config["sleep"] and not m.sleeping and m.is_shown() and m.mood == "neutral"
              and not m.drag and not m.falling and now >= self._no_sleep_until
              and idle >= float(self.config["sleep_after"]) * 1000):
            m.sleep()
        return True

    def _on_windows(self):
        if self.mascot:
            self.mascot.on_windows_changed()

    def _on_desktop(self, old, new):
        m = self.mascot
        if m and m.is_shown():
            m.swim_in(new - old)

    @staticmethod
    def _active_key(info):
        return (info["class"], info["title"]) if info else None

    def _on_active(self, info, comment=True):
        m = self.mascot
        if m is None:
            return
        # Fullscreen apps on her monitor (videos, games, presentations) hide her.
        monitor = Gdk.Display.get_default().get_monitor_at_point(
            int(m.pos[0] + m.frames.width / 2), int(m.pos[1] + m.frames.height / 2)).get_geometry()
        fullscreen = False
        if info and info["fullscreen"] and self.config["fullscreen_hide"]:
            x, y, w, h = info["rect"]
            fullscreen = (x < monitor.x + monitor.width and monitor.x < x + w
                          and y < monitor.y + monitor.height and monitor.y < y + h)
        if fullscreen and not self.auto_hidden:
            self.auto_hidden = True
            if m.is_shown():
                m.hide_all()
        elif not fullscreen and self.auto_hidden:
            self.auto_hidden = False
            if not self.user_hidden:
                m.show_all_again()
        key = self._active_key(info)
        if comment and key != self._last_active:
            self._last_active = key
            self._comment_on(info)

    def _comment_on(self, info):
        m = self.mascot
        now = time.monotonic()
        if (not info or not self.config["comments"] or not m.is_shown() or m.sleeping
                or m.drag or m.mood != "neutral" or m.bubble.get_visible()
                or now - self._last_comment < APP_COMMENT_COOLDOWN):
            return
        app = f"{info['instance']} {info['class']}".lower()
        title = info["title"].lower()
        for index, (field, pattern, mood, lines) in enumerate(APP_RULES):
            if not re.search(pattern, title if field == "title" else app):
                continue
            if now - self._rule_times.get(index, -1e9) < APP_RULE_COOLDOWN:
                return
            self._rule_times[index] = now
            self._last_comment = now
            if mood:
                m.set_mood(mood, announce=False, escalate=None, revert_after=6)
            m.say(random.choice(lines))
            return

    def terminate_proc(self, proc):
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def run_script(self, script, *args):
        """Run a script in the background."""
        script = os.path.join(SCRIPTS_PATH, script)

        if (proc := RUNNING_PROCS.get(script)):
            del RUNNING_PROCS[script]
            self.terminate_proc(proc)

        if not os.path.exists(script):
            print(f"whalechan: {script} not found", file=sys.stderr)
            return

        try:
            proc = subprocess.Popen([script] + list(args), stdin=subprocess.DEVNULL, close_fds=True)
            RUNNING_PROCS[script] = proc
        except OSError as exc:
            print(f"whalechan: {script} failed to run: {exc}", file=sys.stderr)
            self.mascot.say(f"I couldn't run {script!r}. It says: {exc}")

    def restart_app(self, *_args):
        """Replace this process with a fresh one, keeping the same launch arguments."""
        argv = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        try:
            subprocess.Popen([sys.executable, "-c", RESTART_HELPER, str(os.getpid()), *argv],
                             stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        except OSError as exc:
            print(f"whalechan: restart failed: {exc}", file=sys.stderr)
            if self.mascot:
                self.mascot.say("I couldn't restart. Check the terminal.")
            return
        self.quit_app()

    def quit_app(self, *_args):
        if self.x11:
            self.x11.close()
            self.x11 = None
        if self.control:
            self.control.stop()
            self.control = None
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
        for proc in RUNNING_PROCS.values():
            self.terminate_proc(proc)
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

    # -- remote control ------------------------------------------------------------
    def handle_request(self, req):
        cmd = str(req.get("cmd", "")).lower()
        m = self.mascot
        key = req.get("key")
        if key:
            # Several senders (e.g. one OpenCode plugin instance per location) may
            # report the same event; act on the first and drop repeats briefly.
            now = time.monotonic()
            self._recent_keys = {k: t for k, t in self._recent_keys.items() if now - t < 3}
            if key in self._recent_keys:
                return {"ok": True, "duplicate": True}
            self._recent_keys[key] = now
        if cmd == "ping":
            return {"ok": True, "ready": m is not None}
        if cmd == "quit":
            GLib.idle_add(self.quit_app)
            return {"ok": True}
        if m is None:
            return {"ok": False, "error": "Whale-chan is still baking her frames, try again shortly"}
        visible = m.is_shown()
        revert = float(req["for"]) if req.get("for") else None

        if cmd == "status":
            return {"ok": True, "ready": True, "pid": os.getpid(), "mood": m.mood, "state": m.state,
                    "visible": visible, "x": round(m.pos[0]), "y": round(m.pos[1]),
                    "size": int(self.config["size"]), "opacity": self.config["opacity"],
                    "glow": bool(self.config["glow"]), "sleeping": m.sleeping,
                    "perched": bool(m.perch), "gaze": m.gaze,
                    "hidden_for_fullscreen": self.auto_hidden,
                    "desktop_awareness": self.x11 is not None}
        if cmd == "say":
            if req.get("mood"):
                if req["mood"] not in MOODS:
                    return {"ok": False, "error": f"unknown mood {req['mood']!r}"}
                m.set_mood(req["mood"], announce=False, revert_after=revert)
            duration = req.get("duration")
            text = m.say(str(req.get("text") or "") or None,
                         int(float(duration) * 1000) if duration else None)
            return {"ok": True, "text": text, "visible": visible}
        if cmd == "mood":
            mood = str(req.get("mood", "neutral")).lower()
            if mood not in MOODS:
                return {"ok": False, "error": f"unknown mood {mood!r}; choose from {', '.join(MOODS)}"}
            strain = req.get("strain")
            m.set_mood(mood, announce=bool(req.get("announce")),
                       strain=int(strain) if strain is not None else 0,
                       escalate=None if strain is not None else (2.8, 6.8),
                       revert_after=revert)
            if req.get("text"):
                m.say(str(req["text"]))
            return {"ok": True, "mood": mood}
        if cmd == "react":
            event = normalize_event(req.get("event"))
            if event not in EVENTS:
                return {"ok": False, "error": f"unknown event {req.get('event')!r}; "
                                              f"choose from {', '.join(EVENTS)}"}
            m.react(event, str(req.get("text") or "") or None, quiet=bool(req.get("quiet")))
            return {"ok": True, "event": event, "mood": m.mood, "visible": visible}
        if cmd == "feed":
            return {"ok": True, "text": m.feed()}
        if cmd == "show":
            if not visible:
                self.show_mascot()
            return {"ok": True}
        if cmd == "hide":
            self.hide_mascot(None)
            return {"ok": True}
        if cmd == "toggle":
            self.toggle_mascot()
            return {"ok": True, "visible": m.is_shown()}
        if cmd == "sleep":
            if m.mood != "neutral":
                m.set_mood("neutral", announce=False)
            m.sleep()
            self._no_sleep_until = 0
            return {"ok": True, "sleeping": m.sleeping}
        if cmd == "wake":
            m.wake()
            self._no_sleep_until = time.monotonic() + float(self.config["sleep_after"])
            return {"ok": True}
        if cmd == "move":
            try:
                m.move_to(float(req["x"]), float(req["y"]))
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "error": "move needs numeric x and y"}
            return {"ok": True, "x": round(m.pos[0]), "y": round(m.pos[1]), "perched": bool(m.perch)}
        if cmd == "home":
            m.reset_position()
            return {"ok": True}
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    # -- menu ------------------------------------------------------------------------------
    def build_menu(self):
        m = self.mascot
        menu = Gtk.Menu()

        def item(label, callback, sub=None):
            mi = Gtk.MenuItem.new_with_label(label)
            mi.connect("activate", lambda *_: callback())
            menu.append(mi)
            return mi

        def submenu(label):
            mi = Gtk.MenuItem.new_with_label(label)
            sub = Gtk.Menu()
            mi.set_submenu(sub)
            sub.append(mi) if sub is not None else menu.append(mi)
            return sub

        def radio(sub, group, label, active, callback):
            ri = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            ri.set_active(active)
            ri.connect("toggled", lambda w: w.get_active() and callback())
            sub.append(ri)
            return ri

        if m.is_shown():
            item("Say something", m.say)
            item("Feed 🍚", m.feed)
        else:
            item("Show Whale-chan", self.show_mascot)
        menu.append(Gtk.SeparatorMenuItem())

        moods = submenu("Mood")
        group = None
        for mood in MOODS:
            group = radio(moods, group, MOOD_LABELS[mood], mood == m.mood,
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

        behaviour = submenu("Behaviour")
        for key, label in [("follow", "Follow the cursor with my eyes"),
                           ("perch", "Stand on windows"),
                           ("comments", "Comment on apps"),
                           ("sleep", "Nap when you're away"),
                           ("fullscreen_hide", "Hide for fullscreen apps")]:
            check = Gtk.CheckMenuItem.new_with_label(label)
            check.set_active(bool(self.config[key]))
            check.connect("toggled", lambda w, key=key: self.set_behaviour(key, w.get_active()))
            behaviour.append(check)

        menu.append(Gtk.SeparatorMenuItem())
        item("Back to the corner", m.reset_position)
        if m.is_shown():
            item("Hide for 10 minutes", lambda: self.hide_mascot(600))
            item("Hide", lambda: self.hide_mascot(None))
        menu.append(Gtk.SeparatorMenuItem())
        item("Restart", self.restart_app)
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

        scripts = submenu("Scripts")
        for script in os.listdir(SCRIPTS_PATH):
            path = os.path.join(SCRIPTS_PATH, script)
            if not os.access(path, os.X_OK):
                continue

            script_name = os.path.splitext(script)[0].capitalize()
            if (proc := RUNNING_PROCS.get(path)) and proc.poll() is None:
                script_name += " (running)"

            item(script_name, lambda script=script: self.run_script(script), sub=scripts)

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

    def set_behaviour(self, key, on):
        self.config[key] = bool(on)
        self.config.save()
        m = self.mascot
        if key == "perch" and not on:
            m.perch = None
        elif key == "sleep" and not on:
            m.wake(announce=False)
        elif key == "fullscreen_hide" and self.x11:
            self._on_active(self.x11.active(), comment=False)

    def set_glow(self, on):
        self.config["glow"] = bool(on)
        self.config.save()
        self.mascot.queue_draw()

    def hide_mascot(self, seconds):
        self.user_hidden = True
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
        self.user_hidden = False
        self.auto_hidden = False
        self.mascot.show_all_again()

    def toggle_mascot(self):
        if self.mascot.is_shown():
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
