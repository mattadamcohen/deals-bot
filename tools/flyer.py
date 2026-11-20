"""Black & white printable flyers with Matt's exact Telegram QR code.
  out/flyer_a4.pdf (A4 poster with tear-off tabs) and out/stickers_a4.pdf (4 A6 stickers per page)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
from ad import F, kw, size, text_c

REPO = Path(__file__).resolve().parent.parent
QR_SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/user-data/uploads/e9f2ee30-image.png")
BLACK, WHITE = (0, 0, 0), (255, 255, 255)
DPI = 300


def qr_card():
    im = Image.open(QR_SRC).convert("RGB")
    card = im.crop((138, 607, 943, 1468))  # the white QR card exactly as provided
    # remove the dark screenshot background showing in the rounded corners
    m = Image.new("L", card.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([3, 3, card.width - 4, card.height - 4], radius=92, fill=255)
    out = Image.new("RGB", card.size, WHITE)
    out.paste(card, (0, 0), m)
    return out


def check_line(d, cx, y, items, f):
    """'✔ item' x3, laid out right-to-left with drawn check marks."""
    widths = [size(d, t, f)[0] for t in items]
    box = f.size * 0.9
    gap = f.size * 1.2
    total = sum(widths) + len(items) * (box + 18) + gap * (len(items) - 1)
    x = cx + total / 2
    for t, w in zip(items, widths):
        # check box on the right of each item (Hebrew reading order)
        d.rounded_rectangle([x - box, y, x, y + box], radius=10, outline=BLACK, width=6)
        d.line([(x - box * 0.78, y + box * 0.52), (x - box * 0.55, y + box * 0.78), (x - box * 0.18, y + box * 0.22)], fill=BLACK, width=9)
        x -= box + 18
        tw, th, b = size(d, t, f)
        d.text((x - tw - b[0], y + box / 2 - th / 2 - b[1]), t, font=f, fill=BLACK, **kw(t))
        x -= tw + gap


def arrow_down(d, cx, y, s):
    d.rectangle([cx - s * 0.18, y, cx + s * 0.18, y + s * 0.7], fill=BLACK)
    d.polygon([(cx - s * 0.5, y + s * 0.6), (cx + s * 0.5, y + s * 0.6), (cx, y + s * 1.15)], fill=BLACK)


def poster():
    W, H = 2480, 3508  # A4 @ 300dpi
    im = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(im)
    # header band
    d.rectangle([0, 0, W, 900], fill=BLACK)
    text_c(d, W / 2, 90, "דילים מטורפים", F(900, 240), WHITE)
    text_c(d, W / 2, 370, "מאמזון ואליאקספרס", F(900, 160), WHITE)
    text_c(d, W / 2, 580, "כל יום בערוץ הטלגרם שלנו", F(800, 86), WHITE)
    text_c(d, W / 2, 735, "Hottest Amazon & AliExpress Deals", F(900, 92), WHITE)
    # call to action
    text_c(d, W / 2, 960, "סרקו והצטרפו בחינם", F(900, 140), BLACK)
    arrow_down(d, W / 2, 1150, 110)
    # QR card with a thick frame
    card = qr_card()
    cw = 1120
    card = card.resize((cw, int(card.height * cw / card.width)), Image.LANCZOS)
    x, y = (W - cw) // 2, 1320
    d.rounded_rectangle([x - 36, y - 36, x + cw + 36, y + card.height + 36], radius=170, fill=BLACK)
    m = Image.new("L", card.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=140, fill=255)
    im.paste(card, (x, y), m)
    yb = y + card.height + 85
    check_line(d, W / 2, yb, ["הכי נמכרים", "משלוח לארץ", "מחירים בשקלים"], F(800, 70))
    text_c(d, W / 2, yb + 120, "Deals with free shipping to Israel", F(800, 62), BLACK)
    text_c(d, W / 2, yb + 210, "Join our Telegram community now!", F(900, 70), BLACK)
    # tear-off tabs
    top = H - 560
    n = 8
    tw_ = W / n
    for i in range(n + 1):
        xx = i * tw_
        for yy in range(int(top), H, 40):
            d.line([(xx, yy), (xx, yy + 20)], fill=BLACK, width=4)
    for xx in range(0, W, 40):
        d.line([(xx, top), (xx + 20, top)], fill=BLACK, width=4)
    tab = Image.new("RGB", (560, int(tw_) - 30), WHITE)
    td = ImageDraw.Draw(tab)
    text_c(td, 280, 20, "t.me/ilamazondeals", F(800, 46), BLACK)
    text_c(td, 280, 110, "דילים מאמזון ואלי", F(900, 54), BLACK)
    tab = tab.rotate(90, expand=True)
    for i in range(n):
        im.paste(tab, (int(i * tw_ + (tw_ - tab.width) / 2), int(top + 0)))
    return im


def sticker(w, h):
    im = Image.new("RGB", (w, h), WHITE)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([12, 12, w - 12, h - 12], radius=60, outline=BLACK, width=14)
    d.rounded_rectangle([12, 12, w - 12, 400], radius=60, fill=BLACK)
    d.rectangle([12, 200, w - 12, 400], fill=BLACK)
    text_c(d, w / 2, 50, "דילים מאמזון ואליאקספרס", F(900, 90), WHITE)
    text_c(d, w / 2, 180, "סרקו והצטרפו לערוץ בחינם", F(800, 62), WHITE)
    text_c(d, w / 2, 285, "Hottest Amazon & AliExpress Deals", F(800, 54), WHITE)
    card = qr_card()
    cw = int(w * 0.62)
    card = card.resize((cw, int(card.height * cw / card.width)), Image.LANCZOS)
    m = Image.new("L", card.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=110, fill=255)
    im.paste(card, ((w - cw) // 2, 440), m)
    yy = 440 + card.height + 30
    text_c(d, w / 2, yy, "הכי נמכרים · משלוח לארץ · מחירים בשקלים", F(800, 50), BLACK)
    text_c(d, w / 2, yy + 80, "Free shipping deals to Israel", F(800, 46), BLACK)
    text_c(d, w / 2, yy + 150, "Join our Telegram community now!", F(900, 52), BLACK)
    return im


def sticker_sheet():
    W, H = 2480, 3508
    sheet = Image.new("RGB", (W, H), WHITE)
    sw, sh = W // 2, H // 2
    s = sticker(sw - 60, sh - 60)
    for r in range(2):
        for c in range(2):
            sheet.paste(s, (c * sw + 30, r * sh + 30))
    d = ImageDraw.Draw(sheet)
    for xx in range(0, W, 40):  # cut guides
        d.line([(xx, H // 2), (xx + 18, H // 2)], fill=(150, 150, 150), width=3)
    for yy in range(0, H, 40):
        d.line([(W // 2, yy), (W // 2, yy + 18)], fill=(150, 150, 150), width=3)
    return sheet


if __name__ == "__main__":
    out = REPO / "out"
    out.mkdir(exist_ok=True)
    p = poster()
    p.save(out / "flyer_a4.png")
    p.save(out / "flyer_a4.pdf", resolution=DPI)
    s = sticker_sheet()
    s.save(out / "stickers_a4.png")
    s.save(out / "stickers_a4.pdf", resolution=DPI)
    print("ok")
