"""Profile a game screenshot layer by layer: who uses which part of the lightness /
saturation range, who owns the reserved bands, how far each layer separates from
the canvas. Pillow + numpy only. On Windows run with `py`.

  python sv_profile.py shot.png -o OUT -r "!environment:0,0,1,1" -r "player:0.42,0.40,0.50,0.55" -m "enemies:mask.png" -r "hud:0,0.88,1,1"

LAYERS - list the canvas (bottom) layer first, the top layer last
  -r NAME:x0,y0,x1,y1      rectangle        -p NAME:x,y,x,y,...   polygon
  -m NAME:mask.png         mask (non-black and non-transparent pixels)
  Coordinates are pixels of the original image, or 0-1 fractions when every value
  is <= 1. Repeat a name to merge shapes. A pixel claimed by several layers goes to
  the last one listed. "!NAME:shape" = the pixels of that shape no normal layer
  claims (use "!canvas:0,0,1,1" for "everything else").

INPUT
  --crop x0,y0,x1,y1       crop image, shapes and masks together (pixels or fractions)
  --frame N|all            frame of a GIF/APNG (default 0). all = pool every frame and
                           report each layer's share of frame-to-frame motion
  --ignore-alpha           count fully transparent pixels (excluded by default)
  --display-gamma G        the code values drive a display with gamma G (1 = raw
                           linear LED panel); convert to what an sRGB monitor would
                           show before measuring
  --baseline OTHER.png     same-size frame to compare against (reports IMAGE - OTHER)

MEASURE
  --space hsb|hsl|lab      colour space of the saturation / lightness columns, the
                           chart, the reach numbers and the top band (default hsb).
                           L* (CIELAB lightness, what a greyscale test shows) is
                           always printed next to it
  --pct 5,50,95            percentiles; first and last form the envelope
  --min-v 15               saturation is only measured where lightness >= this
                           (HSB/HSL saturation explodes near black); 0-1 or 0-100
  --top-band 90            lightness threshold of the default reserved band "top"
  --band NAME:COND         extra reserved band, repeatable. COND = terms joined by &:
                           X>=n, X<=n with X in H S V L L* C, or H=a-b (degrees,
                           wraps through 0). Example: "enemy:H=330-20&S>=60".
                           A hue term needs an S>= or C>= term. V/S are HSB (S is
                           HSL with --space hsl), L is HSL lightness, C is chroma.

OUTPUT
  Table per layer: area, saturation, lightness and L* percentiles, detail density
  (mean |Laplacian| x100; compare within one image, or use the "x canvas" ratio),
  share of the top band it owns by the chosen lightness and by L*, share of the
  layer inside the band. Then reach beyond the canvas: local (ring of canvas pixels
  around the layer) first, global second, and the share of the layer's pixels that
  fall outside the canvas p1-p99 range.
  Images: sv_chart.png, value_bands.png (red = in the top band by both measures,
  orange = by the space lightness only, i.e. saturated glow), gray.png, blur.png,
  layers_overlay.png (check your regions), protan.png, deutan.png, plus bands.png,
  diff.png, motion.png when applicable.
"""
import argparse, os, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PALETTE = [(40, 190, 70), (240, 125, 55), (215, 30, 40), (245, 200, 30),
           (60, 140, 240), (180, 80, 220), (20, 200, 200), (140, 140, 140)]
MACHADO = {"protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
           "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]}
XYZ = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]], np.float32)
SPACES = {"hsb": ("Sb", "V", "S", "V", 100.0), "hsl": ("Sl", "L", "S", "L", 100.0), "lab": ("C", "L*", "C*", "L*", 135.0)}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(2)


def warn(msg):
    print("WARN: " + msg)


