#!/usr/bin/env python3
"""Keep you in your work loop.

Every so often Whale-chan brings up a random open `anx` task (not @done). She
also watches which window has focus (in a terminal, the focused tmux session
counts as its own place), keeps your last 100 visits, finds your most common
loop in them (say DeepseekMascot -> RemCLI -> TeaWithGPT -> YouTube ->
HarnessTools) and, when the next stop after where you are has been neglected
for a while, tells you to go check it.

Run `scripts/tasks.py --report` to see what she has learned.
"""

import json
import os
import random
import re
import shlex
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHALECHAN = str(ROOT / "desktop" / "whalechan")
STATE_PATH = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "whalechan" / "tasks.json"
DEFAULT_TASKS = Path(os.environ.get("DOINGO_PATH", Path.home() / "Documents/Projects/MarkdownProjects/ANX/doing"))

POLL = 2            # seconds between focus checks
MIN_STAY = 5        # focus shorter than this is passing through, not a visit
SETTLE = 60         # be somewhere this long before she suggests moving on
HISTORY = 100       # visits kept for finding the loop
MAX_LOOP = 8        # longest loop considered
IDLE_AFTER = 120    # say nothing once you've been away from the keyboard this long
TALK_GAP = 180      # at least this long between any two lines
FORGET_AFTER = 7 * 86400

TERMINALS = {"kitty", "alacritty", "gnome-terminal", "xterm", "urxvt", "foot", "org.wezfurlong.wezterm",
             "konsole", "terminator", "st-256color", "tilix", "xfce4-terminal"}
BROWSERS = {"firefox", "chromium", "google-chrome", "brave-browser", "vivaldi-stable", "librewolf", "zen"}
SITES = ["YouTube Music", "YouTube", "Twitch", "Reddit", "Discord", "GitHub", "Gmail", "ChatGPT", "Claude",
         "WhatsApp", "Telegram", "Netflix", "Twitter", "X"]
IGNORED = {"", "gjs", "gnome-shell"}

TASK_LINES = [
    ("thinking", "Did you forget about {task}?"),
    ("smug", "It's been {age} since you started {task}, huh?"),
    ("happy", "We should try doing {task} today!"),
    ("neutral", "Hey… {task} is still waiting for you."),
    ("thinking", "What about {task}? Just saying."),
    ("smug", "Remember {task}? Because I do."),
    ("happy", "Five minutes on {task}? I'll cheer for you!"),
    ("sad", "{task} has been sitting there for {age}. It's lonely."),
    ("dance", "Ooh, {task}! Today's the day, I can feel it."),
]
LOOP_LINES = [
    "Hey, you should probably check {place}. It's been {ago} since you checked it out.",
    "{place} hasn't seen you in {ago}…",
    "Loop time! {place} is next. Last visit: {ago} ago.",
    "Weren't you going to {place} after this? It's been {ago}.",
    "Don't break the rhythm. {place} next!",
    "{ago} without {place}. Suspicious.",
    "Psst. {place}. {ago}. Just saying.",
]
LATE_LINES = [  # the next stop is more than three times overdue
    "{place}! It's been {ago}! Go go go!",
    "Did {place} do something to you? {ago}!",
    "{ago} since {place}. I'm not mad. Okay, I'm a little mad.",
]


