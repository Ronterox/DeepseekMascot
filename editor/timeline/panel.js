// Timeline panel (below the preview): a row per animated part of the selected mood/variant on one
// time axis (the mood loop), keyframe diamonds, playhead/scrubbing, delay flags, beat grid, and the
// hand-track link to the preview's hand handles.

import { motionSummary, num } from "../model.js";
import { debounceFrame, h, select } from "../ui.js";
import {
  addStop, addTrack, beatMs, deleteStops, dragHandStop, ensureEditable, gridStep, HAND_TRACKS, loopMs, moveStops,
  partOrder, periodReport, rows, setBeat, setTiming, snapT, trackInfo,
} from "./actions.js";
import { BAKE_FPS, cycles, diamonds, evalHand, fmtTime, handPath, localAt, normDelay, round1, timeOf } from "./model.js";
import { resolvePose } from "../../tools/moods.mjs";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const typingTarget = (el) => el && (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) || el.isContentEditable);

function tFromTime(time, k, tm) {
  const p = (time - tm.delay) / tm.d - k;
  return timeOf(100, k, tm) >= timeOf(0, k, tm) ? p * 100 : (1 - p) * 100;
}

function niceStep(L) {
  for (const s of [50, 100, 200, 250, 500, 1000, 2000, 5000]) if (L / s <= 16) return s;
  return 10000;
}

export class Timeline {
  constructor(el, store, preview, { status, prefs, savePrefs }) {
    this.el = el;
    this.store = store;
    this.preview = preview;
    this.status = status;
    this.prefs = prefs;
    this.savePrefs = savePrefs;
    this.collapsed = !!prefs.tlCollapsed;
    this.height = prefs.tlHeight || 230;
    this.snap = prefs.tlSnap || "b4";
    this.loop = prefs.tlLoop !== false;
    this.inherited = !!prefs.tlInherited;
    this.half = true;
    this.handInfo = {};
    this.drags = 0;
    this.render = debounceFrame(() => this.draw());
    store.on("change", () => this.render());
    preview.onPlayState(() => this.updatePlay());
    document.addEventListener("keydown", (e) => this.keys(e));
    el.hidden = false;
    requestAnimationFrame(() => this.tick());
  }

  pref(key, value) {
    this.prefs[key] = value;
    this.savePrefs();
  }

  // ------------------------------------------------------------ drawing
  draw() {
    const { store } = this;
    const entry = store.current;
    this.el.classList.toggle("collapsed", this.collapsed);
    this.el.style.height = this.collapsed ? "" : `${this.height}px`;
    if (!entry) {
      this.el.replaceChildren();
      return;
    }
    const L = (this.L = loopMs(store));
    this.rowsList = rows(store, this.inherited);
    this.pruneSelection();
    const body = this.collapsed ? null : this.body(L);
    this.el.replaceChildren(
      h("div.tl-resize", { title: "Drag to resize the timeline", onpointerdown: (e) => this.resize(e) }),
      this.header(L),
      ...(body ? [body] : []),
    );
    this.prepareHands();
    this.updatePlay();
    // After the pose/opacity transitions (<= .7s) have settled, like the bake's settle().
    clearTimeout(this.periodTimer);
    this.periodTimer = setTimeout(() => this.updatePeriod(), 800);
  }

  pruneSelection() {
    const { part, stops } = this.store.track;
    if (!part) return;
    const info = trackInfo(this.store, part);
    const valid = new Set(diamonds(info?.stops).map((d) => `${d.i}:${d.j}`));
    const keep = stops.filter((d) => valid.has(`${d.i}:${d.j}`));
    if (keep.length !== stops.length) this.store.track = { part: info ? part : null, stops: keep };
  }

