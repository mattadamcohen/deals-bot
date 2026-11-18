"""Gift-box reel: a present shakes, the lid pops, deals fly out one by one with their prices, then a CTA.
  python tools/giftbox.py ASIN[:label] ASIN[:label] ...   -> reel-out/giftbox.mp4
"""
import math, os, random, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import reel, promo
from ad import F, text_c, kw, size

bot = reel.bot
W, H, FPS = 1080, 1920, 30
RED, DRED, GOLD, YEL, BLUE, NAVY, WHITE, INK = (230, 30, 60), (170, 15, 40), (255, 196, 0), (255, 214, 0), (20, 80, 230), (8, 30, 110), (255, 255, 255), (20, 20, 30)
BOX_CX, BOX_TOP, BOX_W, BOX_H = W // 2, 1250, 540, 400
LID_H = 120

ease_out = lambda x: 1 - (1 - min(max(x, 0), 1)) ** 3
ease_back = lambda x: 1 + 2.7 * (min(max(x, 0), 1) - 1) ** 3 + 1.7 * (min(max(x, 0), 1) - 1) ** 2


def background():
    im = Image.new("RGB", (W, H), (60, 20, 140))
    d = ImageDraw.Draw(im)
    cx, cy, R = W / 2, 1000, 2600
    for i in range(0, 36, 2):
        a0, a1 = math.radians(i * 10), math.radians(i * 10 + 10)
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))],
                  fill=(80, 35, 170))
    g = Image.new("L", (W, H))
    ImageDraw.Draw(g).ellipse([cx - 600, cy - 600, cx + 600, cy + 600], fill=170)
    im.paste(Image.new("RGB", (W, H), (150, 90, 255)), mask=g.filter(ImageFilter.GaussianBlur(160)))
    return im


BG = None


