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
        reel.pill(d, W / 2, 1185, p["price"], reel.F(900, 70), reel.YEL, reel.NAVY, pad=(50, 12))
    reel.pill(d, W / 2, 1290, "משלוח חינם לישראל מעל $49 · \u200e@ilamazondeals\u200e", reel.F(800, 36), reel.BLACK, reel.WHITE)
    return img


def caption(p, n):
    title_he = reel.short_he(p.get("title_he") or p.get("title"), 70, 2000)
    openers = ["🔥 דיל חם מאמזון", "👀 שווה בדיקה", "💡 המציאה של עכשיו", "🛒 זה מה שכולם קונים", "⚡ דיל חדש באמזון"]
    off = f" ({pct(p)}% הנחה)" if pct(p) else ""
    price = f"💲 {p['price']}{off}" if p.get("price") else (f"🏷️ {pct(p)}% הנחה" if pct(p) else "")
    rank = ("מוצר חם בקטגוריית " if p.get("source") == "movers-and-shakers" else f"#{p.get('rank')} בהכי נמכרים בקטגוריית ") \
        + p.get("category_he", "")
    en_title = re.sub(r"\s+", " ", p.get("title", ""))[:110]
    lines = [f"{openers[n % len(openers)]} 🇮🇱", "", title_he, rank, ""]
    if price:
        lines.append(price)
    lines += ["📦 משלוח חינם לישראל בהזמנה מעל $49", f"🖤 {reel.season_badge()}", "",
              "💬 רוצים את הקישור? כתבו \"לינק\" בתגובות ונשלח לכם אותו בהודעה פרטית",
              f"🔗 או העתיקו: {link(p['asin'])}",
              "👈 כל הדילים בערוץ הטלגרם, הקישור בביו", "",
              f"EN: {en_title}"
              + (f" | {p['price']}" if p.get("price") else "") + (f" | {pct(p)}% off" if pct(p) else "")
              + " | Free shipping to Israel on $49+ orders | Comment \"link\" and we'll DM it to you", ""]
    tags = ["#אמזון", "#דילים", "#משלוחחינם", "#קניותאונליין", "#בלאקפריידיי", "#חנוכה", "#מתנותלחנוכה",
            "#amazonfinds", "#amazondeals", "#israel", "#דיליםמאמזון", "#מבצעים"]
    random.Random(n).shuffle(tags)
    lines.append(" ".join(tags[:9]))
    return "\n".join(lines)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def host(asin, img):
    """Commit the card into the public repo so Instagram can download it by URL."""
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    path = CARD_DIR / f"{asin}.jpg"
    img.save(path, "JPEG", quality=90)
    # keep only the newest 40 cards
    for old in sorted(CARD_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime)[:-40]:
        old.unlink()
    git("config", "user.name", "deals-bot")
    git("config", "user.email", "deals-bot@users.noreply.github.com")
    git("add", "data/ig")
    git("commit", "-m", f"Instagram card {asin}")
    for _ in range(3):
        r = git("push")
        if r.returncode == 0:
            break
        git("pull", "--rebase")
    url = RAW.format(asin)
    for _ in range(12):  # wait until GitHub serves it
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return url
        except Exception:
            pass
        time.sleep(5)
    return url


def publish(url, cap):
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig = str(CONFIG.get("ig_user_id") or "")
    r = requests.post(f"{API}/{ig}/media", data={"image_url": url, "caption": cap, "access_token": token}, timeout=60)
    print("IG container:", r.status_code, r.text[:200])
    if not r.ok:
        return None
    cid = r.json()["id"]
    for _ in range(20):
        st = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if st.get("status_code") in ("FINISHED", None):
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            print("IG processing failed:", st)
            return None
        time.sleep(4)
    pub = requests.post(f"{API}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
    print("IG publish:", pub.status_code, pub.text[:200])
    return pub.json().get("id") if pub.ok else None


def main():
    log_f = REPO / "data" / "posts.json"
    posts = json.loads(log_f.read_text())
    st_f = REPO / "data" / "reels.json"
    st = json.loads(st_f.read_text()) if st_f.exists() else {}

    if "--preview" in sys.argv:
        p = posts[-1]
        (REPO / "reel-out").mkdir(exist_ok=True)
        card(p, int(sys.argv[-1]) if sys.argv[-1].isdigit() else 0).save(REPO / "reel-out" / "card.jpg", quality=90)
        print(caption(p, 0))
        return

    if not (os.getenv("IG_ACCESS_TOKEN") and CONFIG.get("ig_user_id") and CONFIG.get("ig_post_each_deal", True)):
        print("Instagram posts: not configured")
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)
    pending = [p for p in posts if not p.get("ig_media") and (IMG_DIR / f"{p['asin']}.jpg").exists()
               and datetime.fromisoformat(p["posted_at"]) > cutoff]
    for p in pending[-2:]:
        n = st.get("post_count", 0)
        url = host(p["asin"], card(p, n))
        media = publish(url, caption(p, n))
        p["ig_media"] = media or "failed"
        st["post_count"] = n + 1
        print(f"{p['asin']}: instagram {'posted ' + media if media else 'FAILED'}")
    log_f.write_text(json.dumps(posts, indent=1, ensure_ascii=False))
    st_f.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
