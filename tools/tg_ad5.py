"""5 Telegram Ads image options (16:9, 1280x720), built to read at small size:
few words, big products, one CTA. python tools/tg_ad5.py -> out/tgad_1..5.png"""
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from promo_styles import T, heb, anton, brush, card, pill, shadow_paste, glow_line, OUT, REPO

W, H = 1280, 720
AD = REPO / "data" / "ad"
IM = REPO / ".cache" / "promo_img"
P = {  # real channel deals, price in ₪ at the posted price
    "adidas": (AD / "t_adidas.jpg", "Adidas", 165), "casio": (AD / "t_casio.jpg", "Casio", 91),
    "cerave": (AD / "t_cerave.jpg", "CeraVe", 58), "fossil": (AD / "t_fossil.jpg", "Fossil", 221),
    "stanley": (AD / "t_stanley.jpg", "Stanley", 87), "logitech": (AD / "b_g305.jpg", "Logitech", 99),
    "baseus": (AD / "b_baseus.jpg", "Baseus", 249), "reebok": (AD / "b_reebok.jpg", "Reebok", 201),
    "owala": (IM / "B0FFTLNC5S.jpg", "Owala", 76), "8bitdo": (IM / "ali-1005009157516970.jpg", "8BitDo", 91),
    "projector": (IM / "ali-1005011752099805.jpg", "HY300", 198), "keyboard": (IM / "ali-1005007345135328.jpg", "GMK87", 183),
    "ugreen": (AD / "t_ugreen.jpg", "UGREEN", 47),
}


def grad(c1, c2, diag=False):
    im = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(c1, c2)) + (255,))
    return im


def tile(im, k, x, y, w, h, price_bg, label=True, rot=0, price=True, brand_bg=(10, 10, 10)):
    c = card(P[k][0], w, h, radius=26, pad=10, fit="contain")
    if rot:
        c = c.rotate(rot, expand=True, resample=Image.BICUBIC)
    shadow_paste(im, c, (int(x), int(y)), alpha=150, blur=16)
    cx = x + c.width / 2
    if label:
        pill(im, cx, y + 8, P[k][1], anton(34), (255, 255, 255), brand_bg, padx=18)
    if price:
        pill(im, cx, y + c.height - 8, f"₪{P[k][2]}", heb(900, 40), (255, 255, 255), price_bg, padx=20, outline=(255, 255, 255))


def cta(im, cx, cy, text, bg, fg, size=50):
    pill(im, cx, cy, text, heb(900, size), fg, bg, padx=46, outline=(255, 255, 255))


def confetti(im, colors, n=26, seed=1):
    r = random.Random(seed)
    for _ in range(n):
        c = Image.new("RGBA", (30, 16), (0, 0, 0, 0))
        ImageDraw.Draw(c).rectangle([0, 0, 29, 15], fill=r.choice(colors) + (255,))
        im.alpha_composite(c.rotate(r.randint(0, 180), expand=True), (r.randint(0, W - 30), r.randint(0, H - 30)))


# 1. BRANDS FOR LESS: black / yellow / red
def ad1():
    Y, R, K = (255, 210, 0), (230, 20, 35), (10, 10, 10)
    im = grad((26, 26, 30), (0, 0, 0))
    confetti(im, [Y, R, (255, 255, 255)], 22)
    b = brush(1200, 190, Y, 2, jag=20)
    bd = ImageDraw.Draw(b)
    bd.text((600, 70), "BRANDS FOR LESS", font=anton(110), fill=K, anchor="mm")
    T(bd, (600, 152), "מותגים אמיתיים במחירי דיל · כל יום", heb(900, 44), R)
    shadow_paste(im, b.rotate(-1.5, expand=True, resample=Image.BICUBIC), (40, 14), alpha=140)
    for i, k in enumerate(["adidas", "logitech", "stanley", "casio"]):
        tile(im, k, 48 + i * 300, 245, 280, 300, R, rot=[-3, 2, -2, 3][i])
    cta(im, W / 2, 650, "הצטרפו לערוץ הדילים בטלגרם", Y, K, 50)
    return im


# 2. Price-sticker wall: electric blue / red / white
def ad2():
    B, R = (30, 110, 255), (255, 40, 60)
    im = grad(B, (8, 30, 120))
    d = ImageDraw.Draw(im)
    T(d, (1000, 150), "הדיל הבא", heb(900, 96), (255, 255, 255))
    T(d, (1000, 255), "כבר בערוץ", heb(900, 96), (255, 214, 60))
    T(d, (1000, 360), "אמזון · אליאקספרס · מותגים", heb(800, 36), (220, 230, 255))
    T(d, (1000, 410), "מאות דילים חדשים כל יום", heb(800, 36), (220, 230, 255))
    for i, (k, x, y, r) in enumerate([("reebok", 40, 30, -4), ("baseus", 390, 45, 3), ("owala", 60, 375, 3), ("fossil", 390, 385, -3)]):
        tile(im, k, x, y, 290, 280, R, rot=r)
    cta(im, 1000, 560, "הצטרפו בחינם", R, (255, 255, 255), 54)
    T(d, (1000, 655), "@ilamazondeals", heb(800, 38), (255, 214, 60))
    return im