def say(text, mood=None):
    """Speak, borrowing a mood only when she isn't busy with another one (thinking, waiting…)."""
    try:
        status = json.loads(subprocess.run([WHALECHAN, "--json", "status"], capture_output=True,
                                           text=True, timeout=5).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    if not status.get("ok") or status.get("sleeping") or not status.get("visible"):
        return False
    cmd = [WHALECHAN, "-q", "say", text]
    if mood and mood != "neutral" and status.get("mood") == "neutral":
        cmd += ["-m", mood, "--for", "8"]
    try:
        subprocess.run(cmd, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def ask_settings():
    defaults = {"TASKS_FILE": str(DEFAULT_TASKS / "what_was_I_doing.txt"), "TASK_EVERY": "20", "LOOP_AFTER": "15"}
    out = subprocess.run([WHALECHAN, "input", "Tasks", *(f"{k}={v}" for k, v in defaults.items())],
                         stdout=subprocess.PIPE, text=True)
    if out.returncode:
        sys.exit(out.returncode)
    values = dict(defaults)
    for line in out.stdout.splitlines():
        name, _, value = shlex.split(line)[1].partition("=")
        values[name] = value
    try:
        return Path(values["TASKS_FILE"]).expanduser(), int(values["TASK_EVERY"]) * 60, int(values["LOOP_AFTER"]) * 60
    except ValueError:
        say("Tasks: TASK_EVERY and LOOP_AFTER are whole minutes.", "sad")
        sys.exit(1)


# -- tasks ---------------------------------------------------------------------------------
TASK_RE = re.compile(r"^(\d\d/\d\d/\d\d \d\d:\d\d:\d\d) ║ (.+)$")


def open_tasks(path):
    """(started, text) for every line of the doing file without @done."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    tasks = []
    for line in lines:
        m = TASK_RE.match(line.strip())
        if not m or "@done" in m[2]:
            continue
        tag, sep, text = m[2].partition(":")
        if not sep or not re.fullmatch(r"\w+", tag.strip()):
            text = m[2]
        text = text.split(" // ")[0].strip()
        if len(text) > 70:
            text = text[:70].rsplit(" ", 1)[0] + "…"
        try:
            tasks.append((datetime.strptime(m[1], "%d/%m/%y %H:%M:%S").timestamp(), text))
        except ValueError:
            continue
    return tasks


def human(seconds):
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' * (minutes != 1)}"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hour{'s' * (hours != 1)}"
    return f"{hours // 24} days"


# -- where you are -------------------------------------------------------------------------
class Focus:
    def __init__(self):
        from Xlib import X, display
        self.X = X
        self.d = display.Display()
        self.root = self.d.screen().root
        self.active = self.d.intern_atom("_NET_ACTIVE_WINDOW")
        self.name = self.d.intern_atom("_NET_WM_NAME")

    def place(self):
        """A name for where your focus is, or None for nothing worth tracking."""
        try:
            prop = self.root.get_full_property(self.active, self.X.AnyPropertyType)
            if not prop or not prop.value[0]:
                return None
            win = self.d.create_resource_object("window", prop.value[0])
            wm_class = (win.get_wm_class() or ("", ""))[1]
            title = win.get_full_property(self.name, 0)
            title = title.value if title else (win.get_wm_name() or "")
            title = title.decode("utf-8", "replace") if isinstance(title, bytes) else title
        except Exception:  # noqa: BLE001 - windows vanish between requests
            return None
        cls = wm_class.lower()
        if cls in IGNORED or cls.startswith("whale"):
            return None
        if cls in TERMINALS:
            return tmux_session() or wm_class
        if cls in BROWSERS:
            return site(title) or wm_class
        return wm_class[:1].upper() + wm_class[1:]


def tmux_session():
    try:
        out = subprocess.run(["tmux", "list-clients", "-F", "#{client_flags}\t#{client_session}"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        flags, _, session = line.partition("\t")
        if "focused" in flags.split(","):
            return session
    return None


def site(title):
    """'Song - Artist | YouTube Music — Original profile — Mozilla Firefox' -> 'YouTube Music'."""
    title = re.split(r" — | - (?:Google Chrome|Chromium|Brave|Vivaldi)$", title)[0]
    title = re.sub(r"^\(\d+\)\s*", "", title)
    parts = [p.strip() for p in re.split(r" [-|·/] ", title) if p.strip()]
    for part in reversed(parts):
        for name in SITES:
            if part.lower() == name.lower():
                return name
    return parts[-1] if parts else None


# -- the loop ------------------------------------------------------------------------------
def top_loop(history):
    """The cycle (A -> B -> ... -> back to A) that accounts for the most visits."""
    counts = Counter()
    for i, start in enumerate(history):
        for j in range(i + 1, min(len(history), i + MAX_LOOP + 1)):
            if history[j] == start:
                cycle = history[i:j]
                if len(cycle) > 1 and len(set(cycle)) == len(cycle):
                    k = cycle.index(min(cycle))
                    counts[tuple(cycle[k:] + cycle[:k])] += 1
                break
    best = max(counts, key=lambda c: counts[c] * len(c), default=None)
    return list(best) if best and counts[best] > 1 else None


def next_stop(history, here):
    loop = top_loop(history)
    if loop and here in loop:
        return loop[(loop.index(here) + 1) % len(loop)]
    after = Counter(b for a, b in zip(history, history[1:]) if a == here)
    return after.most_common(1)[0][0] if after else None


# -- state ---------------------------------------------------------------------------------
def load_state():
    try:
        state = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict) or not isinstance(state.get("history", []), list) \
            or not isinstance(state.get("last_seen", {}), dict):
        state = {}
    return {"history": state.get("history", []), "last_seen": state.get("last_seen", {})}


def save_state(state):
    cutoff = time.time() - FORGET_AFTER
    state["last_seen"] = {k: v for k, v in state["last_seen"].items() if v > cutoff or k in state["history"]}
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(STATE_PATH)
    except OSError as exc:
        print(f"tasks: could not save state: {exc}", file=sys.stderr)


def report():
    state, now = load_state(), time.time()
    print("Places, most neglected first:")
    for place, seen in sorted(state["last_seen"].items(), key=lambda kv: kv[1]):
        print(f"  {human(now - seen):>12} ago  {place}")
    loop = top_loop(state["history"])
    print("Loop:", " -> ".join(loop + loop[:1]) if loop else "not enough history yet")
    print("Last visits:", " -> ".join(state["history"][-12:]))
    tasks = open_tasks(DEFAULT_TASKS / "what_was_I_doing.txt")
    print(f"Open tasks: {len(tasks)}")


def main():
    if "--report" in sys.argv:
        report()
        return 0
    tasks_file, task_every, loop_after = ask_settings()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    sys.path.insert(0, str(ROOT / "desktop"))
    try:
        from x11watch import IdleMonitor
        idle = IdleMonitor()
    except ImportError:
        idle = None
    focus = Focus()
    state = load_state()
    here, since = None, time.time()
    last_talk, last_save, nudged, recent_tasks, away = 0.0, 0.0, {}, [], False
    next_task = time.time() + random.uniform(0.25, 1.0) * task_every
    try:
        while True:
            time.sleep(POLL)
            now = time.time()
            if idle and (idle.idle_ms() or 0) > IDLE_AFTER * 1000:
                away = True
                continue
            if away:  # back from a break: settle in before she says anything
                away, since, last_talk = False, now, now

            place = focus.place()
            if place and place != here:
                if here and now - since >= MIN_STAY and state["history"][-1:] != [here]:
                    state["history"] = (state["history"] + [here])[-HISTORY:]
                    save_state(state)
                here, since = place, now
            if here and now - since >= MIN_STAY:
                state["last_seen"][here] = now
            if now - last_save > 60:
                save_state(state)
                last_save = now

            if now - last_talk < TALK_GAP:
                continue
            if now >= next_task:
                next_task = now + random.uniform(0.5, 1.5) * task_every
                fresh = [t for t in open_tasks(tasks_file) if t[1] not in recent_tasks] or open_tasks(tasks_file)
                if fresh:
                    started, task = random.choice(fresh)
                    recent_tasks = (recent_tasks + [task])[-5:]
                    mood, line = random.choice(TASK_LINES)
                    if say(line.format(task=f"“{task}”", age=human(now - started)), mood):
                        last_talk = now
                continue
            target = next_stop(state["history"], here) if here and now - since >= SETTLE else None
            seen = state["last_seen"].get(target)
            if target and target != here and seen and now - seen >= loop_after \
                    and now - nudged.get(target, 0) >= loop_after:
                late = now - seen >= 3 * loop_after
                line = random.choice(LATE_LINES if late else LOOP_LINES)
                nudged[target] = now
                if say(line.format(place=target, ago=human(now - seen)), "angry" if late else "waiting"):
                    last_talk = now
    finally:
        save_state(state)


if __name__ == "__main__":
    sys.exit(main())
