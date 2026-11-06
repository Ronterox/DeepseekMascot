// Pure helpers over the mood data (moods/README.md): scopes, inheritance and small mutations.
// A "scope" is the mood itself (variant null) or one of its data-strain variants.

export const clone = (v) => (v === undefined ? undefined : structuredClone(v));
export const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
export const NAME_RE = /^[a-z][a-z0-9-]{0,23}$/;
export const FISTS = ["none", "l", "r", "both"];
export const SIDES = ["l", "r"];

export const variantKeys = (mood) => Object.keys(mood.variants || {}).sort((a, b) => Number(a) - Number(b));

export function scopeOf(mood, variant, create = false) {
  if (variant == null) return mood;
  if (!mood.variants?.[variant]) {
    if (!create) return {};
    mood.variants ??= {};
    mood.variants[variant] = {};
  }
  return mood.variants[variant];
}

/** Ensure a nested object path exists on `obj` and return the innermost object. */
export function ensure(obj, ...keys) {
  let o = obj;
  for (const k of keys) o = o[k] ??= {};
  return o;
}

function pruneScope(s) {
  if (s.pose) {
    if (s.pose.vars && !Object.keys(s.pose.vars).length) delete s.pose.vars;
    if (s.pose.arms && !Object.keys(s.pose.arms).length) delete s.pose.arms;
    if (!Object.keys(s.pose).length) delete s.pose;
  }
  if (s.layers) {
    for (const k of ["show", "hide"]) if (s.layers[k] && !s.layers[k].length) delete s.layers[k];
    if (!Object.keys(s.layers).length) delete s.layers;
  }
  if (s.motion && !Object.keys(s.motion).length) delete s.motion;
  if (s.css === "") delete s.css;
}

/** Drop empty containers left behind by edits (variants themselves are kept even when empty). */
export function prune(mood) {
  pruneScope(mood);
  if (mood.keyframes && !Object.keys(mood.keyframes).length) delete mood.keyframes;
  for (const v of Object.values(mood.variants || {})) pruneScope(v);
  if (mood.variants && !Object.keys(mood.variants).length) delete mood.variants;
  return mood;
}

// ---------------------------------------------------------------- inheritance
// Each lookup returns {value, from} where from is "variant" | "mood" | "defaults" | "rig" | null.

export function poseVar(mood, variant, ctx, key) {
  if (variant != null) {
    const v = mood.variants?.[variant]?.pose?.vars?.[key];
    if (v !== undefined) return { value: v, from: "variant" };
  }
  if (mood.pose?.vars?.[key] !== undefined) return { value: mood.pose.vars[key], from: "mood" };
  if (ctx.defaults.pose?.vars?.[key] !== undefined) return { value: ctx.defaults.pose.vars[key], from: "defaults" };
  return { value: ctx.rig.poseVars[key].default, from: "rig" };
}

/** Arm spec ("l" | "r") or fist ("fist") as the cascade resolves it. */
export function armSpec(mood, variant, ctx, key) {
  if (variant != null) {
    const v = mood.variants?.[variant]?.pose?.arms?.[key];
    if (v !== undefined) return { value: v, from: "variant" };
  }
  if (mood.pose?.arms?.[key] !== undefined) return { value: mood.pose.arms[key], from: "mood" };
  const d = ctx.defaults.pose.arms[key];
  return { value: d ?? (key === "fist" ? "none" : undefined), from: "defaults" };
}

export function scopeLayerState(scope, cls) {
  if (scope?.layers?.hide?.includes(cls)) return false;
  if (scope?.layers?.show?.includes(cls)) return true;
  return undefined;
}

export function layerDefault(rig, cls) {
  for (const g of Object.values(rig.layers)) if (cls in g.items) return g.items[cls].default === "visible";
  return false;
}

/** Visibility inherited by `variant`'s scope (i.e. ignoring that scope's own show/hide). */
export function layerInherited(mood, variant, rig, cls) {
  if (variant == null) return layerDefault(rig, cls);
  return scopeLayerState(mood, cls) ?? layerDefault(rig, cls);
}

