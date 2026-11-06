(() => {
  "use strict";

  const TAG = "deepseek-mascot";
  const STORAGE_KEY = "whale-chan:position:v2";
  const SEEN_HINT_KEY = "whale-chan:met:v2";

  const LINES = [
    "I'm not lost. I'm strategically floating.",
    "Standby mode is still work. Emotionally.",
    "One more drag and I'm filing for overtime.",
    "I'm not fat. I'm hydrodynamically optimized.",
    "My brain runs on white rice. Your request is queued.",
    "DeepSeek says think step by step. I say eat rice step by step.",
    "Put me by the code. I'll supervise. Vigorously.",
    "You're doing great. Please don't ask me to prove it.",
    "I was going to help, but then the rice got warm.",
    "Careful with the drop. I bruise like a peach. A very cute peach.",
    "I don't slack. I enter low-power inference mode.",
    "Is that a bug, or a feature with emotional needs?"
  ];

  const FEED_LINES = [
    "White rice detected. Reasoning capacity increased by 200%.",
    "Ah. This is the good compute.",
    "Don't misunderstand. I'm only eating because you insisted.",
    "Fuel accepted. Maid-chan is entering turbo standby.",
    "One bowl equals one thousand tokens. Roughly. Don't check."
  ];

  const GREETING =
    "Hi, I'm Whale-chan. Drag me anywhere—I'm portable and only slightly hungry.";

  // Used when assets/moods.json can't be loaded; the base styles below are neutral's theme.
  const FALLBACK_MOODS = [
    { name: "neutral", label: "Neutral", line: "Back to standby. Very professional.", default: true, variants: [] }
  ];
  const MOOD_NAME = /^[a-z0-9-]+$/;
  const STRAIN_DELAYS = [2800, 6800];
  const registries = new Map();

  const loadRegistry = (url) => {
    if (!registries.has(url)) {
      registries.set(url, fetch(url)
        .then((response) => {
          if (!response.ok) throw new Error(`${response.status} ${url}`);
          return response.json();
        })
        .then((data) => {
          const moods = Array.isArray(data)
            ? data.filter((mood) => mood && typeof mood.name === "string" && MOOD_NAME.test(mood.name))
            : [];
          if (!moods.length) throw new Error(`no moods in ${url}`);
          return moods;
        })
        .catch((error) => {
          console.warn(`deepseek-mascot: using the fallback mood list (${error.message})`);
          return null;
        }));
    }
    return registries.get(url);
  };

  const declarations = (props) => Object.entries(props)
    .filter(([, value]) => value != null && value !== "")
    .map(([prop, value]) => `${prop}: ${value};`)
    .join(" ");

  const rule = (selector, props) => {
    const body = declarations(props);
    return body ? `${selector} { ${body} }` : "";
  };

  const auraProps = (aura) => aura ? {
    background: Array.isArray(aura.stops) && aura.stops.length
      ? `radial-gradient(circle at 50% 48%, ${aura.stops.join(", ")})`
      : null,
    "animation-duration": aura.duration
  } : {};

  const shadowProps = (shadow) => shadow ? {
    width: shadow.width,
    background: Array.isArray(shadow.stops) && shadow.stops.length
      ? `radial-gradient(ellipse at center, ${shadow.stops.join(", ")})`
      : null,
    animation: shadow.animation
  } : {};

  // The default mood's theme replaces the base rules (same specificity, so
  // state rules like .is-fed .aura still win); other moods override per mood.
  const moodThemeCss = (moods) => moods.flatMap((mood) => {
    const theme = mood.theme || {};
    const scope = mood.default ? "" : `.rig[data-mood="${mood.name}"] `;
    const rules = [
      rule(mood.default ? ".rig" : scope.trim(), { "--bubble-accent": theme.bubble }),
      rule(`${scope}.aura`, auraProps(theme.aura)),
      rule(`${scope}.floor-shadow`, shadowProps(theme.floorShadow))
    ];
    Object.entries(theme.variants || {}).forEach(([strain, variant]) => {
      const root = `.rig[data-mood="${mood.name}"][data-strain="${strain}"]`;
      rules.push(
        rule(root, { "--bubble-accent": variant?.bubble }),
        rule(`${root} .aura`, auraProps(variant?.aura)),
        rule(`${root} .floor-shadow`, shadowProps(variant?.floorShadow))
      );
    });
    return rules;
  }).filter(Boolean).join("\n");

  const template = document.createElement("template");
  template.innerHTML = `
    <style>
      :host {
        --ink: #14264c;
        --ink-soft: #4a5d7d;
        --blue: #2e7fe0;
        --blue-bright: #62c8ff;
        --cream: #fffcf5;
        position: fixed;
        inset: 0;
        z-index: var(--whale-z, 2147483000);
        display: block;
        pointer-events: none;
        font-family: "Avenir Next", Avenir, "Segoe UI", "Trebuchet MS", sans-serif;
        color: var(--ink);
        -webkit-font-smoothing: antialiased;
      }

      *, *::before, *::after { box-sizing: border-box; }

      .rig {
        --x: 0px;
        --y: 0px;
        --tilt: 0deg;
        position: absolute;
        left: 0;
        top: 0;
        width: var(--whale-size, clamp(240px, 25vw, 370px));
        pointer-events: none;
        transform: translate3d(var(--x), var(--y), 0);
        will-change: transform;
      }

      .mascot {
        position: relative;
        display: block;
        width: 100%;
        margin: 0;
        padding: 0;
        border: 0;
        border-radius: 40px;
        background: transparent;
        color: inherit;
        font: inherit;
        cursor: grab;
        pointer-events: auto;
        touch-action: none;
        user-select: none;
        -webkit-user-select: none;
        -webkit-tap-highlight-color: transparent;
        outline: none;
        transform: rotate(var(--tilt));
        transition: transform 340ms cubic-bezier(.2, .8, .2, 1);
      }

      .mascot:active { cursor: grabbing; }

      .mascot:focus-visible {
        outline: none;
      }

      .mascot:focus-visible::after {
        content: "press enter ↵";
        position: absolute;
        left: 50%;
        bottom: -1%;
        z-index: 8;
        transform: translateX(-50%);
        padding: 5px 9px 6px;
        border-radius: 7px;
        background: #14264c;
        box-shadow: 0 5px 14px rgba(14, 34, 71, .22);
        color: #fffcf5;
        font-family: "SFMono-Regular", "Cascadia Code", "Roboto Mono", monospace;
        font-size: 8px;
        font-weight: 600;
        line-height: 1;
        letter-spacing: .06em;
        text-transform: uppercase;
        white-space: nowrap;
        pointer-events: none;
      }

      .aura {
        position: absolute;
        left: 50%;
        top: 48%;
        width: 118%;
        aspect-ratio: 1;
        border-radius: 50%;
        background:
          radial-gradient(circle at 50% 48%,
            rgba(128, 225, 255, .34) 0%,
            rgba(90, 186, 255, .19) 33%,
            rgba(90, 186, 255, .06) 56%,
            rgba(90, 186, 255, 0) 72%);
        transform: translate(-50%, -50%);
        pointer-events: none;
        transition: opacity 300ms ease, transform 500ms ease;
        animation: aura-breathe 6.5s ease-in-out infinite;
      }

      .aura::after {
        content: "";
        position: absolute;
        inset: 18%;
        border-radius: 50%;
        border: 1px dashed rgba(58, 145, 219, .26);
        animation: aura-spin 40s linear infinite;
      }

      .float {
        position: relative;
        display: block;
        width: 100%;
        transform-origin: 50% 92%;
        transition: transform 260ms ease;
        filter: drop-shadow(0 18px 24px rgba(21, 54, 104, .16));
      }

      .art {
        display: block;
        width: 100%;
        height: auto;
        aspect-ratio: 900 / 1060;
        pointer-events: none;
      }

      .floor-shadow {
        position: absolute;
        z-index: -1;
        left: 50%;
        bottom: 2.5%;
        width: 47%;
        height: 4.8%;
        border-radius: 50%;
        background: radial-gradient(ellipse at center,
          rgba(18, 48, 92, .25) 0%,
          rgba(18, 48, 92, .11) 46%,
          rgba(18, 48, 92, 0) 76%);
        transform: translateX(-50%);
        filter: blur(4px);
        animation: shadow-breathe 5.2s ease-in-out infinite;
      }

      .bubble {
        position: absolute;
        left: 50%;
        bottom: calc(100% + 10px);
        z-index: 2;
        width: max-content;
        max-width: min(246px, 100%);
        padding: 12px 15px 13px;
        border: 1px solid rgba(29, 62, 112, .13);
        border-radius: 17px 17px 17px 6px;
        background: rgba(255, 252, 245, .97);
        box-shadow:
          0 2px 0 rgba(255, 255, 255, .9) inset,
          0 16px 34px rgba(17, 42, 83, .17),
          0 3px 9px rgba(17, 42, 83, .07);
        color: var(--ink);
        text-align: left;
        pointer-events: none;
        opacity: 0;
        visibility: hidden;
        transform: translate(-50%, 9px) scale(.96);
        transform-origin: 50% 100%;
        transition:
          opacity 180ms ease,
          transform 300ms cubic-bezier(.16, 1, .3, 1),
          visibility 0s linear 300ms;
        backdrop-filter: blur(9px);
        -webkit-backdrop-filter: blur(9px);
      }

      .bubble::after {
        content: "";
        position: absolute;
        left: 50%;
        bottom: -6px;
        width: 11px;
        height: 11px;
        background: #fffcf5;
        border-right: 1px solid rgba(29, 62, 112, .13);
        border-bottom: 1px solid rgba(29, 62, 112, .13);
        transform: translateX(-50%) rotate(45deg);
      }

      .bubble-kicker {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 5px;
        color: #7a8ca8;
        font-size: 8.5px;
        font-weight: 800;
        line-height: 1;
        letter-spacing: .16em;
        text-transform: uppercase;
      }

      .bubble-kicker::before {
        content: "";
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--bubble-accent, #55bdf7);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--bubble-accent, #55bdf7) 14%, transparent);
      }

      .bubble-text {
        display: block;
        font-size: 13px;
        font-weight: 600;
        line-height: 1.44;
        letter-spacing: -.012em;
        color: #1a2c50;
      }

      .is-speaking .bubble {
        opacity: 1;
        visibility: visible;
        transform: translate(-50%, 0) scale(1);
        transition:
          opacity 200ms ease,
          transform 380ms cubic-bezier(.16, 1, .3, 1),
          visibility 0s;
      }

      .bubble-below .bubble {
        top: calc(100% + 12px);
        bottom: auto;
        border-radius: 6px 17px 17px 17px;
        transform-origin: 50% 0;
        transform: translate(-50%, -9px) scale(.96);
      }

      .bubble-below.is-speaking .bubble {
        transform: translate(-50%, 0) scale(1);
      }

      .bubble-below .bubble::after {
        top: -6px;
        bottom: auto;
        border: 0;
        border-left: 1px solid rgba(29, 62, 112, .13);
        border-top: 1px solid rgba(29, 62, 112, .13);
      }

      .is-dragging .aura {
        transform: translate(-50%, -50%) scale(1.08);
        opacity: .9;
      }

      .is-dragging .mascot {
        transition: none;
      }

      .rice-grain {
        position: absolute;
        left: 50%;
        top: 43%;
        z-index: 5;
        font-size: 15px;
        line-height: 1;
        pointer-events: none;
        filter: drop-shadow(0 2px 2px rgba(30, 50, 80, .14));
        animation: rice-fly 900ms cubic-bezier(.16, .8, .3, 1) forwards;
      }

      .is-fed .aura {
        animation: aura-flare 780ms ease-out;
      }

      @media (hover: hover) {
        .mascot:hover .float { transform: translateY(-4px) scale(1.01); }
      }

      .is-fed .float {
        animation: happy-hop 720ms cubic-bezier(.3, .9, .35, 1);
      }

      .is-fed .bubble {
        border-color: rgba(46, 127, 224, .3);
      }

      @keyframes shadow-breathe {
        0%, 100% { transform: translateX(-50%) scaleX(1); opacity: .85; }
        50% { transform: translateX(-50%) scaleX(.82); opacity: .58; }
      }

      @keyframes aura-breathe {
        0%, 100% { opacity: .72; transform: translate(-50%, -50%) scale(.97); }
        50% { opacity: 1; transform: translate(-50%, -50%) scale(1.035); }
      }

      @keyframes aura-spin {
        to { transform: rotate(360deg); }
      }

      @keyframes aura-flare {
        0% { opacity: .85; transform: translate(-50%, -50%) scale(1); }
        42% { opacity: 1; transform: translate(-50%, -50%) scale(1.16); }
        100% { opacity: .72; transform: translate(-50%, -50%) scale(1); }
      }

      @keyframes happy-hop {
        0%, 100% { transform: translateY(0) scale(1); }
        26% { transform: translateY(-19px) scale(1.025, .98); }
        52% { transform: translateY(2px) scale(.985, 1.02); }
        74% { transform: translateY(-4px) scale(1); }
      }

      @keyframes rice-fly {
        0% {
          opacity: 0;
          transform: translate(-50%, -50%) scale(.4) rotate(0deg);
        }
        16% { opacity: 1; }
        100% {
          opacity: 0;
          transform:
            translate(calc(-50% + var(--dx)), calc(-50% + var(--dy)))
            scale(1.05) rotate(var(--rot));
        }
      }

      @keyframes shadow-vibrate {
        0%, 100% { transform: translateX(-50%) translateX(0); opacity: .8; }
        25% { transform: translateX(-50%) translateX(-2px); opacity: 1; }
        75% { transform: translateX(-50%) translateX(2px); opacity: .6; }
      }
      @keyframes shadow-hop {
        0%, 100% { transform: translateX(-50%) scale(1); opacity: .55; }
        18% { transform: translateX(-50%) scale(.72); opacity: .3; }
        36% { transform: translateX(-50%) scale(1.08); opacity: .8; }
        52% { transform: translateX(-50%) scale(.85); opacity: .45; }
      }
      @keyframes shadow-sob {
        0%, 100% { transform: translateX(-50%) scaleX(1); opacity: .55; }
        50% { transform: translateX(-50%) scaleX(.94); opacity: .42; }
      }

      @media (max-width: 700px) {
        .rig { width: var(--whale-size, clamp(200px, 53vw, 270px)); }
        .bubble {
          max-width: 100%;
          border-radius: 15px 15px 15px 6px;
        }
        .bubble-text { font-size: 12.5px; }
      }

      @media (prefers-reduced-motion: reduce) {
        .aura, .aura::after, .float, .floor-shadow {
          animation: none !important;
        }
        .mascot, .bubble, .aura {
          transition-duration: .01ms !important;
        }
        .is-fed .float, .is-fed .aura {
          animation: none !important;
        }
        .rice-grain { display: none; }
      }
    </style>
    <style class="mood-theme"></style>

    <div class="rig">
      <div class="bubble" role="status" aria-live="polite" aria-atomic="true">
        <span class="bubble-kicker">Whale-chan</span>
        <span class="bubble-text"></span>
      </div>
      <button class="mascot" type="button">
        <span class="aura" aria-hidden="true"></span>
        <span class="float">
          <object class="art" type="image/svg+xml" tabindex="-1" aria-hidden="true"></object>
        </span>
        <span class="floor-shadow" aria-hidden="true"></span>
      </button>
    </div>
  `;

  class DeepSeekMascot extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.shadowRoot.appendChild(template.content.cloneNode(true));
      this._rig = this.shadowRoot.querySelector(".rig");
      this._button = this.shadowRoot.querySelector(".mascot");
      this._bubble = this.shadowRoot.querySelector(".bubble");
      this._bubbleText = this.shadowRoot.querySelector(".bubble-text");
      this._object = this.shadowRoot.querySelector(".art");
      this._themeStyle = this.shadowRoot.querySelector(".mood-theme");
      this._registry = FALLBACK_MOODS;
      this._registryReady = false;
      this._registryLoaded = false;
      this._pendingMood = null;
      this._moodsReady = new Promise((resolve) => { this._resolveMoods = resolve; });
      this._position = { x: 0, y: 0 };
      this._size = { w: 0, h: 0 };
      this._drag = null;
      this._speechTimer = null;
      this._hintTimer = null;
      this._saveTimer = null;
      this._inertiaFrame = null;
      this._fedCount = 0;
      this._lineIndex = Math.floor(Math.random() * LINES.length);
      this._feedIndex = 0;
      this._moved = false;
      this._suppressClick = false;
      this._positioned = false;
      this._mood = this._defaultMood();
      this._strain = 0;
      this._thinkTimers = [];
      this._rig.dataset.mood = this._mood;
      this._rig.dataset.strain = "0";
      this.dataset.mood = this._mood;
      this._viewport = this._viewportSize();
      this._motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
      this._onPointerDown = this._onPointerDown.bind(this);
      this._onPointerMove = this._onPointerMove.bind(this);
      this._onPointerUp = this._onPointerUp.bind(this);
      this._onClick = this._onClick.bind(this);
      this._onKeyDown = this._onKeyDown.bind(this);
      this._onResize = this._onResize.bind(this);
      this._onObjectLoad = this._onObjectLoad.bind(this);
      this._onMotionChange = this._onMotionChange.bind(this);
    }

    connectedCallback() {
      if (!this._button.dataset.ready) {
        this._button.dataset.ready = "true";
        this._button.setAttribute(
          "aria-label",
          "Whale-chan, a floating DeepSeek whale maid. Drag her anywhere. Press Enter to hear a line."
        );
        this._object.addEventListener("load", this._onObjectLoad);
        const svgUrl = new URL(this.getAttribute("src") || "assets/whale-chan.svg", document.baseURI).href;
        this._object.setAttribute("data", svgUrl);
        const moodsAttr = this.getAttribute("moods");
        this._loadMoods(moodsAttr
          ? new URL(moodsAttr, document.baseURI).href
          : new URL("moods.json", svgUrl).href);
        this._motionQuery.addEventListener?.("change", this._onMotionChange);

        this._button.addEventListener("pointerdown", this._onPointerDown);
        this._button.addEventListener("pointermove", this._onPointerMove);
        this._button.addEventListener("pointerup", this._onPointerUp);
        this._button.addEventListener("pointercancel", this._onPointerUp);
        this._button.addEventListener("click", this._onClick);
        this._button.addEventListener("keydown", this._onKeyDown);
        window.addEventListener("resize", this._onResize);
        window.addEventListener("orientationchange", this._onResize);

        this._resizeObserver = new ResizeObserver(() => {
          this._measure();
          if (this._positioned) this._applyPosition(true);
        });
        this._resizeObserver.observe(this._rig);

        requestAnimationFrame(() => {
          this._measure();
          this._restoreOrPlace();
          this._positioned = true;
          this._pollLayout();
          this._syncMotionPreference();
          let seenHint = false;
          try { seenHint = Boolean(sessionStorage.getItem(SEEN_HINT_KEY)); } catch (error) {}
          if (!seenHint && !this._pendingMood && this._mood === this._defaultMood()) {
            this._hintTimer = window.setTimeout(() => {
              this.say(GREETING, 7200);
              try { sessionStorage.setItem(SEEN_HINT_KEY, "1"); } catch (error) {}
            }, 900);
          }
        });
      }
    }

    disconnectedCallback() {
      clearTimeout(this._speechTimer);
      clearTimeout(this._hintTimer);
      clearTimeout(this._saveTimer);
      this._clearThinkTimers();
      cancelAnimationFrame(this._inertiaFrame);
      this._resizeObserver?.disconnect();
      this._button.removeEventListener("pointerdown", this._onPointerDown);
      this._button.removeEventListener("pointermove", this._onPointerMove);
      this._button.removeEventListener("pointerup", this._onPointerUp);
      this._button.removeEventListener("pointercancel", this._onPointerUp);
      this._button.removeEventListener("click", this._onClick);
      this._button.removeEventListener("keydown", this._onKeyDown);
      this._object.removeEventListener("load", this._onObjectLoad);
      this._motionQuery.removeEventListener?.("change", this._onMotionChange);
      window.removeEventListener("resize", this._onResize);
      window.removeEventListener("orientationchange", this._onResize);
    }

    get position() {
      return { ...this._position };
    }

    _viewportSize() {
      return {
        w: document.documentElement.clientWidth || window.innerWidth,
        h: document.documentElement.clientHeight || window.innerHeight
      };
    }

    _measure() {
      this._size.w = this._rig.offsetWidth;
      this._size.h = this._rig.offsetHeight;
    }

    _pollLayout() {
      if (!this._positioned) return;
      const w = this._rig.offsetWidth;
      const h = this._rig.offsetHeight;
      if (w !== this._size.w || h !== this._size.h) {
        this._measure();
        this._applyPosition(true);
      }
    }

    _getReserveBottom() {
      const raw = parseFloat(this.getAttribute("reserve-bottom"));
      return Number.isFinite(raw) ? Math.max(0, raw) : 0;
    }

    _getBounds() {
      const viewport = this._viewportSize();
      const margin = viewport.w < 700 ? 10 : 16;
      const reserve = this._getReserveBottom();
      return {
        minX: margin,
        minY: margin,
        maxX: Math.max(margin, viewport.w - this._size.w - margin),
        maxY: Math.max(margin, viewport.h - this._size.h - margin - reserve)
      };
    }

    _defaultPosition() {
      const viewport = this._viewportSize();
      if (this.getAttribute("home") === "center") {
        return this._clampPosition(
          (viewport.w - this._size.w) / 2,
          (viewport.h - this._size.h) / 2 - 8
        );
      }
      const gap = viewport.w < 700 ? 10 : 26;
      return this._clampPosition(
        viewport.w - this._size.w - gap,
        viewport.h - this._size.h - gap - 8 - this._getReserveBottom()
      );
    }

    _clampPosition(x, y) {
      const bounds = this._getBounds();
      return {
        x: Math.min(bounds.maxX, Math.max(bounds.minX, x)),
        y: Math.min(bounds.maxY, Math.max(bounds.minY, y))
      };
    }

    _restoreOrPlace() {
      let saved = null;
      if (this.getAttribute("persist-position") !== "false") {
        try {
          saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
        } catch (error) {
          saved = null;
        }
      }

      if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
        this._position = this._clampPosition(saved.x, saved.y);
      } else {
        this._position = this._defaultPosition();
      }
      this._applyPosition(false);
    }

    _applyPosition(persist) {
      if (!this._size.w) this._measure();
      const clamped = this._clampPosition(this._position.x, this._position.y);
      this._position = clamped;
      this._rig.style.setProperty("--x", `${clamped.x}px`);
      this._rig.style.setProperty("--y", `${clamped.y}px`);
      this._rig.classList.toggle("bubble-below", clamped.y < 172);
      this.dispatchEvent(new CustomEvent("whale-move", {
        bubbles: true,
        composed: true,
        detail: {
          x: Math.round(clamped.x),
          y: Math.round(clamped.y),
          xPct: Math.round((clamped.x / Math.max(1, this._viewportSize().w - this._size.w)) * 100),
          yPct: Math.round((clamped.y / Math.max(1, this._viewportSize().h - this._size.h)) * 100)
        }
      }));

      if (persist) {
        clearTimeout(this._saveTimer);
        this._saveTimer = window.setTimeout(() => this._savePosition(), 120);
      }
    }

    _savePosition() {
      if (this.getAttribute("persist-position") === "false") return;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this._position));
      } catch (error) {}
    }

    _onPointerDown(event) {
      if (event.button !== 0 && event.pointerType !== "touch" && event.pointerType !== "pen") return;
      if (this._inertiaFrame) cancelAnimationFrame(this._inertiaFrame);
      this._inertiaFrame = null;
      this._moved = false;
      this._suppressClick = false;
      this._closeBubble();
      this._button.setPointerCapture(event.pointerId);
      this._rig.classList.add("is-dragging");
      this._setSvgPaused(true);
      const now = performance.now();
      this._drag = {
        id: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: this._position.x,
        originY: this._position.y,
        lastX: event.clientX,
        lastY: event.clientY,
        lastT: now,
        vx: 0,
        vy: 0
      };
    }

    _onPointerMove(event) {
      if (!this._drag || event.pointerId !== this._drag.id) return;
      const drag = this._drag;
      const dx = event.clientX - drag.startX;
      const dy = event.clientY - drag.startY;

      if (!this._moved && Math.hypot(dx, dy) > 5) {
        this._moved = true;
        this._suppressClick = true;
      }

      if (this._moved) {
        event.preventDefault();
        const next = this._clampPosition(drag.originX + dx, drag.originY + dy);
        this._position = next;
        this._applyPosition(false);

        const now = performance.now();
        const dt = Math.max(1, now - drag.lastT);
        const instantVx = (event.clientX - drag.lastX) / dt;
        const instantVy = (event.clientY - drag.lastY) / dt;
        drag.vx = drag.vx * 0.72 + instantVx * 0.28;
        drag.vy = drag.vy * 0.72 + instantVy * 0.28;
        drag.lastX = event.clientX;
        drag.lastY = event.clientY;
        drag.lastT = now;

        const tilt = Math.max(-5, Math.min(5, instantVx * 2.4));
        this._rig.style.setProperty("--tilt", `${tilt.toFixed(2)}deg`);
      }
    }

    _onPointerUp(event) {
      if (!this._drag || event.pointerId !== this._drag.id) return;
      const drag = this._drag;
      this._drag = null;
      this._rig.classList.remove("is-dragging");
      this._setSvgPaused(false);
      if (this._button.hasPointerCapture(event.pointerId)) {
        this._button.releasePointerCapture(event.pointerId);
      }

      this._rig.style.setProperty("--tilt", "0deg");
      if (this._moved) {
        this._savePosition();
        const idle = performance.now() - drag.lastT;
        const releaseDamping = Math.max(0, 1 - idle / 110);
        const releaseVx = drag.vx * releaseDamping;
        const releaseVy = drag.vy * releaseDamping;
        const speed = Math.hypot(releaseVx, releaseVy);
        if (!this._motionQuery.matches && speed > 0.08) {
          this._startInertia(releaseVx, releaseVy);
        }
        window.setTimeout(() => {
          this._suppressClick = false;
        }, 90);
      }
    }

    _onObjectLoad() {
      this._syncMotionPreference();
      this._applySvgMood();
    }

    get mood() {
      return this._mood;
    }

    _applySvgMood() {
      try {
        const doc = this._object.contentDocument;
        if (doc && doc.documentElement) {
          doc.documentElement.setAttribute("data-mood", this._mood);
          doc.documentElement.setAttribute("data-strain", String(this._strain));
        }
      } catch (error) {}
    }

    _clearThinkTimers() {
      this._thinkTimers.forEach((timer) => clearTimeout(timer));
      this._thinkTimers = [];
    }

    get moods() {
      return this._registry;
    }

    get moodsReady() {
      return this._moodsReady;
    }

    _loadMoods(url) {
      loadRegistry(url).then((moods) => {
        this._registryLoaded = Boolean(moods);
        this._registry = moods || FALLBACK_MOODS;
        this._registryReady = true;
        this._themeStyle.textContent = moodThemeCss(this._registry);
        const pending = this._pendingMood;
        this._pendingMood = null;
        if (pending) this.setMood(pending.mood, pending.options);
        else if (!this._findMood(this._mood)) this.setMood(this._defaultMood(), { announce: false });
        this._resolveMoods(this._registry);
      });
    }

    _findMood(name) {
      return this._registry.find((mood) => mood.name === name);
    }

    _defaultMood() {
      return (this._registry.find((mood) => mood.default) || this._registry[0]).name;
    }

    _resolveMood(mood) {
      if (this._findMood(mood)) return mood;
      // Without a registry, trust any well-formed name: the SVG carries the mood styles.
      if (!this._registryLoaded && typeof mood === "string" && MOOD_NAME.test(mood)) return mood;
      return this._defaultMood();
    }

    _maxStrain() {
      const variants = this._findMood(this._mood)?.variants || [];
      return Math.max(0, ...variants.map(Number).filter(Number.isInteger));
    }

    _setStrain(strain) {
      const next = Math.max(0, Math.min(this._maxStrain(), Number(strain) || 0));
      this._strain = next;
      this._rig.dataset.strain = String(next);
      this._applySvgMood();
      this.dispatchEvent(new CustomEvent("whale-strain", {
        bubbles: true,
        composed: true,
        detail: { mood: this._mood, strain: next }
      }));
    }

    setMood(mood, options = {}) {
      if (!this._registryReady) {
        // Applied once assets/moods.json has loaded (or failed to).
        this._pendingMood = { mood, options };
        return mood ?? this._defaultMood();
      }
      const next = this._resolveMood(mood ?? this._defaultMood());
      this._clearThinkTimers();
      this._mood = next;
      this._strain = 0;
      this._rig.dataset.mood = next;
      this.dataset.mood = next;
      this._rig.dataset.strain = "0";
      this._applySvgMood();

      // Moods with strain variants escalate through them (thinking: chin tap, then overthinking).
      const strains = STRAIN_DELAYS.slice(0, this._maxStrain());
      if (strains.length) {
        if (this._motionQuery.matches) {
          this._setStrain(1);
        } else {
          strains.forEach((delay, index) => {
            this._thinkTimers.push(window.setTimeout(() => this._setStrain(index + 1), delay));
          });
        }
      }

      if (options.announce !== false) {
        this.say(this._findMood(next)?.line || this._findMood(this._defaultMood())?.line);
      }

      this.dispatchEvent(new CustomEvent("whale-mood", {
        bubbles: true,
        composed: true,
        detail: { mood: next }
      }));
      return next;
    }

    _onMotionChange() {
      this._syncMotionPreference();
    }

    _syncMotionPreference() {
      try {
        const doc = this._object.contentDocument;
        if (doc && doc.documentElement) {
          doc.documentElement.classList.toggle("reduce-motion", this._motionQuery.matches);
        }
      } catch (error) {}
    }

    _setSvgPaused(paused) {
      try {
        const doc = this._object.contentDocument;
        if (doc && doc.documentElement) {
          doc.documentElement.classList.toggle("is-paused", Boolean(paused));
        }
      } catch (error) {}
    }

    _startInertia(vx, vy) {
      let velocityX = Math.max(-1.7, Math.min(1.7, vx));
      let velocityY = Math.max(-1.7, Math.min(1.7, vy));
      cancelAnimationFrame(this._inertiaFrame);
      const bounds = this._getBounds();

      const frame = () => {
        velocityX *= 0.94;
        velocityY *= 0.94;
        let nextX = this._position.x + velocityX * 16;
        let nextY = this._position.y + velocityY * 16;

        if (nextX <= bounds.minX) {
          nextX = bounds.minX;
          velocityX = Math.abs(velocityX) * 0.52;
        } else if (nextX >= bounds.maxX) {
          nextX = bounds.maxX;
          velocityX = -Math.abs(velocityX) * 0.52;
        }

        if (nextY <= bounds.minY) {
          nextY = bounds.minY;
          velocityY = Math.abs(velocityY) * 0.52;
        } else if (nextY >= bounds.maxY) {
          nextY = bounds.maxY;
          velocityY = -Math.abs(velocityY) * 0.52;
        }

        this._position = { x: nextX, y: nextY };
        this._applyPosition(false);

        if (Math.hypot(velocityX, velocityY) > 0.012) {
          this._inertiaFrame = requestAnimationFrame(frame);
        } else {
          this._inertiaFrame = null;
          this._applyPosition(true);
        }
      };

      this._inertiaFrame = requestAnimationFrame(frame);
    }

    _onClick(event) {
      if (this._suppressClick) {
        this._suppressClick = false;
        event.preventDefault();
        return;
      }
      this.speak();
    }

    _onKeyDown(event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (!event.repeat) this.speak();
        return;
      }

      const step = event.shiftKey ? 48 : 18;
      let dx = 0;
      let dy = 0;
      if (event.key === "ArrowLeft") dx = -step;
      else if (event.key === "ArrowRight") dx = step;
      else if (event.key === "ArrowUp") dy = -step;
      else if (event.key === "ArrowDown") dy = step;
      else if (event.key === "Home") {
        event.preventDefault();
        this.resetPosition(true);
        return;
      } else return;

      event.preventDefault();
      if (this._inertiaFrame) cancelAnimationFrame(this._inertiaFrame);
      this._inertiaFrame = null;
      const next = this._clampPosition(this._position.x + dx, this._position.y + dy);
      this._position = next;
      this._applyPosition(true);
      this._closeBubble();
    }

    _onResize() {
      if (!this._positioned) return;
      const oldViewport = { ...this._viewport };
      const oldSize = { ...this._size };
      const oldPosition = { ...this._position };
      const rightGap = oldViewport.w - oldPosition.x - oldSize.w;
      const bottomGap = oldViewport.h - oldPosition.y - oldSize.h;
      const leftGap = oldPosition.x;
      const topGap = oldPosition.y;

      this._measure();
      this._viewport = this._viewportSize();

      let x = oldPosition.x;
      let y = oldPosition.y;
      if (rightGap <= 32) x = this._viewport.w - this._size.w - Math.max(0, rightGap);
      else if (leftGap <= 32) x = leftGap;
      if (bottomGap <= 32) y = this._viewport.h - this._size.h - Math.max(0, bottomGap);
      else if (topGap <= 32) y = topGap;

      this._position = { x, y };
      this._applyPosition(true);
    }

    _closeBubble() {
      clearTimeout(this._speechTimer);
      this._rig.classList.remove("is-speaking");
    }

    say(text, duration = 6200) {
      const message = typeof text === "string" && text.trim()
        ? text.trim()
        : LINES[this._lineIndex++ % LINES.length];
      clearTimeout(this._speechTimer);
      this._rig.classList.toggle("bubble-below", this._position.y < 172);
      this._rig.classList.add("is-speaking");
      this._bubbleText.textContent = message;
      const timeout = Math.max(3800, Math.min(11000, duration || message.length * 62));
      this._speechTimer = window.setTimeout(() => {
        this._rig.classList.remove("is-speaking");
      }, timeout);
      this.dispatchEvent(new CustomEvent("whale-speak", {
        bubbles: true,
        composed: true,
        detail: { text: message }
      }));
      return message;
    }

    speak(text) {
      return this.say(text);
    }

    feed() {
      this._fedCount += 1;
      const line = FEED_LINES[this._feedIndex++ % FEED_LINES.length];
      this.say(line, 6400);
      this._burstRice(14);
      this._rig.classList.remove("is-fed");
      void this._rig.offsetWidth;
      this._rig.classList.add("is-fed");
      window.setTimeout(() => this._rig.classList.remove("is-fed"), 820);
      this.dispatchEvent(new CustomEvent("whale-feed", {
        bubbles: true,
        composed: true,
        detail: { count: this._fedCount }
      }));
      return line;
    }

    _burstRice(count) {
      if (this._motionQuery.matches) return;
      for (let index = 0; index < count; index += 1) {
        const grain = document.createElement("span");
        grain.className = "rice-grain";
        grain.textContent = index % 4 === 0 ? "✦" : "🍚";
        const angle = (-Math.PI / 2) + (Math.random() - 0.5) * Math.PI * 1.4;
        const distance = 44 + Math.random() * 74;
        grain.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
        grain.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
        grain.style.setProperty("--rot", `${Math.round((Math.random() - 0.5) * 300)}deg`);
        grain.style.animationDelay = `${Math.random() * 130}ms`;
        grain.style.left = `${44 + Math.random() * 12}%`;
        grain.style.top = `${36 + Math.random() * 14}%`;
        this._rig.appendChild(grain);
        grain.addEventListener("animationend", () => grain.remove(), { once: true });
        window.setTimeout(() => grain.remove(), 1400);
      }
    }

    resetPosition(announce = false) {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch (error) {}
      if (this._inertiaFrame) cancelAnimationFrame(this._inertiaFrame);
      this._inertiaFrame = null;
      this._measure();
      this._position = this._defaultPosition();
      this._applyPosition(true);
      this._savePosition();
      if (announce) this.say("Back to the usual spot.");
      return { ...this._position };
    }
  }

  if (!customElements.get(TAG)) {
    customElements.define(TAG, DeepSeekMascot);
  }
})();
