(() => {
  "use strict";

  const mascot = document.querySelector("deepseek-mascot");
  if (!mascot) return;

  const buttons = [...document.querySelectorAll(".mood-btn")];
  const moodName = document.getElementById("mood-name");
  const moodWord = document.getElementById("mood-word");
  const consoleEl = document.querySelector(".console");
  let currentMood = "neutral";

  const popWord = () => {
    if (!moodWord) return;
    moodWord.classList.remove("changing");
    void moodWord.offsetWidth;
    moodWord.classList.add("changing");
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

    buttons.forEach((button) => {
      const active = button.dataset.mood === currentMood;
      button.setAttribute("aria-pressed", String(active));
    });
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const mood = button.dataset.mood;
      const next = mascot.mood === mood ? "neutral" : mood;
      mascot.setMood(next);
    });
  });

  mascot.addEventListener("whale-mood", (event) => {
    applyMood(event.detail.mood);
  });

  mascot.addEventListener("whale-strain", (event) => {
    if (event.detail.mood !== "thinking") return;
    const level = event.detail.strain;
    const label = level >= 2 ? "overthinking" : "thinking";
    if (moodName) moodName.textContent = label;
    if (moodWord) {
      moodWord.textContent = label;
      moodWord.classList.toggle("long", label.length > 8);
      popWord();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const initialMood = params.get("mood") || "neutral";
  applyMood(initialMood, { pop: false });
  if (typeof mascot.setMood === "function") {
    mascot.setMood(initialMood, { announce: false });
  }
})();
