// Inspector: variant (scope) bar, validation errors and the tabbed panels for the selected mood.
// Panels are plain {id, label, render(el, api)} objects; add one to PANELS to get a new tab.

import { facePanel } from "./panels/face.js";
import { metaPanel } from "./panels/meta.js";
import { motionPanel } from "./panels/motion.js";
import { posePanel } from "./panels/pose.js";
import { trackPanel } from "./panels/track.js";
import { variantKeys } from "./model.js";
import { debounceFrame, h } from "./ui.js";

export const PANELS = [posePanel, facePanel, motionPanel, trackPanel, metaPanel];

export class Inspector {
  constructor(el, store, preview) {
    this.el = el;
    this.store = store;
    this.preview = preview;
    this.tab = localStorage.getItem("whale-editor-tab") || "pose";
    this.render = debounceFrame(() => this.draw());
    store.on("change", ({ kind, source }) => {
      if (kind === "track" && source === "timeline" && store.track.part && this.tab !== "track") {
        this.tab = "track";
        localStorage.setItem("whale-editor-tab", "track");
      }
      if (source !== "live") this.render();
      else this.drawErrors();
    });
  }

  setTab(id) {
    this.tab = id;
    localStorage.setItem("whale-editor-tab", id);
    this.draw();
  }

  api(entry) {
    const { store } = this;
    return {
      store, entry, preview: this.preview,
      ctx: store.ctx,
      mood: entry.mood,
      variant: store.variant,
      edit: (fn, opts = {}) => store.edit(fn, { source: "inspector", ...opts }),
      rerender: () => this.render(),
    };
  }

  variantBar(entry) {
    const { store } = this;
    const keys = variantKeys(entry.mood);
    const cur = store.variant;
    const tab = (v, label, title) => h("button", {
      type: "button", role: "tab", "aria-selected": String(cur === v), class: cur === v ? "on" : "", title,
      onclick: () => store.selectVariant(v),
    }, label);
    const add = () => {
      let n = 0;
      while (keys.includes(String(n))) n++;
      const v = String(n);
      store.edit((d) => { (d.variants ??= {})[v] = {}; });
      store.selectVariant(v);
    };
    const remove = () => {
      if (!confirm(`Delete variant (strain ${cur}) of ${entry.mood.name}?`)) return;
      store.edit((d) => {
        delete d.variants[cur];
        if (!Object.keys(d.variants).length) delete d.variants;
      });
      store.selectVariant(null);
    };
    return h("div.scopebar", { role: "tablist", "aria-label": "Variant" },
      h("span.scope-label", {}, keys.length ? "Strain" : "Scope"),
      tab(null, "Base", "The mood itself (what every variant inherits)"),
      keys.map((v) => tab(v, v, `Variant: data-strain="${v}" overrides`)),
      h("button.icon-btn", { type: "button", title: "Add a data-strain variant", onclick: add }, "+"),
      h("span.grow"),
      cur == null && keys.includes("0")
        ? h("span.muted.small", { title: 'Variant "0" also matches an SVG without data-strain' }, "preview includes strain 0")
        : null,
      cur != null ? h("button.mini.danger", { type: "button", onclick: remove, title: `Delete variant ${cur}` }, "delete") : null);
  }

  drawErrors() {
    const entry = this.store.current;
    const box = this.el.querySelector(".errors");
    if (!entry || !box) return;
    const errs = this.store.errorsFor(entry);
    const other = this.store.errors().length - errs.length;
    box.hidden = !errs.length && !other;
    box.replaceChildren(
      ...errs.map((e) => h("li", {}, e)),
      other ? h("li.muted", {}, `${other} problem(s) in other moods`) : "",
    );
  }

  draw() {
    const { store } = this;
    const entry = store.current;
    const active = document.activeElement;
    const focusKey = this.el.contains(active) ? active?.dataset?.k : null;
    const body = this.el.querySelector(".insp-body");
    const scroll = body ? body.scrollTop : 0;
    if (!entry) {
      this.el.replaceChildren(h("p.empty", {}, "No mood selected."));
      return;
    }
    const panel = PANELS.find((p) => p.id === this.tab) || PANELS[0];
    const content = h("div.insp-body", { role: "tabpanel" });
    try {
      panel.render(content, this.api(entry));
    } catch (err) {
      console.error(err);
      content.append(h("pre.crash", {}, `Panel error: ${err.message}`));
    }
    this.el.replaceChildren(
      h("div.insp-head", {},
        h("div.tabs", { role: "tablist" }, PANELS.map((p, i) => h("button", {
          type: "button", role: "tab", "aria-selected": String(p === panel), class: p === panel ? "on" : "",
          title: `${p.label} (Alt+${i + 1})`, onclick: () => this.setTab(p.id),
        }, p.label))),
        panel.id === "meta" ? h("div.scopebar.muted", {}, "Meta applies to the whole mood") : this.variantBar(entry)),
      h("ul.errors", { hidden: true, role: "alert" }),
      content,
    );
    this.drawErrors();
    content.scrollTop = scroll;
    if (focusKey) {
      const el = content.querySelector(`[data-k="${CSS.escape(focusKey)}"]`);
      if (el) el.focus({ preventScroll: true });
    }
  }
}
