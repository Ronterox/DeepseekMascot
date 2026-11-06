"""Control protocol shared by the mascot (server) and the `whalechan` CLI.

Transport: a Unix stream socket, one request per line, one JSON reply per line.
A request is either a JSON object, e.g. {"cmd": "say", "text": "Build passed"},
or a plain-text line, e.g. `say Build passed` or `react success`.

This module must stay free of GTK imports so the CLI starts instantly.
"""

import json
import os
import re
import shlex
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "assets" / "moods.json"
# Used when assets/moods.json is missing or unreadable.
FALLBACK_MOODS = ["neutral", "angry", "smug", "happy", "sad", "thinking", "sleepy", "dance"]


def load_moods(path=REGISTRY_PATH):
    """The mood registry built by tools/build_whale_chan.py: an ordered list of dicts."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, list):
        data = []
    moods = [m for m in data if isinstance(m, dict) and re.fullmatch(r"[a-z0-9-]+", str(m.get("name", "")))]
    if not moods:
        moods = [{"name": name, "default": name == "neutral", "slow": name == "sleepy",
                  "variants": ["0", "1", "2"] if name == "thinking" else []} for name in FALLBACK_MOODS]
    return moods


def strains(mood):
    """Strain levels above 0 that a registry mood has variants for (thinking: [1, 2])."""
    return sorted(int(v) for v in mood.get("variants") or [] if str(v).isdigit() and int(v) > 0)


MOOD_REGISTRY = load_moods()
MOODS = [m["name"] for m in MOOD_REGISTRY]
EVENTS = {
    # event: (mood, seconds before returning to neutral or None)
    "working": ("thinking", None),
    "success": ("happy", 8),
    "failure": ("sad", 10),
    "error": ("angry", 10),
    "attention": (None, None),
    "idle": ("neutral", None),
}
EVENT_ALIASES = {
    "start": "working", "thinking": "working", "busy": "working",
    "done": "success", "ok": "success", "pass": "success", "passed": "success",
    "fail": "failure", "failed": "failure",
    "crash": "error",
    "input": "attention", "waiting": "attention", "notify": "attention",
    "reset": "idle", "neutral": "idle",
}
COMMANDS = ["ping", "status", "say", "mood", "feed", "react", "show", "hide",
            "toggle", "home", "move", "sleep", "wake", "quit"]


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime else Path(f"/tmp/whalechan-{os.getuid()}")
    return base / "whalechan.sock"


def normalize_event(name):
    name = (name or "").strip().lower()
    return EVENT_ALIASES.get(name, name)


def parse_plain(line):
    """Turn `say hello there` / `mood happy 5` / `react fail tests broke` into a request."""
    try:
        words = shlex.split(line)
    except ValueError:
        words = line.split()
    if not words:
        return {}
    cmd, rest = words[0].lower(), words[1:]
    if cmd == "say":
        return {"cmd": "say", "text": " ".join(rest)}
    if cmd == "mood":
        req = {"cmd": "mood", "mood": rest[0] if rest else "neutral"}
        if len(rest) > 1:
            try:
                req["for"] = float(rest[1])
            except ValueError:
                pass
        return req
    if cmd == "move" and len(rest) >= 2:
        return {"cmd": "move", "x": rest[0], "y": rest[1]}
    if cmd == "react":
        return {"cmd": "react", "event": rest[0] if rest else "", "text": " ".join(rest[1:])}
    return {"cmd": cmd}
