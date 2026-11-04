#!/usr/bin/env python3
"""Builds assets/whale-chan.svg — a hand-rigged vector Whale-chan.

    python3 tools/build_whale_chan.py [output.svg]

The SVG is the shipped artifact; this script is only needed to change the art or poses.
Arm poses are solved with two-bone IK from hand targets (see the P table).

Every body part lives in its own pivot group so CSS can pose and animate it:
  .char > .char-pose > .char-anim             whole body (hops, stomps, sways)
  .upper                                       breathing torso / head / arms
  .head-pose > .head-anim                      head tilt (back hair + face share it)
  .arm-l/.arm-r  > .u-pose > .u-anim           shoulder joint
                 > .f-pose > .f-anim           elbow joint
  .tail-pose > .tail-anim > .fluke-anim        tail + fluke flick
  .ear-l/.ear-r, .ahoge, .brow-l/.brow-r, .iris, eyelids, mouths
"""
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets" / "whale-chan.svg"
CX = 430
SHOULDER_L = (376, 524)
SHOULDER_R = (484, 524)
L_UPPER, L_FORE = 70, 76

INK = "#101b47"
SKIN = "#fff3ec"
SKIN_LINE = "#9c6470"
NAVY = "#1d2d68"
NAVY_DK = "#131e4b"
GOLD = "#d9b45c"
WHITE_LINE = "#93a6c9"


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


# ---------------------------------------------------------------- poses
P = {}
P["neutral"] = dict(l=ik(SHOULDER_L, (340, 664)), r=ik(SHOULDER_R, (520, 664), right=True))
P["angry"] = dict(l=(46, 126), r=(46, 126), fist="both")
P["smug"] = dict(l=ik(SHOULDER_L, (384, 624)), r=ik(SHOULDER_R, (476, 624), right=True), fist="both")
P["happy"] = dict(l=ik(SHOULDER_L, (300, 414)), r=ik(SHOULDER_R, (564, 404), right=True), fist="l")
P["sad"] = dict(l=(-4, 6), r=ik(SHOULDER_R, (488, 424), right=True), fist="r")
_think_r = ik(SHOULDER_R, (452, 484), right=True, elbow_out=False)


def _elbow(shoulder, angle, right=False):
    sx, sy = shoulder
    a = math.radians(angle)
    ex = sx - L_UPPER * math.sin(a) if not right else sx + L_UPPER * math.sin(a)
    return ex, sy + L_UPPER * math.cos(a)


_re = _elbow(SHOULDER_R, _think_r[0], right=True)
P["think0"] = dict(l=ik(SHOULDER_L, (_re[0] - 8, _re[1] + 6)), r=_think_r, fist="l")
P["think1"] = dict(l=ik(SHOULDER_L, (322, 402)), r=ik(SHOULDER_R, (538, 402), right=True))
P["think2"] = dict(l=ik(SHOULDER_L, (306, 392)), r=ik(SHOULDER_R, (554, 392), right=True))


# ---------------------------------------------------------------- defs
DEFS = f"""
  <defs>
    <linearGradient id="g-hair-back" gradientUnits="userSpaceOnUse" x1="0" y1="170" x2="0" y2="740">
      <stop offset="0" stop-color="#1a2b6b"/><stop offset=".42" stop-color="#21408f"/>
      <stop offset=".7" stop-color="#2a66c2"/><stop offset=".88" stop-color="#46a6e6"/>
      <stop offset="1" stop-color="#77d0f6"/>
    </linearGradient>
    <linearGradient id="g-hair-front" gradientUnits="userSpaceOnUse" x1="0" y1="170" x2="0" y2="590">
      <stop offset="0" stop-color="#1c2e70"/><stop offset=".45" stop-color="#2346a0"/>
      <stop offset=".75" stop-color="#2d6cc6"/><stop offset="1" stop-color="#5bbcef"/>
    </linearGradient>
    <linearGradient id="g-hair-shine" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#8fd6ff" stop-opacity="0"/><stop offset=".5" stop-color="#9fe0ff" stop-opacity=".75"/>
      <stop offset="1" stop-color="#8fd6ff" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="g-face" cx="430" cy="410" r="130" gradientUnits="userSpaceOnUse">
      <stop offset=".6" stop-color="{SKIN}"/><stop offset="1" stop-color="#fbe2d8"/>
    </radialGradient>
    <linearGradient id="g-iris" x1="0" y1="-28" x2="0" y2="36" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#0d2463"/><stop offset=".4" stop-color="#1b4fb4"/>
      <stop offset=".72" stop-color="#2d8fe8"/><stop offset="1" stop-color="#86e2ff"/>
    </linearGradient>
    <linearGradient id="g-dress" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#24367a"/><stop offset="1" stop-color="#16225a"/>
    </linearGradient>
    <linearGradient id="g-skirt" gradientUnits="userSpaceOnUse" x1="0" y1="636" x2="0" y2="850">
      <stop offset="0" stop-color="#1a2862"/><stop offset=".6" stop-color="#22357a"/><stop offset="1" stop-color="#2b4290"/>
    </linearGradient>
    <linearGradient id="g-white" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e9f0fb"/>
    </linearGradient>
    <linearGradient id="g-tail" gradientUnits="userSpaceOnUse" x1="500" y1="880" x2="820" y2="640">
      <stop offset="0" stop-color="#17255c"/><stop offset=".6" stop-color="#22397e"/><stop offset="1" stop-color="#2f4f9d"/>
    </linearGradient>
    <linearGradient id="g-sleeve" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#18265e"/><stop offset=".55" stop-color="#26397f"/><stop offset="1" stop-color="#1a2963"/>
    </linearGradient>
    <linearGradient id="g-tear" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#d9f6ff" stop-opacity=".95"/><stop offset="1" stop-color="#7fd3ff" stop-opacity=".55"/>
    </linearGradient>
    <radialGradient id="g-blush">
      <stop offset="0" stop-color="#ff8ea0" stop-opacity=".75"/><stop offset="1" stop-color="#ff8ea0" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="clip-eye" clipPathUnits="userSpaceOnUse">
      <path d="M-31,-21 C-27,-37 25,-39 32,-23 C37,-3 29,34 1,36 C-24,35 -36,4 -31,-21Z"/>
    </clipPath>
  </defs>"""


