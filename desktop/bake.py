#!/usr/bin/env python3
"""Bake the animated Whale-chan SVG into looping transparent PNG frames.

WebKitGTK re-renders the CSS-rigged SVG on the CPU every frame, which costs a
full core. Instead, this tool drives the SVG offscreen once: it sets each mood,
retimes every idle loop so they all share one period (seamless loops), steps the
animation clock frame by frame and snapshots the result. The desktop app then
only plays images back.

Besides the moods it bakes variants of `neutral` with CSS-variable overrides:
gaze directions, with the same loop period as neutral, so the app can switch
between them frame-for-frame.

Usage: python3 desktop/bake.py [--svg PATH] [--width 260] [--fps 20] [--cache DIR]
       python3 desktop/bake.py --preview sheet.png [--states a,b] [--time MS]
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

BAKE_VERSION = 3
MASK_EVERY = 4      # sample every Nth frame for the click mask
MASK_GROW = 3       # px of slack around the silhouette
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SVG = ROOT / "assets" / "whale-chan.svg"


def state(name, mood, strain=0, vars=None, cls="", sync=None):
    """A baked state: a mood plus optional CSS-variable overrides and an extra class.

    `sync` names another state whose loop period this one must share, so the app
    can swap between them at the same frame index (only the overrides differ).
    """
    return {"name": name, "mood": mood, "strain": strain, "vars": vars or {}, "cls": cls, "sync": sync}


# Irises (--ix/--iy) and head (--hr/--hx/--hy) turned toward screen directions.
GAZE = {
    "look-l": {"--ix": "-10px", "--iy": "2px", "--hr": "-4deg", "--hx": "-3px"},
    "look-r": {"--ix": "10px", "--iy": "2px", "--hr": "4deg", "--hx": "3px"},
    "look-ul": {"--ix": "-8px", "--iy": "-11px", "--hr": "-3deg", "--hx": "-2px", "--hy": "-4px"},
    "look-ur": {"--ix": "8px", "--iy": "-11px", "--hr": "3deg", "--hx": "2px", "--hy": "-4px"},
}
STATES = [
    state("neutral", "neutral"),
    state("angry", "angry"),
    state("smug", "smug"),
    state("happy", "happy"),
    state("sad", "sad"),
    state("thinking", "thinking"),
    state("thinking-1", "thinking", 1),
    state("thinking-2", "thinking", 2),
    *[state(f"neutral-{name}", "neutral", vars=v, sync="neutral") for name, v in GAZE.items()],
    state("sleepy", "sleepy"),
]
# Extra rules for states that need more than variables (none at the moment).
STATE_CSS = ""
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
    setState(mood, strain, vars, cls) {
      svg.setAttribute('data-mood', mood);
      svg.setAttribute('data-strain', String(strain));
      svg.removeAttribute('style');
      for (const [k, v] of Object.entries(vars || {})) svg.style.setProperty(k, v);
      for (const c of [...svg.classList]) if (c.startsWith('st-')) svg.classList.remove(c);
      if (cls) svg.classList.add(cls);
      settle();
      settle();
      return anims().length;
    },
    durations() {
      // Only animations that can be seen in this state decide the loop period;
      // effect layers of other moods keep animating at opacity 0.
      const hidden = (el) => {
        for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
          const cs = getComputedStyle(p);
          if (cs.opacity === '0' || cs.display === 'none' || cs.visibility === 'hidden') return true;
        }
        return false;
      };
      const out = [];
      for (const a of anims()) {
        if (!(a instanceof CSSAnimation)) continue;
        if (a.effect.target && hidden(a.effect.target)) continue;
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
    def __init__(self, svg_path, width, fps, out_dir, states=None, preview=None, preview_ms=0):
        self.svg_path = Path(svg_path)
        self.states = states or STATES
        self.preview = preview
        self.preview_ms = preview_ms
        self.previews = []
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

    @staticmethod
    def _set_state_js(st):
        return (f"bake.setState({json.dumps(st['mood'])}, {st['strain']}, "
                f"{json.dumps(st['vars'])}, {json.dumps(st['cls'])})")

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
{STATE_CSS}
</style></head><body><div id="stage">{svg}</div></body></html>"""

        if not self.preview:
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
            if not self.preview:
                shutil.rmtree(self.tmp_dir, ignore_errors=True)
            raise RuntimeError(self.error)

    def _on_load(self, view, event):
        if event != WebKit2.LoadEvent.FINISHED:
            return
        self._js(PAGE_JS + ";1", lambda _v: self._collect_durations(0, {}))

    def _collect_durations(self, index, plan):
        if index == len(self.states):
            for st in self.states:
                if st["sync"] in plan:
                    plan[st["name"]] = dict(plan[st["sync"]])
            self.plan = plan
            self.total = sum(item["frames"] for item in plan.values())
            self.done = 0
            self._start_state(0)
            return
        st = self.states[index]

        def got(value):
            durations = sorted({round(float(x), 3) for x in json.loads(value.to_string())})
            frames = max(1, round(choose_period(durations) / 1000 * self.fps))
            plan[st["name"]] = {"frames": frames, "period_ms": frames * 1000 / self.fps}
            self._collect_durations(index + 1, plan)

        self._js(f"{self._set_state_js(st)}; JSON.stringify(bake.durations())", got)

    def _start_state(self, index):
        if index == len(self.states):
            GLib.idle_add(self._finish_preview if self.preview else self._finish)
            return
        st = self.states[index]
        if self.preview:
            self._js(f"{self._set_state_js(st)}; bake.retime({self.plan[st['name']]['period_ms']}); "
                     f"bake.seek({self.preview_ms}); 1",
                     lambda _v: self._snapshot(lambda surface: self._preview_shot(index, surface)))
            return
        (self.tmp_dir / st["name"]).mkdir()
        self._js(f"{self._set_state_js(st)}; bake.retime({self.plan[st['name']]['period_ms']}); 1",
                 lambda _v: self._frame(index, 0))

    def _preview_shot(self, index, surface):
        self.previews.append((self.states[index]["name"], surface))
        self._start_state(index + 1)

    def _finish_preview(self):
        cols = min(4, len(self.previews))
        rows = (len(self.previews) + cols - 1) // cols
        label_h = 22
        sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, cols * self.view_w, rows * (self.view_h + label_h))
        cr = cairo.Context(sheet)
        cr.set_source_rgb(0.47, 0.66, 0.53)
        cr.paint()
        for i, (name, surface) in enumerate(self.previews):
            x, y = (i % cols) * self.view_w, (i // cols) * (self.view_h + label_h)
            cr.set_source_surface(surface, x, y + label_h)
            cr.paint()
            cr.set_source_rgb(0.08, 0.15, 0.3)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(14)
            cr.move_to(x + 8, y + 16)
            cr.show_text(name)
        sheet.write_to_png(str(self.preview))
        self.loop.quit()
        return False

    def _frame(self, state_index, frame):
        name = self.states[state_index]["name"]
        if frame == self.plan[name]["frames"]:
            self._start_state(state_index + 1)
            return
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
        for st in self.states:
            src_dir = self.tmp_dir / st["name"]
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
    _prune(out, svg_path, width, fps)
    return out


def _prune(keep, svg_path, width, fps):
    """Delete older bakes of the same SVG, size and fps (they can never be hit again)."""
    for sibling in keep.parent.iterdir():
        if sibling == keep or not sibling.is_dir():
            continue
        try:
            manifest = json.loads((sibling / "manifest.json").read_text())
        except (OSError, ValueError):
            if sibling.name.endswith(".tmp"):
                continue  # possibly another bake in progress
            manifest = None
        if manifest is None or (manifest.get("svg") == str(svg_path)
                                and manifest.get("art", {}).get("w") == width
                                and manifest.get("fps") == fps):
            shutil.rmtree(sibling, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--svg", default=str(DEFAULT_SVG))
    parser.add_argument("--width", type=int, default=260, help="art width in pixels")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--cache", default=None, help="cache root directory")
    parser.add_argument("--preview", metavar="PNG",
                        help="render one frame per state into a contact sheet instead of baking")
    parser.add_argument("--states", help="comma-separated state names for --preview")
    parser.add_argument("--time", type=float, default=0, help="--preview: animation time in ms")
    args = parser.parse_args()
    try:
        if args.preview:
            states = STATES
            if args.states:
                wanted = args.states.split(",")
                states = [st for st in STATES if st["name"] in wanted]
            Baker(args.svg, args.width, args.fps, Path("/nonexistent"), states=states,
                  preview=Path(args.preview), preview_ms=args.time).run()
            print(f"done {args.preview}", flush=True)
            return 0
        out = bake(args.svg, args.width, args.fps, args.cache)
    except Exception as exc:  # noqa: BLE001
        print(f"error {exc}", file=sys.stderr, flush=True)
        return 1
    print(f"done {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
