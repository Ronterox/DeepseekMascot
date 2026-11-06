// Track: the timeline selection — track timing, tools (mirror, convert, make local) and the selected stop(s).

import { easingField } from "../easing.js";
import { motionSummary, num } from "../model.js";
import {
  addStop, convertToHand, deleteStops, duplicateStops, editStop, ensureEditable, HAND_TRACKS, keyframeUsers, loopMs,
  makeLocal, mirrorTrack, overrideHere, removeTrack, rows, setStopT, setTiming, splitStop, trackInfo,
} from "../timeline/actions.js";
import { counterpart, diamonds, fmtTime, formatTransform, localAt, parseTransform, ts } from "../timeline/model.js";
import { field, h, section, select } from "../ui.js";

const TIME_RE = /^-?(\d+|\d*\.\d+)m?s$/;
const DIRECTIONS = [["", "normal"], ["alternate", "alternate"], ["reverse", "reverse"], ["alternate-reverse", "alt-reverse"]];
const FIELDS = [["tx", "Move X", "px"], ["ty", "Move Y", "px"], ["rot", "Rotate", "°"], ["sx", "Scale X", "×"], ["sy", "Scale Y", "×"]];
const GROUP_OF = { tx: "t", ty: "t", rot: "r", sx: "s", sy: "s" };
let half = true;

function timingSection(api, info) {
  const { store } = api;
  const part = info.part;
  const L = loopMs(store);
  if (!info.own) return section("Timing", h("p.note", {}, motionSummary(info.m)));
  const set = (k, v, opts) => setTiming(store, part, k, v, opts);
  const time = (k, placeholder) => h("input.time", {
    type: "text", value: info.m[k] ?? "", placeholder, spellcheck: "false", dataset: { k: `tr-${k}` },
    onchange: (e) => {
      const v = e.target.value.trim();
      if (v && !TIME_RE.test(v)) {
        e.target.setCustomValidity("CSS time, e.g. .5s or -250ms");
        e.target.reportValidity();
        return;
      }
      if (k === "duration" && !v) return;
      set(k, v);
    },
  });
  const fit = (n) => h("button.mini", { type: "button", title: n === 1 ? "Duration = the mood loop" : `Duration = mood loop / ${n}`, onclick: () => set("duration", fmtTime(Math.round(L / n))) }, n === 1 ? "1×" : n === 2 ? "½" : "¼");
  return section("Timing", { tools: h("span.muted", {}, `loop ${num(L / 1000)}s`) },
    h("div.grid2", {},
      field("Duration", h("div.inline", {}, time("duration", "1s"), fit(1), fit(2), fit(4))),
      field("Delay (drag the flag ▸)", time("delay", "0s")),
      field("Direction", select(DIRECTIONS, info.m.direction ?? "", { dataset: { k: "tr-dir" }, onchange: (e) => set("direction", e.target.value) })),
      field("Iterations", h("input.time", {
        type: "text", value: info.m.iterations ?? "", placeholder: "infinite", spellcheck: "false", dataset: { k: "tr-iter" },
        onchange: (e) => set("iterations", e.target.value.trim()),
      }))),
    field("Easing (per segment, unless a stop sets its own)", easingField({
      value: info.m.easing ?? "", inherit: "ease", k: "tr-easing",
      onchange: (v, { live, end }) => {
        set("easing", v, live ? { key: `ease-${part}`, source: "live" } : {});
        if (end) {
          store.commit();
          api.rerender();
        }
      },
    }), { wide: true }));
}

