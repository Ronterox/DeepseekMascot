#!/usr/bin/env python3
"""Builds assets/whale-chan.svg — a hand-rigged, anime-styled vector Whale-chan.

    python3 tools/build_whale_chan.py [output.svg]

The SVG is the shipped artifact; this script is only needed to change the art or the moods.
The art is traced in the coordinate space of reference/isolated/whalechan-art-master.webp
and placed on the 900x1060 canvas by ART_TRANSFORM.

Moods are data: moods/<name>.json (pose, expression layers, motion, theme) are compiled to
CSS by tools/moods.mjs — the same compiler the browser editor uses — which this script runs
through `node tools/compile_moods.mjs`. Next to the SVG it writes:
  rig.json    the art catalog the compiler/editor need (arm geometry, rig parts + pivots,
              pose variables, expression layer classes)
  moods.json  the runtime mood registry (labels, speech lines, icons, themes, variants)
Effect-layer animations, transitions and the pose-variable bindings stay here with the art.

Every body part lives in its own pivot group so CSS can pose and animate it:
  .char-pose > .char-anim                      whole body (hops, stomps, sways)
  .upper-anim                                  breathing torso / head / arms
  .head-pose > .head-anim                      head tilt (back hair + face share it)
  .arm-l/.arm-r  > .u-pose > .u-anim           shoulder joint
                 > .f-pose > .f-anim           elbow joint
  .leg-l/.leg-r                                hip joint (dance kicks)
  .tail-pose > .tail-wag > .fluke              tail + fluke flick
  .ear-l/.ear-r, .ahoge, .lock-l/.lock-r, .brow-l/.brow-r, .iris-pose, eyelids, mouths
  .pillow > .pillow-squish                     plush the sleepy pose hugs
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "assets" / "whale-chan.svg"


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


# ---------------------------------------------------------------- geometry
def cubic(p0, p1, p2, p3, t):
    mt = 1 - t
    return (
        mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1],
    )


def sample_cubics(segments, steps=60):
    pts = []
    for seg in segments:
        for i in range(steps + (1 if seg is segments[-1] else 0)):
            pts.append(cubic(*seg, i / steps))
    return pts


def resample(pts, n):
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    total = acc[-1]
    out, j = [], 0
    for i in range(n + 1):
        target = total * i / n
        while j < len(acc) - 2 and acc[j + 1] < target:
            j += 1
        seg = acc[j + 1] - acc[j] or 1
        t = (target - acc[j]) / seg
        a, b = pts[j], pts[j + 1]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def scallops(pts, height, start=True):
    """Quadratic bumps between consecutive points, bulging to the left of travel."""
    d = f"M{fmt(pts[0][0])},{fmt(pts[0][1])}" if start else f"L{fmt(pts[0][0])},{fmt(pts[0][1])}"
    for a, b in zip(pts, pts[1:]):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        vx, vy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(vx, vy) or 1
        nx, ny = vy / ln, -vx / ln
        d += f" Q{fmt(mx + nx * height * 2)},{fmt(my + ny * height * 2)} {fmt(b[0])},{fmt(b[1])}"
    return d


def polyline(pts):
    return " ".join(f"L{fmt(x)},{fmt(y)}" for x, y in pts)


def arc_pts(cx, cy, r, a0, a1, n):
    return [
        (cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
         cy - r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
        for i in range(n + 1)
    ]


def spiral(turns=2.4, r=24, n=90):
    pts = []
    for i in range(n + 1):
        t = i / n
        ang = t * turns * 2 * math.pi
        rr = r * t
        pts.append((rr * math.cos(ang), rr * math.sin(ang)))
    return "M0,0 " + polyline(pts)


def star4(cx, cy, r, inner=0.28):
    pts = []
    for i in range(8):
        ang = math.radians(i * 45 - 90)
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return "M" + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts) + "Z"


def heart(cx, cy, s):
    return (f"M{fmt(cx)},{fmt(cy + 9 * s)} C{fmt(cx - 14 * s)},{fmt(cy)} {fmt(cx - 12 * s)},{fmt(cy - 11 * s)} "
            f"{fmt(cx - 5 * s)},{fmt(cy - 11 * s)} C{fmt(cx - 2 * s)},{fmt(cy - 11 * s)} {fmt(cx)},{fmt(cy - 8 * s)} "
            f"{fmt(cx)},{fmt(cy - 6 * s)} C{fmt(cx)},{fmt(cy - 8 * s)} {fmt(cx + 2 * s)},{fmt(cy - 11 * s)} "
            f"{fmt(cx + 5 * s)},{fmt(cy - 11 * s)} C{fmt(cx + 12 * s)},{fmt(cy - 11 * s)} {fmt(cx + 14 * s)},{fmt(cy)} "
            f"{fmt(cx)},{fmt(cy + 9 * s)}Z")


def pivot(classes, x, y, inner, mirror=False, src=None):
    """Group whose local origin is the pivot (x, y); inner art is authored in absolute coords.

    `classes` may be "a|b" to nest several transformable groups on the same pivot.
    `src` is the art's own pivot when it was drawn elsewhere (used for mirrored copies).
    """
    flip = " scale(-1,1)" if mirror else ""
    sx, sy = src or (x, y)
    names = classes.split("|")
    opens = "".join(f'<g class="{c}">' for c in names)
    closes = "</g>" * len(names)
    return (f'<g transform="translate({fmt(x)},{fmt(y)}){flip}">{opens}'
            f'<g transform="translate({fmt(-sx)},{fmt(-sy)})">{inner}</g>{closes}</g>')


# ================================================================ anime art
# All art below is authored in the coordinate space of
# reference/isolated/whalechan-art-master.webp (756 x 1014) so it can be traced
# directly over the reference; ART_TRANSFORM places it on the 900 x 1060 canvas.
MX = 303                      # vertical mirror axis of the character
ART_SCALE = 0.92
ART_OFFSET = (152, 88)
ART_TRANSFORM = f"translate({ART_OFFSET[0]},{ART_OFFSET[1]}) scale({ART_SCALE})"
NECK = (303, 452)
FEET = (303, 990)
SHOULDER_L = (236, 488)
SHOULDER_R = (370, 488)
L_UPPER, L_FORE = 108, 118     # shoulder→elbow, elbow→hand centre

HAIR_LINE = "#1d2b63"
HAIR_DK = "#22346c"
SKIN = "#feece3"
SKIN_SH = "#f6cdc1"
SKIN_LINE = "#b5736a"
NAVY = "#28325d"
NAVY_DK = "#1d2547"
NAVY_LINE = "#141a38"
WHITE = "#fdfcfe"
WHITE_SH = "#dcd8ea"
WHITE_LINE = "#64608a"
GOLD = "#c9a866"
GOLD_DK = "#8c6d3a"
LASH = "#1b1420"


def mx(x):
    return 2 * MX - x


def mirror_pts(pts):
    return [(mx(x), y) for x, y in pts]


def mirror_g(inner):
    return f'<g transform="translate({2 * MX},0) scale(-1,1)">{inner}</g>'


def spline(pts, closed=False):
    """Catmull-Rom through `pts` as cubic Béziers."""
    n = len(pts)
    d = f"M{fmt(pts[0][0])},{fmt(pts[0][1])}"
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[0]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else pts[-1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{fmt(c1[0])},{fmt(c1[1])} {fmt(c2[0])},{fmt(c2[1])} {fmt(p2[0])},{fmt(p2[1])}"
    return d + ("Z" if closed else "")


def sample_spline(pts, per=14):
    segs = []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[0]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[-1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segs.append((p1, c1, c2, p2))
    return sample_cubics(segs, per)


def offset_curve(pts, dist):
    out = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        vx, vy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(vx, vy) or 1
        out.append((p[0] + vy / ln * dist, p[1] - vx / ln * dist))
    return out


def lock_geom(center, w0, power=0.7, n=16, swell=0.12):
    """Tapered hair lock around a centreline. Returns (outline, centreline, widths)."""
    c = resample(sample_spline(center, 20), n - 1)
    left, right, widths = [], [], []
    for i, p in enumerate(c):
        t = i / (n - 1)
        a, b = c[max(0, i - 1)], c[min(n - 1, i + 1)]
        vx, vy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(vx, vy) or 1
        nx, ny = vy / ln, -vx / ln
        w = w0 * (1 - t) ** power * (1 + swell * math.sin(math.pi * min(1, t * 1.6)))
        widths.append(w)
        left.append((p[0] + nx * w / 2, p[1] + ny * w / 2))
        right.append((p[0] - nx * w / 2, p[1] - ny * w / 2))
    outline = left[:-1] + [c[-1]] + list(reversed(right[:-1]))
    return outline, c, widths


def lock(center, w0, fill, power=0.7, line=HAIR_LINE, lw=1.7, shade="#1f2f68", shine="#8fb0ee",
         side=1, cls=None, shade_op=.32, shine_op=.5):
    """A tapered lock with a cel-shade wedge along one edge and a soft highlight on the other."""
    outline, c, widths = lock_geom(center, w0, power)
    d = spline(outline, closed=True)
    attr = f' class="{cls}"' if cls else ""
    out = f'<path{attr} d="{d}" fill="{fill}" stroke="{line}" stroke-width="{lw}" stroke-linejoin="round"/>'
    n = len(c)

    def band(k0, k1, t0, t1):
        a, b = [], []
        for i in range(int(n * t0), max(int(n * t0) + 2, int(n * t1))):
            i = min(i, n - 1)
            p, q = c[max(0, i - 1)], c[min(n - 1, i + 1)]
            vx, vy = q[0] - p[0], q[1] - p[1]
            ln = math.hypot(vx, vy) or 1
            nx, ny = vy / ln * side, -vx / ln * side
            w = widths[i]
            a.append((c[i][0] + nx * w * k0, c[i][1] + ny * w * k0))
            b.append((c[i][0] + nx * w * k1, c[i][1] + ny * w * k1))
        return spline(a + list(reversed(b)), closed=True)

    if shade:
        out += f'<path d="{band(0.5, 0.14, 0.0, 0.92)}" fill="{shade}" opacity="{shade_op}"/>'
    if shine:
        out += f'<path d="{band(-0.34, -0.22, 0.14, 0.5)}" fill="{shine}" opacity="{shine_op}"/>'
    return out, d


def wavy(p0, p1, amp, waves, bend=0.0, n=8):
    """Centreline from p0 to p1 with a sideways S-wave and an optional bow."""
    pts = []
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1
    nx, ny = dy / ln, -dx / ln
    for i in range(n + 1):
        t = i / n
        off = amp * math.sin(t * waves * 2 * math.pi) * min(1, t * 3) + bend * 4 * t * (1 - t)
        pts.append((p0[0] + dx * t + nx * off, p0[1] + dy * t + ny * off))
    return pts


def lock_path(center, w0, power=0.7):
    return spline(lock_geom(center, w0, power)[0], closed=True)


# ---------------------------------------------------------------- rig pivots
PILLOW = (303, 610)            # centre of the plush she hugs while asleep
HIP_L = (241, 790)             # leg pivots (hidden under the skirt)
HIP_R = (366, 790)
TAIL_PIVOT = (430, 806)
FLUKE_PIVOT = (632, 708)
EAR_PIVOT = (466, 320)         # right fin-ear; the left one is mirrored about MX
AHOGE_PIVOT = (306, 104)


# ---------------------------------------------------------------- defs
DEFS = f"""
  <defs>
    <linearGradient id="g-hair-back" gradientUnits="userSpaceOnUse" x1="0" y1="140" x2="0" y2="705">
      <stop offset="0" stop-color="#28396f"/><stop offset=".38" stop-color="#30488a"/>
      <stop offset=".56" stop-color="#3a6cb2"/><stop offset=".74" stop-color="#4b9bd2"/>
      <stop offset="1" stop-color="#6fc6ec"/>
    </linearGradient>
    <linearGradient id="g-hair-lock" gradientUnits="userSpaceOnUse" x1="0" y1="300" x2="0" y2="700">
      <stop offset="0" stop-color="#3a5496"/><stop offset=".3" stop-color="#4474b8"/>
      <stop offset=".6" stop-color="#54a4d8"/><stop offset="1" stop-color="#86d3f2"/>
    </linearGradient>
    <linearGradient id="g-hair-front" gradientUnits="userSpaceOnUse" x1="0" y1="105" x2="0" y2="360">
      <stop offset="0" stop-color="#2d4383"/><stop offset=".45" stop-color="#3a5698"/>
      <stop offset=".78" stop-color="#5370b0"/><stop offset="1" stop-color="#8e93c2"/>
    </linearGradient>
    <linearGradient id="g-hair-side" gradientUnits="userSpaceOnUse" x1="0" y1="150" x2="0" y2="420">
      <stop offset="0" stop-color="#2f4687"/><stop offset=".55" stop-color="#3f60a6"/>
      <stop offset="1" stop-color="#5a9fd4"/>
    </linearGradient>
    <linearGradient id="g-gloss" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#7d9ce0" stop-opacity=".2"/><stop offset=".45" stop-color="#86a6e8" stop-opacity=".85"/>
      <stop offset="1" stop-color="#6f8fd8" stop-opacity=".55"/>
    </linearGradient>
    <radialGradient id="g-face" cx="303" cy="360" r="125" gradientUnits="userSpaceOnUse">
      <stop offset=".62" stop-color="{SKIN}"/><stop offset="1" stop-color="#fbdccf"/>
    </radialGradient>
    <linearGradient id="g-iris" x1="0" y1="-27" x2="0" y2="29" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#121a46"/><stop offset=".3" stop-color="#1b3276"/>
      <stop offset=".56" stop-color="#2a5db2"/><stop offset=".8" stop-color="#4a9fdc"/>
      <stop offset="1" stop-color="#9ad8f0"/>
    </linearGradient>
    <radialGradient id="g-iris-glow" cx="0" cy="13" r="18" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#c4f0ff" stop-opacity=".95"/><stop offset="1" stop-color="#6cc4f0" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="g-dress" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2d3768"/><stop offset="1" stop-color="#222a54"/>
    </linearGradient>
    <linearGradient id="g-skirt" gradientUnits="userSpaceOnUse" x1="0" y1="590" x2="0" y2="810">
      <stop offset="0" stop-color="#212a54"/><stop offset=".55" stop-color="#29335f"/><stop offset="1" stop-color="#323e70"/>
    </linearGradient>
    <linearGradient id="g-white" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#eeecf4"/>
    </linearGradient>
    <linearGradient id="g-tail" gradientUnits="userSpaceOnUse" x1="420" y1="880" x2="700" y2="620">
      <stop offset="0" stop-color="#232c56"/><stop offset=".6" stop-color="#2b3563"/><stop offset="1" stop-color="#343f72"/>
    </linearGradient>
    <linearGradient id="g-belly" gradientUnits="userSpaceOnUse" x1="0" y1="800" x2="0" y2="895">
      <stop offset="0" stop-color="#8d95c6"/><stop offset="1" stop-color="#cdd1ea"/>
    </linearGradient>
    <linearGradient id="g-sleeve" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#1f2750"/><stop offset=".5" stop-color="#2e396b"/><stop offset="1" stop-color="#232c57"/>
    </linearGradient>
    <linearGradient id="g-bow" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#77c0e8"/><stop offset="1" stop-color="#4b95cb"/>
    </linearGradient>
    <linearGradient id="g-tear" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#d9f6ff" stop-opacity=".95"/><stop offset="1" stop-color="#7fd3ff" stop-opacity=".55"/>
    </linearGradient>
    <radialGradient id="g-blush">
      <stop offset="0" stop-color="#f7948c" stop-opacity=".75"/><stop offset=".6" stop-color="#fbaea4" stop-opacity=".35"/>
      <stop offset="1" stop-color="#fbaea4" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="clip-eye" clipPathUnits="userSpaceOnUse">
      <path d="{'{EYE_SHAPE}'}"/>
    </clipPath>
    <clipPath id="clip-face" clipPathUnits="userSpaceOnUse"><path d="{'{FACE_SHAPE}'}"/></clipPath>
  </defs>"""

EYE_SHAPE = "M-29,-17 C-20,-30 24,-34 44,-20 C50,-4 43,17 26,24 C10,29 -12,28 -22,18 C-30,8 -31,-8 -29,-17Z"
FACE_SHAPE = ("M199,258 C194,330 193,382 209,407 C227,433 264,443 303,443 C342,443 379,433 397,407 "
              "C413,382 412,330 407,258Z")
DEFS = DEFS.replace("{EYE_SHAPE}", EYE_SHAPE).replace("{FACE_SHAPE}", FACE_SHAPE)


# ---------------------------------------------------------------- tail
def tail():
    top = "M404,770 C468,788 536,792 582,766 C606,750 614,726 606,700"
    bottom = "M640,722 C646,780 626,840 576,864 C518,890 452,868 404,830"
    stem = top + " L640,722 C646,780 626,840 576,864 C518,890 452,868 404,830Z"
    belly = ("M414,830 C468,866 536,884 588,860 C624,842 640,806 642,768 "
             "C632,810 606,840 570,850 C522,862 466,850 414,814Z")
    shine = "M470,800 C520,812 566,806 596,786"
    fluke = ("M596,712 C590,676 596,634 620,602 C636,626 644,652 646,668 "
             "C672,648 706,640 742,648 C722,678 688,704 656,722 C636,732 604,728 596,712Z")
    fluke_shine = "M624,624 C632,640 636,656 636,672 M672,660 C694,652 716,650 734,654"
    fluke_art = (f'<path d="{fluke}" fill="url(#g-tail)" stroke="{NAVY_LINE}" stroke-width="2.4" stroke-linejoin="round"/>'
                 f'<path d="{fluke_shine}" fill="none" stroke="#5a67a6" stroke-width="3" stroke-linecap="round" opacity=".55"/>')
    stem_art = (f'<path d="{stem}" fill="url(#g-tail)"/>'
                f'<path d="{belly}" fill="url(#g-belly)"/>'
                f'<path d="{shine}" fill="none" stroke="#5d6aa8" stroke-width="5" stroke-linecap="round" opacity=".5"/>'
                f'<path d="{top}" fill="none" stroke="{NAVY_LINE}" stroke-width="2.8" stroke-linecap="round"/>'
                f'<path d="{bottom}" fill="none" stroke="{NAVY_LINE}" stroke-width="2.8" stroke-linecap="round"/>')
    inner = pivot("fluke", *FLUKE_PIVOT, fluke_art) + stem_art
    return pivot("tail-pose|tail-wag", *TAIL_PIVOT, inner)


# ---------------------------------------------------------------- hair (back)
BACK_SIL = [
    (303, 112), (238, 116), (186, 150), (150, 206), (118, 290), (116, 350), (110, 395),
    (90, 438), (78, 470), (84, 492), (58, 510), (38, 534), (34, 560), (48, 584), (60, 600),
    (30, 604), (20, 618), (34, 636), (70, 640), (48, 660), (50, 682), (84, 698), (112, 690),
    (138, 700), (162, 680), (184, 648), (210, 620), (303, 610),
    (398, 620), (424, 650), (446, 676), (478, 692), (512, 678), (540, 688), (566, 668),
    (596, 664), (616, 642), (618, 618), (606, 604), (618, 584), (622, 552), (612, 524),
    (590, 504), (578, 486), (576, 456), (562, 432), (536, 406), (520, 370), (510, 320),
    (494, 262), (466, 200), (424, 146), (366, 116),
]

BACK_LOCKS = [  # (start, end, amplitude, waves, bow, width, gradient)
    ((150, 320), (26, 614), 14, 1.6, -30, 70, "url(#g-hair-back)"),
    ((176, 380), (64, 684), 13, 1.5, -20, 62, "url(#g-hair-lock)"),
    ((208, 420), (128, 694), 12, 1.4, -10, 54, "url(#g-hair-lock)"),
    ((456, 320), (616, 616), 14, 1.6, 30, 70, "url(#g-hair-back)"),
    ((432, 380), (574, 668), 13, 1.5, 20, 62, "url(#g-hair-lock)"),
    ((402, 420), (476, 692), 12, 1.4, 10, 54, "url(#g-hair-lock)"),
]


def hair_back():
    sil = spline(BACK_SIL, closed=True)
    locks = ""
    for p0, p1, amp, waves, bow, w, fill in BACK_LOCKS:
        side = -1 if p1[0] < MX else 1
        art, _ = lock(wavy(p0, p1, amp, waves, bow), w, fill, power=0.5, lw=1.4, side=side,
                      shade="#1d2f66", shine="#b4e6fb", shade_op=.24, shine_op=.3)
        locks += art
    curls = ""
    for path in ["M40,600 C26,606 22,624 36,632", "M64,644 C50,656 50,676 66,684",
                 "M604,606 C616,618 614,636 600,642", "M560,664 C574,672 586,670 594,662"]:
        curls += f'<path d="{path}" fill="none" stroke="#a6e2fb" stroke-width="2.6" stroke-linecap="round" opacity=".7"/>'
    shine = ""
    for path in ["M96,470 C84,500 70,520 60,548", "M560,470 C576,496 592,516 602,546",
                 "M134,520 C120,560 106,590 98,620", "M500,540 C520,570 536,600 548,628"]:
        shine += f'<path d="{path}" fill="none" stroke="#9fd7f5" stroke-width="3" stroke-linecap="round" opacity=".28"/>'
    return (f'<clipPath id="clip-hair-back"><path d="{sil}"/></clipPath>'
            f'<path d="{sil}" fill="url(#g-hair-back)" stroke="{HAIR_LINE}" stroke-width="2" stroke-linejoin="round"/>'
            f'<g clip-path="url(#clip-hair-back)">{locks}{shine}{curls}</g>'
            f'<path d="{sil}" fill="none" stroke="#151d48" stroke-width="2.8" stroke-linejoin="round"/>')


# ---------------------------------------------------------------- legs
def legs():
    """Each stocking + shoe hangs from its own hip pivot so the dance can kick it out."""
    out = ""
    for side, hip, d, shade, cx, buckle_side in [
            ("l", HIP_L, "M206,780 L276,780 C276,846 272,894 270,938 L224,938 C220,894 210,846 206,780Z",
             "M260,820 C258,860 257,900 256,930", 247, -1),
            ("r", HIP_R, "M330,780 L402,780 C400,846 394,894 392,938 L344,938 C342,894 334,846 330,780Z",
             "M346,820 C348,860 350,900 352,930", 369, 1)]:
        b = cx + buckle_side * 22
        art = (f'<path d="{d}" fill="{WHITE}" stroke="{WHITE_LINE}" stroke-width="2"/>'
               f'<path d="{shade}" fill="none" stroke="{WHITE_SH}" stroke-width="7" stroke-linecap="round"/>'
               f'<path d="M{cx - 26},946 C{cx - 30},972 {cx - 20},992 {cx},993 C{cx + 22},994 {cx + 31},976 {cx + 27},946 '
               f'C{cx + 14},956 {cx - 14},956 {cx - 26},946Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
               f'<path d="M{cx - 26},946 C{cx - 14},956 {cx + 14},956 {cx + 27},946" fill="none" stroke="#4a568e" stroke-width="1.6" opacity=".8"/>'
               f'<path d="M{cx - 24},934 C{cx - 10},942 {cx + 12},942 {cx + 26},934" fill="none" stroke="{NAVY}" stroke-width="6.5" stroke-linecap="round"/>'
               f'<path d="M{cx - 24},934 C{cx - 10},942 {cx + 12},942 {cx + 26},934" fill="none" stroke="{NAVY_LINE}" stroke-width="1.2" stroke-linecap="round" opacity=".6"/>'
               f'<circle cx="{b}" cy="938" r="6.5" fill="{NAVY}" stroke="{GOLD}" stroke-width="2.8"/>'
               f'<path d="M{cx - 18},976 C{cx - 12},986 {cx},989 {cx + 10},987" fill="none" stroke="#6a77b4" stroke-width="3" stroke-linecap="round" opacity=".7"/>'
               f'<path d="M{cx - 22},984 C{cx - 12},992 {cx + 14},992 {cx + 24},982" fill="none" stroke="{NAVY_DK}" stroke-width="4" stroke-linecap="round"/>')
        out += pivot(f"leg leg-{side}", hip[0], hip[1], art)
    return f'<g class="legs">{out}</g>'


# ---------------------------------------------------------------- torso
def torso():
    neck = (f'<path d="M282,430 L324,430 L325,462 L281,462Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="1.6"/>'
            f'<path d="M282,438 C292,452 314,452 324,438 L324,454 C312,460 294,460 282,454Z" fill="{SKIN_SH}"/>')

    # petticoat: two big ruffle tiers under the hem
    hem = resample(sample_cubics([((92, 736), (128, 782), (478, 782), (524, 730))]), 20)
    tier1_low = resample(sample_cubics([((100, 764), (138, 822), (468, 822), (520, 758))]), 20)
    tier2_low = resample(sample_cubics([((134, 790), (172, 852), (434, 852), (482, 784))]), 18)
    petti = ""
    for top, low, h in [(resample(sample_cubics([((116, 756), (154, 812), (452, 812), (502, 750))]), 18), tier2_low, 7),
                        (hem, tier1_low, 6)]:
        petti += (f'<path d="M{fmt(top[0][0])},{fmt(top[0][1] - 8)} {polyline(top)} '
                  f'{scallops(list(reversed(low)), -h, start=False)}Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.8" stroke-linejoin="round"/>')
        for a, b in zip(top[1:-1], low[1:-1]):
            petti += (f'<path d="M{fmt(a[0] + (b[0] - a[0]) * .35)},{fmt(a[1] + (b[1] - a[1]) * .35)} L{fmt(b[0])},{fmt(b[1] + 2)}" '
                      f'stroke="{WHITE_SH}" stroke-width="2.6" stroke-linecap="round"/>')

    skirt_d = ("M212,588 C240,596 366,596 394,588 C430,636 490,684 524,730 "
               "C496,772 400,788 303,790 C206,788 118,776 92,736 C118,680 178,636 212,588Z")
    skirt = f'<path d="{skirt_d}" fill="url(#g-skirt)" stroke="{NAVY_LINE}" stroke-width="2.8" stroke-linejoin="round"/>'
    folds = ""
    for a, b in [((228, 600), (150, 770)), ((262, 604), (236, 786)), ((344, 604), (372, 786)), ((378, 600), (458, 772))]:
        bend = 10 if b[0] > MX else -10
        folds += (f'<path d="M{a[0]},{a[1]} Q{(a[0] + b[0]) / 2 + bend},{(a[1] + b[1]) / 2} {b[0]},{b[1]}" '
                  f'fill="none" stroke="{NAVY_DK}" stroke-width="7" opacity=".55" stroke-linecap="round"/>')
    folds += f'<path d="M140,724 C150,700 170,670 196,640" fill="none" stroke="#4a5690" stroke-width="5" stroke-linecap="round" opacity=".45"/>'
    embroidery = (f'<path d="M106,742 C156,772 448,772 510,736" fill="none" stroke="{GOLD}" stroke-width="2.2"/>'
                  f'<path d="M112,754 C164,784 442,784 504,748" fill="none" stroke="{GOLD}" stroke-width="1.2" opacity=".85"/>')
    vine = resample(sample_cubics([((118, 736), (166, 764), (442, 764), (498, 730))]), 14)
    for i, (x, y) in enumerate(vine[1:-1]):
        if i % 2 == 0:
            embroidery += f'<path d="{star4(x, y - 10, 6, .32)}" fill="{GOLD}" opacity=".9"/>'
        else:
            embroidery += f'<path d="M{fmt(x - 8)},{fmt(y - 6)} q8,-8 16,0" fill="none" stroke="{GOLD}" stroke-width="1.2" opacity=".8"/>'
    bows = ""
    for bx, by, s in [(170, 716, 1), (428, 722, -1)]:
        bows += (f'<g transform="translate({bx},{by}) scale({s},1) rotate(-6)">'
                 f'<path d="M-3,6 L-12,50 L-2,44 Z M3,6 L12,52 L2,46Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="1.6" stroke-linejoin="round"/>'
                 f'<path d="M0,0 C-10,-16 -30,-14 -28,2 C-26,14 -10,10 0,0Z M0,0 C10,-16 30,-14 28,2 C26,14 10,10 0,0Z" fill="{NAVY}" stroke="{GOLD}" stroke-width="2.2"/>'
                 f'<circle r="5" fill="{GOLD}" stroke="{GOLD_DK}" stroke-width="1.2"/></g>')

    bodice_d = "M228,468 C262,456 344,456 378,468 L394,592 L212,592Z"
    bodice = f'<path d="{bodice_d}" fill="url(#g-dress)" stroke="{NAVY_LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
    # white shirt front + side ruffles
    shirt = (f'<path d="M244,456 L362,456 L356,540 L250,540Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.6"/>')
    for x in (270, 284, 322, 336):
        shirt += f'<path d="M{x},470 L{x},536" stroke="{WHITE_SH}" stroke-width="1.6"/>'
    shirt += f'<path d="M294,478 L294,540 M312,478 L312,540" stroke="{WHITE_LINE}" stroke-width="1.2"/>'
    rl = resample([(246, 456), (252, 540)], 8)
    rr = resample([(354, 540), (360, 456)], 8)
    ruff_l = offset_curve(rl, 22)
    ruff_r = offset_curve(rr, 22)
    shirt += (f'<path d="M{fmt(rl[0][0])},{fmt(rl[0][1])} {scallops(ruff_l, 6, start=False)} L{fmt(rl[-1][0])},{fmt(rl[-1][1])}Z" '
              f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.6" stroke-linejoin="round"/>')
    shirt += (f'<path d="M{fmt(rr[0][0])},{fmt(rr[0][1])} {scallops(ruff_r, 6, start=False)} L{fmt(rr[-1][0])},{fmt(rr[-1][1])}Z" '
              f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.6" stroke-linejoin="round"/>')
    buttons = "".join(f'<circle cx="303" cy="{y}" r="3.2" fill="{NAVY}"/>' for y in (500, 514, 528))
    corset = (f'<path d="M240,532 C270,538 336,538 366,532 L370,590 C336,598 270,598 236,590Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="2.2"/>'
              f'<path d="M242,540 C272,546 334,546 364,540" fill="none" stroke="#3f4a80" stroke-width="1.4" opacity=".8"/>'
              f'<path d="M262,536 L260,594 M344,536 L346,594" stroke="{NAVY_DK}" stroke-width="1.6"/>')
    for x, y in [(278, 554), (328, 554), (278, 576), (328, 576)]:
        corset += (f'<circle cx="{x}" cy="{y}" r="5" fill="{GOLD}" stroke="{GOLD_DK}" stroke-width="1.2"/>'
                   f'<circle cx="{x - 1.5}" cy="{y - 1.5}" r="1.6" fill="#f3e3b8"/>')

    apron_core = [((254, 592), (240, 640), (222, 696), (228, 730)),
                  ((228, 730), (240, 758), (366, 758), (378, 730)),
                  ((378, 730), (384, 696), (366, 640), (352, 592))]
    edge = resample(sample_cubics(apron_core), 30)
    ruffle_out = offset_curve(edge, -16)
    apron = (f'<path d="M{fmt(edge[0][0])},{fmt(edge[0][1])} {scallops(ruffle_out, 5, start=False)} L{fmt(edge[-1][0])},{fmt(edge[-1][1])}Z" '
             f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.8" stroke-linejoin="round"/>')
    for a, b in zip(edge[1:-1], ruffle_out[1:-1]):
        apron += (f'<path d="M{fmt(a[0])},{fmt(a[1])} L{fmt(a[0] + (b[0] - a[0]) * .9)},{fmt(a[1] + (b[1] - a[1]) * .9)}" '
                  f'stroke="{WHITE_SH}" stroke-width="2.2" stroke-linecap="round"/>')
    apron += (f'<path d="{spline(edge)}" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.6"/>'
              f'<path d="M248,640 C240,680 236,710 244,734 M360,640 C368,680 370,710 362,734" fill="none" stroke="#e7e4ef" stroke-width="5" stroke-linecap="round"/>')
    whale_logo = ('<g transform="translate(330,690) scale(1.25)">'
                  '<path d="M-16,4 C-16,-8 -4,-12 6,-10 C12,-9 15,-6 16,-3 L22,-8 C24,-9 25,-7 24,-6 L19,0 C18,8 8,12 -2,12 C-10,12 -16,9 -16,4Z" fill="#2c4a9a" stroke="#18295e" stroke-width="1.2"/>'
                  '<path d="M-14,6 C-6,10 6,10 14,4" fill="none" stroke="#e8eefa" stroke-width="2.4" stroke-linecap="round"/>'
                  '<circle cx="-6" cy="-2" r="1.6" fill="#fff"/>'
                  '<path d="M-2,-12 C-4,-18 -8,-20 -10,-20 M-2,-12 C0,-18 4,-20 6,-20" fill="none" stroke="#4fa8e0" stroke-width="1.8" stroke-linecap="round"/>'
                  '</g>')

    collar = (f'<path d="M270,452 C286,446 320,446 336,452 L338,464 C320,458 286,458 268,464Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.6"/>'
              f'<path d="{scallops(resample([(268, 464), (338, 464)], 9), -2.2)}" fill="none" stroke="{WHITE_LINE}" stroke-width="1.4"/>')
    bowtie = (f'<g transform="translate(303,472) scale(1.22)">'
              f'<path d="M-4,6 L-20,36 L-8,32 L-2,34Z M4,6 L20,36 L8,32 L2,34Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="1.6" stroke-linejoin="round"/>'
              f'<path d="M-14,26 l6,-2 M12,26 l-4,-2" stroke="{GOLD}" stroke-width="1.2" stroke-linecap="round"/>'
              f'<path d="M0,0 C-10,-14 -36,-16 -36,-2 C-36,12 -12,12 0,0Z M0,0 C10,-14 36,-16 36,-2 C36,12 12,12 0,0Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="1.8"/>'
              f'<path d="M-30,-4 C-24,-8 -14,-6 -8,-2 M30,-4 C24,-8 14,-6 8,-2" fill="none" stroke="#46528a" stroke-width="2" stroke-linecap="round"/>'
              f'<circle r="8" fill="#5fb4dc" stroke="{GOLD}" stroke-width="2.6"/><circle cx="-2.5" cy="-2.5" r="2.4" fill="#e6fbff"/></g>')
    return (f'<g class="torso">{neck}{petti}{skirt}{folds}{embroidery}{bows}{bodice}{shirt}{buttons}'
            f'{corset}{apron}{whale_logo}{collar}{bowtie}</g>')


# ---------------------------------------------------------------- head pieces
def fin_ear(mirror):
    top = "M460,290 C498,274 556,294 590,352 C562,342 532,344 508,350 C488,354 468,352 460,340Z"
    under_pts = resample(sample_spline([(590, 352), (566, 374), (524, 382), (486, 374), (464, 350)], 12), 7)
    under = (f"M466,336 C492,348 524,344 552,345 C568,346 580,348 588,350 "
             f"{scallops(under_pts, 5.5, start=False)}Z")
    art = (f'<path d="{top}" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="2" stroke-linejoin="round"/>'
           f'<path d="M474,300 C506,294 540,308 566,330" fill="none" stroke="#4b5794" stroke-width="3" stroke-linecap="round" opacity=".7"/>'
           f'<path d="{under}" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="1.8" stroke-linejoin="round"/>'
           f'<path d="M492,356 C510,354 528,352 546,350 M500,364 C516,362 532,360 548,358" fill="none" stroke="{WHITE_SH}" stroke-width="1.6" stroke-linecap="round"/>')
    art = f'<g transform="rotate(14,{EAR_PIVOT[0]},{EAR_PIVOT[1]})">{art}</g>'
    if mirror:
        return pivot("ear ear-l|ear-flap-l", mx(EAR_PIVOT[0]), EAR_PIVOT[1], art, mirror=True, src=EAR_PIVOT)
    return pivot("ear ear-r|ear-flap-r", *EAR_PIVOT, art)


def eye(cx, cy, s):
    """s=1 → viewer-right eye (outer corner +x); s=-1 mirrored. Highlights keep a top-left light."""
    hl = (f'<ellipse cx="{-10 * s}" cy="-12" rx="7.6" ry="7" fill="#fff"/>'
          f'<circle cx="{1 * s}" cy="-5" r="3.8" fill="#fff"/>'
          f'<circle cx="{11 * s}" cy="12" r="2.4" fill="#fff" opacity=".95"/>'
          f'<path d="M{-15 * s},8 Q{-13 * s},15 {-7 * s},18" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round" opacity=".8"/>')
    iris = (f'<g class="iris"><g class="iris-pose">'
            f'<ellipse cx="1" cy="2" rx="25.5" ry="27" fill="url(#g-iris)"/>'
            f'<ellipse cx="0" cy="11" rx="17" ry="13" fill="url(#g-iris-glow)"/>'
            f'<path d="M-24,-4 C-19,-27 21,-27 26,-4 C14,-13 -12,-13 -24,-4Z" fill="#0c1440" opacity=".6"/>'
            f'<ellipse cx="1" cy="3" rx="8" ry="12" fill="#0a1238"/>'
            f'<path d="M-15,10 C-8,19 8,19 15,10" fill="none" stroke="#9ee0fa" stroke-width="1.6" opacity=".8"/>'
            f'<ellipse cx="1" cy="2" rx="25.5" ry="27" fill="none" stroke="#0f1846" stroke-width="2"/>'
            f'<g class="hl">{hl}</g>'
            f'<g class="hl-sad"><circle cx="{8 * s}" cy="-4" r="5" fill="#fff"/><ellipse cx="{-11 * s}" cy="12" rx="5" ry="3.4" fill="#fff" opacity=".9"/></g>'
            f'</g></g>')
    tear_pool = '<path class="tear-pool" d="M-24,14 C-10,30 16,30 34,14 C24,26 -6,28 -24,14Z" fill="#c8f2ff"/>'
    lash = (f'<g class="lash-default">'
            f'<path d="M-32,-13 C-23,-32 2,-40 23,-37 C37,-35 49,-26 57,-15 L62,-12 C55,-11 50,-10 46,-8 '
            f'C37,-22 20,-28 2,-28 C-14,-28 -24,-22 -30,-9Z" fill="{LASH}"/>'
            f'<path d="M32,-35 l9,-8 M43,-29 l11,-6 M51,-22 l11,-3" stroke="{LASH}" stroke-width="2.4" stroke-linecap="round"/>'
            f'<path d="M46,-8 C52,4 48,16 37,24 C43,13 45,3 41,-5Z" fill="#6e3226" opacity=".9"/>'
            f'<path d="M-17,-39 C2,-46 26,-44 41,-33" fill="none" stroke="{SKIN_LINE}" stroke-width="1.4" opacity=".55"/></g>')
    lower = (f'<path d="M-14,26 C0,29 16,28 30,23" fill="none" stroke="#b5776c" stroke-width="1.4" stroke-linecap="round" opacity=".6"/>'
             f'<path d="M-29,-11 C-31,-3 -29,5 -25,10" fill="none" stroke="#a65c52" stroke-width="1.4" opacity=".5"/>')
    lids = (
        f'<g class="lid lid-angry"><path d="M-40,-62 L62,-62 L62,-24 L-40,-1Z" fill="{SKIN}"/>'
        f'<path d="M-32,-3 L54,-23" stroke="{LASH}" stroke-width="6" stroke-linecap="round"/></g>'
        f'<g class="lid lid-smug"><path d="M-40,-62 L62,-62 L62,-7 Q8,1 -40,-3Z" fill="{SKIN}"/>'
        f'<path d="M-30,-4 Q8,2 48,-7 L58,-11" fill="none" stroke="{LASH}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></g>'
        f'<g class="lid lid-sad"><path d="M-40,-62 L62,-62 L62,-6 L-40,-24Z" fill="{SKIN}"/>'
        f'<path d="M-30,-23 Q8,-21 50,-7" fill="none" stroke="{LASH}" stroke-width="5.5" stroke-linecap="round"/></g>'
    )
    open_eye = (f'<g class="eye-open"><g class="blink">'
                f'<path d="{EYE_SHAPE}" fill="#fff"/>'
                f'<path d="M-29,-17 C-20,-30 24,-34 44,-20 L44,-8 C24,-22 -18,-20 -29,-6Z" fill="#d9d6ea" opacity=".7"/>'
                f'<g clip-path="url(#clip-eye)">{iris}{tear_pool}</g>'
                f'{lash}{lower}{lids}</g></g>')
    happy = (f'<g class="eye-alt eye-happy"><path d="M-26,8 Q4,-22 34,6" fill="none" stroke="{LASH}" stroke-width="6" stroke-linecap="round"/>'
             f'<path d="M34,6 L44,0" stroke="{LASH}" stroke-width="4" stroke-linecap="round"/></g>')
    squeeze = (f'<g class="eye-alt eye-squeeze"><path d="M26,-16 L-14,2 L26,20" fill="none" stroke="{LASH}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></g>')
    sleep = (f'<g class="eye-alt eye-sleep">'
             f'<path d="M-22,-8 C-8,-15 18,-16 38,-9" fill="none" stroke="{SKIN_LINE}" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>'
             f'<path d="M-28,2 C-16,16 18,20 42,2" fill="none" stroke="{LASH}" stroke-width="5.5" stroke-linecap="round"/>'
             f'<path d="M42,2 L53,-1 M35,9 L43,15 M24,13 L28,21 M10,15 L11,22" stroke="{LASH}" stroke-width="2.6" stroke-linecap="round"/></g>')
    swirl = (f'<g class="eye-alt eye-swirl"><circle cx="6" r="27" fill="#fff" stroke="{LASH}" stroke-width="2.4"/>'
             f'<g transform="translate(6,0)"><g class="swirl"><path d="{spiral(r=22)}" fill="none" stroke="#2a56b0" stroke-width="3.6" stroke-linecap="round"/></g></g></g>')
    return (f'<g transform="translate({cx},{cy}) scale({s},1)">'
            f'{open_eye}{happy}{squeeze}{swirl}{sleep}</g>')


EYE_L = (242, 355)
EYE_R = (366, 355)


def brows():
    br = f'<path d="M-17,3 Q0,-3 17,1" fill="none" stroke="#2b2346" stroke-width="2.6" stroke-linecap="round" opacity=".9"/>'
    return (pivot("brow brow-l", 241, 291, f'<g transform="translate(241,291)">{br}</g>', mirror=True)
            + pivot("brow brow-r", 365, 291, f'<g transform="translate(365,291)">{br}</g>'))


def mouths():
    ln = "#8f4a48"
    m = f'<g class="mouth m-neutral"><path d="M291,401 Q303,410 315,401" fill="none" stroke="{ln}" stroke-width="2" stroke-linecap="round"/></g>'
    m += (f'<g class="mouth m-angry"><path d="M289,411 Q303,397 317,411 Q315,420 303,419 Q291,420 289,411Z" fill="#a83a44" stroke="#6e1f2e" stroke-width="1.8" stroke-linejoin="round"/>'
          f'<path d="M295,404 L297,410 L300,403Z" fill="#fff"/><path d="M296,416 Q303,413 310,416" fill="none" stroke="#ff9aa6" stroke-width="2.4" stroke-linecap="round"/></g>')
    m += (f'<g class="mouth m-smug"><path d="M288,401 Q295,408 303,402 Q311,408 318,401" fill="none" stroke="{ln}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g>')
    m += (f'<g class="mouth m-happy"><path d="M287,397 Q303,400 319,397 Q318,422 303,423 Q288,422 287,397Z" fill="#b23c4e" stroke="#6e1f2e" stroke-width="1.8" stroke-linejoin="round"/>'
          f'<path d="M293,415 Q303,407 313,415 Q310,422 303,422 Q296,422 293,415Z" fill="#ff98a8"/></g>')
    m += (f'<g class="mouth m-sad"><g class="quiver"><path d="M290,411 Q293,404 298,408 Q303,403 308,408 Q313,404 316,411" fill="none" stroke="{ln}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g></g>')
    m += f'<g class="mouth m-think0"><ellipse cx="310" cy="406" rx="4.5" ry="5.5" fill="#a83a44" stroke="#6e1f2e" stroke-width="1.6"/></g>'
    m += f'<g class="mouth m-think1"><path d="M289,407 q4,-5 7,0 t7,0 t7,0 t7,0" fill="none" stroke="{ln}" stroke-width="2" stroke-linecap="round"/></g>'
    snore = (f'<ellipse cx="303" cy="408" rx="5" ry="4.2" fill="#a83a44" stroke="#6e1f2e" stroke-width="1.6"/>'
             f'<ellipse cx="303" cy="410" rx="2.6" ry="1.6" fill="#ff98a8"/>')
    m += f'<g class="mouth m-sleepy">{pivot("snore", 303, 404, snore)}</g>'
    m += (f'<g class="mouth m-think2"><path d="M288,404 L294,399 L300,405 L306,399 L312,405 L318,400 Q316,420 303,420 Q290,420 288,404Z" fill="#a83a44" stroke="#6e1f2e" stroke-width="1.8" stroke-linejoin="round"/></g>')
    return m


CAP = ("M303,104 C230,104 162,146 140,214 C126,256 122,302 128,350 L198,350 C198,312 204,284 216,266 "
       "C236,250 270,244 303,244 C336,244 370,250 390,266 C402,284 408,312 408,350 L480,354 "
       "C486,300 480,250 464,206 C442,146 376,104 303,104Z")
BANGS = [  # (centreline, root width, taper power, gradient, shade side)
    ([(234, 128), (182, 230), (168, 312), (180, 374), (212, 414)], 72, 0.36, "url(#g-hair-side)", -1),
    ([(372, 128), (424, 230), (438, 312), (426, 374), (394, 414)], 72, 0.36, "url(#g-hair-side)", 1),
    ([(268, 106), (236, 200), (214, 268), (216, 330)], 84, 0.5, "url(#g-hair-front)", -1),
    ([(340, 106), (376, 200), (396, 268), (392, 328)], 84, 0.5, "url(#g-hair-front)", 1),
    ([(318, 104), (312, 200), (298, 272), (290, 322), (297, 354)], 100, 0.62, "url(#g-hair-front)", 1),
    ([(300, 250), (306, 300), (312, 328), (320, 346)], 20, 0.85, "url(#g-hair-front)", 1),

]


def bang_paths():
    return [lock_path(c, w, p) for c, w, p, _, _ in BANGS]


def front_hair():
    cap = f'<path d="{CAP}" fill="url(#g-hair-front)" stroke="#151d48" stroke-width="2.6" stroke-linejoin="round"/>'
    locks = ""
    for i, (c, w, p, fill, side) in enumerate(BANGS):
        art, _ = lock(c, w, fill, power=p, line="#24367a", lw=1.3, side=side, shade="#22336e", shine="#a3bcf3", shine_op=.3)
        if i == 0:
            art = pivot("lock lock-l", c[0][0], c[0][1], art)
        elif i == 1:
            art = pivot("lock lock-r", c[0][0], c[0][1], art)
        locks += art
    clip = "".join(f'<path d="{d}"/>' for d in [CAP] + bang_paths())
    def arc(y0, sag, x0=190, x1=416, n=14):
        return [(x0 + (x1 - x0) * i / n, y0 + sag * ((2 * i / n - 1) ** 2)) for i in range(n + 1)]
    top = arc(166, 30)
    bottom = [(x, y + 18 + 6 * math.sin(i * 1.9)) for i, (x, y) in enumerate(arc(166, 27))]
    gloss = (f'<path d="{spline(top)} L{fmt(bottom[-1][0])},{fmt(bottom[-1][1])} '
             f'{spline(list(reversed(bottom)))[1:].split(" ", 1)[1]}Z" fill="url(#g-gloss)" opacity=".5"/>')
    for x, y, h in [(244, 176, 24), (284, 168, 28), (324, 168, 28), (362, 176, 24)]:
        gloss += f'<path d="M{x},{y} q4,{h / 2} 0,{h} q-4,{-h / 2} 0,{-h}Z" fill="#d6e4ff" opacity=".55"/>'
    under_band = (f'<path d="M140,214 C162,146 230,110 303,110 C376,110 442,146 464,206 '
                  f'C438,160 376,128 303,128 C230,128 168,160 140,214Z" fill="{HAIR_DK}" opacity=".55"/>')
    crown = (f'<path d="M290,140 C296,150 310,150 316,140" fill="none" stroke="{HAIR_LINE}" stroke-width="1.4" opacity=".6"/>')
    return (f'<clipPath id="clip-hair-front">{clip}</clipPath>'
            f'{cap}{locks}<g clip-path="url(#clip-hair-front)">{under_band}{gloss}</g>{crown}')


def headdress():
    inner_pts = resample(sample_spline([(162, 232), (178, 186), (222, 140), (270, 116), (308, 108),
                                        (352, 110), (398, 122), (436, 156), (462, 200), (476, 244)], 16), 26)
    outer_pts = offset_curve(inner_pts, 28)
    band_in = offset_curve(inner_pts, -2)
    band_out = offset_curve(inner_pts, 8)
    frill = (f'<path d="{scallops(resample(outer_pts, 11), 9)} '
             f'L{fmt(band_out[-1][0])},{fmt(band_out[-1][1])} {polyline(list(reversed(band_out)))}Z" '
             f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2" stroke-linejoin="round"/>')
    pleats = ""
    bumps = resample(outer_pts, 11)
    for a, b in zip(bumps[1:-1], bumps[2:]):
        pass
    for i in range(1, 11):
        p = bumps[i]
        j = min(range(len(band_out)), key=lambda k: math.dist(band_out[k], p))
        q = band_out[j]
        pleats += (f'<path d="M{fmt(q[0])},{fmt(q[1])} Q{fmt((p[0] + q[0]) / 2 + 3)},{fmt((p[1] + q[1]) / 2)} '
                   f'{fmt(p[0])},{fmt(p[1])}" fill="none" stroke="{WHITE_SH}" stroke-width="4" stroke-linecap="round" opacity=".9"/>')
    band = (f'<path d="M{fmt(band_in[0][0])},{fmt(band_in[0][1])} {polyline(band_in[1:])} '
            f'L{fmt(band_out[-1][0])},{fmt(band_out[-1][1])} {polyline(list(reversed(band_out)))}Z" '
            f'fill="#f7f6fb" stroke="{WHITE_LINE}" stroke-width="1.2" stroke-linejoin="round"/>'
            f'<path d="M{fmt(band_in[0][0])},{fmt(band_in[0][1])} {polyline(band_in[1:])}" fill="none" stroke="#2c3466" stroke-width="2" stroke-linecap="round"/>')
    bow = ('<g transform="translate(478,258) rotate(12)">'
           '<path d="M0,0 C-12,-22 -38,-20 -36,0 C-34,16 -14,12 0,0Z M0,0 C12,-22 38,-20 36,0 C34,16 14,12 0,0Z" fill="url(#g-bow)" stroke="#2f6d9e" stroke-width="2" stroke-linejoin="round"/>'
           '<path d="M-4,4 L-14,30 L-5,26 Z M4,4 L14,30 L5,26Z" fill="#4a95cb" stroke="#2f6d9e" stroke-width="1.8" stroke-linejoin="round"/>'
           '<path d="M-8,-6 C-16,-12 -26,-12 -30,-4 M8,-6 C16,-12 26,-12 30,-4" fill="none" stroke="#b6e4fb" stroke-width="2.6" stroke-linecap="round"/>'
           '<ellipse rx="7" ry="8" fill="#5aa6d6" stroke="#2f6d9e" stroke-width="2"/></g>')
    return f'<g class="headdress">{frill}{pleats}{band}{bow}</g>'


def ahoge():
    art = (f'<path d="M318,106 C346,78 350,38 322,24 C298,12 268,26 261,48 C278,36 300,34 314,46 '
           f'C328,60 322,86 302,106Z" fill="url(#g-hair-front)" stroke="{HAIR_LINE}" stroke-width="2" stroke-linejoin="round"/>'
           f'<path d="M320,32 C334,40 340,56 334,74" fill="none" stroke="#7d9ce0" stroke-width="3" stroke-linecap="round" opacity=".7"/>')
    return pivot("ahoge|ahoge-anim", *AHOGE_PIVOT, art)


def face():
    blush = ""
    for x in (221, 385):
        blush += (f'<ellipse cx="{x}" cy="394" rx="32" ry="19" fill="url(#g-blush)"/>'
                  f'<path d="M{x - 12},396 l6,-9 M{x - 3},398 l6,-9 M{x + 6},396 l5,-8" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".85"/>')
    shadow = "".join(f'<path d="{d}" transform="translate(2,9)"/>' for d in bang_paths()[2:])
    return (f'<path d="{FACE_SHAPE}" fill="url(#g-face)" stroke="{SKIN_LINE}" stroke-width="1.8"/>'
            f'<g clip-path="url(#clip-face)" fill="{SKIN_SH}" opacity=".8">{shadow}'
            f'<path d="M190,250 L420,250 L420,272 C380,262 230,262 190,272Z"/></g>'
            f'<g class="blush">{blush}</g>'
            f'<path d="M301,378 l2,2.5" stroke="#d59a8e" stroke-width="2" stroke-linecap="round"/>')


# ---------------------------------------------------------------- arms
def arm(side):
    mirror = side == "r"
    sx, sy = SHOULDER_R if mirror else SHOULDER_L
    upper = (f'<circle cy="{L_UPPER}" r="20" fill="url(#g-sleeve)" stroke="{NAVY_LINE}" stroke-width="2.2"/>'
             f'<path d="M-25,-10 C-32,14 -28,52 -22,80 L-20,{L_UPPER} C-8,{L_UPPER + 9} 8,{L_UPPER + 9} 20,{L_UPPER} '
             f'L22,80 C28,52 32,14 25,-10 C12,-20 -12,-20 -25,-10Z" fill="url(#g-sleeve)" stroke="{NAVY_LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
             f'<path d="M-14,-4 C-20,20 -18,50 -12,80" fill="none" stroke="#46528c" stroke-width="3" stroke-linecap="round" opacity=".6"/>'
             f'<path d="M14,10 C18,40 16,70 14,96" fill="none" stroke="{NAVY_DK}" stroke-width="5" stroke-linecap="round" opacity=".55"/>')
    cuff_pts = resample([(-26, 82), (26, 82)], 6)
    fore = (f'<path d="M-20,-6 L-24,64 L24,64 L20,-6Z" fill="url(#g-sleeve)" stroke="{NAVY_LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
            f'<path d="M12,4 L15,60" stroke="{NAVY_DK}" stroke-width="5" stroke-linecap="round" opacity=".5"/>'
            f'<path d="M-25,58 L25,58 L26,82 L-26,82Z" fill="{NAVY_DK}" stroke="{NAVY_LINE}" stroke-width="2" stroke-linejoin="round"/>'
            f'<path d="M-25,62 L25,62 M-26,78 L26,78" stroke="{GOLD}" stroke-width="1.6"/>'
            f'<path d="M-18,70 l4,-3 l4,3 l4,-3 l4,3 l4,-3 l4,3 l4,-3 l4,3" fill="none" stroke="{GOLD}" stroke-width="1.1" opacity=".9"/>'
            f'<path d="M-26,82 {scallops(list(reversed(cuff_pts)), -5, start=False)[1:]} Z" fill="{WHITE}" stroke="{WHITE_LINE}" stroke-width="1.6"/>')
    hand_open = (f'<g class="hand-open">'
                 f'<path d="M-13,90 C-19,104 -16,122 -6,128 C4,133 15,126 16,112 C17,100 13,92 5,89 C-2,88 -9,88 -13,90Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="1.8" stroke-linejoin="round"/>'
                 f'<path d="M14,96 C21,99 22,108 16,113" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="1.6" stroke-linecap="round"/>'
                 f'<path d="M-5,112 L-6,124 M2,112 L2,126 M8,110 L9,122" stroke="#d9a294" stroke-width="1.3" stroke-linecap="round"/></g>')
    hand_fist = (f'<g class="hand-fist">'
                 f'<path d="M-16,92 C-19,108 -12,120 0,120 C13,120 19,108 16,92 C11,85 -11,85 -16,92Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="1.8"/>'
                 f'<path d="M-10,104 Q-5,99 0,104 Q5,99 10,104" fill="none" stroke="#d9a294" stroke-width="1.6" stroke-linecap="round"/></g>')
    bowl = ""
    if mirror:
        grains = resample([(-28, -46), (-18, -66), (0, -72), (18, -66), (28, -46)], 9)
        bowl = (f'<g transform="translate(0,114)"><g class="bowl"><g transform="scale(1.15)">'
                f'<g class="bowl-steam">'
                f'<path d="M-12,-80 C-20,-92 -4,-100 -12,-114" fill="none" stroke="#bfe8ff" stroke-width="4" stroke-linecap="round"/>'
                f'<path d="M8,-82 C0,-94 16,-102 8,-118" fill="none" stroke="#bfe8ff" stroke-width="4" stroke-linecap="round"/></g>'
                f'<path d="{scallops(grains, 2.2)} Z" fill="#fff" stroke="#c3cfe2" stroke-width="1.8"/>'
                f'<path d="M-36,-46 C-34,-18 -18,-6 0,-6 C18,-6 34,-18 36,-46Z" fill="url(#g-white)" stroke="#2a4c9a" stroke-width="2.2" stroke-linejoin="round"/>'
                f'<path d="M-32,-32 C-18,-24 18,-24 32,-32" fill="none" stroke="#3b82dc" stroke-width="2.6"/>'
                f'<path d="M-20,-20 q5,-5 10,0 t10,0 t10,0 t10,0" fill="none" stroke="#52b6f2" stroke-width="2"/>'
                f'<path d="M-12,-7 L12,-7 L10,0 L-10,0Z" fill="#dbe6f6" stroke="#2a4c9a" stroke-width="2"/>'
                f'<path d="M24,-74 L46,-30 M30,-76 L50,-34" stroke="#9b5a2c" stroke-width="3" stroke-linecap="round"/>'
                f'</g></g></g>')
    fore_group = (f'<g transform="translate(0,{L_UPPER})"><g class="f-pose"><g class="f-anim">'
                  f'{fore}{hand_open}{hand_fist}{bowl}</g></g></g>')
    inner = f'<g class="u-pose"><g class="u-anim">{upper}{fore_group}</g></g>'
    flip = " scale(-1,1)" if mirror else ""
    return f'<g class="arm arm-{side}" transform="translate({sx},{sy}){flip}">{inner}</g>'


# ---------------------------------------------------------------- effects
PUFF = "M0,0 c-14,0 -20,-14 -10,-22 c0,-14 20,-16 24,-6 c12,-4 22,8 14,18 c4,10 -10,16 -16,10 c-4,6 -14,4 -12,0Z"


def head_fx():
    anger = ('<g class="fx fx-angry"><g transform="translate(432,150)"><g class="anger-mark">'
             '<path d="M-6,-20 C-6,-10 -10,-6 -20,-6 M6,-20 C6,-10 10,-6 20,-6 M-6,20 C-6,10 -10,6 -20,6 M6,20 C6,10 10,6 20,6" '
             'fill="none" stroke="#ff3a4f" stroke-width="6.5" stroke-linecap="round"/></g></g>'
             f'<g transform="translate(150,175)"><g class="steam steam-a"><path d="{PUFF}" fill="#fff" stroke="#c9d6ea" stroke-width="2.2"/></g></g>'
             f'<g transform="translate(470,160)"><g class="steam steam-b"><path d="{PUFF}" fill="#fff" stroke="#c9d6ea" stroke-width="2.2"/></g></g>'
             '</g>')
    drop = "M0,-8 C5,-1 7,3 7,6 A7,7 0 1,1 -7,6 C-7,3 -5,-1 0,-8Z"
    tears = ('<g class="fx fx-sad">'
             '<path class="tear-stream" d="M230,380 C227,400 227,425 230,446 L244,446 C246,425 245,400 244,380Z" fill="url(#g-tear)"/>'
             '<path class="tear-stream" d="M362,380 C360,400 360,425 363,446 L377,446 C379,425 378,400 376,380Z" fill="url(#g-tear)"/>'
             f'<g transform="translate(237,446)"><g class="drop drop-a"><path d="{drop}" fill="#9fe0ff" stroke="#4aa6e0" stroke-width="1.4"/></g></g>'
             f'<g transform="translate(370,446)"><g class="drop drop-b"><path d="{drop}" fill="#9fe0ff" stroke="#4aa6e0" stroke-width="1.4"/></g></g>'
             '<g class="gloom" stroke="#7d8fd8" stroke-width="2.6" stroke-linecap="round" opacity=".55">'
             '<path d="M226,180 L226,232 M244,170 L244,240 M262,166 L262,228 M280,164 L280,242"/></g>'
             '</g>')
    sweat = ('<g class="fx fx-sweat"><g transform="translate(168,268)"><g class="sweat">'
             '<path d="M0,-16 C8,-4 11,3 11,8 A11,11 0 1,1 -11,8 C-11,3 -8,-4 0,-16Z" fill="#c9f0ff" stroke="#4aa6e0" stroke-width="2"/>'
             '<path d="M-4,4 Q-5,10 -1,13" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></g></g></g>')
    think_steam = ('<g class="fx fx-overheat">'
                   f'<g transform="translate(200,100)"><g class="steam steam-a"><path d="{PUFF}" fill="#f3f7ff" stroke="#c9d6ea" stroke-width="2.2"/></g></g>'
                   f'<g transform="translate(410,92)"><g class="steam steam-b"><path d="{PUFF}" fill="#f3f7ff" stroke="#c9d6ea" stroke-width="2.2"/></g></g>'
                   '</g>')
    bubble = (f'<circle cx="321" cy="389" r="14" fill="#dff4ff" fill-opacity=".55" stroke="#86c3ec" stroke-width="2"/>'
              f'<path d="M313,382 C315,378 319,377 322,378" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'
              f'<circle cx="328" cy="394" r="2" fill="#fff" opacity=".8"/>')
    snot = f'<g class="fx fx-sleepy">{pivot("snot", 306, 384, bubble)}</g>'
    return anger + tears + sweat + think_steam + snot


def body_fx():
    smug = '<g class="fx fx-smug">'
    for i, (x, y, r) in enumerate([(116, 168, 16), (530, 104, 12), (566, 410, 10), (70, 430, 9)]):
        smug += f'<g transform="translate({x},{y})"><g class="twinkle tw-{i}"><path d="{star4(0, 0, r)}" fill="#ffd36b" stroke="#e5a52a" stroke-width="1.4"/></g></g>'
    smug += "</g>"
    happy = '<g class="fx fx-happy">'
    items = [(84, 270, "heart", "#ff8aa8"), (566, 240, "star", "#ffd36b"), (40, 470, "star", "#7fd8ff"),
             (610, 450, "heart", "#ff9fbc"), (150, 80, "star", "#9fe6ff"), (500, 54, "heart", "#ff8aa8")]
    for i, (x, y, kind, col) in enumerate(items):
        shape = heart(0, 0, 1.1) if kind == "heart" else star4(0, 0, 13)
        happy += f'<g transform="translate({x},{y})"><g class="float-up fu-{i}"><path d="{shape}" fill="{col}" stroke="#fff" stroke-width="2"/></g></g>'
    happy += "</g>"
    cloud = ("M-46,10 C-62,10 -64,-12 -48,-16 C-48,-34 -24,-40 -14,-28 C-6,-44 22,-44 28,-26 "
             "C44,-32 60,-18 52,-4 C64,2 58,20 44,18 C34,26 -36,26 -46,10Z")
    sad = (f'<g class="fx fx-sad"><g transform="translate(128,58)"><g class="rain-cloud">'
           f'<path d="{cloud}" fill="#b7c6e6" stroke="#7b8fbf" stroke-width="2.6"/>'
           f'<path d="M-30,0 C-20,6 10,8 30,2" fill="none" stroke="#dbe5f8" stroke-width="3" stroke-linecap="round"/>'
           f'<g class="rain"><path class="rd rd-0" d="M-24,30 l-4,12"/><path class="rd rd-1" d="M0,32 l-4,12"/><path class="rd rd-2" d="M22,30 l-4,12"/></g>'
           f'</g></g></g>')
    bubble = (f'<g class="fx fx-think"><g class="thought" transform="translate(592,92)">'
              f'<circle cx="-92" cy="88" r="7" fill="#fff" stroke="#7fb4dc" stroke-width="2.4"/>'
              f'<circle cx="-70" cy="64" r="11" fill="#fff" stroke="#7fb4dc" stroke-width="2.4"/>'
              f'<path d="{cloud}" transform="scale(1.25)" fill="#fff" stroke="#7fb4dc" stroke-width="2.2"/>'
              f'<g class="think-dots"><circle class="dot dot-0" cx="-24" cy="0" r="7" fill="#2e7fe0"/>'
              f'<circle class="dot dot-1" cx="0" cy="0" r="7" fill="#2e7fe0"/><circle class="dot dot-2" cx="24" cy="0" r="7" fill="#2e7fe0"/></g>'
              f'<g class="think-scribble"><path d="M-40,4 C-30,-22 -10,20 0,-6 C10,-30 22,22 34,-8 C40,-20 46,6 30,10 C10,16 -20,-18 -34,0" '
              f'fill="none" stroke="#e0485e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
              f'</g>'
              f'<g transform="translate(108,168)"><g class="qmark"><path d="M-9,-10 C-9,-24 12,-24 12,-10 C12,-1 2,0 2,9" fill="none" stroke="#2e7fe0" stroke-width="5.5" stroke-linecap="round"/>'
              f'<circle cx="2" cy="19" r="3.6" fill="#2e7fe0"/></g></g>'
              f'<g transform="translate(98,188)"><g class="bang"><path d="M0,-26 L0,4" stroke="#e0485e" stroke-width="7" stroke-linecap="round"/><circle cy="18" r="4.4" fill="#e0485e"/>'
              f'<path d="M-26,-14 C-26,-28 -6,-28 -6,-14 C-6,-6 -16,-4 -16,4" transform="translate(-6,0)" fill="none" stroke="#2e7fe0" stroke-width="5.5" stroke-linecap="round"/><circle cx="-22" cy="16" r="3.6" fill="#2e7fe0"/></g></g>'
              f'</g>')
    zzz = '<g class="fx fx-sleepy">'
    for i, (x, y, size) in enumerate([(452, 186, 1.0), (476, 172, 1.25), (500, 160, 1.5)]):
        z = (f'<path d="M{fmt(-9 * size)},{fmt(-9 * size)} L{fmt(9 * size)},{fmt(-9 * size)} '
             f'L{fmt(-9 * size)},{fmt(9 * size)} L{fmt(9 * size)},{fmt(9 * size)}" fill="none" stroke="#fff" '
             f'stroke-width="{fmt(8 * size)}" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<path d="M{fmt(-9 * size)},{fmt(-9 * size)} L{fmt(9 * size)},{fmt(-9 * size)} '
             f'L{fmt(-9 * size)},{fmt(9 * size)} L{fmt(9 * size)},{fmt(9 * size)}" fill="none" stroke="#4f74d0" '
             f'stroke-width="{fmt(3.6 * size)}" stroke-linecap="round" stroke-linejoin="round"/>')
        zzz += f'<g transform="translate({x},{y})"><g class="zz zz-{i}">{z}</g></g>'
    zzz += "</g>"
    eighth = ('<ellipse rx="8" ry="6" transform="rotate(-22)"/><path d="M4.5,-2 L4.5,-32 L8,-32 L8,-2Z"/>'
              '<path d="M8,-32 C14,-28 20,-22 17,-12 C16,-18 12,-21 8,-22Z"/>')
    beamed = ('<ellipse rx="8" ry="6" transform="rotate(-22)"/><ellipse cx="22" cy="-5" rx="8" ry="6" transform="rotate(-22,22,-5)"/>'
              '<path d="M4.5,-2 L4.5,-30 L8,-30 L8,-2Z M26.5,-7 L26.5,-35 L30,-35 L30,-7Z M4.5,-32 L30,-37 L30,-30 L4.5,-25Z"/>')
    dance = '<g class="fx fx-dance">'
    for i, (x, y, s, kind, col) in enumerate([(70, 340, 1.3, eighth, "#ff8aa8"), (592, 300, 1.2, beamed, "#7fd8ff"),
                                              (40, 540, 1.1, beamed, "#ffd36b"), (624, 520, 1.25, eighth, "#ff9fbc"),
                                              (116, 150, 1.0, beamed, "#9fe6ff"), (508, 120, 1.1, eighth, "#ffd36b")]):
        dance += (f'<g transform="translate({x},{y}) scale({s})"><g class="note nt-{i}">'
                  f'<g fill="#fff" stroke="#fff" stroke-width="5" stroke-linejoin="round">{kind}</g>'
                  f'<g fill="{col}">{kind}</g></g></g>')
    dance += "</g>"
    return smug + happy + sad + bubble + zzz + dance


def pillow():
    """A little whale plush, only visible in the sleepy pose (hugged against her chest)."""
    cx, cy = PILLOW
    body = (f"M{cx - 92},{cy + 6} C{cx - 96},{cy - 34} {cx - 50},{cy - 56} {cx + 4},{cy - 54} "
            f"C{cx + 56},{cy - 52} {cx + 86},{cy - 30} {cx + 88},{cy + 2} "
            f"C{cx + 90},{cy + 36} {cx + 50},{cy + 56} {cx - 4},{cy + 56} "
            f"C{cx - 56},{cy + 56} {cx - 90},{cy + 40} {cx - 92},{cy + 6}Z")
    belly = (f"M{cx - 78},{cy + 18} C{cx - 50},{cy + 46} {cx + 44},{cy + 48} {cx + 76},{cy + 16} "
             f"C{cx + 66},{cy + 44} {cx + 34},{cy + 56} {cx - 4},{cy + 56} C{cx - 44},{cy + 56} {cx - 70},{cy + 42} {cx - 78},{cy + 18}Z")
    fluke = (f"M{cx + 80},{cy - 8} C{cx + 96},{cy - 30} {cx + 112},{cy - 44} {cx + 128},{cy - 46} "
             f"C{cx + 122},{cy - 30} {cx + 116},{cy - 22} {cx + 108},{cy - 14} "
             f"C{cx + 122},{cy - 10} {cx + 132},{cy - 2} {cx + 136},{cy + 8} C{cx + 118},{cy + 10} {cx + 98},{cy + 6} {cx + 84},{cy + 4}Z")
    art = (f'<path d="{fluke}" fill="url(#g-bow)" stroke="#2f6d9e" stroke-width="2.2" stroke-linejoin="round"/>'
           f'<path d="{body}" fill="url(#g-bow)" stroke="#2f6d9e" stroke-width="2.4" stroke-linejoin="round"/>'
           f'<path d="{belly}" fill="#f4f9ff" stroke="#9cc4e4" stroke-width="1.6" stroke-linejoin="round"/>'
           f'<path d="M{cx - 70},{cy - 26} C{cx - 50},{cy - 44} {cx - 16},{cy - 48} {cx + 12},{cy - 46}" fill="none" stroke="#c9ecff" stroke-width="5" stroke-linecap="round" opacity=".8"/>'
           f'<path d="M{cx - 30},{cy - 22} q8,8 16,0 M{cx + 14},{cy - 22} q8,8 16,0" fill="none" stroke="#1b2f62" stroke-width="3" stroke-linecap="round"/>'
           f'<ellipse cx="{cx - 36}" cy="{cy - 8}" rx="8" ry="4.5" fill="#ffb2c4" opacity=".8"/>'
           f'<ellipse cx="{cx + 36}" cy="{cy - 8}" rx="8" ry="4.5" fill="#ffb2c4" opacity=".8"/>'
           f'<path d="M{cx - 4},{cy - 10} q4,4 8,0" fill="none" stroke="#1b2f62" stroke-width="2.2" stroke-linecap="round"/>'
           f'<path d="M{cx - 6},{cy - 54} C{cx - 10},{cy - 66} {cx - 16},{cy - 70} {cx - 22},{cy - 70} '
           f'M{cx - 6},{cy - 54} C{cx - 2},{cy - 66} {cx + 4},{cy - 70} {cx + 10},{cy - 70}" fill="none" stroke="#4fa8e0" stroke-width="3" stroke-linecap="round"/>'
           f'<path d="M{cx - 80},{cy + 22} C{cx - 56},{cy + 14} {cx + 50},{cy + 12} {cx + 80},{cy + 18}" fill="none" stroke="#9cc4e4" stroke-width="1.2" stroke-dasharray="4 5" opacity=".9"/>')
    return f'<g class="pillow">{pivot("pillow-squish", cx, cy + 56, art)}</g>'


def build(moods):
    """moods: the output of compile_moods() — {"css", "registry", "poses"}."""
    names = [m["name"] for m in moods["registry"]]
    default = next((m["name"] for m in moods["registry"] if m["default"]), names[0])
    mood_list = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1060" role="img" '
            f'aria-labelledby="title desc" class="whale-chan" data-mood="{default}" data-strain="0">\n'
            f'  <title id="title">Whale-chan</title>\n'
            f'  <desc id="desc">A chibi DeepSeek whale maid drawn as rigged vector art. Her body, face, tail, '
            f'fin-ears and ahoge are posed and animated per mood: {mood_list}.</desc>'
            f'{DEFS}{css(moods["css"])}\n  {ART}\n</svg>\n')


def art():
    head_back = pivot("head-pose|head-anim", NECK[0], NECK[1], hair_back())
    eyes = eye(EYE_L[0], EYE_L[1], -1) + eye(EYE_R[0], EYE_R[1], 1)
    head_front_inner = (f'{fin_ear(True)}{fin_ear(False)}{face()}{eyes}{mouths()}{front_hair()}{brows()}'
                        f'{headdress()}{ahoge()}{head_fx()}')
    head_front = pivot("head-pose|head-anim", NECK[0], NECK[1], head_front_inner)
    upper = (f'<g class="upper"><g class="upper-anim">{head_back}{torso()}{head_front}'
             f'{pillow()}{arm("l")}{arm("r")}</g></g>')
    return (f'<g transform="{ART_TRANSFORM}"><g transform="translate({FEET[0]},{FEET[1]})"><g class="char-pose"><g class="char-anim">'
            f'<g transform="translate({-FEET[0]},{-FEET[1]})">{tail()}{legs()}{upper}{body_fx()}</g></g></g></g></g>')


ART = art()


# ---------------------------------------------------------------- rig catalog (assets/rig.json)
# Motion parts the mood data may animate: name -> (selector, pivot in art space, label).
RIG_PARTS = {
    "body": (".char-anim", FEET, "Whole body (pivots at the feet)"),
    "upper": (".upper-anim", (0, 0), "Upper body (breathing; translate only)"),
    "head": (".head-anim", NECK, "Head"),
    "arm-l.u": (".arm-l .u-anim", SHOULDER_L, "Left upper arm (shoulder)"),
    "arm-l.f": (".arm-l .f-anim", (SHOULDER_L[0], SHOULDER_L[1] + L_UPPER), "Left forearm (elbow; pivot follows the upper arm)"),
    "arm-r.u": (".arm-r .u-anim", SHOULDER_R, "Right upper arm (shoulder)"),
    "arm-r.f": (".arm-r .f-anim", (SHOULDER_R[0], SHOULDER_R[1] + L_UPPER), "Right forearm (elbow; pivot follows the upper arm)"),
    "leg-l": (".leg-l", HIP_L, "Left leg (hip)"),
    "leg-r": (".leg-r", HIP_R, "Right leg (hip)"),
    "tail": (".tail-wag", TAIL_PIVOT, "Tail"),
    "fluke": (".fluke", FLUKE_PIVOT, "Tail fluke"),
    "ear-l": (".ear-flap-l", (mx(EAR_PIVOT[0]), EAR_PIVOT[1]), "Left fin-ear"),
    "ear-r": (".ear-flap-r", EAR_PIVOT, "Right fin-ear"),
    "ahoge": (".ahoge-anim", AHOGE_PIVOT, "Ahoge"),
    "lock-l": (".lock-l", BANGS[0][0][0], "Left side lock"),
    "lock-r": (".lock-r", BANGS[1][0][0], "Right side lock"),
    "blink": (".blink", None, "Eye blink (scaleY about each eye centre)"),
}
# Pose variables bound in css(): name -> (default, unit, min, max, step, label).
POSE_VARS = {
    "hr": ("0deg", "deg", -20, 20, 0.5, "Head tilt"),
    "hx": ("0px", "px", -20, 20, 1, "Head shift X"),
    "hy": ("0px", "px", -20, 20, 1, "Head shift Y"),
    "bl-r": ("0deg", "deg", -30, 30, 1, "Left brow angle"),
    "bl-y": ("0px", "px", -12, 12, 1, "Left brow height"),
    "br-r": ("0deg", "deg", -30, 30, 1, "Right brow angle"),
    "br-y": ("0px", "px", -12, 12, 1, "Right brow height"),
    "ix": ("0px", "px", -14, 14, 1, "Gaze X"),
    "iy": ("0px", "px", -14, 14, 1, "Gaze Y"),
    "is": ("1", "", 0.6, 1.4, 0.01, "Iris size"),
    "ear": ("0deg", "deg", -40, 40, 1, "Fin-ears"),
    "ahoge": ("0deg", "deg", -60, 60, 1, "Ahoge"),
    "tail": ("0deg", "deg", -30, 30, 1, "Tail"),
    "cy": ("0px", "px", -20, 20, 1, "Body drop"),
    "cs": ("1", "", 0.9, 1.1, 0.005, "Body squash"),
    "blush": (".75", "", 0, 1, 0.05, "Blush"),
}
# Expression layers: hidden until a mood shows them, except these, which moods may hide.
VISIBLE_LAYERS = ["eye-open", "lash-default", "hl"]
LAYER_FAMILIES = ["mouth", "lid", "eye-alt", "fx"]   # class="<family> <layer>"
LAYER_GROUPS = [  # (key, label, classes that file an element under the group)
    ("eyes", "Eyes", ["eye-open", "eye-alt"]),
    ("lids", "Eyelids", ["lid"]),
    ("eyeDetails", "Eye details", ["lash-default", "hl", "hl-sad", "tear-pool"]),
    ("mouths", "Mouths", ["mouth"]),
    ("effects", "Effects", ["fx"]),
    ("props", "Props", ["bowl", "pillow"]),
    ("thought", "Thought bubble", ["think-dots", "think-scribble", "qmark", "bang"]),
]
HIDDEN_LAYERS = [c for _, _, cs in LAYER_GROUPS for c in cs if c not in VISIBLE_LAYERS]
LAYER_LABELS = {
    "eye-open": "Open eyes", "eye-happy": "Happy arcs ^^", "eye-squeeze": "Squeezed > <", "eye-swirl": "Dizzy swirls",
    "eye-sleep": "Sleeping lines", "lid-angry": "Angry lids", "lid-smug": "Smug half-lids", "lid-sad": "Sad lids",
    "lash-default": "Default lashes", "hl": "Eye sparkle", "hl-sad": "Teary sparkle", "tear-pool": "Tear pool",
    "m-neutral": "Neutral smile", "m-angry": "Angry shout", "m-smug": "Smug cat mouth", "m-happy": "Open smile",
    "m-sad": "Wobbly frown", "m-think0": "Small 'o'", "m-think1": "Wavy strain", "m-think2": "Jagged panic",
    "m-sleepy": "Snoring", "fx-angry": "Anger mark + steam", "fx-sad": "Tears, rain cloud, gloom",
    "fx-sweat": "Sweat drop", "fx-overheat": "Overheat steam", "fx-sleepy": "Zzz + snot bubble",
    "fx-smug": "Twinkles", "fx-happy": "Hearts + stars", "fx-think": "Thought bubble", "fx-dance": "Music notes",
    "bowl": "Rice bowl", "pillow": "Whale plush", "think-dots": "Thinking dots", "think-scribble": "Scribble",
    "qmark": "Question mark", "bang": "?! mark",
}


def layer_catalog(markup):
    groups = {key: {"label": label, "items": {}} for key, label, _ in LAYER_GROUPS}
    owner = {c: key for key, _, cs in LAYER_GROUPS for c in cs}
    for attr in re.findall(r'class="([^"]+)"', markup):
        tokens = attr.split()
        hit = next((t for t in tokens if t in owner), None)
        if not hit:
            continue
        if hit in LAYER_FAMILIES and len(tokens) < 2:
            continue
        layer = tokens[-1] if hit in LAYER_FAMILIES else hit
        groups[owner[hit]]["items"].setdefault(layer, {
            "label": LAYER_LABELS.get(layer, layer.replace("-", " ").capitalize()),
            "default": "visible" if layer in VISIBLE_LAYERS else "hidden",
        })
    return groups


def rig():
    for part, (selector, _, _) in RIG_PARTS.items():
        for cls in re.findall(r"\.([\w-]+)", selector):
            assert re.search(rf'class="(?:[^"]* )?{cls}[ "]', ART), f"{part}: no .{cls} in the art"
    return {
        "version": 1,
        "viewBox": [0, 0, 900, 1060],
        "art": {"transform": ART_TRANSFORM, "offset": list(ART_OFFSET), "scale": ART_SCALE},
        "mirrorX": MX,
        "neck": list(NECK),
        "feet": list(FEET),
        "arms": {
            "upper": L_UPPER, "fore": L_FORE,
            "l": {"shoulder": list(SHOULDER_L), "vars": {"u": "--lu", "f": "--lf", "fist": "--lfist"}},
            "r": {"shoulder": list(SHOULDER_R), "mirrored": True, "vars": {"u": "--ru", "f": "--rf", "fist": "--rfist"}},
        },
        "parts": {name: {"selector": sel, "pivot": list(pv) if pv else None, "label": label}
                  for name, (sel, pv, label) in RIG_PARTS.items()},
        "poseVars": {name: {"default": d, "unit": u, "min": lo, "max": hi, "step": st, "label": label}
                     for name, (d, u, lo, hi, st, label) in POSE_VARS.items()},
        "layers": layer_catalog(ART),
    }


def dump_json(obj):
    """Indented JSON with short number lists kept on one line."""
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    return re.sub(r"\[\s+(-?[\d.]+(?:,\s+-?[\d.]+)*)\s+\]",
                  lambda m: "[" + ", ".join(m.group(1).replace(",", " ").split()) + "]", text) + "\n"


def compile_moods(rig_path):
    cmd = ["node", str(HERE / "compile_moods.mjs"), "--rig", str(rig_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE.parent)
    except FileNotFoundError:
        sys.exit("build_whale_chan: Node.js (`node`) is required to compile moods/*.json")
    if res.returncode:
        sys.stderr.write(res.stderr)
        sys.exit(res.returncode)
    return json.loads(res.stdout)


# ---------------------------------------------------------------- CSS
def css(mood_css):
    """Static art CSS (pose-variable bindings, layer defaults, effect loops) + the compiled mood CSS."""
    hidden = ", ".join(f".{c}" for c in HIDDEN_LAYERS)
    return f"""
  <style><![CDATA[
    .whale-chan {{ overflow: visible; }}
    g {{ transform-box: view-box; }}

    .char-pose {{ transform: translateY(var(--cy)) scale(1, var(--cs)); transition: transform .6s cubic-bezier(.34,1.4,.64,1); }}
    .head-pose {{ transform: translate(var(--hx), var(--hy)) rotate(var(--hr)); transition: transform .55s cubic-bezier(.34,1.5,.64,1); }}
    .arm-l .u-pose {{ transform: rotate(var(--lu)); }}
    .arm-l .f-pose {{ transform: rotate(var(--lf)); }}
    .arm-r .u-pose {{ transform: rotate(var(--ru)); }}
    .arm-r .f-pose {{ transform: rotate(var(--rf)); }}
    .u-pose, .f-pose {{ transition: transform .6s cubic-bezier(.34,1.45,.64,1); }}
    .arm-l .hand-fist {{ opacity: var(--lfist); }}
    .arm-l .hand-open {{ opacity: calc(1 - var(--lfist)); }}
    .arm-r .hand-fist {{ opacity: var(--rfist); }}
    .arm-r .hand-open {{ opacity: calc(1 - var(--rfist)); }}
    .brow-l {{ transform: translateY(var(--bl-y)) rotate(var(--bl-r)); }}
    .brow-r {{ transform: translateY(var(--br-y)) rotate(var(--br-r)); }}
    .brow {{ transition: transform .4s cubic-bezier(.34,1.5,.64,1); }}
    .iris-pose {{ transform: translate(var(--ix), var(--iy)) scale(var(--is)); transition: transform .45s ease; }}
    .ear {{ transform: rotate(var(--ear)); transition: transform .5s cubic-bezier(.34,1.5,.64,1); }}
    .ahoge {{ transform: rotate(var(--ahoge)); transition: transform .6s cubic-bezier(.34,1.6,.64,1); }}
    .tail-pose {{ transform: rotate(var(--tail)); transition: transform .7s cubic-bezier(.34,1.4,.64,1); }}
    .blush {{ opacity: var(--blush); transition: opacity .4s ease; }}
    .bowl {{ transform: rotate(calc(-1 * (var(--ru) + var(--rf)))); transition: transform .6s cubic-bezier(.34,1.45,.64,1), opacity .25s ease; }}

    /* expression layers: moods show/hide them (opacity) */
    {hidden} {{
      opacity: 0; transition: opacity .25s ease;
    }}
    .lash-default, .eye-open {{ transition: opacity .2s ease; }}

    /* ---------- effect layers (they only show in the moods that reveal them) ---------- */
    .anger-mark {{ animation: anger-pulse .55s ease-in-out infinite; }}
    .fx-angry .steam {{ animation: steam-puff 1.1s ease-out infinite; }}
    .fx-angry .steam-b {{ animation-delay: -.55s; }}
    .twinkle {{ animation: twinkle 1.8s ease-in-out infinite; }}
    .tw-1 {{ animation-delay: -.5s; }} .tw-2 {{ animation-delay: -1.1s; }} .tw-3 {{ animation-delay: -1.4s; }}
    .float-up {{ animation: float-up 2.4s ease-out infinite; }}
    .fu-1 {{ animation-delay: -.4s; }} .fu-2 {{ animation-delay: -.8s; }} .fu-3 {{ animation-delay: -1.2s; }}
    .fu-4 {{ animation-delay: -1.6s; }} .fu-5 {{ animation-delay: -2s; }}
    .bowl-steam path {{ animation: wisp 1.6s ease-in-out infinite; }}
    .bowl-steam path + path {{ animation-delay: -.8s; }}
    .quiver {{ animation: quiver .2s linear infinite; }}
    .tear-stream {{ animation: shimmer 1.2s ease-in-out infinite; }}
    .drop {{ animation: drip 1.3s ease-in infinite; }}
    .drop-b {{ animation-delay: -.65s; }}
    .rain-cloud {{ animation: cloud-bob 3s ease-in-out infinite; }}
    .rd {{ stroke: #7fb6ea; stroke-width: 3.5; stroke-linecap: round; animation: rain .9s linear infinite; }}
    .rd-1 {{ animation-delay: -.3s; }} .rd-2 {{ animation-delay: -.6s; }}
    .gloom {{ animation: gloom 2.4s ease-in-out infinite; }}
    .dot {{ animation: dot 1.2s ease-in-out infinite; }}
    .dot-1 {{ animation-delay: .2s; }} .dot-2 {{ animation-delay: .4s; }}
    .qmark {{ animation: q-bob 1.8s ease-in-out infinite; }}
    .sweat {{ animation: sweat 1.4s ease-in infinite; }}
    .swirl {{ animation: spin 1s linear infinite; }}
    .fx-overheat .steam {{ animation: steam-puff 1s ease-out infinite; }}
    .fx-overheat .steam-b {{ animation-delay: -.5s; }}
    .think-scribble {{ animation: scribble .5s steps(3) infinite; }}
    .bang {{ animation: q-bob .5s ease-in-out infinite; }}
    .pillow-squish {{ animation: pillow-squish 4.8s ease-in-out infinite; }}
    .snore {{ animation: snore 4.8s ease-in-out infinite; }}
    .snot {{ animation: snot-bubble 4.8s ease-in-out infinite; }}
    .zz {{ animation: zz-float 4.8s ease-out infinite; }}
    .zz-1 {{ animation-delay: -1.6s; }} .zz-2 {{ animation-delay: -3.2s; }}
    .note {{ animation: note-float 1.6s ease-out infinite; }}
    .nt-1 {{ animation-delay: -.8s; }} .nt-2 {{ animation-delay: -.4s; }} .nt-3 {{ animation-delay: -1.2s; }}
    .nt-4 {{ animation-delay: -1s; }} .nt-5 {{ animation-delay: -.2s; }}

    @keyframes anger-pulse {{ 0%, 100% {{ transform: scale(.85); }} 50% {{ transform: scale(1.15); }} }}
    @keyframes steam-puff {{
      0% {{ transform: translate(0, 10px) scale(.4); opacity: 0; }}
      25% {{ opacity: 1; }}
      100% {{ transform: translate(0, -46px) scale(1.25); opacity: 0; }}
    }}
    @keyframes twinkle {{ 0%, 100% {{ transform: scale(.2) rotate(0); opacity: 0; }} 50% {{ transform: scale(1) rotate(45deg); opacity: 1; }} }}
    @keyframes float-up {{
      0% {{ transform: translateY(20px) scale(.3) rotate(-10deg); opacity: 0; }}
      20% {{ opacity: 1; }}
      100% {{ transform: translateY(-70px) scale(1.1) rotate(14deg); opacity: 0; }}
    }}
    @keyframes wisp {{ 0%, 100% {{ transform: translateY(4px); opacity: .2; }} 50% {{ transform: translateY(-6px); opacity: .95; }} }}
    @keyframes quiver {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(1px); }} }}
    @keyframes shimmer {{ 0%, 100% {{ opacity: .7; }} 50% {{ opacity: 1; }} }}
    @keyframes drip {{
      0% {{ transform: translate(0, -6px) scale(.4); opacity: 0; }}
      20% {{ transform: translate(0, 0) scale(1); opacity: 1; }}
      100% {{ transform: translate(0, 120px) scale(.9); opacity: 0; }}
    }}
    @keyframes cloud-bob {{ 0%, 100% {{ transform: translate(0, 0); }} 50% {{ transform: translate(6px, -4px); }} }}
    @keyframes rain {{ 0% {{ transform: translate(0, -6px); opacity: 0; }} 30% {{ opacity: 1; }} 100% {{ transform: translate(-6px, 30px); opacity: 0; }} }}
    @keyframes gloom {{ 0%, 100% {{ opacity: .35; }} 50% {{ opacity: .7; }} }}
    @keyframes dot {{ 0%, 100% {{ transform: translateY(0); opacity: .35; }} 40% {{ transform: translateY(-6px); opacity: 1; }} }}
    @keyframes q-bob {{ 0%, 100% {{ transform: translateY(0) rotate(-8deg); }} 50% {{ transform: translateY(-8px) rotate(8deg); }} }}
    @keyframes sweat {{ 0% {{ transform: translateY(-6px); opacity: 0; }} 25% {{ opacity: 1; }} 100% {{ transform: translateY(26px); opacity: 0; }} }}
    @keyframes spin {{ from {{ transform: rotate(0); }} to {{ transform: rotate(360deg); }} }}
    @keyframes pillow-squish {{ 0%, 100% {{ transform: scale(1, 1); }} 45% {{ transform: scale(1.025, .965); }} }}
    @keyframes snore {{ 0%, 100% {{ transform: scale(.8, .65); }} 45% {{ transform: scale(1, 1.15); }} }}
    @keyframes snot-bubble {{
      0%, 100% {{ transform: scale(.25); }}
      45% {{ transform: scale(1.05); }}
      55% {{ transform: scale(1); }}
    }}
    @keyframes zz-float {{
      0% {{ transform: translate(0, 10px) scale(.35) rotate(-12deg); opacity: 0; }}
      18% {{ opacity: 1; }}
      100% {{ transform: translate(64px, -118px) scale(1.15) rotate(10deg); opacity: 0; }}
    }}
    @keyframes scribble {{ 0% {{ transform: rotate(0); }} 33% {{ transform: rotate(8deg) scale(1.05); }} 66% {{ transform: rotate(-6deg) scale(.95); }} }}
    @keyframes note-float {{
      0% {{ transform: translate(0, 16px) scale(.4) rotate(-14deg); opacity: 0; }}
      20% {{ opacity: 1; }}
      50% {{ transform: translate(8px, -28px) scale(1) rotate(10deg); }}
      100% {{ transform: translate(-4px, -72px) scale(1.1) rotate(-8deg); opacity: 0; }}
    }}

    /* moods:begin (replaced live by the mood editor) */
{mood_css}
    /* moods:end */

    /* ---------- pause while dragging, honour reduced motion ---------- */
    .is-paused * {{ animation-play-state: paused !important; }}
    .reduce-motion *, .reduce-motion *::before {{ animation: none !important; transition-duration: .01ms !important; }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; transition-duration: .01ms !important; }}
    }}
  ]]></style>"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rig_path = OUT.parent / "rig.json"
    rig_path.write_text(dump_json(rig()))
    moods = compile_moods(rig_path)
    (OUT.parent / "moods.json").write_text(dump_json(moods["registry"]))
    OUT.write_text(build(moods))
    print(f"wrote {OUT}, {rig_path.name}, moods.json")
    for name, pose in moods["poses"].items():
        print(f"  {name:10s} left arm {tuple(pose['l'])}  right arm {tuple(pose['r'])}  fist {pose['fist']}")
