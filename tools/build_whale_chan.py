#!/usr/bin/env python3
"""Builds assets/whale-chan.svg — a hand-rigged, anime-styled vector Whale-chan.

    python3 tools/build_whale_chan.py [output.svg]

The SVG is the shipped artifact; this script is only needed to change the art or poses.
The art is traced in the coordinate space of reference/isolated/whalechan-art-master.webp
and placed on the 900x1060 canvas by ART_TRANSFORM. Arm poses are solved with two-bone IK
from hand targets (see the P table).

Every body part lives in its own pivot group so CSS can pose and animate it:
  .char-pose > .char-anim                      whole body (hops, stomps, sways)
  .upper-anim                                  breathing torso / head / arms
  .head-pose > .head-anim                      head tilt (back hair + face share it)
  .arm-l/.arm-r  > .u-pose > .u-anim           shoulder joint
                 > .f-pose > .f-anim           elbow joint
  .tail-pose > .tail-wag > .fluke              tail + fluke flick
  .ear-l/.ear-r, .ahoge, .lock-l/.lock-r, .brow-l/.brow-r, .iris-pose, eyelids, mouths
"""
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets" / "whale-chan.svg"
CX = 303  # mirror axis used by the IK helper


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def mirror_x(x):
    return 2 * CX - x


# ---------------------------------------------------------------- geometry
def ik(shoulder, target, right=False, elbow_out=True):
    """Two-bone IK in the left-arm frame (arm hangs along +y, rotate() positive swings outward)."""
    sx, sy = shoulder
    tx, ty = target
    if right:
        sx, tx = mirror_x(sx), mirror_x(tx)
    dx, dy = tx - sx, ty - sy
    d = max(abs(L_UPPER - L_FORE) + 1, min(math.hypot(dx, dy), L_UPPER + L_FORE - 0.5))
    phi = math.atan2(-dx, dy)
    a = math.acos((L_UPPER ** 2 + d * d - L_FORE ** 2) / (2 * L_UPPER * d))
    options = []
    for sgn in (1, -1):
        t1 = phi + sgn * a
        ex, ey = sx - L_UPPER * math.sin(t1), sy + L_UPPER * math.cos(t1)
        t12 = math.atan2(-(tx - ex), ty - ey)
        t2 = (t12 - t1 + math.pi) % (2 * math.pi) - math.pi
        t1n = (t1 + math.pi) % (2 * math.pi) - math.pi
        options.append((ex, math.degrees(t1n), math.degrees(t2)))
    options.sort(key=lambda o: o[0], reverse=not elbow_out)
    _, u, f = options[0]
    return round(u, 1), round(f, 1)


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
ART_TRANSFORM = f"translate(152,88) scale({ART_SCALE})"
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


# ---------------------------------------------------------------- poses
P = {}
P["neutral"] = dict(l=ik(SHOULDER_L, (125, 680)), r=ik(SHOULDER_R, (mx(125), 680), right=True))
P["angry"] = dict(l=(46, 128), r=(46, 128), fist="both")
P["smug"] = dict(l=ik(SHOULDER_L, (238, 594)), r=ik(SHOULDER_R, (mx(238), 594), right=True), fist="both")
P["happy"] = dict(l=ik(SHOULDER_L, (150, 330)), r=ik(SHOULDER_R, (462, 316), right=True), fist="l")
P["sad"] = dict(l=(-4, 6), r=ik(SHOULDER_R, (366, 374), right=True), fist="r")
_think_r = ik(SHOULDER_R, (322, 440), right=True, elbow_out=False)


def _elbow(shoulder, angle, right=False):
    sx, sy = shoulder
    a = math.radians(angle)
    ex = sx + L_UPPER * math.sin(a) if right else sx - L_UPPER * math.sin(a)
    return ex, sy + L_UPPER * math.cos(a)


