"""Change the Hebrew title of an already-posted deal and update its Telegram caption.
  python tools/retitle.py "ASIN|new hebrew title|optional new english title"
"""
import json, os, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot

asin, title, *en = sys.argv[1].split("|")
log_f = bot.ROOT / "data" / "posts.json"
posts = json.loads(log_f.read_text())
p = next(x for x in posts if x["asin"] == asin.strip())
p["title_he"] = title.strip()
if en and en[0].strip():
    p["title"] = en[0].strip()
cats = {c["en"]: c for c in bot.CONFIG["categories"]}
cat = cats.get(p.get("category_en"), {"slug": p.get("category_slug", ""), "en": p.get("category_en", ""), "he": p.get("category_he", "")})
cap = bot.caption(dict(p), cat)
print(cap)
api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
r = requests.post(f"{api}/editMessageCaption", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "message_id": p["message_id"],
                                                     "caption": cap, "parse_mode": "HTML"})
print("telegram edit:", r.json().get("ok"), r.json().get("description", ""))
if r.json().get("ok"):
    log_f.write_text(json.dumps(posts, indent=1, ensure_ascii=False))
