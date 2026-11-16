"""Instagram ad drafts (feed 4:5 and story 9:16) promoting the Telegram channel.
  python tools/ad.py ASIN1 ASIN2 ASIN3 ASIN4  -> out/ad_feed.png, out/ad_story.png
"""
import math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "data" / "images"
OUT = REPO / "out"
F = lambda w, s: ImageFont.truetype(str(REPO / "assets" / "fonts" / f"Heebo-{w}.ttf"), s)

YEL, ORA, RED = (255, 214, 0), (255, 140, 0), (235, 30, 60)
BLUE, NAVY, WHITE, INK = (20, 80, 230), (8, 30, 110), (255, 255, 255), (20, 20, 30)
TG = (34, 158, 217)


def kw(s):
    return {"direction": "rtl", "language": "he"} if any("֐" <= c <= "׿" for c in s) else {}


def size(d, s, f):
    b = d.textbbox((0, 0), s, font=f, **kw(s))
    return b[2] - b[0], b[3] - b[1], b


def text_c(d, cx, y, s, f, fill, stroke=0, sfill=None):
    w, h, b = size(d, s, f)
    d.text((cx - w / 2 - b[0], y - b[1]), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill, **kw(s))
    return h


def burst_bg(W, H, cy):
    im = Image.new("RGB", (W, H), YEL)
    d = ImageDraw.Draw(im)
    cx, R = W / 2, max(W, H) * 1.5
    for i in range(36):
        if i % 2:
            continue
        a0, a1 = math.radians(i * 10), math.radians(i * 10 + 10)
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))],
                  fill=(255, 196, 0))
    glow = Image.new("L", (W, H))
    ImageDraw.Draw(glow).ellipse([cx - 520, cy - 520, cx + 520, cy + 520], fill=150)
    im.paste(Image.new("RGB", (W, H), (255, 240, 150)), mask=glow.filter(ImageFilter.GaussianBlur(120)))
    return im