_re = _elbow(SHOULDER_R, _think_r[0], right=True)
P["think0"] = dict(l=ik(SHOULDER_L, (_re[0] - 10, _re[1] + 8)), r=_think_r, fist="l")
P["think1"] = dict(l=ik(SHOULDER_L, (172, 334)), r=ik(SHOULDER_R, (mx(172), 334), right=True))
P["think2"] = dict(l=ik(SHOULDER_L, (152, 304)), r=ik(SHOULDER_R, (mx(152), 304), right=True))


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
    inner = pivot("fluke", 632, 708, fluke_art) + stem_art
    return pivot("tail-pose|tail-wag", 430, 806, inner)


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
    out = ""
    for d, shade in [("M206,780 L276,780 C276,846 272,894 270,938 L224,938 C220,894 210,846 206,780Z",
                      "M260,820 C258,860 257,900 256,930"),
                     ("M330,780 L402,780 C400,846 394,894 392,938 L344,938 C342,894 334,846 330,780Z",
                      "M346,820 C348,860 350,900 352,930")]:
        out += (f'<path d="{d}" fill="{WHITE}" stroke="{WHITE_LINE}" stroke-width="2"/>'
                f'<path d="{shade}" fill="none" stroke="{WHITE_SH}" stroke-width="7" stroke-linecap="round"/>')
    shoes = ""
    for cx, buckle_side in [(247, -1), (369, 1)]:
        b = cx + buckle_side * 22
        shoes += (f'<path d="M{cx - 26},946 C{cx - 30},972 {cx - 20},992 {cx},993 C{cx + 22},994 {cx + 31},976 {cx + 27},946 '
                  f'C{cx + 14},956 {cx - 14},956 {cx - 26},946Z" fill="{NAVY}" stroke="{NAVY_LINE}" stroke-width="2.2" stroke-linejoin="round"/>'
                  f'<path d="M{cx - 26},946 C{cx - 14},956 {cx + 14},956 {cx + 27},946" fill="none" stroke="#4a568e" stroke-width="1.6" opacity=".8"/>'
                  f'<path d="M{cx - 24},934 C{cx - 10},942 {cx + 12},942 {cx + 26},934" fill="none" stroke="{NAVY}" stroke-width="6.5" stroke-linecap="round"/>'
                  f'<path d="M{cx - 24},934 C{cx - 10},942 {cx + 12},942 {cx + 26},934" fill="none" stroke="{NAVY_LINE}" stroke-width="1.2" stroke-linecap="round" opacity=".6"/>'
                  f'<circle cx="{b}" cy="938" r="6.5" fill="{NAVY}" stroke="{GOLD}" stroke-width="2.8"/>'
                  f'<path d="M{cx - 18},976 C{cx - 12},986 {cx},989 {cx + 10},987" fill="none" stroke="#6a77b4" stroke-width="3" stroke-linecap="round" opacity=".7"/>'
                  f'<path d="M{cx - 22},984 C{cx - 12},992 {cx + 14},992 {cx + 24},982" fill="none" stroke="{NAVY_DK}" stroke-width="4" stroke-linecap="round"/>')
    return f'<g class="legs">{out}{shoes}</g>'


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
    art = f'<g transform="rotate(14,466,320)">{art}</g>'
    if mirror:
        return pivot("ear ear-l|ear-flap-l", mx(466), 320, art, mirror=True, src=(466, 320))
    return pivot("ear ear-r|ear-flap-r", 466, 320, art)


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
    swirl = (f'<g class="eye-alt eye-swirl"><circle cx="6" r="27" fill="#fff" stroke="{LASH}" stroke-width="2.4"/>'
             f'<g transform="translate(6,0)"><g class="swirl"><path d="{spiral(r=22)}" fill="none" stroke="#2a56b0" stroke-width="3.6" stroke-linecap="round"/></g></g></g>')
    return (f'<g transform="translate({cx},{cy}) scale({s},1)">'
            f'{open_eye}{happy}{squeeze}{swirl}</g>')


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
    return pivot("ahoge|ahoge-anim", 306, 104, art)


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
    return anger + tears + sweat + think_steam


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
    return smug + happy + sad + bubble


def build():
    head_back = pivot("head-pose|head-anim", NECK[0], NECK[1], hair_back())
    eyes = eye(EYE_L[0], EYE_L[1], -1) + eye(EYE_R[0], EYE_R[1], 1)
    head_front_inner = (f'{fin_ear(True)}{fin_ear(False)}{face()}{eyes}{mouths()}{front_hair()}{brows()}'
                        f'{headdress()}{ahoge()}{head_fx()}')
    head_front = pivot("head-pose|head-anim", NECK[0], NECK[1], head_front_inner)
    upper = (f'<g class="upper"><g class="upper-anim">{head_back}{torso()}{head_front}'
             f'{arm("l")}{arm("r")}</g></g>')
    char = (f'<g transform="{ART_TRANSFORM}"><g transform="translate({FEET[0]},{FEET[1]})"><g class="char-pose"><g class="char-anim">'
            f'<g transform="translate({-FEET[0]},{-FEET[1]})">{tail()}{legs()}{upper}{body_fx()}</g></g></g></g></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1060" role="img" '
            f'aria-labelledby="title desc" class="whale-chan" data-mood="neutral" data-strain="0">\n'
            f'  <title id="title">Whale-chan</title>\n'
            f'  <desc id="desc">A chibi DeepSeek whale maid drawn as rigged vector art. Her body, face, tail, '
            f'fin-ears and ahoge are posed and animated per mood: neutral, angry, smug, happy, sad and thinking.</desc>'
            f'{DEFS}{css()}\n  {char}\n</svg>\n')