function toolsSection(api, info) {
  const { store, preview, mood } = api;
  const part = info.part;
  const tools = [];
  if (!info.own) {
    tools.push(h("button.mini", { type: "button", onclick: () => overrideHere(store, part), title: "Copy this motion into the selected scope to edit it" }, `Override in this ${store.variant == null ? "mood" : "variant"}`));
  } else if (info.kind === "kf" && !info.local) {
    tools.push(h("button.mini", { type: "button", onclick: () => makeLocal(store, part), title: "Copy the library keyframes into this mood (moods/_keyframes.json stays untouched)" }, "Make local copy"));
  }
  const twin = counterpart(part);
  if (twin !== part && info.kind !== "none") {
    tools.push(h("span.inline", {},
      h("button.mini", {
        type: "button", title: `Copy to ${twin} with mirrored values`,
        onclick: () => {
          const t = mirrorTrack(store, preview, part, half);
          if (t) store.selectTrack(t, []);
        },
      }, `Mirror → ${twin}`),
      h("label.check.small", { title: "Shift the copy by half its duration (alternating sides, like dance)" },
        h("input", { type: "checkbox", checked: half, onchange: (e) => { half = e.target.checked; } }), "½ offset")));
  }
  const side = /^arm-([lr])(\.[uf])?$/.exec(part)?.[1];
  if (side && !HAND_TRACKS.includes(part) && info.kind === "kf") {
    tools.push(h("button.mini", {
      type: "button", title: "Replace this arm's upper/fore keyframes with an equivalent hand-stop track",
      onclick: () => {
        if (convertToHand(store, side)) store.selectTrack(`arm-${side}`, []);
      },
    }, `Convert arm-${side} to hand track`));
  }
  if (info.own) {
    tools.push(h("button.mini.danger", {
      type: "button",
      onclick: () => {
        if (confirm(`Remove the ${part} track from this ${store.variant == null ? "mood" : "variant"}?`)) {
          removeTrack(store, part);
          store.selectTrack(null, []);
        }
      },
    }, "Remove track"));
  }
  const notes = [];
  if (info.kind === "kf" && info.local) {
    const users = keyframeUsers(mood, info.name);
    notes.push(h("p.note", {}, "Keyframes ", h("code", {}, info.name), ` (@keyframes ${mood.name}-${info.name})`,
      users.length > 1 ? ` — shared with ${users.filter((u) => u !== part).join(", ")}` : ""));
  } else if (info.kind === "kf") {
    notes.push(h("p.note", {}, "Library keyframes ", h("code", {}, info.name), " are read-only here."));
  }
  if (info.kind === "hand") notes.push(h("p.note", {}, "Drag the preview's hand handle: on a stop it moves that stop, elsewhere it adds one at the playhead."));
  return section(`${info.part}`, { tools: h("span.muted", {}, info.kind === "hand" ? "hand track" : info.kind === "kf" ? "keyframes" : "none") },
    h("div.tool-row", {}, tools), notes);
}

function stopFields(api, info, d) {
  const { store } = api;
  const part = info.part;
  const stop = info.stops[d.i];
  const ro = !info.editable;
  const shared = ts(stop).length > 1;
  const live = (k) => ({ key: `stop-${part}-${d.i}-${k}`, source: "live" });
  const out = [];
  out.push(h("div.grid3", {},
    field("At %", h("input.num", {
      type: "number", step: "0.1", min: 0, max: 100, value: d.t, disabled: ro, dataset: { k: "st-t" },
      onchange: (e) => {
        const t = Math.max(0, Math.min(100, Number(e.target.value)));
        setStopT(store, part, d, t);
        store.selectTrack(part, [{ ...d, t }]);
      },
    })),
    shared ? h("p.note", {}, `Shared by ${ts(stop).join("%, ")}% — edits apply to all. `,
      ro ? null : h("button.mini", { type: "button", onclick: () => { const n = splitStop(store, part, d); if (n) store.selectTrack(part, [n]); } }, "split")) : null));

  if (info.kind === "hand") {
    if (stop.hand) {
      const put = (n, v) => editStop(store, part, d.i, (s) => { s.hand = n === 0 ? [v, s.hand[1]] : [s.hand[0], v]; }, live(`h${n}`).key, "live");
      out.push(h("div.grid3", {},
        field("Hand X", h("input.num", { type: "number", step: "any", value: stop.hand[0], disabled: ro, dataset: { k: "st-hx" }, oninput: (e) => e.target.value !== "" && put(0, Number(e.target.value)), onchange: () => api.rerender() })),
        field("Hand Y", h("input.num", { type: "number", step: "any", value: stop.hand[1], disabled: ro, dataset: { k: "st-hy" }, oninput: (e) => e.target.value !== "" && put(1, Number(e.target.value)), onchange: () => api.rerender() })),
        h("label.check", {}, h("input", {
          type: "checkbox", checked: stop.elbowOut !== false, disabled: ro, dataset: { k: "st-elbow" },
          onchange: (e) => editStop(store, part, d.i, (s) => { if (e.target.checked) delete s.elbowOut; else s.elbowOut = false; }),
        }), "Elbow out")));
    } else {
      out.push(h("p.note", {}, `Angles [${stop.angles.join(", ")}] — dragging the hand turns it into a hand target.`));
    }
  } else {
    const parsed = parseTransform(stop.transform);
    if (stop.transform !== undefined && parsed) {
      out.push(h("div.tf-grid", {}, FIELDS.map(([k, label, unit]) => field(`${label} ${unit}`, h("input.num", {
        type: "number", step: k.startsWith("s") ? "0.01" : k === "rot" ? "0.5" : "1", value: parsed[k], disabled: ro, dataset: { k: `st-${k}` },
        oninput: (e) => {
          if (e.target.value === "" || !Number.isFinite(Number(e.target.value))) return;
          const cur = parseTransform(info.stops[d.i].transform) || parsed;
          const next = { ...cur, [k]: Number(e.target.value) };
          const has = { ...cur.has, [GROUP_OF[k]]: true };
          editStop(store, part, d.i, (s) => { s.transform = formatTransform(next, has); }, live(k).key, "live");
        },
        onchange: () => { store.commit(); api.rerender(); },
      })))));
    }
    out.push(field(parsed ? "transform (canonical when edited above)" : "transform (raw: not a plain translate/rotate/scale)", h("input.time", {
      type: "text", value: stop.transform ?? "", disabled: ro, spellcheck: "false", dataset: { k: "st-raw" },
      onchange: (e) => editStop(store, part, d.i, (s) => {
        if (e.target.value.trim()) s.transform = e.target.value.trim();
        else delete s.transform;
      }),
    }), { wide: true }));
    for (const [prop, value] of Object.entries(stop)) {
      if (["t", "transform", "easing"].includes(prop)) continue;
      out.push(field(prop, h("input.time", {
        type: "text", value, disabled: ro, spellcheck: "false", dataset: { k: `st-p-${prop}` },
        onchange: (e) => editStop(store, part, d.i, (s) => {
          if (e.target.value.trim()) s[prop] = e.target.value.trim();
          else delete s[prop];
        }),
      }), { wide: true, hint: "Empty removes the property" }));
    }
    if (!ro && !("opacity" in stop)) {
      out.push(h("button.mini", { type: "button", onclick: () => editStop(store, part, d.i, (s) => { s.opacity = "1"; }) }, "+ opacity"));
    }
  }
  out.push(field("Easing from this stop", easingField({
    value: stop.easing ?? "", inherit: `track (${info.m.easing || "ease"})`, inheritValue: info.m.easing || "ease", k: "st-easing",
    onchange: (v, { live: isLive, end }) => {
      if (ro) return;
      editStop(store, part, d.i, (s) => {
        if (v) s.easing = v;
        else delete s.easing;
      }, isLive ? `stop-ease-${part}-${d.i}` : null, isLive ? "live" : undefined);
      if (end) {
        store.commit();
        api.rerender();
      }
    },
  }), { wide: true }));
  return out;
}