def shadow(base, box, r, off=14, blur=18, alpha=90):
    sh = Image.new("L", base.size)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(sh).rounded_rectangle([x0 + off // 2, y0 + off, x1 + off // 2, y1 + off], radius=r, fill=alpha)
    base.paste(Image.new("RGB", base.size, (120, 70, 0)), mask=sh.filter(ImageFilter.GaussianBlur(blur)))


def card(base, asin, box, label, tilt):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(c)
    cd.rounded_rectangle([0, 0, w - 1, h - 1], radius=36, fill=WHITE)
    ph = Image.open(IMG / f"{asin}.jpg").convert("RGB")
    ph.thumbnail((w - 50, h - 110), Image.LANCZOS)
    c.paste(ph, ((w - ph.width) // 2, 25 + (h - 110 - ph.height) // 2))
    # category tag at the bottom
    f = F(900, 44)
    tw, th, b = size(cd, label, f)
    cd.rounded_rectangle([(w - tw) / 2 - 30, h - 82, (w + tw) / 2 + 30, h - 22], radius=30, fill=BLUE)
    cd.text(((w - tw) / 2 - b[0], h - 52 - th / 2 - b[1]), label, font=f, fill=WHITE, **kw(label))
    c = c.rotate(tilt, resample=Image.BICUBIC, expand=True)
    shadow(base, (x0, y0, x1, y1), 36)
    base.paste(c, (x0 - (c.width - w) // 2, y0 - (c.height - h) // 2), c)


def sticker(base, cx, cy, r, lines, tilt=-12):
    s = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    pts = []
    for i in range(32):
        a = math.pi * 2 * i / 32
        rr = r if i % 2 == 0 else r * 0.86
        pts.append((r + 10 + rr * math.cos(a), r + 10 + rr * math.sin(a)))
    d.polygon(pts, fill=RED)
    y = r + 10 - sum(f.size for _, f in lines) * 0.55
    for t, f in lines:
        text_c(d, r + 10, y, t, f, WHITE)
        y += f.size * 1.1
    s = s.rotate(tilt, resample=Image.BICUBIC)
    base.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)


def plane(d, cx, cy, s, fill):
    """Simple paper-plane glyph."""
    d.polygon([(cx - s, cy), (cx + s, cy - s * 0.8), (cx + s * 0.35, cy + s * 0.85), (cx + s * 0.05, cy + s * 0.25)], fill=fill)
    d.polygon([(cx + s * 0.05, cy + s * 0.25), (cx + s, cy - s * 0.8), (cx - s * 0.05, cy + s * 0.65)], fill=(220, 235, 255))


def cta(base, cx, cy, w, h):
    d = ImageDraw.Draw(base)
    shadow(base, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), h // 2, off=12, alpha=120)
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=h // 2, fill=TG)
    t = "הצטרפו לערוץ בטלגרם"
    f = F(900, int(h * 0.42))
    tw, th, b = size(d, t, f)
    gap, ps = 26, int(h * 0.24)
    total = tw + gap + ps * 2
    x = cx - total / 2
    plane(d, x + ps, cy, ps, WHITE)
    d.text((x + ps * 2 + gap - b[0], cy - th / 2 - b[1] - 4), t, font=f, fill=WHITE, **kw(t))


def header(base, W, y):
    d = ImageDraw.Draw(base)
    # blue ribbon
    d.polygon([(40, y), (W - 40, y - 22), (W - 56, y + 170), (56, y + 192)], fill=BLUE)
    text_c(d, W / 2, y + 30, "דילים מטורפים", F(900, 122), WHITE, stroke=5, sfill=NAVY)
    text_c(d, W / 2, y + 222, "מאמזון ואליאקספרס", F(900, 78), INK)


def benefits(d, W, y, f):
    t = "הכי נמכרים  •  משלוח לארץ  •  מחירים בשקלים"
    tw, th, b = size(d, t, f)
    d.rounded_rectangle([W / 2 - tw / 2 - 40, y - 20, W / 2 + tw / 2 + 40, y + th + 30], radius=40, fill=WHITE)
    text_c(d, W / 2, y + 2, t, f, INK)


def feed(asins, labels):
    W, H = 1080, 1350
    im = burst_bg(W, H, 700)
    header(im, W, 50)
    cw, ch, gx, gy, top = 430, 350, 44, 30, 400
    tilts = [3, -3, -2, 3]
    for i, a in enumerate(asins[:4]):
        col, row = i % 2, i // 2
        x0 = W / 2 + gx / 2 if col == 0 else W / 2 - gx / 2 - cw
        y0 = top + row * (ch + gy)
        card(im, a, (int(x0), int(y0), int(x0 + cw), int(y0 + ch)), labels[i], tilts[i])
    sticker(im, 120, 420, 105, [("דילים", F(900, 46)), ("חדשים", F(900, 46)), ("כל יום", F(800, 36))], tilt=12)
    d = ImageDraw.Draw(im)
    benefits(d, W, 1150, F(800, 40))
    cta(im, W / 2, 1268, 820, 104)
    return im


def story(asins, labels):
    W, H = 1080, 1920
    im = burst_bg(W, H, 900)
    header(im, W, 170)
    cw, ch, gx, gy, top = 440, 420, 40, 36, 590
    tilts = [3, -3, -2, 3]
    for i, a in enumerate(asins[:4]):
        col, row = i % 2, i // 2
        x0 = W / 2 + gx / 2 if col == 0 else W / 2 - gx / 2 - cw
        y0 = top + row * (ch + gy)
        card(im, a, (int(x0), int(y0), int(x0 + cw), int(y0 + ch)), labels[i], tilts[i])
    sticker(im, 130, 600, 115, [("דילים", F(900, 52)), ("חדשים", F(900, 52)), ("כל יום", F(800, 40))], tilt=12)
    d = ImageDraw.Draw(im)
    benefits(d, W, 1490, F(800, 42))
    cta(im, W / 2, 1620, 860, 116)
    text_c(d, W / 2, 1700, "t.me/ilamazondeals", F(800, 40), NAVY)
    return im


if __name__ == "__main__":
    asins = sys.argv[1:5]
    labels = ["צעצועים", "לבית", "יצירה לילדים", "גאדג׳טים"]
    OUT.mkdir(exist_ok=True)
    feed(asins, labels).save(OUT / "ad_feed.png")
    story(asins, labels).save(OUT / "ad_story.png")
    print("saved", OUT / "ad_feed.png", OUT / "ad_story.png")
