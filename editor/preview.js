// Live preview: the built SVG inlined into a shadow root (its global CSS can't leak into the editor),
// with the generated mood block of its <style> swapped for freshly compiled CSS on every edit.
// Also owns playback (Web Animations API) and the art-space overlay (hand handles, pivots).
//
// The timeline drives it through seek(ms), setPaused(), time(), animations(), setTrackArm() and onDrag.

import { fk } from "../tools/moods.mjs";

const SVG_NS = "http://www.w3.org/2000/svg";
const BEGIN = "/* moods:begin";
const END = "/* moods:end */";
// Older builds have no markers: the generated block starts with this comment and ends before the pause rules.
const LEGACY_BEGIN = "    /* ---------- generated from moods/*.json";
const LEGACY_END = "    /* ---------- pause while dragging";

const SHADOW_CSS = `
  :host { display: block; }
  svg.whale-chan { display: block; width: 100%; height: auto; }
  svg.dragging * { transition: none !important; }
  .ed-overlay { pointer-events: none; }
  .ed-overlay [data-drag] { pointer-events: all; cursor: grab; }
  .ed-overlay.hide-hands .ed-arm, .ed-overlay.hide-pivots .ed-pivots { display: none; }
  .ed-bone { fill: none; stroke: var(--ed-handle, #347fdb); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; opacity: .55; stroke-dasharray: 2 7; }
  .ed-joint { fill: #fff; stroke: var(--ed-handle, #347fdb); stroke-width: 2.5; opacity: .85; }
  .ed-hand { fill: var(--ed-handle, #347fdb); fill-opacity: .22; stroke: var(--ed-handle, #347fdb); stroke-width: 3; transition: fill-opacity .15s; }
  .ed-hand-core { fill: var(--ed-handle, #347fdb); }
  .ed-arm:hover .ed-hand, .ed-arm.active .ed-hand { fill-opacity: .45; }
  .ed-arm.active .ed-hand { cursor: grabbing; }
  .ed-path { fill: none; stroke: #e0397a; stroke-width: 2.5; stroke-linejoin: round; opacity: .45; }
  .ed-arm.track { --ed-handle: #e0397a; }
  .ed-arm.track:not(.on-stop) .ed-hand { stroke-dasharray: 5 4; fill-opacity: .08; }
  .ed-target { stroke: #d95a4e; stroke-width: 2.5; stroke-linecap: round; }
  .ed-tag { font: 600 17px/1 system-ui, sans-serif; fill: var(--ed-handle, #347fdb); paint-order: stroke; stroke: #fff; stroke-width: 4px; }
  .ed-pivot circle { fill: none; stroke: #e0397a; stroke-width: 2; }
  .ed-pivot path { stroke: #e0397a; stroke-width: 2; }
  .ed-pivot text { font: 500 13px/1 system-ui, sans-serif; fill: #b0215a; paint-order: stroke; stroke: #fff; stroke-width: 3.5px; }
`;

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

export class Preview {
  constructor(host) {
    this.host = host;
    this.root = host.attachShadow({ mode: "open" });
    this.svg = null;
    this.paused = false;
    this.speed = 1;
    this.pausedAt = 0;
    this.t0 = this.now();
    this.known = new WeakSet();
    this.showHands = true;
    this.showPivots = false;
    this.onDrag = null; // (side, [x, y] art space, phase: "start" | "move" | "end")
    this.playListeners = new Set(); // fn(paused) on play/pause/seek
    this.css = "";
  }

  /** Inline (or re-inline after a build) the SVG markup. */
  load(markup, rig) {
    this.rig = rig;
    const doc = new DOMParser().parseFromString(markup, "image/svg+xml");
    const err = doc.querySelector("parsererror");
    if (err) throw new Error(`whale-chan.svg: ${err.textContent.slice(0, 200)}`);
    const svg = document.importNode(doc.documentElement, true);
    svg.removeAttribute("aria-labelledby");
    svg.setAttribute("aria-label", "Whale-chan preview");
    const style = svg.querySelector("style");
    const text = style.textContent;
    let a = text.indexOf(BEGIN);
    let b = text.indexOf(END);
    if (a >= 0 && b > a) {
      a = text.indexOf("\n", a) + 1;
    } else {
      a = text.indexOf(LEGACY_BEGIN);
      b = text.indexOf(LEGACY_END);
      if (a < 0 || b < 0) throw new Error("whale-chan.svg: can't find the generated mood CSS block");
    }
    this.cssHead = text.slice(0, a);
    this.cssTail = text.slice(b);
    this.style = style;
    const own = document.createElement("style");
    own.textContent = SHADOW_CSS;
    this.root.replaceChildren(own, svg);
    this.svg = svg;
    this.known = new WeakSet();
    this.buildOverlay();
    if (this.css) this.setCss(this.css);
  }

