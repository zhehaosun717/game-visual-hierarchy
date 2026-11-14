"""Check a layered palette before anything is drawn: envelopes per layer, free
space around the canvas, ramp steps, contrast against the canvas, reserved bands.
Pillow only. On Windows run with `py`.

  python palette_check.py palette.txt -o swatches.png --reserve "V>=90:fx" --reserve "H=330-20&S>=60:enemy"

PALETTE FILE (UTF-8), one colour per line:   #hex  layer[/ramp]  free note
    #3a4d3c  ground/grass   main ground
    #8c7e66  path
    #120a12  enemy          outline
    #fff6e0  fx             impact core
  The first layer is the canvas; layers keep their order of first appearance.
  "layer/ramp" groups colours of one ramp, so steps are measured inside the ramp.
  Blank lines and lines starting with "# " (hash + space), ";" or "//" are comments.

OPTIONS
  --reserve "COND:layer,layer"   colours matching COND may only belong to the named
        layers (an exclusive band with one meaning). COND = terms joined by &:
        X>=n, X<=n with X in H S V L L* C (0-100, H in degrees), or H=a-b (wraps
        through 0, e.g. H=330-20). A hue term needs an S>= or C>= term.
        S and V are HSB, L is HSL lightness, L* is CIELAB lightness (what a
        greyscale test shows), C is CIELAB chroma.
  --display-gamma G    the code values drive a display with gamma G (1 = raw linear
        LED panel); measure what an sRGB monitor would have to show instead
  -o FILE.png          swatch sheet by layer; the strip under each row simulates
        red-blind (protan) vision

REPORT
  per layer: S, V and L* ranges; the closest pair inside each ramp (in L*, with the
  V difference); free space below / above the canvas; how far each layer reaches
  beyond the canvas; contrast ratio (WCAG formula) of each layer's darkest and
  lightest colour against the least favourable canvas colour.
EXIT CODE  0 ok, 1 a reserve is violated, 2 cannot parse the file or the arguments.
"""
import argparse, os, re, sys
from PIL import Image, ImageDraw, ImageFont

PROTAN = [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]


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


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def enc(l):
    l = min(max(l, 0.0), 1.0)
    return 12.92 * l if l <= 0.0031308 else 1.055 * l ** (1 / 2.4) - 0.055


def lab_f(t):
    return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29


def channels(rgb):
    """rgb 0-1 floats -> dict H (deg), S, V (HSB), L (HSL), L*, C (CIELAB), Y."""
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / d) % 6 * 60
    elif mx == g:
        h = ((b - r) / d + 2) * 60
    else:
        h = ((r - g) / d + 4) * 60
    rl, gl, bl = lin(r), lin(g), lin(b)
    x = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
    y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl
    fx, fy, fz = lab_f(x / 0.95047), lab_f(y), lab_f(z / 1.08883)
    return {"H": h, "S": (d / mx if mx else 0.0) * 100, "V": mx * 100, "L": (mx + mn) / 2 * 100,
            "L*": 116 * fy - 16, "C": ((500 * (fx - fy)) ** 2 + (200 * (fy - fz)) ** 2) ** 0.5, "Y": y}


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


def match(terms, ch):
    for t in terms:
        x = ch[t[0]]
        if t[1] == "range":
            ok = (t[2] <= x <= t[3]) if t[2] <= t[3] else (x >= t[2] or x <= t[3])
        else:
            ok = x >= t[2] if t[1] == ">=" else x <= t[2]
        if not ok:
            return False
    return True


