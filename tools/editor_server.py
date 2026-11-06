#!/usr/bin/env python3
"""Local server for the Whale-chan mood editor (editor/). Standard library only.

    python3 tools/editor_server.py [--port 8765] [--root <repo dir>] [--open]

Serves the repo statically (no caching) and a small JSON API on 127.0.0.1:

    GET    /api/state                  {moods: {name: mood}, defaults, keyframes, rig}
    PUT    /api/moods/<name>           body: mood JSON; validated with tools/compile_moods.mjs
    DELETE /api/moods/<name>           refuses the default mood
    POST   /api/moods/<name>/rename    body: {"to": "new-name", "mood": {...optional new content}}
    POST   /api/build                  runs tools/build_whale_chan.py -> {ok, stdout, stderr}

Mood files are written atomically in the same compact style as the hand-kept ones.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
WIDTH = 110
MAX_BODY = 4 << 20
LOCK = threading.Lock()

# Canonical key order per level; keys not listed keep their order after these.
MOOD_ORDER = ["name", "order", "default", "meta", "pose", "layers", "motion", "keyframes", "variants", "css"]
META_ORDER = ["label", "line", "button", "icon", "slow", "theme"]
THEME_ORDER = ["accent", "accentDeep", "accentSoft", "button", "bubble", "aura", "floorShadow",
               "desktopAccent", "desktopGlow", "variants"]
SCOPE_ORDER = ["pose", "layers", "motion", "css"]
POSE_ORDER = ["arms", "vars"]
ARMS_ORDER = ["l", "r", "fist"]
LAYERS_ORDER = ["show", "hide"]
ANIM_ORDER = ["keyframes", "stops", "duration", "easing", "delay", "iterations", "direction"]


def ordered(obj, order):
    if not isinstance(obj, dict):
        return obj
    head = {k: obj[k] for k in order if k in obj}
    head.update((k, v) for k, v in obj.items() if k not in head)
    return head


def order_scope(scope, order=SCOPE_ORDER):
    scope = ordered(scope, order)
    if isinstance(scope.get("pose"), dict):
        scope["pose"] = ordered(scope["pose"], POSE_ORDER)
        if isinstance(scope["pose"].get("arms"), dict):
            scope["pose"]["arms"] = ordered(scope["pose"]["arms"], ARMS_ORDER)
    if isinstance(scope.get("layers"), dict):
        scope["layers"] = ordered(scope["layers"], LAYERS_ORDER)
    if isinstance(scope.get("motion"), dict):
        scope["motion"] = {k: ordered(v, ANIM_ORDER) for k, v in scope["motion"].items()}
    return scope


def order_mood(mood):
    mood = order_scope(mood, MOOD_ORDER)
    meta = mood.get("meta")
    if isinstance(meta, dict):
        meta = ordered(meta, META_ORDER)
        if isinstance(meta.get("theme"), dict):
            theme = meta["theme"] = ordered(meta["theme"], THEME_ORDER)
            for key in ("desktopAccent", "desktopGlow"):  # RGB 0-1 floats; JS turns 1.0 into 1
                if isinstance(theme.get(key), list):
                    theme[key] = [float(x) if isinstance(x, int) and not isinstance(x, bool) else x for x in theme[key]]
        mood["meta"] = meta
    if isinstance(mood.get("variants"), dict):
        mood["variants"] = {k: order_scope(v) if isinstance(v, dict) else v for k, v in mood["variants"].items()}
    return mood


def compact(v):
    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))


def dump_mood(obj):
    """Indented JSON where any container that fits on its line (WIDTH chars) stays inline."""

    def emit(v, indent, prefix, top=False):
        flat = compact(v)
        if not isinstance(v, (dict, list)) or not v or (not top and indent + len(prefix) + len(flat) <= WIDTH):
            return flat
        pad = " " * (indent + 2)
        if isinstance(v, dict):
            items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: "
                     f"{emit(x, indent + 2, json.dumps(k, ensure_ascii=False) + ': ')}" for k, x in v.items()]
            return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
        items = [pad + emit(x, indent + 2, "") for x in v]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"

    return emit(obj, 0, "", top=True) + "\n"


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ApiError(Exception):
    def __init__(self, status, message, errors=None):
        super().__init__(message)
        self.status = status
        self.errors = errors or []


class Repo:
    def __init__(self, root):
        self.root = root
        self.moods = root / "moods"
        self.rig = root / "assets" / "rig.json"

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def mood_files(self):
        return sorted(p for p in self.moods.glob("*.json") if not p.name.startswith("_"))

    def mood_path(self, name):
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise ApiError(HTTPStatus.BAD_REQUEST, f"invalid mood name {name!r} (must match {NAME_RE.pattern})")
        return self.moods / f"{name}.json"

    def state(self):
        return {
            "moods": {p.stem: self.read(p) for p in self.mood_files()},
            "defaults": self.read(self.moods / "_defaults.json"),
            "keyframes": self.read(self.moods / "_keyframes.json"),
            "rig": self.read(self.rig),
        }

    def validate(self, write=None, remove=()):
        """Compile the would-be mood set (current files, minus `remove`, plus `write`) with node."""
        with tempfile.TemporaryDirectory(prefix="whale-moods-", dir=os.environ.get("TMPDIR")) as tmp:
            tmp = Path(tmp)
            for p in self.moods.glob("*.json"):
                if p.stem not in remove and not (write and p.stem in write):
                    shutil.copy(p, tmp / p.name)
            for name, text in (write or {}).items():
                (tmp / f"{name}.json").write_text(text, encoding="utf-8")
            cmd = ["node", str(self.root / "tools" / "compile_moods.mjs"), "--moods", str(tmp), "--rig", str(self.rig)]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root, timeout=60)
            except FileNotFoundError:
                raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "node is required to validate moods")
        if res.returncode:
            lines = [ln.strip() for ln in res.stderr.splitlines() if ln.strip()]
            errors = [ln for ln in lines if not ln.startswith("compile_moods:")] or lines
            raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid mood data", errors)

    def save(self, name, mood):
        path = self.mood_path(name)
        if not isinstance(mood, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "expected a mood object")
        if mood.get("name") != name:
            raise ApiError(HTTPStatus.BAD_REQUEST, f'"name" must be {name!r} (use rename to change it)')
        text = dump_mood(order_mood(mood))
        self.validate(write={name: text})
        created = not path.exists()
        atomic_write(path, text)
        return {"ok": True, "name": name, "created": created}

    def delete(self, name):
        path = self.mood_path(name)
        if not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, f"no mood {name!r}")
        if self.read(path).get("default"):
            raise ApiError(HTTPStatus.CONFLICT, f"{name!r} is the default mood and can't be deleted")
        self.validate(remove={name})
        path.unlink()
        return {"ok": True, "name": name}

    def rename(self, name, body):
        src = self.mood_path(name)
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, 'expected {"to": "<name>"}')
        to = body.get("to")
        dst = self.mood_path(to)
        if not src.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, f"no mood {name!r}")
        if to == name:
            raise ApiError(HTTPStatus.BAD_REQUEST, "new name equals the old one")
        if dst.exists():
            raise ApiError(HTTPStatus.CONFLICT, f"a mood named {to!r} already exists")
        mood = body.get("mood") or self.read(src)
        if not isinstance(mood, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "expected a mood object")
        mood = {**mood, "name": to}
        text = dump_mood(order_mood(mood))
        self.validate(write={to: text}, remove={name})
        atomic_write(dst, text)
        src.unlink()
        return {"ok": True, "name": to, "from": name}

    def build(self):
        cmd = [sys.executable, str(self.root / "tools" / "build_whale_chan.py")]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root, timeout=300)
        except subprocess.TimeoutExpired as err:
            return {"ok": False, "stdout": err.stdout or "", "stderr": "build timed out"}
        return {"ok": res.returncode == 0, "stdout": res.stdout, "stderr": res.stderr}


class Handler(SimpleHTTPRequestHandler):
    repo = None
    port = 0
    server_version = "WhaleEditor/1"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/") or (args and str(args[1])[:1] in "45"):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------ static files
    def translate_path(self, path):
        rel = unquote(urlsplit(path).path)
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        root = self.repo.root
        if any(p == ".." or p.startswith(".") or "\\" in p or "\0" in p for p in parts):
            return str(root / "\0denied")
        full = (root.joinpath(*parts)).resolve()
        if full != root and root not in full.parents:
            return str(root / "\0denied")
        return str(full)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        if path in ("", "/"):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/editor/")
            self.end_headers()
            return None
        if "\0denied" in self.translate_path(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_HEAD(self):
        if "\0denied" in self.translate_path(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

    def do_PUT(self):
        self.api("PUT", urlsplit(self.path).path)

    def do_POST(self):
        self.api("POST", urlsplit(self.path).path)

    def do_DELETE(self):
        self.api("DELETE", urlsplit(self.path).path)

    # ------------------------------------------------------------ API
    def send_json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def check_origin(self, method):
        """Only same-origin local pages may call the API (no DNS rebinding, no cross-site writes)."""
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if self.headers.get("Host") not in allowed:
            raise ApiError(HTTPStatus.FORBIDDEN, "bad Host header")
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc not in allowed:
            raise ApiError(HTTPStatus.FORBIDDEN, "cross-origin request refused")
        if method in ("PUT", "POST") and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "expected Content-Type: application/json")

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request too large")
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"null")
        except ValueError as err:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"invalid JSON: {err}")

    def api(self, method, path):
        try:
            self.check_origin(method)
            parts = [unquote(p) for p in path.split("/")[2:]]
            with LOCK:
                result = self.route(method, parts)
            self.send_json(HTTPStatus.OK, result)
        except ApiError as err:
            self.send_json(err.status, {"ok": False, "error": str(err), "errors": err.errors})
        except Exception as err:  # noqa: BLE001 - report anything else as a 500 to the editor
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False,
                           "error": f"{type(err).__name__}: {err}", "errors": []})

    def route(self, method, parts):
        repo = self.repo
        match method, parts:
            case "GET", ["state"]:
                return repo.state()
            case "PUT", ["moods", name]:
                return repo.save(name, self.body())
            case "DELETE", ["moods", name]:
                return repo.delete(name)
            case "POST", ["moods", name, "rename"]:
                return repo.rename(name, self.body())
            case "POST", ["build"]:
                return repo.build()
        raise ApiError(HTTPStatus.NOT_FOUND, f"no API route {method} /api/{'/'.join(parts)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=6767)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="repository directory")
    ap.add_argument("--open", action="store_true", help="open the editor in a browser")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "moods").is_dir() or not (root / "tools" / "compile_moods.mjs").is_file():
        sys.exit(f"editor_server: {root} doesn't look like the Whale-chan repo (no moods/ or tools/compile_moods.mjs)")
    Handler.repo = Repo(root)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *a, **kw: Handler(*a, directory=str(root), **kw))
    Handler.port = httpd.server_address[1]
    url = f"http://127.0.0.1:{Handler.port}/editor/"
    print(f"Whale-chan mood editor: {url}  (root {root})", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
