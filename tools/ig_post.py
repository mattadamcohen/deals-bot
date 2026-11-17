"""Instagram photo post for each new Telegram deal.

Run after bot.py: finds posts in data/posts.json that have no Instagram post yet (posted in the last
few hours), renders a branded 1080x1350 card, hosts it in this (public) repo so Instagram can fetch it,
then publishes it with a Hebrew-first caption that includes the product link.
  python tools/ig_post.py            # publish pending deals
  python tools/ig_post.py --preview  # just render the latest deal's card to reel-out/
"""
import json, os, random, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reel  # shared fonts, colors, helpers
bot = reel.bot

REPO = reel.REPO
CONFIG = reel.CONFIG
W, H = 1080, 1350
IMG_DIR = REPO / "data" / "images"
CARD_DIR = REPO / "data" / "ig"
RAW = "https://raw.githubusercontent.com/mattadamcohen/deals-bot/main/data/ig/{}.jpg"
API = "https://graph.facebook.com/v23.0"


def link(asin):
    tag = CONFIG.get("amazon_tag", "")
    return f"https://www.amazon.com/dp/{asin}" + (f"?tag={tag}" if tag else "")


def pct(p):
    return int(re.sub(r"[^\d]", "", p.get("discount") or "") or 0)


def card(p, n):
    """Render the post image for deal p using theme n."""
    reel.apply_theme(n)
    img = Image.new("RGB", (W, H), reel.DEEP)
    g = Image.new("L", (W, H))
    gd = ImageDraw.Draw(g)
    for r in range(1300, 0, -20):
        gd.ellipse([W / 2 - r, 520 - r, W / 2 + r, 520 + r], fill=int(255 * (1 - r / 1300)))
    img.paste(Image.new("RGB", (W, H), reel.GLOW), mask=g.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(img)

    # header
    if p.get("source") == "movers-and-shakers":
        head = f"מוצר חם · {p.get('category_he', '')}"
    else:
        head = f"#{p.get('rank')} בהכי נמכרים · {p.get('category_he', '')}"
    reel.pill(d, W / 2, 80, head, reel.F(800, 46), reel.WHITE, reel.BLUE)

    # product card
    box = Image.new("RGBA", (860, 860), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle([0, 0, 859, 859], radius=56, fill=reel.WHITE)
    prod = Image.open(IMG_DIR / f"{p['asin']}.jpg").convert("RGB")
    prod.thumbnail((780, 780), Image.LANCZOS)
    box.paste(prod, ((860 - prod.width) // 2, (860 - prod.height) // 2))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([110, 170, 970, 1030], radius=56, fill=(0, 8, 48, 110))
    sh = shadow.filter(ImageFilter.GaussianBlur(26))
    img.paste(sh, (0, 0), sh)
    img.paste(box, (110, 150), box)

    # discount (or rank) burst
    bu = reel.burst(140)
    bd = ImageDraw.Draw(bu)
    s = f"-{pct(p)}%" if pct(p) else f"#{p.get('rank')}"
    f = reel.F(900, 84 if len(s) <= 4 else 70)
    bb = bd.textbbox((0, 0), s, font=f)
    bd.text((150 - (bb[2] - bb[0]) / 2 - bb[0], 150 - (bb[3] - bb[1]) / 2 - bb[1]), s, font=f, fill=reel.NAVY)
    reel.paste_scaled(img, bu.rotate(-8, resample=Image.BICUBIC, expand=True), 905, 285, 1)

    # title, price, footer
    reel.text_c(d, 1052, reel.short_he(p.get("title_he") or p.get("title"), 70, 980), reel.F(900, 70))
    if p.get("price"):
        reel.pill(d, W / 2, 1185, bot.shekels(p["price"]), reel.F(900, 70), reel.YEL, reel.NAVY, pad=(50, 12))
    reel.pill(d, W / 2, 1290, "משלוח חינם לארץ מעל $49 · \u200e@ilamazondeals\u200e", reel.F(800, 36), reel.BLACK, reel.WHITE)
    return img


def caption(p, n):
    title_he = reel.short_he(p.get("title_he") or p.get("title"), 70, 2000)
    openers = ["🔥 דיל חם מאמזון", "👀 שווה בדיקה", "💡 המציאה של עכשיו", "🛒 זה מה שכולם קונים", "⚡ דיל חדש באמזון"]
    off = f" ({pct(p)}% הנחה)" if pct(p) else ""
    price = f"💰 {bot.shekels(p['price'])}{off}" if p.get("price") else (f"🏷️ {pct(p)}% הנחה" if pct(p) else "")
    rank = ("מוצר חם בקטגוריית " if p.get("source") == "movers-and-shakers" else f"#{p.get('rank')} בהכי נמכרים בקטגוריית ") \
        + p.get("category_he", "")
    en_title = re.sub(r"\s+", " ", p.get("title", ""))[:110]
    lines = [f"{openers[n % len(openers)]} 🇮🇱", "", title_he, rank, ""]
    if price:
        lines.append(price)
    lines += ["📦 משלוח חינם לארץ בהזמנה מעל $49", f"🖤 {reel.season_badge()}", "",
              "💬 רוצים את הקישור? כתבו \"לינק\" בתגובות ונשלח לכם אותו בהודעה פרטית",
              f"🔗 או העתיקו: {link(p['asin'])}",
              "👈 כל הדילים בערוץ הטלגרם, הקישור בביו", "",
              f"EN: {en_title}"
              + (f" | {bot.shekels(p['price'])}" if p.get("price") else "") + (f" | {pct(p)}% off" if pct(p) else "")
              + " | Free shipping to Israel on $49+ orders | Comment \"link\" and we'll DM it to you", ""]
    tags = ["#אמזון", "#דילים", "#משלוחחינם", "#קניותאונליין", "#בלאקפריידיי", "#חנוכה", "#מתנותלחנוכה",
            "#amazonfinds", "#amazondeals", "#israel", "#דיליםמאמזון", "#מבצעים"]
    random.Random(n).shuffle(tags)
    lines.append(" ".join(tags[:9]))
    return "\n".join(lines)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def host(images):
    """Commit images {name: PIL image} into the public repo so Instagram can download them; returns {name: url}."""
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    for name, img in images.items():
        img.save(CARD_DIR / f"{name}.jpg", "JPEG", quality=90)
    for old in sorted(CARD_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime)[:-60]:
        old.unlink()
    git("config", "user.name", "deals-bot")
    git("config", "user.email", "deals-bot@users.noreply.github.com")
    git("add", "data/ig")
    git("commit", "-m", "Instagram images")
    for _ in range(3):
        if git("push").returncode == 0:
            break
        git("pull", "--rebase", "-X", "theirs")
    urls = {name: RAW.format(name) for name in images}
    for url in urls.values():  # wait until GitHub serves them
        for _ in range(12):
            try:
                if requests.head(url, timeout=15).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(5)
    return urls


def wait_ready(cid, token):
    for _ in range(30):
        st = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if st.get("status_code") in ("FINISHED", None):
            return True
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            print("IG processing failed:", st)
            return False
        time.sleep(4)
    return False


def publish(urls, cap):
    """Publish one image, or a carousel when given several image urls. Returns the media id or None."""
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig = str(CONFIG.get("ig_user_id") or "")
    if len(urls) == 1:
        r = requests.post(f"{API}/{ig}/media", data={"image_url": urls[0], "caption": cap, "access_token": token}, timeout=60)
    else:
        children = []
        for u in urls:
            c = requests.post(f"{API}/{ig}/media", data={"image_url": u, "is_carousel_item": "true",
                                                          "access_token": token}, timeout=60)
            print("IG item:", c.status_code, c.text[:120])
            if not c.ok:
                return None
            children.append(c.json()["id"])
        for c in children:
            wait_ready(c, token)
        r = requests.post(f"{API}/{ig}/media", data={"media_type": "CAROUSEL", "children": ",".join(children),
                                                      "caption": cap, "access_token": token}, timeout=60)
    print("IG container:", r.status_code, r.text[:200])
    if not r.ok or not wait_ready(r.json()["id"], token):
        return None
    pub = requests.post(f"{API}/{ig}/media_publish", data={"creation_id": r.json()["id"], "access_token": token}, timeout=60)
    print("IG publish:", pub.status_code, pub.text[:200])
    return pub.json().get("id") if pub.ok else None


def cover(items, n):
    """First carousel slide."""
    reel.apply_theme(n)
    img = Image.new("RGB", (W, H), reel.DEEP)
    g = Image.new("L", (W, H))
    gd = ImageDraw.Draw(g)
    for r in range(1300, 0, -20):
        gd.ellipse([W / 2 - r, 520 - r, W / 2 + r, 520 + r], fill=int(255 * (1 - r / 1300)))
    img.paste(Image.new("RGB", (W, H), reel.GLOW), mask=g.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(img)
    reel.paste_scaled(img, reel.LOGO_IM, W / 2, 330, 0.48)
    reel.text_c(d, 620, f"{len(items)} דילים מאמזון", reel.F(900, 120))
    reel.text_c(d, 780, "עם משלוח חינם לארץ", reel.F(800, 72), reel.YEL)
    # little product thumbnails
    thumbs = [Image.open(IMG_DIR / f"{p['asin']}.jpg").convert("RGB") for p in items][:4]
    size, gap = 200, 30
    x0 = (W - (len(thumbs) * size + (len(thumbs) - 1) * gap)) / 2
    for i, t in enumerate(thumbs):
        tile = Image.new("RGB", (size, size), reel.WHITE)
        t.thumbnail((size - 24, size - 24), Image.LANCZOS)
        tile.paste(t, ((size - t.width) // 2, (size - t.height) // 2))
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=32, fill=255)
        img.paste(tile, (int(x0 + i * (size + gap)), 930), m)
    reel.pill(d, W / 2, 1220, reel.season_badge(), reel.F(800, 50), reel.BLACK, reel.WHITE)
    reel.text_c(d, 1270, "החליקו לכל הדילים", reel.F(700, 40), (210, 222, 255))
    return img


def carousel_caption(items, n):
    openers = ["🔥 {k} דילים מאמזון עם משלוח חינם לארץ 🇮🇱", "🛒 {k} מוצרים שכולם קונים עכשיו באמזון 🇮🇱",
               "👀 {k} מציאות שמצאנו לכם באמזון 🇮🇱", "⚡ הלהיטים של אמזון, {k} דילים עם משלוח חינם 🇮🇱"]
    lines = [openers[n % len(openers)].format(k=len(items)), ""]
    for i, p in enumerate(items, 1):
        bits = [x for x in (bot.shekels(p.get("price") or ""), f"{pct(p)}% הנחה" if pct(p) else "") if x]
        lines.append(f"{i}. {reel.short_he(p.get('title_he') or p.get('title'), 70, 2000)}" + (f" | {' | '.join(bits)}" if bits else ""))
    lines += ["", "📦 משלוח חינם לארץ בהזמנה מעל $49, אפשר לשלב כמה מוצרים", f"🖤 {reel.season_badge()}", "",
              "💬 כתבו \"לינק\" בתגובות ונשלח לכם את הקישורים לכל המוצרים בהודעה פרטית",
              reel.links_text(items) if reel.LINKS_IN_CAPTION else "🔗 הקישורים לכל המוצרים גם בתגובה הראשונה",
              "👈 עוד דילים כל יום בערוץ הטלגרם, הקישור בביו", ""]
    tags = ["#אמזון", "#דילים", "#משלוחחינם", "#קניותאונליין", "#בלאקפריידיי", "#חנוכה", "#מתנותלחנוכה",
            "#amazonfinds", "#amazondeals", "#israel", "#דיליםמאמזון", "#מבצעים"]
    random.Random(n).shuffle(tags)
    lines.append(" ".join(tags[:9]))
    return "\n".join(lines)


def post_carousel(items, st):
    n = st.get("post_count", 0)
    images = {f"cover-{items[0]['asin']}": cover(items, n)}
    for p in items:
        images[p["asin"]] = card(p, n)
    urls = host(images)
    media = publish(list(urls.values()), carousel_caption(items, n))
    st["post_count"] = n + 1
    if media:
        reel.add_links(media, items, st)
        st.setdefault("media", []).append({"id": media, "asins": [p["asin"] for p in items],
                                           "at": datetime.now(timezone.utc).isoformat(), "kind": "carousel"})
        st["media"] = st["media"][-30:]
    return media


def main():
    log_f = REPO / "data" / "posts.json"
    posts = json.loads(log_f.read_text())
    by_asin = {p["asin"]: p for p in posts}
    st_f = REPO / "data" / "reels.json"
    st = json.loads(st_f.read_text()) if st_f.exists() else {}
    reel.LINKS_IN_CAPTION = bool(st.get("ig_links_in_caption"))

    if "--preview" in sys.argv:
        (REPO / "reel-out").mkdir(exist_ok=True)
        items = posts[-4:]
        cover(items, 1).save(REPO / "reel-out" / "cover.jpg", quality=90)
        card(items[0], 1).save(REPO / "reel-out" / "card.jpg", quality=90)
        print(carousel_caption(items, 1))
        return
    if not (os.getenv("IG_ACCESS_TOKEN") and CONFIG.get("ig_user_id")):
        print("Instagram posts: not configured")
        return

    has_img = lambda a: a in by_asin and (IMG_DIR / f"{a}.jpg").exists()
    if "--asins" in sys.argv:  # post these deals now, as one post / carousel
        asins = [a for a in sys.argv[sys.argv.index("--asins") + 1].split(",") if has_img(a)]
        batches = [asins] if asins else []
    else:  # daily carousel slot(s): the best 4 deals since the last carousel
        slot = reel.due_slot(st, "carousel_slots", "carousel_slots_done")
        if not slot:
            print("No carousel slot due now")
            return
        pool = [p for p in posts if p.get("store") != "aliexpress" and has_img(p["asin"])]
        batches = [[p["asin"] for p in reel.pick_best(pool, st.get("last_carousel_at", ""), 4)]]
        st["carousel_slots_done"] = (st.get("carousel_slots_done", []) + [slot])[-10:]
        st["last_carousel_at"] = datetime.now(timezone.utc).isoformat()
        st.pop("carousel_queue", None)
    for asins in batches[:1]:
        items = [by_asin[a] for a in asins if has_img(a)]
        if not items:
            continue
        media = post_carousel(items, st) if len(items) > 1 else None
        if len(items) == 1:
            n = st.get("post_count", 0)
            urls = host({items[0]["asin"]: card(items[0], n)})
            media = publish(list(urls.values()), caption(items[0], n))
            if media:
                reel.add_links(media, items, st)
                st.setdefault("media", []).append({"id": media, "asins": asins, "at": datetime.now(timezone.utc).isoformat()})
        print(f"instagram {'posted ' + media if media else 'FAILED'}: {asins}")
    st_f.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
