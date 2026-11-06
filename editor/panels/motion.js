// Motion (v1 form): one animation per rig part, mood-local keyframes and the raw CSS escape hatch.
// Hand tracks (arm-l / arm-r stops) are summarised here and edited in the timeline.

import { clone, motionOf, motionSummary, scopeOf, trackFor, uniqueName } from "../model.js";
import { field, h, section, select } from "../ui.js";
import { originBadge, resetBtn } from "./pose.js";

const EASINGS = ["ease-in-out", "ease", "ease-in", "ease-out", "linear", "steps(3)", "cubic-bezier(.34,1.5,.64,1)"];
const DIRECTIONS = [["", "normal"], ["alternate", "alternate"], ["reverse", "reverse"], ["alternate-reverse", "alt-reverse"]];
const TIME_RE = /^-?(\d+|\d*\.\d+)m?s$/;

function keyframeOptions(api) {
  const local = Object.keys(api.mood.keyframes || {});
  const lib = Object.keys(api.ctx.keyframes);
  const groups = [];
  if (local.length) groups.push({ group: `This mood (${api.mood.name}-…)`, options: local });
  groups.push({ group: "Library (_keyframes.json)", options: lib });
  return groups;
}

function suggestKeyframes(api, part) {
  const lib = Object.keys(api.ctx.keyframes);
  const stem = part.replace(/\.[uf]$/, "").replace(/-[lr]$/, "");
  return lib.find((k) => k.startsWith(stem)) || (part.startsWith("arm") ? "arm-idle" : lib[0]);
}

