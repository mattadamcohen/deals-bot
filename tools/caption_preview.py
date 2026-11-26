"""Send Matt (owner chat) a preview of the short Telegram caption, built from a recent post: python tools/caption_preview.py [asin]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
import bot

bot.CONFIG["caption_style"] = "short"
posts = json.loads((bot.ROOT / "data" / "posts.json").read_text())
want = sys.argv[1:] or [posts[-1]["asin"], next(p["asin"] for p in reversed(posts) if p.get("store") == "aliexpress")]
for asin in want:
    p = next(x for x in reversed(posts) if x["asin"] == asin)
    item = {k: p.get(k) for k in ("asin", "title", "price", "was", "discount", "rating", "reviews", "store", "link", "image", "sold")}
    item["coupon"] = json.loads(p["coupon"]) if p.get("coupon", "").startswith("{") else None
    text = bot.caption(item, {"slug": p.get("category_slug", ""), "he": p.get("category_he", ""), "en": p.get("category_en", "")})
    print(text, "\n----")
    photo = bot.square_photo(p["image"])
    r = requests.post(f"https://api.telegram.org/bot{bot.TG_TOKEN}/sendPhoto",
                      data={"chat_id": bot.CONFIG["owner_chat_id"], "caption": text, "parse_mode": "HTML"},
                      files={"photo": ("p.jpg", photo, "image/jpeg")}, timeout=60)
    print("sent", r.ok, r.text[:200])
