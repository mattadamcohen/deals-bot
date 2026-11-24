"""Instagram promo posts in the banner style (Matt, Nov 24): 2 a day at config promo_slots (Israel hours).
Each post: a theme (brands, gadgets, under 35, home, kids, beauty; Black Friday during promo days), 3 real
channel deals (max 1 fashion item), palettes alternating with hard contrast. Feed = 1080x1350, also shared
as a 1080x1920 story. Every 5th post is a recap carousel (collage cover + the last 4 designs).
  python tools/ig_promo.py           # post if a slot is due
  python tools/ig_promo.py --now     # post now
  python tools/ig_promo.py --preview # render only, to out/promo_*.png
"""
import io, json, os, random, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import promo_styles as S
from promo_styles import T, heb, anton, brush, card, pill, shadow_paste

REPO = S.REPO
CONFIG = json.loads((REPO / "config.json").read_text())
STATE = REPO / "data" / "ig_promo.json"
CACHE = REPO / ".cache" / "promo_img"
RATE = S.RATE
TZ = ZoneInfo("Asia/Jerusalem")

# bright palettes with hard contrast; consecutive posts never share one
PALETTES = [
    dict(name="blue-red", bg1=(30, 110, 255), bg2=(8, 30, 120), dark=(8, 8, 14), strip=(255, 40, 60),
         hot=(255, 40, 60), gold=(255, 214, 60), l2=(255, 40, 60)),
    dict(name="pink-orange", bg1=(255, 30, 140), bg2=(110, 0, 230), dark=(10, 6, 20), strip=(255, 120, 0),
         hot=(255, 90, 0), gold=(255, 230, 0), l2=(255, 230, 0)),
    dict(name="lime-pink", bg1=(170, 255, 40), bg2=(20, 170, 90), dark=(8, 10, 12), strip=(255, 30, 140),
         hot=(255, 30, 140), gold=(200, 255, 60), l2=(255, 30, 140)),
    dict(name="turq-orange", bg1=(0, 220, 220), bg2=(0, 90, 170), dark=(6, 10, 22), strip=(255, 110, 20),
         hot=(255, 90, 0), gold=(255, 220, 60), l2=(255, 140, 0)),
]

BRANDS = (r"nike|adidas|puma|reebok|new balance|skechers|under armour|asics|crocs|levi'?s|calvin klein|tommy hilfiger|"
          r"columbia|the north face|carhartt|owala|stanley|yeti|hydro ?flask|lego|logitech|anker|soundcore|jbl|sony|apple|"
          r"samsung|xiaomi|baseus|ugreen|razer|corsair|8bitdo|fossil|casio|laneige|medicube|cerave|la roche|olaplex|"
          r"neutrogena|e\.l\.f|maybelline|loreal|l'oreal|revlon|laura geller|dyson|philips|braun|oral-?b|ninja|"
          r"instant pot|keurig|nespresso|contigo|zojirushi|fujifilm|kodak|garmin|fitbit|olight|amazon basics|melissa|nerf|"
          r"hot wheels|barbie|fisher-price|schylling|needoh|squishmallows|mattel|hasbro")
FASHION = re.compile(r"shoe|sneaker|boot|slipper|sandal|jacket|coat|hoodie|shirt|sweater|dress|pants|jeans|legging|belt|"
                     r"sock|hat\b|cap\b|scarf|glove|bag\b|backpack|wallet|watch\b", re.I)

THEMES = {
    "brands": dict(l1="BRAND", l2="DEALS", strip="המותגים שאתם אוהבים", w3="מותגים אמיתיים · מחירים של דיל",
                   cap="🔥 מותגים אהובים במחירים של דיל"),
    "gadgets": dict(l1="COOL", l2="GADGETS", strip="שלא ידעתם שאתם צריכים", w1="גאדג'טים מגניבים",
                    w3="טכנולוגיה · גיימינג · בית חכם", cap="⚡ גאדג'טים מגניבים שלא ידעתם שאתם צריכים"),
    "under35": dict(l1="SUPER", l2="CHEAP", strip="שווה כל שקל", w1="דילים מתחת ל-", w2="35 ש״ח",
                    w3="על מאות מוצרים", cap="💸 דילים מתחת ל-35 ש״ח"),
    "home": dict(l1="HOME", l2="HACKS", strip="סדר, ארגון ומטבח", w1="מוצרים חכמים לבית",
                 w3="ארגון · מטבח · בית", cap="🏠 מוצרים חכמים לבית"),
    "kids": dict(l1="KIDS", l2="FUN", strip="צעצועים שהילדים יאהבו", w1="צעצועים ומשחקים",
                 w3="סקווישי · משחקים · מתנות", cap="🧸 צעצועים שהילדים יאהבו"),
    "beauty": dict(l1="GLOW", l2="DEALS", strip="ביוטי וטיפוח בדילים", w1="ביוטי וטיפוח",
                   w3="טיפוח · איפור · שיער", cap="✨ ביוטי וטיפוח בדילים"),
    "blackfriday": dict(l1="BLACK", l2="FRIDAY", strip="כבר הגיע לערוץ הדילים", w1="הדילים הכי שווים",
                        w3="אמזון · אליאקספרס", cap="🖤 בלאק פריידי בערוץ הדילים"),
}
ROTATION = ["brands", "gadgets", "under35", "home", "kids", "beauty"]

