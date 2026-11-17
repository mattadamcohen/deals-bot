"""Promo post designs (Instagram 4:5) for the page + Telegram channel + $50 giveaway.
  python tools/promo.py   -> out/promo_a.png, promo_b.png, promo_c.png
"""
import math, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).parent))
import ad
from ad import F, kw, size, text_c, YEL, RED, BLUE, NAVY, WHITE, INK, TG

REPO = ad.REPO
PICKS = [("B06W2JSJ4H", "שעונים"), ("ali-1005010105528998", "סניקרס"), ("ali-1005007668695524", "מצלמות אבטחה"), ("B08JCD4PS6", "יצירה לילדים")]
W, H = 1080, 1350


def cutout(asin, maxw, maxh):
    """Product photo with the white background removed (flood fill from the edges), trimmed and scaled."""
    im = Image.open(REPO / "data" / "images" / f"{asin}.jpg").convert("RGB")
    im.thumbnail((1200, 1200), Image.LANCZOS)
    w, h = im.size
    # mask of background-coloured pixels (close to the corner colour) connected to the border
    px = im.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    ref = tuple(sorted(c[i] for c in corners)[2] for i in range(3))
    diff = ImageChops.difference(im, Image.new("RGB", im.size, ref)).convert("L")
    seed = diff.point(lambda v: 255 if v < 22 else 0)
    for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if seed.getpixel((x, y)) == 255:
            ImageDraw.floodfill(seed, (x, y), 128)
    bg = seed.point(lambda v: 255 if v == 128 else 0)
    alpha = ImageChops.invert(bg).filter(ImageFilter.GaussianBlur(1.2))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 30 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    out.thumbnail((maxw, maxh), Image.LANCZOS)
    return out


def drop(base, img, cx, cy, glow=None, shadow=True):
    x, y = int(cx - img.width / 2), int(cy - img.height / 2)
    a = img.split()[3]
    if glow:
        g = Image.new("RGBA", (img.width + 160, img.height + 160), (0, 0, 0, 0))
        gm = Image.new("L", g.size)
        gm.paste(a, (80, 80))
        gm = gm.filter(ImageFilter.GaussianBlur(40)).point(lambda v: min(255, v * 2))
        base.paste(Image.new("RGB", g.size, glow), (x - 80, y - 80), gm)
    if shadow:
        sm = Image.new("L", base.size)
        sm.paste(a.point(lambda v: v * 0.45), (x + 14, y + 22))
        base.paste(Image.new("RGB", base.size, (0, 0, 0)), mask=sm.filter(ImageFilter.GaussianBlur(16)))
    base.paste(img, (x, y), img)


