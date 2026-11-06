// Pure timeline helpers: easing curves, transform strings, stop lists, time mapping and the desktop
// bake's loop-period choice. No DOM, no store.

import { fk, ik } from "../../tools/moods.mjs";
import { num } from "../model.js";

// ---------------------------------------------------------------- easing
export const EASE_PRESETS = {
  linear: [0, 0, 1, 1],
  ease: [0.25, 0.1, 0.25, 1],
  "ease-in": [0.42, 0, 1, 1],
  "ease-out": [0, 0, 0.58, 1],
  "ease-in-out": [0.42, 0, 0.58, 1],
};

/** {bezier: [x1, y1, x2, y2]} | {steps: n, start: bool} | null for an easing string. */
export function parseEasing(str) {
  const s = String(str ?? "ease").trim();
  if (s in EASE_PRESETS) return { bezier: EASE_PRESETS[s] };
  let m = /^cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)$/.exec(s);
  if (m) return { bezier: m.slice(1).map(Number) };
  m = /^steps\(\s*(\d+)\s*(?:,\s*([a-z-]+))?\s*\)$/.exec(s);
  if (m) return { steps: Math.max(1, Number(m[1])), start: m[2] === "start" || m[2] === "jump-start" };
  if (s === "step-start") return { steps: 1, start: true };
  if (s === "step-end") return { steps: 1, start: false };
  return null;
}

function bezierFn([x1, y1, x2, y2]) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t) => ((ax * t + bx) * t + cx) * t;
  const sy = (t) => ((ay * t + by) * t + cy) * t;
  const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0 || x >= 1) return x <= 0 ? 0 : 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const e = sx(t) - x;
      const d = dx(t);
      if (Math.abs(e) < 1e-6) return sy(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    let lo = 0, hi = 1;
    t = x;
    for (let i = 0; i < 40; i++) {
      const v = sx(t);
      if (Math.abs(v - x) < 1e-6) break;
      if (v < x) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sy(t);
  };
}

export function easingFn(str) {
  const e = parseEasing(str) || { bezier: EASE_PRESETS.ease };
  if (e.steps) return (p) => Math.min(1, (e.start ? Math.ceil(p * e.steps) : Math.floor(p * e.steps)) / e.steps);
  return bezierFn(e.bezier);
}

// ---------------------------------------------------------------- transforms
const IDENTITY = { tx: 0, ty: 0, rot: 0, sx: 1, sy: 1 };
const GROUP = { translate: 0, translateX: 0, translateY: 0, rotate: 1, scale: 2, scaleX: 2, scaleY: 2 };

function length(v) {
  const m = /^(-?(?:\d+\.?\d*|\.\d+))(px)?$/.exec(v.trim());
  return m && (m[2] || Number(m[1]) === 0) ? Number(m[1]) : null;
}

function angle(v) {
  const m = /^(-?(?:\d+\.?\d*|\.\d+))(deg|turn)?$/.exec(v.trim());
  if (!m || (!m[2] && Number(m[1]) !== 0)) return null;
  return m[2] === "turn" ? Number(m[1]) * 360 : Number(m[1]);
}

/**
 * Parses "translate(..) rotate(..) scale(..)" (each optional, in that order) into
 * {tx, ty, rot, sx, sy, has: {t, r, s}}; null when the string needs the raw editor.
 */
export function parseTransform(str) {
  const s = String(str ?? "").trim();
  const out = { ...IDENTITY, has: { t: false, r: false, s: false } };
  if (s === "none" || s === "") return out;
  const re = /([a-zA-Z]+)\(([^)]*)\)\s*/g;
  let pos = 0;
  let last = -1;
  const seen = new Set();
  for (let m; (m = re.exec(s)); ) {
    if (m.index !== pos) return null;
    pos = re.lastIndex;
    const [, fn, argStr] = m;
    if (!(fn in GROUP) || seen.has(fn) || GROUP[fn] < last) return null;
    seen.add(fn);
    last = GROUP[fn];
    const args = argStr.split(",").map((a) => a.trim());
    const nums = fn.startsWith("scale") ? args.map(Number) : fn === "rotate" ? args.map(angle) : args.map(length);
    if (nums.some((n) => n === null || !Number.isFinite(n))) return null;
    if (fn === "translate" && (seen.has("translateX") || seen.has("translateY") || nums.length > 2)) return null;
    if ((fn === "rotate" && nums.length !== 1) || (fn === "scale" && nums.length > 2)) return null;
    if (fn === "translate") [out.tx, out.ty = 0] = nums;
    else if (fn === "translateX") out.tx = nums[0];
    else if (fn === "translateY") out.ty = nums[0];
    else if (fn === "rotate") out.rot = nums[0];
    else if (fn === "scale") [out.sx, out.sy = nums[0]] = nums;
    else if (fn === "scaleX") out.sx = nums[0];
    else out.sy = nums[0];
    out.has["trs"[GROUP[fn]]] = true;
  }
  return pos === s.length ? out : null;
}