# layout per canvas height
LAY = {
    1920: dict(pole=(60, 1180), bfy=120, bfh=380, bfs=190, sy=510, sh=190, ss=74, wy=730, wh=420, w2s=150,
               py=1230, pw=300, ph=330, cy=1700, ch=170),
    1350: dict(pole=(30, 800), bfy=25, bfh=290, bfs=145, sy=310, sh=150, ss=60, wy=470, wh=320, w2s=118,
               py=830, pw=300, ph=290, cy=1190, ch=145),
}


def usd(p):
    try:
        return float(re.sub(r"[^\d.]", "", p.get("price") or ""))
    except ValueError:
        return 0.0


def ils(p):
    return round(usd(p) * RATE)


def title(p):
    return p.get("title_en") or p.get("title_he") or ""


def brand_of(p):
    # the maker's name comes first in the title; later mentions are usually "for iPhone/Xiaomi..." compatibility
    head = " ".join(re.split(r"\b(?:for|compatible|fits|with)\b", title(p), maxsplit=1, flags=re.I)[0].split()[:4])
    m = re.search(rf"\b(?:{BRANDS})\b", head, re.I)
    if not m:
        return None
    b = m.group(0)
    return {"jbl": "JBL", "lego": "LEGO", "ugreen": "UGREEN", "8bitdo": "8BitDo", "needoh": "NeeDoh",
            "olight": "OLIGHT", "e.l.f": "e.l.f.", "loreal": "L'Oréal"}.get(b.lower(), b.title() if (b.islower() or (b.isupper() and len(b) > 5)) else b)


