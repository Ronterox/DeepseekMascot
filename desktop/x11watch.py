"""Watch the X11 desktop for Whale-chan.

Tracks the windows she can stand on (visible top edges, following moves live),
the active window (for app reactions and fullscreen detection), workspace
switches, and how long the user has been idle (MIT-SCREEN-SAVER via libXss).

Events come from a dedicated python-xlib connection driven by the GLib main
loop. Moves and resizes update cached geometry straight from ConfigureNotify;
the window list is only rebuilt when stacking or mapping changes.
"""

import ctypes
import ctypes.util

from gi.repository import GLib
from Xlib import X, Xatom, display

IGNORED_TYPES = {"_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK",
                 "_NET_WM_WINDOW_TYPE_SPLASH", "_NET_WM_WINDOW_TYPE_NOTIFICATION",
                 "_NET_WM_WINDOW_TYPE_TOOLBAR", "_NET_WM_WINDOW_TYPE_MENU",
                 "_NET_WM_WINDOW_TYPE_UTILITY"}
ALL_DESKTOPS = 0xFFFFFFFF


class IdleMonitor:
    """Milliseconds since the last keyboard/mouse input, from libXss."""

    class _Info(ctypes.Structure):
        _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int), ("kind", ctypes.c_int),
                    ("til_or_since", ctypes.c_ulong), ("idle", ctypes.c_ulong),
                    ("event_mask", ctypes.c_ulong)]

    def __init__(self):
        self._ok = False
        try:
            xlib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
            xss = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1")
            xlib.XOpenDisplay.restype = ctypes.c_void_p
            xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            xlib.XDefaultRootWindow.restype = ctypes.c_ulong
            xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(self._Info)
            xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(self._Info)]
            self._dpy = xlib.XOpenDisplay(None)
            if not self._dpy:
                return
            self._root = xlib.XDefaultRootWindow(self._dpy)
            self._info = xss.XScreenSaverAllocInfo()
            self._xss = xss
            self._ok = True
        except OSError:
            pass

    def idle_ms(self):
        if not self._ok:
            return None
        if not self._xss.XScreenSaverQueryInfo(self._dpy, self._root, self._info):
            return None
        return int(self._info.contents.idle)


class Window:
    """Cached facts about one managed client window."""

    __slots__ = ("client", "frame", "ox", "oy", "dw", "dh", "frame_ext", "gtk_ext",
                 "fx", "fy", "fw", "fh", "wm_class", "title", "states", "desktop", "kind")

    def rect(self):
        """Visible rectangle: client area plus WM decorations minus CSD shadows."""
        l, r, t, b = self.frame_ext
        gl, gr, gt, gb = self.gtk_ext
        cx, cy = self.fx + self.ox, self.fy + self.oy
        cw, ch = self.fw - self.dw, self.fh - self.dh
        return (cx - l + gl, cy - t + gt, cw + l + r - gl - gr, ch + t + b - gt - gb)

    @property
    def fullscreen(self):
        return "_NET_WM_STATE_FULLSCREEN" in self.states

    @property
    def maximized(self):
        return {"_NET_WM_STATE_MAXIMIZED_VERT", "_NET_WM_STATE_MAXIMIZED_HORZ"} <= self.states

    @property
    def hidden(self):
        return "_NET_WM_STATE_HIDDEN" in self.states


