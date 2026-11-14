"""Find prices for already-posted deals that went out without one, and update their Telegram posts."""
import json, os, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot

log_f = bot.ROOT / "data" / "posts.json"
posts = json.loads(log_f.read_text())
todo = [p for p in posts if not p.get("price")]
print(f"{len(todo)} post(s) without a price")
if todo:
    amz = bot.Amazon()
    amz.set_location_israel()
    api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
    cats = {c["en"]: c for c in bot.CONFIG["categories"]}
    for p in todo:
        info = amz.product(p["asin"])
        print(p["asin"], "price:", info.get("price") or "still not found", "was:", info.get("was"))
        if not info.get("price"):
            continue
        p["price"] = info["price"]
        if info.get("was") and not p.get("was"):
            p["was"] = info["was"]
        if p.get("message_id"):
            cat = cats.get(p["category_en"], {"slug": p.get("category_slug", ""), "en": p["category_en"], "he": p["category_he"]})
            r = requests.post(f"{api}/editMessageCaption", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                              "message_id": p["message_id"], "caption": bot.caption(dict(p), cat), "parse_mode": "HTML"})
            print("  telegram edit:", r.json().get("ok"), r.json().get("description", ""))
    log_f.write_text(json.dumps(posts, indent=1, ensure_ascii=False))
