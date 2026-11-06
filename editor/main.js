// Whale-chan mood editor: wires the store, preview, sidebar and inspector together.

import { compileCss, resolvePose } from "../tools/moods.mjs";
import { api } from "./api.js";
import { Inspector } from "./inspector.js";
import { armSpec, blankMood, duplicateMood, NAME_RE, poseVar, splitUnit } from "./model.js";
import { dragHand } from "./panels/pose.js";
import { Preview } from "./preview.js";
import { Sidebar } from "./sidebar.js";
import { Store } from "./store.js";
import { Timeline } from "./timeline/panel.js";
import { debounceFrame } from "./ui.js";

const $ = (sel) => document.querySelector(sel);
const prefs = JSON.parse(localStorage.getItem("whale-editor-prefs") || "{}");
const savePrefs = () => localStorage.setItem("whale-editor-prefs", JSON.stringify(prefs));

let statusTimer = 0;
function status(msg, kind = "info", sticky = false) {
  const el = $("#status");
  el.textContent = msg;
  el.dataset.kind = kind;
  clearTimeout(statusTimer);
  if (!sticky) statusTimer = setTimeout(() => { el.textContent = ""; }, kind === "error" ? 9000 : 3500);
}

function showLog(title, text) {
  $("#log-title").textContent = title;
  $("#log-body").textContent = text;
  $("#show-log").hidden = false;
  $("#log-dialog").showModal();
}

