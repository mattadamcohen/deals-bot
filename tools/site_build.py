"""Build the israelideals.com site from what the bot posted to Telegram.
  python tools/site_build.py            -> site/dist/ (index.html, CNAME, logo)
Keeps a rolling store in data/site_deals.json (posts.json only holds the last 40):
deals expire after SITE_DAYS, and anything deleted from the Telegram channel is dropped.
"""
import json, re, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bot

SITE = ROOT / "site"
DIST = SITE / "dist"
STORE = ROOT / "data" / "site_deals.json"
REMOVED = ROOT / "data" / "site_removed.json"
SITE_DAYS = bot.CONFIG.get("site_days", 14)
DOMAIN = bot.CONFIG.get("site_domain", "israelideals.com")
THEMES = {"tech", "home", "kitchen", "kids", "fashion", "beauty", "sport", "car"}


def load(p, d):
    try:
        return json.loads(p.read_text())
    except Exception:
        return d


def num(s):
    s = re.sub(r"[^0-9.]", "", str(s or "").replace(",", ""))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def slim(p):
    store = "aliexpress" if p.get("store") == "aliexpress" or str(p.get("asin", "")).startswith("ali-") else "amazon"
    th = bot.theme_of(p.get("category_slug"), p.get("category_en"), p.get("title"))
    sold, reviews = num(p.get("sold")), num(p.get("reviews"))
    return {
        "id": p["asin"], "store": store, "theme": th if th in THEMES else "other",
        "title_he": p.get("title_he") or p.get("title", ""), "title_en": p.get("title", ""),
        "price": p.get("price", ""), "was": p.get("was", ""), "discount": p.get("discount", ""),
        "rating": p.get("rating", ""), "reviews": p.get("reviews", ""), "sold": p.get("sold", ""),
        # "most purchased": AliExpress gives units sold; Amazon gives no sales count, so its review count stands in
        "pop": sold if store == "aliexpress" else reviews,
        "img": p.get("image", ""), "link": p.get("link") or (f"https://www.amazon.com/dp/{p['asin']}?tag={bot.AMAZON_TAG}" if store == "amazon" else ""), "posted_at": p.get("posted_at", ""),
        "msg": [p.get("message_id")] + list(p.get("album_ids") or []),
    }


def main():
    posts = load(ROOT / "data" / "posts.json", [])
    store = {d["id"]: d for d in load(STORE, [])}
    for p in posts:
        if p.get("asin") and p.get("image"):
            d = slim(p)
            if d["link"]:
                store[p["asin"]] = d
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SITE_DAYS)).isoformat()
    removed = set(str(x) for x in load(REMOVED, []))
    deals = [d for d in store.values()
             if d["posted_at"] >= cutoff and not removed & {str(m) for m in d["msg"] if m}]
    deals.sort(key=lambda d: d["posted_at"], reverse=True)
    STORE.write_text(json.dumps(deals, ensure_ascii=False, indent=0))

    rate = bot.usd_ils() or load(ROOT / "data" / "fx.json", {}).get("rate") or 3.65
    pub = [{k: v for k, v in d.items() if k != "msg"} for d in deals]
    html = (SITE / "template.html").read_text()
    html = html.replace("/*DATA*/", "const PRODUCTS = " + json.dumps(pub, ensure_ascii=False) + ";")
    html = html.replace("/*RATE*/", str(round(rate, 4)))
    html = html.replace("/*BUILT*/", datetime.now(timezone.utc).isoformat(timespec="minutes"))
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    (DIST / "index.html").write_text(html)
    (DIST / "CNAME").write_text(DOMAIN + "\n")
    shutil.copy(ROOT / "assets" / "ilamazondeals-logo.png", DIST / "logo.png")
    print(f"site: {len(pub)} deals, rate {rate}, -> {DIST}")


if __name__ == "__main__":
    main()