# 3. TECH DEALS: crisp neon, black / acid lime / hot orange
def ad3():
    L, O = (198, 255, 0), (255, 96, 32)
    im = grad((12, 12, 40), (4, 4, 14))
    for (x1, y1, x2, y2, c) in [(30, 60, 150, 20, L), (1130, 40, 1250, 90, O), (40, 690, 170, 640, O), (1120, 680, 1250, 630, L)]:
        glow_line(im, (x1, y1), (x2, y2), c, 8)
    d = ImageDraw.Draw(im)
    for dx, dy, col in [(6, 7, (0, 0, 0))]:
        d.text((W / 2 + dx, 95 + dy), "TECH DEALS", font=anton(130), fill=col, anchor="mm", stroke_width=8, stroke_fill=col)
    d.text((W / 2, 95), "TECH DEALS", font=anton(130), fill=(255, 255, 255), anchor="mm", stroke_width=8, stroke_fill=L)
    T(d, (W / 2, 198), "גאדג'טים, גיימינג ובית חכם במחירים שווים", heb(900, 44), O)
    for i, k in enumerate(["ugreen", "8bitdo", "keyboard", "baseus"]):
        x = 55 + i * 298
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(fr).rounded_rectangle([x - 4, 246, x + 274, 538], radius=30, outline=[L, O][i % 2] + (255,), width=12)
        im.alpha_composite(fr.filter(ImageFilter.GaussianBlur(10)))
        tile(im, k, x, 250, 270, 285, O if i % 2 == 0 else (30, 30, 30), label=False)
        ImageDraw.Draw(im).rounded_rectangle([x, 250, x + 270, 535], radius=26, outline=[L, O][i % 2], width=5)
    cta(im, W / 2, 640, "הצטרפו לערוץ הדילים בחינם", L, (10, 10, 20), 48)
    return im


# 4. "Your feed" concept: magenta, stacked deal bubbles like channel posts
def ad4():
    M, V, Y = (255, 30, 140), (110, 0, 230), (255, 230, 0)
    im = grad(M, V)
    confetti(im, [Y, (255, 255, 255), (20, 10, 40)], 18, 5)
    d = ImageDraw.Draw(im)
    T(d, (330, 165), "ככה נראה", heb(900, 92), (255, 255, 255))
    T(d, (330, 270), "הפיד שלך", heb(900, 92), Y)
    T(d, (330, 360), "כשאתה בערוץ 🔥".replace(" 🔥", ""), heb(900, 56), (255, 255, 255))
    cta(im, 330, 500, "הצטרפו לערוץ", Y, (20, 10, 40), 58)
    T(d, (330, 600), "@ilamazondeals", heb(800, 40), (255, 255, 255))
    rows = [("adidas", "נעלי ריצה Adidas"), ("logitech", "עכבר Logitech"), ("cerave", "ג׳ל ניקוי CeraVe"), ("stanley", "ספל Stanley")]
    for i, (k, txt) in enumerate(rows):
        x, y, w, h = 650 + (i % 2) * 30, 40 + i * 168, 580, 150
        bub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bub)
        bd.rounded_rectangle([0, 0, w - 1, h - 1], radius=34, fill=(255, 255, 255, 255))
        th = card(P[k][0], 130, 130, radius=20, pad=4, fit="contain")
        bub.alpha_composite(th, (w - 140, 10))
        T(bd, (w - 160, 42), "🔥 דיל חדש".replace("🔥 ", ""), heb(800, 30), M, anchor="rm")
        T(bd, (w - 160, 88), txt, heb(900, 34), (20, 10, 40), anchor="rm")
        bd.rounded_rectangle([20, 85, 160, 135], radius=25, fill=V + (255,))
        T(bd, (90, 110), f"₪{P[k][2]}", heb(900, 34), (255, 255, 255))
        shadow_paste(im, bub, (x, y), alpha=120, blur=14)
    return im


# 5. Join + giveaway hook: turquoise / orange / black
def ad5():
    TQ, O, K = (0, 220, 220), (255, 110, 20), (6, 10, 22)
    im = grad(TQ, (0, 90, 170))
    confetti(im, [O, K, (255, 255, 255)], 24, 9)
    b = brush(700, 250, K, 3, jag=18)
    bd = ImageDraw.Draw(b)
    T(bd, (350, 80), "הצטרפו לערוץ", heb(900, 74), (255, 255, 255))
    T(bd, (350, 175), "ותיכנסו להגרלה", heb(900, 64), O)
    shadow_paste(im, b.rotate(-2, expand=True, resample=Image.BICUBIC), (560, 30), alpha=140)
    s = Image.new("RGBA", (620, 190), (0, 0, 0, 0))
    sd = ImageDraw.Draw(s)
    sd.rectangle([0, 0, 619, 189], fill=(255, 255, 255))
    sd.text((310, 85), "$50 AMAZON", font=anton(110), fill=O, anchor="mm")
    T(sd, (310, 165), "גיפט קארד לאמזון · ההגרלה ב-1.12", heb(800, 30), K)
    shadow_paste(im, s.rotate(1.5, expand=True, resample=Image.BICUBIC), (600, 300), alpha=150)
    for k, x, y, r in [("reebok", 30, 30, -4), ("logitech", 290, 55, 3), ("owala", 40, 380, 3), ("casio", 295, 400, -3)]:
        tile(im, k, x, y, 230, 215, O, rot=r)
    cta(im, 910, 600, "ועוד מאות דילים כל יום", O, (255, 255, 255), 50)
    return im


def main():
    OUT.mkdir(exist_ok=True)
    for i, fn in enumerate([ad1, ad2, ad3, ad4, ad5], 1):
        p = OUT / f"tgad_{i}.png"
        fn().convert("RGB").save(p)
        print(p)


if __name__ == "__main__":
    main()
