"""Telegram Ads giveaway image, DEAL CITY style, 16:9 (1920x1080).
  python tools/tg_ad_city_wide.py -> out/tg_ad_dealcity_16x9.png
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import dealcity as D
from ad import F, text_c
from tg_ad_city import giveaway_badge

W, H, G, CTA, LW = 1920, 1080, 10, 200, 760


def main():
    im = Image.new("RGB", (W, H), D.BLACK)
    im.paste(D.title_panel(LW - 2 * G, H - CTA - 2 * G, big=150, sub="."), (G, G))
    giveaway_badge(im, LW / 2, (H - CTA) * 0.70, bw=660)
    d = ImageDraw.Draw(im)
    more, fm = "ועוד מאות מוצרים!", F(900, 64)
    from ad import size
    mw, mh, _ = size(d, more, fm)
    my = (H - CTA) * 0.70 + 90
    d.rectangle([LW / 2 - mw / 2 - 30, my, LW / 2 + mw / 2 + 30, my + mh + 34], fill=D.BLACK, outline=D.TEAL, width=4)
    text_c(d, LW / 2, my + 15, more, fm, D.TEAL)
    pw = (W - LW) / 3
    P = [("tga_gecko", "שממית מטפסת", 23.93), ("tga_monitor", "מסך גיימינג נייד", 126.69), ("tga_coffee", "שבלונות לקפה", 16.63)]
    for i, (name, he, usd) in enumerate(P):
        box = (int(LW + i * pw), 0, int(LW + (i + 1) * pw), H - CTA)
        bx = (box[0] + G, box[1] + G, box[2] - G, box[3] - G)
        im.paste(D.photo_contain(name, bx), bx[:2])
        D.price_sticker(im, bx[2] - 8, bx[1] + 14, D.ils(usd))
        D.name_tag(im, bx[0] + 12, bx[3] - 12, he, bx[2] - bx[0] - 24)
    cta = D.compose(W, H, [], CTA)
    im.paste(cta.crop((0, H - CTA, W, H)), (0, H - CTA))
    out = D.OUT / "tg_ad_dealcity_16x9.png"
    im.save(out)
    print(out)


if __name__ == "__main__":
    main()
