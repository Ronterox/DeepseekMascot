# Mood editor

A local web editor for `moods/*.json` with a live preview. No build step or dependencies.

```sh
python3 tools/editor_server.py --open        # http://127.0.0.1:8765/editor/  (needs node for validation/builds)
```

Edits are compiled in the browser by the same `tools/moods.mjs` the build uses and swapped into the
inlined SVG (the block between `/* moods:begin */` and `/* moods:end */`). **Save** writes the mood
file (validated by the server first), **Build** saves everything and reruns
`tools/build_whale_chan.py`.

Keys: Ctrl+S save (Shift: save all), Ctrl+Z / Ctrl+Shift+Z undo/redo, Alt+1-5 tabs, Space play/pause,
H hand handles, P pivots, ↑/↓ in the mood list; timeline: ←/→ step (snap grid), K add stop at the
playhead, Del delete stops, Esc deselect.

## Files

| File               | Role                                                                          |
| ------------------ | ----------------------------------------------------------------------------- |
| `main.js`          | boot, live-compile loop, toolbar, save/build, dialogs, shortcuts              |
| `store.js`         | working copies vs. saved, selection `{id, variant}`, per-mood undo, `change` events |
| `model.js`         | pure helpers: scopes (mood / variant), inheritance lookups, layer logic       |
| `preview.js`       | SVG in a shadow root, CSS swap, playback (Web Animations), art-space overlay  |
| `inspector.js`     | variant bar, errors, tabs; `PANELS` registry                                  |
| `panels/*.js`      | `{id, label, render(el, api)}`: pose, face, motion, meta                      |
| `sidebar.js`       | mood list                                                                     |
| `timeline/model.js`   | pure: easing curves, transform parse/format, stop evaluation, time mapping, `choosePeriod` port |
| `timeline/actions.js` | timeline edits via the store (add/move/delete stops, mirror, convert, make local) |
| `timeline/panel.js`   | the timeline UI under the preview (rows, ruler, playhead, drags, hand-handle link) |
| `panels/track.js`  | inspector for the timeline selection (timing, tools, stop fields)             |
| `easing.js`        | easing field with presets and a cubic-bezier curve                            |
| `api.js`           | client for `tools/editor_server.py`                                           |

## Timeline

- One row per part with motion in the selected scope (tick "inherited" for the idle/base motion,
  read-only). All rows share one time axis: the mood loop (`meta.editor` bpm × counts, else the
  longest track); each row repeats its cycles with its delay/direction. Diamonds are stops; a stop
  with `t: [0, 100]` shows one diamond per percent and edits them together (split to separate).
- Click/drag the ruler or an empty lane to scrub (pauses and seeks every animation — the preview
  runs all animations on one clock); click a diamond to select + seek, Shift-click to multi-select,
  drag to move (snaps to the grid in absolute time, so beats line up across tracks), double-click a
  lane or press K to add a stop holding the interpolated value, drag a cycle flag to change the delay.
- Keyframe tracks edit mood-local keyframes only: library keyframes and inherited tracks ask for a
  local copy / override first. Structured transform fields rewrite only the stop you edit, in
  canonical `translate() rotate() scale()` order; anything else stays a raw string.
- Hand tracks: the preview's hand handle follows the track; dragging it on a stop moves that stop,
  elsewhere it adds one at the playhead. The faint line is the hand's path over a cycle.
- Mirror copies a track to the other side (hand x about `rig.mirrorX`; rotation/x-translation
  negated when both parts face the same way, detected from the art's transforms), optionally half
  a cycle later. "Convert to hand track" turns u/f keyframes into IK stops.
- The "bake" badge runs desktop/bake.py's `choose_period` on the visible animation durations and
  warns when tracks don't divide the mood loop or will be retimed.