  header(L) {
    const { store } = this;
    const ed = store.current.mood.meta?.editor || {};
    const beat = beatMs(store);
    const own = new Set(this.rowsList.filter((r) => r.own).map((r) => r.part));
    const free = partOrder(store.ctx.rig).filter((p) => !own.has(p));
    const beatIn = (k, value, placeholder, title) => h("input.num.tl-num", {
      type: "number", min: "1", step: "1", value: value ?? "", placeholder, title, dataset: { k },
      onchange: () => {
        const bpm = Number(this.el.querySelector('[data-k="tl-bpm"]').value);
        const counts = Number(this.el.querySelector('[data-k="tl-counts"]').value);
        setBeat(store, bpm, counts);
      },
    });
    this.playBtn = h("button.tool", { type: "button", title: "Play / pause (Space)", onclick: () => this.preview.setPaused(!this.preview.paused) });
    this.readout = h("span.tl-time.mono");
    this.periodBadge = h("span.tl-period", {});
    return h("div.tl-head", {},
      this.playBtn,
      h("button.tool", {
        type: "button", class: this.loop ? "on" : "", title: "Loop playback over the mood loop (off: free-running, like the page)",
        onclick: () => { this.loop = !this.loop; this.pref("tlLoop", this.loop); this.render(); },
      }, "⟳"),
      this.readout,
      h("span.sep"),
      h("label.mini-field", { title: "Beats per minute and loop length in counts (stored as meta.editor; editor only)" }, "bpm",
        beatIn("tl-bpm", ed.bpm, "–", "BPM"), "×", beatIn("tl-counts", ed.counts, "–", "Counts per loop")),
      h("label.mini-field", { title: "Snap stops and delays to this grid" }, select([
        ["off", "off"], ["pct1", "1%"], ["pct5", "5%"],
        ...(beat ? [["b1", "1 count"], ["b2", "½ count"], ["b4", "¼ count"], ["b8", "⅛ count"]] : []),
      ], beat || !this.snap.startsWith("b") ? this.snap : "pct1", {
        dataset: { k: "tl-snap" }, onchange: (e) => { this.snap = e.target.value; this.pref("tlSnap", this.snap); },
      })),
      select([["", "+ track…"], { group: "Hand tracks (IK stops)", options: free.filter((p) => HAND_TRACKS.includes(p)).map((p) => [p, `${p} (hand)`]) },
        { group: "Keyframe tracks", options: free.filter((p) => !HAND_TRACKS.includes(p)) }], "", {
        class: "tl-add", dataset: { k: "tl-add" }, title: "Add a track for a rig part",
        onchange: (e) => {
          const part = e.target.value;
          e.target.value = "";
          if (part && addTrack(store, part, L)) store.selectTrack(part, []);
        },
      }),
      h("label.check.small", { title: "Also show inherited (read-only) motion" },
        h("input", { type: "checkbox", checked: this.inherited, onchange: (e) => { this.inherited = e.target.checked; this.pref("tlInherited", this.inherited); this.render(); } }),
        "inherited"),
      h("span.grow"),
      this.periodBadge,
      h("button.icon-btn", {
        type: "button", title: this.collapsed ? "Show the timeline" : "Collapse the timeline",
        onclick: () => { this.collapsed = !this.collapsed; this.pref("tlCollapsed", this.collapsed); this.render(); },
      }, this.collapsed ? "▴" : "▾"));
  }

  body(L) {
    const beat = beatMs(this.store);
    const step = niceStep(L);
    const ruler = h("div.tl-lane.tl-ruler", { onpointerdown: (e) => this.scrub(e) });
    for (let t = 0; t <= L + 1; t += step) {
      ruler.append(h("span.tl-tick", { style: { left: `${(t / L) * 100}%` } }, h("b", {}, `${num(t / 1000)}s`)));
    }
    const grid = h("div.tl-grid");
    if (beat) {
      for (let b = 0, n = 0; b <= L + 1; b += beat, n++) {
        grid.append(h("span.tl-beat", { class: n % 4 === 0 ? "bar" : "", style: { left: `${(b / L) * 100}%` } }));
        if (b < L - 1) ruler.append(h("span.tl-count", { style: { left: `${(b / L) * 100}%` } }, String(n + 1)));
      }
    }
    this.ph = h("div.tl-ph");
    const content = h("div.tl-content", {},
      h("div.tl-row.tl-ruler-row", {},
        h("div.tl-label.muted", { title: "The mood loop: bpm × counts, or the longest track" }, `loop ${num(L / 1000)}s`), ruler),
      this.rowsList.length ? this.rowsList.map((r) => this.row(r, L)) : h("p.tl-empty", {},
        "No motion of its own in this scope. Add a track with “+ track…”, or tick “inherited” to see the idle motion."),
      grid, this.ph);
    return h("div.tl-body", {}, content);
  }

