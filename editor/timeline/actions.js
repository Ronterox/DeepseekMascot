// Timeline operations on the selected mood/variant. Everything goes through store.edit (pass a stable
// `key` while dragging and call store.commit() at the end, so one gesture is one undo step).

import { fk, ik, resolvePose } from "../../tools/moods.mjs";
import { clone, motionOf, scopeOf, uniqueName } from "../model.js";
import {
  bakePeriod, counterpart, diamonds, evalHand, evalTransform, fmtTime, formatTransform, localAt, mirrorTransform,
  normDelay, parseTransform, retimed, round1, stopAngles, timeOf, timing, ts,
} from "./model.js";

export const HAND_TRACKS = ["arm-l", "arm-r"];
const SOURCE = "timeline";

/** Rig parts plus the two hand tracks, each hand track just before its arm's u/f parts. */
export function partOrder(rig) {
  const out = [];
  for (const p of Object.keys(rig.parts)) {
    if (p === "arm-l.u" || p === "arm-r.u") out.push(p.slice(0, 5));
    out.push(p);
  }
  return out;
}

const scopeName = (store) => (store.variant == null ? "mood" : `variant ${store.variant}`);

/**
 * What drives `part` in the selected scope: {part, own, from, m, kind: "kf" | "hand" | "none", local,
 * name, stops, tm, editable} or null when nothing animates it.
 */
export function trackInfo(store, part) {
  const entry = store.current;
  if (!entry) return null;
  const { mood } = entry;
  const scope = scopeOf(mood, store.variant);
  const own = scope.motion?.[part];
  const eff = own !== undefined ? { value: own, from: store.variant == null ? "mood" : "variant" } : motionOf(mood, store.variant, store.ctx, part);
  const m = eff.value;
  if (m == null) return null;
  const base = { part, own: own !== undefined, from: eff.from, m };
  if (m === "none") return { ...base, kind: "none", stops: [], editable: false };
  if (m.stops) return { ...base, kind: "hand", stops: m.stops, tm: timing(m), editable: base.own };
  const local = !!mood.keyframes && m.keyframes in mood.keyframes;
  const stops = local ? mood.keyframes[m.keyframes] : store.ctx.keyframes[m.keyframes] || [];
  return { ...base, kind: "kf", local, name: m.keyframes, stops, tm: timing(m), editable: base.own && local };
}

/** Rows for the timeline: own tracks first-class, inherited ones optional (read-only). */
export function rows(store, inherited) {
  const out = [];
  const infos = new Map(partOrder(store.ctx.rig).map((p) => [p, trackInfo(store, p)]));
  for (const [part, info] of infos) {
    if (!info) continue;
    const side = /^arm-([lr])\.[uf]$/.exec(part)?.[1];
    const track = side && infos.get(`arm-${side}`);
    if (!info.own && track && track.kind === "hand") continue; // a hand track drives this arm
    if (info.own || inherited) out.push(info);
  }
  return out;
}

/** Other parts (in the mood and its variants) using local keyframes `name`. */
export function keyframeUsers(mood, name) {
  const out = [];
  const scan = (motion, where) => {
    for (const [p, m] of Object.entries(motion || {})) if (m?.keyframes === name) out.push(where ? `${p} (${where})` : p);
  };
  scan(mood.motion);
  for (const [v, s] of Object.entries(mood.variants || {})) scan(s.motion, `strain ${v}`);
  return out;
}

export function loopMs(store) {
  const mood = store.current?.mood;
  const ed = mood?.meta?.editor;
  if (ed?.bpm > 0 && ed?.counts > 0) return (ed.counts * 60000) / ed.bpm;
  const own = rows(store, false).filter((r) => r.tm).map((r) => r.tm.d);
  if (own.length) return Math.max(...own);
  const all = rows(store, true).filter((r) => r.tm).map((r) => r.tm.d);
  return all.length ? Math.max(...all) : 4000;
}

export function beatMs(store) {
  const ed = store.current?.mood?.meta?.editor;
  return ed?.bpm > 0 ? 60000 / ed.bpm : null;
}

