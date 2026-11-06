// Pose: arm targets (also draggable on the preview), fists and every pose variable from rig.json.

import { fk, ik, resolvePose } from "../../tools/moods.mjs";
import { armSpec, ensure, FISTS, num, poseVar, scopeOf, splitUnit } from "../model.js";
import { field, h, section, select, seg } from "../ui.js";

const SIDE_LABEL = { l: "Left arm", r: "Right arm" };
const FIST_LABEL = { none: "Open hands", l: "Left fist", r: "Right fist", both: "Both fists" };

export function originBadge(from, variant) {
  const own = variant == null ? from === "mood" : from === "variant";
  const text = own ? "set" : from === "mood" ? "base" : from === "defaults" || from === "rig" ? "default" : "";
  return h("span.origin", { class: own ? "own" : "", title: own ? "Set in this scope" : `Inherited from ${from}` }, text);
}

export function resetBtn(onclick, enabled, title = "Reset to inherited value") {
  return h("button.icon-btn.reset", { type: "button", title, disabled: !enabled, onclick }, "↺");
}

function armRows(api, side) {
  const { mood, variant, ctx, edit } = api;
  const spec = armSpec(mood, variant, ctx, side);
  const own = variant == null ? spec.from === "mood" : spec.from === "variant";
  const value = spec.value;
  const angles = resolvePose(mood, ctx, variant)[side];
  const mode = value.angles ? "angles" : "hand";
  const set = (next, opts) => edit((_, scope) => {
    ensure(scope, "pose", "arms")[side] = next;
  }, opts);
  const liveNum = (k, get, put) => h("input.num", {
    type: "number", step: "any", value: get(), dataset: { k: `${side}-${k}` },
    oninput: (e) => {
      const n = Number(e.target.value);
      if (Number.isFinite(n) && e.target.value !== "") set(put(n), { key: `arm-${side}-${k}`, source: "live" });
    },
    onchange: () => api.rerender(),
  });

  let inputs;
  if (mode === "hand") {
    const [x, y] = value.hand;
    inputs = [
      field("Hand X", liveNum("x", () => x, (n) => ({ ...value, hand: [n, value.hand[1]] }))),
      field("Hand Y", liveNum("y", () => y, (n) => ({ ...value, hand: [value.hand[0], n] }))),
      h("label.check", { title: "Which IK solution: elbow out (default) or tucked in" },
        h("input", {
          type: "checkbox", checked: value.elbowOut !== false, dataset: { k: `${side}-elbow` },
          onchange: (e) => {
            const next = { hand: value.hand };
            if (!e.target.checked) next.elbowOut = false;
            set(next);
          },
        }), "Elbow out"),
    ];
  } else {
    inputs = [
      field("Upper °", liveNum("u", () => value.angles[0], (n) => ({ angles: [n, value.angles[1]] }))),
      field("Fore °", liveNum("f", () => value.angles[1], (n) => ({ angles: [value.angles[0], n] }))),
    ];
  }
  const toMode = (m) => {
    if (m === mode) return;
    if (m === "angles") set({ angles: [...angles] });
    else {
      const p = fk(ctx.rig, side, angles).hand.map((v) => Number(v.toFixed(1)));
      set({ hand: p });
    }
  };
  return h("div.arm-block", {},
    h("div.row-head", {},
      h("strong", {}, SIDE_LABEL[side]),
      originBadge(spec.from, variant),
      h("span.grow"),
      seg([["hand", "Target", "Hand target in art space, solved with IK"], ["angles", "Angles", "Upper/fore arm angles in degrees"]], mode, toMode),
      resetBtn(() => edit((_, scope) => { delete scope.pose?.arms?.[side]; }), own)),
    h("div.grid3", {}, inputs),
    scopeOf(mood, variant).motion?.[`arm-${side}`]?.stops
      ? h("p.note", {}, "This arm has a hand track: while the timeline is open, the preview handle edits its stops.")
      : null,
    mode === "angles" ? null : h("div.solved.muted.mono", { title: "Solved angles: upper arm, forearm (degrees; + swings outward)" }, `upper ${angles[0]}°  fore ${angles[1]}°`));
}

function varRow(api, key, def) {
  const { mood, variant, ctx, edit } = api;
  const cur = poseVar(mood, variant, ctx, key);
  const own = variant == null ? cur.from === "mood" : cur.from === "variant";
  const { n } = splitUnit(cur.value);
  const unit = def.unit;
  const put = (v, opts) => edit((_, scope) => {
    ensure(scope, "pose", "vars")[key] = `${num(v)}${unit}`;
  }, opts);
  const range = h("input.range", {
    type: "range", min: Math.min(def.min, n), max: Math.max(def.max, n), step: def.step, value: n, dataset: { k: `var-${key}-r` },
    oninput: (e) => {
      box.value = e.target.value;
      put(Number(e.target.value), { key: `var-${key}`, source: "live" });
    },
    onchange: () => api.rerender(),
  });
  const box = h("input.num", {
    type: "number", step: def.step, value: n, dataset: { k: `var-${key}-n` },
    oninput: (e) => {
      if (e.target.value === "" || !Number.isFinite(Number(e.target.value))) return;
      range.value = e.target.value;
      put(Number(e.target.value), { key: `var-${key}`, source: "live" });
    },
    onchange: () => api.rerender(),
  });
  return h("div.var-row", { class: own ? "own" : "", title: `--${key} (${cur.value}, from ${cur.from})` },
    h("span.var-label", {}, def.label),
    range, box, h("span.unit", {}, unit || "×"),
    resetBtn(() => edit((_, scope) => { delete scope.pose?.vars?.[key]; }), own,
      variant == null ? "Reset to the default" : "Reset to the base mood's value"));
}

export const posePanel = {
  id: "pose",
  label: "Pose",
  render(el, api) {
    const { mood, variant, ctx, edit } = api;
    const fist = armSpec(mood, variant, ctx, "fist");
    const fistOwn = variant == null ? fist.from === "mood" : fist.from === "variant";
    el.append(
      section("Arms", {
        tools: h("span.muted", {}, "drag the ", h("b.handle-dot", {}), " handles on the preview"),
      },
      armRows(api, "l"),
      armRows(api, "r"),
      h("div.row-head", {},
        h("strong", {}, "Fists"), originBadge(fist.from, variant), h("span.grow"),
        select(FISTS.map((f) => [f, FIST_LABEL[f]]), fist.value, {
          dataset: { k: "fist" },
          onchange: (e) => edit((_, scope) => { ensure(scope, "pose", "arms").fist = e.target.value; }),
        }),
        resetBtn(() => edit((_, scope) => { delete scope.pose?.arms?.fist; }), fistOwn))),
      section("Pose variables", {
        tools: h("span.muted", {}, variant == null ? "unset = _defaults.json" : "unset = base mood"),
      }, Object.entries(ctx.rig.poseVars).map(([k, def]) => varRow(api, k, def))),
    );
  },
};

/** Preview drag handler: moves `side`'s hand in the selected scope, keeping its mode (target/angles). */
export function dragHand(store, side, point, dragKey) {
  const entry = store.current;
  if (!entry) return;
  const { ctx } = store;
  const spec = armSpec(entry.mood, store.variant, ctx, side).value;
  store.edit((_, scope) => {
    const arms = ensure(scope, "pose", "arms");
    if (spec.angles) arms[side] = { angles: ik(ctx.rig, side, point, true) };
    else arms[side] = spec.elbowOut === false ? { hand: point, elbowOut: false } : { hand: point };
  }, { key: dragKey, source: "preview" });
}
