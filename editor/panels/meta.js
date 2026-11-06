// Meta: name, label, speech line, menu order, button/slow flags, icon and theme colours.
// Shared by all variants (runtime only, doesn't affect the SVG).

import { ensure, NAME_RE } from "../model.js";
import { field, h, iconSvg, parseColor, rgbToTriple, section, toHex, tripleToRgb } from "../ui.js";

function text(api, k, value, onchange, props = {}) {
  return h(props.rows ? "textarea" : "input", {
    type: props.rows ? undefined : "text", value: value ?? "", dataset: { k }, spellcheck: props.rows ? "true" : "false",
    ...props, onchange: (e) => onchange(e.target.value, e),
  });
}

function colorRow(api, key, label, { alpha = false } = {}) {
  const theme = api.mood.meta?.theme || {};
  const raw = theme[key];
  const c = parseColor(raw);
  const set = (v, opts) => api.edit((d) => { ensure(d, "meta", "theme")[key] = v; }, opts);
  const picker = h("input.swatch", {
    type: "color", value: c ? toHex(c) : "#000000", dataset: { k: `theme-${key}-c` },
    oninput: (e) => {
      const p = parseColor(e.target.value);
      const next = alpha ? `rgba(${p.r}, ${p.g}, ${p.b}, ${c?.a ?? 0.12})` : e.target.value;
      textIn.value = next;
      set(next, { key: `theme-${key}`, source: "live" });
    },
    onchange: () => api.rerender(),
  });
  const textIn = text(api, `theme-${key}-t`, raw ?? "", (v) => set(v.trim() === "" ? null : v.trim()), { placeholder: "none (null)" });
  return field(label, h("div.color", { class: raw == null ? "empty" : "" }, picker, textIn));
}

function tripleRow(api, key, label) {
  const theme = api.mood.meta?.theme || {};
  const t = Array.isArray(theme[key]) ? theme[key] : null;
  const set = (v, opts) => api.edit((d) => { ensure(d, "meta", "theme")[key] = v; }, opts);
  const out = h("code.triple", {}, t ? `[${t.join(", ")}]` : "unset");
  return field(label, h("div.color", {},
    h("input.swatch", {
      type: "color", value: t ? toHex(tripleToRgb(t)) : "#000000", dataset: { k: `theme-${key}` },
      oninput: (e) => {
        const triple = rgbToTriple(parseColor(e.target.value));
        out.textContent = `[${triple.join(", ")}]`;
        set(triple, { key: `theme-${key}`, source: "live" });
      },
      onchange: () => api.rerender(),
    }), out), { hint: "Desktop app colour, stored as RGB 0-1" });
}

function jsonArea(api, k, value, onvalue, rows = 3) {
  const err = h("div.field-error");
  const area = h("textarea.mono", {
    rows, spellcheck: "false", dataset: { k }, value: value === undefined ? "" : JSON.stringify(value, null, 1).replace(/\n\s*/g, " "),
    onchange: (e) => {
      const s = e.target.value.trim();
      if (!s) return onvalue(undefined);
      try {
        onvalue(JSON.parse(s));
      } catch (ex) {
        err.textContent = ex.message;
      }
    },
  });
  return h("div", {}, area, err);
}

