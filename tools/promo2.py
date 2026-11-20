"""Black Friday promo posts in three styles (4:5): party/balloons, blue confetti, neon night.
  python tools/promo2.py  -> out/bf_party.png, out/bf_confetti.png, out/bf_neon.png
"""
import math, random, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).parent))
import promo
from ad import F, kw, size, text_c

REPO = promo.REPO
W, H = 1080, 1350
PRODUCTS = ["ali-1005012438054801", "ali-1005010739277474", "ali-1005009648930864", "ali-1005013125741328"]
YEL, ORA, PINK, PURP, NAVY, WHITE, INK = (255, 214, 0), (255, 140, 0), (255, 60, 150), (90, 30, 160), (10, 25, 120), (255, 255, 255), (20, 20, 30)


def text_mask(s, f, pad=40):
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    tw, th, b = size(d, s, f)
    m = Image.new("L", (int(tw + pad * 2), int(th + pad * 2)))
    ImageDraw.Draw(m).text((pad - b[0], pad - b[1]), s, font=f, fill=255, **kw(s))
    return m


def gradient(w, h, stops, vertical=True):
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    n = h if vertical else w
    for i in range(n):
        t = i / max(n - 1, 1)
        for k in range(len(stops) - 1):
            if t <= (k + 1) / (len(stops) - 1):
                lt = t * (len(stops) - 1) - k
                c = tuple(int(stops[k][j] + (stops[k + 1][j] - stops[k][j]) * lt) for j in range(3))
                break
        if vertical:
            d.line([(0, i), (w, i)], fill=c)
        else:
            d.line([(i, 0), (i, h)], fill=c)
    return g


def fancy_text(base, cx, cy, s, f, stops, outline=(60, 20, 110), ow=12, shadow=True, tilt=0):
    """3D-ish bubbly title: gradient fill, thick outline, drop shadow."""
    m = text_mask(s, f, pad=ow + 30)
    grown = m.filter(ImageFilter.MaxFilter(ow * 2 + 1))
    layer = Image.new("RGBA", m.size, (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", m.size, (0, 0, 0, 0))
        sh.paste((20, 0, 40, 170), (0, 0), grown)
        layer.alpha_composite(ImageChops.offset(sh, 6, 12) if False else sh, (0, 0))
        layer = Image.new("RGBA", m.size, (0, 0, 0, 0))
        base_sh = Image.new("RGBA", m.size, (0, 0, 0, 0))
        base_sh.paste((20, 0, 40, 150), (0, 0), grown)
        base_sh = base_sh.filter(ImageFilter.GaussianBlur(6))
        layer.alpha_composite(base_sh, (8, 14) if False else (0, 0))
    o = Image.new("RGBA", m.size, (0, 0, 0, 0))
    o.paste(outline + (255,), (0, 0), grown)
    layer.alpha_composite(o)
    g = gradient(m.width, m.height, stops).convert("RGBA")
    g.putalpha(m)
    layer.alpha_composite(g)
    # glossy highlight on the top half
    hl = Image.new("L", m.size)
    ImageDraw.Draw(hl).rectangle([0, 0, m.width, m.height * 0.45], fill=70)
    hl = ImageChops.multiply(hl, m)
    layer.paste((255, 255, 255, 255), (0, 0), hl) if False else layer.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", m.size, WHITE).split(), hl)))
    if tilt:
        layer = layer.rotate(tilt, resample=Image.BICUBIC, expand=True)
    if shadow:
        sh = layer.split()[3].filter(ImageFilter.GaussianBlur(8))
        base.paste((20, 0, 40), (int(cx - layer.width / 2 + 8), int(cy - layer.height / 2 + 14)), sh.point(lambda v: v * 0.6))
    base.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)), layer)