  setCss(css) {
    this.css = css;
    if (!this.svg) return;
    this.style.textContent = `${this.cssHead}${css}\n${this.cssTail}`;
    this.syncSoon();
  }

  setState(mood, strain) {
    if (!this.svg) return;
    if (this.svg.getAttribute("data-mood") !== mood) this.svg.setAttribute("data-mood", mood);
    if (strain == null) this.svg.removeAttribute("data-strain");
    else if (this.svg.getAttribute("data-strain") !== strain) this.svg.setAttribute("data-strain", strain);
    this.syncSoon();
  }

  // ------------------------------------------------------------ playback
  animations() {
    if (!this.svg) return [];
    return this.svg.getAnimations({ subtree: true }).filter((a) => typeof CSSAnimation === "undefined" || a instanceof CSSAnimation);
  }

  syncSoon() {
    if (this._sync) return;
    this._sync = requestAnimationFrame(() => {
      this._sync = 0;
      this.sync();
    });
  }

  // Playback runs on one clock: time() is the animation time every CSS animation is held to, so
  // animations created later (new CSS, another mood) join in phase instead of starting at 0.
  now() {
    return document.timeline.currentTime ?? performance.now();
  }

  /** Current animation time in ms (since the last restart/seek, scaled by speed). */
  time() {
    return this.paused ? this.pausedAt : (this.now() - this.t0) * this.speed;
  }

  /** Apply clock, play state and speed to animations created since the last call. */
  sync() {
    const t = this.time();
    for (const a of this.animations()) {
      if (a.playbackRate !== this.speed) a.playbackRate = this.speed;
      if (!this.known.has(a)) {
        this.known.add(a);
        a.currentTime = t;
      }
      if (this.paused) {
        if (a.playState !== "paused") a.pause();
      } else if (a.playState === "paused") {
        a.play();
      }
    }
  }

  /** Put every animation at `ms` and restart the clock from there. */
  applyTime(ms) {
    this.pausedAt = ms;
    this.t0 = this.now() - ms / this.speed;
    for (const a of this.animations()) {
      this.known.add(a);
      a.currentTime = ms;
    }
    this.sync();
  }

  onPlayState(fn) {
    this.playListeners.add(fn);
  }

  setPaused(paused) {
    if (paused === this.paused) return;
    const t = this.time();
    this.paused = paused;
    this.applyTime(t);
    for (const fn of this.playListeners) fn(paused);
  }

  restart() {
    this.applyTime(0);
  }

  /** Jump every animation to `ms` (timeline scrubbing); pauses playback. */
  seek(ms) {
    const was = this.paused;
    this.paused = true;
    this.applyTime(Math.max(0, ms));
    if (!was) for (const fn of this.playListeners) fn(true);
  }

  setSpeed(speed) {
    const t = this.time();
    this.speed = speed;
    this.t0 = this.now() - t / speed;
    this.sync();
  }

  // ------------------------------------------------------------ overlay
  buildOverlay() {
    const rig = this.rig;
    const g = svgEl("g", { class: "ed-overlay", transform: rig.art.transform });
    const [fx, fy] = rig.feet;
    // Same structure as .char-pose so --cy/--cs (body drop/squash) move the handles too.
    const charPose = svgEl("g");
    this.charPose = charPose;
    const arms = {};
    for (const side of ["l", "r"]) {
      const arm = svgEl("g", { class: `ed-arm ed-arm-${side}` });
      const bone = svgEl("polyline", { class: "ed-bone" });
      const shoulder = svgEl("circle", { class: "ed-joint", r: 5 });
      const elbow = svgEl("circle", { class: "ed-joint", r: 6 });
      const target = svgEl("path", { class: "ed-target", d: "" });
      const path = svgEl("polyline", { class: "ed-path" });
      const hand = svgEl("circle", { class: "ed-hand", r: 17, "data-drag": side });
      const core = svgEl("circle", { class: "ed-hand-core", r: 4 });
      const tag = svgEl("text", { class: "ed-tag", "text-anchor": "middle" });
      tag.textContent = side === "l" ? "L" : "R";
      const title = svgEl("title");
      hand.append(title);
      arm.append(path, bone, shoulder, elbow, target, hand, core, tag);
      charPose.append(arm);
      arms[side] = { arm, bone, shoulder, elbow, hand, core, tag, target, path, title };
      this.bindDrag(hand, side);
    }
    const pivots = svgEl("g", { class: "ed-pivots" });
    for (const [name, part] of Object.entries(rig.parts)) {
      if (!part.pivot || (part.pivot[0] === 0 && part.pivot[1] === 0)) continue;
      const [x, y] = part.pivot;
      const p = svgEl("g", { class: "ed-pivot", transform: `translate(${x},${y})` });
      const t = svgEl("text", { x: 9, y: -8 });
      t.textContent = name;
      const tt = svgEl("title");
      tt.textContent = part.label;
      p.append(svgEl("circle", { r: 6 }), svgEl("path", { d: "M-11,0H11M0,-11V11" }), t, tt);
      p.dataset.part = name;
      pivots.append(p);
    }
    charPose.append(pivots);
    const outer = svgEl("g", { transform: `translate(${fx},${fy})` });
    const inner = svgEl("g", { transform: `translate(${-fx},${-fy})` });
    inner.append(charPose);
    outer.append(this.charPoseTransform = svgEl("g"));
    this.charPoseTransform.append(inner);
    g.append(outer);
    this.overlay = g;
    this.arms = arms;
    this.svg.append(g);
    this.applyOverlayFlags();
  }

