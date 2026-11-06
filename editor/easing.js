// Easing field: presets, free text and a cubic-bezier curve with two draggable control points.

import { EASE_PRESETS, parseEasing } from "./timeline/model.js";
import { h } from "./ui.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const PRESETS = [...Object.keys(EASE_PRESETS), "cubic-bezier(.34,1.5,.64,1)", "cubic-bezier(.3,.75,.4,1)", "steps(3)"];
const S = 92; // curve box size (px); y range -0.5..1.5 so overshoot fits
const X = (x) => 6 + x * (S - 12);
const Y = (y) => S - 6 - ((y + 0.5) / 2) * (S - 12);
const r2 = (v) => Number(v.toFixed(2));

const el = (tag, attrs = {}) => {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};

/**
 * easingField({value, onchange(value, {live, end}), inherit: "label for empty" | null, inheritValue, k})
 * Empty value means "inherit" when `inherit` is given; `inheritValue` is drawn as the curve then.
 */
export function easingField({ value, onchange, inherit = null, inheritValue = inherit, k = "easing" }) {
  const svg = el("svg", { class: "ease-curve", viewBox: `0 0 ${S} ${S}`, width: S, height: S });
  const text = h("input.time", {
    type: "text", value: value ?? "", placeholder: inherit ?? "ease", spellcheck: "false", list: "easings", dataset: { k },
    onchange: (e) => commit(e.target.value.trim()),
  });
  const presets = h("select.ease-presets", {
    dataset: { k: `${k}-p` }, title: "Presets",
    onchange: (e) => commit(e.target.value),
  },
  h("option", { value: "", selected: !PRESETS.includes(value) }, value && !PRESETS.includes(value) ? "custom" : inherit ? `↳ ${inherit}` : "preset…"),
  PRESETS.map((p) => h("option", { value: p, selected: p === value }, p)));

  function commit(v, live = false) {
    text.value = v;
    draw(v);
    onchange(v, { live });
  }

  function draw(v) {
    svg.replaceChildren();
    svg.append(el("rect", { class: "ease-box", x: X(0), y: Y(1), width: X(1) - X(0), height: Y(0) - Y(1) }));
    const e = parseEasing(v || inheritValue || "ease");
    if (!e) return;
    if (e.steps) {
      let d = `M${X(0)},${Y(e.start ? 1 / e.steps : 0)}`;
      for (let i = 1; i <= e.steps; i++) {
        const y = Math.min(1, (e.start ? i + 1 : i) / e.steps);
        d += `H${X(i / e.steps)}V${Y(y)}`;
      }
      svg.append(el("path", { class: "ease-line", d }));
      return;
    }
    const arm = el("path", { class: "ease-arm" });
    const line = el("path", { class: "ease-line" });
    svg.append(arm, line);
    const knobs = [];
    const place = ([x1, y1, x2, y2]) => {
      arm.setAttribute("d", `M${X(0)},${Y(0)}L${X(x1)},${Y(y1)}M${X(1)},${Y(1)}L${X(x2)},${Y(y2)}`);
      line.setAttribute("d", `M${X(0)},${Y(0)}C${X(x1)},${Y(y1)} ${X(x2)},${Y(y2)} ${X(1)},${Y(1)}`);
      knobs.forEach((kn, n) => {
        kn.setAttribute("cx", X([x1, x2][n]));
        kn.setAttribute("cy", Y([y1, y2][n]));
      });
    };
    if (v || !inherit) {
      for (let n = 0; n < 2; n++) knobs.push(el("circle", { class: "ease-knob", r: 5 }));
    }
    place(e.bezier);
    knobs.forEach((knob, n) => {
      knob.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        knob.setPointerCapture(ev.pointerId);
        const box = svg.getBoundingClientRect();
        const pts = [...e.bezier];
        const move = (mv) => {
          const px = ((mv.clientX - box.left) / box.width) * S;
          const py = ((mv.clientY - box.top) / box.height) * S;
          pts[n * 2] = r2(Math.max(0, Math.min(1, (px - 6) / (S - 12))));
          pts[n * 2 + 1] = r2(Math.max(-0.5, Math.min(1.5, ((S - 6 - py) / (S - 12)) * 2 - 0.5)));
          text.value = `cubic-bezier(${pts.join(",")})`;
          presets.value = "";
          presets.options[0].textContent = "custom";
          place(pts);
          onchange(text.value, { live: true });
        };
        const up = () => {
          knob.removeEventListener("pointermove", move);
          knob.removeEventListener("pointerup", up);
          onchange(text.value, { live: false, end: true });
        };
        knob.addEventListener("pointermove", move);
        knob.addEventListener("pointerup", up);
      });
      svg.append(knob);
    });
  }

  draw(value);
  return h("div.ease-field", {}, h("div.ease-inputs", {}, presets, text), svg);
}