# ---------------------------------------------------------------- CSS
def css():
    def arm_vars(p):
        lu, lf = p["l"]
        ru, rf = p["r"]
        fist = p.get("fist", "")
        return (f"--lu:{lu}deg;--lf:{lf}deg;--ru:{ru}deg;--rf:{rf}deg;"
                f"--lfist:{1 if fist in ('l', 'both') else 0};--rfist:{1 if fist in ('r', 'both') else 0};")

    sel = {
        "neutral": '.whale-chan[data-mood="neutral"], .whale-chan:not([data-mood])',
        "angry": '.whale-chan[data-mood="angry"]',
        "smug": '.whale-chan[data-mood="smug"]',
        "happy": '.whale-chan[data-mood="happy"]',
        "sad": '.whale-chan[data-mood="sad"]',
        "think0": '.whale-chan[data-mood="thinking"]',
        "think1": '.whale-chan[data-mood="thinking"][data-strain="1"]',
        "think2": '.whale-chan[data-mood="thinking"][data-strain="2"]',
    }
    pose_vars = {
        "neutral": "--hr:0deg;--hx:0px;--hy:0px;--bl-r:0deg;--bl-y:0px;--br-r:0deg;--br-y:0px;--ix:0px;--iy:0px;--is:1;--ear:0deg;--ahoge:0deg;--tail:0deg;--cy:0px;--cs:1;--blush:.75;",
        "angry": "--hr:0deg;--hx:0px;--hy:6px;--bl-r:20deg;--bl-y:6px;--br-r:20deg;--br-y:6px;--ix:0px;--iy:2px;--is:.86;--ear:-18deg;--ahoge:-10deg;--tail:-6deg;--cy:0px;--cs:1;--blush:1;",
        "smug": "--hr:-7deg;--hx:-4px;--hy:-4px;--bl-r:-6deg;--bl-y:-6px;--br-r:10deg;--br-y:2px;--ix:-7px;--iy:1px;--is:1;--ear:-8deg;--ahoge:12deg;--tail:-14deg;--cy:0px;--cs:1;--blush:.9;",
        "happy": "--hr:4deg;--hx:0px;--hy:-4px;--bl-r:-8deg;--bl-y:-8px;--br-r:-8deg;--br-y:-8px;--ix:0px;--iy:0px;--is:1;--ear:-14deg;--ahoge:-6deg;--tail:-10deg;--cy:0px;--cs:1;--blush:1;",
        "sad": "--hr:6deg;--hx:4px;--hy:10px;--bl-r:-20deg;--bl-y:-2px;--br-r:-20deg;--br-y:-2px;--ix:0px;--iy:5px;--is:1.04;--ear:26deg;--ahoge:48deg;--tail:20deg;--cy:6px;--cs:.98;--blush:.55;",
        "think0": "--hr:-8deg;--hx:-4px;--hy:0px;--bl-r:-12deg;--bl-y:-8px;--br-r:12deg;--br-y:2px;--ix:8px;--iy:-9px;--is:.95;--ear:-6deg;--ahoge:24deg;--tail:6deg;--cy:0px;--cs:1;--blush:.7;",
        "think1": "--hr:0deg;--hx:0px;--hy:4px;--bl-r:16deg;--bl-y:4px;--br-r:16deg;--br-y:4px;--ear:12deg;--ahoge:40deg;--tail:10deg;--blush:.9;",
        "think2": "--hr:0deg;--hx:0px;--hy:2px;--bl-r:-14deg;--bl-y:-6px;--br-r:-14deg;--br-y:-6px;--ear:-20deg;--ahoge:-4deg;--tail:-4deg;--blush:1;",
    }
    rules = "\n".join(f"    {sel[k]} {{ {arm_vars(P[k])}{pose_vars[k]} }}" for k in sel)

    return f"""
  <style><![CDATA[
    .whale-chan {{ overflow: visible; }}
    g {{ transform-box: view-box; }}
{rules}

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

    /* expression layers */
    .mouth, .lid, .eye-alt, .fx, .bowl, .hl-sad, .tear-pool, .think-scribble, .think-dots, .qmark, .bang {{
      opacity: 0; transition: opacity .25s ease;
    }}
    .lash-default, .eye-open {{ transition: opacity .2s ease; }}
    .whale-chan[data-mood="neutral"] .m-neutral, .whale-chan:not([data-mood]) .m-neutral,
    .whale-chan[data-mood="angry"] .m-angry, .whale-chan[data-mood="angry"] .lid-angry, .whale-chan[data-mood="angry"] .fx-angry,
    .whale-chan[data-mood="smug"] .m-smug, .whale-chan[data-mood="smug"] .lid-smug, .whale-chan[data-mood="smug"] .fx-smug,
    .whale-chan[data-mood="happy"] .m-happy, .whale-chan[data-mood="happy"] .eye-happy, .whale-chan[data-mood="happy"] .fx-happy, .whale-chan[data-mood="happy"] .bowl,
    .whale-chan[data-mood="sad"] .m-sad, .whale-chan[data-mood="sad"] .lid-sad, .whale-chan[data-mood="sad"] .fx-sad,
    .whale-chan[data-mood="sad"] .hl-sad, .whale-chan[data-mood="sad"] .tear-pool,
    .whale-chan[data-mood="thinking"] .fx-think,
    .whale-chan[data-mood="thinking"][data-strain="0"] .m-think0, .whale-chan[data-mood="thinking"]:not([data-strain]) .m-think0,
    .whale-chan[data-mood="thinking"][data-strain="0"] .think-dots, .whale-chan[data-mood="thinking"]:not([data-strain]) .think-dots,
    .whale-chan[data-mood="thinking"][data-strain="0"] .qmark, .whale-chan[data-mood="thinking"]:not([data-strain]) .qmark,
    .whale-chan[data-mood="thinking"][data-strain="1"] .m-think1, .whale-chan[data-mood="thinking"][data-strain="1"] .eye-squeeze,
    .whale-chan[data-mood="thinking"][data-strain="1"] .think-dots, .whale-chan[data-mood="thinking"][data-strain="1"] .fx-sweat,
    .whale-chan[data-mood="thinking"][data-strain="2"] .m-think2, .whale-chan[data-mood="thinking"][data-strain="2"] .eye-swirl,
    .whale-chan[data-mood="thinking"][data-strain="2"] .think-scribble, .whale-chan[data-mood="thinking"][data-strain="2"] .fx-sweat,
    .whale-chan[data-mood="thinking"][data-strain="2"] .fx-overheat, .whale-chan[data-mood="thinking"][data-strain="2"] .bang {{
      opacity: 1;
    }}
    .whale-chan[data-mood="angry"] .lash-default, .whale-chan[data-mood="smug"] .lash-default, .whale-chan[data-mood="sad"] .lash-default,
    .whale-chan[data-mood="sad"] .hl,
    .whale-chan[data-mood="happy"] .eye-open,
    .whale-chan[data-mood="thinking"][data-strain="1"] .eye-open, .whale-chan[data-mood="thinking"][data-strain="2"] .eye-open {{
      opacity: 0;
    }}

    /* ---------- idle motion (every mood) ---------- */
    .blink {{ animation: blink 4.6s infinite; }}

    .char-anim   {{ animation: float-bob 4.2s ease-in-out infinite; }}
    .upper-anim  {{ animation: breathe 3.6s ease-in-out infinite; }}
    .head-anim   {{ animation: head-idle 5.2s ease-in-out infinite; }}
    .tail-wag    {{ animation: tail-idle 3.2s ease-in-out infinite; }}
    .fluke       {{ animation: fluke-idle 3.2s ease-in-out -.5s infinite; }}
    .ear-flap-l, .ear-flap-r {{ animation: ear-idle 3s ease-in-out infinite; }}
    .ear-flap-r  {{ animation-delay: -.25s; }}
    .ahoge-anim  {{ animation: ahoge-idle 2.6s ease-in-out infinite; }}
    .arm-l .u-anim {{ animation: arm-idle 3.6s ease-in-out infinite; }}
    .arm-r .u-anim {{ animation: arm-idle 3.6s ease-in-out -1.8s infinite; }}
    .lock-l, .lock-r {{ animation: lock-sway 3.6s ease-in-out infinite; }}
    .lock-r {{ animation-delay: -1.2s; }}

    /* ---------- angry: stomping, fists pumping, tail thrashing ---------- */
    .whale-chan[data-mood="angry"] .char-anim {{ animation: stomp .5s cubic-bezier(.3,.7,.4,1) infinite; }}
    .whale-chan[data-mood="angry"] .head-anim {{ animation: rage-shake .16s linear infinite; }}
    .whale-chan[data-mood="angry"] .arm-l .u-anim {{ animation: pump .5s ease-in-out infinite; }}
    .whale-chan[data-mood="angry"] .arm-r .u-anim {{ animation: pump .5s ease-in-out -.25s infinite; }}
    .whale-chan[data-mood="angry"] .arm .f-anim {{ animation: fist-shake .12s linear infinite; }}
    .whale-chan[data-mood="angry"] .tail-wag {{ animation: tail-thrash .42s ease-in-out infinite; }}
    .whale-chan[data-mood="angry"] .fluke {{ animation: fluke-thrash .42s ease-in-out -.1s infinite; }}
    .whale-chan[data-mood="angry"] .ear-flap-l, .whale-chan[data-mood="angry"] .ear-flap-r {{ animation: ear-buzz .14s linear infinite; }}
    .whale-chan[data-mood="angry"] .ahoge-anim {{ animation: ahoge-buzz .12s linear infinite; }}
    .anger-mark {{ animation: anger-pulse .55s ease-in-out infinite; }}
    .fx-angry .steam {{ animation: steam-puff 1.1s ease-out infinite; }}
    .fx-angry .steam-b {{ animation-delay: -.55s; }}

    /* ---------- smug: hands on hips, swaying, slow proud tail swish ---------- */
    .whale-chan[data-mood="smug"] .char-anim {{ animation: smug-sway 3s ease-in-out infinite; }}
    .whale-chan[data-mood="smug"] .head-anim {{ animation: smug-nod 1.5s ease-in-out infinite; }}
    .whale-chan[data-mood="smug"] .arm .u-anim {{ animation: none; }}
    .whale-chan[data-mood="smug"] .tail-wag {{ animation: tail-swish 2.4s ease-in-out infinite; }}
    .whale-chan[data-mood="smug"] .fluke {{ animation: fluke-idle 2.4s ease-in-out -.4s infinite; }}
    .whale-chan[data-mood="smug"] .ahoge-anim {{ animation: ahoge-idle 1.5s ease-in-out infinite; }}
    .twinkle {{ animation: twinkle 1.8s ease-in-out infinite; }}
    .tw-1 {{ animation-delay: -.5s; }} .tw-2 {{ animation-delay: -1.1s; }} .tw-3 {{ animation-delay: -1.4s; }}

    /* ---------- happy: hopping, cheering, wagging ---------- */
    .whale-chan[data-mood="happy"] .char-anim {{ animation: hop .76s cubic-bezier(.3,.6,.4,1) infinite; }}
    .whale-chan[data-mood="happy"] .upper-anim {{ animation: none; }}
    .whale-chan[data-mood="happy"] .head-anim {{ animation: happy-tilt 1.52s ease-in-out infinite; }}
    .whale-chan[data-mood="happy"] .arm-l .u-anim {{ animation: cheer .38s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="happy"] .arm-r .u-anim {{ animation: cheer .38s ease-in-out -.38s infinite alternate; }}
    .whale-chan[data-mood="happy"] .tail-wag {{ animation: tail-wag .38s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="happy"] .fluke {{ animation: fluke-thrash .38s ease-in-out -.1s infinite; }}
    .whale-chan[data-mood="happy"] .ear-flap-l, .whale-chan[data-mood="happy"] .ear-flap-r {{ animation: ear-flap .38s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="happy"] .ahoge-anim {{ animation: ahoge-boing .76s ease-in-out infinite; }}
    .float-up {{ animation: float-up 2.4s ease-out infinite; }}
    .fu-1 {{ animation-delay: -.4s; }} .fu-2 {{ animation-delay: -.8s; }} .fu-3 {{ animation-delay: -1.2s; }}
    .fu-4 {{ animation-delay: -1.6s; }} .fu-5 {{ animation-delay: -2s; }}
    .bowl-steam path {{ animation: wisp 1.6s ease-in-out infinite; }}
    .bowl-steam path + path {{ animation-delay: -.8s; }}

    /* ---------- sad: slumped, sobbing, rubbing an eye, tail on the floor ---------- */
    .whale-chan[data-mood="sad"] .char-anim {{ animation: none; }}
    .whale-chan[data-mood="sad"] .upper-anim {{ animation: sob 1.1s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .head-anim {{ animation: sob-head 1.1s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .arm-l .u-anim {{ animation: limp 4s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .arm-r .u-anim {{ animation: none; }}
    .whale-chan[data-mood="sad"] .arm-r .f-anim {{ animation: rub-eye .5s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="sad"] .tail-wag {{ animation: tail-idle 6s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .fluke {{ animation: fluke-sad 3s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .ear-flap-l, .whale-chan[data-mood="sad"] .ear-flap-r {{ animation: ear-idle 6s ease-in-out infinite; }}
    .whale-chan[data-mood="sad"] .ahoge-anim {{ animation: ahoge-droop 2.2s ease-in-out infinite; }}
    .quiver {{ animation: quiver .2s linear infinite; }}
    .tear-stream {{ animation: shimmer 1.2s ease-in-out infinite; }}
    .drop {{ animation: drip 1.3s ease-in infinite; }}
    .drop-b {{ animation-delay: -.65s; }}
    .rain-cloud {{ animation: cloud-bob 3s ease-in-out infinite; }}
    .rd {{ stroke: #7fb6ea; stroke-width: 3.5; stroke-linecap: round; animation: rain .9s linear infinite; }}
    .rd-1 {{ animation-delay: -.3s; }} .rd-2 {{ animation-delay: -.6s; }}
    .gloom {{ animation: gloom 2.4s ease-in-out infinite; }}

    /* ---------- thinking: chin tap → temple press → overheated meltdown ---------- */
    .whale-chan[data-mood="thinking"] .char-anim {{ animation: think-sway 3.4s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"] .head-anim {{ animation: head-idle 3.4s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"] .arm-l .u-anim {{ animation: none; }}
    .whale-chan[data-mood="thinking"] .arm-r .u-anim {{ animation: none; }}
    .whale-chan[data-mood="thinking"] .arm-r .f-anim {{ animation: chin-tap .9s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"] .tail-wag {{ animation: tail-tap 1.8s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"] .ahoge-anim {{ animation: ahoge-ponder 2.2s ease-in-out infinite; }}
    .dot {{ animation: dot 1.2s ease-in-out infinite; }}
    .dot-1 {{ animation-delay: .2s; }} .dot-2 {{ animation-delay: .4s; }}
    .qmark {{ animation: q-bob 1.8s ease-in-out infinite; }}

    .whale-chan[data-mood="thinking"][data-strain="1"] .char-anim {{ animation: think-sway 1.6s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="1"] .head-anim {{ animation: strain-shake .3s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="1"] .arm .f-anim {{ animation: temple-rub .3s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="thinking"][data-strain="1"] .dot {{ animation-duration: .6s; }}
    .whale-chan[data-mood="thinking"][data-strain="1"] .ahoge-anim {{ animation: ahoge-buzz .3s linear infinite; }}
    .sweat {{ animation: sweat 1.4s ease-in infinite; }}

    .whale-chan[data-mood="thinking"][data-strain="2"] .char-anim {{ animation: overheat .14s linear infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .head-anim {{ animation: dizzy .9s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .arm-l .u-anim {{ animation: flail .26s ease-in-out infinite alternate; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .arm-r .u-anim {{ animation: flail .26s ease-in-out -.13s infinite alternate; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .arm .f-anim {{ animation: none; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .tail-wag {{ animation: tail-thrash .3s ease-in-out infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .ahoge-anim {{ animation: ahoge-spin .6s linear infinite; }}
    .whale-chan[data-mood="thinking"][data-strain="2"] .ear-flap-l, .whale-chan[data-mood="thinking"][data-strain="2"] .ear-flap-r {{ animation: ear-buzz .14s linear infinite; }}
    .swirl {{ animation: spin 1s linear infinite; }}
    .fx-overheat .steam {{ animation: steam-puff 1s ease-out infinite; }}
    .fx-overheat .steam-b {{ animation-delay: -.5s; }}
    .think-scribble {{ animation: scribble .5s steps(3) infinite; }}
    .bang {{ animation: q-bob .5s ease-in-out infinite; }}

    /* ---------- keyframes ---------- */
    @keyframes blink {{ 0%, 93%, 100% {{ transform: scaleY(1); }} 95.5% {{ transform: scaleY(.08); }} }}
    @keyframes float-bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-9px); }} }}
    @keyframes breathe {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-2.5px); }} }}
    @keyframes head-idle {{ 0%, 100% {{ transform: rotate(-2deg); }} 50% {{ transform: rotate(2.5deg); }} }}
    @keyframes tail-idle {{ 0%, 100% {{ transform: rotate(-4deg); }} 50% {{ transform: rotate(5deg); }} }}
    @keyframes fluke-idle {{ 0%, 100% {{ transform: rotate(-6deg); }} 50% {{ transform: rotate(8deg); }} }}
    @keyframes ear-idle {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(-6deg); }} }}
    @keyframes ahoge-idle {{ 0%, 100% {{ transform: rotate(-7deg); }} 50% {{ transform: rotate(8deg); }} }}
    @keyframes arm-idle {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(2.5deg); }} }}
    @keyframes lock-sway {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(-1.5deg); }} }}

    @keyframes stomp {{
      0%, 100% {{ transform: translateY(0) scale(1, 1); }}
      30% {{ transform: translateY(-12px) scale(.99, 1.02); }}
      55% {{ transform: translateY(0) scale(1.03, .96); }}
      70% {{ transform: translateY(0) scale(1, 1); }}
    }}
    @keyframes rage-shake {{ 0%, 100% {{ transform: rotate(-1.6deg) translateX(-1px); }} 50% {{ transform: rotate(1.6deg) translateX(1px); }} }}
    @keyframes pump {{ 0%, 100% {{ transform: rotate(-14deg); }} 50% {{ transform: rotate(10deg); }} }}
    @keyframes fist-shake {{ 0%, 100% {{ transform: rotate(-3deg); }} 50% {{ transform: rotate(3deg); }} }}
    @keyframes tail-thrash {{ 0%, 100% {{ transform: rotate(-12deg); }} 50% {{ transform: rotate(12deg); }} }}
    @keyframes fluke-thrash {{ 0%, 100% {{ transform: rotate(-16deg); }} 50% {{ transform: rotate(16deg); }} }}
    @keyframes ear-buzz {{ 0%, 100% {{ transform: rotate(-4deg); }} 50% {{ transform: rotate(4deg); }} }}
    @keyframes ahoge-buzz {{ 0%, 100% {{ transform: rotate(-5deg); }} 50% {{ transform: rotate(5deg); }} }}
    @keyframes anger-pulse {{ 0%, 100% {{ transform: scale(.85); }} 50% {{ transform: scale(1.15); }} }}
    @keyframes steam-puff {{
      0% {{ transform: translate(0, 10px) scale(.4); opacity: 0; }}
      25% {{ opacity: 1; }}
      100% {{ transform: translate(0, -46px) scale(1.25); opacity: 0; }}
    }}

    @keyframes smug-sway {{ 0%, 100% {{ transform: rotate(-1.6deg); }} 50% {{ transform: rotate(1.6deg); }} }}
    @keyframes smug-nod {{ 0%, 100% {{ transform: rotate(0) translateY(0); }} 50% {{ transform: rotate(-3deg) translateY(-3px); }} }}
    @keyframes tail-swish {{ 0%, 100% {{ transform: rotate(-8deg); }} 50% {{ transform: rotate(8deg); }} }}
    @keyframes twinkle {{ 0%, 100% {{ transform: scale(.2) rotate(0); opacity: 0; }} 50% {{ transform: scale(1) rotate(45deg); opacity: 1; }} }}

    @keyframes hop {{
      0%, 100% {{ transform: translateY(0) scale(1.04, .95); }}
      18% {{ transform: translateY(-14px) scale(.97, 1.04); }}
      45% {{ transform: translateY(-40px) scale(1, 1); }}
      78% {{ transform: translateY(0) scale(1.03, .96); }}
    }}
    @keyframes happy-tilt {{ 0%, 100% {{ transform: rotate(-5deg); }} 50% {{ transform: rotate(5deg); }} }}
    @keyframes cheer {{ from {{ transform: rotate(-10deg); }} to {{ transform: rotate(12deg); }} }}
    @keyframes tail-wag {{ from {{ transform: rotate(-14deg); }} to {{ transform: rotate(10deg); }} }}
    @keyframes ear-flap {{ from {{ transform: rotate(-12deg); }} to {{ transform: rotate(10deg); }} }}
    @keyframes ahoge-boing {{ 0%, 100% {{ transform: rotate(0) scaleY(1); }} 40% {{ transform: rotate(-14deg) scaleY(1.1); }} 70% {{ transform: rotate(10deg) scaleY(.92); }} }}
    @keyframes float-up {{
      0% {{ transform: translateY(20px) scale(.3) rotate(-10deg); opacity: 0; }}
      20% {{ opacity: 1; }}
      100% {{ transform: translateY(-70px) scale(1.1) rotate(14deg); opacity: 0; }}
    }}
    @keyframes wisp {{ 0%, 100% {{ transform: translateY(4px); opacity: .2; }} 50% {{ transform: translateY(-6px); opacity: .95; }} }}

    @keyframes sob {{ 0%, 100% {{ transform: translateY(0); }} 20% {{ transform: translateY(3px); }} 35% {{ transform: translateY(0); }} 50% {{ transform: translateY(3px); }} }}
    @keyframes sob-head {{ 0%, 100% {{ transform: rotate(0); }} 20% {{ transform: rotate(1.5deg) translateY(2px); }} 50% {{ transform: rotate(-1deg) translateY(2px); }} }}
    @keyframes limp {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(-4deg); }} }}
    @keyframes rub-eye {{ from {{ transform: rotate(-9deg); }} to {{ transform: rotate(7deg); }} }}
    @keyframes fluke-sad {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(-5deg); }} }}
    @keyframes ahoge-droop {{ 0%, 100% {{ transform: rotate(0); }} 50% {{ transform: rotate(6deg); }} }}
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

    @keyframes think-sway {{ 0%, 100% {{ transform: rotate(-1deg); }} 50% {{ transform: rotate(1deg); }} }}
    @keyframes chin-tap {{ 0%, 60%, 100% {{ transform: rotate(0); }} 75% {{ transform: rotate(-7deg); }} }}
    @keyframes tail-tap {{ 0%, 60%, 100% {{ transform: rotate(0); }} 75% {{ transform: rotate(-10deg); }} }}
    @keyframes ahoge-ponder {{ 0%, 100% {{ transform: rotate(-8deg); }} 50% {{ transform: rotate(8deg); }} }}
    @keyframes dot {{ 0%, 100% {{ transform: translateY(0); opacity: .35; }} 40% {{ transform: translateY(-6px); opacity: 1; }} }}
    @keyframes q-bob {{ 0%, 100% {{ transform: translateY(0) rotate(-8deg); }} 50% {{ transform: translateY(-8px) rotate(8deg); }} }}
    @keyframes strain-shake {{ 0%, 100% {{ transform: rotate(-1deg); }} 50% {{ transform: rotate(1deg); }} }}
    @keyframes temple-rub {{ from {{ transform: rotate(-6deg); }} to {{ transform: rotate(6deg); }} }}
    @keyframes sweat {{ 0% {{ transform: translateY(-6px); opacity: 0; }} 25% {{ opacity: 1; }} 100% {{ transform: translateY(26px); opacity: 0; }} }}
    @keyframes overheat {{ 0%, 100% {{ transform: translateX(-1.5px); }} 50% {{ transform: translateX(1.5px); }} }}
    @keyframes dizzy {{ 0%, 100% {{ transform: rotate(-6deg); }} 50% {{ transform: rotate(6deg); }} }}
    @keyframes flail {{ from {{ transform: rotate(-16deg); }} to {{ transform: rotate(14deg); }} }}
    @keyframes ahoge-spin {{ from {{ transform: rotate(0); }} to {{ transform: rotate(360deg); }} }}
    @keyframes spin {{ from {{ transform: rotate(0); }} to {{ transform: rotate(360deg); }} }}
    @keyframes scribble {{ 0% {{ transform: rotate(0); }} 33% {{ transform: rotate(8deg) scale(1.05); }} 66% {{ transform: rotate(-6deg) scale(.95); }} }}

    /* ---------- pause while dragging, honour reduced motion ---------- */
    .is-paused * {{ animation-play-state: paused !important; }}
    .reduce-motion *, .reduce-motion *::before {{ animation: none !important; transition-duration: .01ms !important; }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; transition-duration: .01ms !important; }}
    }}
  ]]></style>"""




if __name__ == "__main__":
    OUT.write_text(build())
    print(f"wrote {OUT}")
    for name, pose in P.items():
        print(f"  {name:8s} left arm {pose['l']}  right arm {pose['r']}")