  applyOverlayFlags() {
    if (!this.overlay) return;
    this.overlay.classList.toggle("hide-hands", !this.showHands);
    this.overlay.classList.toggle("hide-pivots", !this.showPivots);
  }

  setOverlay({ hands = this.showHands, pivots = this.showPivots } = {}) {
    this.showHands = hands;
    this.showPivots = pivots;
    this.applyOverlayFlags();
  }

  /** pose = resolvePose() result; targets = {l, r} requested hand targets (or null); body = {cy, cs}. */
  updateOverlay(pose, targets, body) {
    if (!this.overlay) return;
    this.charPoseTransform.setAttribute("transform", `translate(0,${body.cy}) scale(1,${body.cs})`);
    this.pose = pose;
    this.targets = targets;
    for (const side of ["l", "r"]) this.drawArm(side);
  }

  /**
   * Hand-track mode for one arm (the timeline drives it): {angles, path: [[x, y], ...], onStop, target}
   * draws the handle at the animated hand with its path; null returns to the pose handle.
   */
  setTrackArm(side, info) {
    this.trackArms ??= {};
    this.trackArms[side] = info;
    if (this.pose) this.drawArm(side);
  }

  drawArm(side) {
    const a = this.arms[side];
    const track = this.trackArms?.[side];
    const [sx, sy] = this.rig.arms[side].shoulder;
    const { elbow, hand } = fk(this.rig, side, track ? track.angles : this.pose[side]);
    a.arm.classList.toggle("track", !!track);
    a.arm.classList.toggle("on-stop", !!track?.onStop);
    a.path.setAttribute("points", track?.path ? track.path.map((p) => p.join(",")).join(" ") : "");
    a.title.textContent = track
      ? (track.onStop ? "Drag to move this hand stop" : "Drag to add a hand stop at the playhead")
      : `Drag to move the ${side === "l" ? "left" : "right"} hand (IK)`;
    const targets = track ? { [side]: track.target } : this.targets;
    a.bone.setAttribute("points", `${sx},${sy} ${elbow[0]},${elbow[1]} ${hand[0]},${hand[1]}`);
    a.shoulder.setAttribute("cx", sx);
    a.shoulder.setAttribute("cy", sy);
    a.elbow.setAttribute("cx", elbow[0]);
    a.elbow.setAttribute("cy", elbow[1]);
    for (const el of [a.hand, a.core]) {
      el.setAttribute("cx", hand[0]);
      el.setAttribute("cy", hand[1]);
    }
    // The forearm pivot rides on the posed upper arm.
    this.overlay.querySelector(`[data-part="arm-${side}.f"]`)?.setAttribute("transform", `translate(${elbow[0]},${elbow[1]})`);
    a.tag.setAttribute("x", hand[0]);
    a.tag.setAttribute("y", hand[1] - 24);
    const t = targets?.[side];
    const off = t && Math.hypot(t[0] - hand[0], t[1] - hand[1]) > 3;
    a.target.setAttribute("d", off ? `M${t[0] - 7},${t[1] - 7}l14,14m0,-14l-14,14` : "");
  }

  /** Client (pointer) coordinates -> art space, through the same transforms as the arms. */
  toArt(clientX, clientY) {
    const m = this.charPose.getScreenCTM().inverse();
    const p = new DOMPoint(clientX, clientY).matrixTransform(m);
    return [Number(p.x.toFixed(1)), Number(p.y.toFixed(1))];
  }

  bindDrag(el, side) {
    let id = null;
    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      id = e.pointerId;
      el.setPointerCapture(id);
      this.svg.classList.add("dragging");
      this.arms[side].arm.classList.add("active");
      this.onDrag?.(side, this.toArt(e.clientX, e.clientY), "start");
    });
    el.addEventListener("pointermove", (e) => {
      if (e.pointerId !== id) return;
      this.onDrag?.(side, this.toArt(e.clientX, e.clientY), "move");
    });
    const end = (e) => {
      if (e.pointerId !== id) return;
      id = null;
      this.svg.classList.remove("dragging");
      this.arms[side].arm.classList.remove("active");
      this.onDrag?.(side, null, "end");
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  }
}
