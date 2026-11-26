"""Telegram ad idea #3: 'Brands at deal prices' (16:9). python tools/tg_ad_brands.py -> out/tgad_brands.png"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent))
from promo_styles import T, heb, anton, pill, shadow_paste, glow_line, OUT
from tg_ad5 import P, tile, grad, confetti, W, H

im = grad((40, 120, 255), (6, 22, 110))
spot = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(spot).ellipse([-200, -100, 900, 820], fill=(80, 200, 255, 110))
im.alpha_composite(spot.filter(ImageFilter.GaussianBlur(160)))
import random
r = random.Random(11)
for _ in range(26):
    c = Image.new("RGBA", (30, 16), (0, 0, 0, 0))
    ImageDraw.Draw(c).rectangle([0, 0, 29, 15], fill=r.choice([(255, 214, 0), (255, 40, 60), (255, 255, 255)]) + (255,))
    x = r.choice([r.randint(0, 640), r.randint(1200, 1250)]); y = r.randint(0, H - 30)
    im.alpha_composite(c.rotate(r.randint(0, 180), expand=True), (x, y))
for (a, b, c) in [((60, 40), (170, 20), (90, 230, 255)), ((1150, 690), (1260, 650), (255, 80, 200)), ((620, 700), (720, 680), (90, 230, 255))]:
    glow_line(im, a, b, c, 7)
# product fan on the left
spots = [("adidas", 40, 30, -5), ("logitech", 335, 22, 4), ("casio", 50, 380, 4), ("stanley", 335, 372, -4)]
for k, x, y, r in spots:
    tile(im, k, x, y, 260, 255, (255, 40, 60), rot=r, brand_bg=(8, 20, 90))
d = ImageDraw.Draw(im)
X = 960
T(d, (X, 110), "מותגים אמיתיים.", heb(900, 84), (255, 255, 255))
T(d, (X, 215), "מחירי דיל.", heb(900, 96), (255, 214, 0))
T(d, (X, 320), "כל יום.", heb(900, 84), (255, 255, 255))
d.text((X, 410), "ADIDAS · LOGITECH · CASIO · STANLEY", font=anton(40), fill=(200, 225, 255), anchor="mm")
T(d, (X, 470), "ועוד מאות מותגים מאמזון ואליאקספרס", heb(700, 34), (220, 232, 255))
pill(im, X, 570, "הצטרפו לערוץ בחינם", heb(900, 52), (10, 10, 30), (255, 214, 0), padx=48, outline=(255, 255, 255))
T(ImageDraw.Draw(im), (X, 660), "@ilamazondeals", heb(800, 40), (255, 255, 255))
OUT.mkdir(exist_ok=True)
im.convert("RGB").save(OUT / "tgad_brands.png")
print("ok")
