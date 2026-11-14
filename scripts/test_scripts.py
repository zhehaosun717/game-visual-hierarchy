"""Regression test for sv_profile.py and palette_check.py.

  python test_scripts.py        (Windows: py test_scripts.py)

Builds small inputs in a temp folder, runs both scripts and checks exit codes,
output files and key strings. Prints one PASS/FAIL line per case; exit code 1 if
any case fails. Run it after every change to the scripts.
"""
import os, re, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SV, PAL = os.path.join(HERE, "sv_profile.py"), os.path.join(HERE, "palette_check.py")
IMAGES = ["sv_chart.png", "value_bands.png", "gray.png", "blur.png", "layers_overlay.png", "protan.png", "deutan.png"]
results = []


def run(script, *args):
    p = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def case(name, script, args, code=0, has=(), lacks=(), files=(), outdir=None, check=None):
    rc, out, err = run(script, *args)
    text = out + err
    problems = []
    if rc != code:
        problems.append(f"exit {rc}, expected {code}")
    problems += [f"missing text {s!r}" for s in has if s not in text]
    problems += [f"unexpected text {s!r}" for s in lacks if s in text]
    problems += [f"missing file {f}" for f in files if not os.path.isfile(os.path.join(outdir, f))]
    if check and not problems:
        msg = check(out)
        if msg:
            problems.append(msg)
    results.append(not problems)
    print(("PASS  " if not problems else "FAIL  ") + name + ("" if not problems else "  <- " + "; ".join(problems)))
    if problems:
        print("      " + text.strip().replace("\n", "\n      ")[-900:])
    return out


def area_of(out, layer):
    m = re.search(r"^" + re.escape(layer) + r"\s+([\d.]+)%", out, re.M)
    return float(m.group(1)) if m else None