def neon(base, cx, cy, s, f, color, glow=26, tube=WHITE, tilt=0):
    m = text_mask(s, f, pad=glow * 2)
    layer = Image.new("RGBA", m.size, (0, 0, 0, 0))
    for r, a in ((glow, 200), (glow // 2, 255)):
        g = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(r))
        c = Image.new("RGBA", m.size, color + (0,))
        c.putalpha(g.point(lambda v: min(255, int(v * a / 255 * 1.6))))
        layer.alpha_composite(c)
    edge = m.filter(ImageFilter.MaxFilter(7))
    c = Image.new("RGBA", m.size, color + (255,))
    c.putalpha(edge)
    layer.alpha_composite(c)
    core = Image.new("RGBA", m.size, tube + (255,))
    core.putalpha(m.filter(ImageFilter.MinFilter(3)))
    layer.alpha_composite(core)
    if tilt:
        layer = layer.rotate(tilt, resample=Image.BICUBIC, expand=True)
    base.paste(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)), layer)


def circle_photo(base, asin, cx, cy, r, ring=ORA, ring_w=14):
    ph = promo.cutout(asin, int(r * 1.5), int(r * 1.5))
    disc = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse([0, 0, r * 2 - 1, r * 2 - 1], fill=WHITE)
    disc.paste(ph, (r - ph.width // 2, r - ph.height // 2), ph)
    m = Image.new("L", (r * 2, r * 2))
    ImageDraw.Draw(m).ellipse([0, 0, r * 2 - 1, r * 2 - 1], fill=255)
    d = ImageDraw.Draw(base)
    sh = Image.new("L", base.size)
    ImageDraw.Draw(sh).ellipse([cx - r - ring_w + 8, cy - r - ring_w + 16, cx + r + ring_w + 8, cy + r + ring_w + 16], fill=120)
    base.paste((40, 10, 60), (0, 0), sh.filter(ImageFilter.GaussianBlur(14)))
    d.ellipse([cx - r - ring_w, cy - r - ring_w, cx + r + ring_w, cy + r + ring_w], fill=ring)
    base.paste(disc, (cx - r, cy - r), m)


def confetti(base, n, seed, cols, area=None):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(base)
    x0, y0, x1, y1 = area or (0, 0, W, H)
    for _ in range(n):
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        s, a = rnd.uniform(10, 24), rnd.uniform(0, math.pi)
        dx, dy = math.cos(a) * s, math.sin(a) * s
        w = s * 0.35
        d.polygon([(x - dx - math.sin(a) * w, y - dy + math.cos(a) * w), (x + dx - math.sin(a) * w, y + dy + math.cos(a) * w),
                   (x + dx + math.sin(a) * w, y + dy - math.cos(a) * w), (x - dx + math.sin(a) * w, y - dy - math.cos(a) * w)],
                  fill=rnd.choice(cols))


def streamer(d, pts, color, w=10):
    d.line(pts, fill=color, width=w, joint="curve")


def logo(base, cx, cy, dsz, ring):
    promo.logo(base, cx, cy, dsz, ring=ring)


# ---------------------------------------------------------------- 1. party / balloons
def party():
    im = gradient(W, H, [(120, 200, 255), (255, 200, 90), (255, 120, 60)]).convert("RGB")
    d = ImageDraw.Draw(im)
    # string lights
    pts = [(x, 60 + 40 * math.sin(x / 170)) for x in range(-20, W + 40, 20)]
    d.line(pts, fill=(60, 40, 90), width=4)
    for i, (x, y) in enumerate(pts[::4]):
        d.ellipse([x - 13, y + 4, x + 13, y + 34], fill=[YEL, PINK, (90, 220, 255), (140, 255, 120)][i % 4])
    # balloons
    for bx, by, c in ((80, 900, PINK), (170, 820, (90, 200, 255)), (W - 90, 880, YEL), (W - 180, 800, PINK)):
        d.line([(bx, by + 90), (bx + 10, by + 330)], fill=(255, 255, 255), width=3)
        d.ellipse([bx - 70, by - 90, bx + 70, by + 90], fill=c)
        d.ellipse([bx - 40, by - 65, bx - 15, by - 25], fill=(255, 255, 255))
    confetti(im, 120, 3, [PINK, YEL, (90, 220, 255), PURP, WHITE])
    logo(im, W / 2, 175, 150, WHITE)
    fancy_text(im, W / 2, 340, "CRAZY BLACK FRIDAY!", F(900, 84), [(255, 240, 120), (255, 150, 40), (255, 70, 120)], tilt=3)
    fancy_text(im, W / 2, 480, "דילים מטורפים", F(900, 96), [(255, 230, 90), (255, 120, 50)], outline=(90, 20, 120), ow=10, tilt=2)
    fancy_text(im, W / 2, 580, "מאמזון ואליאקספרס", F(900, 70), [(255, 255, 255), (230, 220, 255)], outline=(90, 20, 120), ow=8)
    # big price circle
    cx, cy, r = W / 2, 820, 170
    d = ImageDraw.Draw(im)
    d.ellipse([cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14], fill=YEL)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PURP)
    text_c(d, cx, cy - 135, "עד", F(900, 64), WHITE)
    fancy_text(im, cx, cy + 5, "70%", F(900, 150), [(255, 240, 120), (255, 170, 0)], outline=(60, 10, 100), ow=8, shadow=False)
    text_c(ImageDraw.Draw(im), cx, cy + 95, "הנחה", F(900, 60), WHITE)
    circle_photo(im, PRODUCTS[0], 190, 760, 120)
    circle_photo(im, PRODUCTS[1], W - 190, 760, 120, ring=PINK)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 1090, W, H], fill=(70, 20, 130))
    d.rectangle([0, 1090, W, 1102], fill=YEL)
    text_c(d, W / 2, 1125, "🎁 הגרלה! הצטרפו לערוץ וזכו ב-$50 לאמזון".replace("🎁 ", ""), F(900, 52), YEL)
    text_c(d, W / 2, 1200, "הדילים הכי שווים כל יום · מחירים בשקלים · עד $75", F(800, 38), WHITE)
    text_c(d, W / 2, 1265, "t.me/ilamazondeals", F(900, 46), WHITE)
    return im


