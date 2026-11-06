// Whale-chan mood compiler: moods/*.json -> the mood CSS inside assets/whale-chan.svg
// plus the runtime registry (assets/moods.json). Shared by tools/build_whale_chan.py
// (through tools/compile_moods.mjs) and the browser editor, so it must stay dependency-free
// and free of Node-only APIs. See moods/README.md for the data format.
//
// ctx = { rig, defaults, keyframes }: assets/rig.json, moods/_defaults.json, moods/_keyframes.json.

const ROOT = ".whale-chan";
const INDENT = "    ";
const MOOD_KEYS = ["name", "order", "default", "meta", "pose", "layers", "motion", "keyframes", "variants", "css"];
const VARIANT_KEYS = ["pose", "layers", "motion", "css"];
const MOTION_KEYS = ["keyframes", "duration", "easing", "delay", "iterations", "direction"];
const TRACK_KEYS = ["stops", "duration", "easing", "delay", "iterations", "direction"];
const FISTS = ["none", "l", "r", "both"];
const SIDES = ["l", "r"];
const NAME_RE = /^[a-z][a-z0-9-]*$/;

// Python-compatible formatting: one decimal, trailing ".0" dropped.
export function fmt(v) {
  const s = v.toFixed(1);
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}

const round1 = (v) => Number(v.toFixed(1));

function pymod(a, b) {
  let m = a % b;
  if (m) {
    if ((b < 0) !== (m < 0)) m += b;
  } else {
    m = 0;
  }
  return m;
}

const DEG = 180 / Math.PI;

/**
 * Two-bone IK for one arm. `hand` is an absolute art-space target; the right arm is solved
 * in the mirrored left-arm frame, so the returned [upper, fore] angles (degrees, rounded to
 * 0.1) mean the same thing for either arm: the arm hangs along +y and positive swings outward.
 */
export function ik(rig, side, hand, elbowOut = true) {
  const L1 = rig.arms.upper;
  const L2 = rig.arms.fore;
  let [sx, sy] = rig.arms[side].shoulder;
  let [tx, ty] = hand;
  if (side === "r") {
    sx = 2 * rig.mirrorX - sx;
    tx = 2 * rig.mirrorX - tx;
  }
  const dx = tx - sx;
  const dy = ty - sy;
  const d = Math.max(Math.abs(L1 - L2) + 1, Math.min(Math.hypot(dx, dy), L1 + L2 - 0.5));
  const phi = Math.atan2(-dx, dy);
  const a = Math.acos((L1 ** 2 + d * d - L2 ** 2) / (2 * L1 * d));
  const options = [1, -1].map((sgn) => {
    const t1 = phi + sgn * a;
    const ex = sx - L1 * Math.sin(t1);
    const ey = sy + L1 * Math.cos(t1);
    const t12 = Math.atan2(-(tx - ex), ty - ey);
    const t2 = pymod(t12 - t1 + Math.PI, 2 * Math.PI) - Math.PI;
    const t1n = pymod(t1 + Math.PI, 2 * Math.PI) - Math.PI;
    return [ex, t1n * DEG, t2 * DEG];
  });
  if (elbowOut ? options[1][0] < options[0][0] : options[1][0] > options[0][0]) options.reverse();
  const [, u, f] = options[0];
  return [round1(u), round1(f)];
}

/** Hand position for given arm angles (forward kinematics, art space). */
export function fk(rig, side, [u, f]) {
  const { upper: L1, fore: L2 } = rig.arms;
  const [sx, sy] = rig.arms[side].shoulder;
  const s = side === "r" ? -1 : 1;
  const a1 = u / DEG;
  const a2 = (u + f) / DEG;
  const ex = sx - s * L1 * Math.sin(a1);
  const ey = sy + L1 * Math.cos(a1);
  return { elbow: [ex, ey], hand: [ex - s * L2 * Math.sin(a2), ey + L2 * Math.cos(a2)] };
}

function solveArm(rig, side, spec) {
  if (spec.angles) return [spec.angles[0], spec.angles[1]];
  return ik(rig, side, spec.hand, spec.elbowOut !== false);
}

export function sortMoods(moods) {
  return [...moods].sort((a, b) => (a.order ?? 1e9) - (b.order ?? 1e9) || a.name.localeCompare(b.name));
}