const px = (v) => (v === 0 ? "0" : `${num(v)}px`);

/** Canonical "translate(..) rotate(..) scale(..)", keeping the groups in `has` or not at identity. */
export function formatTransform(v, has = {}) {
  const parts = [];
  if (has.t || v.tx || v.ty) {
    if (v.tx && v.ty) parts.push(`translate(${px(v.tx)}, ${px(v.ty)})`);
    else if (v.tx) parts.push(`translateX(${px(v.tx)})`);
    else parts.push(`translateY(${px(v.ty)})`);
  }
  if (has.r || v.rot) parts.push(`rotate(${v.rot ? `${num(v.rot)}deg` : "0"})`);
  if (has.s || v.sx !== 1 || v.sy !== 1) parts.push(v.sx === v.sy ? `scale(${num(v.sx)})` : `scale(${num(v.sx)}, ${num(v.sy)})`);
  return parts.join(" ") || "rotate(0)";
}

/** Mirror a transform left/right: rotation and horizontal translation flip sign. */
export function mirrorTransform(str) {
  const p = parseTransform(str);
  if (p) return formatTransform({ ...p, rot: -p.rot, tx: -p.tx }, p.has);
  const neg = (n) => (n.startsWith("-") ? n.slice(1) : n === "0" ? n : `-${n}`);
  return String(str)
    .replace(/rotate\(\s*(-?[\d.]+)/g, (_, n) => `rotate(${neg(n)}`)
    .replace(/translateX\(\s*(-?[\d.]+)/g, (_, n) => `translateX(${neg(n)}`)
    .replace(/translate\(\s*(-?[\d.]+)/g, (_, n) => `translate(${neg(n)}`);
}

// ---------------------------------------------------------------- stops
export const ts = (stop) => [].concat(stop.t);
export const round1 = (v) => Math.round(v * 10) / 10;

/** Every keyframe position as a diamond: {i: stop index, j: index into its t list, t}. */
export function diamonds(stops) {
  const out = [];
  (stops || []).forEach((s, i) => ts(s).forEach((t, j) => out.push({ i, j, t })));
  return out;
}

const sorted = (stops) => diamonds(stops).sort((a, b) => a.t - b.t);

/** Surrounding diamonds of percent t (CSS uses the underlying value where 0%/100% is missing). */
function bracket(stops, t) {
  const pts = sorted(stops);
  let a = null;
  let b = null;
  for (const p of pts) {
    if (p.t <= t) a = p;
    if (p.t >= t && !b) b = p;
  }
  return { a, b };
}

// Missing 0%/100% stops fall back to the underlying value, as in CSS.
function segment(stops, t, easing) {
  const { a, b } = bracket(stops, t);
  const ta = a ? a.t : 0;
  const tb = b ? b.t : 100;
  const k = tb > ta ? easingFn((a && stops[a.i].easing) || easing)((t - ta) / (tb - ta)) : 0;
  return { a, b, k };
}

/** Structured transform at percent t, or {raw} when the stops can't be parsed. */
export function evalTransform(stops, t, easing) {
  const { a, b, k } = segment(stops, t, easing);
  const val = (p) => (p ? parseTransform(stops[p.i].transform) : { ...IDENTITY, has: {} });
  const va = val(a);
  const vb = val(b);
  if (!va || !vb) return { raw: stops[(a || b).i].transform };
  const lerp = (x, y) => Number((x + (y - x) * k).toFixed(3));
  return {
    tx: lerp(va.tx, vb.tx), ty: lerp(va.ty, vb.ty), rot: lerp(va.rot, vb.rot), sx: lerp(va.sx, vb.sx), sy: lerp(va.sy, vb.sy),
    has: { t: va.has.t || vb.has.t, r: va.has.r || vb.has.r, s: va.has.s || vb.has.s },
  };
}

export function stopAngles(rig, side, stop) {
  return stop.angles ? [...stop.angles] : ik(rig, side, stop.hand, stop.elbowOut !== false);
}

/** Arm angles of a hand track at percent t; `pose` fills in missing 0%/100% like CSS does. */
export function evalHand(rig, side, stops, t, easing, pose) {
  const { a, b, k } = segment(stops, t, easing);
  const aa = a ? stopAngles(rig, side, stops[a.i]) : pose;
  const ab = b ? stopAngles(rig, side, stops[b.i]) : pose;
  return [aa[0] + (ab[0] - aa[0]) * k, aa[1] + (ab[1] - aa[1]) * k];
}

export function handPath(rig, side, stops, easing, pose, n = 64) {
  const out = [];
  for (let i = 0; i <= n; i++) out.push(fk(rig, side, evalHand(rig, side, stops, (i / n) * 100, easing, pose)).hand.map((v) => Number(v.toFixed(1))));
  return out;
}

// ---------------------------------------------------------------- time
export function parseTime(v) {
  const m = /^(-?(?:\d+\.?\d*|\.\d+))(m?s)$/.exec(String(v ?? "").trim());
  if (!m) return 0;
  return m[2] === "ms" ? Number(m[1]) : Number(m[1]) * 1000;
}

export const fmtTime = (ms) => `${num(ms / 1000)}s`;

export function timing(m) {
  const n = m.iterations == null || m.iterations === "infinite" ? Infinity : Number(m.iterations) || 1;
  return { d: Math.max(1, parseTime(m.duration)), delay: parseTime(m.delay), dir: m.direction || "normal", n };
}

const forward = (dir, k) => !(dir === "reverse" || (dir === "alternate" && k % 2) || (dir === "alternate-reverse" && !(k % 2)));

/** Where a track is at animation time T: {t (percent), k (iteration), active}. */
export function localAt(T, tm) {
  const a = T - tm.delay;
  if (a < 0) return { t: 0, k: 0, active: false };
  let k = Math.floor(a / tm.d);
  let p = (a - k * tm.d) / tm.d;
  if (k >= tm.n) {
    k = tm.n - 1;
    p = 1;
  }
  return { t: (forward(tm.dir, k) ? p : 1 - p) * 100, k, active: true };
}

/** Animation time of percent t in iteration k. */
export function timeOf(t, k, tm) {
  const p = forward(tm.dir, k) ? t / 100 : 1 - t / 100;
  return tm.delay + (k + p) * tm.d;
}

/** Iterations that intersect [0, L]. */
export function cycles(tm, L) {
  const first = Math.max(0, Math.floor(-tm.delay / tm.d));
  const out = [];
  for (let k = first; tm.delay + k * tm.d < L && k < tm.n && out.length < 400; k++) out.push(k);
  return out;
}

/** Same phase as `delay`, normalised into (-d, 0] like the hand-kept moods. */
export function normDelay(delay, d) {
  let v = ((delay % d) + d) % d;
  if (v > 0) v -= d;
  return Math.abs(v) < 0.5 ? 0 : v;
}

// ---------------------------------------------------------------- bake period (desktop/bake.py)
// Python's round(): halves go to the even neighbour.
function pyRound(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 ? r - 1 : r;
}

/** Port of choose_period(): the loop period P (ms) every duration is retimed to divide. */
export function choosePeriod(durations, lo = 4800, hi = 8000, step = 100) {
  if (!durations.length) return lo;
  let best = null;
  for (let p = lo; p <= hi; p += step) {
    const errs = durations.map((d) => Math.abs(p / Math.max(1, pyRound(p / d)) - d) / d);
    const score = Math.max(...errs) + errs.reduce((x, y) => x + y, 0) / errs.length;
    if (best === null || score < best[0] - 1e-9) best = [score, p];
  }
  return best[1];
}

export const BAKE_FPS = 20;

/** Period after frame rounding (frames = round(P / 1000 * fps)), as the bake does it. */
export function bakePeriod(durations, fps = BAKE_FPS) {
  const frames = Math.max(1, pyRound((choosePeriod(durations) / 1000) * fps));
  return { frames, period: (frames * 1000) / fps };
}

export const retimed = (d, period) => period / Math.max(1, Math.round(period / d));

// ---------------------------------------------------------------- sides
export const counterpart = (part) => part.replace(/-(l|r)(?=$|\.)/, (_, s) => (s === "l" ? "-r" : "-l"));
export const hasSide = (part) => counterpart(part) !== part;