  row(info, L) {
    const { store } = this;
    const sel = store.track.part === info.part;
    const selected = new Set(sel ? store.track.stops.map((d) => `${d.i}:${d.j}`) : []);
    const lane = h("div.tl-lane", {
      dataset: { part: info.part },
      onpointerdown: (e) => this.lanePointer(e, info),
      ondblclick: (e) => this.laneDouble(e, info),
    });
    if (info.kind === "none") {
      lane.append(h("span.tl-none", {}, "none (stopped)"));
    } else {
      const { tm } = info;
      const ds = diamonds(info.stops);
      for (const k of cycles(tm, L)) {
        const s = tm.delay + k * tm.d;
        const a = clamp(s, 0, L);
        const b = clamp(s + tm.d, 0, L);
        lane.append(h("span.tl-cyc", { class: k % 2 ? "odd" : "", style: { left: `${(a / L) * 100}%`, width: `${((b - a) / L) * 100}%` } }));
        if (s >= 0 && s < L && info.own) {
          lane.append(h("span.tl-flag", { dataset: { k }, style: { left: `${(s / L) * 100}%` }, title: `Cycle start: drag to change the delay (${info.m.delay || "0s"})` }));
        }
        for (const d of ds) {
          const time = timeOf(d.t, k, tm);
          if (time < -0.5 || time > L + 0.5) continue;
          lane.append(h("span.tl-d", {
            class: [selected.has(`${d.i}:${d.j}`) ? "sel" : "", info.editable ? "" : "ro", Array.isArray(info.stops[d.i].t) ? "shared" : "", info.stops[d.i].easing ? "eased" : ""].join(" "),
            dataset: { i: d.i, j: d.j, k, t: d.t },
            style: { left: `${(time / L) * 100}%` },
            title: `${d.t}%${info.stops[d.i].hand ? ` · hand [${info.stops[d.i].hand.join(", ")}]` : info.stops[d.i].transform ? ` · ${info.stops[d.i].transform}` : ""}`,
          }));
        }
      }
    }
    const kind = info.kind === "hand" ? "✋" : info.kind === "kf" ? "◆" : "–";
    const tag = !info.own ? h("span.tl-tag", { title: `Inherited from ${info.from}` }, info.from === "defaults" ? "idle" : "base")
      : info.kind === "kf" && !info.local ? h("span.tl-tag.lib", { title: `Library keyframes "${info.name}" (make a local copy to edit)` }, "lib") : null;
    return h("div.tl-row", { class: [sel ? "sel" : "", info.own ? "" : "inh"].join(" ") },
      h("div.tl-label", {
        title: `${info.part}: ${motionSummary(info.m)}`,
        onclick: () => store.selectTrack(info.part, []),
      },
      h("span.tl-kind", {}, kind),
      h("strong.mono", {}, info.part),
      tag,
      h("span.grow"),
      info.tm ? h("span.muted.mono.small", {}, info.m.duration) : null),
      lane);
  }

  updatePlay() {
    if (!this.playBtn) return;
    this.playBtn.textContent = this.preview.paused ? "▶" : "❚❚";
    this.playBtn.classList.toggle("on", this.preview.paused);
  }

  updatePeriod() {
    if (!this.periodBadge || !this.store.current) return;
    let rep;
    try {
      rep = periodReport(this.store, this.preview);
    } catch (err) {
      console.warn(err);
      return;
    }
    const warn = !rep.loopOk || rep.retimed.length;
    const lines = [
      `Desktop bake loop: ${num(rep.period / 1000)}s (${rep.frames} frames @ ${BAKE_FPS} fps), picked like choose_period() in desktop/bake.py`,
      `from the visible animation durations: ${rep.durations.map((d) => `${num(d / 1000)}s`).join(", ")}`,
      `Mood loop: ${num(rep.L / 1000)}s`,
    ];
    if (rep.uneven.length) lines.push(`Not dividing the mood loop: ${rep.uneven.map((x) => `${x.part} ${num(x.d / 1000)}s`).join(", ")}`);
    if (rep.retimed.length) lines.push(`Retimed by the bake: ${rep.retimed.map((x) => `${x.part} ${num(x.d / 1000)}s → ${(x.r / 1000).toFixed(3)}s`).join(", ")}`);
    this.periodBadge.className = `tl-period${warn ? " warn" : ""}`;
    this.periodBadge.textContent = `${warn ? "⚠ " : ""}bake ${num(rep.period / 1000)}s`;
    this.periodBadge.title = lines.join("\n");
  }

  // ------------------------------------------------------------ playhead & hands
  tick() {
    requestAnimationFrame(() => this.tick());
    const { preview } = this;
    if (!this.store.current || !this.L) return;
    let T = preview.time();
    const L = this.L;
    if (this.loop && !preview.paused && T >= L) {
      T %= L;
      preview.applyTime(T);
    }
    const shown = this.loop ? Math.min(T, L) : T % L;
    if (this.ph) this.ph.style.setProperty("--f", String(shown / L));
    if (this.readout) this.readout.textContent = `${(shown / 1000).toFixed(2)} / ${num(L / 1000)}s`;
    for (const side of ["l", "r"]) {
      const hi = this.handInfo[side];
      if (!hi) continue;
      const at = localAt(T, hi.info.tm);
      const angles = evalHand(this.store.ctx.rig, side, hi.info.stops, at.t, hi.info.m.easing, hi.pose);
      const hit = diamonds(hi.info.stops).find((d) => Math.abs(d.t - at.t) < 0.6);
      preview.setTrackArm(side, { angles, path: hi.path, onStop: !!hit, target: hit ? hi.info.stops[hit.i].hand : null });
    }
  }

