"""Instagram reel (1080x1920, ~11s) of 3 recent channel deals, same style as the first one.
  python tools/reel.py --auto   # after every `reel_every` new posts: render the 3 biggest deals and send to the owner
  python tools/reel.py --latest # render the latest 3 posts now and send
The video is sent to the owner's Telegram chat (config owner_chat_id) with a ready-to-paste Instagram caption."""
import json, math, os, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features
import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import bot  # shared helpers (shekel prices)
CONFIG = json.loads((REPO / "config.json").read_text())
W, H, FPS = 1080, 1920, 30
OUT = Path(tempfile.mkdtemp())
IMG = REPO / "data" / "images"
LOGO = REPO / "assets" / "ilamazondeals-logo.png"
F = lambda w, s: ImageFont.truetype(str(REPO / "assets" / "fonts" / f"Heebo-{w}.ttf"), s)
try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"
if not features.check("raqm"):
    sys.exit("Pillow has no raqm support: Hebrew would render backwards (install libfribidi0)")

BLUE, DEEP, NAVY = (10, 59, 196), (6, 36, 122), (10, 42, 143)
YEL, ORA, WHITE, BLACK = (255, 212, 59), (255, 159, 28), (255, 255, 255), (15, 15, 20)
GLOW = (31, 91, 255)

# color themes: (accent/pill, deep background, glow, dark text on accent, highlight)
THEMES = {
    "blue":   ((10, 59, 196), (6, 36, 122), (31, 91, 255), (10, 42, 143), (255, 212, 59)),
    "purple": ((109, 40, 217), (46, 16, 101), (139, 92, 246), (59, 7, 100), (255, 212, 59)),
    "teal":   ((13, 148, 136), (4, 55, 64), (20, 184, 166), (4, 47, 46), (255, 214, 102)),
    "coral":  ((220, 38, 38), (110, 18, 36), (248, 113, 113), (90, 12, 24), (255, 230, 109)),
    "night":  ((40, 40, 48), (8, 8, 12), (70, 70, 84), (20, 20, 24), (255, 196, 40)),
}
INTROS = [("דילים מאמזון", "עם משלוח חינם לארץ"), ("הכי נמכרים באמזון", "עם משלוח חינם לארץ"),
          ("3 מציאות מאמזון", "עם משלוח חינם לארץ"), ("מה כולם קונים?", "הלהיטים של אמזון השבוע")]
OUTROS = [("עוד דילים כל יום", "הצטרפו לערוץ בטלגרם"), ("רוצים עוד?", "כל הקישורים בטלגרם"),
          ("לא מפספסים דיל", "הצטרפו עכשיו לטלגרם")]
TEXT = {"intro": INTROS[0], "outro": OUTROS[0], "badge": "לקראת בלאק פריידיי וחנוכה"}


def season_badge():
    from datetime import datetime, timezone, timedelta
    d = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    if d < "2026-11-27":
        return "לקראת בלאק פריידיי וחנוכה"
    if d <= "2026-12-01":
        return "בלאק פריידיי כבר כאן"
    if d <= "2026-12-12":
        return "רעיונות למתנות לחנוכה"
    return "הדילים הכי חמים של השבוע"


def apply_theme(n):
    """Pick colors/texts for reel number n (Black Friday week always uses the dark 'night' theme)."""
    global BLUE, DEEP, GLOW, NAVY, YEL, _bg
    from datetime import datetime, timezone, timedelta
    d = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    names = ["blue", "purple", "teal", "coral", "night"]
    name = "night" if "2026-11-27" <= d <= "2026-12-01" else names[n % len(names)]
    BLUE, DEEP, GLOW, NAVY, YEL = THEMES[name]
    _bg = None
    TEXT["intro"] = INTROS[n % len(INTROS)]
    TEXT["outro"] = OUTROS[n % len(OUTROS)]
    TEXT["badge"] = season_badge()
    return name

DEALS = []  # filled in main()


