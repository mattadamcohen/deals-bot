"""Telegram Ads image for the giveaway (square, party style).
  python tools/tg_ad.py -> out/tg_ad_giveaway.png
"""
import math, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import promo2 as P
from ad import F, text_c

W = H = 1080
YEL, ORA, PINK, PURP, WHITE = P.YEL, P.ORA, P.PINK, P.PURP, P.WHITE
CYAN = (90, 220, 255)


def gift_box(d, cx, cy, s, body, ribbon):
    w, h = s, s * 0.8
    d.rectangle([cx - w / 2, cy - h / 2 + s * 0.18, cx + w / 2, cy + h / 2], fill=body)
    d.rectangle([cx - w / 2 - s * 0.06, cy - h / 2, cx + w / 2 + s * 0.06, cy - h / 2 + s * 0.2], fill=body)
    d.rectangle([cx - s * 0.08, cy - h / 2, cx + s * 0.08, cy + h / 2], fill=ribbon)
    d.rectangle([cx - w / 2 - s * 0.06, cy - h / 2 + s * 0.06, cx + w / 2 + s * 0.06, cy - h / 2 + s * 0.14], fill=ribbon)
    for sgn in (-1, 1):
        d.ellipse([cx + sgn * s * 0.04 - s * 0.16 + sgn * s * 0.1, cy - h / 2 - s * 0.2,
                   cx + sgn * s * 0.04 + s * 0.16 + sgn * s * 0.1, cy - h / 2 + s * 0.02], outline=ribbon, width=max(6, int(s * 0.07)))


def gift_card(base, cx, cy, w, h, tilt):
    card = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([28, 32, w + 28, h + 32], radius=34, fill=(0, 0, 0, 90))
    g = P.gradient(w, h, [(30, 40, 70), (20, 25, 45)], vertical=False).convert("RGBA")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=34, fill=255)
    card.paste(g, (20, 20), m)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([20, 20, w + 20, h + 20], radius=34, outline=YEL, width=6)
    d.text((w - 10, 70), "GIFT CARD", font=F(900, 46), fill=WHITE, anchor="rm")
    d.text((w / 2 + 20, h / 2 + 60), "$50", font=F(900, 160), fill=YEL, anchor="mm")
    card = card.rotate(tilt, resample=Image.BICUBIC, expand=True)
    base.paste(card, (int(cx - card.width / 2), int(cy - card.height / 2)), card)


def main():
    im = P.gradient(W, H, [(110, 195, 255), (255, 200, 90), (255, 110, 60)]).convert("RGB")
    d = ImageDraw.Draw(im)
    pts = [(x, 46 + 34 * math.sin(x / 160)) for x in range(-20, W + 40, 20)]
    d.line(pts, fill=(60, 40, 90), width=4)
    for i, (x, y) in enumerate(pts[::4]):
        d.ellipse([x - 12, y + 4, x + 12, y + 32], fill=[YEL, PINK, CYAN, (140, 255, 120)][i % 4])
    for bx, by, c in ((90, 640, PINK), (190, 560, CYAN), (W - 95, 620, YEL), (W - 195, 545, PINK)):
        d.line([(bx, by + 85), (bx + 10, by + 300)], fill=WHITE, width=3)
        d.ellipse([bx - 64, by - 82, bx + 64, by + 82], fill=c)
        d.ellipse([bx - 36, by - 58, bx - 14, by - 22], fill=WHITE)
    P.confetti(im, 110, 5, [PINK, YEL, CYAN, PURP, WHITE])
    P.logo(im, W / 2, 150, 130, WHITE)
    P.fancy_text(im, W / 2, 300, "הגרלה!", F(900, 120), [(255, 240, 120), (255, 150, 40), (255, 70, 120)], tilt=3)
    P.fancy_text(im, W / 2, 410, "גיפט קארד לאמזון", F(900, 74), [(255, 255, 255), (230, 220, 255)], outline=(90, 20, 120), ow=8)
    d = ImageDraw.Draw(im)
    gift_box(d, 310, 650, 150, PINK, YEL)
    gift_box(d, 780, 670, 120, PURP, CYAN)
    gift_card(im, W / 2 + 10, 630, 430, 260, -6)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 840, W, H], fill=(70, 20, 130))
    d.rectangle([0, 840, W, 852], fill=YEL)
    text_c(d, W / 2, 875, "הצטרפו לערוץ ואתם בהגרלה", F(900, 56), YEL)
    text_c(d, W / 2, 950, "דילים יומיים מאמזון ואליאקספרס · משלוח לארץ", F(800, 36), WHITE)
    text_c(d, W / 2, 1005, "ההגרלה ב-1.12 · t.me/ilamazondeals", F(800, 34), WHITE)
    out = P.REPO / "out" / "tg_ad_giveaway.png"
    out.parent.mkdir(exist_ok=True)
    im.save(out)
    print(out)


if __name__ == "__main__":
    main()