  /** Own hand tracks take over the preview's hand handles while the timeline is open. */
  prepareHands() {
    const { store } = this;
    for (const side of ["l", "r"]) {
      const info = this.collapsed ? null : trackInfo(store, `arm-${side}`);
      const active = info && info.kind === "hand" && info.own;
      if (active) {
        const pose = resolvePose(store.current.mood, store.ctx, store.variant)[side];
        this.handInfo[side] = { info, pose, path: handPath(store.ctx.rig, side, info.stops, info.m.easing, pose) };
      } else if (this.handInfo[side]) {
        delete this.handInfo[side];
        this.preview.setTrackArm(side, null);
      }
    }
  }

  /** Called for drags on the preview's hand handles; returns true when the timeline handled it. */
  handDrag(side, point, phase) {
    const hi = this.handInfo[side];
    if (!hi) return false;
    const part = `arm-${side}`;
    if (phase === "start") {
      this.preview.setPaused(true);
      const at = localAt(this.preview.time(), hi.info.tm);
      this.hand = { t: round1(at.t), state: {}, key: `hand-${side}-${++this.drags}` };
    }
    if (!this.hand) return true;
    if (point) dragHandStop(this.store, part, this.hand.t, point, this.hand.state, this.hand.key);
    if (phase === "end") {
      this.store.commit();
      const info = trackInfo(this.store, part);
      const i = this.hand.state.i;
      const d = diamonds(info?.stops).find((x) => x.i === i);
      if (d) this.store.selectTrack(part, [d]);
      this.hand = null;
    }
    return true;
  }

  // ------------------------------------------------------------ interaction
  timeAt(lane, clientX) {
    const r = lane.getBoundingClientRect();
    return clamp(((clientX - r.left) / r.width) * this.L, 0, this.L);
  }

  scrub(e) {
    if (e.button !== 0) return;
    e.preventDefault();
    const lane = e.currentTarget;
    this.preview.seek(this.timeAt(lane, e.clientX));
    this.follow(e, (mv) => this.preview.seek(this.timeAt(lane, mv.clientX)));
  }