const variantKeys = (mood) => Object.keys(mood.variants || {}).sort((a, b) => Number(a) - Number(b));

function mergeArms(base, over) {
  return over ? { ...base, ...over } : base;
}

/** Resolved arm angles for a mood (optionally one data-strain variant): {l:[u,f], r:[u,f], fist}. */
export function resolvePose(mood, ctx, variant) {
  let arms = mergeArms(ctx.defaults.pose.arms, mood.pose?.arms);
  if (variant != null) arms = mergeArms(arms, mood.variants?.[variant]?.pose?.arms);
  return { l: solveArm(ctx.rig, "l", arms.l), r: solveArm(ctx.rig, "r", arms.r), fist: arms.fist || "none" };
}

function rootSelectors(mood, variant) {
  const base = [`${ROOT}[data-mood="${mood.name}"]`];
  if (mood.default) base.push(`${ROOT}:not([data-mood])`);
  if (variant == null) return base;
  const strain = [`[data-strain="${variant}"]`];
  if (variant === "0") strain.push(":not([data-strain])");
  return base.flatMap((b) => strain.map((s) => b + s));
}

const within = (roots, sel) => roots.map((r) => (sel ? `${r} ${sel}` : r)).join(", ");

function armVarDecls(rig, pose) {
  const out = [];
  for (const side of SIDES) {
    const v = rig.arms[side].vars;
    out.push(`${v.u}:${pose[side][0]}deg`, `${v.f}:${pose[side][1]}deg`);
  }
  for (const side of SIDES) {
    const on = pose.fist === side || pose.fist === "both";
    out.push(`${rig.arms[side].vars.fist}:${on ? 1 : 0}`);
  }
  return out;
}

function varDecls(vars) {
  return Object.entries(vars || {}).map(([k, v]) => `--${k}:${v}`);
}

function animation(m, name) {
  const parts = [name, m.duration];
  if (m.easing) parts.push(m.easing);
  if (m.delay) parts.push(m.delay);
  parts.push(m.iterations || "infinite");
  if (m.direction) parts.push(m.direction);
  return parts.join(" ");
}

function pct(t) {
  return (Array.isArray(t) ? t : [t]).map((x) => `${x}%`).join(", ");
}

// A stop's "easing" times the segment that starts at it.
const stopEasing = (s) => (s.easing ? ` animation-timing-function: ${s.easing};` : "");

function keyframesCss(name, stops) {
  const body = stops.map((s) => {
    const decls = Object.entries(s).filter(([k]) => k !== "t")
      .map(([k, v]) => `${k === "easing" ? "animation-timing-function" : k}: ${v};`).join(" ");
    return `${pct(s.t)} { ${decls} }`;
  });
  return `${INDENT}@keyframes ${name} { ${body.join(" ")} }`;
}

function partSelector(rig, part) {
  return rig.parts[part].selector;
}

// Hand-target track -> u/f keyframes holding offsets from the base pose, because .u-anim/.f-anim
// rotate on top of the .u-pose/.f-pose angles.
function trackKeyframes(rig, side, track, base) {
  const u = [];
  const f = [];
  for (const stop of track.stops) {
    const [su, sf] = solveArm(rig, side, stop);
    u.push(`${pct(stop.t)} { transform: rotate(${fmt(su - base[0])}deg);${stopEasing(stop)} }`);
    f.push(`${pct(stop.t)} { transform: rotate(${fmt(sf - base[1])}deg);${stopEasing(stop)} }`);
  }
  return { u: u.join(" "), f: f.join(" ") };
}

function expandCss(css, roots) {
  const out = [];
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf("{", i);
    if (open < 0) break;
    let depth = 1;
    let j = open + 1;
    while (j < css.length && depth) {
      if (css[j] === "{") depth++;
      else if (css[j] === "}") depth--;
      j++;
    }
    const head = css.slice(i, open).trim();
    const body = css.slice(open + 1, j - 1).trim();
    if (head.startsWith("@")) {
      out.push(`${INDENT}${head} { ${body} }`);
    } else {
      const sels = head.split(",").map((s) => s.trim()).filter(Boolean);
      const full = roots.flatMap((r) => sels.map((s) => (s.includes("&") ? s.replaceAll("&", r) : `${r} ${s}`)));
      out.push(`${INDENT}${full.join(", ")} { ${body} }`);
    }
    i = j;
  }
  return out;
}

