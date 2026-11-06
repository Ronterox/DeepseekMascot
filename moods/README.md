# Moods

Every Whale-chan mood is a JSON file here. `tools/moods.mjs` compiles them into the mood CSS
inside `assets/whale-chan.svg` and into the runtime registry `assets/moods.json`. The same
compiler runs in the browser editor, so editing these files and the editor are equivalent.

```sh
python3 tools/build_whale_chan.py          # rebuilds rig.json, the SVG and moods.json (needs node)
node tools/compile_moods.mjs               # just validate + print {"css", "registry", "poses"}
```

| File              | What it is                                                            |
| ----------------- | --------------------------------------------------------------------- |
| `<name>.json`     | one mood; the file name must equal `"name"`                           |
| `_defaults.json`  | baseline pose and the idle motion every mood starts from              |
| `_keyframes.json` | shared keyframe library for part motions                              |

Names of rig parts, pose variables and expression layers come from `assets/rig.json`, which
the build derives from the art. Unknown names are build errors.

## Mood file

```jsonc
{
  "name": "dance",                 // [a-z0-9-], used as data-mood="dance"
  "order": 80,                     // menu order (ascending)
  "default": true,                 // only on neutral: also matches an SVG without data-mood
  "meta": { ... },                 // see "meta"; runtime only, does not affect the SVG
  "pose": { "arms": { ... }, "vars": { ... } },
  "layers": { "show": ["m-happy", "eye-happy", "fx-dance"], "hide": ["eye-open"] },
  "motion": { "<part>": <animation> | "none", ... },
  "keyframes": { "body": [ <stop>, ... ] },     // mood-local, emitted as "<mood>-<key>"
  "variants": { "1": { ... }, "2": { ... } },   // data-strain overrides
  "css": "& .dot { animation-duration: .6s; }"  // optional raw escape hatch
}
```

### pose

- `arms.l` / `arms.r`: either `{"hand": [x, y]}` — an absolute target in art space (the
  coordinate space of `reference/isolated/whalechan-art-master.webp`, see `rig.json` `art`) solved
  with two-bone IK — or `{"angles": [upper, fore]}` in degrees. Give the right hand where it
  should really be; the compiler mirrors it into the arm's frame. `"elbowOut": false` picks the
  other IK solution (elbow tucked in).
- `arms.fist`: `"none" | "l" | "r" | "both"`.
- `vars`: the other pose variables as CSS strings without the `--`, e.g. `"hr": "-7deg"`.
  See `rig.json` `poseVars` for the list, units and slider ranges. Anything a mood omits keeps
  the `_defaults.json` value.

### layers

Classes of expression layers (`rig.json` `layers`). Layers marked `"default": "hidden"` (mouths,
alternate eyes, lids, effects, props, thought-bubble bits) appear only when a mood `show`s them;
the few `"visible"` ones (`eye-open`, `lash-default`, `hl`) can be hidden.

### motion

Keys are rig parts (`rig.json` `parts`): `body`, `upper`, `head`, `arm-l.u`, `arm-l.f`,
`arm-r.u`, `arm-r.f`, `leg-l`, `leg-r`, `tail`, `fluke`, `ear-l`, `ear-r`, `ahoge`, `lock-l`,
`lock-r`, `blink`. A part the mood leaves out keeps its idle motion from `_defaults.json`;
`"none"` stops it.

```jsonc
"head": { "keyframes": "smug-nod", "duration": "1.5s", "easing": "ease-in-out",
          "delay": "-.4s", "iterations": "infinite", "direction": "alternate" }
```

Only `keyframes` and `duration` are required (`iterations` defaults to `infinite`). `keyframes`
is a mood-local key first, then a name from `_keyframes.json`. Arm motions rotate on top of the
pose, so arm keyframes are offsets in degrees.