def contrast(y1, y2):
    hi, lo = max(y1, y2), min(y1, y2)
    return (hi + 0.05) / (lo + 0.05)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("palette")
    ap.add_argument("-o", "--out")
    ap.add_argument("--reserve", action="append", default=[], help='"COND:layer,layer"')
    ap.add_argument("--display-gamma", type=float)
    a = ap.parse_args()
    if a.display_gamma is not None and a.display_gamma <= 0:
        fail("--display-gamma must be > 0")

    try:
        lines = open(a.palette, encoding="utf-8-sig").read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        fail(f"cannot read {a.palette!r}: {e}")
    rows = []
    for no, raw in enumerate(lines, 1):
        ln = raw.strip()
        if not ln or ln == "#" or ln.startswith("# ") or ln.startswith(";") or ln.startswith("//"):
            continue
        m = re.match(r"#?([0-9a-fA-F]{6})\s+(\S+)\s*(.*)$", ln)
        if not m:
            fail(f"line {no}: cannot parse {raw!r} (expected: #hex layer[/ramp] note; comments start with '# ', ';' or '//')")
        hx, tag, note = m.groups()
        layer, _, ramp = tag.partition("/")
        if not layer:
            fail(f"line {no}: empty layer name in {raw!r}")
        rgb = tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
        shown = tuple(enc(c ** a.display_gamma) for c in rgb) if a.display_gamma is not None else rgb
        rows.append(dict(hex="#" + hx.lower(), rgb=rgb, shown=shown, layer=layer, ramp=ramp, note=note, **channels(shown)))
    if not rows:
        fail(f"{a.palette!r} contains no colours")
    layers = list(dict.fromkeys(r["layer"] for r in rows))
    seen = {}
    for r in rows:
        if r["hex"] in seen:
            warn(f"{r['hex']} appears more than once ({seen[r['hex']]} and {r['layer']})")
        seen.setdefault(r["hex"], r["layer"])

    print(f"{len(rows)} colours, {len(layers)} layers (canvas = '{layers[0]}'); S and V are HSB, L* is CIELAB lightness")
    if a.display_gamma is not None:
        print(f"display gamma {a.display_gamma:g}: values are what an sRGB monitor would need to show to match the panel")
    print(f"{'layer':<14}{'n':>3}  {'S min-max':>10}  {'V min-max':>10}  {'L* min-max':>10}")
    by = {L: [r for r in rows if r["layer"] == L] for L in layers}
    env = {}
    for L in layers:
        cs = by[L]
        rng = lambda k: (min(r[k] for r in cs), max(r[k] for r in cs))
        env[L] = {k: rng(k) for k in ("S", "V", "L*", "Y")}
        e = env[L]
        print(f"{L:<14}{len(cs):>3}  {e['S'][0]:4.0f}-{e['S'][1]:<4.0f}   {e['V'][0]:4.0f}-{e['V'][1]:<4.0f}   {e['L*'][0]:4.0f}-{e['L*'][1]:<4.0f}")

    print("\nclosest pair of colours (dL* = difference in perceived lightness; dV shown for reference):")
    for L in layers:
        groups = {}
        for r in by[L]:
            groups.setdefault(r["ramp"], []).append(r)
        for ramp, cs in groups.items():
            label = f"{L}/{ramp}" if ramp else L
            kind = "ramp step" if ramp else "min L* gap between any two colours in the layer (not a ramp step)"
            if len(cs) < 2:
                print(f"  {label:<20} single colour")
                continue
            cs = sorted(cs, key=lambda r: r["L*"])
            x, y = min(zip(cs, cs[1:]), key=lambda p: p[1]["L*"] - p[0]["L*"])
            print(f"  {label:<20} {kind}: dL* {y['L*'] - x['L*']:4.1f} (dV {abs(y['V'] - x['V']):4.1f})  {x['hex']} ~ {y['hex']}")

    c = env[layers[0]]
    allv, alll = [r["V"] for r in rows], [r["L*"] for r in rows]
    print(f"\ncanvas '{layers[0]}': V {c['V'][0]:.0f}-{c['V'][1]:.0f}, L* {c['L*'][0]:.0f}-{c['L*'][1]:.0f}. "
          f"Free below: V {c['V'][0] - min(allv):.0f}, L* {c['L*'][0] - min(alll):.0f}. "
          f"Free above: V {max(allv) - c['V'][1]:.0f}, L* {max(alll) - c['L*'][1]:.0f}.")
    if len(layers) > 1:
        print("reach beyond the canvas (+ = range the canvas leaves free):")
        for L in layers[1:]:
            e = env[L]
            print(f"  {L:<14} brighter {e['V'][1] - c['V'][1]:+4.0f} (L* {e['L*'][1] - c['L*'][1]:+4.0f})   "
                  f"darker {c['V'][0] - e['V'][0]:+4.0f} (L* {c['L*'][0] - e['L*'][0]:+4.0f})   more saturated {e['S'][1] - c['S'][1]:+4.0f}")
        print("contrast against the least favourable canvas colour (WCAG ratio; 3:1 is a common floor for large gameplay elements):")
        canv = by[layers[0]]
        for L in layers[1:]:
            dark, light = min(by[L], key=lambda r: r["Y"]), max(by[L], key=lambda r: r["Y"])
            wd = min(canv, key=lambda k: contrast(dark["Y"], k["Y"]))
            wl = min(canv, key=lambda k: contrast(light["Y"], k["Y"]))
            both = min(max(contrast(dark["Y"], k["Y"]), contrast(light["Y"], k["Y"])) for k in canv)
            print(f"  {L:<14} darkest {dark['hex']} {contrast(dark['Y'], wd['Y']):4.1f}:1 (vs {wd['hex']})   "
                  f"lightest {light['hex']} {contrast(light['Y'], wl['Y']):4.1f}:1 (vs {wl['hex']})   dark+light pair, worst case {both:4.1f}:1")

    bad = 0
    for spec in a.reserve:
        if ":" not in spec:
            fail(f"--reserve {spec!r}: expected COND:layer[,layer]")
        cond, _, own = spec.rpartition(":")
        owners = {t.strip() for t in own.split(",") if t.strip()}
        unknown = sorted(o for o in owners if o not in layers)
        if unknown or not owners:
            fail(f"--reserve {spec!r}: unknown layer(s) {unknown}; the palette has {layers}")
        terms = parse_cond(cond)
        if any(t[0] != "H" and t[1] != "range" and 0 < t[2] <= 1 for t in terms):
            warn(f"--reserve {spec!r}: thresholds are written 0-100, not 0-1")
        hit = [r for r in rows if match(terms, r)]
        intruders = [r for r in hit if r["layer"] not in owners]
        print(f"\nreserve {cond} for {sorted(owners)}: {len(hit)} colour(s) in the band, " + ("OK" if not intruders else "VIOLATED"))
        if not hit:
            warn("no colour matches this condition, so the check proves nothing")
        for r in intruders:
            print(f"  {r['hex']} layer={r['layer']} H{r['H']:.0f} S{r['S']:.0f} V{r['V']:.0f} L*{r['L*']:.0f} {r['note']}")
        bad += len(intruders)

    if a.out:
        parent = os.path.dirname(os.path.abspath(a.out))
        os.makedirs(parent, exist_ok=True)
        sw, pad, strip, fs = 56, 8, 14, font(12)
        width = 160 + max(len(by[L]) for L in layers) * (sw + pad)
        rowh = sw + strip + 22
        im = Image.new("RGB", (width, len(layers) * rowh + pad + 18), "white")
        d = ImageDraw.Draw(im)
        to8 = lambda t: tuple(int(round(min(max(v, 0), 1) * 255)) for v in t)
        for i, L in enumerate(layers):
            y = pad + i * rowh
            d.text((8, y + sw / 2 - 8), L, fill="black", font=font(15))
            for j, r in enumerate(by[L]):
                x = 160 + j * (sw + pad)
                l3 = [lin(v) for v in r["shown"]]
                sim = tuple(enc(sum(m * v for m, v in zip(row, l3))) for row in PROTAN)
                d.rectangle([x, y, x + sw, y + sw], fill=to8(r["shown"]), outline=(160, 160, 160))
                d.rectangle([x, y + sw, x + sw, y + sw + strip], fill=to8(sim), outline=(160, 160, 160))
                d.text((x, y + sw + strip + 2), f"V{r['V']:.0f} L*{r['L*']:.0f}", fill="black", font=fs)
        d.text((8, len(layers) * rowh + pad), "strip under each swatch: red-blind (protan) simulation", fill=(90, 90, 90), font=fs)
        im.save(a.out)
        print(f"\nwrote {a.out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
