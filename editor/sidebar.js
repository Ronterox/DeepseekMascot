// Mood list: select, create (blank / duplicate), delete; dirty and error markers.

import { variantKeys } from "./model.js";
import { debounceFrame, h, iconSvg } from "./ui.js";

export class Sidebar {
  constructor(el, store, actions) {
    this.el = el;
    this.store = store;
    this.actions = actions; // {create, remove}
    this.render = debounceFrame(() => this.draw());
    store.on("change", ({ kind, source }) => {
      if (source !== "live" || kind !== "edit") this.render();
    });
    el.addEventListener("keydown", (e) => this.keys(e));
  }

  keys(e) {
    if (!e.target.closest(".mood-list") || !["ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const list = this.store.list();
    const i = list.findIndex((x) => x.id === this.store.selection.id);
    const j = { ArrowUp: i - 1, ArrowDown: i + 1, Home: 0, End: list.length - 1 }[e.key];
    const next = list[Math.max(0, Math.min(list.length - 1, j))];
    if (next) {
      this.store.select(next.id);
      requestAnimationFrame(() => this.el.querySelector(`[data-id="${next.id}"]`)?.focus());
    }
  }

  draw() {
    const { store } = this;
    const cur = store.current;
    const items = store.list().map((e) => {
      const dirty = store.isDirty(e);
      const errs = store.errorsFor(e).length;
      const accent = e.mood.meta?.theme?.accent || "#347fdb";
      const sel = e === cur;
      return h("li", {
        role: "option", "aria-selected": String(sel), tabindex: sel ? "0" : "-1", class: sel ? "on" : "",
        dataset: { id: e.id }, style: { "--mood": accent },
        onclick: () => store.select(e.id),
      },
      h("span.mood-ico", {}, iconSvg(e.mood.meta?.icon || "<circle cx=\"12\" cy=\"12\" r=\"4\"/>")),
      h("span.mood-text", {},
        h("span.mood-name", {}, e.mood.meta?.label || e.mood.name),
        h("span.mood-sub.mono", {}, e.mood.name, variantKeys(e.mood).length ? ` · ${variantKeys(e.mood).length} var` : "")),
      errs ? h("span.badge.err", { title: `${errs} validation problem(s)` }, "!") : null,
      dirty ? h("span.badge.dirty", { title: e.saved ? "Unsaved changes" : "New, not saved yet" }, e.saved ? "●" : "new") : null);
    });
    const canDelete = cur && !cur.mood.default;
    this.el.replaceChildren(
      h("div.side-head", {},
        h("h2", {}, "Moods"),
        h("span.grow"),
        h("button.mini", { type: "button", title: "New mood (blank or duplicate)", onclick: () => this.actions.create() }, "+ New")),
      h("ul.mood-list", { role: "listbox", "aria-label": "Moods" }, items),
      h("div.side-foot", {},
        h("button.mini", { type: "button", disabled: !cur, onclick: () => this.actions.create(true), title: "Duplicate the selected mood" }, "Duplicate"),
        h("button.mini.danger", {
          type: "button", disabled: !canDelete, onclick: () => this.actions.remove(),
          title: canDelete ? "Delete the selected mood" : "The default mood can't be deleted",
        }, "Delete")),
    );
  }
}