def fetch_img(p):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{p['id']}.jpg"
    if not f.exists() and os.getenv("PROMO_OFFLINE"):
        return None
    if not f.exists():
        try:
            r = requests.get(p["img"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            Image.open(io.BytesIO(r.content)).convert("RGB").save(f, quality=92)
        except Exception as e:
            print("image failed", p["id"], e)
            return None
    return f


def pool():
    s = json.loads((REPO / "data" / "site_deals.json").read_text())
    s = s if isinstance(s, list) else list(s.values())
    since = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
    return [p for p in s if p.get("img") and usd(p) > 0 and p.get("posted_at", "") > since]


def score(p):
    off = int(re.sub(r"[^\d]", "", p.get("discount") or "") or 0)
    return off + min(40, (p.get("pop") or 0) ** 0.33) + (10 if p["store"] == "amazon" else 0)


def matches(theme, p):
    th = p.get("theme")
    if theme == "brands":
        return brand_of(p) is not None
    if theme == "gadgets":
        return th in ("tech", "car")
    if theme == "under35":
        return ils(p) <= 35
    if theme == "home":
        return th in ("home", "kitchen")
    if theme == "kids":
        return th == "kids"
    if theme == "beauty":
        return th == "beauty"
    return True  # blackfriday: anything good


def pick(theme, used):
    cands = sorted([p for p in pool() if matches(theme, p) and p["id"] not in used], key=score, reverse=True)
    out, fashion, brands = [], 0, set()
    for p in cands:
        is_f = bool(FASHION.search(title(p))) or p.get("theme") == "fashion"
        if is_f and fashion:
            continue
        if theme == "brands" and brand_of(p) in brands:
            continue
        if not fetch_img(p):
            continue
        out.append(p)
        fashion += is_f
        brands.add(brand_of(p))
        if len(out) == 3:
            break
    return out


def texts(theme, items):
    t = dict(THEMES[theme])
    low = min(ils(p) for p in items)
    if theme == "brands":
        t["w1"] = " · ".join(brand_of(p) for p in items)
    t.setdefault("w2", f"החל מ-{low} ש״ח")
    return t


def render(theme, items, pal, h):
    L = LAY[h]
    t = texts(theme, items)
    W = 1080
    DK, HOT = pal["dark"], pal["hot"]
    im = Image.new("RGBA", (W, h))
    g = ImageDraw.Draw(im)
    for y in range(h):
        k = y / h
        g.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(pal["bg1"], pal["bg2"])) + (255,))
    rnd = random.Random(7)
    for _ in range(34 if h > 1500 else 24):
        c = Image.new("RGBA", (40, 22), (0, 0, 0, 0))
        ImageDraw.Draw(c).rectangle([0, 0, 39, 21], fill=rnd.choice([HOT, pal["strip"], DK, (255, 255, 255)]) + (255,))
        im.alpha_composite(c.rotate(rnd.randint(0, 180), expand=True), (rnd.randint(0, W - 40), rnd.randint(0, h - 40)))
    for px in (70, W - 110):
        g.rectangle([px, L["pole"][0], px + 40, L["pole"][1]], fill=DK)
        g.rectangle([px + 8, L["pole"][0], px + 16, L["pole"][1]], fill=(60, 60, 70))
    # title banner
    bh = L["bfh"]
    b = brush(940, bh, DK, 2)
    lay = Image.new("RGBA", b.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.text((470, bh * 0.32), t["l1"], font=anton(L["bfs"]), fill=(255, 255, 255), anchor="mm")
    ld.text((500, bh * 0.74), t["l2"], font=anton(L["bfs"]), fill=pal["l2"], anchor="mm")
    lay = lay.transform(lay.size, Image.AFFINE, (1, 0.22, -40 * bh / 380, 0, 1, 0), resample=Image.BICUBIC)
    b.alpha_composite(lay)
    shadow_paste(im, b.rotate(-2, expand=True, resample=Image.BICUBIC), (60, L["bfy"]), alpha=140)
    # strip
    sh = L["sh"]
    r = brush(980, sh, pal["strip"], 3, jag=18)
    r.alpha_composite(brush(840, int(sh * 0.63), DK, 5, jag=12), (70, int(sh * 0.18)))
    T(ImageDraw.Draw(r), (490, sh / 2), t["strip"], heb(900, L["ss"] if len(t["strip"]) < 22 else int(L["ss"] * 0.84)),
      (255, 255, 255))
    shadow_paste(im, r.rotate(1.5, expand=True, resample=Image.BICUBIC), (40, L["sy"]), alpha=140)
    # white sign
    wh = L["wh"]
    wb = Image.new("RGBA", (920, wh), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wb)
    wd.rectangle([0, 0, 919, wh - 1], fill=(250, 250, 248))
    w1s = 96 if len(t["w1"]) < 15 else 62 if len(t["w1"]) < 30 else 50
    T(wd, (460, wh * 0.2), t["w1"], heb(900, int(w1s * wh / 420)), DK)
    T(wd, (460, wh * 0.52), t["w2"], heb(900, L["w2s"] if len(t["w2"]) > 6 else int(L["w2s"] * 1.6)), HOT)
    sw = 640 if len(t["w3"]) < 18 else 860
    sub = brush(sw, int(90 * wh / 420), DK, 9, jag=12)
    T(ImageDraw.Draw(sub), (sw / 2, sub.height / 2), t["w3"], heb(900, int(52 * wh / 420)), (255, 255, 255))
    wb.alpha_composite(sub, ((920 - sw) // 2, wh - sub.height - int(12 * wh / 420)))
    shadow_paste(im, wb.rotate(-1, expand=True, resample=Image.BICUBIC), (70, L["wy"]), alpha=150)
    # products
    cw, chh = L["pw"], L["ph"]
    for i, p in enumerate(items):
        x, y = 45 + i * (cw + 30), L["py"] + (20 if i != 1 else 0)
        c = card(CACHE / f"{p['id']}.jpg", cw, chh, radius=30, pad=10, fit="contain")
        c = c.rotate([-4, 0, 4][i], expand=True, resample=Image.BICUBIC)
        shadow_paste(im, c, (x, y), alpha=150)
        pill(im, x + c.width / 2, y + c.height - 6, f"₪{ils(p)}", heb(900, 58 if h > 1500 else 52), (255, 255, 255), HOT,
             padx=28, outline=(255, 255, 255))
    # CTA
    ch = L["ch"]
    bar = brush(1000, ch, DK, 11, jag=16)
    bd = ImageDraw.Draw(bar)
    T(bd, (500, ch * 0.36), "הצטרפו לערוץ בטלגרם", heb(900, int(60 * ch / 170)), (255, 255, 255))
    T(bd, (500, ch * 0.74), "@ilamazondeals  ·  israelideals.com", heb(800, int(40 * ch / 170)), pal["gold"])
    shadow_paste(im, bar, (40, L["cy"]), alpha=140)
    return im.convert("RGB")


def recap_cover(items, pal):
    W, h = 1080, 1350
    im = Image.new("RGBA", (W, h))
    g = ImageDraw.Draw(im)
    for y in range(h):
        k = y / h
        g.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(pal["bg1"], pal["bg2"])) + (255,))
    b = brush(1000, 230, pal["dark"], 4)
    bd = ImageDraw.Draw(b)
    T(bd, (500, 82), "הלהיטים של השבוע", heb(900, 88), (255, 255, 255))
    T(bd, (500, 175), "החליקו לכל הדילים  ←", heb(800, 46), pal["gold"])
    shadow_paste(im, b, (40, 30), alpha=140)
    cw, chh, gap = 320, 400, 25
    x0 = (W - 3 * cw - 2 * gap) // 2
    for i, p in enumerate(items[:6]):
        x, y = x0 + (i % 3) * (cw + gap), 300 + (i // 3) * (chh + gap)
        shadow_paste(im, card(CACHE / f"{p['id']}.jpg", cw, chh, radius=30, pad=10, fit="contain"), (x, y), alpha=120)
        pill(im, x + cw / 2, y + chh - 10, f"₪{ils(p)}", heb(900, 50), (255, 255, 255), pal["hot"], padx=24,
             outline=(255, 255, 255))
    bar = brush(1000, 130, pal["dark"], 11, jag=14)
    T(ImageDraw.Draw(bar), (500, 65), "@ilamazondeals  ·  israelideals.com", heb(800, 46), pal["gold"])
    shadow_paste(im, bar, (40, 1170), alpha=140)
    return im.convert("RGB")


# ------------------------------------------------------------------ publishing
def short_link(p):
    if p["store"] == "aliexpress":
        try:
            import aliexpress
            return aliexpress.link(f"https://www.aliexpress.com/item/{p['id'][4:]}.html") or p["link"]
        except Exception as e:
            print("short link failed", e)
    return p["link"]


def name_he(p):
    import reel
    return reel.short_he(p.get("title_he") or p.get("title_en"))


def caption(theme, items):
    lines = [THEMES[theme]["cap"], ""]
    for i, p in enumerate(items, 1):
        lines.append(f"{i}. {name_he(p)} · ₪{ils(p)}")
    lines += ["", "🔗 הקישורים למוצרים בתגובות", "📲 עוד מאות דילים כל יום בערוץ הטלגרם: t.me/ilamazondeals",
              "🌐 israelideals.com", "", "#דילים #אמזון #אליאקספרס #קניות #ישראל #deals #amazonfinds #aliexpress"]
    return "\n".join(lines)


def comment(media, text):
    r = requests.post(f"https://graph.facebook.com/v23.0/{media}/comments",
                      data={"message": text, "access_token": os.getenv("IG_ACCESS_TOKEN", "").strip()}, timeout=30)
    print("comment", r.status_code, r.text[:200])


def story(url):
    import ig_post
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig = str(CONFIG.get("ig_user_id"))
    r = requests.post(f"{ig_post.API}/{ig}/media", data={"image_url": url, "media_type": "STORIES",
                                                         "access_token": token}, timeout=60)
    print("story container", r.status_code, r.text[:200])
    if r.ok and ig_post.wait_ready(r.json()["id"], token):
        pub = requests.post(f"{ig_post.API}/{ig}/media_publish", data={"creation_id": r.json()["id"],
                                                                        "access_token": token}, timeout=60)
        print("story publish", pub.status_code, pub.text[:200])


def black_friday_today():
    d = datetime.now(TZ).date().isoformat()
    return any(pp["from"] <= d <= min(pp["to"], CONFIG.get("promo_bf_until", "2026-11-29"))
               for pp in CONFIG.get("promo_periods", []) if "Black Friday" in pp.get("name", ""))


def due_slot(st):
    local = datetime.now(TZ)
    now_h = local.hour + local.minute / 60
    for h in CONFIG.get("promo_slots", []):
        key = f"{local.date().isoformat()}-{h}"
        if h <= now_h < h + 2 and key not in st.get("slots_done", []):
            return key, h
    return None, None


def main():
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    preview = "--preview" in sys.argv
    slot, hour = (None, None)
    if not (preview or "--now" in sys.argv):
        slot, hour = due_slot(st)
        if not slot:
            print("No promo slot due now")
            return
    n = st.get("count", 0)
    hist = st.get("history", [])
    pal_i = (st.get("last_palette", -1) + 1) % len(PALETTES)
    if "--palette" in sys.argv:
        pal_i = [p["name"] for p in PALETTES].index(sys.argv[sys.argv.index("--palette") + 1])
    pal = PALETTES[pal_i]
    import ig_post

    recap = n % 5 == 4 and len(hist) >= 4 and not preview
    if recap:
        last = hist[-4:]
        by = {p["id"]: p for p in pool()}
        items = [by[i] for h_ in last for i in h_["ids"] if i in by and fetch_img(by[i])][:6]
        cover = recap_cover(items, pal)
        name = f"promo-{datetime.now(timezone.utc):%Y%m%d%H%M}-recap"
        urls = ig_post.host({name: cover})
        slides = [urls[name]] + [ig_post.RAW.format(h_["image"]) for h_ in last]
        cap = "🏆 הלהיטים של השבוע בערוץ הדילים\nהחליקו לכל הדילים 👉\n\n" + "\n".join(
            f"• {name_he(p)} · ₪{ils(p)}" for p in items) + \
            "\n\n📲 t.me/ilamazondeals\n🌐 israelideals.com\n\n#דילים #אמזון #אליאקספרס #deals"
        media = ig_post.publish(slides, cap)
        print("recap", media)
        if media:
            for p in items:
                comment(media, f"🔗 {name_he(p)}: {short_link(p)}")
            st.update(count=n + 1, last_palette=pal_i)
            if slot:
                st["slots_done"] = (st.get("slots_done", []) + [slot])[-20:]
            STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        return

    if black_friday_today() and (hour == CONFIG.get("promo_slots", [12])[0] or (hour is None and st.get("last_theme") != "blackfriday")):
        theme = "blackfriday"
    else:
        ri = st.get("rotation", 0)
        theme = ROTATION[ri % len(ROTATION)]
        st["rotation"] = ri + 1
    if "--theme" in sys.argv:
        theme = sys.argv[sys.argv.index("--theme") + 1]
    used = set(st.get("used", []))
    if "--ids" in sys.argv:
        by = {p["id"]: p for p in json.loads((REPO / "data" / "site_deals.json").read_text())}
        items = [by[i] for i in sys.argv[sys.argv.index("--ids") + 1].split(",") if i in by and fetch_img(by[i])]
    else:
        items = pick(theme, used)
    if "--w3" in sys.argv:
        THEMES[theme]["w3"] = sys.argv[sys.argv.index("--w3") + 1].replace("_", " ")
    if len(items) < 3:
        print("not enough items for", theme, "- falling back to blackfriday/any")
        theme = "brands" if theme != "brands" else "gadgets"
        items = pick(theme, used)
    if len(items) < 3:
        print("not enough items")
        return
    feed, tall = render(theme, items, pal, 1350), render(theme, items, pal, 1920)
    if preview:
        S.OUT.mkdir(exist_ok=True)
        feed.save(S.OUT / "promo_feed.png")
        tall.save(S.OUT / "promo_story.png")
        print(theme, [p["id"] for p in items])
        return
    stamp = f"promo-{datetime.now(timezone.utc):%Y%m%d%H%M}"
    urls = ig_post.host({stamp: feed, stamp + "-s": tall})
    media = ig_post.publish([urls[stamp]], caption(theme, items))
    print("feed", theme, media)
    if not media:
        return
    for i, p in enumerate(items, 1):
        comment(media, f"🔗 {i}. {name_he(p)}: {short_link(p)}")
    try:
        story(urls[stamp + "-s"])
    except Exception as e:
        print("story failed", e)
    hist.append({"at": datetime.now(timezone.utc).isoformat(), "theme": theme, "ids": [p["id"] for p in items],
                 "image": stamp, "media": media})
    st.update(count=n + 1, last_palette=pal_i, last_theme=theme, history=hist[-20:],
              used=(list(used) + [p["id"] for p in items])[-90:])
    if slot:
        st["slots_done"] = (st.get("slots_done", []) + [slot])[-20:]
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