function kfName(mood, key, ctx) {
  if (mood.keyframes && key in mood.keyframes) return `${mood.name}-${key}`;
  if (key in ctx.keyframes) return key;
  throw new Error(`${mood.name}: unknown keyframes "${key}"`);
}

function compileScope(mood, scope, ctx, { roots, variant, pose, basePose, baseMotion }) {
  const { rig } = ctx;
  const rules = [];
  const frames = [];
  const decls = [];
  if (scope.pose?.arms || variant == null) decls.push(...armVarDecls(rig, pose));
  decls.push(...varDecls(scope.pose?.vars));
  if (decls.length) rules.push(`${INDENT}${roots.join(", ")} { ${decls.join(";")}; }`);

  const show = scope.layers?.show || [];
  const hide = scope.layers?.hide || [];
  if (show.length) rules.push(`${INDENT}${show.map((c) => within(roots, `.${c}`)).join(", ")} { opacity: 1; }`);
  if (hide.length) rules.push(`${INDENT}${hide.map((c) => within(roots, `.${c}`)).join(", ")} { opacity: 0; }`);

  const motion = { ...(scope.motion || {}) };
  // A variant that moves an arm re-bases the mood's hand tracks for that arm.
  if (variant != null) {
    for (const side of SIDES) {
      const key = `arm-${side}`;
      const moved = pose[side][0] !== basePose[side][0] || pose[side][1] !== basePose[side][1];
      const overridden = key in motion || `${key}.u` in motion || `${key}.f` in motion;
      if (moved && !overridden && baseMotion?.[key]?.stops) motion[key] = baseMotion[key];
    }
  }
  const tag = variant == null ? mood.name : `${mood.name}-s${variant}`;
  for (const [part, m] of Object.entries(motion)) {
    if (part === "arm-l" || part === "arm-r") {
      const side = part.slice(-1);
      if (m === "none") {
        for (const j of ["u", "f"]) rules.push(`${INDENT}${within(roots, partSelector(rig, `${part}.${j}`))} { animation: none; }`);
        continue;
      }
      const kf = trackKeyframes(rig, side, m, pose[side]);
      for (const j of ["u", "f"]) {
        const name = `${tag}-${part}-${j}`;
        frames.push(`${INDENT}@keyframes ${name} { ${kf[j]} }`);
        rules.push(`${INDENT}${within(roots, partSelector(rig, `${part}.${j}`))} { animation: ${animation(m, name)}; }`);
      }
      continue;
    }
    const value = m === "none" ? "none" : animation(m, kfName(mood, m.keyframes, ctx));
    rules.push(`${INDENT}${within(roots, partSelector(rig, part))} { animation: ${value}; }`);
  }
  if (scope.css) rules.push(...expandCss(scope.css, roots));
  return { rules, frames };
}

/** CSS for one mood: base rules, then one block per data-strain variant, then its keyframes. */
export function compileMoodCss(mood, ctx) {
  const basePose = resolvePose(mood, ctx);
  const base = compileScope(mood, mood, ctx, { roots: rootSelectors(mood), pose: basePose });
  const rules = [`${INDENT}/* ---------- ${mood.name} ---------- */`, ...base.rules];
  const frames = [...base.frames];
  for (const v of variantKeys(mood)) {
    const out = compileScope(mood, mood.variants[v], ctx, {
      roots: rootSelectors(mood, v), variant: v, pose: resolvePose(mood, ctx, v), basePose, baseMotion: mood.motion,
    });
    rules.push(...out.rules);
    frames.push(...out.frames);
  }
  for (const [key, stops] of Object.entries(mood.keyframes || {})) frames.push(keyframesCss(`${mood.name}-${key}`, stops));
  return [...rules, ...frames].join("\n");
}

