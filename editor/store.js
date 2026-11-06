// Editor state: the working copy of every mood, what's saved on disk, the selection and per-mood
// undo history. Views subscribe with store.on("change", fn); detail = {kind, source}.
//   kind: "edit" | "select" | "list" | "history" | "saved" | "context" | "track"
//   source: who caused it ("inspector", "live", "preview", "timeline", ...), so a view can skip
//   re-rendering for its own live edits.

import { sortMoods, validate } from "../tools/moods.mjs";
import { clone, equal, prune, scopeOf, variantKeys } from "./model.js";

const HISTORY = 200;
const COALESCE_MS = 1500;

let nextId = 1;

export class Store extends EventTarget {
  constructor({ moods, defaults, keyframes, rig }) {
    super();
    this.ctx = { rig, defaults, keyframes };
    this.entries = new Map();
    for (const mood of Object.values(moods)) this.add(mood, true);
    const first = this.list().find((e) => e.mood.default) || this.list()[0];
    this.selection = { id: first?.id ?? null, variant: null };
    this.track = { part: null, stops: [] }; // timeline selection: a part and diamonds [{i, j, t}]
    this._errors = null;
  }

  on(type, fn) {
    this.addEventListener(type, (e) => fn(e.detail));
  }

  emit(kind, source) {
    if (kind !== "select" && kind !== "track") this._errors = null;
    this.dispatchEvent(new CustomEvent("change", { detail: { kind, source } }));
  }

  add(mood, saved = false) {
    const id = nextId++;
    this.entries.set(id, {
      id, mood: clone(mood), saved: saved ? clone(mood) : null, savedName: saved ? mood.name : null,
      undo: [], redo: [], lastKey: null, lastTime: 0,
    });
    return id;
  }

  setContext(patch) {
    Object.assign(this.ctx, patch);
    this.emit("context");
  }

  // ------------------------------------------------------------ queries
  list() {
    const byName = new Map([...this.entries.values()].map((e) => [e.mood, e]));
    return sortMoods([...byName.keys()]).map((m) => byName.get(m));
  }

  moods() {
    return [...this.entries.values()].map((e) => e.mood);
  }

  get current() {
    return this.entries.get(this.selection.id) || null;
  }

  get variant() {
    return this.selection.variant;
  }

  byName(name) {
    return [...this.entries.values()].find((e) => e.mood.name === name) || null;
  }

  isDirty(entry) {
    return !entry.saved || entry.savedName !== entry.mood.name || !equal(entry.saved, entry.mood);
  }

  dirtyEntries() {
    return this.list().filter((e) => this.isDirty(e));
  }

  /** Schema errors for the whole working set (cached until the next edit). */
  errors() {
    if (!this._errors) {
      try {
        this._errors = validate(this.moods(), this.ctx);
      } catch (err) {
        this._errors = [String(err.message || err)];
      }
    }
    return this._errors;
  }

  errorsFor(entry) {
    const name = entry.mood.name || "<unnamed>";
    return this.errors().filter((e) => e.startsWith(`${name}:`) || e.startsWith(`${name}.`) || (e.startsWith("more than one") && entry.mood.default));
  }

  // ------------------------------------------------------------ selection
  select(id, variant = null, source) {
    const entry = this.entries.get(id);
    if (!entry) return;
    if (variant != null && !entry.mood.variants?.[variant]) variant = null;
    if (this.selection.id === id && this.selection.variant === variant) return;
    this.selection = { id, variant };
    this.track = { part: null, stops: [] };
    this.emit("select", source);
  }

  selectTrack(part, stops = [], source = "timeline") {
    this.track = { part, stops };
    this.emit("track", source);
  }

  selectVariant(variant, source) {
    this.select(this.selection.id, variant, source);
  }

  // ------------------------------------------------------------ edits
  /**
   * Apply `fn(draft, scope)` to a copy of the selected mood; `scope` is the selected variant (created
   * on demand) or the mood. Edits sharing `key` within a short window collapse into one undo step.
   */
  edit(fn, { key = null, source = "inspector", entry = this.current } = {}) {
    if (!entry) return false;
    const before = entry.mood;
    const draft = clone(before);
    const variant = entry === this.current ? this.selection.variant : null;
    fn(draft, variant == null ? draft : scopeOf(draft, variant, true));
    prune(draft);
    if (equal(draft, before)) return false;
    const now = performance.now();
    if (!(key && entry.lastKey === key && now - entry.lastTime < COALESCE_MS)) {
      entry.undo.push(before);
      if (entry.undo.length > HISTORY) entry.undo.shift();
    }
    entry.redo = [];
    entry.lastKey = key;
    entry.lastTime = now;
    entry.mood = draft;
    if (variant != null && !draft.variants?.[variant]) this.selection.variant = null;
    this.emit("edit", source);
    return true;
  }

  /** Ends undo coalescing (e.g. on pointerup), so the next edit starts a new step. */
  commit(entry = this.current) {
    if (entry) entry.lastKey = null;
  }

  replace(entry, mood, source) {
    entry.undo.push(entry.mood);
    entry.redo = [];
    entry.lastKey = null;
    entry.mood = clone(mood);
    this.fixVariant();
    this.emit("edit", source);
  }

  undo(entry = this.current) {
    if (!entry?.undo.length) return;
    entry.redo.push(entry.mood);
    entry.mood = entry.undo.pop();
    entry.lastKey = null;
    this.fixVariant();
    this.emit("history");
  }

  redo(entry = this.current) {
    if (!entry?.redo.length) return;
    entry.undo.push(entry.mood);
    entry.mood = entry.redo.pop();
    entry.lastKey = null;
    this.fixVariant();
    this.emit("history");
  }

  fixVariant() {
    const e = this.current;
    if (e && this.selection.variant != null && !variantKeys(e.mood).includes(this.selection.variant)) this.selection.variant = null;
  }

  // ------------------------------------------------------------ list changes
  create(mood) {
    const id = this.add(prune(mood), false);
    this.selection = { id, variant: null };
    this.track = { part: null, stops: [] };
    this.emit("list");
    return id;
  }

  drop(entry) {
    this.entries.delete(entry.id);
    if (this.selection.id === entry.id) {
      const next = this.list().find((e) => e.mood.default) || this.list()[0];
      this.selection = { id: next?.id ?? null, variant: null };
      this.track = { part: null, stops: [] };
    }
    this.emit("list");
  }

  markSaved(entry) {
    entry.saved = clone(entry.mood);
    entry.savedName = entry.mood.name;
    this.emit("saved");
  }
}