def box_body():
    b = Image.new("RGBA", (BOX_W, BOX_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle([0, 0, BOX_W - 1, BOX_H - 1], radius=24, fill=RED)
    d.rectangle([0, 0, BOX_W, 40], fill=DRED)  # shadow under the lid
    d.rectangle([BOX_W / 2 - 45, 0, BOX_W / 2 + 45, BOX_H], fill=GOLD)
    return b


def box_lid():
    w = BOX_W + 50
    lid = Image.new("RGBA", (w, LID_H + 170), (0, 0, 0, 0))
    d = ImageDraw.Draw(lid)
    top = 170
    d.rounded_rectangle([0, top, w - 1, top + LID_H - 1], radius=22, fill=RED)
    d.rectangle([w / 2 - 50, top, w / 2 + 50, top + LID_H], fill=GOLD)
    # bow
    for sx in (-1, 1):
        d.ellipse([w / 2 + sx * 30 - 95 + (sx * 70), top - 150, w / 2 + sx * 30 + 95 + (sx * 70), top + 10], fill=GOLD,
                  outline=(220, 150, 0), width=8)
    d.ellipse([w / 2 - 45, top - 70, w / 2 + 45, top + 20], fill=(240, 170, 0))
    return lid


BODY, LID = None, None


def draw_box(im, t_shake=0.0, lid_off=(0, 0), lid_rot=0.0, lid_alpha=1.0, lid=True):
    dx = math.sin(t_shake * 40) * 14 * min(t_shake * 3, 1) if t_shake else 0
    sh = Image.new("L", (W, H))
    ImageDraw.Draw(sh).ellipse([BOX_CX - 330, BOX_TOP + BOX_H - 30, BOX_CX + 330, BOX_TOP + BOX_H + 60], fill=140)
    im.paste(Image.new("RGB", (W, H), (20, 5, 50)), mask=sh.filter(ImageFilter.GaussianBlur(25)))
    im.paste(BODY, (int(BOX_CX - BOX_W / 2 + dx), BOX_TOP), BODY)
    if not lid:
        # open box: dark inside rim
        ImageDraw.Draw(im).rounded_rectangle([BOX_CX - BOX_W / 2 + 10 + dx, BOX_TOP - 18, BOX_CX + BOX_W / 2 - 10 + dx, BOX_TOP + 26],
                                             radius=14, fill=(110, 10, 30))
        return
    lid = LID.rotate(lid_rot, resample=Image.BICUBIC, expand=True) if lid_rot else LID
    if lid_alpha < 1:
        lid = lid.copy()
        lid.putalpha(lid.split()[3].point(lambda v: int(v * lid_alpha)))
    x = BOX_CX - lid.width / 2 + dx + lid_off[0]
    y = BOX_TOP - LID.height + 30 + lid_off[1] - (lid.height - LID.height) / 2
    im.paste(lid, (int(x), int(y)), lid)


def confetti(im, t, seed=7, n=90):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(im)
    cols = [YEL, (255, 90, 160), (60, 220, 255), (120, 255, 120), WHITE, (255, 140, 0)]
    for _ in range(n):
        ang = rnd.uniform(-math.pi * 0.95, -math.pi * 0.05)
        sp = rnd.uniform(900, 1700)
        x = BOX_CX + math.cos(ang) * sp * t
        y = BOX_TOP + math.sin(ang) * sp * t + 1300 * t * t
        s = rnd.randint(10, 20)
        d.rectangle([x, y, x + s, y + s * 0.6], fill=rnd.choice(cols))


def rays(im, t, alpha=1.0):
    g = Image.new("L", (W, H))
    gd = ImageDraw.Draw(g)
    cx, cy = BOX_CX, BOX_TOP
    for i in range(14):
        a = math.radians(-180 + i * 13 + t * 40)
        gd.polygon([(cx, cy), (cx + 1600 * math.cos(a - 0.05), cy + 1600 * math.sin(a - 0.05)),
                    (cx + 1600 * math.cos(a + 0.05), cy + 1600 * math.sin(a + 0.05))], fill=int(120 * alpha))
    im.paste(Image.new("RGB", (W, H), (255, 240, 170)), mask=g.filter(ImageFilter.GaussianBlur(18)))


def header(im, line1, line2=None):
    d = ImageDraw.Draw(im)
    text_c(d, W / 2, 150, line1, F(900, 110), YEL, stroke=6, sfill=NAVY)
    if line2:
        text_c(d, W / 2, 300, line2, F(900, 60), WHITE, stroke=4, sfill=NAVY)


def price_tag(im, cx, cy, price, off, scale=1.0):
    d = ImageDraw.Draw(im)
    f = F(900, int(84 * scale))
    tw, th, b = size(d, price, f)
    w, h = tw + 80 * scale, th + 46 * scale
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=h / 2, fill=YEL, outline=INK, width=int(5 * scale))
    d.text((cx - tw / 2 - b[0], cy - th / 2 - b[1]), price, font=f, fill=INK, **kw(price))
    if off:
        t = f"{off} הנחה"
        f2 = F(900, int(44 * scale))
        tw2, th2, b2 = size(d, t, f2)
        x, y = cx + w / 2 - 20, cy - h / 2 - 30
        d.rounded_rectangle([x - tw2 / 2 - 22, y - th2 / 2 - 14, x + tw2 / 2 + 22, y + th2 / 2 + 14], radius=24, fill=RED)
        d.text((x - tw2 / 2 - b2[0], y - th2 / 2 - b2[1]), t, font=f2, fill=WHITE, **kw(t))


def badge(im, cx, cy, off):
    d = ImageDraw.Draw(im)
    t = f"{off} הנחה"
    f = F(900, 46)
    tw, th, b = size(d, t, f)
    d.rounded_rectangle([cx - tw / 2 - 26, cy - th / 2 - 16, cx + tw / 2 + 26, cy + th / 2 + 16], radius=28, fill=RED, outline=WHITE, width=4)
    d.text((cx - tw / 2 - b[0], cy - th / 2 - b[1]), t, font=f, fill=WHITE, **kw(t))


def card(img, maxw=620, maxh=560):
    """Product cut-out on a white rounded card."""
    c = img.copy()
    c.thumbnail((maxw - 60, maxh - 60), Image.LANCZOS)
    w, h = c.width + 60, c.height + 60
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle([0, 0, w - 1, h - 1], radius=40, fill=(255, 255, 255, 255))
    out.paste(c, (30, 30), c)
    return out


def paste_scaled(im, img, cx, cy, s, rot=0.0):
    if s <= 0.02:
        return
    w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
    t = img.resize((w, h), Image.LANCZOS)
    if rot:
        t = t.rotate(rot, resample=Image.BICUBIC, expand=True)
    sh = Image.new("L", im.size)
    sh.paste(t.split()[3].point(lambda v: v // 2), (int(cx - t.width / 2 + 12), int(cy - t.height / 2 + 22)))
    im.paste(Image.new("RGB", im.size, (10, 0, 30)), mask=sh.filter(ImageFilter.GaussianBlur(18)))
    im.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)), t)