/** Snap step in ms for a track (null = off). */
export function gridStep(store, snap, tm) {
  const beat = beatMs(store);
  if (snap === "off") return null;
  if (snap.startsWith("pct")) return (tm.d * Number(snap.slice(3))) / 100;
  if (!beat) return tm.d / 100;
  return beat / Number(snap.slice(1));
}

/** Percent t in iteration k moved to the nearest grid line (in absolute time, so beats line up). */
export function snapT(t, k, tm, step) {
  if (!step) return round1(t);
  const time = Math.round(timeOf(t, k, tm) / step) * step;
  const p = (time - tm.delay) / tm.d - k;
  const tt = timeOf(100, k, tm) >= timeOf(0, k, tm) ? p * 100 : (1 - p) * 100;
  return round1(Math.max(0, Math.min(100, tt)));
}

function poseAngles(store, side) {
  return resolvePose(store.current.mood, store.ctx, store.variant)[side];
}

/** Hand-stop body for a solved arm: {hand} plus elbowOut:false when IK would pick the other elbow. */
function handStop(rig, side, angles) {
  const hand = fk(rig, side, angles).hand.map((v) => Number(v.toFixed(1)));
  const out = ik(rig, side, hand, true);
  const near = (a) => Math.abs(a[0] - angles[0]) + Math.abs(a[1] - angles[1]) < 2;
  return near(out) || !near(ik(rig, side, hand, false)) ? { hand } : { hand, elbowOut: false };
}

const stopsOf = (draft, scope, part) => {
  const m = scope.motion[part];
  return m.stops || draft.keyframes[m.keyframes];
};

// ---------------------------------------------------------------- make editable
export function overrideHere(store, part) {
  const info = trackInfo(store, part);
  if (!info || info.own) return;
  store.edit((_, scope) => {
    (scope.motion ??= {})[part] = clone(info.m);
  }, { source: SOURCE });
}

export function makeLocal(store, part) {
  const info = trackInfo(store, part);
  if (!info || info.kind !== "kf" || info.local || !info.own) return;
  store.edit((draft, scope) => {
    const taken = new Set([...Object.keys(draft.keyframes || {}), ...Object.keys(store.ctx.keyframes)]);
    const name = uniqueName(info.name, taken);
    (draft.keyframes ??= {})[name] = clone(store.ctx.keyframes[info.name]);
    scope.motion[part].keyframes = name;
  }, { source: SOURCE });
}

/** Asks before overriding an inherited track or copying library keyframes; true when editable. */
export function ensureEditable(store, part) {
  let info = trackInfo(store, part);
  if (!info || info.kind === "none") return false;
  if (!info.own) {
    if (!confirm(`"${part}" is inherited from ${info.from}. Override it in this ${scopeName(store)}?`)) return false;
    overrideHere(store, part);
    info = trackInfo(store, part);
  }
  if (info.kind === "kf" && !info.local) {
    if (!confirm(`"${part}" uses the shared library keyframes "${info.name}" (moods/_keyframes.json).\nMake a local copy in this mood to edit it?`)) return false;
    makeLocal(store, part);
  }
  return trackInfo(store, part)?.editable;
}

// ---------------------------------------------------------------- stops
/** Adds a stop at percent t holding the track's current (interpolated) value; returns its diamond. */
export function addStop(store, part, t) {
  const info = trackInfo(store, part);
  if (!info?.editable) return null;
  t = round1(t);
  const hit = diamonds(info.stops).find((d) => Math.abs(d.t - t) < 0.05);
  if (hit) return hit;
  let stop;
  if (info.kind === "hand") {
    const side = part.slice(-1);
    const angles = evalHand(store.ctx.rig, side, info.stops, t, info.m.easing, poseAngles(store, side));
    stop = { t, ...handStop(store.ctx.rig, side, angles) };
  } else {
    const v = evalTransform(info.stops, t, info.m.easing);
    stop = { t, transform: v.raw ?? formatTransform(v, v.has) };
  }
  let index = -1;
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    index = stops.push(stop) - 1;
  }, { source: SOURCE });
  return { i: index, j: 0, t };
}