def main():
    with tempfile.TemporaryDirectory() as t:
        j = lambda *p: os.path.join(t, *p)
        # ---- inputs
        flat = Image.new("RGB", (64, 64), (0, 0, 0))
        d = ImageDraw.Draw(flat)
        d.rectangle([10, 10, 30, 30], fill=(255, 60, 40))
        d.rectangle([40, 40, 60, 60], fill=(250, 250, 250))
        flat.save(j("flat.png"))
        mid = Image.new("RGB", (64, 64), (60, 80, 70))
        ImageDraw.Draw(mid).rectangle([10, 10, 30, 30], fill=(200, 180, 60))
        mid.save(j("mid.png"))
        mid2 = mid.copy()
        ImageDraw.Draw(mid2).rectangle([40, 40, 60, 60], fill=(255, 255, 255))
        mid2.save(j("mid2.png"))
        Image.new("RGB", (8, 8), (90, 60, 30)).save(j("tiny.png"))
        frames = []
        for k in range(6):
            f = Image.new("RGB", (32, 32), (0, 0, 20))
            ImageDraw.Draw(f).rectangle([4 + 3 * k, 12, 8 + 3 * k, 16], fill=(255, 255, 255) if k == 3 else (255, 200, 0))
            frames.append(f)
        frames[0].save(j("led.gif"), save_all=True, append_images=frames[1:], duration=100, loop=0)
        spr = np.zeros((32, 32, 4), np.uint8)
        spr[..., :3] = (255, 0, 255)  # hidden colour under alpha 0
        spr[8:24, 8:24] = (40, 160, 90, 255)
        Image.fromarray(spr, "RGBA").save(j("sprite.png"))
        msk = np.zeros((64, 64, 4), np.uint8)
        msk[..., :3] = 255  # white everywhere, but only the square is opaque
        msk[0:32, 0:32, 3] = 255
        Image.fromarray(msk, "RGBA").save(j("mask.png"))
        Image.fromarray((np.linspace(0, 65535, 64 * 64).reshape(64, 64)).astype(np.uint16)).save(j("deep.png"))

        # ---- sv_profile
        o = j("o1")
        case("flat-colour layers on black (old crash); canvas has no measurable S", SV,
             [j("flat.png"), "-o", o, "-r", "!bg:0,0,1,1", "-r", "sprite:10,10,31,31", "-r", "fx:40,40,61,61"],
             has=["n/a", "saturated glow"], lacks=["Traceback"], files=IMAGES, outdir=o)
        o = j("o2")
        case("8x8 image, no layers", SV, [j("tiny.png"), "-o", o], has=["whole frame"], files=IMAGES, outdir=o)
        o = j("o3")
        case("GIF default frame warns about frames", SV, [j("led.gif"), "-o", o, "-r", "!bg:0,0,1,1"], has=["6 frames", "frame 0 only"], files=IMAGES, outdir=o)
        o = j("o4")
        case("GIF --frame all pools frames and reports motion", SV,
             [j("led.gif"), "-o", o, "--frame", "all", "-r", "!bg:0,0,1,1", "-r", "dot:0,12,32,17"],
             has=["pooling 6 frames", "motion", "by L*: max 2.4% at frame 3"], files=IMAGES + ["motion.png"], outdir=o)
        o = j("o5")
        case("RGBA sprite: transparent pixels excluded", SV, [j("sprite.png"), "-o", o],
             has=["fully transparent", "#28a05a"], lacks=["ff00ff"], files=IMAGES, outdir=o)
        o = j("o6")
        case("--top-band 0.7 does not crash", SV, [j("mid.png"), "-o", o, "-r", "!bg:0,0,1,1", "--top-band", "0.7"], has=["V >= 70"], files=IMAGES, outdir=o)
        o = j("o7")
        case("--top-band 90 and --min-v 15 read as percentages", SV, [j("mid.png"), "-o", o, "--top-band", "90", "--min-v", "15"],
             has=["V >= 90 ", "V >= 15)"], lacks=["9000"], files=IMAGES, outdir=o)
        o = j("o8")
        case("!layer keeps its own shape; rest is unassigned", SV,
             [j("mid.png"), "-o", o, "-r", "!left:0,0,0.5,1", "-r", "obj:10,10,31,31"], has=["(unassigned)"], files=IMAGES, outdir=o,
             check=lambda out: None if abs((area_of(out, "left") or 0) - (50 - 441 / 4096 * 100)) < 0.2 else f"left area {area_of(out, 'left')}")
        o = j("o9")
        case("--space hsl", SV, [j("mid.png"), "-o", o, "-r", "!bg:0,0,1,1", "-r", "obj:10,10,31,31", "--space", "hsl", "--pct", "5,50,90,95"],
             has=["space hsl", "L p5-50-90-95"], files=IMAGES, outdir=o)
        o = j("o10")
        case("--space lab", SV, [j("mid.png"), "-o", o, "--space", "lab"], has=["C* p5"], files=IMAGES, outdir=o)
        o = j("o11")
        case("--band with a hue range that wraps through 0", SV,
             [j("flat.png"), "-o", o, "-r", "!bg:0,0,1,1", "-r", "sprite:10,10,31,31", "--band", "enemy:H=330-20&S>=60"],
             has=["band ownership", "enemy:H=330-20&S>=60"], files=IMAGES + ["bands.png"], outdir=o,
             check=lambda out: None if re.search(r"enemy:H=330-20&S>=60\s+[\d.]+%\s+0\.0%\s+100\.0%", out) else "sprite should own 100% of the hue band")
        case("hue band without S>= is rejected", SV, [j("flat.png"), "-o", j("o12"), "--band", "x:H=330-20"], code=2, has=["S>="])
        o = j("o13")
        case("--baseline reports the difference", SV, [j("mid2.png"), "-o", o, "-r", "!bg:0,0,1,1", "-r", "obj:10,10,31,31", "--baseline", j("mid.png")],
             has=["baseline comparison", "(whole frame)"], files=IMAGES + ["diff.png"], outdir=o)
        o = j("o14")
        case("--display-gamma 1 (linear LED)", SV, [j("led.gif"), "-o", o, "--display-gamma", "1"], has=["display gamma 1"], files=IMAGES, outdir=o)
        o = j("o15")
        case("mask: transparent white background is not part of the layer", SV,
             [j("mid.png"), "-o", o, "-r", "!bg:0,0,1,1", "-m", "obj:" + j("mask.png")], files=IMAGES, outdir=o,
             check=lambda out: None if abs((area_of(out, "obj") or 0) - 25.0) < 0.2 else f"obj area {area_of(out, 'obj')}")
        o = j("o16")
        case("Chinese layer names survive the pipe", SV, [j("mid.png"), "-o", o, "-r", "!地面:0,0,1,1", "-r", "敌人:10,10,31,31"], has=["地面", "敌人"], files=IMAGES, outdir=o)
        o = j("o17")
        case("swapped rectangle corners and --crop with fractions", SV,
             [j("mid.png"), "-o", o, "-r", "!bg:0,0,1,1", "-r", "obj:31,31,10,10", "--crop", "0,0,0.75,0.75"], has=["image 48x48"], files=IMAGES, outdir=o,
             check=lambda out: None if abs((area_of(out, "obj") or 0) - 441 / 2304 * 100) < 0.2 else f"obj area {area_of(out, 'obj')}")
        case("odd polygon coordinates are an error", SV, [j("mid.png"), "-o", j("o18"), "-p", "x:1,2,3,4,5"], code=2, has=["polygon"])
        case("empty canvas layer is an error", SV, [j("mid.png"), "-o", j("o19"), "-r", "bg:0,0,10,10", "-r", "top:0,0,1,1"], code=2, has=["canvas"])
        o = j("o20")
        case("16-bit greyscale image", SV, [j("deep.png"), "-o", o], files=IMAGES, outdir=o,
             check=lambda out: None if re.search(r"whole frame\s+100\.0%.*?\s(\d+)-(\d+)-(9\d|100)\s", out) else "lightness should span up to ~95")

        # ---- palette_check
        pal = "﻿# 注释\n; also a comment\n// and this\n#3a4d3c 地面/草 主色\n#485c47 地面/草\n#586b52 地面/草\n#6b6b70 地面/石\n" \
              "#8c7e66 路径\n#120a12 敌人 描边\n#D8443C 敌人\n#fff6e0 特效 内核\n#ffd85a 特效\n"
        open(j("pal.txt"), "w", encoding="utf-8").write(pal)
        open(j("bad.txt"), "w", encoding="utf-8").write("#3a4d3c ground\nnot a colour line\n")
        open(j("dup.txt"), "w", encoding="utf-8").write("#3a4d3c ground\n#3a4d3c fx\n#e63c32 ground flower\n")
        case("palette: BOM, comments, ramps, Chinese layers", PAL, [j("pal.txt"), "-o", j("sub", "dir", "sw.png")],
             has=["9 colours, 4 layers", "地面/草", "ramp step", "not a ramp step", "contrast against"], files=["sw.png"], outdir=j("sub", "dir"))
        case("palette: hue reserve holds", PAL, [j("pal.txt"), "--reserve", "H=330-20&S>=60:敌人", "--reserve", "V>=90:特效"], has=["OK"], lacks=["VIOLATED"])
        case("palette: hue reserve violated -> exit 1", PAL, [j("dup.txt"), "--reserve", "H=330-20&S>=60:fx"], code=1, has=["VIOLATED", "#e63c32", "more than once"])
        case("palette: unknown layer -> exit 2", PAL, [j("pal.txt"), "--reserve", "V>=90:vfx"], code=2, has=["unknown layer"])
        case("palette: unparsable line -> exit 2", PAL, [j("bad.txt")], code=2, has=["line 2"])
        case("palette: 0-1 threshold and empty band are flagged", PAL, [j("pal.txt"), "--reserve", "L*>=99.9:特效", "--reserve", "V>=0.9:特效"],
             code=1, has=["proves nothing", "written 0-100"])
        case("palette: --display-gamma", PAL, [j("pal.txt"), "--display-gamma", "1"], has=["display gamma 1"])

    ok = sum(results)
    print(f"\n{ok}/{len(results)} passed")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
