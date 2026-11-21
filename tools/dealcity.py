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


def title_panel(w, h, big=170, sub="הדילים הכי חמים בעיר"):
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
    he = sub
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


RATE = 3.3428


def ils(usd):
    return f"{round(usd * RATE):,}₪"


def photo_contain(name, box):
    w, h = box[2] - box[0], box[3] - box[1]
    src = Image.open(AD / f"{name}.jpg").convert("RGB")
    bg = grade(ImageOps.fit(src, (w, h), Image.LANCZOS)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (40, 5, 60)), 0.45)
    fg = src.copy()
    fg.thumbnail((int(w * .94), int((h - 74) * .97)), Image.LANCZOS)
    tint = p2.gradient(fg.width, fg.height, [(255, 120, 180), (255, 190, 110)]).convert("RGB")
    fg = Image.blend(fg, ImageChops.multiply(fg, tint), 0.12)
    x, y = (w - fg.width) // 2, max(6, (h - 74 - fg.height) // 2)
    sh = Image.new("L", bg.size, 0)
    ImageDraw.Draw(sh).rectangle([x + 10, y + 14, x + fg.width + 10, y + fg.height + 14], fill=170)
    bg.paste((10, 0, 20), (0, 0), sh.filter(ImageFilter.GaussianBlur(14)))
    bg.paste(fg, (x, y))
    return bg


def price_sticker(im, x, y, price, angle=-8):
    num = price.replace("₪", "")
    f, fs = F(900, 62), F(900, 50)
    d0 = ImageDraw.Draw(im)
    nw, nh, nb = size(d0, num, f)
    sw, sh_, sb = size(d0, "₪", fs)
    st = Image.new("RGBA", (int(nw + sw + 82), int(nh + 50)), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    d.rounded_rectangle([6, 6, st.width - 1, st.height - 1], radius=18, fill=(0, 0, 0, 255))
    d.rounded_rectangle([0, 0, st.width - 7, st.height - 7], radius=18, fill=PINK + (255,), outline=(255, 240, 150, 255), width=5)
    d.text((28 - sb[0], 20 + (nh - sh_) - sb[1]), "₪", font=fs, fill=WHITE)
    d.text((28 + sw + 10 - nb[0], 20 - nb[1]), num, font=f, fill=WHITE, direction="ltr")
    st = st.rotate(angle, expand=True, resample=Image.BICUBIC)
    im.paste(st, (int(x - st.width), int(y)), st)


def name_tag(im, x, y, s, maxw):
    d = ImageDraw.Draw(im)
    fs = 46
    while size(d, s, F(900, fs))[0] > maxw - 40 and fs > 26:
        fs -= 2
    f = F(900, fs)
    w, h, b = size(d, s, f)
    d.rectangle([x, y - h - 26, x + w + 32, y], fill=BLACK)
    text_c(d, x + 16 + w / 2, y - h - 14, s, f, WHITE)


def product_post(title_sub, panels, title_h):
    """panels: (img, box, he_name, usd, focus). Title panel spans the top; CTA band at the bottom."""
    W, H, g = 1080, 1350, 10
    im = Image.new("RGB", (W, H), BLACK)
    im.paste(title_panel(W - 2 * g, title_h - 2 * g, big=190, sub=title_sub), (g, g))
    for name, box, he, usd, focus in panels:
        bx = (box[0] + g, box[1] + g, box[2] - g, box[3] - g)
        im.paste(photo_contain(name, bx), bx[:2])
        price_sticker(im, bx[2] - 8, bx[1] + 14, ils(usd))
        name_tag(im, bx[0] + 12, bx[3] - 12, he, bx[2] - bx[0] - 24)
    cta = compose(W, H, [], 190)  # reuse the CTA band
    im.paste(cta.crop((0, H - 190, W, H)), (0, H - 190))
    return im


def post_home():
    T, M, B = 330, 740, 1160
    P = [("gta_espresso", (0, T, 540, M), "מכונת אספרסו ניידת", 41.56, (.85, .5)),
         ("gta_robot", (540, T, 1080, M), "רובוט שואב ושוטף", 15.06, (.5, .85)),
         ("gta_headphones", (0, M, 540, B), "אוזניות Baseus ANC", 41.44, (1, .6)),
         ("gta_tablet", (540, M, 1080, B), "טאבלט 10 אינץ'", 63.03, (.5, .5))]
    return product_post("בית וטק במחירי רחוב", P, T)


def post_gifts():
    T, M, B = 300, 730, 1160
    P = [("gta_kart", (0, T, 540, M), "קארטינג חשמלי", 381.29, None),
         ("gta_camera", (540, T, 1080, M), "מצלמה דיגיטלית 4K", 42.19, None),
         ("gta_train", (0, M, 360, B), "רכבת מגנטית", 27.73, None),
         ("gta_eyepatch", (360, M, 720, B), "מדבקות עיניים", 17.50, None),
         ("gta_sweater", (720, M, 1080, B), "סוודר לנשים", 17.08, None)]
    return product_post("מתנות לחנוכה", P, T)


if __name__ == "__main__" and "--posts" in sys.argv:
    OUT.mkdir(exist_ok=True)
    post_home().save(OUT / "dealcity_home.jpg", quality=95)
    post_gifts().save(OUT / "dealcity_gifts.jpg", quality=95)
    print("posts ok")
elif __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    feed().save(OUT / "dealcity_feed.png")
    story().save(OUT / "dealcity_story.png")
    print("ok")