**Hand tracks** — `arm-l` / `arm-r` animate a whole arm by hand targets instead (can't be mixed
with that arm's `.u`/`.f` keys). Each stop is solved with IK and emitted as two keyframe sets,
`<mood>-arm-r-u` / `-f`, holding offsets from the pose:

```jsonc
"arm-r": { "stops": [{ "t": 0, "hand": [368, 594] }, { "t": 4, "hand": [456, 250] }, ...],
           "duration": "3.2s", "easing": "ease-in-out", "delay": "-1.6s" }
```

Stops accept `hand`/`angles`/`elbowOut` like the pose, and an optional `easing` (below).

### keyframes (here and in `_keyframes.json`)

A list of stops: `t` is a percent or a list of percents, every other key is a CSS property.

```json
[{ "t": [0, 100], "transform": "rotate(-4deg)" }, { "t": 50, "transform": "rotate(4deg)" }]
```

Any stop (here or in a hand track) may add `"easing": "ease-out"`: the timing function for the
segment from that stop to the next (emitted as `animation-timing-function`; default: the motion's
`easing`).

### meta.editor

Settings for the mood editor only (`{"bpm": 150, "counts": 8}`: the loop is `counts` beats long,
used for the ruler and snapping). The compiler and the runtime registry ignore it.

### variants

`variants` override the mood per `data-strain` value (only thinking uses them). A variant may
contain `pose`, `layers`, `motion` and `css`; everything else is inherited from the mood through
the cascade. `pose.arms` merges over the mood's arms (so restate `fist` if it changes); `vars`
only needs what differs. Variant `"0"` also matches an SVG without `data-strain`. Variants use
the mood's `keyframes`. If a variant moves an arm that the mood animates with a hand track, the
track is re-solved for the variant's pose automatically.

### css

Raw CSS for what the schema can't express. `&` is the mood's (or variant's) root selector; a
selector without `&` is scoped under it. Use sparingly — the editor can't edit it visually.

### meta

Used by the page, the widget and the desktop app (via `assets/moods.json`), not by the SVG.

```jsonc
"meta": {
  "label": "Dance",
  "line": "Right fist up! Pump it! Now the other side!",  // speech line when the mood is picked
  "button": true,                  // has a mood button (false for neutral)
  "icon": "<path d=\"...\"/>",     // inner markup of the 24x24 button icon (null without button)
  "slow": false,                   // desktop app plays it at a reduced frame rate
  "theme": {
    "accent": "#d9608f", "accentDeep": "#a83c68", "accentSoft": "rgba(217, 96, 143, 0.12)",  // page accent
    "button": "#cf5a88",           // mood button colour
    "bubble": "#ec6f9e",           // widget speech bubble accent
    "aura": { "stops": ["rgba(255, 176, 214, .34) 0%", ...], "duration": "1.6s" },  // widget aura
    "floorShadow": null,           // widget floor shadow: {stops?, animation?, width?}; null/missing keys = neutral's
    "desktopAccent": [0.925, 0.435, 0.62], "desktopGlow": [1, 0.69, 0.84],  // desktop app, RGB 0-1
    "variants": { "2": { "floorShadow": { "animation": "shadow-vibrate .21s linear infinite" } } }
  }
}
```

Neutral's theme holds the base values the other moods fall back to.

## _defaults.json

```jsonc
{
  "pose": { "arms": { ... }, "vars": { ... } },   // emitted on .whale-chan, the fallback for every mood
  "motion": { "body": { "keyframes": "float-bob", "duration": "4.2s", "easing": "ease-in-out" }, ... }
}
```

## Output

CSS order: defaults, then each mood by `order` (base rules, then variants in strain order, then
its keyframes), then the shared keyframe library. Selectors look like
`.whale-chan[data-mood="thinking"][data-strain="1"] .head-anim`.

`assets/moods.json` is the ordered registry:
`[{ name, label, line, button, icon, slow, default, theme, variants: ["0", "1", "2"] }, ...]`.