/** The whole mood stylesheet: defaults (pose vars + idle motion), every mood in order, keyframe library. */
export function compileCss(moods, ctx) {
  const { rig, defaults } = ctx;
  const errors = validate(moods, ctx);
  if (errors.length) throw new Error(errors.join("\n"));
  const out = ["    /* ---------- generated from moods/*.json by tools/moods.mjs ---------- */"];
  const decls = [...armVarDecls(rig, resolvePose({ name: "", pose: {} }, ctx)), ...varDecls(defaults.pose.vars)];
  out.push(`${INDENT}${ROOT} { ${decls.join(";")}; }`);
  for (const [part, m] of Object.entries(defaults.motion || {})) {
    out.push(`${INDENT}${partSelector(rig, part)} { animation: ${m === "none" ? "none" : animation(m, m.keyframes)}; }`);
  }
  for (const mood of sortMoods(moods)) out.push(compileMoodCss(mood, ctx));
  out.push(`${INDENT}/* ---------- shared part keyframes (moods/_keyframes.json) ---------- */`);
  for (const [name, stops] of Object.entries(ctx.keyframes)) out.push(keyframesCss(name, stops));
  return out.join("\n");
}

/** Runtime registry: ordered list of what the page, widget and desktop app need per mood. */
export function buildRegistry(moods) {
  return sortMoods(moods).map((m) => ({
    name: m.name,
    label: m.meta?.label ?? m.name,
    line: m.meta?.line ?? "",
    button: m.meta?.button !== false,
    icon: m.meta?.icon ?? null,
    slow: !!m.meta?.slow,
    default: !!m.default,
    theme: m.meta?.theme ?? null,
    variants: variantKeys(m),
  }));
}

// ---------------------------------------------------------------- validation
function layerClasses(rig) {
  const out = new Set();
  for (const group of Object.values(rig.layers)) for (const cls of Object.keys(group.items)) out.add(cls);
  return out;
}

const isPair = (v) => Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && Number.isFinite(x));

function checkArm(where, spec, errors) {
  if (!spec || typeof spec !== "object") return errors.push(`${where}: expected {hand:[x,y]} or {angles:[u,f]}`);
  if (spec.hand !== undefined && spec.angles !== undefined) errors.push(`${where}: give either "hand" or "angles", not both`);
  else if (spec.hand !== undefined ? !isPair(spec.hand) : !isPair(spec.angles)) errors.push(`${where}: "hand"/"angles" must be [number, number]`);
  if (spec.elbowOut !== undefined && typeof spec.elbowOut !== "boolean") errors.push(`${where}: "elbowOut" must be a boolean`);
}

function checkPose(where, pose, ctx, errors) {
  if (!pose) return;
  for (const k of Object.keys(pose)) if (k !== "arms" && k !== "vars") errors.push(`${where}.pose: unknown key "${k}"`);
  if (pose.arms) {
    for (const k of Object.keys(pose.arms)) {
      if (k === "fist") {
        if (!FISTS.includes(pose.arms.fist)) errors.push(`${where}.pose.arms.fist: must be one of ${FISTS.join(", ")}`);
      } else if (SIDES.includes(k)) {
        checkArm(`${where}.pose.arms.${k}`, pose.arms[k], errors);
      } else {
        errors.push(`${where}.pose.arms: unknown key "${k}"`);
      }
    }
  }
  for (const [k, v] of Object.entries(pose.vars || {})) {
    if (!(k in ctx.rig.poseVars)) errors.push(`${where}.pose.vars: unknown pose variable "${k}"`);
    else if (typeof v !== "string") errors.push(`${where}.pose.vars.${k}: must be a CSS string like "4deg"`);
  }
}

function checkStops(where, stops, errors, { hand = false } = {}) {
  if (!Array.isArray(stops) || !stops.length) return errors.push(`${where}: expected a non-empty list of stops`);
  stops.forEach((s, i) => {
    const ts = Array.isArray(s?.t) ? s.t : [s?.t];
    if (!ts.length || !ts.every((t) => typeof t === "number" && t >= 0 && t <= 100)) {
      errors.push(`${where}[${i}].t: must be a percent 0-100 or a list of them`);
    }
    if (s?.easing !== undefined && typeof s.easing !== "string") errors.push(`${where}[${i}].easing: must be a CSS easing string`);
    if (hand) checkArm(`${where}[${i}]`, s, errors);
  });
}