export const metaPanel = {
  id: "meta",
  label: "Meta",
  render(el, api) {
    const { mood, store, entry, edit } = api;
    const meta = mood.meta || {};
    const theme = meta.theme || {};
    const setMeta = (k, v) => edit((d) => { ensure(d, "meta")[k] = v; });
    const nameErr = h("div.field-error");
    const nameIn = text(api, "name", mood.name, (v) => {
      const name = v.trim();
      if (!NAME_RE.test(name)) {
        nameErr.textContent = "lowercase letters, digits and dashes; starts with a letter; max 24";
        return;
      }
      const other = store.byName(name);
      if (other && other !== entry) {
        nameErr.textContent = `"${name}" is already taken`;
        return;
      }
      edit((d) => { d.name = name; });
    }, { maxlength: 24, pattern: NAME_RE.source, autocomplete: "off" });

    const iconBox = h("div.icon-preview", {}, iconSvg(meta.icon), iconSvg(meta.icon, 40));
    const iconArea = text(api, "icon", meta.icon ?? "", (v) => setMeta("icon", v.trim() ? v.trim() : null), {
      rows: 4, class: "mono", placeholder: "inner markup of a 24×24 icon, e.g. <path d=\"…\"/>",
      oninput: (e) => iconBox.replaceChildren(iconSvg(e.target.value), iconSvg(e.target.value, 40)),
    });

    el.append(
      section("Identity",
        h("div.grid2", {},
          field("Name (file / data-mood)", h("div", {}, nameIn, nameErr), {
            hint: entry.savedName && entry.savedName !== mood.name ? `Will rename moods/${entry.savedName}.json on save` : "moods/<name>.json",
          }),
          field("Label", text(api, "label", meta.label, (v) => setMeta("label", v))),
          field("Order", h("input.num", {
            type: "number", step: "10", value: mood.order ?? "", dataset: { k: "order" },
            onchange: (e) => edit((d) => {
              if (e.target.value === "") delete d.order;
              else d.order = Number(e.target.value);
            }),
          }), { hint: "Menu order, ascending" }),
          h("div.checks", {},
            h("label.check", {}, h("input", { type: "checkbox", checked: meta.button !== false, dataset: { k: "button" }, onchange: (e) => setMeta("button", e.target.checked) }), "Mood button"),
            h("label.check", { title: "Desktop app plays it at a reduced frame rate" }, h("input", { type: "checkbox", checked: !!meta.slow, dataset: { k: "slow" }, onchange: (e) => setMeta("slow", e.target.checked) }), "Slow"),
            mood.default ? h("span.pill", { title: "Matches an SVG without data-mood; can't be deleted" }, "default mood") : null)),
        field("Speech line", text(api, "line", meta.line, (v) => setMeta("line", v), { rows: 2 }), { wide: true })),
      section("Icon", h("div.icon-edit", {}, iconArea, iconBox)),
      section("Theme",
        h("div.grid2", {},
          colorRow(api, "accent", "Accent"),
          colorRow(api, "accentDeep", "Accent deep"),
          colorRow(api, "accentSoft", "Accent soft", { alpha: true }),
          colorRow(api, "button", "Button"),
          colorRow(api, "bubble", "Speech bubble"),
          h("div"),
          tripleRow(api, "desktopAccent", "Desktop accent"),
          tripleRow(api, "desktopGlow", "Desktop glow")),
        field("Aura stops (one per line)", text(api, "aura-stops", (theme.aura?.stops || []).join("\n"), (v) => edit((d) => {
          const aura = ensure(d, "meta", "theme", "aura");
          aura.stops = v.split("\n").map((s) => s.trim()).filter(Boolean);
        }), { rows: 4, class: "mono" }), { wide: true }),
        h("div.grid2", {},
          field("Aura duration", text(api, "aura-dur", theme.aura?.duration, (v) => edit((d) => {
            ensure(d, "meta", "theme", "aura").duration = v.trim();
          }), { placeholder: "e.g. 4.8s" })),
          h("div.aura", {
            title: "Aura preview",
            style: { background: theme.aura?.stops?.length ? `radial-gradient(ellipse closest-side, ${theme.aura.stops.join(", ")}), #fbf8f0` : "" },
          })),
        h("details.adv", {},
          h("summary", {}, "Floor shadow & theme variants (JSON)"),
          field("floorShadow", jsonArea(api, "floor", theme.floorShadow, (v) => edit((d) => {
            const t = ensure(d, "meta", "theme");
            if (v === undefined) delete t.floorShadow;
            else t.floorShadow = v;
          })), { wide: true, hint: "null or {stops?, animation?, width?}; missing keys fall back to neutral" }),
          field("variants", jsonArea(api, "theme-variants", theme.variants, (v) => edit((d) => {
            const t = ensure(d, "meta", "theme");
            if (v === undefined) delete t.variants;
            else t.variants = v;
          })), { wide: true, hint: 'Per data-strain theme overrides, e.g. {"2": {"floorShadow": {...}}}' }))),
      h("p.note", {}, "Meta is shared by every variant and only used by the page, widget and desktop app."),
    );
  },
};
