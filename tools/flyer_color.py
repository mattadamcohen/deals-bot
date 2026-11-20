"""Colour A4 flyers (party / blue confetti styles) with Matt's exact Telegram QR code.
  -> out/flyer_party_a4.pdf, out/flyer_confetti_a4.pdf"""
import math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).parent))
import promo2 as p2, flyer
from ad import F, text_c

REPO = flyer.REPO
W, H = 2480, 3508
YEL, ORA, PINK, PURP, NAVY, WHITE, INK = p2.YEL, p2.ORA, p2.PINK, p2.PURP, p2.NAVY, p2.WHITE, p2.INK


def qr_block(im, cx, y, cw, frame, frame_w=40, radius=150):
    card = flyer.qr_card()
    card = card.resize((cw, int(card.height * cw / card.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    x = cx - cw // 2
    sh = Image.new("L", im.size)
    ImageDraw.Draw(sh).rounded_rectangle([x - frame_w + 20, y - frame_w + 30, x + cw + frame_w + 20, y + card.height + frame_w + 30],
                                         radius=radius + 30, fill=130)
    im.paste((30, 0, 50), (0, 0), sh.filter(ImageFilter.GaussianBlur(30)))
    d.rounded_rectangle([x - frame_w, y - frame_w, x + cw + frame_w, y + card.height + frame_w], radius=radius + 30, fill=frame)
    m = Image.new("L", card.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=radius, fill=255)
    im.paste(card, (x, y), m)
    return y + card.height + frame_w


def ticks(d, cx, y, items, f, fill, box_fill):
    flyer_check = flyer.check_line
    # reuse the B&W check layout but in colour: draw on a temp layer then tint
    layer = Image.new("RGBA", (W, int(f.size * 1.6)), (0, 0, 0, 0))
    flyer_check(ImageDraw.Draw(layer), cx, 0, items, f)
    col = Image.new("RGBA", layer.size, fill + (255,))
    col.putalpha(layer.split()[3])
    return col


def party():
    im = p2.gradient(W, H, [(120, 200, 255), (255, 205, 100), (255, 125, 70)]).convert("RGB")
    d = ImageDraw.Draw(im)
    pts = [(x, 130 + 80 * math.sin(x / 380)) for x in range(-40, W + 80, 40)]
    d.line(pts, fill=(60, 40, 90), width=8)
    for i, (x, y) in enumerate(pts[::4]):
        d.ellipse([x - 28, y + 8, x + 28, y + 74], fill=[YEL, PINK, (90, 220, 255), (140, 255, 120)][i % 4])
    for bx, by, c in ((190, 2050, PINK), (400, 1880, (90, 200, 255)), (W - 200, 2000, YEL), (W - 420, 1850, PINK)):
        d.line([(bx, by + 200), (bx + 20, by + 800)], fill=WHITE, width=6)
        d.ellipse([bx - 160, by - 200, bx + 160, by + 200], fill=c)
        d.ellipse([bx - 95, by - 150, bx - 35, by - 60], fill=WHITE)
    p2.confetti(im, 260, 3, [PINK, YEL, (90, 220, 255), PURP, WHITE], area=(0, 0, W, H))
    p2.logo(im, W / 2, 380, 300, WHITE)
    p2.fancy_text(im, W / 2, 740, "CRAZY DEALS!", F(900, 260), [(255, 240, 120), (255, 150, 40), (255, 70, 120)], ow=24, tilt=3)
    p2.fancy_text(im, W / 2, 1040, "דילים מטורפים", F(900, 220), [(255, 230, 90), (255, 120, 50)], outline=(90, 20, 120), ow=20, tilt=2)
    p2.fancy_text(im, W / 2, 1260, "מאמזון ואליאקספרס", F(900, 150), [(255, 255, 255), (230, 220, 255)], outline=(90, 20, 120), ow=16)
    d = ImageDraw.Draw(im)
    text_c(d, W / 2, 1420, "Hottest Amazon & AliExpress Deals", F(900, 96), (70, 20, 130))
    yb = qr_block(im, W // 2, 1640, 1000, PURP)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 2900, W, H], fill=(70, 20, 130))
    d.rectangle([0, 2900, W, 2925], fill=YEL)
    text_c(d, W / 2, 2965, "סרקו והצטרפו לערוץ הטלגרם בחינם!", F(900, 112), YEL)
    text_c(d, W / 2, 3130, "הכי נמכרים · משלוח לארץ · מחירים בשקלים", F(800, 78), WHITE)
    text_c(d, W / 2, 3255, "Free shipping deals to Israel · Join our Telegram community now!", F(800, 62), WHITE)
    text_c(d, W / 2, 3370, "t.me/ilamazondeals", F(900, 80), WHITE)
    return im


def confetti_blue():
    im = p2.gradient(W, H, [(20, 30, 200), (35, 60, 230), (20, 25, 170)]).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, H], outline=ORA, width=50)
    for pts, c in [([(140, 200), (320, 380), (200, 600), (390, 780)], (90, 230, 200)),
                   ([(W - 180, 260), (W - 360, 450), (W - 220, 680), (W - 420, 860)], ORA),
                   ([(170, 2200), (330, 2380), (220, 2560)], PINK), ([(W - 200, 2100), (W - 380, 2280), (W - 240, 2460)], (90, 230, 200))]:
        d.line(pts, fill=c, width=20, joint="curve")
    p2.confetti(im, 240, 9, [ORA, PINK, YEL, (90, 230, 200), WHITE, (255, 80, 80)], area=(60, 60, W - 60, H - 60))
    p2.logo(im, W / 2, 330, 280, ORA)
    d = ImageDraw.Draw(im)
    d.arc([300, 520, W - 300, 1200], start=190, end=330, fill=ORA, width=40)
    p2.fancy_text(im, W / 2, 790, "CRAZY", F(900, 400), [(255, 255, 255), (200, 210, 235)], outline=(190, 90, 0), ow=20, tilt=-4)
    p2.fancy_text(im, W / 2, 1090, "Deals!", F(900, 230), [(255, 255, 255), (210, 220, 240)], outline=(190, 90, 0), ow=16, tilt=-4)
    d = ImageDraw.Draw(im)
    text_c(d, W / 2, 1290, "הדילים הכי שווים מאמזון ואליאקספרס", F(900, 116), WHITE)
    text_c(d, W / 2, 1450, "Hottest Amazon & AliExpress Deals", F(800, 88), (255, 220, 160))
    yb = qr_block(im, W // 2, 1650, 980, WHITE, frame_w=34)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([W / 2 - 1000, 2930, W / 2 + 1000, 3130], radius=100, fill=WHITE)
    text_c(d, W / 2, 2965, "סרקו והצטרפו בחינם!", F(900, 110), NAVY)
    text_c(d, W / 2, 3190, "הכי נמכרים · משלוח לארץ · מחירים בשקלים", F(800, 76), WHITE)
    text_c(d, W / 2, 3305, "Join our Telegram community now!", F(900, 72), (255, 220, 160))
    return im


if __name__ == "__main__":
    out = REPO / "out"
    for name, fn in (("flyer_party_a4", party), ("flyer_confetti_a4", confetti_blue)):
        im = fn()
        im.save(out / f"{name}.png")
        im.save(out / f"{name}.pdf", resolution=300)
    print("ok")
