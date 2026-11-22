"""Referral promo for the giveaway.
  python tools/giveaway_promo.py preview   -> sends rules, pinned text and broadcast to Matt only
  python tools/giveaway_promo.py publish   -> edits the rules (206) and pinned post (207) in place, then posts the broadcast
"""
import json, os, sys
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent
CFG = json.loads((REPO / "config.json").read_text())
BASE = REPO / "data" / "giveaway"
TOKEN, CHAT = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
API = f"https://api.telegram.org/bot{TOKEN}"
RULES_ID, PINNED_ID = 206, 207


def call(method, **d):
    r = requests.post(f"{API}/{method}", data=d, timeout=30).json()
    print(method, r.get("ok"), r.get("description", ""))
    return r


me = requests.get(f"{API}/getMe").json()["result"]["username"]
uname = requests.get(f"{API}/getChat", params={"chat_id": CHAT}).json()["result"].get("username", "ilamazondeals")
rules_url = f"https://t.me/{uname}/{RULES_ID}"
join_btn = json.dumps({"inline_keyboard": [[{"text": "🎁 אני משתתף/ת + קישור אישי", "url": f"https://t.me/{me}?start=giveaway"}]]})
bc_btn = json.dumps({"inline_keyboard": [[{"text": "🎟️ קבלו קישור אישי", "url": f"https://t.me/{me}?start=giveaway"}]]})
rules = (BASE / "rules.txt").read_text()
post = (BASE / "post.txt").read_text().replace("{rules}", rules_url)
bc = (BASE / "broadcast.txt").read_text()

if sys.argv[1] == "preview":
    owner = str(CFG["owner_chat_id"])
    call("sendMessage", chat_id=owner, text="👀 PREVIEW 1/3: rules (edits message 206)\n\n" + rules)
    call("sendMessage", chat_id=owner, parse_mode="HTML", text="👀 PREVIEW 2/3: pinned post (edits 207)\n\n" + post,
         reply_markup=join_btn, disable_web_page_preview="true")
    call("sendMessage", chat_id=owner, parse_mode="HTML", text="👀 PREVIEW 3/3: new broadcast post\n\n" + bc,
         reply_markup=bc_btn, disable_web_page_preview="true")
elif sys.argv[1] == "publish":
    call("editMessageText", chat_id=CHAT, message_id=RULES_ID, text=rules)
    call("editMessageText", chat_id=CHAT, message_id=PINNED_ID, parse_mode="HTML", text=post,
         reply_markup=join_btn, disable_web_page_preview="true")
    call("sendMessage", chat_id=CHAT, parse_mode="HTML", text=bc, reply_markup=bc_btn, disable_web_page_preview="true")