def font(size):
    for f in ("msyh.ttc", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def unit(text, what, allow_zero=False):
    try:
        x = float(text)
    except ValueError:
        fail(f"{what}: not a number: {text!r}")
    if x > 1:
        x /= 100.0
    if not ((0 <= x if allow_zero else 0 < x) and x <= 1):
        fail(f"{what} must be within 0-1 (or 0-100), got {text!r}")
    return x


def srgb_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def srgb_enc(l):
    l = np.clip(l, 0, 1)
    return np.where(l <= 0.0031308, 12.92 * l, 1.055 * np.power(l, 1 / 2.4) - 0.055).astype(np.float32)


def lab_f(t):
    return np.where(t > (6 / 29) ** 3, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)


def channels(rgb):
    """rgb float32 (...,3) in 0-1 -> dict of channel arrays (0-100, H in degrees)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    sb = np.divide(d, mx, out=np.zeros_like(d), where=mx > 0)
    lh = (mx + mn) / 2
    den = 1 - np.abs(2 * lh - 1)
    sl = np.clip(np.divide(d, den, out=np.zeros_like(d), where=den > 1e-6), 0, 1)
    dd = np.where(d > 0, d, 1)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) * 60
    h = np.where(d > 0, h, 0)
    x = srgb_lin(rgb) @ XYZ.T
    fx, fy, fz = lab_f(x[..., 0] / 0.95047), lab_f(x[..., 1]), lab_f(x[..., 2] / 1.08883)
    return {"H": h.astype(np.float32), "Sb": sb * 100, "V": mx * 100, "Sl": sl * 100, "L": lh * 100,
            "L*": (116 * fy - 16).astype(np.float32), "C": np.hypot(500 * (fx - fy), 200 * (fy - fz)).astype(np.float32),
            "Y": x[..., 1]}


def parse_cond(text):
    terms = []
    for raw in text.split("&"):
        t = raw.replace(" ", "")
        m = re.fullmatch(r"H=([\d.]+)-([\d.]+)", t)
        if m:
            terms.append(("H", "range", float(m.group(1)) % 360, float(m.group(2)) % 360))
            continue
        m = re.fullmatch(r"(L\*|[HSVLC])(>=|<=)([\d.]+)", t)
        if not m:
            fail(f"cannot parse condition term {raw!r} (use X>=n, X<=n with X in H S V L L* C, or H=a-b)")
        terms.append((m.group(1), m.group(2), float(m.group(3))))
    if any(t[0] == "H" for t in terms) and not any(t[0] in ("S", "C") and t[1] == ">=" for t in terms):
        fail(f"condition {text!r}: a hue term needs an S>= or C>= term (hue means nothing at low saturation)")
    return terms


def eval_cond(terms, ch):
    m = None
    for t in terms:
        x = ch[t[0]]
        if t[1] == "range":
            mm = ((x >= t[2]) & (x <= t[3])) if t[2] <= t[3] else ((x >= t[2]) | (x <= t[3]))
        else:
            mm = (x >= t[2]) if t[1] == ">=" else (x <= t[2])
        m = mm if m is None else (m & mm)
    return m


def nums(text, w, h, what):
    try:
        v = [float(t) for t in text.split(",")]
    except ValueError:
        fail(f"{what}: coordinates must be numbers: {text!r}")
    if all(abs(t) <= 1.0 for t in v):
        v = [t * (w if i % 2 == 0 else h) for i, t in enumerate(v)]
    return v


def load(path, frame, gamma):
    """-> rgb float32 (F,H,W,3) in 0-1 (after display gamma), alpha uint8 (F,H,W), frame count."""
    try:
        im = Image.open(path)
    except (OSError, ValueError) as e:
        fail(f"cannot open image {path!r}: {e}")
    n = getattr(im, "n_frames", 1)
    if frame == "all":
        idx = list(range(n))
    else:
        try:
            idx = [int(frame)]
        except ValueError:
            fail(f"--frame must be a number or 'all', got {frame!r}")
        if not 0 <= idx[0] < n:
            fail(f"--frame {idx[0]} out of range: {os.path.basename(path)} has {n} frame(s)")
    w, h = im.size
    if len(idx) * w * h > 60_000_000:
        keep = max(2, 60_000_000 // (w * h))
        idx = [idx[int(i)] for i in np.linspace(0, len(idx) - 1, keep)]
        warn(f"too many pixels for --frame all; sampling {keep} of {n} frames evenly")
    rgb, alpha = [], []
    for i in idx:
        im.seek(i)
        fr = im
        if fr.mode in ("I;16", "I;16L", "I;16B", "I", "F"):
            a = np.asarray(fr).astype(np.float32)
            if a.max() > 255:
                a = a / 257.0
            fr = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
        rgba = np.asarray(fr.convert("RGBA"))
        rgb.append(rgba[..., :3])
        alpha.append(rgba[..., 3])
    rgb = np.stack(rgb).astype(np.float32) / 255.0
    if gamma is not None:
        rgb = srgb_enc(np.power(rgb, gamma))
    return rgb, np.stack(alpha), n


def pstr(a, pcts):
    return "n/a" if a.size == 0 else "-".join(f"{v:.0f}" for v in np.percentile(a, pcts))


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    class Shape(argparse.Action):  # keeps -r / -p / -m in command-line order
        def __call__(self, parser, ns, value, option_string=None):
            ns.shapes = (getattr(ns, "shapes", None) or []) + [(self.dest[0], value)]

    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="sv_profile_out")
    ap.add_argument("-r", "--rect", action=Shape, help="NAME:x0,y0,x1,y1")
    ap.add_argument("-p", "--poly", action=Shape, help="NAME:x,y,x,y,...")
    ap.add_argument("-m", "--mask", action=Shape, help="NAME:mask.png")
    ap.add_argument("--crop")
    ap.add_argument("--frame", default="0")
    ap.add_argument("--ignore-alpha", action="store_true")
    ap.add_argument("--display-gamma", type=float)
    ap.add_argument("--baseline")
    ap.add_argument("--space", choices=list(SPACES), default="hsb")
    ap.add_argument("--pct", default="5,50,95")
    ap.add_argument("--min-v", default="0.15")
    ap.add_argument("--top-band", default="0.90")
    ap.add_argument("--band", action="append", default=[], help="NAME:COND")
    a = ap.parse_args()

    thr = unit(a.top_band, "--top-band")
    minv = unit(a.min_v, "--min-v", allow_zero=True)
    try:
        pcts = [float(t) for t in a.pct.split(",")]
    except ValueError:
        fail(f"--pct must be a comma list of numbers, got {a.pct!r}")
    if len(pcts) < 2 or any(not 0 <= p <= 100 for p in pcts) or pcts != sorted(pcts):
        fail("--pct needs at least two ascending percentiles within 0-100")
    ptxt = "p" + "-".join(f"{p:g}" for p in pcts)
    sat_k, lig_k, satname, ligname, smax = SPACES[a.space]
    if a.display_gamma is not None and a.display_gamma <= 0:
        fail("--display-gamma must be > 0")

    rgb, alpha, nframes = load(a.image, a.frame, a.display_gamma)
    F, H0, W0 = rgb.shape[:3]
    if nframes > 1:
        print(f"{nframes} frames in {os.path.basename(a.image)}; " +
              (f"pooling {F} frames" if a.frame == "all" else f"measuring frame {a.frame} only (use --frame all to pool every frame)"))

    # ---- crop box (original coordinates)
    cx0, cy0, cx1, cy1 = 0, 0, W0, H0
    if a.crop:
        v = nums(a.crop, W0, H0, "--crop")
        if len(v) != 4:
            fail("--crop needs x0,y0,x1,y1")
        cx0, cx1 = sorted((int(round(v[0])), int(round(v[2]))))
        cy0, cy1 = sorted((int(round(v[1])), int(round(v[3]))))
        cx0, cy0, cx1, cy1 = max(0, cx0), max(0, cy0), min(W0, cx1), min(H0, cy1)
        if cx1 <= cx0 or cy1 <= cy0:
            fail(f"--crop {a.crop!r} leaves no pixels")

    # ---- layer shapes, built in original coordinates
    order, shapes, invert = [], {}, set()
    for kind, spec in (getattr(a, "shapes", None) or []):
        if ":" not in spec:
            fail(f"layer {spec!r}: expected NAME:...")
        name, payload = spec.split(":", 1)
        inv = name.startswith("!")
        name = name[1:] if inv else name
        if not name:
            fail(f"layer {spec!r}: empty name")
        m = np.zeros((H0, W0), bool)
        if kind == "r":
            v = nums(payload, W0, H0, f"rectangle {name!r}")
            if len(v) != 4:
                fail(f"rectangle {name!r} needs x0,y0,x1,y1")
            x0, x1 = sorted((int(round(v[0])), int(round(v[2]))))
            y0, y1 = sorted((int(round(v[1])), int(round(v[3]))))
            m[max(0, y0):min(H0, y1), max(0, x0):min(W0, x1)] = True
        elif kind == "p":
            v = nums(payload, W0, H0, f"polygon {name!r}")
            if len(v) % 2 or len(v) < 6:
                fail(f"polygon {name!r} needs an even number of coordinates and at least 3 points (got {len(v)} numbers)")
            pim = Image.new("L", (W0, H0), 0)
            ImageDraw.Draw(pim).polygon(list(zip(v[0::2], v[1::2])), fill=255)
            m = np.asarray(pim) > 0
        else:
            try:
                mim = Image.open(payload)
            except (OSError, ValueError) as e:
                fail(f"mask {name!r}: cannot open {payload!r}: {e}")
            if mim.mode.startswith("I") or mim.mode == "F":
                mm = np.asarray(mim) > 0
            else:
                arr = np.asarray(mim.convert("RGBA"))
                mm = (arr[..., :3].max(-1) > 0) & (arr[..., 3] > 0)
            if mm.shape == (H0, W0):
                m = mm
            elif a.crop and mm.shape == (cy1 - cy0, cx1 - cx0):
                m[cy0:cy1, cx0:cx1] = mm
            else:
                mh, mw = mm.shape
                if abs((mw / mh) / (W0 / H0) - 1) > 0.01:
                    fail(f"mask {name!r} is {mw}x{mh} but the image is {W0}x{H0}: different aspect ratio")
                warn(f"mask {name!r} is {mw}x{mh}, image is {W0}x{H0}; resizing the mask (nearest)")
                m = np.asarray(Image.fromarray(mm.astype(np.uint8) * 255).resize((W0, H0), Image.NEAREST)) > 0
        if not m[cy0:cy1, cx0:cx1].any():
            warn(f"a shape of layer {name!r} covers 0 pixels: {spec!r}")
        if inv:
            invert.add(name)
        if name not in shapes:
            order.append(name)
            shapes[name] = m
        else:
            shapes[name] = shapes[name] | m

    rgb, alpha = rgb[:, cy0:cy1, cx0:cx1], alpha[:, cy0:cy1, cx0:cx1]
    H, W = rgb.shape[1:3]
    if not order:
        order, shapes = ["whole frame"], {"whole frame": np.ones((H0, W0), bool)}
    shapes = {n: m[cy0:cy1, cx0:cx1] for n, m in shapes.items()}

    owner = np.full((H, W), -1, np.int16)
    for i, n in enumerate(order):
        if n not in invert:
            owner[shapes[n]] = i
    fixed = owner >= 0
    for i, n in enumerate(order):
        if n in invert:
            owner[shapes[n] & ~fixed] = i

    valid = np.ones((F, H, W), bool)
    transparent = alpha == 0
    if transparent.any() and not a.ignore_alpha:
        valid = ~transparent
        print(f"{transparent.mean()*100:.1f}% of pixels are fully transparent and excluded (--ignore-alpha to count them)")
    if not valid.any():
        fail("no pixels left to measure (everything is transparent)")
    own3 = np.broadcast_to(owner, (F, H, W))
    masks = {n: (own3 == i) & valid for i, n in enumerate(order)}
    canvas = order[0]
    if not masks[canvas].any():
        fail(f"the canvas layer {canvas!r} (first layer) has no pixels")
    colour = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(order)}

    ch = channels(rgb)
    sat, lig, lst = ch[sat_k], ch[lig_k], ch["L*"]
    if a.space == "hsb":
        sat_ok = ch["V"] >= minv * 100
    elif a.space == "hsl":
        sat_ok = (ch["L"] >= minv * 100) & (ch["L"] <= 100 - minv * 100)
    else:
        sat_ok = np.ones((F, H, W), bool)
    cond_ch = {"H": ch["H"], "S": ch["Sl"] if a.space == "hsl" else ch["Sb"], "V": ch["V"], "L": ch["L"], "L*": lst, "C": ch["C"]}

    grey = srgb_enc(ch["Y"])  # grey with the same L*
    gp = np.pad(grey, ((0, 0), (1, 1), (1, 1)), mode="reflect" if min(H, W) > 1 else "edge")
    lap = np.abs(4 * grey - gp[:, :-2, 1:-1] - gp[:, 2:, 1:-1] - gp[:, 1:-1, :-2] - gp[:, 1:-1, 2:])

    thr100 = thr * 100
    lthr = thr100 if a.space == "lab" else float(116 * lab_f(srgb_lin(np.float32(thr))) - 16)
    band_main = (lig >= thr100 - 1e-4) & valid
    band_l = (lst >= lthr - 1e-3) & valid
    bands = [(f"top:{ligname}>={thr100:g}", band_main), (f"top(L*>={lthr:.1f})", band_l)]
    custom = []
    for spec in a.band:
        if ":" not in spec:
            fail(f"--band {spec!r}: expected NAME:COND")
        bname, cond = spec.split(":", 1)
        terms = parse_cond(cond)
        if any(t[0] != "H" and t[1] != "range" and 0 < t[2] <= 1 for t in terms):
            warn(f"--band {spec!r}: thresholds are written 0-100, not 0-1")
        custom.append((f"{bname}:{cond}", eval_cond(terms, cond_ch) & valid))
    bands += custom

    # ---- layer table
    note = {"hsb": f"S only where V >= {minv*100:g}", "hsl": f"S only where {minv*100:g} <= L <= {100-minv*100:g}", "lab": "C* = chroma, no filter"}[a.space]
    print(f"image {W}x{H}" + (f" x {F} frames" if F > 1 else "") + f"   space {a.space} ({note}); top band = {ligname} >= {thr100:g} (L* equivalent {lthr:.1f})")
    if a.display_gamma is not None:
        print(f"display gamma {a.display_gamma:g}: values below are what an sRGB monitor would need to show to match the panel")
    hdr = (f"{'layer':<14}{'area':>7}  {satname + ' ' + ptxt:>15}  {ligname + ' ' + ptxt:>15}  {'L* ' + ptxt:>15}  "
           f"{'detail':>6} {'xcanvas':>7}  {'top%' + ligname:>7} {'top%L*':>7} {'inTop%':>7}")
    print(hdr)
    env, det = {}, {}
    nvalid = int(valid.sum())
    tot_main, tot_l = max(int(band_main.sum()), 1), max(int(band_l.sum()), 1)
    canvas_det = float(lap[masks[canvas]].mean())
    own_main, own_l = {}, {}
    for n in order:
        m = masks[n]
        if not m.any():
            print(f"{n:<14}  (no pixels)")
            continue
        s = sat[m & sat_ok]
        lv, ls = lig[m], lst[m]
        det[n] = float(lap[m].mean())
        env[n] = (np.percentile(s, pcts) if s.size else None, np.percentile(lv, pcts), np.percentile(ls, pcts), s.size / m.sum())
        own_main[n], own_l[n] = (band_main & m).sum() / tot_main * 100, (band_l & m).sum() / tot_l * 100
        xc = f"{det[n] / canvas_det:7.1f}" if canvas_det > 0 else f"{'n/a':>7}"
        print(f"{n:<14}{m.sum() / nvalid * 100:6.1f}%  {pstr(s, pcts):>15}  {pstr(lv, pcts):>15}  {pstr(ls, pcts):>15}  "
              f"{det[n]*100:6.1f} {xc}  {own_main[n]:6.1f}% {own_l[n]:6.1f}% {(lv >= thr100 - 1e-4).mean()*100:6.1f}%")
        if s.size == 0:
            warn(f"layer {n!r} has no pixels where {satname} can be measured ({note}); {satname} shown as n/a")
        elif s.size / m.sum() < 0.05:
            warn(f"layer {n!r}: {satname} is measured on only {s.size / m.sum()*100:.1f}% of its pixels")
    un = (own3 == -1) & valid
    if un.any():
        print(f"{'(unassigned)':<14}{un.sum() / nvalid * 100:6.1f}%  owns {(band_main & un).sum() / tot_main * 100:.1f}% of the top band")
    print(f"  detail = mean |Laplacian| x100 of the greyscale image: compare layers within one image, or use xcanvas;")
    print(f"  top%{ligname} / top%L* = share of ALL top-band pixels inside this layer, by {ligname} and by L*; inTop% = share of the layer in the band")
    names = [n for n in order if n in env]
    if band_main.any() and band_l.any():
        lead_a, lead_b = max(names, key=lambda n: own_main[n]), max(names, key=lambda n: own_l[n])
        if lead_a != lead_b:
            print(f"NOTE: by {ligname} the top band belongs mostly to {lead_a!r}, by L* mostly to {lead_b!r}: "
                  f"{lead_a!r} is saturated glow rather than light. Judge it together with saturation.")
    elif band_main.any() and not band_l.any():
        print(f"NOTE: nothing reaches the top band by L*; what is in the band by {ligname} is saturated colour, not light.")

    if custom:
        print("\nband ownership (size = share of the frame; then the share of the band inside each layer):")
        print(f"{'band':<30}{'size':>7}  " + "  ".join(f"{n[:12]:>12}" for n in names))
        for bname, bm in bands:
            tot = int(bm.sum())
            print(f"{bname[:30]:<30}{tot / nvalid * 100:6.2f}%  " +
                  "  ".join(f"{((bm & masks[n]).sum() / tot * 100 if tot else 0):11.1f}%" for n in names))

    # ---- reach beyond the canvas
    if len(names) > 1:
        cs, cl, cL, _ = env[canvas]
        cm = masks[canvas]
        c1, c99 = np.percentile(lig[cm], [1, 99])
        cs_all = sat[cm & sat_ok]
        cs99 = np.percentile(cs_all, 99) if cs_all.size else None
        r = max(1, int(round(min(H, W) * 0.01)))
        lo, hi = 0, len(pcts) - 1
        print(f"\nreach beyond the canvas {canvas!r} (+ = range the canvas leaves free; envelope = {ptxt.split('-')[0]}..p{pcts[-1]:g}):")
        for n in names[1:]:
            ns, nl, nL, _ = env[n]
            m2 = (owner == order.index(n))
            dil = np.asarray(Image.fromarray(m2.astype(np.uint8) * 255).filter(ImageFilter.BoxBlur(r))) > 0
            ring = np.broadcast_to(dil & ~m2 & (owner == 0), (F, H, W)) & valid
            if ring.sum() >= 8:
                rl, rL = np.percentile(lig[ring], [pcts[lo], pcts[hi]]), np.percentile(lst[ring], [pcts[lo], pcts[hi]])
                rs = sat[ring & sat_ok]
                ms = f"more saturated {ns[hi] - np.percentile(rs, pcts[hi]):+4.0f}" if ns is not None and rs.size else "more saturated  n/a"
                print(f"  {n:<13} local  (ring {r}px): brighter {nl[hi] - rl[1]:+4.0f} (L* {nL[hi] - rL[1]:+4.0f})   "
                      f"darker {rl[0] - nl[lo]:+4.0f} (L* {rL[0] - nL[lo]:+4.0f})   {ms}")
            else:
                print(f"  {n:<13} local  : n/a (the layer does not touch the canvas)")
            ms = f"more saturated {ns[hi] - cs[hi]:+4.0f}" if ns is not None and cs is not None else "more saturated  n/a"
            print(f"  {'':<13} global            : brighter {nl[hi] - cl[hi]:+4.0f} (L* {nL[hi] - cL[hi]:+4.0f})   "
                  f"darker {cl[lo] - nl[lo]:+4.0f} (L* {cL[lo] - nL[lo]:+4.0f})   {ms}")
            m = masks[n]
            lv = lig[m]
            sv = sat[m & sat_ok]
            so = f"{(sv > cs99).mean()*100:5.1f}%" if sv.size and cs99 is not None else "  n/a"
            print(f"  {'':<13} pixels outside the canvas p1-p99: brighter {(lv > c99).mean()*100:5.1f}%   darker {(lv < c1).mean()*100:5.1f}%   more saturated {so}")

    # ---- small palettes
    code = (np.round(rgb * 255).astype(np.uint32) * np.array([65536, 256, 1], np.uint32)).sum(-1, dtype=np.uint32)
    probe = np.unique(code.ravel()[:: max(1, code.size // 200_000)])
    if probe.size <= 256 and np.unique(code).size <= 256:
        print(f"\nsmall palette - most used colours per layer (hex share {satname}/{ligname}/L*):")
        for n in names:
            m = masks[n]
            cols, cnt = np.unique(code[m], return_counts=True)
            parts = []
            for k in np.argsort(-cnt)[:8]:
                i = np.argmax(m.ravel() & (code.ravel() == cols[k]))
                parts.append(f"#{int(cols[k]):06x} {cnt[k] / cnt.sum()*100:4.1f}% {sat.ravel()[i]:.0f}/{lig.ravel()[i]:.0f}/{lst.ravel()[i]:.0f}")
            print(f"  {n:<13} " + " | ".join(parts))

    # ---- motion (pooled frames)
    os.makedirs(a.out, exist_ok=True)
    written = []
    if F > 1:
        dl = np.abs(np.diff(lst, axis=0)) * (valid[1:] & valid[:-1])
        energy = dl.sum(0)
        tot = float(energy.sum())
        print("\nmotion (share of frame-to-frame |dL*| energy per layer):")
        if tot > 0:
            print("  " + "   ".join(f"{n} {energy[owner == order.index(n)].sum() / tot * 100:.1f}%" for n in names))
        else:
            print("  no change between frames")
        per = np.maximum(valid.reshape(F, -1).sum(1), 1)
        for label, bm in ((ligname, band_main), ("L*", band_l)):
            share = bm.reshape(F, -1).sum(1) / per * 100
            print(f"  top band share per frame by {label}: max {share.max():.1f}% at frame {int(share.argmax())}, min {share.min():.1f}%")
        e = energy / max(float(energy.max()), 1e-6)
        Image.fromarray((np.stack([e, e * 0.6, 1 - e], -1) * 255 * (0.25 + 0.75 * e[..., None])).astype(np.uint8)).save(os.path.join(a.out, "motion.png"))
        written.append("motion.png")

    # ---- baseline comparison
    if a.baseline:
        b_rgb, b_alpha, _ = load(a.baseline, "0", a.display_gamma)
        b_rgb = b_rgb[:, cy0:cy1, cx0:cx1] if b_rgb.shape[1:3] == (H0, W0) else b_rgb
        if b_rgb.shape[1:3] != (H, W):
            fail(f"--baseline is {b_rgb.shape[2]}x{b_rgb.shape[1]}, the image is {W}x{H}: sizes must match")
        bch = channels(b_rgb[:1])
        diff = np.abs(rgb[0] - b_rgb[0]).max(-1)
        changed = diff > 8 / 255
        v0 = valid[0]
        b_sat_ok = sat_ok[0]
        print(f"\nbaseline comparison (this image minus {os.path.basename(a.baseline)}; changed = a channel differs by more than 8/255):")
        print(f"{'layer':<14}{'changed':>8}  {'d' + ligname:>7} {'d' + satname:>7} {'dL*':>7}")
        for n in names:
            m = (owner == order.index(n)) & v0
            if not m.any():
                continue
            ms = m & b_sat_ok
            dsat = f"{(sat[0][ms] - bch[sat_k][0][ms]).mean():+7.1f}" if ms.any() else f"{'n/a':>7}"
            print(f"{n:<14}{changed[m].mean()*100:7.1f}%  {(lig[0][m] - bch[lig_k][0][m]).mean():+7.1f} {dsat} {(lst[0][m] - bch['L*'][0][m]).mean():+7.1f}")
        print(f"{'(whole frame)':<14}{changed[v0].mean()*100:7.1f}%")
        b_cond = {"H": bch["H"], "S": bch["Sl"] if a.space == "hsl" else bch["Sb"], "V": bch["V"], "L": bch["L"], "L*": bch["L*"], "C": bch["C"]}
        b_bands = [bch[lig_k][0] >= thr100 - 1e-4, bch["L*"][0] >= lthr - 1e-3] + \
                  [eval_cond(parse_cond(s.split(":", 1)[1]), b_cond)[0] for s in a.band]
        print("band size and ownership, baseline -> this image:")
        for (bname, bm), bb in zip(bands, b_bands):
            bb = bb & v0
            now, was = bm[0], bb
            parts = []
            for n in names:
                m = (owner == order.index(n))
                p_now = (now & m).sum() / max(now.sum(), 1) * 100
                p_was = (was & m).sum() / max(was.sum(), 1) * 100
                parts.append(f"{n} {p_was:.0f}->{p_now:.0f}%")
            print(f"  {bname[:28]:<28} size {was.sum() / max(v0.sum(), 1) * 100:.2f}->{now.sum() / max(v0.sum(), 1) * 100:.2f}%   " + "  ".join(parts))
        dn = np.clip(diff * 4, 0, 1)
        Image.fromarray((np.stack([dn, dn * 0.5, 0.15 + 0 * dn], -1) * 255).astype(np.uint8)).save(os.path.join(a.out, "diff.png"))
        written.append("diff.png")

    # ---- diagnostic images (frame 0), saved before the chart
    f0 = rgb[0]
    img8 = Image.fromarray(np.round(f0 * 255).astype(np.uint8))
    Image.fromarray(np.round(grey[0] * 255).astype(np.uint8)).save(os.path.join(a.out, "gray.png"))
    img8.filter(ImageFilter.GaussianBlur(max(2, min(W, H) / 120))).save(os.path.join(a.out, "blur.png"))
    edges = [b for b in (0.2, 0.4, 0.6, 0.8) if b < thr] + [thr]
    base = np.array([[20, 20, 60], [60, 60, 130], [110, 130, 160], [190, 190, 150], [250, 220, 120]], np.uint8)[:len(edges)]
    idx = np.digitize(lig[0] / 100, edges)
    vb = np.vstack([base, [[255, 150, 0]]]).astype(np.uint8)[np.minimum(idx, len(edges))]
    vb[band_main[0] & band_l[0]] = (255, 40, 40)
    vb[~valid[0]] = (0, 0, 0)
    Image.fromarray(vb).save(os.path.join(a.out, "value_bands.png"))
    ov = f0 * 0.45
    for n in order:
        mk = owner == order.index(n)
        ov[mk] = ov[mk] * 0.6 + np.array(colour[n], np.float32) / 255 * 0.55
    Image.fromarray((np.clip(ov, 0, 1) * 255).astype(np.uint8)).save(os.path.join(a.out, "layers_overlay.png"))
    linf0 = srgb_lin(f0)
    for kind, mat in MACHADO.items():
        sim = srgb_enc(linf0 @ np.array(mat, np.float32).T)
        Image.fromarray(np.round(sim * 255).astype(np.uint8)).save(os.path.join(a.out, kind + ".png"))
    written += ["gray.png", "blur.png", "value_bands.png", "layers_overlay.png", "protan.png", "deutan.png"]
    if custom:
        bimg = np.repeat(grey[0][..., None], 3, -1) * 0.4
        for k, (bname, bm) in enumerate(custom):
            bimg[bm[0]] = np.array(PALETTE[(k + 2) % len(PALETTE)], np.float32) / 255
        Image.fromarray((np.clip(bimg, 0, 1) * 255).astype(np.uint8)).save(os.path.join(a.out, "bands.png"))
        written.append("bands.png")

    # ---- chart: saturation x lightness plane with one box per layer
    N, P, LW = 400, 60, 250
    chart = Image.new("RGB", (N + 2 * P + LW, N + 2 * P), "white")
    hist, _, _ = np.histogram2d((1 - lig[valid] / 100).ravel(), (sat[valid] / smax).ravel(), bins=N, range=[[0, 1], [0, 1]])
    dens = np.log1p(hist)
    dens = dens / max(float(dens.max()), 1e-6)
    if np.count_nonzero(hist) < 2000:  # few colours: grow the dots so they stay visible
        dens = np.asarray(Image.fromarray((dens * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) / 255.0
    chart.paste(Image.fromarray((255 - dens * 235).astype(np.uint8)).convert("RGB"), (P, P))
    d = ImageDraw.Draw(chart)
    fn, fs = font(16), font(13)
    d.rectangle([P - 1, P - 1, P + N, P + N], outline="black")
    ty = P + (1 - thr) * N
    d.line([P, ty, P + N, ty], fill=(200, 200, 200))
    for t in (0, .25, .5, .75, 1):
        d.text((P + t * N - 10, P + N + 6), f"{t * smax:.0f}", fill="black", font=fs)
        d.text((P - 32, P + (1 - t) * N - 8), f"{t * 100:.0f}", fill="black", font=fs)
    d.text((P + N / 2 - 90, P + N + 26), f"{satname} ({a.space}) ->", fill="black", font=fn)
    d.text((6, 18), f"{ligname} ({a.space}) ^      grey = all pixels (log density)", fill="black", font=fn)
    ly = P
    for i, n in enumerate(names):
        c = colour[n]
        es, el, _, _ = env[n]
        y0, y1 = P + (1 - el[-1] / 100) * N, P + (1 - el[0] / 100) * N
        x0, x1 = (P, P) if es is None else (P + min(es[0] / smax, 1) * N, P + min(es[-1] / smax, 1) * N)
        o = i * 2
        ox, oy = min(o, max((x1 - x0 - 6) / 2, 0)), min(o, max((y1 - y0 - 6) / 2, 0))
        x0, x1, y0, y1 = x0 + ox, x1 - ox, y0 + oy, y1 - oy
        if y1 - y0 < 6:
            y0, y1 = (y0 + y1) / 2 - 3, (y0 + y1) / 2 + 3
        if es is None:
            d.line([P, y0, P, y1], fill=c, width=4)
        else:
            if x1 - x0 < 6:
                x0, x1 = (x0 + x1) / 2 - 3, (x0 + x1) / 2 + 3
            d.rectangle([x0, y0, x1, y1], outline=c, width=3)
        d.rectangle([P + N + 20, ly, P + N + 36, ly + 16], fill=c)
        d.text((P + N + 42, ly - 2), n, fill="black", font=fn)
        stxt = f"{satname} n/a" if es is None else f"{satname} {es[0]:.0f}-{es[-1]:.0f}"
        d.text((P + N + 20, ly + 20), f"{stxt}  {ligname} {el[0]:.0f}-{el[-1]:.0f}", fill="black", font=fs)
        ly += 50
    chart.save(os.path.join(a.out, "sv_chart.png"))
    written.append("sv_chart.png")
    print(f"\nwrote {', '.join(written)} to {a.out}" + (" (images show the first pooled frame)" if F > 1 else ""))


if __name__ == "__main__":
    main()