# ---------------------------------------------------------------- tail
def tail():
    top = "M500,782 C560,800 616,842 676,834 C726,826 756,790 770,744"
    bottom = "M798,758 C786,812 736,884 656,890 C594,894 540,866 500,842"
    stem = ("M500,782 C560,800 616,842 676,834 C726,826 756,790 770,744 L798,758 "
            "C786,812 736,884 656,890 C594,894 540,866 500,842Z")
    belly = ("M512,846 C570,874 632,884 684,872 C734,858 770,818 790,764 "
             "C780,824 730,870 660,874 C602,878 556,862 512,834Z")
    fluke = ("M762,756 C766,718 752,682 734,646 C764,660 786,686 794,708 "
             "C812,690 842,680 874,684 C850,706 822,738 802,764 C792,774 768,770 762,756Z")
    fluke_shade = "M772,744 C774,716 766,690 750,666 C772,682 786,700 790,716Z"
    fluke_tip = "M800,740 C820,716 842,700 862,692"
    shine = "M590,826 C630,846 676,846 712,828"
    fluke_art = (f'<path d="{fluke}" fill="url(#g-tail)" stroke="{INK}" stroke-width="3.2" stroke-linejoin="round"/>'
                 f'<path d="{fluke_shade}" fill="#3a5fb0" opacity=".6"/>'
                 f'<path d="{fluke_tip}" fill="none" stroke="#5f8fe0" stroke-width="3" stroke-linecap="round" opacity=".6"/>')
    stem_art = (f'<path d="{stem}" fill="url(#g-tail)"/>'
                f'<path d="{belly}" fill="#c9d7f0" opacity=".95"/>'
                f'<path d="{shine}" fill="none" stroke="#6fa8ec" stroke-width="5" stroke-linecap="round" opacity=".55"/>'
                f'<path d="{top}" fill="none" stroke="{INK}" stroke-width="3.2" stroke-linecap="round"/>'
                f'<path d="{bottom}" fill="none" stroke="{INK}" stroke-width="3.2" stroke-linecap="round"/>')
    inner = pivot("fluke", 782, 752, fluke_art) + stem_art
    return pivot("tail-pose|tail-wag", 520, 806, inner)


# ---------------------------------------------------------------- hair (back)
def hair_back():
    # left half as cubic segments from the crown down and back in; the right half is mirrored
    half = [
        ((352, 176), (278, 232), (268, 330)), ((262, 380), (250, 410), (246, 450)),
        ((242, 490), (258, 512), (246, 552)), ((234, 590), (214, 612), (220, 652)),
        ((224, 690), (204, 702), (216, 726)), ((230, 746), (262, 740), (270, 716)),
        ((280, 738), (312, 746), (326, 720)), ((338, 740), (362, 730), (364, 708)),
        ((366, 690), (360, 668), (378, 648)),
    ]
    d = "M430,176 " + " ".join(f"C{a[0]},{a[1]} {b[0]},{b[1]} {c[0]},{c[1]}" for a, b, c in half)
    d += f" L430,640 L{mirror_x(378)},648"
    starts = [(430, 176)] + [c for _, _, c in half[:-1]]
    for (a, b, _), p0 in reversed(list(zip(half, starts))):
        d += f" C{mirror_x(b[0])},{b[1]} {mirror_x(a[0])},{a[1]} {mirror_x(p0[0])},{p0[1]}"
    d += "Z"
    strands = ""
    for path in [
        "M262,420 C250,480 252,540 238,600 C232,630 236,660 252,690",
        "M296,470 C286,540 300,600 284,660 C280,684 292,704 308,716",
        "M246,520 C236,560 228,600 230,640",
    ]:
        strands += f'<path d="{path}" fill="none" stroke="#14286a" stroke-width="2.4" stroke-linecap="round" opacity=".55"/>'
        strands += f'<g transform="translate({2 * CX},0) scale(-1,1)"><path d="{path}" fill="none" stroke="#14286a" stroke-width="2.4" stroke-linecap="round" opacity=".55"/></g>'
    curls = ""
    for path in ["M226,654 C214,676 222,700 244,704", "M300,700 C296,716 304,728 318,728"]:
        curls += f'<path d="{path}" fill="none" stroke="#a8e6ff" stroke-width="3" stroke-linecap="round" opacity=".55"/>'
        curls += f'<g transform="translate({2 * CX},0) scale(-1,1)"><path d="{path}" fill="none" stroke="#a8e6ff" stroke-width="3" stroke-linecap="round" opacity=".55"/></g>'
    return (f'<clipPath id="clip-hair-back"><path d="{d}"/></clipPath>'
            f'<path d="{d}" fill="url(#g-hair-back)" stroke="{INK}" stroke-width="3.2" stroke-linejoin="round"/>'
            f'<g clip-path="url(#clip-hair-back)">{strands}{curls}</g>')


# ---------------------------------------------------------------- legs
def legs():
    out = ""
    for x0 in (399, 433):
        out += (f'<path d="M{x0},812 L{x0 + 28},812 L{x0 + 27},952 L{x0 + 1},952Z" fill="#fbfcff" stroke="{WHITE_LINE}" stroke-width="2.4"/>'
                f'<path d="M{x0 + 20},830 L{x0 + 19},946" stroke="#dfe7f5" stroke-width="5" stroke-linecap="round"/>')
    shoes = ""
    for cx in (412, 448):
        shoes += (f'<path d="M{cx - 21},952 C{cx - 23},934 {cx + 21},930 {cx + 23},950 '
                  f'C{cx + 28},974 {cx + 18},990 {cx},990 C{cx - 18},990 {cx - 28},974 {cx - 21},952Z" '
                  f'fill="{NAVY}" stroke="{INK}" stroke-width="3"/>'
                  f'<path d="M{cx - 15},948 C{cx - 6},944 {cx + 8},944 {cx + 16},948" fill="none" stroke="{NAVY_DK}" stroke-width="5" stroke-linecap="round"/>'
                  f'<circle cx="{cx + 9}" cy="947" r="3.4" fill="{GOLD}" stroke="#8b6a22" stroke-width="1"/>'
                  f'<path d="M{cx - 10},966 C{cx - 8},976 {cx - 2},980 {cx + 4},980" fill="none" stroke="#4d68b4" stroke-width="3" stroke-linecap="round" opacity=".7"/>')
    return f'<g class="legs">{out}{shoes}</g>'


