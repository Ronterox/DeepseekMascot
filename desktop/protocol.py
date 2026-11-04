"""Control protocol shared by the mascot (server) and the `whalechan` CLI.

Transport: a Unix stream socket, one request per line, one JSON reply per line.
A request is either a JSON object, e.g. {"cmd": "say", "text": "Build passed"},
or a plain-text line, e.g. `say Build passed` or `react success`.

This module must stay free of GTK imports so the CLI starts instantly.
"""

import os
import shlex
from pathlib import Path

MOODS = ["neutral", "angry", "smug", "happy", "sad", "thinking"]
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