  /** Window-level pointer tracking (rows are re-rendered while dragging, so no element capture). */
  follow(e, move, up) {
    const id = e.pointerId;
    const mv = (ev) => ev.pointerId === id && move(ev);
    const end = (ev) => {
      if (ev.pointerId !== id) return;
      window.removeEventListener("pointermove", mv);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      up?.(ev);
    };
    window.addEventListener("pointermove", mv);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  lanePointer(e, info) {
    if (e.button !== 0) return;
    const { store } = this;
    const lane = e.currentTarget;
    const dEl = e.target.closest(".tl-d");
    const flag = e.target.closest(".tl-flag");
    if (dEl) return this.stopPointer(e, info, lane, dEl);
    if (flag && info.own) return this.delayDrag(e, info, lane);
    store.selectTrack(info.part, []);
    this.scrub(e);
  }

  stopPointer(e, info, lane, dEl) {
    e.preventDefault();
    const { store } = this;
    const d = { i: Number(dEl.dataset.i), j: Number(dEl.dataset.j), t: Number(dEl.dataset.t) };
    const k = Number(dEl.dataset.k);
    const same = store.track.part === info.part;
    let sel = same ? store.track.stops : [];
    const has = sel.some((x) => x.i === d.i && x.j === d.j);
    if (e.shiftKey || e.ctrlKey || e.metaKey) sel = has ? sel.filter((x) => !(x.i === d.i && x.j === d.j)) : [...sel, d];
    else if (!has) sel = [d];
    store.selectTrack(info.part, sel);
    if (!info.editable) {
      this.preview.seek(timeOf(d.t, k, info.tm));
      if (!info.own || info.kind === "kf") this.status(`${info.part} is ${info.own ? "using library keyframes" : "inherited"}: use “make local” / “override” in the Track panel to edit it`);
      return;
    }
    const x0 = e.clientX;
    const width = lane.getBoundingClientRect().width;
    const orig = sel.map((x) => ({ ...x }));
    const key = `move-${info.part}-${++this.drags}`;
    const step = gridStep(store, this.snap, info.tm);
    let moved = false;
    let delta = 0;
    this.follow(e, (mv) => {
      const dx = mv.clientX - x0;
      if (!moved && Math.abs(dx) < 3) return;
      moved = true;
      const time = timeOf(d.t, k, info.tm) + (dx / width) * this.L;
      const t = snapT(clamp(tFromTime(time, k, info.tm), 0, 100), k, info.tm, step);
      delta = round1(t - d.t);
      const lo = Math.min(...orig.map((x) => x.t));
      const hi = Math.max(...orig.map((x) => x.t));
      delta = clamp(delta, -lo, 100 - hi);
      moveStops(store, info.part, orig, delta, key);
    }, () => {
      if (moved) {
        store.commit();
        store.selectTrack(info.part, orig.map((x) => ({ ...x, t: round1(x.t + delta) })));
      } else if (!(e.shiftKey || e.ctrlKey || e.metaKey)) {
        store.selectTrack(info.part, [d]);
        this.preview.seek(timeOf(d.t, k, info.tm));
      }
    });
  }

  delayDrag(e, info, lane) {
    e.preventDefault();
    const { store } = this;
    store.selectTrack(info.part, []);
    const x0 = e.clientX;
    const width = lane.getBoundingClientRect().width;
    const d0 = info.tm.delay;
    const step = gridStep(store, this.snap, info.tm);
    const key = `delay-${info.part}-${++this.drags}`;
    this.follow(e, (mv) => {
      let delay = d0 + ((mv.clientX - x0) / width) * this.L;
      if (step) delay = Math.round(delay / step) * step;
      delay = normDelay(delay, info.tm.d);
      setTiming(store, info.part, "delay", delay ? fmtTime(Math.round(delay)) : "", { key });
    }, () => store.commit());
  }

  laneDouble(e, info) {
    if (e.target.closest(".tl-d, .tl-flag") || info.kind === "none") return;
    const time = this.timeAt(e.currentTarget, e.clientX);
    const at = localAt(time, info.tm);
    if (!at.active) return;
    if (!ensureEditable(this.store, info.part)) return;
    const step = gridStep(this.store, this.snap, info.tm);
    const d = addStop(this.store, info.part, snapT(at.t, at.k, info.tm, step));
    if (d) {
      this.store.selectTrack(info.part, [d]);
      this.preview.seek(timeOf(d.t, at.k, info.tm));
    }
  }

  /** K: add a stop at the playhead on the selected row (capturing the current value). */
  addAtPlayhead() {
    const { store } = this;
    const part = store.track.part;
    if (!part) return this.status("Select a track row first (click its name)");
    if (!ensureEditable(store, part)) return;
    const info = trackInfo(store, part);
    const at = localAt(this.preview.time(), info.tm);
    if (!at.active) return this.status("The track hasn't started at the playhead (delay)");
    const d = addStop(store, part, at.t);
    if (d) store.selectTrack(part, [d]);
  }

  step(dir) {
    const info = this.store.track.part && trackInfo(this.store, this.store.track.part);
    const s = (info?.tm && gridStep(this.store, this.snap, info.tm)) || 1000 / BAKE_FPS;
    const T = this.preview.time();
    const L = this.L;
    let next = Math.round((T % L) / s + dir) * s;
    if (next < 0) next = L - s;
    if (next > L) next = 0;
    this.preview.seek(next);
  }

  keys(e) {
    if (this.collapsed || e.ctrlKey || e.metaKey || e.altKey || typingTarget(document.activeElement)) return;
    if (document.querySelector("dialog[open]")) return;
    const { store } = this;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      this.step(e.key === "ArrowLeft" ? -1 : 1);
    } else if ((e.key === "Delete" || e.key === "Backspace") && store.track.part && store.track.stops.length) {
      e.preventDefault();
      if (deleteStops(store, store.track.part, store.track.stops)) store.selectTrack(store.track.part, []);
    } else if (e.key.toLowerCase() === "k") {
      e.preventDefault();
      this.addAtPlayhead();
    } else if (e.key === "Escape" && store.track.stops.length) {
      store.selectTrack(store.track.part, []);
    }
  }

  resize(e) {
    e.preventDefault();
    const y0 = e.clientY;
    const h0 = this.height;
    this.follow(e, (mv) => {
      this.height = clamp(h0 - (mv.clientY - y0), 110, Math.round(window.innerHeight * 0.7));
      this.el.style.height = `${this.height}px`;
    }, () => this.pref("tlHeight", this.height));
  }
}