# ---------------------------------------------------------------- torso
def torso():
    neck = (f'<path d="M414,468 L446,468 L447,512 L413,512Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2"/>'
            f'<path d="M414,476 C424,488 436,488 446,476 L446,494 C436,500 424,500 414,494Z" fill="#f2cfc4" opacity=".8"/>')

    # petticoat frill under the hem
    hem = sample_cubics([((266, 832), (330, 858), (530, 858), (594, 832))])
    hem_pts = resample(hem, 16)
    low = [(x, y + 24) for x, y in hem_pts]
    petti = (f'<path d="M{fmt(hem_pts[0][0])},{fmt(hem_pts[0][1] - 6)} {polyline(hem_pts)} '
             f'{scallops(list(reversed(low)), -6, start=False)}Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.4" stroke-linejoin="round"/>')

    skirt_d = "M378,634 C402,644 458,644 482,634 C520,688 568,770 594,832 C540,862 320,862 266,832 C292,770 340,688 378,634Z"
    skirt = f'<path d="{skirt_d}" fill="url(#g-skirt)" stroke="{INK}" stroke-width="3.2" stroke-linejoin="round"/>'
    folds = ""
    for a, b in [((396, 650), (346, 840)), ((418, 652), (396, 850)), ((442, 652), (464, 850)), ((464, 650), (514, 840))]:
        folds += f'<path d="M{a[0]},{a[1]} Q{(a[0] + b[0]) / 2 + (6 if b[0] > CX else -6)},{(a[1] + b[1]) / 2} {b[0]},{b[1]}" fill="none" stroke="{NAVY_DK}" stroke-width="2.4" opacity=".7"/>'
    embroidery = (f'<path d="M282,812 C350,836 510,836 578,812" fill="none" stroke="{GOLD}" stroke-width="2.4"/>'
                  f'<path d="M286,822 C352,846 508,846 574,822" fill="none" stroke="{GOLD}" stroke-width="1.2" opacity=".8"/>')
    for x, y in [(318, 822), (374, 836), (486, 836), (542, 822)]:
        embroidery += f'<path d="{star4(x, y, 6, .3)}" fill="{GOLD}"/>'
    bows = ""
    for bx, by, s in [(322, 774, 1), (538, 774, -1)]:
        bows += (f'<g transform="translate({bx},{by}) scale({s},1) rotate(-8)">'
                 f'<path d="M0,0 C-10,-14 -24,-10 -22,2 C-20,12 -8,8 0,0Z M0,0 C10,-14 24,-10 22,2 C20,12 8,8 0,0Z" fill="{NAVY}" stroke="{GOLD}" stroke-width="2"/>'
                 f'<path d="M-2,2 L-8,22 M2,2 L8,22" stroke="{GOLD}" stroke-width="2.4" stroke-linecap="round"/>'
                 f'<circle r="4" fill="{GOLD}"/></g>')

    bodice_d = "M372,514 C392,504 468,504 488,514 C494,560 488,606 484,640 L376,640 C372,606 366,560 372,514Z"
    bodice = f'<path d="{bodice_d}" fill="url(#g-dress)" stroke="{INK}" stroke-width="3.2" stroke-linejoin="round"/>'
    # white shirt front with ruffles
    rl = resample([(404, 512), (409, 600)], 7)
    rr = resample([(451, 600), (456, 512)], 7)
    shirt = (f'<path d="{scallops(rl, 3)} {scallops(rr, 3, start=False)}Z" '
             f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2"/>')
    buttons = "".join(f'<circle cx="430" cy="{y}" r="3" fill="{NAVY}"/>' for y in (556, 572, 588))
    corset = (f'<path d="M378,598 C402,606 458,606 482,598 L485,642 C460,650 400,650 375,642Z" fill="{NAVY_DK}" stroke="{INK}" stroke-width="3"/>'
              f'<path d="M380,606 C404,613 456,613 480,606" fill="none" stroke="#3a55a6" stroke-width="1.6" opacity=".7"/>')
    for x, y in [(404, 618), (404, 634), (456, 618), (456, 634)]:
        corset += f'<circle cx="{x}" cy="{y}" r="3.6" fill="{GOLD}" stroke="#8b6a22" stroke-width="1"/>'

    # apron with frilled edge
    apron_core = [((392, 644), (380, 700), (364, 760), (364, 792)),
                  ((364, 792), (390, 820), (470, 820), (496, 792)),
                  ((496, 792), (496, 760), (480, 700), (468, 644))]
    edge = resample(sample_cubics(apron_core), 22)
    apron = (f'<path d="{scallops(edge, 4)} Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.4" stroke-linejoin="round"/>'
             f'<path d="M382,700 C380,740 378,770 384,790 M478,700 C480,740 482,770 476,790" fill="none" stroke="#dbe5f4" stroke-width="3"/>')
    whale_logo = ('<g transform="translate(452,770)">'
                  '<path d="M-16,4 C-16,-8 -4,-12 6,-10 C12,-9 15,-6 16,-3 L22,-8 C24,-9 25,-7 24,-6 L19,0 C18,8 8,12 -2,12 C-10,12 -16,9 -16,4Z" fill="#2a5fc0" stroke="#163780" stroke-width="1.4"/>'
                  '<path d="M-14,6 C-6,10 6,10 14,4" fill="none" stroke="#e6f2ff" stroke-width="2.2" stroke-linecap="round"/>'
                  '<circle cx="-6" cy="-2" r="1.6" fill="#fff"/>'
                  '<path d="M-2,-12 C-4,-18 -8,-20 -10,-20 M-2,-12 C0,-18 4,-20 6,-20" fill="none" stroke="#5ab8f0" stroke-width="2" stroke-linecap="round"/>'
                  '</g>')

    collar_l = resample(sample_cubics([((430, 516), (414, 534), (392, 534), (382, 518))]), 6)
    collar_r = resample(sample_cubics([((478, 518), (468, 534), (446, 534), (430, 516))]), 6)
    collar = (f'<path d="M430,508 C412,500 392,502 382,518 {scallops(list(reversed(collar_l)), 2.5, start=False)}Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.2"/>'
              f'<path d="M430,508 C448,500 468,502 478,518 {scallops(collar_r, -2.5, start=False)}Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.2"/>')
    bowtie = (f'<g transform="translate(430,522)">'
              f'<path d="M0,0 C-8,-12 -26,-14 -26,-2 C-26,10 -10,10 0,0Z M0,0 C8,-12 26,-14 26,-2 C26,10 10,10 0,0Z" fill="{NAVY}" stroke="{INK}" stroke-width="2"/>'
              f'<path d="M-3,4 L-12,26 L-4,22 Z M3,4 L12,26 L4,22Z" fill="{NAVY}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
              f'<circle r="6.5" fill="#53c8ff" stroke="{GOLD}" stroke-width="2.4"/><circle cx="-2" cy="-2" r="2" fill="#e6fbff"/></g>')
    return (f'<g class="torso">{neck}{petti}{skirt}{folds}{embroidery}{bows}{bodice}{shirt}{buttons}'
            f'{corset}{apron}{whale_logo}{collar}{bowtie}</g>')


# ---------------------------------------------------------------- head pieces
def fin_ear(mirror):
    x = 560
    art = (f'<path d="M{x},360 c30,-28 84,-34 130,-8 c-24,6 -40,14 -56,26 c-22,12 -48,12 -68,4Z" fill="{NAVY}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
           f'<path d="M{x + 8},380 c26,2 54,-4 76,-12 c20,-8 36,-14 46,-16 c-12,18 -34,36 -62,44 c-24,6 -46,2 -60,-16Z" fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.4" stroke-linejoin="round"/>'
           f'<path d="M{x + 30},388 c16,-4 32,-10 46,-18 M{x + 36},398 c14,-4 26,-10 38,-18" fill="none" stroke="#c4d2ea" stroke-width="2" stroke-linecap="round"/>'
           f'<path d="M{x + 18},350 c24,-16 56,-20 86,-10" fill="none" stroke="#3b5aaa" stroke-width="3" stroke-linecap="round" opacity=".7"/>')
    if mirror:
        return pivot("ear ear-l|ear-flap-l", mirror_x(x), 366, art, mirror=True, src=(x, 366))
    return pivot("ear ear-r|ear-flap-r", x, 366, art)


def eye(cx, cy, s):
    """s=1 → viewer-right eye (outer corner +x); s=-1 mirrored. Highlights keep the same light side."""
    hl = (f'<ellipse cx="{-9 * s}" cy="-9" rx="9" ry="11.5" fill="#fff"/>'
          f'<circle cx="{12 * s}" cy="17" r="4.6" fill="#fff"/>'
          f'<circle cx="{13 * s}" cy="-13" r="2.4" fill="#fff" opacity=".9"/>')
    sclera = "M-31,-21 C-27,-37 25,-39 32,-23 C37,-3 29,34 1,36 C-24,35 -36,4 -31,-21Z"
    iris = (f'<g class="iris"><g class="iris-pose">'
            f'<ellipse cx="1" cy="5" rx="25" ry="31" fill="url(#g-iris)"/>'
            f'<path d="M-24,-6 C-20,-28 22,-28 26,-6 C16,-15 -14,-15 -24,-6Z" fill="#081a4d" opacity=".55"/>'
            f'<ellipse cx="1" cy="7" rx="11" ry="15" fill="#091340"/>'
            f'<path d="M-18,21 C-8,32 12,32 20,21 C10,26 -8,26 -18,21Z" fill="#a6f2ff"/>'
            f'<path d="M-14,10 L-20,18 M16,10 L22,18" stroke="#6fd0ff" stroke-width="2" stroke-linecap="round" opacity=".7"/>'
            f'<ellipse cx="1" cy="5" rx="25" ry="31" fill="none" stroke="#0b1d55" stroke-width="2"/>'
            f'<g class="hl">{hl}</g>'
            f'<g class="hl-sad"><ellipse cx="{8 * s}" cy="-2" rx="6" ry="7" fill="#fff"/><ellipse cx="{-12 * s}" cy="14" rx="5" ry="3.5" fill="#fff" opacity=".9"/></g>'
            f'</g></g>')
    tear_pool = '<path class="tear-pool" d="M-26,18 C-12,34 14,34 28,16 C18,30 -10,32 -26,18Z" fill="#c8f2ff"/>'
    lash = (f'<g class="lash-default">'
            f'<path d="M-37,-13 C-31,-38 22,-45 38,-24 L47,-30 C45,-22 42,-18 38,-13 C31,-30 -22,-32 -33,-9Z" fill="{INK}"/>'
            f'<path d="M-22,-41 Q6,-51 32,-39" fill="none" stroke="{SKIN_LINE}" stroke-width="1.8" opacity=".55"/></g>')
    lower = f'<path d="M-15,37 Q2,41 19,35" fill="none" stroke="{SKIN_LINE}" stroke-width="2" stroke-linecap="round" opacity=".55"/>'
    lids = (
        f'<g class="lid lid-angry"><path d="M-46,-64 L52,-64 L52,-27 L-46,-1Z" fill="{SKIN}"/>'
        f'<path d="M-38,-2 L42,-25" stroke="{INK}" stroke-width="7" stroke-linecap="round"/></g>'
        f'<g class="lid lid-smug"><path d="M-46,-64 L52,-64 L52,-6 Q6,2 -46,-2Z" fill="{SKIN}"/>'
        f'<path d="M-36,-3 Q4,3 38,-7 L48,-12" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></g>'
        f'<g class="lid lid-sad"><path d="M-46,-64 L52,-64 L52,-10 L-46,-28Z" fill="{SKIN}"/>'
        f'<path d="M-35,-26 Q6,-24 40,-10" fill="none" stroke="{INK}" stroke-width="6.5" stroke-linecap="round"/></g>'
    )
    open_eye = (f'<g class="eye-open"><g class="blink">'
                f'<path d="{sclera}" fill="#fff"/>'
                f'<g clip-path="url(#clip-eye)">{iris}{tear_pool}</g>'
                f'{lash}{lower}{lids}</g></g>')
    happy = (f'<g class="eye-alt eye-happy"><path d="M-30,10 Q0,-26 31,8" fill="none" stroke="{INK}" stroke-width="7.5" stroke-linecap="round"/>'
             f'<path d="M31,8 L42,2" stroke="{INK}" stroke-width="5" stroke-linecap="round"/></g>')
    squeeze = (f'<g class="eye-alt eye-squeeze"><path d="M24,-18 L-18,2 L24,22" fill="none" stroke="{INK}" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round"/></g>')
    swirl = (f'<g class="eye-alt eye-swirl"><circle r="30" fill="#fff" stroke="{INK}" stroke-width="3"/>'
             f'<g class="swirl"><path d="{spiral()}" fill="none" stroke="#1c4fb0" stroke-width="4.5" stroke-linecap="round"/></g></g>')
    return (f'<g transform="translate({cx},{cy}) scale({s},1)">'
            f'{open_eye}{happy}{squeeze}{swirl}</g>')


def brows():
    br = (f'<path d="M-19,3 Q-2,-6 19,-1" fill="none" stroke="{SKIN}" stroke-width="9" stroke-linecap="round" opacity=".55"/>'
          f'<path d="M-19,3 Q-2,-6 19,-1" fill="none" stroke="#1b1a3f" stroke-width="4.2" stroke-linecap="round"/>')
    return (pivot("brow brow-l", 378, 350, f'<g transform="translate(378,350)">{br}</g>', mirror=True)
            + pivot("brow brow-r", 482, 350, f'<g transform="translate(482,350)">{br}</g>'))


def mouths():
    m = ""
    m += f'<g class="mouth m-neutral"><path d="M418,452 Q430,461 442,452" fill="none" stroke="#7a3446" stroke-width="3" stroke-linecap="round"/></g>'
    m += (f'<g class="mouth m-angry"><path d="M413,462 Q430,444 447,462 Q445,472 430,471 Q415,472 413,462Z" fill="#9c2c3e" stroke="#6e1f2e" stroke-width="2.4" stroke-linejoin="round"/>'
          f'<path d="M420,455 L423,462 L426,454Z" fill="#fff"/><path d="M422,468 Q430,464 438,468" fill="none" stroke="#ff8fa0" stroke-width="3" stroke-linecap="round"/></g>')
    m += (f'<g class="mouth m-smug"><path d="M412,450 Q421,459 430,451 Q439,459 448,450" fill="none" stroke="#7a3446" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
          f'<path d="M448,450 l5,-3" stroke="#7a3446" stroke-width="2.4" stroke-linecap="round"/></g>')
    m += (f'<g class="mouth m-happy"><path d="M410,446 Q430,449 450,446 Q449,476 430,477 Q411,476 410,446Z" fill="#a52d45" stroke="#6e1f2e" stroke-width="2.4" stroke-linejoin="round"/>'
          f'<path d="M418,469 Q430,460 442,469 Q438,476 430,476 Q422,476 418,469Z" fill="#ff8ea4"/>'
          f'<path d="M413,448 Q430,451 447,448 L446,453 Q430,456 414,453Z" fill="#fff"/></g>')
    m += (f'<g class="mouth m-sad"><g class="quiver"><path d="M413,463 Q417,453 423,458 Q430,452 437,458 Q443,453 447,463" fill="none" stroke="#7a3446" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g></g>')
    m += (f'<g class="mouth m-think0"><ellipse cx="440" cy="457" rx="5.5" ry="6.5" fill="#9c2c3e" stroke="#6e1f2e" stroke-width="2"/></g>')
    m += (f'<g class="mouth m-think1"><path d="M412,458 q5,-6 9,0 t9,0 t9,0 t9,0" fill="none" stroke="#7a3446" stroke-width="3" stroke-linecap="round"/></g>')
    m += (f'<g class="mouth m-think2"><path d="M412,454 L420,448 L428,456 L436,448 L444,456 L450,450 Q448,474 430,474 Q414,474 412,454Z" fill="#9c2c3e" stroke="#6e1f2e" stroke-width="2.4" stroke-linejoin="round"/></g>')
    return m


def front_hair():
    dome = "M300,360 C288,240 352,176 430,176 C508,176 572,240 562,360"
    edge = [
        ((556, 386), (546, 404)), ((540, 368), (528, 338)), ((522, 364), (508, 382)),
        ((502, 352), (490, 334)), ((482, 356), (466, 374)), ((460, 344), (448, 330)),
        ((446, 372), (428, 400)), ((424, 360), (414, 332)), ((404, 354), (390, 376)),
        ((384, 350), (372, 336)), ((364, 362), (350, 386)), ((344, 356), (334, 340)),
        ((326, 374), (314, 402)), ((306, 382), (300, 360)),
    ]
    d = dome + " " + " ".join(f"Q{c[0]},{c[1]} {p[0]},{p[1]}" for c, p in edge) + "Z"
    texture = ""
    for path in ["M430,186 C436,250 438,320 428,398", "M392,196 C376,260 380,320 390,374",
                 "M470,196 C486,260 482,320 466,372", "M350,224 C330,280 334,340 350,384",
                 "M512,224 C532,280 530,330 508,380", "M318,290 C306,330 310,370 314,400",
                 "M544,290 C556,330 552,370 546,402"]:
        texture += f'<path d="{path}" fill="none" stroke="#14286c" stroke-width="2.2" stroke-linecap="round" opacity=".6"/>'
    shine = ('<path d="M338,262 C368,238 400,230 430,230 C462,230 494,238 522,262 L514,272 C488,252 460,246 430,246 C400,246 372,252 346,272Z" '
             'fill="url(#g-hair-shine)"/>'
             '<path d="M360,258 l10,-14 l4,16Z M404,244 l6,-15 l6,15Z M450,244 l6,-15 l6,15Z M492,256 l6,-14 l6,16Z" fill="#c7efff" opacity=".7"/>')
    side = ("M320,336 C302,388 306,456 302,522 C300,550 306,568 318,584 C292,574 280,550 280,516 "
            "C278,446 284,382 302,326Z")
    side_lock = (f'<path d="{side}" fill="url(#g-hair-front)" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
                 f'<path d="M298,380 C292,440 294,500 296,548" fill="none" stroke="#14286c" stroke-width="2" opacity=".55"/>')
    side_locks = (f'<g class="lock lock-l">{side_lock}</g>'
                  f'<g transform="translate({2 * CX},0) scale(-1,1)"><g class="lock lock-r">{side_lock}</g></g>')
    return (f'{side_locks}<path d="{d}" fill="url(#g-hair-front)" stroke="{INK}" stroke-width="3.2" stroke-linejoin="round"/>'
            f'{texture}{shine}')


def headdress():
    outer = arc_pts(430, 352, 200, 158, 22, 13)
    inner = arc_pts(430, 352, 170, 22, 158, 13)
    frill = (f'<path d="{scallops(outer, 6)} L{fmt(inner[0][0])},{fmt(inner[0][1])} {polyline(inner[1:])}Z" '
             f'fill="url(#g-white)" stroke="{WHITE_LINE}" stroke-width="2.6" stroke-linejoin="round"/>')
    pleats = ""
    for a in range(30, 152, 10):
        p1 = arc_pts(430, 352, 174, a, a, 1)[0]
        p2 = arc_pts(430, 352, 194, a, a, 1)[0]
        pleats += f'<path d="M{fmt(p1[0])},{fmt(p1[1])} L{fmt(p2[0])},{fmt(p2[1])}" stroke="#d3ddef" stroke-width="2"/>'
    band = arc_pts(430, 352, 168, 160, 20, 24)
    band_d = f"M{fmt(band[0][0])},{fmt(band[0][1])} " + polyline(band[1:])
    ribbon = f'<path d="{band_d}" fill="none" stroke="{NAVY}" stroke-width="8" stroke-linecap="round"/>'
    bow = ('<g transform="translate(566,286) rotate(18)">'
           '<path d="M0,0 C-14,-24 -44,-22 -42,0 C-40,18 -16,14 0,0Z M0,0 C14,-24 44,-22 42,0 C40,18 16,14 0,0Z" fill="#4db8f2" stroke="#1d6bb6" stroke-width="2.6" stroke-linejoin="round"/>'
           '<path d="M-4,4 L-16,30 L-6,26 Z M4,4 L16,30 L6,26Z" fill="#3aa3e6" stroke="#1d6bb6" stroke-width="2" stroke-linejoin="round"/>'
           '<path d="M-10,-6 C-20,-12 -30,-12 -34,-4 M10,-6 C20,-12 30,-12 34,-4" fill="none" stroke="#a9e4ff" stroke-width="3" stroke-linecap="round"/>'
           '<ellipse rx="8" ry="9" fill="#38a0e4" stroke="#1d6bb6" stroke-width="2.4"/></g>')
    return f'<g class="headdress">{ribbon}{frill}{pleats}{bow}</g>'


def ahoge():
    art = (f'<path d="M424,182 C398,146 410,96 450,92 C480,90 490,120 472,136 C468,140 462,140 460,136 '
           f'C472,124 464,106 448,108 C424,112 420,146 440,180Z" fill="url(#g-hair-front)" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
           f'<path d="M424,160 C414,130 426,108 446,104" fill="none" stroke="#7cc8f4" stroke-width="3" stroke-linecap="round" opacity=".6"/>')
    return pivot("ahoge|ahoge-anim", 432, 180, art)


def face():
    shape = "M316,332 C312,392 322,436 352,462 C376,482 404,488 430,488 C456,488 484,482 508,462 C538,436 548,392 544,332Z"
    blush = ""
    for x in (354, 506):
        blush += (f'<ellipse cx="{x}" cy="448" rx="26" ry="13" fill="url(#g-blush)"/>'
                  f'<path d="M{x - 10},452 l5,-8 M{x - 1},452 l5,-8 M{x + 8},452 l5,-8" stroke="#ff7f95" stroke-width="2" stroke-linecap="round" opacity=".55"/>')
    return (f'<path d="{shape}" fill="url(#g-face)" stroke="{SKIN_LINE}" stroke-width="2.6"/>'
            f'<path d="M318,350 C360,372 500,372 542,350 L544,332 L316,332Z" fill="#f4d3ca" opacity=".55"/>'
            f'<g class="blush">{blush}</g>'
            f'<path d="M428,428 l2.5,3" stroke="#d99a90" stroke-width="2.4" stroke-linecap="round"/>')


# ---------------------------------------------------------------- arms
def arm(side):
    mirror = side == "r"
    sx, sy = SHOULDER_R if mirror else SHOULDER_L
    puff = (f'<path d="M-22,-8 C-30,10 -27,34 -17,46 C-8,54 8,54 17,46 C27,34 30,10 22,-8 C12,-17 -12,-17 -22,-8Z" '
            f'fill="url(#g-sleeve)" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
            f'<path d="M-12,-4 C-16,10 -14,26 -8,36" fill="none" stroke="#4462b4" stroke-width="3" stroke-linecap="round" opacity=".6"/>')
    upper = (f'<circle cy="{L_UPPER}" r="13.5" fill="url(#g-sleeve)" stroke="{INK}" stroke-width="3"/>'
             f'<path d="M-15,34 L-13,74 C-6,80 6,80 13,74 L15,34Z" fill="url(#g-sleeve)" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    cuff_pts = resample([(-16, 56), (16, 56)], 5)
    fore = (f'<path d="M-13,-4 L-13,48 L13,48 L13,-4Z" fill="url(#g-sleeve)" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
            f'<path d="M-15,40 L15,40 L16,56 L-16,56Z" fill="{NAVY_DK}" stroke="{INK}" stroke-width="2.6" stroke-linejoin="round"/>'
            f'<path d="M-14,44 L14,44 M-15,52 L15,52" stroke="{GOLD}" stroke-width="1.6"/>'
            f'<path d="M-16,56 {scallops(list(reversed(cuff_pts)), -3, start=False)[1:]} Z" fill="#fff" stroke="{WHITE_LINE}" stroke-width="2"/>')
    hand_open = (f'<g class="hand-open">'
                 f'<path d="M-10,62 C-14,72 -12,86 -2,90 C8,92 14,82 13,70 C12,63 8,60 1,60 C-4,60 -8,60 -10,62Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.4" stroke-linejoin="round"/>'
                 f'<path d="M11,66 C17,68 18,76 13,80" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.2" stroke-linecap="round"/>'
                 f'<path d="M-3,80 L-4,88 M3,80 L3,89" stroke="#d8a69c" stroke-width="1.6" stroke-linecap="round"/></g>')
    hand_fist = (f'<g class="hand-fist">'
                 f'<path d="M-13,64 C-15,76 -10,86 0,86 C11,86 15,76 13,64 C9,58 -9,58 -13,64Z" fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2.4"/>'
                 f'<path d="M-8,74 Q-4,70 0,74 Q4,70 8,74" fill="none" stroke="#d8a69c" stroke-width="1.8" stroke-linecap="round"/></g>')
    bowl = ""
    if mirror:
        grains = resample([(-28, -46), (-18, -66), (0, -72), (18, -66), (28, -46)], 9)
        bowl = (f'<g transform="translate(0,84)"><g class="bowl">'
                f'<g class="bowl-steam">'
                f'<path d="M-12,-80 C-20,-92 -4,-100 -12,-114" fill="none" stroke="#bfe8ff" stroke-width="4" stroke-linecap="round"/>'
                f'<path d="M8,-82 C0,-94 16,-102 8,-118" fill="none" stroke="#bfe8ff" stroke-width="4" stroke-linecap="round"/></g>'
                f'<path d="{scallops(grains, 2.2)} Z" fill="#fff" stroke="#c3cfe2" stroke-width="2"/>'
                f'<path d="M-36,-46 C-34,-18 -18,-6 0,-6 C18,-6 34,-18 36,-46Z" fill="url(#g-white)" stroke="#2a4c9a" stroke-width="2.8" stroke-linejoin="round"/>'
                f'<path d="M-32,-32 C-18,-24 18,-24 32,-32" fill="none" stroke="#3b82dc" stroke-width="3"/>'
                f'<path d="M-20,-20 q5,-5 10,0 t10,0 t10,0 t10,0" fill="none" stroke="#52b6f2" stroke-width="2.2"/>'
                f'<path d="M-12,-7 L12,-7 L10,0 L-10,0Z" fill="#dbe6f6" stroke="#2a4c9a" stroke-width="2.2"/>'
                f'<path d="M24,-74 L46,-30 M30,-76 L50,-34" stroke="#9b5a2c" stroke-width="3.4" stroke-linecap="round"/>'
                f'</g></g>')
    fore_group = (f'<g transform="translate(0,{L_UPPER})"><g class="f-pose"><g class="f-anim">'
                  f'{fore}{hand_open}{hand_fist}{bowl}</g></g></g>')
    inner = f'<g class="u-pose"><g class="u-anim">{upper}{puff}{fore_group}</g></g>'
    flip = " scale(-1,1)" if mirror else ""
    return f'<g class="arm arm-{side}" transform="translate({sx},{sy}){flip}">{inner}</g>'


# ---------------------------------------------------------------- effects
def head_fx():
    anger = ('<g class="fx fx-angry"><g transform="translate(548,236)"><g class="anger-mark">'
             '<path d="M-6,-20 C-6,-10 -10,-6 -20,-6 M6,-20 C6,-10 10,-6 20,-6 M-6,20 C-6,10 -10,6 -20,6 M6,20 C6,10 10,6 20,6" '
             'fill="none" stroke="#ff3a4f" stroke-width="7" stroke-linecap="round"/></g></g>'
             '<g transform="translate(300,250)"><g class="steam steam-a"><path d="M0,0 c-14,0 -20,-14 -10,-22 c0,-14 20,-16 24,-6 c12,-4 22,8 14,18 c4,10 -10,16 -16,10 c-4,6 -14,4 -12,0Z" fill="#fff" stroke="#c9d6ea" stroke-width="2.4"/></g></g>'
             '<g transform="translate(576,232)"><g class="steam steam-b"><path d="M0,0 c-14,0 -20,-14 -10,-22 c0,-14 20,-16 24,-6 c12,-4 22,8 14,18 c4,10 -10,16 -16,10 c-4,6 -14,4 -12,0Z" fill="#fff" stroke="#c9d6ea" stroke-width="2.4"/></g></g>'
             '</g>')
    tears = ('<g class="fx fx-sad">'
             '<path class="tear-stream" d="M366,436 C362,456 362,480 366,500 L380,500 C382,480 380,456 380,436Z" fill="url(#g-tear)"/>'
             '<path class="tear-stream" d="M480,436 C478,456 478,480 482,500 L496,500 C498,480 496,456 494,436Z" fill="url(#g-tear)"/>'
             '<g transform="translate(372,500)"><g class="drop drop-a"><path d="M0,-8 C5,-1 7,3 7,6 A7,7 0 1,1 -7,6 C-7,3 -5,-1 0,-8Z" fill="#9fe0ff" stroke="#4aa6e0" stroke-width="1.6"/></g></g>'
             '<g transform="translate(489,500)"><g class="drop drop-b"><path d="M0,-8 C5,-1 7,3 7,6 A7,7 0 1,1 -7,6 C-7,3 -5,-1 0,-8Z" fill="#9fe0ff" stroke="#4aa6e0" stroke-width="1.6"/></g></g>'
             '<g class="gloom" stroke="#6a7fd0" stroke-width="3" stroke-linecap="round" opacity=".55">'
             '<path d="M352,280 L352,330 M370,268 L370,334 M388,262 L388,322 M406,258 L406,336"/></g>'
             '</g>')
    sweat = ('<g class="fx fx-sweat"><g transform="translate(306,334)"><g class="sweat">'
             '<path d="M0,-16 C8,-4 11,3 11,8 A11,11 0 1,1 -11,8 C-11,3 -8,-4 0,-16Z" fill="#c9f0ff" stroke="#4aa6e0" stroke-width="2.4"/>'
             '<path d="M-4,4 Q-5,10 -1,13" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></g></g></g>')
    think_steam = ('<g class="fx fx-overheat">'
                   '<g transform="translate(330,206)"><g class="steam steam-a"><path d="M0,0 c-14,0 -20,-14 -10,-22 c0,-14 20,-16 24,-6 c12,-4 22,8 14,18 c4,10 -10,16 -16,10 c-4,6 -14,4 -12,0Z" fill="#f3f7ff" stroke="#c9d6ea" stroke-width="2.4"/></g></g>'
                   '<g transform="translate(522,196)"><g class="steam steam-b"><path d="M0,0 c-14,0 -20,-14 -10,-22 c0,-14 20,-16 24,-6 c12,-4 22,8 14,18 c4,10 -10,16 -16,10 c-4,6 -14,4 -12,0Z" fill="#f3f7ff" stroke="#c9d6ea" stroke-width="2.4"/></g></g>'
                   '</g>')
    return anger + tears + sweat + think_steam


def body_fx():
    smug = '<g class="fx fx-smug">'
    for i, (x, y, r) in enumerate([(286, 262, 16), (604, 196, 12), (628, 420, 10), (250, 470, 9)]):
        smug += f'<g transform="translate({x},{y})"><g class="twinkle tw-{i}"><path d="{star4(0, 0, r)}" fill="#ffd36b" stroke="#e5a52a" stroke-width="1.6"/></g></g>'
    smug += "</g>"
    happy = '<g class="fx fx-happy">'
    items = [(250, 330, "heart", "#ff8aa8"), (620, 300, "star", "#ffd36b"), (210, 500, "star", "#7fd8ff"),
             (650, 470, "heart", "#ff9fbc"), (300, 180, "star", "#9fe6ff"), (590, 150, "heart", "#ff8aa8")]
    for i, (x, y, kind, col) in enumerate(items):
        shape = heart(0, 0, 1.1) if kind == "heart" else star4(0, 0, 13)
        happy += f'<g transform="translate({x},{y})"><g class="float-up fu-{i}"><path d="{shape}" fill="{col}" stroke="#fff" stroke-width="2"/></g></g>'
    happy += "</g>"
    cloud = ("M-46,10 C-62,10 -64,-12 -48,-16 C-48,-34 -24,-40 -14,-28 C-6,-44 22,-44 28,-26 "
             "C44,-32 60,-18 52,-4 C64,2 58,20 44,18 C34,26 -36,26 -46,10Z")
    sad = (f'<g class="fx fx-sad"><g transform="translate(300,150)"><g class="rain-cloud">'
           f'<path d="{cloud}" fill="#b7c6e6" stroke="#7b8fbf" stroke-width="3"/>'
           f'<path d="M-30,0 C-20,6 10,8 30,2" fill="none" stroke="#dbe5f8" stroke-width="3" stroke-linecap="round"/>'
           f'<g class="rain"><path class="rd rd-0" d="M-24,30 l-4,12"/><path class="rd rd-1" d="M0,32 l-4,12"/><path class="rd rd-2" d="M22,30 l-4,12"/></g>'
           f'</g></g></g>')
    bubble = (f'<g class="fx fx-think"><g class="thought" transform="translate(664,176)">'
              f'<circle cx="-92" cy="88" r="7" fill="#fff" stroke="#7fb4dc" stroke-width="2.6"/>'
              f'<circle cx="-70" cy="64" r="11" fill="#fff" stroke="#7fb4dc" stroke-width="2.6"/>'
              f'<path d="{cloud}" transform="scale(1.25)" fill="#fff" stroke="#7fb4dc" stroke-width="2.4"/>'
              f'<g class="think-dots"><circle class="dot dot-0" cx="-24" cy="0" r="7" fill="#2e7fe0"/>'
              f'<circle class="dot dot-1" cx="0" cy="0" r="7" fill="#2e7fe0"/><circle class="dot dot-2" cx="24" cy="0" r="7" fill="#2e7fe0"/></g>'
              f'<g class="think-scribble"><path d="M-40,4 C-30,-22 -10,20 0,-6 C10,-30 22,22 34,-8 C40,-20 46,6 30,10 C10,16 -20,-18 -34,0" '
              f'fill="none" stroke="#e0485e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
              f'</g>'
              f'<g transform="translate(256,232)"><g class="qmark"><path d="M-9,-10 C-9,-24 12,-24 12,-10 C12,-1 2,0 2,9" fill="none" stroke="#2e7fe0" stroke-width="5.5" stroke-linecap="round"/>'
              f'<circle cx="2" cy="19" r="3.6" fill="#2e7fe0"/></g></g>'
              f'<g transform="translate(244,250)"><g class="bang"><path d="M0,-26 L0,4" stroke="#e0485e" stroke-width="7" stroke-linecap="round"/><circle cy="18" r="4.4" fill="#e0485e"/>'
              f'<path d="M-26,-14 C-26,-28 -6,-28 -6,-14 C-6,-6 -16,-4 -16,4" transform="translate(-6,0)" fill="none" stroke="#2e7fe0" stroke-width="5.5" stroke-linecap="round"/><circle cx="-22" cy="16" r="3.6" fill="#2e7fe0"/></g></g>'
              f'</g>')
    return smug + happy + sad + bubble


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


# ---------------------------------------------------------------- assemble
def build():
    t = tail()
    head_back = pivot("head-pose|head-anim", CX, 492, hair_back())
    eyes = eye(378, 400, -1) + eye(482, 400, 1)
    head_front_inner = (f'{fin_ear(True)}{fin_ear(False)}{face()}{eyes}{mouths()}{front_hair()}{brows()}'
                        f'{headdress()}{ahoge()}{head_fx()}')
    head_front = pivot("head-pose|head-anim", CX, 492, head_front_inner)

    upper = (f'<g class="upper"><g class="upper-anim">{head_back}{torso()}{head_front}'
             f'{arm("l")}{arm("r")}</g></g>')
    char = (f'<g transform="translate({CX},990)"><g class="char-pose"><g class="char-anim">'
            f'<g transform="translate({-CX},-990)">{t}{legs()}{upper}{body_fx()}</g></g></g></g>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1060" role="img" '
           f'aria-labelledby="title desc" class="whale-chan" data-mood="neutral" data-strain="0">\n'
           f'  <title id="title">Whale-chan</title>\n'
           f'  <desc id="desc">A chibi DeepSeek whale maid drawn as rigged vector art. Her body, face, tail, '
           f'fin-ears and ahoge are posed and animated per mood: neutral, angry, smug, happy, sad and thinking.</desc>'
           f'{DEFS}{css()}\n  {char}\n</svg>\n')
    return svg


if __name__ == "__main__":
    OUT.write_text(build())
    print(f"wrote {OUT}")
    for name, pose in P.items():
        print(f"  {name:8s} left arm {pose['l']}  right arm {pose['r']}")