def coin(base, cx, cy, r, top, big, bottom, tilt=-10, fill=YEL, ink=INK):
    s = Image.new("RGBA", (r * 2 + 30, r * 2 + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    pts = []
    for i in range(40):
        a = math.pi * 2 * i / 40
        rr = r if i % 2 == 0 else r * 0.9
        pts.append((r + 15 + rr * math.cos(a), r + 15 + rr * math.sin(a)))
    d.polygon(pts, fill=fill)
    d.ellipse([r * 0.18 + 15, r * 0.18 + 15, r * 1.82 + 15, r * 1.82 + 15], outline=ink, width=4)
    text_c(d, r + 15, r * 0.48 + 15, top, F(900, int(r * 0.24)), ink)
    text_c(d, r + 15, r * 0.74 + 15, big, F(900, int(r * 0.62)), ink)
    text_c(d, r + 15, r * 1.42 + 15, bottom, F(800, int(r * 0.2)), ink)
    s = s.rotate(tilt, resample=Image.BICUBIC)
    base.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)


def pill(d, cx, cy, t, f, fill, ink, padx=34, h=None):
    tw, th, b = size(d, t, f)
    h = h or th + 34
    d.rounded_rectangle([cx - tw / 2 - padx, cy - h / 2, cx + tw / 2 + padx, cy + h / 2], radius=h // 2, fill=fill)
    d.text((cx - tw / 2 - b[0], cy - th / 2 - b[1]), t, font=f, fill=ink, **kw(t))


def logo(base, cx, cy, d=150, ring=WHITE):
    lg = Image.open(REPO / "assets" / "ilamazondeals-logo.png").convert("RGB").resize((d, d), Image.LANCZOS)
    m = Image.new("L", (d, d))
    ImageDraw.Draw(m).ellipse([0, 0, d - 1, d - 1], fill=255)
    dr = ImageDraw.Draw(base)
    sh = Image.new("L", base.size)
    ImageDraw.Draw(sh).ellipse([cx - d / 2 - 6, cy - d / 2 + 4, cx + d / 2 + 6, cy + d / 2 + 16], fill=110)
    base.paste(Image.new("RGB", base.size, (0, 0, 0)), mask=sh.filter(ImageFilter.GaussianBlur(10)))
    dr.ellipse([cx - d / 2 - 7, cy - d / 2 - 7, cx + d / 2 + 7, cy + d / 2 + 7], fill=ring)
    base.paste(lg, (int(cx - d / 2), int(cy - d / 2)), m)


def bottom(im, he, en, dark=False):
    """Hebrew line, English line, CTA button."""
    d = ImageDraw.Draw(im)
    pill(d, W / 2, 1085, he, F(900, 42), WHITE if not dark else YEL, INK, h=74)
    text_c(d, W / 2, 1138, en, F(800, 34), INK if not dark else (215, 225, 255))
    ad.cta(im, W / 2, 1252, 820, 100)
    text_c(ImageDraw.Draw(im), W / 2, 1306, "t.me/ilamazondeals", F(800, 28), NAVY if not dark else (215, 225, 255))


# ---------------------------------------------------------------- A: bright burst, 4 products on stage
def style_a():
    im = ad.burst_bg(W, H, 620)
    d = ImageDraw.Draw(im)
    d.polygon([(40, 50), (W - 40, 28), (W - 56, 200), (56, 222)], fill=BLUE)
    text_c(d, W / 2 + 70, 82, "הדילים הכי שווים", F(900, 86), WHITE, stroke=5, sfill=NAVY)
    text_c(d, W / 2, 245, "מאמזון ואליאקספרס, כל יום", F(900, 56), INK)
    text_c(d, W / 2, 315, "Daily Amazon & AliExpress deals for Israel", F(800, 32), NAVY)
    logo(im, 120, 125, 132)
    spots = [(290, 520, 270, 250), (790, 520, 330, 220), (290, 830, 290, 230), (790, 830, 310, 230)]
    for (asin, lab), (cx, cy, mw, mh) in zip(PICKS, spots):
        drop(im, cutout(asin, mw, mh), cx, cy, glow=(255, 255, 230))
    for (asin, lab), (cx, cy, mw, mh) in zip(PICKS, spots):
        pill(ImageDraw.Draw(im), cx, cy + 142, lab, F(900, 32), BLUE, WHITE, h=54)
    coin(im, W / 2, 680, 108, "זכו ב", "$50", "לאמזון", tilt=-8, fill=RED, ink=WHITE)
    bottom(im, "הצטרפו לערוץ הטלגרם ואתם בהגרלה!", "Join our Telegram channel & win a $50 Amazon voucher")
    return im


# ---------------------------------------------------------------- B: dark premium, neon accents
def style_b():
    im = Image.new("RGB", (W, H), (10, 14, 40))
    g = Image.new("L", (W, H))
    gd = ImageDraw.Draw(g)
    for i in range(40):
        r = 900 - i * 20
        gd.ellipse([W / 2 - r, 620 - r * 0.8, W / 2 + r, 620 + r * 0.8], fill=int(i * 3.2))
    im.paste(Image.new("RGB", (W, H), (40, 70, 200)), mask=g.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(im)
    text_c(d, W / 2 + 60, 58, "דילים שאסור לפספס", F(900, 80), YEL)
    text_c(d, W / 2, 162, "אמזון · אליאקספרס · מחירים בשקלים", F(800, 40), (200, 215, 255))
    text_c(d, W / 2, 215, "Deals you can't miss · Amazon & AliExpress", F(800, 30), (160, 180, 240))
    # 2x2 glass tiles
    tw_, th_, gap = 430, 350, 36
    for i, (asin, lab) in enumerate(PICKS):
        col, row = i % 2, i // 2
        x0 = W / 2 + gap / 2 if col == 0 else W / 2 - gap / 2 - tw_
        y0 = 285 + row * (th_ + gap)
        tile = Image.new("RGBA", (tw_, th_), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rounded_rectangle([0, 0, tw_ - 1, th_ - 1], radius=34, fill=(255, 255, 255, 235))
        im.paste(tile, (int(x0), int(y0)), tile)
        drop(im, cutout(asin, tw_ - 70, th_ - 120), x0 + tw_ / 2, y0 + (th_ - 60) / 2, shadow=True)
        pill(ImageDraw.Draw(im), x0 + tw_ / 2, y0 + th_ - 42, lab, F(900, 34), (10, 14, 40), YEL, h=56)
    coin(im, W / 2, 285 + th_ + gap / 2, 108, "זכו ב", "$50", "לאמזון", tilt=10)
    logo(im, 88, 92, 112, ring=YEL)
    bottom(im, "הצטרפו לערוץ = נכנסתם להגרלה", "Join our Telegram channel & win a $50 Amazon voucher", dark=True)
    return im


# ---------------------------------------------------------------- C: one hero product + "deals like this"
def style_c():
    im = Image.new("RGB", (W, H), (255, 214, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 420], fill=BLUE)
    d.polygon([(0, 470), (W, 420), (0, 420)], fill=BLUE)
    text_c(d, W / 2, 50, "דילים כאלה", F(900, 112), WHITE)
    text_c(d, W / 2, 185, "כל יום בטלגרם", F(900, 112), YEL)
    text_c(d, W / 2, 330, "Deals like these, every day on Telegram", F(800, 34), WHITE)
    hero = cutout(PICKS[0][0], 400, 560)
    drop(im, hero, 320, 745, glow=(255, 255, 255))
    # side stack of the other 3
    for i, (asin, lab) in enumerate(PICKS[1:]):
        cy = 545 + i * 175
        ImageDraw.Draw(im).rounded_rectangle([630, cy - 75, 1015, cy + 75], radius=30, fill=WHITE)
        drop(im, cutout(asin, 140, 125), 930, cy, shadow=False)
        dd = ImageDraw.Draw(im)
        tw, th, b = size(dd, lab, F(900, 38))
        dd.text((850 - tw - b[0], cy - th / 2 - b[1]), lab, font=F(900, 38), fill=INK, **kw(lab))
    coin(im, 160, 520, 104, "זכו ב", "$50", "לאמזון", tilt=-12, fill=RED, ink=WHITE)
    logo(im, 95, 95, 120, ring=YEL)
    bottom(im, "הצטרפו לערוץ ואתם בהגרלה על $50", "Join our Telegram channel & win a $50 Amazon voucher")
    return im


if __name__ == "__main__":
    out = REPO / "out"
    out.mkdir(exist_ok=True)
    for name, fn in (("a", style_a), ("b", style_b), ("c", style_c)):
        fn().save(out / f"promo_{name}.png")
    print("ok")
