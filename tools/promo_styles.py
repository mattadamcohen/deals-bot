"""Black Friday story drafts in 3 styles (1080x1920):
  python tools/promo_styles.py -> out/bf_neon.png, out/bf_collage.png, out/bf_banner.png
"""
import json
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "data/images"
OUT = REPO / "out"
FD = REPO / "assets/fonts"
W, H = 1080, 1920
RATE = json.loads((REPO / "data/fx.json").read_text()).get("rate", 3.35)


def heb(w, s):
    from PIL import ImageFont
    return ImageFont.truetype(str(FD / f"Heebo-{w}.ttf"), s)


def anton(s):
    from PIL import ImageFont
    return ImageFont.truetype(str(FD / "Anton-400.ttf"), s)


def ils(usd):
    return f"₪{round(usd * RATE)}"


def T(d, xy, txt, font, fill, anchor="mm", **kw):
    rtl = any("֐" <= c <= "׿" for c in txt)
    d.text(xy, txt, font=font, fill=fill, anchor=anchor, direction="rtl" if rtl else None, **kw)


def glow_text(im, xy, txt, font, color, core=(255, 255, 255), blur=(30,), anchor="mm"):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    T(d, xy, txt, font, color + (200,), anchor, stroke_width=4, stroke_fill=color + (200,))
    for r in blur:
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(r)))
    d2 = ImageDraw.Draw(im)
    T(d2, xy, txt, font, color, anchor, stroke_width=7, stroke_fill=color)
    T(d2, xy, txt, font, core, anchor)


