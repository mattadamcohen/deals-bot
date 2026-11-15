"""One-off channel cleanup:
  1. delete repeat posts of the same product (other color/size) posted within 7 days, keeping the first
  2. re-upload every post's photo as a square so it shows uncropped in the feed (caption unchanged)
  3. remember product families so the bot won't repeat them"""
import json, os, sys
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot

api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
chat = os.environ["TELEGRAM_CHAT_ID"]
log_f = bot.ROOT / "data" / "posts.json"
posts = json.loads(log_f.read_text())
cats = {c["en"]: c for c in bot.CONFIG["categories"]}
state = bot.load_state()

seen, keep, dupes = {}, [], []
for p in posts:
    fam = bot.title_family(p["title"])
    first = seen.get(fam)
    if first and (datetime.fromisoformat(p["posted_at"]) - datetime.fromisoformat(first["posted_at"])).days < 7:
        dupes.append(p)
    else:
        seen.setdefault(fam, p)
        keep.append(p)
    state.setdefault("families", {})[fam] = p["posted_at"]

for p in dupes:
    r = requests.post(f"{api}/deleteMessage", data={"chat_id": chat, "message_id": p.get("message_id")}).json()
    print(f"deleted repeat {p['asin']} ({p['title'][:45]}): {r.get('ok')} {r.get('description', '')}")

for p in keep:
    if not p.get("message_id"):
        continue
    img = bot.ROOT / "data" / "images" / f"{p['asin']}.jpg"
    photo = bot.square_photo(p["image"]) if p.get("image") else None
    if not photo and img.exists():
        from io import BytesIO
        from PIL import Image
        im = Image.open(img).convert("RGB"); im.thumbnail((1000, 1000))
        c = Image.new("RGB", (1080, 1080), (255, 255, 255)); c.paste(im, ((1080 - im.width) // 2, (1080 - im.height) // 2))
        b = BytesIO(); c.save(b, "JPEG", quality=90); photo = b.getvalue()
    if not photo:
        print("no photo for", p["asin"]); continue
    cat = cats.get(p["category_en"], {"slug": p.get("category_slug", ""), "en": p["category_en"], "he": p["category_he"]})
    media = {"type": "photo", "media": "attach://photo", "caption": bot.caption(p, cat), "parse_mode": "HTML"}
    r = requests.post(f"{api}/editMessageMedia", data={"chat_id": chat, "message_id": p["message_id"],
                      "media": json.dumps(media, ensure_ascii=False)},
                      files={"photo": ("deal.jpg", photo, "image/jpeg")}, timeout=60).json()
    print(f"photo {p['asin']} msg {p['message_id']}: {r.get('ok')} {r.get('description', '')}")

log_f.write_text(json.dumps(keep, indent=1, ensure_ascii=False))
bot.save_state(state)