/** Moves diamonds from their `orig` positions by delta percent. */
export function moveStops(store, part, orig, delta, key) {
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    for (const d of orig) {
      const t = round1(Math.max(0, Math.min(100, d.t + delta)));
      const s = stops[d.i];
      if (Array.isArray(s.t)) s.t[d.j] = t;
      else s.t = t;
    }
  }, { key, source: SOURCE });
}

export function setStopT(store, part, d, t) {
  moveStops(store, part, [d], round1(t) - d.t);
}

export function deleteStops(store, part, sel) {
  const info = trackInfo(store, part);
  if (!info?.editable || !sel.length) return false;
  if (sel.length >= diamonds(info.stops).length) {
    alert("A track needs at least one stop. Remove the track instead.");
    return false;
  }
  const order = [...sel].sort((a, b) => b.i - a.i || b.j - a.j);
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    for (const d of order) {
      const s = stops[d.i];
      if (Array.isArray(s.t) && s.t.length > 1) {
        s.t.splice(d.j, 1);
        if (s.t.length === 1) s.t = s.t[0];
      } else {
        stops.splice(d.i, 1);
      }
    }
  }, { source: SOURCE });
  return true;
}

/** Copies the selected stops so the earliest lands on percent `at` (or one grid step later). */
export function duplicateStops(store, part, sel, at, step = 5) {
  const info = trackInfo(store, part);
  if (!info?.editable || !sel.length) return [];
  const first = Math.min(...sel.map((d) => d.t));
  let delta = round1(at - first);
  if (Math.abs(delta) < 0.05) delta = step;
  const added = [];
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    for (const d of sel) {
      const t = round1(Math.max(0, Math.min(100, d.t + delta)));
      const copy = { ...clone(stops[d.i]), t };
      added.push({ i: stops.push(copy) - 1, j: 0, t });
    }
  }, { source: SOURCE });
  return added;
}

/** Gives one percent of a shared stop (t: [0, 100]) its own stop object. */
export function splitStop(store, part, d) {
  let out = null;
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    const s = stops[d.i];
    if (!Array.isArray(s.t) || s.t.length < 2) return;
    s.t.splice(d.j, 1);
    if (s.t.length === 1) s.t = s.t[0];
    out = { i: stops.push({ ...clone(s), t: d.t }) - 1, j: 0, t: d.t };
  }, { source: SOURCE });
  return out;
}

export function editStop(store, part, i, fn, key = null, source = SOURCE) {
  store.edit((draft, scope) => fn(stopsOf(draft, scope, part)[i]), { key, source });
}

/** Hand drag on the preview: moves the stop under the playhead, or adds one there. */
export function dragHandStop(store, part, t, point, state, key) {
  const info = trackInfo(store, part);
  if (!info?.editable) return;
  if (state.i == null) {
    const hit = diamonds(info.stops).find((d) => Math.abs(d.t - t) < 0.6);
    state.i = hit ? hit.i : null;
  }
  store.edit((draft, scope) => {
    const stops = stopsOf(draft, scope, part);
    if (state.i == null) state.i = stops.push({ t: round1(t), hand: point }) - 1;
    const s = stops[state.i];
    delete s.angles;
    s.hand = point;
  }, { key, source: SOURCE });
}

// ---------------------------------------------------------------- tracks
export function setTiming(store, part, key, value, opts = {}) {
  store.edit((_, scope) => {
    const m = scope.motion[part];
    if (value === "" || value == null || (key === "delay" && parseFloat(value) === 0)) delete m[key];
    else m[key] = value;
  }, { source: SOURCE, ...opts });
}

export function removeTrack(store, part) {
  store.edit((_, scope) => {
    delete scope.motion?.[part];
  }, { source: SOURCE });
}