# ---------------------------------------------------------------- 2. blue confetti
def blue_confetti():
    im = gradient(W, H, [(20, 30, 200), (35, 60, 230), (20, 25, 170)]).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, H], outline=ORA, width=22)
    for i, (pts, c) in enumerate([
        ([(60, 80), (140, 160), (90, 260), (170, 340)], (90, 230, 200)),
        ([(W - 80, 120), (W - 160, 200), (W - 100, 300), (W - 190, 380)], ORA),
        ([(80, 700), (150, 780), (100, 860)], PINK), ([(W - 90, 650), (W - 170, 730), (W - 110, 810)], (90, 230, 200))]):
        streamer(d, pts, c, 9)
    confetti(im, 110, 9, [ORA, PINK, YEL, (90, 230, 200), WHITE, (255, 80, 80)])
    logo(im, W / 2, 140, 140, ORA)
    # orange swoosh behind the title
    d = ImageDraw.Draw(im)
    d.arc([140, 210, W - 140, 520], start=190, end=330, fill=ORA, width=18)
    fancy_text(im, W / 2, 340, "CRAZY", F(900, 170), [(255, 255, 255), (200, 210, 235)], outline=(190, 90, 0), ow=8, tilt=-4)
    fancy_text(im, W / 2, 470, "Black Friday!", F(900, 96), [(255, 255, 255), (210, 220, 240)], outline=(190, 90, 0), ow=7, tilt=-4)
    d = ImageDraw.Draw(im)
    text_c(d, W / 2, 575, "מחירים מטורפים לדילים מאמזון ואליאקספרס", F(900, 44), WHITE)
    # product strip on white cards
    cw, ch, gap = 220, 230, 26
    x = W / 2 - (cw * 4 + gap * 3) / 2
    for a in PRODUCTS:
        d.rounded_rectangle([x, 660, x + cw, 660 + ch], radius=28, fill=WHITE)
        ph = promo.cutout(a, cw - 30, ch - 30)
        im.paste(ph, (int(x + (cw - ph.width) / 2), int(660 + (ch - ph.height) / 2)), ph)
        x += cw + gap
    d = ImageDraw.Draw(im)
    # white pill
    d.rounded_rectangle([W / 2 - 330, 950, W / 2 + 330, 1035], radius=42, fill=WHITE)
    text_c(d, W / 2, 968, "הצטרפו: t.me/ilamazondeals", F(900, 46), NAVY)
    d.rounded_rectangle([W / 2 - 230, 1070, W / 2 + 230, 1140], radius=35, outline=WHITE, width=4)
    text_c(d, W / 2, 1083, "לערוץ הדילים >>", F(900, 42), WHITE)
    # badge
    d.rounded_rectangle([W - 420, 1180, W - 40, 1290], radius=20, fill=(255, 255, 255), outline=ORA, width=5)
    text_c(d, W - 230, 1195, "הגרלה על $50 לאמזון", F(900, 38), NAVY)
    text_c(d, W - 230, 1245, "לכל מי שמצטרף לערוץ", F(800, 30), NAVY)
    text_c(d, 280, 1225, "Daily deals for Israel 🇮🇱".replace(" 🇮🇱", ""), F(800, 34), WHITE)
    return im


