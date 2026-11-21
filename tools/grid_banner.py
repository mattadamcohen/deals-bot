"""3-post Instagram grid banner (pin as the top row). One 3240x1440 panorama -> 3 x 1080x1440 tiles.
  python tools/grid_banner.py -> out/grid_full.png, out/grid_1.png (left) .. grid_3.png (right)"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import promo2 as p2
from ad import F, text_c, size
from dealcity import ANTON, BEBAS, SUNSET, palm, skyline, gradient_text, BLACK, WHITE, PINK, ORANGE, TEAL

OUT = Path(__file__).resolve().parent.parent / "out"
W, H, T = 3240, 1440, 1080


def fit(d, s, font, maxw, start):
    fs = start
    while size(d, s, font(fs))[0] > maxw:
        fs -= 4
    return font(fs)


def banner():
    im = p2.gradient(W, H, SUNSET).convert("RGB")
    d = ImageDraw.Draw(im)
    # big striped retro sun in the middle tile
    sx, sy, r = W / 2, H * .66, 520
    sun = Image.new("L", im.size, 0)
    sd = ImageDraw.Draw(sun)
    sd.ellipse([sx - r, sy - r, sx + r, sy + r], fill=255)
    for i in range(8):
        yy = sy + r * (.05 + i * .12)
        sd.rectangle([0, yy, W, yy + 6 + i * 4], fill=0)
    im.paste(p2.gradient(W, H, [(255, 245, 160), (255, 130, 90), (255, 60, 150)]).convert("RGB"), (0, 0), sun)
    horizon = int(H * .86)
    skyline(d, horizon, W, (60, 10, 70), seed=9)
    d.rectangle([0, horizon, W, H], fill=(28, 4, 40))
    for i in range(1, 9):
        yy = horizon + i * 14
        half = r * (1 - i * .1)
        d.line([(sx - half, yy), (sx + half, yy)], fill=(255, 120, 140), width=4)
    for x, h, lean in ((80, 1250, 1), (300, 880, .6), (W - 90, 1300, -1), (W - 330, 900, -.6)):
        palm(d, x, H, h, lean, (18, 0, 28))
    p2.confetti(im, 120, 21, [PINK, ORANGE, TEAL, WHITE], area=(0, 0, W, int(H * .55)))
    # logo top-left tile
    p2.logo(im, 200, 190, 230, ORANGE)
    d = ImageDraw.Draw(im)
    # text that only reads across all three tiles
    text_c(d, W / 2, 150, "WELCOME TO", BEBAS(190), WHITE, stroke=8, sfill=BLACK)
    gradient_text(im, W / 2, 560, "THE HOTTEST DEALS", fit(d, "THE HOTTEST DEALS", ANTON, W - 260, 480),
                  [(255, 250, 190), (255, 160, 60), (255, 50, 140)], ow=14, shadow=(18, 18))
    d = ImageDraw.Draw(im)
    he = "ברוכים הבאים לדילים הכי חמים בישראל"
    f = fit(d, he, lambda s: F(900, s), W - 600, 150)
    tw, th, _ = size(d, he, f)
    d.rectangle([W / 2 - tw / 2 - 50, 850, W / 2 + tw / 2 + 50, 850 + th + 60], fill=BLACK)
    text_c(d, W / 2, 878, he, f, WHITE)
    parts = ["AMAZON", "ALIEXPRESS", "משלוח חינם", "t.me/ilamazondeals"]
    pill_f, gap = F(800, 72), 110
    ws = [size(d, t, pill_f)[0] for t in parts]
    total = sum(ws) + gap * (len(parts) - 1)
    y, ph = 1105, size(d, "AMAZON", pill_f)[1]
    d.rounded_rectangle([W / 2 - total / 2 - 70, y - 26, W / 2 + total / 2 + 70, y + ph + 34], radius=70, fill=PINK)
    x = W / 2 - total / 2
    for i, (t, w) in enumerate(zip(parts, ws)):
        text_c(d, x + w / 2, y, t, pill_f, WHITE)
        x += w
        if i < len(parts) - 1:
            cx, cy = x + gap / 2, y + ph / 2 + 4
            d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(255, 230, 120))
            x += gap
    return im


if __name__ == "__main__":
    # Posts are 4:5 (1080x1350, the API max); the profile grid shows the centre 3:4 crop (1012 wide).
    # So the visible strips (1012 each) must join up; each post carries 34px of overlap on both sides.
    VIS, PAD, PH = 1012, 34, 1350
    CW = 3 * VIS + 2 * PAD
    W = round(CW * 1440 / PH)
    OUT.mkdir(exist_ok=True)
    im = banner().resize((CW, PH), Image.LANCZOS)
    im.save(OUT / "grid_full.png")
    pv = Image.new("RGB", (3 * VIS + 12, PH), (0, 0, 0))
    for i in range(3):
        tile = im.crop((i * VIS, 0, i * VIS + 1080, PH))
        tile.save(OUT / f"grid_{i + 1}.jpg", quality=95)
        pv.paste(tile.crop((PAD, 0, PAD + VIS, PH)), (i * (VIS + 6), 0))
    pv.resize((1086, 482)).save(OUT / "grid_preview.png")
    print("ok")