def build(items, out_path, music=None):
    global BG, BODY, LID
    BG, BODY, LID = background(), box_body(), box_lid()
    cards = [card(it["img"]) for it in items]
    thumbs = []
    segs = []

    def intro(t, dur):  # box bounces in, shakes
        im = BG.copy()
        header(im, "מה יש בקופסה?", "דילים בהפתעה מאמזון ואליאקספרס")
        drop = ease_back(t / 0.7)
        global BOX_TOP
        bt = BOX_TOP
        im2 = im
        shake = max(0.0, t - 0.9)
        offset = int((1 - drop) * -900)
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        base = im2.copy()
        # draw box at an offset by temporarily moving the box origin
        globals()["BOX_TOP"] = bt + offset
        draw_box(base, t_shake=shake)
        globals()["BOX_TOP"] = bt
        return base

    def opening(t, dur):  # lid flies off, rays + confetti
        im = BG.copy()
        rays(im, t, alpha=ease_out(t / 0.4))
        header(im, "מה יש בקופסה?", "דילים בהפתעה מאמזון ואליאקספרס")
        k = ease_out(t / dur)
        draw_box(im, lid_off=(260 * k, -900 * k), lid_rot=-35 * k, lid_alpha=1 - max(0, k - 0.6) / 0.4)
        confetti(im, t)
        return im

    def item_scene(i):
        it, cd = items[i], cards[i]

        def fn(t, dur):
            im = BG.copy()
            rays(im, t + i, alpha=0.6)
            # previously revealed items as a small row at the top
            for j, th in enumerate(thumbs[:i]):
                paste_scaled(im, th, 140 + j * 200, 210, 0.95)
            draw_box(im, lid=False)
            # fly out of the box: from the box mouth to centre, grow, slight spin
            k = ease_back(t / 0.75)
            cy = BOX_TOP + 40 + (640 - (BOX_TOP + 40)) * k
            s = 0.15 + 0.85 * ease_out(t / 0.75)
            paste_scaled(im, cd, W / 2, cy, s, rot=(1 - ease_out(t / 0.75)) * 25)
            if t > 0.55:
                a = min(1, (t - 0.55) / 0.25)
                d = ImageDraw.Draw(im)
                if a > 0.3:
                    text_c(d, W / 2, 955, it["title"], F(900, 58), WHITE, stroke=4, sfill=NAVY)
                    price_tag(im, W / 2, 1105 - (1 - a) * 40, it["price"], "", scale=0.9 + 0.1 * a)
                    if it["off"]:
                        badge(im, W / 2 + cd.width / 2 - 30, 640 - cd.height / 2 + 10, it["off"])
            confetti(im, t * 0.6, seed=i + 11, n=30)
            return im
        return fn

    def outro(t, dur):
        im = BG.copy()
        rays(im, t, alpha=0.8)
        k = ease_out(t / 0.6)
        n = len(cards)
        for j, th in enumerate(thumbs):  # all items around the open box
            ang = math.radians(200 + j * (140 / max(n - 1, 1)))
            r = 430 * k
            paste_scaled(im, th, W / 2 + math.cos(ang) * r * 1.0, 1080 + math.sin(ang) * r * 1.05, 1.55)
        draw_box(im, lid=False)
        d = ImageDraw.Draw(im)
        text_c(d, W / 2, 120, "עוד דילים כאלה כל יום", F(900, 80), YEL, stroke=5, sfill=NAVY)
        if t > 0.4:
            reel_cta = "הצטרפו לערוץ בטלגרם"
            import ad
            text_c(ImageDraw.Draw(im), W / 2, 1690, "כתבו \"לינק\" ונשלח לכם את הקישורים", F(800, 44), WHITE, stroke=3, sfill=NAVY)
            ad.cta(im, W / 2, 1800, 860, 116)
            text_c(ImageDraw.Draw(im), W / 2, 1872, "t.me/ilamazondeals", F(800, 34), WHITE)
        return im

    for cd in cards:
        th = cd.copy()
        th.thumbnail((170, 170), Image.LANCZOS)
        thumbs.append(th)
    segs.append(("g1_intro", intro, 2.0))
    segs.append(("g2_open", opening, 0.9))
    for i in range(len(items)):
        segs.append((f"g3_item{i}", item_scene(i), 2.6))
    segs.append(("g9_outro", outro, 2.6))
    files = [reel.render(n, f, d) for n, f, d in segs]
    lst = reel.OUT / "glist.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    silent = reel.OUT / "gsilent.mp4"
    subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    total = sum(d for _, _, d in segs)
    music = music or sorted((REPO / "assets" / "music").glob("track*.m4a"))[0]
    subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-i", str(silent), "-stream_loop", "-1", "-i", str(music), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-af", f"afade=t=out:st={total - 1:.1f}:d=0.9",
                    "-shortest", "-movflags", "+faststart", str(out_path)], check=True)
    return out_path


if __name__ == "__main__":
    items = []
    for arg in sys.argv[1:]:
        asin, _, label = arg.partition(":")
        p = {"asin": asin}
        import json
        for x in json.loads((REPO / "data" / "posts.json").read_text()):
            if x["asin"] == asin:
                p = x
        off = (p.get("discount") or "").replace("%", "")
        items.append({"img": promo.cutout(asin, 560, 520), "title": label or reel.short_he(p.get("title_he") or p.get("title"), 58, 900),
                      "price": bot.shekels(p.get("price") or ""), "off": f"{off}%" if off else ""})
    OUTD = REPO / "reel-out"
    OUTD.mkdir(exist_ok=True)
    print(build(items, OUTD / "giftbox.mp4"))