# ---------------------------------------------------------------- 3. neon night
def neon_night():
    im = Image.new("RGB", (W, H), (14, 12, 28))
    g = Image.new("L", (W, H))
    ImageDraw.Draw(g).ellipse([W / 2 - 520, 380, W / 2 + 520, 1100], fill=120)
    im.paste((50, 30, 110), (0, 0), g.filter(ImageFilter.GaussianBlur(140)))
    # neon sticks
    rnd = random.Random(5)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for (x, y, a, c) in ((60, 140, -25, PINK), (W - 120, 120, 25, (80, 200, 255)), (70, 760, 20, PINK), (W - 90, 820, -20, (80, 200, 255)),
                         (110, 1230, -25, (80, 200, 255)), (W - 140, 1240, 25, PINK)):
        dx, dy = math.cos(math.radians(a)) * 90, math.sin(math.radians(a)) * 90
        ld.line([(x - dx, y - dy), (x + dx, y + dy)], fill=c + (255,), width=10)
    glow = lay.filter(ImageFilter.GaussianBlur(14))
    im.paste(glow, (0, 0), glow)
    im.paste(lay, (0, 0), lay)
    logo(im, W / 2, 120, 120, (255, 60, 150))
    d = ImageDraw.Draw(im)
    d.polygon([(250, 215), (830, 195), (835, 255), (255, 275)], fill=WHITE)
    text_c(d, 540, 210, "אירוע הדילים השנתי בערוץ!", F(900, 40), INK)
    neon(im, W / 2, 400, "BLACK", F(900, 170), (60, 160, 255))
    neon(im, W / 2, 560, "FRIDAY", F(900, 150), (255, 60, 150))
    neon(im, W / 2, 720, "עד 70% הנחה", F(900, 96), (255, 60, 200))
    text_c(ImageDraw.Draw(im), W / 2, 805, "אמזון · אליאקספרס · מחירים בשקלים", F(800, 42), (220, 210, 255))
    # neon framed box
    box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(box)
    bd.rounded_rectangle([90, 880, W - 90, 1060], radius=70, outline=(110, 255, 140, 255), width=10)
    bg = box.filter(ImageFilter.GaussianBlur(16))
    im.paste(bg, (0, 0), bg)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([100, 890, W - 100, 1050], radius=62, fill=(8, 8, 14))
    im.paste(box, (0, 0), box)
    d = ImageDraw.Draw(im)
    text_c(d, W / 2 + 70, 915, "הצטרפו לערוץ =", F(900, 54), WHITE)
    text_c(d, W / 2 + 70, 985, "הגרלה על $50 לאמזון", F(900, 50), YEL)
    ph = promo.cutout(PRODUCTS[1], 190, 140)
    im.paste(ph, (130, int(970 - ph.height / 2)), ph)
    # outlined neon button
    btn = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(btn).rounded_rectangle([W / 2 - 250, 1120, W / 2 + 250, 1210], radius=45, outline=(255, 60, 150, 255), width=8)
    bgl = btn.filter(ImageFilter.GaussianBlur(12))
    im.paste(bgl, (0, 0), bgl)
    im.paste(btn, (0, 0), btn)
    text_c(ImageDraw.Draw(im), W / 2, 1140, "לערוץ הדילים >>", F(900, 48), WHITE)
    text_c(ImageDraw.Draw(im), W / 2, 1260, "t.me/ilamazondeals", F(800, 40), (200, 190, 255))
    return im


if __name__ == "__main__":
    out = REPO / "out"
    out.mkdir(exist_ok=True)
    for name, fn in (("bf_party", party), ("bf_confetti", blue_confetti), ("bf_neon", neon_night)):
        fn().save(out / f"{name}.png")
    print("ok")
