"""Re-write the captions of posts already in the channel using the current post format.
Posts without a saved message_id are matched to the channel's photo messages in order
(only valid while every bot post so far has been a photo). Text-only bot messages (the setup
test) are deleted when --delete-text is given."""
import json, os, sys, time
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot

api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
chat = os.environ["TELEGRAM_CHAT_ID"]
log_file = bot.ROOT / "data" / "posts.json"
posts = json.loads(log_file.read_text())


def edit(mid, post):
    cat = {"slug": post.get("category_slug", ""), "en": post["category_en"], "he": post["category_he"]}
    text = bot.caption(dict(post), cat)
    r = requests.post(f"{api}/editMessageCaption", data={"chat_id": chat, "message_id": mid,
                                                          "caption": text, "parse_mode": "HTML"}, timeout=30)
    d = r.json()
    desc = d.get("description", "")
    return "ok" if d.get("ok") or "not modified" in desc else desc


text_ids, todo = [], [p for p in posts]
mid = 0
for post in todo:
    if post.get("message_id"):
        print(post["asin"], post["message_id"], edit(post["message_id"], post))
        continue
    while mid < 60:
        mid += 1
        res = edit(mid, post)
        time.sleep(1)
        if res == "ok":
            post["message_id"] = mid
            print(f"{post['asin']} -> message {mid}: updated")
            break
        if "no caption" in res:
            text_ids.append(mid)
        print(f"  message {mid}: {res}")
log_file.write_text(json.dumps(posts, indent=1, ensure_ascii=False))

if "--delete-text" in sys.argv:
    for t in text_ids:
        r = requests.post(f"{api}/deleteMessage", data={"chat_id": chat, "message_id": t}, timeout=30)
        print(f"deleted text message {t}: {r.json()}")