function animFields(api, part, m) {
  const set = (k, v) => api.edit((_, scope) => {
    const cur = scope.motion[part];
    if (v === "" || v == null) delete cur[k];
    else cur[k] = v;
  });
  const timeIn = (k, placeholder) => h("input.time", {
    type: "text", value: m[k] ?? "", placeholder, dataset: { k: `${part}-${k}` }, spellcheck: "false",
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
  const isLocal = m.keyframes in (api.mood.keyframes || {});
  const copyBtn = !isLocal && m.keyframes in api.ctx.keyframes
    ? h("button.mini", {
      type: "button", title: "Copy these library keyframes into the mood so they can be changed here",
      onclick: () => api.edit((draft, scope) => {
        const name = uniqueName(m.keyframes, new Set([...Object.keys(draft.keyframes || {}), ...Object.keys(api.ctx.keyframes)]));
        (draft.keyframes ??= {})[name] = clone(api.ctx.keyframes[m.keyframes]);
        scope.motion[part].keyframes = name;
      }),
    }, "make local")
    : null;
  return h("div.anim-grid", {},
    h("label.field.span3", {}, h("span.field-label", {}, "Keyframes", isLocal ? h("span.pill.tiny", {}, "local") : null), h("div.inline", {},
      select(keyframeOptions(api), m.keyframes, { dataset: { k: `${part}-kf` }, onchange: (e) => set("keyframes", e.target.value) }),
      copyBtn)),
    field("Duration", timeIn("duration", ".5s")),
    field("Delay", timeIn("delay", "0s")),
    field("Easing", h("input.time", {
      type: "text", value: m.easing ?? "", list: "easings", placeholder: "ease", dataset: { k: `${part}-easing` }, spellcheck: "false",
      onchange: (e) => set("easing", e.target.value.trim()),
    })),
    field("Direction", select(DIRECTIONS, m.direction ?? "", { dataset: { k: `${part}-dir` }, onchange: (e) => set("direction", e.target.value) })),
    field("Iterations", h("input.time", {
      type: "text", value: m.iterations ?? "", placeholder: "infinite", dataset: { k: `${part}-iter` }, spellcheck: "false",
      onchange: (e) => set("iterations", e.target.value.trim()),
    })));
}

function partCard(api, part, label) {
  const { mood, variant, ctx } = api;
  const scope = scopeOf(mood, variant);
  const own = scope.motion?.[part];
  const eff = motionOf(mood, variant, ctx, part);
  const side = part.startsWith("arm-") ? part[4] : null;
  const track = side ? trackFor(mood, variant, side) : null;
  const ownTrack = side && scope.motion?.[`arm-${side}`] !== undefined;
  const mode = own === undefined ? "inherit" : own === "none" ? "none" : "animate";
  const setMode = (next) => api.edit((_, s) => {
    s.motion ??= {};
    if (next === "inherit") delete s.motion[part];
    else if (next === "none") s.motion[part] = "none";
    else {
      const base = eff.value && eff.value !== "none" && !eff.value.stops ? clone(eff.value) : null;
      s.motion[part] = base || { keyframes: suggestKeyframes(api, part), duration: "1s", easing: "ease-in-out" };
    }
  });
  const inheritedText = track && own === undefined
    ? `hand track (${track.from === "variant" || (variant == null && track.from === "mood") ? "this scope" : "base"})`
    : motionSummary(eff.value);
  return h("div.part", { class: [mode !== "inherit" ? "own" : "", ownTrack ? "disabled" : ""].join(" ") },
    h("div.row-head", {},
      h("strong.mono", { title: ctx.rig.parts[part]?.label }, part),
      h("span.muted.ellipsis", { title: ctx.rig.parts[part]?.label }, label),
      h("span.grow"),
      ownTrack
        ? h("span.muted.nowrap", {}, "driven by hand track")
        : select([["inherit", "inherit"], ["none", "none"], ["animate", "animate"]], mode, {
          class: "mode", dataset: { k: `${part}-mode` }, onchange: (e) => setMode(e.target.value),
          title: "inherit = keep the " + (variant == null ? "idle motion from _defaults.json" : "base mood's motion"),
        })),
    mode === "inherit" && !ownTrack ? h("div.inherited", {}, originBadge(eff.from ?? "defaults", variant), inheritedText) : null,
    mode === "animate" ? animFields(api, part, own) : null);
}

function trackCard(api, side) {
  const { mood, variant } = api;
  const key = `arm-${side}`;
  const scope = scopeOf(mood, variant);
  const own = scope.motion?.[key];
  const t = trackFor(mood, variant, side);
  if (!t) return null;
  const m = t.value;
  const ownHere = own !== undefined;
  return h("div.part.track", { class: ownHere ? "own" : "" },
    h("div.row-head", {},
      h("strong.mono", {}, key),
      h("span.muted", {}, `${side === "l" ? "Left" : "Right"} hand track`),
      h("span.grow"),
      ownHere ? h("button.mini.danger", {
        type: "button", title: "Remove this hand track",
        onclick: () => {
          if (confirm(`Remove the ${key} hand track (${m === "none" ? "none" : `${m.stops?.length} stops`})?`)) {
            api.edit((_, s) => { delete s.motion[key]; });
          }
        },
      }, "remove") : originBadge("mood", variant)),
    h("div.inherited", {}, motionSummary(m), m.easing ? ` · ${m.easing}` : "", m.delay ? ` · delay ${m.delay}` : ""),
    m.stops ? h("div.stops", {}, m.stops.map((s) => h("span.stop", {
      title: s.hand ? `hand [${s.hand.join(", ")}]` : `angles [${s.angles?.join(", ")}]`,
    }, `${[].concat(s.t).join("/")}%`))) : null,
    h("p.note", {}, ownHere ? "Edit its stops in the timeline below the preview (Track tab)." : "Inherited from the base mood; re-solved for this variant's pose when it moves the arm."));
}

function localKeyframes(api) {
  const { mood, edit } = api;
  const entries = Object.entries(mood.keyframes || {});
  const add = () => {
    const name = prompt("Name for the new mood-local keyframes (emitted as <mood>-<name>):", "move");
    if (!name) return;
    if (!/^[a-z][a-z0-9-]*$/.test(name)) return alert("Use lowercase letters, digits and dashes.");
    edit((d) => {
      (d.keyframes ??= {})[name] = [{ t: [0, 100], transform: "rotate(0)" }, { t: 50, transform: "rotate(5deg)" }];
    });
  };
  return section("Mood keyframes", {
    tools: h("button.mini", { type: "button", onclick: add }, "+ new"),
  },
  entries.length ? null : h("p.note", {}, "None. Use “make local” on a part to copy library keyframes here."),
  entries.map(([name, stops]) => {
    const err = h("div.field-error");
    const used = JSON.stringify([mood.motion, mood.variants]).includes(`"keyframes":"${name}"`);
    return h("div.kf", {},
      h("div.row-head", {},
        h("strong.mono", {}, name), h("span.muted.mono", {}, `@keyframes ${mood.name}-${name}`), h("span.grow"),
        h("button.mini.danger", {
          type: "button", disabled: used, title: used ? "Still used by a part" : "Delete",
          onclick: () => edit((d) => { delete d.keyframes[name]; }),
        }, "delete")),
      h("textarea.mono", {
        rows: Math.min(8, stops.length + 1), spellcheck: "false", dataset: { k: `kf-${name}` },
        value: stops.map((s) => JSON.stringify(s)).join(",\n"),
        onchange: (e) => {
          try {
            const next = JSON.parse(`[${e.target.value}]`);
            edit((d) => { d.keyframes[name] = next; });
          } catch (ex) {
            err.textContent = ex.message;
          }
        },
      }), err);
  }));
}

export const motionPanel = {
  id: "motion",
  label: "Motion",
  render(el, api) {
    const { mood, variant, ctx, edit } = api;
    const scope = scopeOf(mood, variant);
    el.append(h("datalist", { id: "easings" }, EASINGS.map((e) => h("option", { value: e }))));
    const tracks = ["l", "r"].map((s) => trackCard(api, s)).filter(Boolean);
    if (tracks.length) el.append(section("Hand tracks", { tools: h("span.muted", {}, "edit in the timeline") }, tracks));
    el.append(section("Parts", {
      tools: h("span.muted", {}, variant == null ? "inherit = idle from _defaults.json" : "inherit = base mood"),
    }, Object.entries(ctx.rig.parts).map(([part, p]) => partCard(api, part, p.label))));
    el.append(localKeyframes(api));
    el.append(section(`Raw CSS (${variant == null ? "mood" : `variant ${variant}`})`, {
      tools: resetBtn(() => edit((_, s) => { delete s.css; }), !!scope.css, "Clear"),
    },
    h("textarea.mono", {
      rows: 3, spellcheck: "false", dataset: { k: "css" }, value: scope.css ?? "",
      placeholder: "& .dot { animation-duration: .6s; }   (& = this mood's root selector)",
      onchange: (e) => edit((_, s) => { s.css = e.target.value; }),
    }),
    h("p.note", {}, "Escape hatch for what the schema can't express; not visual.")));
  },
};