async function boot() {
  let state;
  let markup;
  try {
    [state, markup] = await Promise.all([api.state(), api.svg()]);
  } catch (err) {
    document.body.classList.add("boot-failed");
    status(`Can't load the editor state: ${err.message}. Is tools/editor_server.py running?`, "error", true);
    throw err;
  }
  const store = new Store(state);
  const preview = new Preview($("#preview-host"));
  preview.load(markup, store.ctx.rig);
  window.whaleEditor = { store, preview }; // handy in devtools; also the hook for v2 panels

  const sidebar = new Sidebar($("#sidebar"), store, { create: openNewDialog, remove: removeCurrent });
  const inspector = new Inspector($("#inspector"), store, preview);
  const timeline = new Timeline($("#timeline"), store, preview, { status, prefs, savePrefs });
  window.whaleEditor.timeline = timeline;

  // ------------------------------------------------------------ live preview
  let lastCss = "";
  const refresh = debounceFrame(() => {
    const entry = store.current;
    const errors = store.errors();
    let stale = errors.length > 0;
    if (!stale) {
      try {
        const css = compileCss(store.moods(), store.ctx);
        if (css !== lastCss) preview.setCss((lastCss = css));
      } catch (err) {
        stale = true;
        console.warn(err);
      }
    }
    $("#stale").hidden = !stale;
    updateButtons();
    if (!entry) return;
    const { mood } = entry;
    const variant = store.variant;
    preview.setState(mood.name, variant);
    $("#preview-state").textContent = `${mood.name}${variant != null ? ` · strain ${variant}` : ""}`;
    $("#preview-state").title = `data-mood="${mood.name}"${variant != null ? ` data-strain="${variant}"` : ""}`;
    const accent = mood.meta?.theme?.accent;
    document.documentElement.style.setProperty("--accent", accent || "#347fdb");
    try {
      const pose = resolvePose(mood, store.ctx, variant);
      const targets = {};
      for (const side of ["l", "r"]) targets[side] = armSpec(mood, variant, store.ctx, side).value?.hand || null;
      const cy = splitUnit(poseVar(mood, variant, store.ctx, "cy").value).n;
      const cs = splitUnit(poseVar(mood, variant, store.ctx, "cs").value).n || 1;
      preview.updateOverlay(pose, targets, { cy, cs });
    } catch (err) {
      console.warn(err);
    }
  });
  store.on("change", refresh);

  let dragKey = null;
  let dragN = 0;
  let dragToTimeline = false;
  preview.onDrag = (side, point, phase) => {
    if (phase === "start") dragToTimeline = timeline.handDrag(side, point, phase);
    else if (dragToTimeline) return timeline.handDrag(side, point, phase);
    if (dragToTimeline) return;
    if (phase === "start") dragKey = `drag-${side}-${++dragN}`;
    if (point) dragHand(store, side, point, dragKey);
    if (phase === "end") store.commit();
  };

  // ------------------------------------------------------------ toolbar
  function updateButtons() {
    const e = store.current;
    const dirty = store.dirtyEntries();
    $("#undo").disabled = !e?.undo.length;
    $("#redo").disabled = !e?.redo.length;
    $("#save").disabled = !e || !store.isDirty(e);
    $("#revert").disabled = !e?.saved || !store.isDirty(e);
    $("#save-all").disabled = !dirty.length;
    $("#save-all").textContent = dirty.length ? `Save all (${dirty.length})` : "Save all";
  }

  async function saveEntry(entry) {
    const errs = store.errorsFor(entry);
    if (errs.length) {
      const err = new Error(`${entry.mood.name} has validation errors`);
      err.errors = errs;
      throw err;
    }
    const { mood } = entry;
    if (entry.savedName && entry.savedName !== mood.name) await api.rename(entry.savedName, mood.name, mood);
    else await api.save(mood.name, mood);
    store.markSaved(entry);
  }

  function reportError(prefix, err) {
    console.error(err);
    const details = err.errors?.length ? `\n${err.errors.join("\n")}` : "";
    status(`${prefix}: ${err.message}${err.errors?.length ? ` (${err.errors.length} problem(s), see log)` : ""}`, "error");
    if (details) showLog(prefix, `${err.message}${details}`);
  }

  async function saveCurrent() {
    const e = store.current;
    if (!e || !store.isDirty(e)) return true;
    try {
      await saveEntry(e);
      status(`Saved moods/${e.mood.name}.json`, "ok");
      return true;
    } catch (err) {
      reportError(`Saving ${e.mood.name} failed`, err);
      return false;
    }
  }

  async function saveAll() {
    const dirty = store.dirtyEntries();
    for (const e of dirty) {
      try {
        await saveEntry(e);
      } catch (err) {
        reportError(`Saving ${e.mood.name} failed`, err);
        return false;
      }
    }
    if (dirty.length) status(`Saved ${dirty.length} mood${dirty.length > 1 ? "s" : ""}`, "ok");
    return true;
  }

  function revert() {
    const e = store.current;
    if (!e?.saved || !store.isDirty(e)) return;
    store.replace(e, e.saved);
    status(`Reverted ${e.mood.name} (undo to get the changes back)`);
  }

  let building = false;
  async function build() {
    if (building) return;
    building = true;
    $("#build").disabled = true;
    try {
      if (!(await saveAll())) return;
      status("Building…", "info", true);
      const res = await api.build();
      const log = [res.stdout, res.stderr].filter(Boolean).join("\n");
      $("#log-body").textContent = log;
      $("#log-title").textContent = res.ok ? "Build output" : "Build failed";
      $("#show-log").hidden = false;
      if (!res.ok) {
        status("Build failed", "error");
        showLog("Build failed", log);
        return;
      }
      const [st, svg] = await Promise.all([api.state(), api.svg()]);
      store.setContext({ rig: st.rig, defaults: st.defaults, keyframes: st.keyframes });
      lastCss = "";
      preview.load(svg, st.rig);
      refresh();
      status("Built assets/whale-chan.svg, rig.json and moods.json", "ok");
    } catch (err) {
      reportError("Build failed", err);
    } finally {
      building = false;
      $("#build").disabled = false;
    }
  }

  // ------------------------------------------------------------ new / delete
  function openNewDialog(duplicate = false) {
    const dlg = $("#new-dialog");
    const cur = store.current;
    $("#new-error").textContent = "";
    $("#new-name").value = "";
    $("#new-dup-name").textContent = cur ? cur.mood.name : "";
    dlg.querySelector('input[value="dup"]').disabled = !cur;
    dlg.querySelector(`input[value="${duplicate && cur ? "dup" : "blank"}"]`).checked = true;
    dlg.returnValue = "";
    dlg.showModal();
    $("#new-name").focus();
  }

  $("#new-ok").addEventListener("click", (e) => {
    const name = $("#new-name").value.trim();
    const taken = store.byName(name);
    let msg = "";
    if (!NAME_RE.test(name)) msg = "Use lowercase letters, digits and dashes (start with a letter, max 24).";
    else if (taken) msg = `"${name}" already exists.`;
    if (msg) {
      e.preventDefault();
      $("#new-error").textContent = msg;
      return;
    }
    const order = Math.max(0, ...store.moods().map((m) => m.order ?? 0)) + 10;
    const dup = $("#new-dialog").querySelector('input[name="new-base"]:checked').value === "dup";
    const neutral = store.list().find((x) => x.mood.default)?.mood;
    const mood = dup && store.current ? duplicateMood(store.current.mood, name, order) : blankMood(name, store.ctx, neutral, order);
    store.create(mood);
    status(`Created ${name} (not saved yet)`);
  });

  async function removeCurrent() {
    const e = store.current;
    if (!e || e.mood.default) return;
    const what = e.savedName ? `This deletes moods/${e.savedName}.json.` : "It was never saved.";
    if (!confirm(`Delete the mood "${e.mood.name}"? ${what}`)) return;
    try {
      if (e.savedName) await api.remove(e.savedName);
      store.drop(e);
      status(`Deleted ${e.mood.name}${e.savedName ? " (run Build to update the SVG)" : ""}`, "ok");
    } catch (err) {
      reportError(`Deleting ${e.mood.name} failed`, err);
    }
  }

  // ------------------------------------------------------------ preview controls
  const viewport = $("#viewport");
  const stage = $("#stage");
  let zoom = prefs.zoom || 1;
  const layout = () => {
    const w = viewport.clientWidth - 40;
    const hgt = viewport.clientHeight - 40;
    const fit = Math.max(120, Math.min(w, hgt * (900 / 1060)));
    stage.style.width = `${Math.round(fit * zoom)}px`;
  };
  new ResizeObserver(layout).observe(viewport);
  const setZoom = (z) => {
    zoom = Math.max(0.4, Math.min(4, z));
    prefs.zoom = zoom;
    savePrefs();
    layout();
  };
  $("#zoom-in").onclick = () => setZoom(zoom * 1.25);
  $("#zoom-out").onclick = () => setZoom(zoom / 1.25);
  $("#zoom-fit").onclick = () => setZoom(1);
  viewport.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom(zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  }, { passive: false });

  const setBg = (bg) => {
    viewport.classList.remove("bg-light", "bg-dark", "bg-checker");
    viewport.classList.add(`bg-${bg}`);
    for (const b of $("#bg").children) {
      b.classList.toggle("on", b.dataset.bg === bg);
      b.setAttribute("aria-checked", String(b.dataset.bg === bg));
    }
    prefs.bg = bg;
    savePrefs();
  };
  for (const b of $("#bg").children) {
    b.setAttribute("role", "radio");
    b.onclick = () => setBg(b.dataset.bg);
  }
  setBg(prefs.bg || "light");

  const setPlaying = (playing) => preview.setPaused(!playing);
  preview.onPlayState((paused) => {
    $("#play").textContent = paused ? "▶" : "❚❚";
    $("#play").setAttribute("aria-label", paused ? "Play" : "Pause");
    $("#play").classList.toggle("on", paused);
  });
  $("#play").onclick = () => setPlaying(preview.paused);
  $("#restart").onclick = () => preview.restart();
  $("#speed").onchange = (e) => preview.setSpeed(Number(e.target.value));

  const overlayFlags = () => preview.setOverlay({ hands: $("#show-hands").checked, pivots: $("#show-pivots").checked });
  $("#show-hands").onchange = overlayFlags;
  $("#show-pivots").onchange = overlayFlags;

  $("#undo").onclick = () => store.undo();
  $("#redo").onclick = () => store.redo();
  $("#save").onclick = saveCurrent;
  $("#save-all").onclick = saveAll;
  $("#revert").onclick = revert;
  $("#build").onclick = build;
  $("#show-log").onclick = () => $("#log-dialog").showModal();

  // ------------------------------------------------------------ keyboard
  const typing = (el) => el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search|)$/.test(el.type)) || el.isContentEditable);
  document.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();
    if (document.querySelector("dialog[open]")) return;
    if (mod && key === "s") {
      e.preventDefault();
      document.activeElement?.dispatchEvent?.(new Event("change", { bubbles: true }));
      if (e.shiftKey) saveAll();
      else saveCurrent();
    } else if (mod && (key === "z" || key === "y") && !typing(document.activeElement)) {
      e.preventDefault();
      if (key === "y" || e.shiftKey) store.redo();
      else store.undo();
    } else if (e.altKey && /^[1-9]$/.test(e.key)) {
      const btn = document.querySelectorAll(".tabs button")[Number(e.key) - 1];
      if (btn) {
        e.preventDefault();
        btn.click();
      }
    } else if (!mod && !e.altKey && !typing(document.activeElement) && !/^(SELECT|BUTTON|INPUT)$/.test(document.activeElement?.tagName)) {
      if (key === " ") {
        e.preventDefault();
        setPlaying(preview.paused);
      } else if (key === "h") {
        $("#show-hands").click();
      } else if (key === "p") {
        $("#show-pivots").click();
      }
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (store.dirtyEntries().length) e.preventDefault();
  });

  sidebar.draw();
  inspector.draw();
  timeline.draw();
  refresh();
}

boot();