def ease(t):  # easeOutBack-ish pop
    t = max(0.0, min(1.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


_bg = None
def background():
    global _bg
    if _bg is None:
        img = Image.new("RGB", (W, H), DEEP)
        g = Image.new("L", (W, H))
        gd = ImageDraw.Draw(g)
        for r in range(1400, 0, -20):
            gd.ellipse([W / 2 - r, 650 - r, W / 2 + r, 650 + r], fill=int(255 * (1 - r / 1400)))
        img.paste(Image.new("RGB", (W, H), GLOW), mask=g.filter(ImageFilter.GaussianBlur(60)))
        _bg = img
    return _bg.copy()


def text_c(d, y, s, font, fill=WHITE, x=W / 2):
    """Centered text, right-to-left aware."""
    rtl = any("֐" <= ch <= "׿" for ch in s)
    kw = {"direction": "rtl", "language": "he"} if rtl else {}
    b = d.textbbox((0, 0), s, font=font, **kw)
    d.text((x - (b[2] - b[0]) / 2 - b[0], y), s, font=font, fill=fill, **kw)
    return b[3] - b[1]


def pill(d, cx, cy, s, font, bg, fg, pad=(44, 18)):
    rtl = any("֐" <= ch <= "׿" for ch in s)
    kw = {"direction": "rtl", "language": "he"} if rtl else {}
    b = d.textbbox((0, 0), s, font=font, **kw)
    w, h = b[2] - b[0], b[3] - b[1]
    d.rounded_rectangle([cx - w / 2 - pad[0], cy - h / 2 - pad[1], cx + w / 2 + pad[0], cy + h / 2 + pad[1] + 6],
                        radius=(h + 2 * pad[1]) / 2, fill=bg)
    d.text((cx - w / 2 - b[0], cy - h / 2 - b[1]), s, font=font, fill=fg, **kw)


def paste_scaled(base, im, cx, cy, scale, alpha=1.0):
    if scale <= 0.01 or alpha <= 0:
        return
    w, h = max(1, int(im.width * scale)), max(1, int(im.height * scale))
    s = im.resize((w, h), Image.LANCZOS)
    if s.mode != "RGBA":
        s = s.convert("RGBA")
    if alpha < 1:
        a = s.getchannel("A").point(lambda v: int(v * alpha))
        s.putalpha(a)
    base.paste(s, (int(cx - w / 2), int(cy - h / 2)), s)


def burst(r, n=16):
    im = Image.new("RGBA", (2 * r + 20, 2 * r + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = r + 10
    pts = []
    for i in range(2 * n):
        a = math.pi * i / n - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.84
        pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
    d.polygon(pts, fill=YEL, outline=WHITE, width=8)
    return im


LOGO_IM = Image.open(LOGO).convert("RGBA")
mask = Image.new("L", LOGO_IM.size, 0)
ImageDraw.Draw(mask).ellipse([0, 0, *LOGO_IM.size], fill=255)
LOGO_IM.putalpha(mask)


def scene_intro(t, dur):
    im = background()
    d = ImageDraw.Draw(im)
    paste_scaled(im, LOGO_IM, W / 2, 610, 0.62 * ease(t / 0.45))
    a = smooth((t - 0.35) / 0.35)
    if a > 0:
        y = 1040 + 60 * (1 - a)
        text_c(d, y, TEXT["intro"][0], F(900, 132 if len(TEXT["intro"][0]) <= 14 else 112))
        text_c(d, y + 170, TEXT["intro"][1], F(800, 74 if len(TEXT["intro"][1]) <= 22 else 64), YEL)
    b = ease((t - 0.8) / 0.4)
    if b > 0:
        layer = Image.new("RGBA", (W, 220), (0, 0, 0, 0))
        pill(ImageDraw.Draw(layer), W / 2, 110, TEXT["badge"], F(800, 60), BLACK, WHITE)
        paste_scaled(im, layer, W / 2, 1520, b)
    return im


PROD = {}
def product_card(name):
    if name not in PROD:
        p = Image.open(IMG / name).convert("RGB")
        p.thumbnail((760, 760), Image.LANCZOS)
        PROD[name] = p
    return PROD[name]


def scene_deal(t, dur, i):
    deal = DEALS[i]
    im = background()
    d = ImageDraw.Draw(im)
    # header
    pill(d, W / 2, 190, f"דיל {i + 1} מתוך 3", F(800, 52), WHITE, BLUE)
    # white card sliding up
    a = smooth(t / 0.35)
    cy = 820 + 260 * (1 - a)
    card = Image.new("RGBA", (880, 880), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, 879, 879], radius=56, fill=WHITE)
    prod = product_card(deal["img"])
    z = 1.0 + 0.07 * (t / dur)
    pw, ph = int(prod.width * z), int(prod.height * z)
    pz = prod.resize((pw, ph), Image.LANCZOS)
    pz = pz.crop(((pw - min(pw, 800)) // 2, (ph - min(ph, 800)) // 2,
                  (pw - min(pw, 800)) // 2 + min(pw, 800), (ph - min(ph, 800)) // 2 + min(ph, 800)))
    card.paste(pz, ((880 - pz.width) // 2, (880 - pz.height) // 2))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([100, cy - 440 + 30, 980, cy + 440 + 30], radius=56, fill=(0, 8, 48, 110))
    im.paste(shadow.filter(ImageFilter.GaussianBlur(28)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(28)))
    im.paste(card, (100, int(cy - 440)), card)
    # discount burst
    b = ease((t - 0.3) / 0.35)
    if b > 0:
        bu = burst(150)
        bd = ImageDraw.Draw(bu)
        f = F(900, 92)
        s = f"-{deal['off']}" if deal["off"] else f"#{deal['rank']}"
        bb = bd.textbbox((0, 0), s, font=f)
        bd.text((160 - (bb[2] - bb[0]) / 2 - bb[0], 160 - (bb[3] - bb[1]) / 2 - bb[1]), s, font=f, fill=NAVY)
        bu = bu.rotate(12 * (1 - b) - 8, resample=Image.BICUBIC, expand=True)
        paste_scaled(im, bu, 870, cy - 400, b)
    # text
    c = smooth((t - 0.45) / 0.35)
    if c > 0:
        y = 1330 + 40 * (1 - c)
        text_c(d, y, deal["title"], F(900, 76))
        text_c(d, y + 112, deal["sub"], F(700, 50), (210, 222, 255))
        if deal["price"]:
            pill(d, W / 2, y + 270, deal["price"], F(900, 80), YEL, NAVY, pad=(54, 16))
    e = smooth((t - 0.75) / 0.3)
    if e > 0:
        pill(d, W / 2, 1810, "משלוח חינם לארץ מעל $49", F(800, 46), BLACK, WHITE)
    return im


def scene_outro(t, dur):
    im = background()
    d = ImageDraw.Draw(im)
    paste_scaled(im, LOGO_IM, W / 2, 640, 0.5 * ease(t / 0.4))
    a = smooth((t - 0.2) / 0.35)
    if a > 0:
        y = 1000 + 50 * (1 - a)
        text_c(d, y, TEXT["outro"][0], F(900, 104))
        text_c(d, y + 150, TEXT["outro"][1], F(800, 66), YEL)
    b = ease((t - 0.5) / 0.4)
    if b > 0:
        layer = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
        pill(ImageDraw.Draw(layer), W / 2, 120, "@ilamazondeals", F(900, 84), WHITE, BLUE, pad=(60, 24))
        paste_scaled(im, layer, W / 2, 1480, b)
    return im


def render(name, fn, dur):
    out, tmp = OUT / f"{name}.mp4", OUT / f"{name}.tmp.mp4"
    p = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(tmp)], stdin=subprocess.PIPE)
    for k in range(round(dur * FPS)):
        p.stdin.write(fn(k / FPS, dur).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        sys.exit(f"ffmpeg failed on {name}")
    os.replace(tmp, out)
    return out


def short_he(title, font_px=76, max_w=940):
    """First chunk of the Hebrew title, trimmed word by word until it fits on one line."""
    t = re.split(r"\s[-|]\s|,|\(|:", title or "")[0].strip()
    words = t.split()
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while len(words) > 2 and d.textlength(" ".join(words), font=F(900, font_px), direction="rtl") > max_w:
        words.pop()
    return " ".join(words)


def to_deal(p):
    off = re.sub(r"[^\d]", "", p.get("discount") or "")
    return {"img": f"{p['asin']}.jpg", "title": short_he(p.get("title_he") or p.get("title")),
            "sub": p.get("category_he") or "", "price": bot.shekels(p.get("price") or ""), "off": f"{off}%" if off else "",
            "rank": p.get("rank") or ""}


def build(posts, n=0):
    theme = apply_theme(n)
    tracks = sorted((REPO / "assets" / "music").glob("track*.m4a"))
    music = tracks[n % len(tracks)]
    print(f"reel #{n}: theme={theme} music={music.name} intro={TEXT['intro'][0]}")
    DEALS[:] = [to_deal(p) for p in posts]
    scenes = [("s1_intro", scene_intro, 2.0)] + \
             [(f"s{i + 2}_deal", (lambda i: lambda t, d: scene_deal(t, d, i))(i), 2.4) for i in range(len(DEALS))] + \
             [("s9_outro", scene_outro, 1.6)]
    files = [render(n, f, d) for n, f, d in scenes]
    lst = OUT / "list.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    silent = OUT / "silent.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(silent)], check=True)
    final = OUT / "ilamazondeals-reel.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(music),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                    "-af", "afade=t=out:st=10:d=0.8", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    return final


LINKS_IN_CAPTION = False  # set when commenting links on a post failed before; then links go in the caption


def item_link(p):
    if p.get("link"):
        return p["link"]
    tag = CONFIG.get("amazon_tag", "")
    return f"https://www.amazon.com/dp/{p['asin']}" + (f"?tag={tag}" if tag else "")


def links_text(posts):
    lines = ["🔗 הקישורים למוצרים:"]
    for i, p in enumerate(posts, 1):
        lines.append(f"{i}. {short_he(p.get('title_he') or p.get('title'))}: {item_link(p)}")
    return "\n".join(lines)


def add_links(media, posts, st):
    """Post the product links as a comment on the new IG post. If that fails, switch to links-in-caption for next time."""
    if not media or LINKS_IN_CAPTION or st.get("ig_links_in_caption"):
        return True
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    r = requests.post(f"https://graph.facebook.com/v23.0/{media}/comments",
                      data={"message": links_text(posts), "access_token": token}, timeout=30)
    print("links comment:", r.status_code, r.text[:150])
    if not r.ok:
        st["ig_links_in_caption"] = True
        owner = str(CONFIG.get("owner_chat_id") or "")
        tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if owner and tok:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": owner, "text":
                          "⚠️ Instagram didn't allow a links comment on the latest post. From now on links go in the caption."})
    return r.ok


def ig_caption(posts, n=0):
    openers = ["🔥 3 דילים מאמזון עם משלוח חינם לארץ 🇮🇱", "🛒 המוצרים שכולם קונים עכשיו באמזון, עם משלוח חינם לארץ 🇮🇱",
               "👀 3 מציאות שמצאנו לכם היום באמזון 🇮🇱", "⚡ הלהיטים של אמזון, ישר עד הבית בישראל 🇮🇱"]
    lines = [openers[n % len(openers)], ""]
    for i, p in enumerate(posts, 1):
        bits = [x for x in (bot.shekels(p.get("price") or ""), f"{p['discount']} הנחה" if p.get("discount") else "") if x]
        lines.append(f"{i}. {short_he(p.get('title_he') or p.get('title'))}" + (f" | {' | '.join(bits)}" if bits else ""))
    if LINKS_IN_CAPTION:
        lines += ["", links_text(posts)]
    lines += ["", "🖤 " + season_badge() + " 🕎", "💬 כתבו \"לינק\" בתגובות ונשלח לכם את הקישורים לכל המוצרים בהודעה פרטית",
              "🔗 הקישורים לכל המוצרים גם בתגובה הראשונה" if not LINKS_IN_CAPTION else "",
              "👈 עוד דילים כל יום בערוץ הטלגרם, הקישור בביו",
              "", "#אמזון #דילים #משלוחחינם #בלאקפריידיי #חנוכה #קניותאונליין #amazonfinds #amazondeals #israel"]
    return "\n".join(lines)


def publish_instagram(video, posts, n=0):
    """Publish the reel to Instagram (Graph API, resumable upload). Returns the media id or None."""
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig = str(CONFIG.get("ig_user_id") or "")
    if not (token and ig and CONFIG.get("ig_autopublish", True)):
        print("Instagram: not configured, skipping")
        return None
    import time
    api = "https://graph.facebook.com/v23.0"
    cap = ig_caption(posts, n)
    r = requests.post(f"{api}/{ig}/media", data={"media_type": "REELS", "upload_type": "resumable",
                                                  "caption": cap, "share_to_feed": "true",
                                                  # cover = first product, fully on screen (intro is 2.0s, deal slide 2.4s)
                                                  "thumb_offset": str(CONFIG.get("reel_cover_ms", 3600)),
                                                  "access_token": token}, timeout=60)
    print("IG container:", r.status_code, r.text[:200])
    if not r.ok:
        return None
    cid = r.json()["id"]
    size = os.path.getsize(video)
    with open(video, "rb") as fh:
        up = requests.post(f"https://rupload.facebook.com/ig-api-upload/v23.0/{cid}",
                           headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                           data=fh, timeout=300)
    print("IG upload:", up.status_code, up.text[:200])
    if not up.ok:
        return None
    for _ in range(40):  # wait for Instagram to process the video (up to ~5 minutes)
        st = requests.get(f"{api}/{cid}", params={"fields": "status_code,status", "access_token": token}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            print("IG processing failed:", st)
            return None
        time.sleep(8)
    pub = requests.post(f"{api}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
    print("IG publish:", pub.status_code, pub.text[:200])
    if not pub.ok:
        return None
    # the id returned for reels doesn't always work for comments; use the newest reel on the account instead
    try:
        lst = requests.get(f"{api}/{ig}/media", params={"fields": "id,media_product_type", "limit": 5,
                                                        "access_token": token}, timeout=30).json().get("data", [])
        newest = next((m["id"] for m in lst if m.get("media_product_type") == "REELS"), None)
        return newest or pub.json().get("id")
    except Exception:
        return pub.json().get("id")


def send(video, posts, ig_media=None, n=0):
    owner = str(CONFIG.get("owner_chat_id") or "")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not (owner and token):
        print("No owner_chat_id in config: reel saved as a workflow artifact only")
        return False
    cap = ig_caption(posts, n)
    with open(video, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                          data={"chat_id": owner, "caption": ("✅ Posted to Instagram automatically" if ig_media else
                                                               "🎬 Reel ready for Instagram"),
                                "supports_streaming": "true", "width": W, "height": H},
                          files={"video": ("ilamazondeals-reel.mp4", fh, "video/mp4")}, timeout=120)
    print("video:", r.status_code, r.text[:200])
    r2 = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       data={"chat_id": owner, "text": "Instagram caption ⬇️\n\n" + cap}, timeout=30)
    print("caption:", r2.status_code)
    return r.ok


def datetime_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def deal_score(p):
    """Best deals first: discount, then best-seller rank, trending a bonus."""
    off = int(re.sub(r"[^\d]", "", p.get("discount") or "") or 0)
    r = p.get("rank") or 99
    return off * 2 + (40 if r <= 3 else 30 if r <= 10 else 20 if r <= 20 else 10) + (15 if p.get("source") == "movers-and-shakers" else 0)


def due_slot(st, slots_key, done_key):
    """The Instagram slot (Israel hour) that is due now and not done today, or None. A slot can catch up for 2 hours."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    local = datetime.now(ZoneInfo("Asia/Jerusalem"))
    for h in CONFIG.get(slots_key, []):
        key = f"{local.date().isoformat()}-{h}"
        if h <= local.hour < h + 2 and key not in st.get(done_key, []):
            return key
    return None


def pick_best(log, since, k):
    """Top-k deals posted since `since` (fallback: most recent ones), kept in posting order."""
    fresh = [p for p in log if p["posted_at"] > since] if since else list(log)
    pool = fresh if len(fresh) >= k else log[-max(k * 2, 8):]
    best = sorted(pool, key=deal_score, reverse=True)[:k]
    return sorted(best, key=lambda p: p["posted_at"])


def main():
    log = json.loads((REPO / "data" / "posts.json").read_text())
    log = [p for p in log if p.get("store") != "aliexpress" and (IMG / f"{p['asin']}.jpg").exists()]
    state_f = REPO / "data" / "reels.json"
    st = json.loads(state_f.read_text()) if state_f.exists() else {}
    global LINKS_IN_CAPTION
    LINKS_IN_CAPTION = bool(st.get("ig_links_in_caption"))
    slot = None
    if "--latest" in sys.argv:
        batch = log[-3:]
    else:
        slot = due_slot(st, "reel_slots", "reel_slots_done")
        if not slot:
            print("No reel slot due now")
            return
        batch = pick_best(log, st.get("last_reel_at", ""), 3)
    if len(batch) < 3:
        print("Need 3 posts with photos")
        return
    import random
    n = st.get("count", 0) if slot else random.randrange(1000)
    video = build(batch, n)
    print("rendered", video, video.stat().st_size // 1024, "KB")
    (REPO / "reel-out").mkdir(exist_ok=True)
    os.replace(video, REPO / "reel-out" / "ilamazondeals-reel.mp4")
    final = REPO / "reel-out" / "ilamazondeals-reel.mp4"
    media = None
    if "--no-instagram" not in sys.argv:
        try:
            media = publish_instagram(final, batch, n)
            if media:
                add_links(media, batch, st)
                st.setdefault("media", []).append({"id": media, "asins": [p["asin"] for p in batch],
                                                   "at": datetime_now_iso()})
                st["media"] = st["media"][-30:]
        except Exception as e:
            print("Instagram publish error:", e)
    send(final, batch, media, n)
    if slot:
        st["reel_slots_done"] = (st.get("reel_slots_done", []) + [slot])[-10:]
        st["last_reel_at"] = datetime_now_iso()
        st["count"] = st.get("count", 0) + 1
    state_f.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
