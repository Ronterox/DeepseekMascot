// Face & layers: expression layers from rig.layers. Eyes and mouths are one-of pickers, the rest toggles.

import { clearLayer, layerVisible, setLayer } from "../model.js";
import { h, section } from "../ui.js";
import { resetBtn } from "./pose.js";

const RADIO_GROUPS = new Set(["eyes", "mouths"]);

function chip(api, cls, item, { radio, group }) {
  const { mood, variant, ctx } = api;
  const st = layerVisible(mood, variant, ctx.rig, cls);
  return h("button.chip", {
    type: "button",
    role: radio ? "radio" : "switch",
    "aria-checked": String(st.value),
    class: [st.value ? "on" : "", st.own ? "own" : ""].join(" "),
    title: `.${cls}${item.default === "visible" ? " (visible by default)" : ""}${st.own ? " — set in this scope" : ""}`,
    dataset: { k: `layer-${cls}` },
    onclick: () => api.edit((draft) => {
      if (radio) {
        for (const other of Object.keys(group.items)) setLayer(draft, variant, ctx.rig, other, other === cls);
      } else {
        setLayer(draft, variant, ctx.rig, cls, !st.value);
      }
    }),
  }, h("span.chip-mark", {}), item.label, h("small.mono", {}, cls));
}

export const facePanel = {
  id: "face",
  label: "Face & layers",
  render(el, api) {
    const { mood, variant, ctx } = api;
    for (const [key, group] of Object.entries(ctx.rig.layers)) {
      const radio = RADIO_GROUPS.has(key);
      const classes = Object.keys(group.items);
      const visible = classes.filter((c) => layerVisible(mood, variant, ctx.rig, c).value);
      const anyOwn = classes.some((c) => layerVisible(mood, variant, ctx.rig, c).own);
      const tools = [];
      if (radio && visible.length > 1) tools.push(h("span.warn", { title: visible.join(", ") }, `${visible.length} shown`));
      if (radio) {
        tools.push(h("button.mini", {
          type: "button", title: "Hide all of this group", dataset: { k: `none-${key}` },
          onclick: () => api.edit((draft) => { for (const c of classes) setLayer(draft, variant, ctx.rig, c, false); }),
        }, "none"));
      }
      tools.push(resetBtn(() => api.edit((draft) => { for (const c of classes) clearLayer(draft, variant, c); }), anyOwn,
        variant == null ? "Reset group to the rig defaults" : "Reset group to the base mood"));
      el.append(section(group.label, { tools },
        h("div.chips", { role: radio ? "radiogroup" : "group", "aria-label": group.label },
          classes.map((cls) => chip(api, cls, group.items[cls], { radio, group })))));
    }
    el.append(h("p.note", {}, "Highlighted outline = set in this ", variant == null ? "mood" : `variant (strain ${variant})`,
      "; others are inherited."));
  },
};