function conflicts(store, part) {
  const scope = scopeOf(store.current.mood, store.variant);
  const keys = HAND_TRACKS.includes(part) ? [`${part}.u`, `${part}.f`] : /^arm-[lr]\.[uf]$/.test(part) ? [part.slice(0, 5)] : [];
  return keys.filter((k) => scope.motion?.[k] !== undefined);
}

function confirmConflicts(store, part) {
  const c = conflicts(store, part);
  return !c.length || confirm(`This replaces ${c.join(", ")} in this ${scopeName(store)} (a hand track and u/f keyframes can't be mixed). Continue?`);
}

function newKeyframeName(draft, store, base) {
  return uniqueName(base.replace(/\./g, "-"), new Set([...Object.keys(draft.keyframes || {}), ...Object.keys(store.ctx.keyframes)]));
}

/** New track for `part` lasting `L` ms: a hand track holding the pose, or flat local keyframes. */
export function addTrack(store, part, L) {
  if (!confirmConflicts(store, part)) return false;
  const duration = fmtTime(L);
  if (HAND_TRACKS.includes(part)) {
    const side = part.slice(-1);
    const body = handStop(store.ctx.rig, side, poseAngles(store, side));
    store.edit((_, scope) => {
      scope.motion ??= {};
      for (const k of conflicts(store, part)) delete scope.motion[k];
      scope.motion[part] = { stops: [{ t: [0, 100], ...clone(body) }, { t: 50, ...clone(body) }], duration, easing: "ease-in-out" };
    }, { source: SOURCE });
    return true;
  }
  const flat = part === "upper" || part === "body" ? "translateY(0)" : "rotate(0)";
  store.edit((draft, scope) => {
    const name = newKeyframeName(draft, store, part);
    (draft.keyframes ??= {})[name] = [{ t: [0, 100], transform: flat }, { t: 50, transform: flat }];
    scope.motion ??= {};
    for (const k of conflicts(store, part)) delete scope.motion[k];
    scope.motion[part] = { keyframes: name, duration, easing: "ease-in-out" };
  }, { source: SOURCE });
  return true;
}

/** Turns an arm's u/f keyframe motion into an equivalent hand-stop track. */
export function convertToHand(store, side) {
  const part = `arm-${side}`;
  const { rig } = store.ctx;
  const u = trackInfo(store, `${part}.u`);
  const f = trackInfo(store, `${part}.f`);
  const live = [u, f].filter((x) => x && x.kind === "kf");
  if (!live.length) return false;
  const pose = poseAngles(store, side);
  const span = (x) => x.tm.d * (x.tm.dir.startsWith("alternate") ? 2 : 1);
  const D = Math.max(...live.map(span));
  // Simple case: same plain timing -> keep the stop times and easing; otherwise sample the eased
  // motion (both directions of an alternate) every 5% and play the samples linearly.
  const simple = live.every((x) => x.tm.d === D && !x.tm.delay && x.tm.dir === "normal");
  const times = simple
    ? [...new Set(live.flatMap((x) => diamonds(x.stops).map((d) => d.t)).concat([0, 100]))].sort((a, b) => a - b)
    : Array.from({ length: 21 }, (_, i) => i * 5);
  const rot = (x, T) => {
    if (!x || x.kind !== "kf") return 0;
    const at = localAt(T, x.tm);
    const v = evalTransform(x.stops, at.t, x.m.easing);
    return v.raw ? parseTransform(v.raw)?.rot ?? 0 : v.rot;
  };
  const stops = times.map((t) => {
    const T = (t / 100) * D;
    return { t: round1(t), ...handStop(rig, side, [pose[0] + rot(u, T), pose[1] + rot(f, T)]) };
  });
  const easing = simple ? (u?.kind === "kf" ? u : f).m.easing : "linear";
  store.edit((_, scope) => {
    scope.motion ??= {};
    delete scope.motion[`${part}.u`];
    delete scope.motion[`${part}.f`];
    scope.motion[part] = { stops, duration: fmtTime(D), ...(easing ? { easing } : {}) };
  }, { source: SOURCE });
  return true;
}

