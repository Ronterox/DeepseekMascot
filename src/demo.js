(() => {
  "use strict";

  const mascot = document.querySelector("deepseek-mascot");
  if (!mascot) return;

  const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve"];

  let buttons = [];
  const buttonBox = document.querySelector(".mood-buttons");
  const moodName = document.getElementById("mood-name");
  const moodWord = document.getElementById("mood-word");
  const consoleEl = document.querySelector(".console");
  let currentMood = "neutral";

  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);

  const rule = (selector, props) => {
    const body = Object.entries(props)
      .filter(([, value]) => value != null && value !== "")
      .map(([prop, value]) => `${prop}: ${value};`)
      .join(" ");
    return body ? `${selector} { ${body} }` : "";
  };

  // The default mood's accents replace the :root ones; moods without a value keep them.
  const themeCss = (moods) => moods.flatMap((mood) => {
    const theme = mood.theme || {};
    return [
      rule(mood.default ? ":root" : `html[data-mood="${mood.name}"]`, {
        "--accent": theme.accent,
        "--accent-deep": theme.accentDeep,
        "--accent-soft": theme.accentSoft
      }),
      rule(`.mood-${mood.name}`, { "--btn": theme.button })
    ];
  }).filter(Boolean).join("\n");

  const buttonHtml = (mood) => `
          <button class="mood-btn mood-${mood.name}" type="button" data-mood="${mood.name}" aria-pressed="false">
            <span class="mood-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">${mood.icon || ""}</svg>
            </span>
            <span class="mood-label">${escapeHtml(mood.label || mood.name)}</span>
          </button>
`;

  const countWord = (count) => NUMBER_WORDS[count] || String(count);

  const popWord = () => {
    if (!moodWord) return;
    moodWord.classList.remove("changing");
    void moodWord.offsetWidth;
    moodWord.classList.add("changing");
  };

  const syncButtons = () => {
    buttons.forEach((button) => {
      const active = button.dataset.mood === currentMood;
      button.setAttribute("aria-pressed", String(active));
    });
  };

  const applyMood = (mood, options = {}) => {
    currentMood = mood || "neutral";
    document.documentElement.dataset.mood = currentMood;
    consoleEl?.setAttribute("data-mood", currentMood);

    if (moodName) moodName.textContent = currentMood;
    if (moodWord) {
      moodWord.textContent = currentMood;
      moodWord.classList.toggle("long", currentMood.length > 8);
      if (options.pop !== false) popWord();
    }

    syncButtons();
  };

  const buildMoods = (moods) => {
    let style = document.getElementById("mood-theme");
    if (!style) {
      style = document.createElement("style");
      style.id = "mood-theme";
      document.head.appendChild(style);
    }
    style.textContent = themeCss(moods);

    const choices = moods.filter((mood) => mood.button);
    if (buttonBox) {
      buttonBox.innerHTML = choices.map(buttonHtml).join("");
      buttonBox.style.setProperty("--mood-count", String(Math.max(1, choices.length)));
      buttons = [...buttonBox.querySelectorAll(".mood-btn")];
      buttons.forEach((button) => {
        button.addEventListener("click", () => {
          const mood = button.dataset.mood;
          const next = mascot.mood === mood ? undefined : mood;
          mascot.setMood(next);
        });
      });
    }
    syncButtons();

    const count = document.getElementById("mood-count");
    if (count) count.textContent = `${String(choices.length).padStart(2, "0")} moods`;
    const word = document.getElementById("mood-count-word");
    if (word) word.textContent = countWord(choices.length);
    const labels = choices.map((mood) => (mood.label || mood.name).toLowerCase());
    const description = document.querySelector('meta[name="description"]');
    if (description && labels.length) {
      const list = labels.length > 1
        ? `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`
        : labels[0];
      description.content = `A draggable DeepSeek whale maid with ${countWord(labels.length)} moods: ${list}.`;
    }
  };

  mascot.addEventListener("whale-mood", (event) => {
    applyMood(event.detail.mood);
  });

  // Word shown for each strain level of the moods that escalate.
  const STRAIN_LABELS = {
    thinking: ["thinking", "thinking", "overthinking"],
    waiting: ["waiting", "impatient", "fuming"]
  };

  mascot.addEventListener("whale-strain", (event) => {
    const labels = STRAIN_LABELS[event.detail.mood];
    if (!labels) return;
    const label = labels[Math.min(event.detail.strain, labels.length - 1)];
    if (moodName) moodName.textContent = label;
    if (moodWord) {
      moodWord.textContent = label;
      moodWord.classList.toggle("long", label.length > 8);
      popWord();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const initialMood = params.get("mood") || undefined;
  applyMood(initialMood, { pop: false });

  customElements.whenDefined("deepseek-mascot").then(() => {
    mascot.moodsReady?.then(buildMoods);
    if (typeof mascot.setMood === "function") {
      mascot.setMood(initialMood, { announce: false });
    }
  });
})();
