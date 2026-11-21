"""'DEAL CITY' ad: original sunset / neon crime-drama panel collage.
  python tools/dealcity.py -> out/dealcity_feed.png (1080x1350), out/dealcity_story.png (1080x1920)"""
import math, random, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageChops
sys.path.insert(0, str(Path(__file__).parent))
import promo2 as p2
from ad import F, text_c, size, kw

REPO = Path(__file__).resolve().parent.parent
AD = REPO / "data" / "ad"
OUT = REPO / "out"
ANTON = lambda s: ImageFont.truetype(str(REPO / "assets/fonts/Anton-400.ttf"), s)
BEBAS = lambda s: ImageFont.truetype(str(REPO / "assets/fonts/BebasNeue-400.ttf"), s)
SUNSET = [(40, 10, 80), (150, 20, 120), (255, 60, 110), (255, 140, 60), (255, 215, 110)]
PINK, ORANGE, TEAL, BLACK, WHITE = (255, 60, 150), (255, 150, 40), (40, 230, 220), (8, 6, 14), (255, 255, 255)


def grade(im):
    """cinematic sunset tint so all panels feel like one world"""
    im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
    tint = p2.gradient(im.width, im.height, [(255, 90, 160), (255, 170, 80)]).convert("RGB")
    im = Image.blend(im, ImageChops.multiply(im, tint), 0.35)
    v = Image.new("L", im.size, 0)
    ImageDraw.Draw(v).ellipse([-im.width * .25, -im.height * .25, im.width * 1.25, im.height * 1.25], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(min(im.size) // 5))
    return Image.composite(im, Image.new("RGB", im.size, (30, 5, 40)), v)


def photo(name, box, focus=(0.5, 0.5)):
    w, h = box[2] - box[0], box[3] - box[1]
    im = Image.open(AD / f"{name}.jpg").convert("RGB")
    return grade(ImageOps.fit(im, (w, h), Image.LANCZOS, centering=focus))


def palm(d, x, base, h, lean, col):
    pts = []
    for i in range(21):
        t = i / 20
        pts.append((x + lean * t * t * h * .35, base - h * t))
    d.line(pts, fill=col, width=max(6, h // 28), joint="curve")
    tx, ty = pts[-1]
    for a in range(0, 360, 40):
        r = math.radians(a + 10)
        fr = []
        for j in range(12):
            t = j / 11
            fr.append((tx + math.cos(r) * h * .32 * t, ty + math.sin(r) * h * .14 * t + (h * .16 * t * t)))
        d.line(fr, fill=col, width=max(5, h // 34), joint="curve")


def skyline(d, y, w, col, seed=4):
    rnd = random.Random(seed)
    x = 0
    while x < w:
        bw, bh = rnd.randint(30, 80), rnd.randint(40, 190)
        d.rectangle([x, y - bh, x + bw, y], fill=col)
        if rnd.random() < .3:
            d.rectangle([x + bw // 2 - 3, y - bh - 40, x + bw // 2 + 3, y - bh], fill=col)
        x += bw + rnd.randint(0, 6)


def gradient_text(base, cx, cy, s, f, stops, outline=BLACK, ow=10, shadow=(12, 12)):
    tmp = Image.new("L", (base.width, base.height), 0)
    dd = ImageDraw.Draw(tmp)
    w, h, b = size(dd, s, f)
    x, y = cx - w / 2 - b[0], cy - h / 2 - b[1]
    sh = Image.new("L", base.size, 0)
    ImageDraw.Draw(sh).text((x + shadow[0], y + shadow[1]), s, font=f, fill=255, stroke_width=ow, **kw(s))
    base.paste(BLACK, (0, 0), sh)
    ol = Image.new("L", base.size, 0)
    ImageDraw.Draw(ol).text((x, y), s, font=f, fill=255, stroke_width=ow, **kw(s))
    base.paste(outline, (0, 0), ol)
    dd.text((x, y), s, font=f, fill=255, **kw(s))
    g = p2.gradient(base.width, int(h + 40), stops).convert("RGB")
    full = Image.new("RGB", base.size)
    full.paste(g, (0, int(y + b[1] - 20)))
    base.paste(full, (0, 0), tmp)


def title_panel(w, h, big=170):
    im = p2.gradient(w, h, SUNSET).convert("RGB")
    d = ImageDraw.Draw(im)
    sx, sy, r = w * .5, h * .62, h * .36
    sun = Image.new("L", im.size, 0)
    sd = ImageDraw.Draw(sun)
    sd.ellipse([sx - r, sy - r, sx + r, sy + r], fill=255)
    for i in range(7):  # retro sun stripes
        yy = sy + r * (.15 + i * .13)
        sd.rectangle([0, yy, w, yy + 4 + i * 2.2], fill=0)
    im.paste(p2.gradient(w, h, [(255, 240, 150), (255, 120, 90), (255, 60, 140)]).convert("RGB"), (0, 0), sun)
    skyline(d, int(h * .9), w, (60, 10, 70))
    d.rectangle([0, int(h * .9), w, h], fill=(30, 5, 40))
    for i in range(1, 6):  # water reflections
        yy = int(h * .9) + i * 7
        d.line([(sx - r * (1 - i * .15), yy), (sx + r * (1 - i * .15), yy)], fill=(255, 120, 120), width=2)
    palm(d, w * .06, h, int(h * .95), 1.0, (20, 0, 30))
    palm(d, w * .15, h, int(h * .7), 0.6, (20, 0, 30))
    palm(d, w * .93, h, int(h * 1.0), -1.0, (20, 0, 30))
    gradient_text(im, w / 2, h * .38, "DEAL CITY", ANTON(big), [(255, 250, 190), (255, 160, 60), (255, 50, 140)], ow=9)
    d = ImageDraw.Draw(im)
    he = "הדילים הכי חמים בעיר"
    f = F(900, int(big * .36))
    tw, th, _ = size(d, he, f)
    d.rectangle([w / 2 - tw / 2 - 26, h * .66 - 10, w / 2 + tw / 2 + 26, h * .66 + th + 26], fill=BLACK)
    text_c(d, w / 2, h * .66 + 4, he, f, WHITE)
    return im


def tag(d, x, y, s, f, fill=BLACK, ink=WHITE):
    w, h, b = size(d, s, f)
    d.rectangle([x, y, x + w + 28, y + h + 22], fill=fill)
    d.text((x + 14 - b[0], y + 11 - b[1]), s, font=f, fill=ink)


def compose(W, H, panels, cta_h):
    im = Image.new("RGB", (W, H), BLACK)
    g = 10
    for name, box, label, focus in panels:
        x0, y0, x1, y1 = box
        bx = (x0 + g, y0 + g, x1 - g, y1 - g)
        if name == "TITLE":
            im.paste(title_panel(bx[2] - bx[0], bx[3] - bx[1], big=int((bx[2] - bx[0]) * .19)), bx[:2])
        else:
            im.paste(photo(name, bx, focus), bx[:2])
            if label:
                tag(ImageDraw.Draw(im), bx[0] + 14, bx[3] - 70, label, BEBAS(44))
    # CTA band
    d = ImageDraw.Draw(im)
    y = H - cta_h
    band = p2.gradient(W, cta_h, [(20, 5, 35), (60, 10, 70)]).convert("RGB")
    im.paste(band, (0, y))
    d.rectangle([0, y, W, y + 8], fill=PINK)
    p2.logo(im, 120, y + cta_h / 2 + 4, 150, ORANGE)
    d = ImageDraw.Draw(im)
    cx = (240 + W) / 2
    text_c(d, cx, y + cta_h * .14, "JOIN THE CREW", ANTON(int(cta_h * .3)), ORANGE)
    line, fs = "הצטרפו לערוץ הטלגרם · משלוח לארץ", int(cta_h * .17)
    while size(d, line, F(800, fs))[0] > W - 280:
        fs -= 2
    text_c(d, cx, y + cta_h * .5, line, F(800, fs), WHITE)
    text_c(d, cx, y + cta_h * .74, "t.me/ilamazondeals", BEBAS(int(cta_h * .2)), TEAL)
    return im


def feed():
    W, H = 1080, 1350
    P = [("drone2", (0, 0, 420, 300), "TECH", (.5, .5)),
         ("headset2", (420, 0, 1080, 300), "GAMING", (1, .4)),
         ("TITLE", (0, 300, 1080, 640), None, None),
         ("shades1", (0, 640, 360, 920), "STYLE", (.5, .5)),
         ("rccar1", (360, 640, 720, 920), "TOYS", (.5, .45)),
         ("jbl2", (720, 640, 1080, 920), "AUDIO", (.6, .5)),
         ("retro2", (0, 920, 540, 1150), "RETRO", (.5, .5)),
         ("smartwatch2", (540, 920, 1080, 1150), "WEARABLES", (.5, .45))]
    return compose(W, H, P, 200)


def story():
    W, H = 1080, 1920
    P = [("drone2", (0, 0, 540, 420), "TECH", (.5, .5)),
         ("headset2", (540, 0, 1080, 420), "GAMING", (1, .4)),
         ("TITLE", (0, 420, 1080, 860), None, None),
         ("shades1", (0, 860, 540, 1220), "STYLE", (.5, .5)),
         ("rccar1", (540, 860, 1080, 1220), "TOYS", (.5, .45)),
         ("jbl2", (0, 1220, 360, 1600), "AUDIO", (.6, .5)),
         ("retro2", (360, 1220, 720, 1600), "RETRO", (.5, .5)),
         ("smartwatch2", (720, 1220, 1080, 1600), "WEARABLES", (.5, .45))]
    return compose(W, H, P, 320)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    feed().save(OUT / "dealcity_feed.png")
    story().save(OUT / "dealcity_story.png")
    print("ok")