function checkMotion(where, motion, ctx, localKeyframes, errors) {
  if (!motion) return;
  const { parts } = ctx.rig;
  for (const [part, m] of Object.entries(motion)) {
    const at = `${where}.motion.${part}`;
    const track = part === "arm-l" || part === "arm-r";
    if (!track && !(part in parts)) {
      errors.push(`${at}: unknown rig part (known: ${[...Object.keys(parts), "arm-l", "arm-r"].join(", ")})`);
      continue;
    }
    if (track && (`${part}.u` in motion || `${part}.f` in motion)) errors.push(`${at}: a hand track can't be combined with ${part}.u/${part}.f`);
    if (m === "none") continue;
    if (!m || typeof m !== "object") {
      errors.push(`${at}: expected "none" or an animation object`);
      continue;
    }
    const allowed = track ? TRACK_KEYS : MOTION_KEYS;
    for (const k of Object.keys(m)) if (!allowed.includes(k)) errors.push(`${at}: unknown key "${k}"`);
    if (typeof m.duration !== "string" || !/^-?(\d+|\d*\.\d+)m?s$/.test(m.duration)) errors.push(`${at}.duration: expected a CSS time like ".5s"`);
    if (m.delay !== undefined && !/^-?(\d+|\d*\.\d+)m?s$/.test(m.delay)) errors.push(`${at}.delay: expected a CSS time like "-.25s"`);
    if (track) {
      checkStops(`${at}.stops`, m.stops, errors, { hand: true });
    } else if (typeof m.keyframes !== "string" || !(m.keyframes in localKeyframes || m.keyframes in ctx.keyframes)) {
      errors.push(`${at}.keyframes: missing keyframes "${m.keyframes}" (not in this mood's "keyframes" nor moods/_keyframes.json)`);
    }
  }
}

function checkLayers(where, layers, known, errors) {
  if (!layers) return;
  for (const k of Object.keys(layers)) {
    if (k !== "show" && k !== "hide") errors.push(`${where}.layers: unknown key "${k}"`);
    else for (const cls of layers[k] || []) if (!known.has(cls)) errors.push(`${where}.layers.${k}: unknown layer class "${cls}"`);
  }
}

/** Returns a list of human-readable schema errors (empty when everything is valid). */
export function validate(moods, ctx) {
  const errors = [];
  const known = layerClasses(ctx.rig);
  const names = new Set();
  let defaults = 0;
  for (const [name, stops] of Object.entries(ctx.keyframes)) checkStops(`_keyframes.${name}`, stops, errors);
  checkPose("_defaults", ctx.defaults.pose, ctx, errors);
  for (const k of ["l", "r"]) if (!ctx.defaults.pose?.arms?.[k]) errors.push(`_defaults.pose.arms.${k}: required`);
  checkMotion("_defaults", ctx.defaults.motion, ctx, {}, errors);
  for (const mood of moods) {
    const where = mood.name || "<unnamed>";
    if (typeof mood.name !== "string" || !NAME_RE.test(mood.name)) errors.push(`${where}: "name" must match ${NAME_RE}`);
    if (names.has(mood.name)) errors.push(`${where}: duplicate mood name`);
    names.add(mood.name);
    if (mood.default) defaults++;
    for (const k of Object.keys(mood)) if (!MOOD_KEYS.includes(k)) errors.push(`${where}: unknown key "${k}"`);
    const local = mood.keyframes || {};
    for (const [k, stops] of Object.entries(local)) checkStops(`${where}.keyframes.${k}`, stops, errors);
    checkPose(where, mood.pose, ctx, errors);
    checkLayers(where, mood.layers, known, errors);
    checkMotion(where, mood.motion, ctx, local, errors);
    if (mood.css !== undefined && typeof mood.css !== "string") errors.push(`${where}.css: must be a string`);
    for (const [v, variant] of Object.entries(mood.variants || {})) {
      const at = `${where}.variants.${v}`;
      if (!/^\d+$/.test(v)) errors.push(`${at}: variant keys are data-strain values ("0", "1", ...)`);
      for (const k of Object.keys(variant)) if (!VARIANT_KEYS.includes(k)) errors.push(`${at}: unknown key "${k}"`);
      checkPose(at, variant.pose, ctx, errors);
      checkLayers(at, variant.layers, known, errors);
      checkMotion(at, variant.motion, ctx, local, errors);
    }
  }
  if (defaults > 1) errors.push(`more than one mood has "default": true`);
  return errors;
}
