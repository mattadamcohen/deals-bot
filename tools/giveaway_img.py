"""Giveaway reminder image in the banner style: python tools/giveaway_img.py [palette] -> out/giveaway_banner.png"""
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from promo_styles import T, heb, anton, brush, pill, shadow_paste, OUT
from ig_promo import PALETTES

W, H = 1080, 1350


def gift(size, box, ribbon):
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    s = size
    d.rounded_rectangle([s * .08, s * .42, s * .92, s * .96], radius=int(s * .05), fill=box + (255,), outline=(10, 10, 10, 255), width=6)
    d.rounded_rectangle([s * .02, s * .28, s * .98, s * .46], radius=int(s * .04), fill=box + (255,), outline=(10, 10, 10, 255), width=6)
    d.rectangle([s * .43, s * .28, s * .57, s * .96], fill=ribbon + (255,), outline=(10, 10, 10, 255), width=5)
    d.ellipse([s * .18, s * .06, s * .5, s * .32], outline=ribbon + (255,), width=int(s * .07))
    d.ellipse([s * .5, s * .06, s * .82, s * .32], outline=ribbon + (255,), width=int(s * .07))
    return g


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "black-yellow"
    BY = dict(name="black-yellow", bg1=(28, 28, 32), bg2=(0, 0, 0), dark=(10, 10, 10), strip=(230, 20, 35),
              hot=(230, 20, 35), gold=(255, 210, 0), l2=(230, 20, 35), banner=(255, 210, 0), l1=(10, 10, 10),
              pill=(230, 20, 35), cta=(255, 210, 0), cta1=(10, 10, 10), cta2=(230, 20, 35), sign=(255, 210, 0))
    pal = BY if name == "black-yellow" else next(p for p in PALETTES if p["name"] == name)
    DK, HOT = pal["dark"], pal["hot"]
    im = Image.new("RGBA", (W, H))
    g = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        g.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(pal["bg1"], pal["bg2"])) + (255,))
    rnd = random.Random(3)
    for _ in range(30):
        c = Image.new("RGBA", (40, 22), (0, 0, 0, 0))
        ImageDraw.Draw(c).rectangle([0, 0, 39, 21], fill=rnd.choice([HOT, DK, (255, 255, 255), pal["gold"]]) + (255,))
        im.alpha_composite(c.rotate(rnd.randint(0, 180), expand=True), (rnd.randint(0, W - 40), rnd.randint(0, H - 40)))
    for px in (70, W - 110):
        g.rectangle([px, 30, px + 40, 800], fill=pal.get("banner", DK))
    # title banner
    bh = 300
    b = brush(940, bh, pal.get("banner", DK), 2)
    lay = Image.new("RGBA", b.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.text((470, bh * .3), "$50 AMAZON", font=anton(132), fill=pal.get("l1", (255, 255, 255)), anchor="mm")
    ld.text((500, bh * .74), "GIVEAWAY", font=anton(150), fill=pal["l2"], anchor="mm")
    lay = lay.transform(lay.size, Image.AFFINE, (1, 0.22, -32, 0, 1, 0), resample=Image.BICUBIC)
    b.alpha_composite(lay)
    shadow_paste(im, b.rotate(-2, expand=True, resample=Image.BICUBIC), (60, 25), alpha=140)
    # strip
    r = brush(980, 150, pal["strip"], 3, jag=18)
    r.alpha_composite(brush(840, 95, DK, 5, jag=12), (70, 27))
    T(ImageDraw.Draw(r), (490, 75), "הגרלה בערוץ הדילים 🎁".replace(" 🎁", ""), heb(900, 62), (255, 255, 255))
    shadow_paste(im, r.rotate(1.5, expand=True, resample=Image.BICUBIC), (40, 320), alpha=140)
    # white sign
    wh = 330
    wb = Image.new("RGBA", (920, wh), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wb)
    wd.rectangle([0, 0, 919, wh - 1], fill=(250, 250, 248))
    T(wd, (460, 68), "כל חבר/ה שמצטרף/ת דרככם", heb(900, 62), DK)
    T(wd, (460, 175), "= עוד כניסה!", heb(900, 120), HOT)
    sub = brush(820, 78, DK, 9, jag=10)
    T(ImageDraw.Draw(sub), (410, 39), "עד 11 כניסות · ההגרלה ב-1.12 ", heb(900, 44), (255, 255, 255))
    wb.alpha_composite(sub, (50, wh - 92))
    shadow_paste(im, wb.rotate(-1, expand=True, resample=Image.BICUBIC), (70, 485), alpha=150)
    # steps + gifts
    shadow_paste(im, gift(230, HOT, pal["gold"]).rotate(10, expand=True, resample=Image.BICUBIC), (20, 870), alpha=120)
    shadow_paste(im, gift(200, pal["gold"], HOT).rotate(-12, expand=True, resample=Image.BICUBIC), (835, 905), alpha=120)
    for i, s in enumerate(["לוחצים על הכפתור בפוסט", "מקבלים קישור אישי", "שולחים לחברים וצוברים כניסות"]):
        pill(im, W / 2 + (0 if i != 1 else 10), 880 + i * 92, s, heb(900, 46), (255, 255, 255), pal.get("pill", DK), padx=40, outline=(255, 255, 255))
    bar = brush(1000, 140, pal.get("cta", DK), 11, jag=14)
    bd = ImageDraw.Draw(bar)
    T(bd, (500, 50), "אתם כבר בפנים? תתחילו להזמין", heb(900, 52), pal.get("cta1", (255, 255, 255)))
    T(bd, (500, 105), "@ilamazondeals  ·  israelideals.com", heb(800, 38), pal.get("cta2", pal["gold"]))
    shadow_paste(im, bar, (40, 1185), alpha=140)
    OUT.mkdir(exist_ok=True)
    p = OUT / "giveaway_banner.png"
    im.convert("RGB").save(p)
    print(p)


if __name__ == "__main__":
    main()