def glow_line(im, p1, p2, color, w=10):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.line([p1, p2], fill=color + (255,), width=w + 10)
    im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.line([p1, p2], fill=color, width=w)
    d.line([p1, p2], fill=(255, 255, 255), width=max(2, w // 3))


def card(path, w, h, radius=36, pad=18, bg=(255, 255, 255), fit="cover"):
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(c).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=bg + (255,))
    p = Image.open(path).convert("RGB")
    # cover-crop for photo feel, then round
    s = (max if fit == "cover" else min)((w - 2 * pad) / p.width, (h - 2 * pad) / p.height)
    p = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
    if fit != "cover":
        bgim = Image.new("RGB", (w - 2 * pad, h - 2 * pad), p.getpixel((2, 2)))
        bgim.paste(p, ((bgim.width - p.width) // 2, (bgim.height - p.height) // 2))
        p = bgim
    l, t = (p.width - (w - 2 * pad)) // 2, (p.height - (h - 2 * pad)) // 2
    p = p.crop((l, t, l + w - 2 * pad, t + h - 2 * pad))
    m = Image.new("L", p.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, p.width - 1, p.height - 1], radius=radius - 10, fill=255)
    c.paste(p, (pad, pad), m)
    return c


def shadow_paste(im, c, xy, blur=22, off=(0, 14), alpha=150, color=(0, 0, 0)):
    sh = Image.new("RGBA", (c.width + 120, c.height + 120), (0, 0, 0, 0))
    a = c.split()[3].point(lambda v: v * alpha // 255)
    sh.paste(Image.new("RGBA", c.size, color + (255,)), (60, 60), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    im.alpha_composite(sh, (xy[0] - 60 + off[0], xy[1] - 60 + off[1]))
    im.alpha_composite(c, xy)


def pill(im, cx, cy, txt, font, fg, bg, padx=40, h=None, outline=None, rot=0):
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), txt, font=font, direction="rtl" if any("֐" <= ch <= "׿" for ch in txt) else None)
    tw = bb[2] - bb[0]
    h = h or int(font.size * 1.55)
    b = Image.new("RGBA", (tw + 2 * padx + 8, h + 8), (0, 0, 0, 0))
    bd = ImageDraw.Draw(b)
    bd.rounded_rectangle([4, 4, tw + 2 * padx + 3, h + 3], radius=h // 2, fill=bg + (255,),
                         outline=(outline + (255,)) if outline else None, width=5 if outline else 0)
    T(bd, ((tw + 2 * padx + 8) / 2, (h + 8) / 2), txt, font, fg)
    if rot:
        b = b.rotate(rot, expand=True, resample=Image.BICUBIC)
    shadow_paste(im, b, (int(cx - b.width / 2), int(cy - b.height / 2)), blur=12, off=(0, 8), alpha=120)


P = {
    "controller": ("ali-1005009157516970.jpg", "בקר 8BitDo", 27.22),
    "projector": ("ali-1005011752099805.jpg", "מקרן HY300", 59.05),
    "headset": ("ali-1005006860959251.jpg", "אוזניות גיימינג", 35.81),
    "f1": ("ali-1005012649943924.jpg", "מכונית F1 לבנייה", 57.29),
    "lights": ("ali-1005013277989107.jpg", "עץ אורות לד", 28.89),
    "dumpling": ("ali-1005012925166688.jpg", "כופתאות סקווישי", 2.42),
    "needoh": ("ali-1005013212982440.jpg", "NeeDoh", 3.61),
    "cubes": ("ali-1005009449232221.jpg", "ארגוניות למזוודה", 5.58),
    "screw": ("ali-1005010088935712.jpg", "סט מברגים 25 ב-1", 6.97),
    "stand": ("ali-1005007476830338.jpg", "מעמד לבקרים", 9.44),
    "belt": ("ali-1005007146966040.jpg", "חגורת עור", 7.16),
    "puma": ("B0CL7L523F.jpg", "PUMA", 41.79),
    "skechers": ("B0BJ291V2G.jpg", "Skechers", 57.32),
    "owala": ("B0FFTLNC5S.jpg", "Owala", 22.79),
    "laneige": ("B0B9HPYZJH.jpg", "LANEIGE", 18.40),
    "olight": ("B0C54ZH8WW.jpg", "פנס OLIGHT", 11.99),
    "keyboard": ("ali-1005007345135328.jpg", "מקלדת GMK87", 54.59),
    "fan": ("ali-1005007628433434.jpg", "מנורה עם מאוורר", 11.36),
}


def img(k):
    return IMG / P[k][0]


# ---------------------------------------------------------------- 1. neon
def neon(tag="אירוע הדילים הכי גדול של השנה!", l1="BLACK", l2="FRIDAY", sub="בערוץ הדילים",
         keys=("headset", "controller", "f1"), cta1="מאות דילים חדשים כל יום",
         cta2="מאמזון ואליאקספרס · נבחרים בשבילכם", big=250):
    im = Image.new("RGBA", (W, H))
    g = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        g.line([(0, y), (W, y)], fill=(int(18 + 30 * t), int(8 + 4 * t), int(40 + 30 * (1 - t)), 255))
    # vignette spot
    spot = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(spot).ellipse([-200, 380, W + 200, 1500], fill=(70, 20, 140, 120))
    im.alpha_composite(spot.filter(ImageFilter.GaussianBlur(160)))
    random.seed(4)
    PINK, CYAN, LIME, YEL = (255, 60, 200), (40, 220, 255), (90, 255, 120), (255, 225, 60)
    for (x, y, ang, L, c) in [(40, 120, -25, 150, CYAN), (900, 90, 20, 140, PINK), (30, 760, 20, 120, PINK),
                              (960, 700, -25, 110, CYAN), (20, 1560, -30, 140, CYAN), (930, 1600, 30, 130, PINK),
                              (880, 1180, -20, 90, LIME), (60, 1150, 15, 90, YEL)]:
        a = math.radians(ang)
        glow_line(im, (x, y), (x + L * math.cos(a), y + L * math.sin(a)), c, 9)
    # tag line on white tape
    pill(im, W / 2, 175, tag, heb(800, 46), (20, 10, 40), (255, 255, 255), rot=4)
    glow_text(im, (W / 2, 360), l1, anton(big), PINK)
    glow_text(im, (W / 2, 590), l2, anton(big), CYAN)
    glow_text(im, (W / 2, 770), sub, heb(900, 92 if len(sub) < 16 else 68), YEL, core=(255, 250, 220))
    # three product cards with neon frames
    cw, chh = 300, 360
    xs = [W / 2 - cw - 40, W / 2, W / 2 + cw + 40]
    for i, (k, col) in enumerate(zip(list(keys), [CYAN, PINK, LIME])):
        cx, top = xs[i], 900 + (0 if i == 1 else 50)
        c = card(img(k), cw, chh, radius=34, pad=12, fit="contain")
        fr = Image.new("RGBA", (cw + 80, chh + 80), (0, 0, 0, 0))
        ImageDraw.Draw(fr).rounded_rectangle([40, 40, cw + 39, chh + 39], radius=38, outline=col + (255,), width=14)
        im.alpha_composite(fr.filter(ImageFilter.GaussianBlur(16)), (int(cx - cw / 2 - 40), top - 40))
        im.alpha_composite(c, (int(cx - cw / 2), top))
        ImageDraw.Draw(im).rounded_rectangle([cx - cw / 2, top, cx + cw / 2, top + chh], radius=34, outline=col, width=5)
        pill(im, cx, top + chh + 10, ils(P[k][2]), heb(900, 58), (255, 255, 255), (230, 30, 150), padx=30, outline=(255, 255, 255))
        T(ImageDraw.Draw(im), (cx, top + chh + 90), P[k][1], heb(800, 38), (255, 255, 255))
    # neon CTA box
    bx = (70, 1500, W - 70, 1680)
    fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(fr).rounded_rectangle(bx, radius=90, outline=LIME + (255,), width=18)
    im.alpha_composite(fr.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(bx, radius=90, fill=(10, 6, 20), outline=LIME, width=7)
    T(d, (W / 2, 1560), cta1, heb(900, 60), (255, 255, 255))
    T(d, (W / 2, 1632), cta2, heb(700, 38), (200, 255, 210))
    pill(im, W / 2, 1790, "@ilamazondeals  ·  israelideals.com", heb(800, 44), (20, 10, 40), YEL, padx=44)
    return im


# ---------------------------------------------------------------- 2. collage
def collage():
    TEAL = (24, 96, 112)
    im = Image.new("RGBA", (W, H), TEAL + (255,))
    g = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        g.line([(0, y), (W, y)], fill=(int(20 + 14 * t), int(104 - 30 * t), int(122 - 30 * t), 255))
    # header like a story: logo + name
    logo = Image.open(REPO / "assets/ilamazondeals-logo.png").convert("RGBA").resize((110, 110))
    m = Image.new("L", (110, 110), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 109, 109], fill=255)
    im.paste(logo, (W - 70 - 110, 110), m)
    T(g, (W - 210, 165), "ilamazondeals", heb(800, 50), (255, 255, 255), anchor="rm")
    T(g, (W / 2, 330), "BLACK FRIDAY", anton(150), (255, 255, 255))
    T(g, (W / 2, 450), "הלהיטים של השבוע בערוץ", heb(900, 64), (255, 214, 90))
    keys = ["projector", "f1", "lights", "controller", "headset", "dumpling"]
    cw, chh, gap = 470, 380, 30
    x0 = (W - 2 * cw - gap) // 2
    for i, k in enumerate(keys):
        x, y = x0 + (i % 2) * (cw + gap), 520 + (i // 2) * (chh + gap)
        shadow_paste(im, card(img(k), cw, chh, radius=40, pad=0), (x, y), alpha=110)
        pill(im, x + cw - 90, y + chh - 50, ils(P[k][2]), heb(900, 50), (255, 255, 255), (238, 40, 60), padx=24)
    pill(im, W / 2, 1815, "🔗  לכל הדילים: israelideals.com".replace("🔗  ", ""), heb(900, 58), (20, 20, 20), (255, 255, 255), padx=60)
    return im


# ---------------------------------------------------------------- 3. banner
def brush(w, h, color, seed=1, jag=26):
    random.seed(seed)
    b = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    pts = []
    for x in range(0, w + 1, 18):
        pts.append((x + random.randint(-6, 6), random.randint(0, jag)))
    for x in range(w, -1, -18):
        pts.append((x + random.randint(-6, 6), h - random.randint(0, jag)))
    d.polygon(pts, fill=color + (255,))
    for _ in range(30):  # dry-brush streaks at the ends
        y = random.randint(jag, h - jag)
        L = random.randint(20, 70)
        side = random.choice([0, 1])
        x = -L if side == 0 else w
        d.line([(max(0, x + (L if side == 0 else 0)) if False else (0 if side == 0 else w - L), y),
                (L if side == 0 else w, y)], fill=(0, 0, 0, 0), width=random.randint(2, 5))
    return b


def banner(l1="BLACK", l2="FRIDAY", strip="כבר הגיע לערוץ הדילים", w1="דילים מתחת ל-", w2="₪35",
           w3="על מאות מוצרים", keys=("dumpling", "screw", "cubes"), w2size=230, l2color=(235, 25, 35)):
    im = Image.new("RGBA", (W, H))
    g = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        g.line([(0, y), (W, y)], fill=(int(110 + 120 * t), int(190 - 20 * t), int(250 - 120 * t), 255))
    # confetti
    random.seed(7)
    for _ in range(40):
        x, y = random.randint(0, W), random.randint(0, H)
        c = Image.new("RGBA", (40, 22), (0, 0, 0, 0))
        ImageDraw.Draw(c).rectangle([0, 0, 39, 21], fill=random.choice([(230, 20, 30), (255, 255, 255), (20, 20, 20)]) + (255,))
        c = c.rotate(random.randint(0, 180), expand=True)
        im.alpha_composite(c, (x, y))
    # wooden poles
    for px in (70, W - 110):
        g.rectangle([px, 60, px + 40, 1180], fill=(120, 80, 45))
        g.rectangle([px + 8, 60, px + 16, 1180], fill=(150, 105, 65))
    # black banner with BLACK FRIDAY
    b = brush(940, 380, (15, 15, 15), 2)
    bd = ImageDraw.Draw(b)
    lay = Image.new("RGBA", b.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.text((470, 120), l1, font=anton(190), fill=(255, 255, 255), anchor="mm")
    ld.text((500, 280), l2, font=anton(190), fill=l2color, anchor="mm")
    lay = lay.transform(lay.size, Image.AFFINE, (1, 0.22, -40, 0, 1, 0), resample=Image.BICUBIC)
    b.alpha_composite(lay)
    shadow_paste(im, b.rotate(-2, expand=True, resample=Image.BICUBIC), (60, 120), alpha=140)
    # red strip
    r = brush(980, 190, (220, 25, 35), 3, jag=18)
    rd = ImageDraw.Draw(r)
    inner = brush(820, 120, (15, 15, 15), 5, jag=12)
    r.alpha_composite(inner, (80, 35))
    T(rd, (490, 95), strip, heb(900, 74 if len(strip) < 22 else 62), (255, 255, 255))
    shadow_paste(im, r.rotate(1.5, expand=True, resample=Image.BICUBIC), (40, 510), alpha=140)
    # white banner with price hook
    wb = Image.new("RGBA", (920, 420), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wb)
    wd.rectangle([0, 0, 919, 419], fill=(250, 250, 248))
    T(wd, (460, 90), w1, heb(900, 96 if len(w1) < 15 else 62), (15, 15, 15))
    T(wd, (460, 250), w2, heb(900, w2size), (225, 20, 30))
    sub = brush(640, 90, (15, 15, 15), 9, jag=12)
    T(ImageDraw.Draw(sub), (320, 45), w3, heb(900, 52), (255, 255, 255))
    wb.alpha_composite(sub, (140, 320))
    shadow_paste(im, wb.rotate(-1, expand=True, resample=Image.BICUBIC), (70, 730), alpha=150)
    # product row
    cw, chh = 300, 330
    for i, k in enumerate(keys):
        x, y = 45 + i * (cw + 30), 1230 + (20 if i != 1 else 0)
        c = card(img(k), cw, chh, radius=30, pad=10, fit="contain")
        c = c.rotate([-4, 0, 4][i], expand=True, resample=Image.BICUBIC)
        shadow_paste(im, c, (x, y), alpha=150)
        pill(im, x + c.width / 2, y + c.height - 6, ils(P[k][2]), heb(900, 58), (255, 255, 255), (225, 20, 30), padx=28,
             outline=(255, 255, 255))
    # CTA
    bar = brush(1000, 170, (15, 15, 15), 11, jag=16)
    bdd = ImageDraw.Draw(bar)
    T(bdd, (500, 60), "הצטרפו לערוץ בטלגרם", heb(900, 60), (255, 255, 255))
    T(bdd, (500, 125), "@ilamazondeals  ·  israelideals.com", heb(800, 40), (255, 210, 80))
    shadow_paste(im, bar, (40, 1700), alpha=140)
    return im


def main():
    OUT.mkdir(exist_ok=True)
    gadgets = lambda: neon(tag="הגאדג'טים הכי שווים של השבוע", l1="COOL", l2="GADGETS", big=230,
                           sub="שלא ידעתם שאתם צריכים", keys=("olight", "controller", "keyboard"),
                           cta1="גאדג'טים, אופנה ומותגים", cta2="דילים חדשים כל יום · אמזון ואליאקספרס")
    brands = lambda: banner(l1="BRAND", l2="DEALS", strip="המותגים שאתם אוהבים", w1="PUMA · Skechers · LANEIGE",
                            w2="החל מ-62 ש״ח", w2size=130, w3="נעליים · אופנה · ביוטי",
                            keys=("puma", "skechers", "laneige"))
    for name, fn in [("bf_neon", neon), ("bf_collage", collage), ("bf_banner", banner),
                     ("neon_gadgets", gadgets), ("banner_brands", brands)]:
        p = OUT / f"{name}.png"
        fn().convert("RGB").save(p)
        print(p)


if __name__ == "__main__":
    main()