class X11Watch:
    def __init__(self, ignore_classes=("whalechan",), on_windows=None, on_active=None, on_desktop=None):
        self.d = display.Display()
        self.d.set_error_handler(lambda *_args: None)  # windows vanish all the time
        self.root = self.d.screen().root
        self.ignore = {c.lower() for c in ignore_classes}
        self.on_windows = on_windows or (lambda: None)
        self.on_active = on_active or (lambda _info: None)
        self.on_desktop = on_desktop or (lambda _old, _new: None)
        self._atoms = {}
        self._names = {}
        self.windows = {}          # client xid -> Window
        self.by_frame = {}         # frame xid -> Window
        self.stacking = []         # client xids, bottom to top
        self.active_xid = None
        self.desktop = self._current_desktop()
        self._refresh_pending = False
        self.idle = IdleMonitor()
        self.root.change_attributes(event_mask=X.PropertyChangeMask | X.SubstructureNotifyMask)
        self._refresh()
        self._set_active(self._prop_window(self.root, "_NET_ACTIVE_WINDOW"), notify=False)
        self.d.flush()
        self._io = GLib.io_add_watch(self.d.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_io)

    # -- atoms and properties ------------------------------------------------
    def atom(self, name):
        value = self._atoms.get(name)
        if value is None:
            value = self.d.intern_atom(name)
            self._atoms[name] = value
            self._names[value] = name
        return value

    def atom_name(self, value):
        name = self._names.get(value)
        if name is None:
            try:
                name = self.d.get_atom_name(value)
            except Exception:  # noqa: BLE001
                name = ""
            self._names[value] = name
        return name

    def _prop(self, win, name, kind=X.AnyPropertyType):
        try:
            prop = win.get_full_property(self.atom(name), kind)
        except Exception:  # noqa: BLE001
            return None
        return prop.value if prop else None

    def _prop_window(self, win, name):
        value = self._prop(win, name)
        return int(value[0]) if value is not None and len(value) else None

    def _current_desktop(self):
        value = self._prop(self.root, "_NET_CURRENT_DESKTOP")
        return int(value[0]) if value is not None and len(value) else 0

    def _title(self, win):
        value = self._prop(win, "_NET_WM_NAME", self.atom("UTF8_STRING"))
        if value is None:
            value = self._prop(win, "WM_NAME", Xatom.STRING)
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value or "")

    # -- window bookkeeping ------------------------------------------------------
    def _load(self, xid):
        win = self.d.create_resource_object("window", xid)
        info = self.windows.get(xid) or Window()
        info.client = xid
        try:
            if not getattr(info, "frame", None):
                frame = win
                while True:
                    tree = frame.query_tree()
                    if tree.parent.id == self.root.id:
                        break
                    frame = tree.parent
                info.frame = frame.id
                cls = win.get_wm_class() or ("", "")
                info.wm_class = (cls[0] or "", cls[1] or "")
                win.change_attributes(event_mask=X.PropertyChangeMask)
            frame = self.d.create_resource_object("window", info.frame)
            fg = frame.get_geometry()
            cg = win.get_geometry()
        except Exception:  # noqa: BLE001
            return None
        info.fx, info.fy, info.fw, info.fh = fg.x, fg.y, fg.width, fg.height
        if info.frame == xid:
            info.ox = info.oy = info.dw = info.dh = 0
        else:
            info.ox, info.oy = cg.x, cg.y
            info.dw, info.dh = fg.width - cg.width, fg.height - cg.height
        fe = self._prop(win, "_NET_FRAME_EXTENTS")
        ge = self._prop(win, "_GTK_FRAME_EXTENTS")
        info.frame_ext = tuple(int(v) for v in fe[:4]) if fe is not None and len(fe) >= 4 else (0, 0, 0, 0)
        info.gtk_ext = tuple(int(v) for v in ge[:4]) if ge is not None and len(ge) >= 4 else (0, 0, 0, 0)
        states = self._prop(win, "_NET_WM_STATE")
        info.states = {self.atom_name(a) for a in states} if states is not None else set()
        desktop = self._prop(win, "_NET_WM_DESKTOP")
        info.desktop = int(desktop[0]) if desktop is not None and len(desktop) else ALL_DESKTOPS
        kinds = self._prop(win, "_NET_WM_WINDOW_TYPE")
        info.kind = self.atom_name(kinds[0]) if kinds is not None and len(kinds) else "_NET_WM_WINDOW_TYPE_NORMAL"
        info.title = self._title(win)
        return info

    def _refresh(self):
        self._refresh_pending = False
        stacking = self._prop(self.root, "_NET_CLIENT_LIST_STACKING")
        xids = [int(x) for x in stacking] if stacking is not None else []
        windows, by_frame = {}, {}
        for xid in xids:
            info = self._load(xid)
            if info is None:
                continue
            windows[xid] = info
            by_frame[info.frame] = info
        self.windows, self.by_frame, self.stacking = windows, by_frame, [x for x in xids if x in windows]
        return False

    def _schedule_refresh(self):
        if not self._refresh_pending:
            self._refresh_pending = True
            GLib.idle_add(self._refresh_and_notify)

    def _refresh_and_notify(self):
        self._refresh()
        self.on_windows()
        return False

    def _set_active(self, xid, notify=True):
        self.active_xid = xid or None
        if notify:
            self.on_active(self.active())

    # -- public queries ------------------------------------------------------------
    def on_current_desktop(self, info):
        return info.desktop in (ALL_DESKTOPS, self.desktop)

    def surfaces(self):
        """Windows she could stand on, topmost first: list of (client xid, rect, Window)."""
        out = []
        for xid in reversed(self.stacking):
            info = self.windows.get(xid)
            if (info is None or info.hidden or info.kind in IGNORED_TYPES
                    or not self.on_current_desktop(info)
                    or info.wm_class[0].lower() in self.ignore or info.wm_class[1].lower() in self.ignore):
                continue
            out.append((xid, info.rect(), info))
        return out

    def active(self):
        info = self.windows.get(self.active_xid) if self.active_xid else None
        if info is None or not self.on_current_desktop(info):
            return None
        return {
            "xid": info.client,
            "instance": info.wm_class[0],
            "class": info.wm_class[1],
            "title": info.title,
            "fullscreen": info.fullscreen,
            "rect": info.rect(),
        }

    def idle_ms(self):
        return self.idle.idle_ms()

    # -- events ------------------------------------------------------------------
    def _on_io(self, _fd, _cond):
        geometry_changed = False
        active_changed = False
        try:
            while self.d.pending_events():
                ev = self.d.next_event()
                kind = ev.type
                if kind == X.ConfigureNotify:
                    info = self.by_frame.get(ev.window.id)
                    if info is not None:
                        info.fx, info.fy, info.fw, info.fh = ev.x, ev.y, ev.width, ev.height
                        geometry_changed = True
                elif kind in (X.MapNotify, X.UnmapNotify, X.DestroyNotify):
                    self._schedule_refresh()
                elif kind == X.PropertyNotify:
                    name = self.atom_name(ev.atom)
                    if ev.window.id == self.root.id:
                        if name == "_NET_CLIENT_LIST_STACKING":
                            self._schedule_refresh()
                        elif name == "_NET_ACTIVE_WINDOW":
                            self.active_xid = self._prop_window(self.root, "_NET_ACTIVE_WINDOW") or None
                            active_changed = True
                        elif name == "_NET_CURRENT_DESKTOP":
                            old, self.desktop = self.desktop, self._current_desktop()
                            if old != self.desktop:
                                self.on_desktop(old, self.desktop)
                                geometry_changed = True
                                active_changed = True
                    else:
                        info = self.windows.get(ev.window.id)
                        if info is None:
                            continue
                        win = self.d.create_resource_object("window", info.client)
                        if name == "_NET_WM_STATE":
                            states = self._prop(win, "_NET_WM_STATE")
                            info.states = {self.atom_name(a) for a in states} if states is not None else set()
                            geometry_changed = True
                            active_changed |= info.client == self.active_xid
                        elif name == "_NET_WM_DESKTOP":
                            desktop = self._prop(win, "_NET_WM_DESKTOP")
                            info.desktop = int(desktop[0]) if desktop is not None and len(desktop) else ALL_DESKTOPS
                            geometry_changed = True
                        elif name in ("_NET_WM_NAME", "WM_NAME") and info.client == self.active_xid:
                            info.title = self._title(win)
                            active_changed = True
                        elif name in ("_NET_FRAME_EXTENTS", "_GTK_FRAME_EXTENTS"):
                            self._schedule_refresh()
        except Exception as exc:  # noqa: BLE001
            print(f"whalechan: X11 watch error: {exc}")
        if geometry_changed:
            self.on_windows()
        if active_changed:
            self.on_active(self.active())
        return True

    def close(self):
        if self._io:
            GLib.source_remove(self._io)
            self._io = None
        try:
            self.d.close()
        except Exception:  # noqa: BLE001
            pass