function stopsSection(api, info) {
  const { store, preview } = api;
  const part = info.part;
  if (info.kind === "none") return null;
  const valid = new Set(diamonds(info.stops).map((d) => `${d.i}:${d.j}`));
  const sel = store.track.stops.filter((d) => valid.has(`${d.i}:${d.j}`));
  const atPlayhead = () => localAt(preview.time(), info.tm);
  const addBtn = h("button.mini", {
    type: "button", title: "Add a stop at the playhead with the current value (K)",
    onclick: () => {
      if (!ensureEditable(store, part)) return;
      const at = atPlayhead();
      const d = addStop(store, part, at.t);
      if (d) store.selectTrack(part, [d]);
    },
  }, "+ stop at playhead");
  const tools = h("span.inline", {},
    addBtn,
    sel.length && info.editable ? h("button.mini", {
      type: "button", title: "Copy the selected stop(s) to the playhead",
      onclick: () => store.selectTrack(part, duplicateStops(store, part, sel, atPlayhead().t)),
    }, "duplicate") : null,
    sel.length && info.editable ? h("button.mini.danger", {
      type: "button", title: "Delete (Del)",
      onclick: () => { if (deleteStops(store, part, sel)) store.selectTrack(part, []); },
    }, "delete") : null);
  let body;
  if (!sel.length) body = h("p.note", {}, `${diamonds(info.stops).length} stops. Click a diamond (Shift: add to selection), drag to move, double-click a lane or press K to add.`);
  else if (sel.length > 1) body = h("p.note", {}, `${sel.length} stops selected (${sel.map((d) => `${d.t}%`).join(", ")}). Drag any of them to move all.`);
  else body = stopFields(api, info, sel[0]);
  return section(sel.length === 1 ? `Stop at ${sel[0].t}%` : "Stops", { tools }, body,
    info.editable ? null : h("p.note", {}, "Read-only: override / make a local copy above to edit."));
}

export const trackPanel = {
  id: "track",
  label: "Track",
  render(el, api) {
    const { store } = api;
    const part = store.track.part;
    const info = part && trackInfo(store, part);
    if (!info) {
      const list = rows(store, false);
      el.append(section("Timeline",
        h("p.note", {}, "Select a row in the timeline below the preview. Space plays, ←/→ step, K adds a stop, Del deletes."),
        list.length ? h("div.tool-row", {}, list.map((r) => h("button.mini", { type: "button", onclick: () => store.selectTrack(r.part, []) }, r.part))) : null));
      return;
    }
    el.append(toolsSection(api, info));
    if (info.tm) el.append(timingSection(api, info));
    const stops = stopsSection(api, info);
    if (stops) el.append(stops);
  },
};
