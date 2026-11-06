// Tiny DOM helpers shared by the panels.

/**
 * h("div.card", {onclick, title, dataset: {k: "x"}}, ...children). Props starting with "on" become
 * listeners, `class`/`style`/`dataset` behave as expected, booleans toggle attributes, `value`/`checked`
 * are set as properties.
 */
export function h(spec, props = {}, ...children) {
  const [tag, ...classes] = spec.split(".");
  const el = tag === "svg" || props.svg ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag || "div");
  if (classes.length) el.classList.add(...classes);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false || k === "svg") continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.classList.add(...String(v).split(/\s+/).filter(Boolean));
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style" && typeof v === "object") for (const [p, x] of Object.entries(v)) el.style.setProperty(p, x);
    else if (k === "value" || k === "checked" || k === "indeterminate") el[k] = v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function section(title, ...children) {
  const opts = typeof children[0] === "object" && children[0] && !(children[0] instanceof Node) && !Array.isArray(children[0]) ? children.shift() : {};
  return h("section.sec", { class: opts.class },
    h("header.sec-head", {}, h("h3", {}, title), opts.tools ? h("div.sec-tools", {}, opts.tools) : null),
    h("div.sec-body", {}, children));
}

export function field(label, control, { hint, wide } = {}) {
  return h("label.field", { class: wide ? "wide" : "", title: hint }, h("span.field-label", {}, label), control);
}

/** A <select> from [value, label] pairs (or plain strings); optgroups as {group, options}. */
export function select(options, value, props = {}) {
  const el = h("select", props);
  const add = (parent, o) => {
    const [v, l] = Array.isArray(o) ? o : [o, o];
    parent.append(h("option", { value: v, selected: v === value }, l));
  };
  for (const o of options) {
    if (o && o.group) {
      const g = h("optgroup", { label: o.group });
      o.options.forEach((x) => add(g, x));
      el.append(g);
    } else add(el, o);
  }
  el.value = value;
  return el;
}

export function seg(options, value, onpick, props = {}) {
  return h("div.seg", { role: "radiogroup", ...props }, options.map(([v, label, title]) =>
    h("button", {
      type: "button", role: "radio", "aria-checked": String(v === value), class: v === value ? "on" : "", title,
      onclick: () => onpick(v),
    }, label)));
}

export function iconSvg(markup, size = 24) {
  const el = h("svg.icon", { svg: true, viewBox: "0 0 24 24", width: size, height: size, "aria-hidden": "true" });
  try {
    el.innerHTML = markup || "";
  } catch {
    // malformed markup: leave empty
  }
  return el;
}

// ---------------------------------------------------------------- colours
export function parseColor(str) {
  if (typeof str !== "string") return null;
  const s = str.trim();
  let m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
  if (m) {
    const hx = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
    return { r: parseInt(hx.slice(0, 2), 16), g: parseInt(hx.slice(2, 4), 16), b: parseInt(hx.slice(4, 6), 16), a: 1 };
  }
  m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+))?\s*\)$/i.exec(s);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null;
}

export const toHex = ({ r, g, b }) => "#" + [r, g, b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");

export const tripleToRgb = (t) => ({ r: t[0] * 255, g: t[1] * 255, b: t[2] * 255, a: 1 });

export const rgbToTriple = ({ r, g, b }) => [r, g, b].map((v) => Number((v / 255).toFixed(3)));

export function debounceFrame(fn) {
  let queued = false;
  return () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      fn();
    });
  };
}