export function layerVisible(mood, variant, rig, cls) {
  const own = scopeLayerState(scopeOf(mood, variant), cls);
  return { value: own ?? layerInherited(mood, variant, rig, cls), own: own !== undefined };
}

/** Mutates `mood` so `cls` ends up `visible` in the scope, recording it only when it differs from what's inherited. */
export function setLayer(mood, variant, rig, cls, visible) {
  const scope = scopeOf(mood, variant, true);
  const layers = (scope.layers ??= {});
  for (const k of ["show", "hide"]) if (layers[k]) layers[k] = layers[k].filter((c) => c !== cls);
  if (visible === layerInherited(mood, variant, rig, cls)) return;
  (layers[visible ? "show" : "hide"] ??= []).push(cls);
}

export function clearLayer(mood, variant, cls) {
  const layers = scopeOf(mood, variant).layers;
  if (!layers) return;
  for (const k of ["show", "hide"]) if (layers[k]) layers[k] = layers[k].filter((c) => c !== cls);
}

export function motionOf(mood, variant, ctx, part) {
  if (variant != null) {
    const v = mood.variants?.[variant]?.motion?.[part];
    if (v !== undefined) return { value: v, from: "variant" };
  }
  if (mood.motion?.[part] !== undefined) return { value: mood.motion[part], from: "mood" };
  if (ctx.defaults.motion?.[part] !== undefined) return { value: ctx.defaults.motion[part], from: "defaults" };
  return { value: null, from: null };
}

/** The hand track ("arm-l" | "arm-r") that drives `side`'s u/f animation in this scope, if any. */
export function trackFor(mood, variant, side) {
  const key = `arm-${side}`;
  const own = scopeOf(mood, variant).motion || {};
  if (own[key] !== undefined) return { value: own[key], from: variant == null ? "mood" : "variant" };
  if (variant != null && !(`${key}.u` in own) && !(`${key}.f` in own) && mood.motion?.[key] !== undefined) {
    return { value: mood.motion[key], from: "mood" };
  }
  return null;
}

// ---------------------------------------------------------------- formatting
/** CSS-ish number: at most 3 decimals, no leading zero (".75", "-.5"), like the hand-kept files. */
export function num(v) {
  const s = String(Number(Number(v).toFixed(3)));
  return s.replace(/^(-?)0\./, "$1.");
}

export function splitUnit(value) {
  const m = /^(-?(?:\d+\.?\d*|\.\d+))(.*)$/.exec(String(value).trim());
  return m ? { n: Number(m[1]), unit: m[2] } : { n: 0, unit: "" };
}

export function motionSummary(m) {
  if (m == null) return "no animation";
  if (m === "none") return "none (stopped)";
  if (m.stops) return `hand track · ${m.stops.length} stops · ${m.duration}`;
  return [m.keyframes, m.duration, m.easing, m.delay && `delay ${m.delay}`, m.direction, m.iterations && m.iterations !== "infinite" && `×${m.iterations}`]
    .filter(Boolean).join(" · ");
}

// ---------------------------------------------------------------- new moods
export function uniqueName(base, taken) {
  let name = base.slice(0, 24);
  for (let i = 2; taken.has(name); i++) name = `${base.slice(0, 21)}-${i}`;
  return name;
}

export function blankMood(name, ctx, neutral, order) {
  const theme = clone(neutral?.meta?.theme) || {};
  theme.button = theme.accent ?? null;
  delete theme.variants;
  return {
    name,
    order,
    meta: { label: name[0].toUpperCase() + name.slice(1).replace(/-/g, " "), line: "", button: true, icon: null, slow: false, theme },
    pose: { arms: clone(ctx.defaults.pose.arms), vars: {} },
    layers: { show: ["m-neutral"] },
  };
}

export function duplicateMood(src, name, order) {
  const m = clone(src);
  m.name = name;
  m.order = order;
  delete m.default;
  if (m.meta) m.meta.label = `${m.meta.label ?? src.name} copy`;
  return m;
}