/** Element orientation in the preview: -1 when the part's art is mirrored (scale(-1, 1)). */
function handedness(preview, selector) {
  const el = preview.svg?.querySelector(selector);
  const m = el?.getCTM();
  return m && m.a * m.d - m.b * m.c < 0 ? -1 : 1;
}

/**
 * Copies `part` to its other-side twin with mirrored values (hand x about rig.mirrorX; rotation and
 * x translation negated when both parts face the same way), optionally half a loop later.
 */
export function mirrorTrack(store, preview, part, half) {
  const info = trackInfo(store, part);
  const target = counterpart(part);
  if (!info || target === part || info.kind === "none") return false;
  const scope = scopeOf(store.current.mood, store.variant);
  if (scope.motion?.[target] !== undefined && !confirm(`Replace the existing ${target} track?`)) return false;
  if (!confirmConflicts(store, target)) return false;
  const { rig } = store.ctx;
  const m = clone(info.m);
  if (half) {
    const d = info.tm.d;
    const delay = normDelay(info.tm.delay - d / 2, d);
    if (delay) m.delay = fmtTime(delay);
    else delete m.delay;
  }
  store.edit((draft, sc) => {
    sc.motion ??= {};
    for (const k of conflicts(store, target)) delete sc.motion[k];
    if (info.kind === "hand") {
      m.stops = m.stops.map((s) => (s.hand ? { ...s, hand: [round1(2 * rig.mirrorX - s.hand[0]), s.hand[1]] } : s));
    } else {
      const flip = handedness(preview, rig.parts[part].selector) === handedness(preview, rig.parts[target].selector);
      if (flip) {
        const stops = info.stops.map((s) => (s.transform ? { ...clone(s), transform: mirrorTransform(s.transform) } : clone(s)));
        const base = counterpart(info.name) !== info.name ? counterpart(info.name) : `${info.name}-mirror`;
        const name = newKeyframeName(draft, store, base);
        (draft.keyframes ??= {})[name] = stops;
        m.keyframes = name;
      }
    }
    sc.motion[target] = m;
  }, { source: SOURCE });
  return target;
}

export function setBeat(store, bpm, counts) {
  store.edit((draft) => {
    const meta = (draft.meta ??= {});
    if (bpm > 0 && counts > 0) meta.editor = { ...(meta.editor || {}), bpm, counts };
    else delete meta.editor;
  }, { source: SOURCE });
}

// ---------------------------------------------------------------- bake period
/** Durations the bake would use (visible infinite CSS animations) -> its period, per-track retiming. */
export function periodReport(store, preview) {
  const hidden = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.opacity === "0" || cs.display === "none" || cs.visibility === "hidden") return true;
    }
    return false;
  };
  const durs = [];
  for (const a of preview.animations()) {
    const t = a.effect.getTiming();
    if (t.iterations === Infinity && t.duration > 0 && !(a.effect.target && hidden(a.effect.target))) durs.push(Math.round(t.duration * 1000) / 1000);
  }
  const uniq = [...new Set(durs)].sort((a, b) => a - b);
  const { period, frames } = bakePeriod(uniq);
  const off = (d) => Math.abs(retimed(d, period) - d) / d > 0.002;
  const L = loopMs(store);
  const tracks = rows(store, false).filter((r) => r.tm && r.tm.n === Infinity).map((r) => ({ part: r.part, d: r.tm.d, r: retimed(r.tm.d, period) }));
  return {
    period, frames, durations: uniq, L,
    loopOk: !off(L) && tracks.every((x) => Math.abs(L / x.d - Math.round(L / x.d)) < 0.01 || Math.abs(x.d / L - Math.round(x.d / L)) < 0.01),
    retimed: tracks.filter((x) => off(x.d)),
    uneven: tracks.filter((x) => !(Math.abs(L / x.d - Math.round(L / x.d)) < 0.01 || Math.abs(x.d / L - Math.round(x.d / L)) < 0.01)),
  };
}

export { ts, stopAngles };
