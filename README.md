# Whale-chan 🐋🍚

A draggable, floating **DeepSeek whale maid** mascot delivered as a
reference-faithful, self-contained animated SVG. No frameworks, no build step,
no dependencies.

![Whale-chan demo preview](assets/preview.webp)

Whale-chan floats above the page with a gentle sway, a travelling light glint,
soft bubbles, and a small cloud of sparkles. Pick her up with a mouse, finger, or
stylus; she has momentum, edge bounce, position memory, and a serious rice habit.

> **Fan project.** Whale-chan is a community-created character, not an official
> DeepSeek mascot. DeepSeek and related marks belong to their respective owners.
> See [Licensing](#licensing) and [`reference/README.md`](reference/README.md).

## Run the demo

The page is static, but it needs to be served over HTTP so the browser can load
the SVG into the widget.

```bash
cd DeepseekMascot
python3 -m http.server 4173
# open http://localhost:4173
```

Any static server works — for example `npx serve .` or `php -S localhost:4173`.

## Desktop mascot (Linux, X11)

Whale-chan can also live on your desktop as a floating, transparent window:

```bash
python3 desktop/whalechan.py
```

Requirements: an X11 session with a compositor (GNOME, KDE, picom, …), Python 3,
PyGObject with GTK 3 and pycairo, and WebKit2GTK 4.0 (needed only for baking).
On Debian/Ubuntu: `sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.0`.

| Input | Behaviour |
| --- | --- |
| Drag | Pick her up; release to throw her with momentum |
| Left click | She says a line |
| Middle click | Feed her rice |
| Right click | Menu: say, feed, mood, size, opacity, glow, hide, quit |
| Tray icon | Left click shows/hides her; right click opens the same menu |

How it works:

- **Baked frames.** WebKitGTK re-renders the CSS-rigged SVG on the CPU every
  frame (about one full core at 60 fps). Instead, [`desktop/bake.py`](desktop/bake.py)
  drives the SVG offscreen once per size: it retimes every idle loop so each mood
  loops seamlessly (7–8 s), snapshots every frame at 20 fps, and writes PNGs plus
  a click mask per mood to `~/.cache/whalechan/frames/<hash>/`. The first launch
  (or a new size) takes about a minute; the cache key changes when the SVG does.
- **Playback.** [`desktop/whalechan.py`](desktop/whalechan.py) is plain GTK and
  cairo with no WebKit at runtime. The current mood's frames are uploaded once as X server
  pixmaps, so playback is a server-side copy (~1–2% CPU).
- **Click-through.** The window is small and moves with her. Its X11 input
  shape is her baked body silhouette, so clicks and scrolls next to her (and on
  floating effects like the thought bubble) reach the windows underneath.
- **Window.** An override-redirect popup: always on top, on every workspace,
  never focused, never tiled by Pop Shell, and absent from the taskbar and
  Alt-Tab. Pass `--managed` for a regular keep-above utility window instead.
- Settings (position, size, mood, opacity, glow) persist in
  `~/.config/whalechan/config.json`. Launching it again while it is running just
  wakes the existing instance.

Bake by hand, e.g. for another SVG with the same rig contract (`data-mood`,
`data-strain`, `.fx` effect layers):

```bash
python3 desktop/bake.py --svg path/to/mascot.svg --width 260 --fps 20
python3 desktop/whalechan.py --svg path/to/mascot.svg
```

## What is included

```text
.
├── index.html              demo landing page
├── styles.css              demo page styles
├── src/
│   ├── mascot.js           <deepseek-mascot> custom element
│   └── demo.js             demo controls + telemetry wiring
├── desktop/
│   ├── whalechan.py        X11 desktop mascot (GTK + cairo)
│   └── bake.py             bakes the SVG rig into looping frames + click masks
├── assets/
│   ├── whale-chan.svg      standalone rigged + animated vector SVG
│   └── preview.webp        README preview
├── tools/
│   └── build_whale_chan.py optional generator for the SVG art and poses
└── reference/
    ├── README.md           image sources, attribution, licensing
    ├── isolated/           transparent reference art + cleaned master
    └── *.webp / *.png      full reference boards
```

## Use the mascot on another page

Copy `src/mascot.js` and `assets/whale-chan.svg` somewhere your page can reach,
then:

```html
<script src="/path/to/mascot.js" defer></script>

<deepseek-mascot src="/path/to/whale-chan.svg"></deepseek-mascot>
```

The widget injects its own styles into a shadow root, so it will not collide with
the rest of the page. It can be placed anywhere in the document; visually it is
fixed to the viewport. Put it near the top of the body if you want it early in
the tab order.

### Sizing

```css
deepseek-mascot {
  --whale-size: 300px;   /* width; height follows the SVG */
  --whale-z: 9999;       /* stacking order */
}
```

On screens under 700px the default size is smaller. If you set `--whale-size`,
that value is used at every breakpoint.

## Interaction model

| Input | Behaviour |
| --- | --- |
| Drag | Moves the mascot with pointer capture; release throws her with velocity |
| Click / tap | Shows a random line in the speech bubble |
| `Enter` / `Space` | Shows a line (when the mascot is focused) |
| Arrow keys | Nudge by 18px; hold `Shift` for 48px |
| `Home` | Park her at the bottom-right edge |
| Viewport resize | Keeps her anchored to whichever edges she was nearest |

Positions are saved to `localStorage` under `whale-chan:position:v2`. The greeting
uses `sessionStorage` under `whale-chan:met:v2`, so she says hello once per
browser session.

## JavaScript API

```js
const whale = document.querySelector("deepseek-mascot");

whale.say("Custom line from your app.");
whale.speak("Alias of say().");
whale.setMood("happy");        // neutral | angry | smug | happy | sad | thinking
whale.setMood("sad", { announce: false }); // switch pose without a speech bubble
whale.mood;                    // current mood
whale.feed();                  // rice particles + a random rice-related line
whale.resetPosition(true);     // park her, optionally announce it
whale.position;                // { x, y } in viewport pixels
```

Events bubble out of the custom element:

```js
whale.addEventListener("whale-move", (event) => {
  console.log(event.detail); // { x, y, xPct, yPct }
});

whale.addEventListener("whale-speak", (event) => {
  console.log(event.detail.text);
});

whale.addEventListener("whale-feed", (event) => {
  console.log(event.detail.count);
});

whale.addEventListener("whale-mood", (event) => {
  console.log(event.detail.mood);
});

// "thinking" escalates on its own: strain 1 after ~2.8s, strain 2 (overthinking) after ~6.8s
whale.addEventListener("whale-strain", (event) => {
  console.log(event.detail.mood, event.detail.strain);
});
```

## Animation & Vector Art

The mascot is a **pure vector, hand-rigged SVG**: no embedded bitmaps or base64
images, so it stays crisp at any size. Every body part sits in its own pivot
group, so CSS can pose and animate it independently:

| Joint / layer | Classes | Pivot |
| --- | --- | --- |
| Whole body (hops, stomps, sways) | `.char-pose` › `.char-anim` | feet |
| Breathing torso | `.upper-anim` | — |
| Head (back hair and face move together) | `.head-pose` › `.head-anim` | neck |
| Shoulders / elbows | `.arm-l`, `.arm-r` › `.u-pose` › `.u-anim` › `.f-pose` › `.f-anim` | shoulder, elbow |
| Tail and fluke | `.tail-pose` › `.tail-wag` › `.fluke` | tail root, fluke base |
| Fin-ears, ahoge, brows, irises | `.ear`, `.ahoge`, `.brow-l/r`, `.iris-pose` | each part |
| Expression layers | `.lid-*`, `.eye-happy`, `.eye-squeeze`, `.eye-swirl`, `.m-*` mouths | — |

Each mood is a **full-body pose**, not just a face swap:

| Mood | Body | Face & effects |
| --- | --- | --- |
| `neutral` | holds her skirt like the reference art, floats and breathes | soft smile, blinking |
| `angry` | fists up and pumping, stomping, tail thrashing, fins flared | slanted lids, fang, 💢 mark, steam puffs |
| `smug` | hands on hips, chin up, slow proud sway and tail swish | half-lidded side-eye, cat mouth, sparkles |
| `happy` | hopping, cheering with a steaming rice bowl held high, fast tail wag | ^ ^ eyes, open smile, hearts and stars |
| `sad` | slumped and sobbing, rubbing one eye, tail and ahoge drooping | teary eyes, wobbly mouth, tear streams, rain cloud |
| `thinking` (`data-strain="0"`) | hand on chin, other arm across her body, tapping | glance up, "o" mouth, thought bubble, `?` |
| `thinking` (`data-strain="1"`) | hands pressed to her temples, shaking | `> <` eyes, sweat drop |
| `thinking` (`data-strain="2"`) | overthinking: arms flailing, vibrating, spinning ahoge | swirl eyes, steam, scribbled thought, `?!` |

Poses are CSS custom properties on the SVG root (for example `--lu`/`--lf` for the
left shoulder and elbow angles, `--hr` for head tilt, `--tail`, `--ahoge`), and each
pose part has a springy `transition`. Switching moods therefore animates smoothly
between poses instead of snapping. A separate keyframe loop on the inner `*-anim`
group adds the idle motion on top.

The art is generated by [`tools/build_whale_chan.py`](tools/build_whale_chan.py).
It is traced in the coordinate space of
[`reference/isolated/whalechan-art-master.webp`](reference/isolated/whalechan-art-master.webp)
(silhouettes were checked against the reference alpha mask) and drawn in the
reference's anime style: tapered hair locks with cel shading and gloss, layered
irises with winged lashes, and line art tinted to each material. Arm poses are
solved with two-bone IK from hand targets. You only need the script to change the
drawing or the poses:

```bash
python3 tools/build_whale_chan.py   # rewrites assets/whale-chan.svg
```

Dragging pauses the SVG animations (`.is-paused`). `prefers-reduced-motion` and the
`.reduce-motion` class stop all loops but keep each mood's static pose.

The widget adds the breathing aura, floor shadow, drag momentum, feed hop, speech bubble, and rice particles. Inertia is also disabled when reduced motion is requested.

## Accessibility notes

- The mascot is a real `<button>` inside a shadow root, with an explicit label.
- It appears early in the tab order; `Enter` and `Space` are handled explicitly.
- A visible `press enter` badge appears on keyboard focus.
- Arrow-key movement does not trap focus.
- The speech bubble is an `aria-live="polite"` status region.
- Decorative SVG, orbit text, and sparkles are hidden from assistive technology.
- Reduced-motion preferences remove non-essential movement.

## Licensing

The **code** (`index.html`, `styles.css`, `src/*.js`) is released under the MIT
License — see [`LICENSE`](LICENSE).

The **character artwork** (`assets/whale-chan.svg`) is an original, hand-crafted
vector illustration adapted from the community **Whale-chan / 鲸鱼娘** reference
[`neutral_standing_front_isolated.webp`](reference/isolated/neutral_standing_front_isolated.webp),
with original SVG animation and presentation built around it. The reference
library by [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan)
(and the original "Mingyue" character by **Shangshan Wuxing**) is shared under
**CC BY-NC-SA 4.0**. As a derivative fan work, the illustration is distributed
under the same **CC BY-NC-SA 4.0** terms: attribution required, non-commercial
use only, share adaptations under the same license.

The visual reference images live in [`reference/`](reference/README.md).
The SVG is fully self-contained vector art, so runtime use needs only
`assets/whale-chan.svg` plus `src/mascot.js`.
