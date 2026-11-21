"""Telegram Ads giveaway image, DEAL CITY style, square.
  python tools/tg_ad_city.py -> out/tg_ad_dealcity.png
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import dealcity as D
import promo2 as p2
from ad import F, text_c, size

W = H = 1080
G, T, CTA = 10, 330, 190


def giveaway_badge(im, cx, cy):
    bw, bh = 820, 96
    b = Image.new("RGBA", (bw + 12, bh + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle([10, 12, bw + 10, bh + 10], radius=22, fill=(0, 0, 0, 255))
    d.rounded_rectangle([0, 0, bw, bh], radius=22, fill=D.PINK + (255,), outline=(255, 240, 150, 255), width=6)
    d.text((bw - 36, bh / 2), "הגרלה!", font=F(900, 54), fill=(255, 240, 150), anchor="rm")
    d.text((36, bh / 2 + 2), "$50 GIFT CARD", font=D.ANTON(62), fill=D.WHITE, anchor="lm")
    b = b.rotate(-2, expand=True, resample=Image.BICUBIC)
    im.paste(b, (int(cx - b.width / 2), int(cy - b.height / 2)), b)


def main():
    im = Image.new("RGB", (W, H), D.BLACK)
    im.paste(D.title_panel(W - 2 * G, T - 2 * G, big=170, sub="."), (G, G))
    giveaway_badge(im, W / 2, 258)
    P = [("tga_gecko", (0, T, 360, H - CTA), "שממית מטפסת", 23.93),
         ("tga_monitor", (360, T, 720, H - CTA), "מסך גיימינג נייד", 126.69),
         ("tga_coffee", (720, T, 1080, H - CTA), "שבלונות לקפה", 16.63)]
    for name, box, he, usd in P:
        bx = (box[0] + G, box[1] + G, box[2] - G, box[3] - G)
        im.paste(D.photo_contain(name, bx), bx[:2])
        D.price_sticker(im, bx[2] - 8, bx[1] + 14, D.ils(usd))
        D.name_tag(im, bx[0] + 12, bx[3] - 12, he, bx[2] - bx[0] - 24)
    cta = D.compose(W, H, [], CTA)
    im.paste(cta.crop((0, H - CTA, W, H)), (0, H - CTA))
    out = D.OUT / "tg_ad_dealcity.png"
    D.OUT.mkdir(exist_ok=True)
    im.save(out)
    print(out)


if __name__ == "__main__":
    main()
