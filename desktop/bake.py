#!/usr/bin/env python3
"""Bake the animated Whale-chan SVG into looping transparent PNG frames.

WebKitGTK re-renders the CSS-rigged SVG on the CPU every frame, which costs a
full core. Instead, this tool drives the SVG offscreen once: it sets each mood,
retimes every idle loop so they all share one period (seamless loops), steps the
animation clock frame by frame and snapshots the result. The desktop app then
only plays images back.

Usage: python3 desktop/bake.py [--svg PATH] [--width 260] [--fps 20] [--out DIR]
Progress is printed to stdout as "progress <done> <total>" lines.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.0")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402
import cairo  # noqa: E402

BAKE_VERSION = 2
MASK_EVERY = 4      # sample every Nth frame for the click mask
MASK_GROW = 3       # px of slack around the silhouette
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SVG = ROOT / "assets" / "whale-chan.svg"
STATES = [
    ("neutral", "neutral", 0),
    ("angry", "angry", 0),
    ("smug", "smug", 0),
    ("happy", "happy", 0),
    ("sad", "sad", 0),
    ("thinking", "thinking", 0),
    ("thinking-1", "thinking", 1),
    ("thinking-2", "thinking", 2),
]
VIEWBOX = (900, 1060)
# Room around the art box for effects that overflow the viewBox (thought
# bubbles, hearts, steam). Everything is auto-cropped afterwards.
PAD_X, PAD_TOP, PAD_BOTTOM = 0.32, 0.36, 0.06

PAGE_JS = r"""
(() => {
  const svg = document.querySelector('#stage svg');
  const anims = () => document.getAnimations();
  const settle = () => {
    getComputedStyle(svg).opacity;
    for (const a of anims()) {
      if (a instanceof CSSTransition) a.finish();
    }
  };
  window.bake = {
    setState(mood, strain) {
      svg.setAttribute('data-mood', mood);
      svg.setAttribute('data-strain', String(strain));
      settle();
      settle();
      return anims().length;
    },
    durations() {
      const out = [];
      for (const a of anims()) {
        if (!(a instanceof CSSAnimation)) continue;
        const t = a.effect.getTiming();
        if (t.iterations === Infinity && t.duration > 0) out.push(t.duration);
      }
      return out;
    },
    retime(period) {
      for (const a of anims()) {
        if (!(a instanceof CSSAnimation)) continue;
        const t = a.effect.getTiming();
        if (t.iterations === Infinity && t.duration > 0) {
          const n = Math.max(1, Math.round(period / t.duration));
          a.effect.updateTiming({ duration: period / n });
        }
        a.pause();
      }
    },
    fx(on) {
      document.documentElement.classList.toggle('no-fx', !on);
      getComputedStyle(svg).opacity;
    },
    seek(ms) {
      for (const a of anims()) {
        if (a instanceof CSSAnimation) {
          a.pause();
          a.currentTime = ms;
        }
      }
      getComputedStyle(svg).opacity;
    }
  };
})();
"""


def cache_key(svg_bytes, width, fps):
    h = hashlib.sha1()
    h.update(svg_bytes)
    h.update(f"v{BAKE_VERSION}:w{width}:f{fps}".encode())
    h.update(Path(__file__).read_bytes())
    return h.hexdigest()[:16]


def default_cache_dir():
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "whalechan" / "frames"


def choose_period(durations_ms, lo=4800, hi=8000, step=100):
    """Pick a loop period P so every duration d is close to P / n.

    Every infinite animation is then retimed to exactly P / n, so the whole
    state loops seamlessly after P milliseconds.
    """
    if not durations_ms:
        return lo
    best = None
    for p in range(lo, hi + 1, step):
        errs = [abs(p / max(1, round(p / d)) - d) / d for d in durations_ms]
        score = max(errs) + sum(errs) / len(errs)
        if best is None or score < best[0] - 1e-9:
            best = (score, p)
    return best[1]


class Baker:
    def __init__(self, svg_path, width, fps, out_dir):
        self.svg_path = Path(svg_path)
        self.width = width
        self.fps = fps
        self.out_dir = Path(out_dir)
        self.art_w = width
        self.art_h = round(width * VIEWBOX[1] / VIEWBOX[0])
        self.pad_x = round(self.art_w * PAD_X)
        self.pad_top = round(self.art_h * PAD_TOP)
        self.pad_bottom = round(self.art_h * PAD_BOTTOM)
        self.view_w = self.art_w + 2 * self.pad_x
        self.view_h = self.art_h + self.pad_top + self.pad_bottom
        self.tmp_dir = self.out_dir.with_name(self.out_dir.name + ".tmp")
        self.union = None
        self.masks = {}
        self.error = None
        self.loop = GLib.MainLoop()

    # -- WebKit plumbing -------------------------------------------------
    def _js(self, code, then):
        modern = hasattr(self.view, "evaluate_javascript")

        def done(view, result):
            try:
                if modern:
                    value = view.evaluate_javascript_finish(result)
                else:
                    value = view.run_javascript_finish(result).get_js_value()
                then(value)
            except Exception as exc:  # noqa: BLE001
                self._fail(f"javascript failed: {exc}")

        if modern:
            self.view.evaluate_javascript(code, -1, None, None, None, done)
        else:
            self.view.run_javascript(code, None, done)

    def _snapshot(self, then):
        def done(view, result):
            try:
                then(view.get_snapshot_finish(result))
            except Exception as exc:  # noqa: BLE001
                self._fail(f"snapshot failed: {exc}")
        self.view.get_snapshot(
            WebKit2.SnapshotRegion.VISIBLE,
            WebKit2.SnapshotOptions.TRANSPARENT_BACKGROUND,
            None,
            done,
        )

    def _fail(self, message):
        self.error = message
        self.loop.quit()

    # -- pipeline ----------------------------------------------------------
    def run(self):
        svg = self.svg_path.read_text(encoding="utf-8")
        if svg.lstrip().startswith("<?xml"):
            svg = svg.split("?>", 1)[1]
        page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; background: transparent; overflow: hidden; }}
#stage {{ position: absolute; left: {self.pad_x}px; top: {self.pad_top}px;
  width: {self.art_w}px; height: {self.art_h}px; }}
#stage svg {{ display: block; width: 100%; height: 100%; overflow: visible; }}
.no-fx .fx, .no-fx .bowl-steam {{ visibility: hidden !important; }}
</style></head><body><div id="stage">{svg}</div></body></html>"""

        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)
        self.tmp_dir.mkdir(parents=True)

        self.window = Gtk.OffscreenWindow()
        self.window.set_default_size(self.view_w, self.view_h)
        self.view = WebKit2.WebView()
        self.view.set_size_request(self.view_w, self.view_h)
        self.view.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        settings = self.view.get_settings()
        settings.set_enable_javascript(True)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.window.add(self.view)
        self.window.show_all()
        self.view.connect("load-changed", self._on_load)
        self.view.load_html(page, self.svg_path.parent.as_uri() + "/")
        self.loop.run()
        self.window.destroy()
        if self.error:
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            raise RuntimeError(self.error)

    def _on_load(self, view, event):
        if event != WebKit2.LoadEvent.FINISHED:
            return
        self._js(PAGE_JS + ";1", lambda _v: self._collect_durations(0, {}))

    def _collect_durations(self, index, plan):
        if index == len(STATES):
            self.plan = plan
            self.total = sum(item["frames"] for item in plan.values())
            self.done = 0
            self._start_state(0)
            return
        name, mood, strain = STATES[index]

        def got(value):
            durations = sorted({round(float(x), 3) for x in json.loads(value.to_string())})
            frames = max(1, round(choose_period(durations) / 1000 * self.fps))
            plan[name] = {"frames": frames, "period_ms": frames * 1000 / self.fps}
            self._collect_durations(index + 1, plan)

        self._js(
            f"bake.setState('{mood}', {strain}); JSON.stringify(bake.durations())",
            got,
        )

    def _start_state(self, index):
        if index == len(STATES):
            GLib.idle_add(self._finish)
            return
        name, mood, strain = STATES[index]
        (self.tmp_dir / name).mkdir()
        self._js(
            f"bake.setState('{mood}', {strain}); "
            f"bake.retime({self.plan[name]['period_ms']}); 1",
            lambda _v: self._frame(index, 0),
        )

    def _frame(self, state_index, frame):
        if frame == self.plan[STATES[state_index][0]]["frames"]:
            self._start_state(state_index + 1)
            return
        name = STATES[state_index][0]
        ms = frame * 1000 / self.fps

        def shot(surface):
            region = Gdk.cairo_region_create_from_surface(surface)
            ext = region.get_extents()
            if ext.width and ext.height:
                box = (ext.x, ext.y, ext.x + ext.width, ext.y + ext.height)
                if self.union is None:
                    self.union = box
                else:
                    u = self.union
                    self.union = (min(u[0], box[0]), min(u[1], box[1]),
                                  max(u[2], box[2]), max(u[3], box[3]))
            surface.write_to_png(str(self.tmp_dir / name / f"{frame:04d}.png"))
            self.done += 1
            print(f"progress {self.done} {self.total}", flush=True)
            if frame % MASK_EVERY == 0:
                self._js("bake.fx(false); 1", lambda _v: self._snapshot(mask_shot))
            else:
                self._frame(state_index, frame + 1)

        def mask_shot(surface):
            region = Gdk.cairo_region_create_from_surface(surface)
            if name in self.masks:
                self.masks[name].union(region)
            else:
                self.masks[name] = region
            self._js("bake.fx(true); 1", lambda _v: self._frame(state_index, frame + 1))

        self._js(f"bake.seek({ms}); 1", lambda _v: self._snapshot(shot))

    def _finish(self):
        margin = 4
        x0, y0, x1, y1 = self.union or (0, 0, self.view_w, self.view_h)
        x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
        x1, y1 = min(self.view_w, x1 + margin), min(self.view_h, y1 + margin)
        cw, ch = x1 - x0, y1 - y0
        for name, _mood, _strain in STATES:
            src_dir = self.tmp_dir / name
            for png in sorted(src_dir.glob("*.png")):
                src = cairo.ImageSurface.create_from_png(str(png))
                dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
                cr = cairo.Context(dst)
                cr.set_source_surface(src, -x0, -y0)
                cr.set_operator(cairo.OPERATOR_SOURCE)
                cr.paint()
                dst.write_to_png(str(png))
        for name, region in self.masks.items():
            _write_mask_png(region, self.tmp_dir / name / "mask.png", x0, y0, cw, ch)
        manifest = {
            "version": BAKE_VERSION,
            "svg": str(self.svg_path),
            "fps": self.fps,
            "width": cw,
            "height": ch,
            # Art box (the SVG viewBox) inside each cropped frame, in pixels.
            "art": {
                "x": self.pad_x - x0,
                "y": self.pad_top - y0,
                "w": self.art_w,
                "h": self.art_h,
            },
            "states": self.plan,
        }
        (self.tmp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        if self.out_dir.exists():
            shutil.rmtree(self.out_dir)
        self.tmp_dir.rename(self.out_dir)
        self.loop.quit()
        return False


def _mask_surface(region, x0, y0, cw, ch):
    surface = cairo.ImageSurface(cairo.FORMAT_A8, cw, ch)
    cr = cairo.Context(surface)
    for i in range(region.num_rectangles()):
        r = region.get_rectangle(i)
        cr.rectangle(r.x - x0, r.y - y0, r.width, r.height)
    cr.fill()
    return surface


def _write_mask_png(region, path, x0, y0, cw, ch):
    """Click mask: union of the body silhouette over the loop, grown a little."""
    hard = _mask_surface(region, x0, y0, cw, ch)
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
    cr = cairo.Context(out)
    cr.set_source_rgb(0, 0, 0)
    g = MASK_GROW
    for dx, dy in [(0, 0), (-g, 0), (g, 0), (0, -g), (0, g)]:
        cr.mask_surface(hard, dx, dy)
    out.write_to_png(str(path))


def bake(svg_path, width, fps, cache_dir=None):
    svg_path = Path(svg_path)
    key = cache_key(svg_path.read_bytes(), width, fps)
    out = Path(cache_dir or default_cache_dir()) / key
    if (out / "manifest.json").exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    Baker(svg_path, width, fps, out).run()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--svg", default=str(DEFAULT_SVG))
    parser.add_argument("--width", type=int, default=260, help="art width in pixels")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--cache", default=None, help="cache root directory")
    args = parser.parse_args()
    try:
        out = bake(args.svg, args.width, args.fps, args.cache)
    except Exception as exc:  # noqa: BLE001
        print(f"error {exc}", file=sys.stderr, flush=True)
        return 1
    print(f"done {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
