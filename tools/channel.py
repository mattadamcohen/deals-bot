"""Change the Telegram channel's settings through the bot.
Usage: python tools/channel.py description "text" | title "text" | photo path/to/image.png
The bot must be a channel admin with the "Change channel info" permission."""
import json, os, sys, requests
token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
api = f"https://api.telegram.org/bot{token}"
action, value = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
if action == "description":
    r = requests.post(f"{api}/setChatDescription", data={"chat_id": chat, "description": value})
elif action == "title":
    r = requests.post(f"{api}/setChatTitle", data={"chat_id": chat, "title": value})
elif action == "photo":
    with open(value, "rb") as f:
        r = requests.post(f"{api}/setChatPhoto", data={"chat_id": chat}, files={"photo": f})
elif action == "whoami":
    # lists private chats that messaged the bot (send /start to the bot first)
    r = requests.get(f"{api}/getUpdates", timeout=30)
    for u in r.json().get("result", []):
        m = u.get("message") or {}
        c = m.get("chat", {})
        if c.get("type") == "private":
            print("PRIVATE CHAT", c.get("id"), c.get("first_name"), c.get("username"))
elif action == "pin":
    r = requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": value})
    if r.ok:
        mid = r.json()["result"]["message_id"]
        r = requests.post(f"{api}/pinChatMessage", data={"chat_id": chat, "message_id": mid, "disable_notification": "true"})
elif action in ("giveaway", "giveaway-preview"):
    # giveaway-preview: send both posts to the owner only. giveaway: post rules + announcement to the channel and pin it.
    import json as _json, pathlib
    base = pathlib.Path(__file__).resolve().parent.parent / "data" / "giveaway"
    owner = str(json.load(open(pathlib.Path(__file__).resolve().parent.parent / "config.json")).get("owner_chat_id"))
    target = owner if action == "giveaway-preview" else chat
    me = requests.get(f"{api}/getMe").json()["result"]["username"]
    r = requests.post(f"{api}/sendMessage", data={"chat_id": target, "text": (base / "rules.txt").read_text(),
                                                  "disable_notification": "true"}).json()
    rid = r["result"]["message_id"]
    uname = requests.get(f"{api}/getChat", params={"chat_id": chat}).json()["result"].get("username", "ilamazondeals")
    rules_url = f"https://t.me/{uname}/{rid}" if target == chat else "https://t.me/" + uname
    kb = {"inline_keyboard": [[{"text": "🎁 אני משתתף/ת", "url": f"https://t.me/{me}?start=giveaway"}]]}
    r = requests.post(f"{api}/sendMessage", data={"chat_id": target, "parse_mode": "HTML",
                                                  "text": (base / "post.txt").read_text().replace("{rules}", rules_url),
                                                  "reply_markup": _json.dumps(kb), "disable_web_page_preview": "true"}).json()
    print("giveaway post", r.get("ok"), r.get("description"), "bot:", me)
    r = requests.Response(); r.status_code = 200; r._content = b'{"ok": true}' 
    if action == "giveaway" and r.get("ok"):
        print("pin", requests.post(f"{api}/pinChatMessage", data={"chat_id": chat, "message_id": r["result"]["message_id"],
                                                                 "disable_notification": "true"}).text[:100])
elif action == "delete":
    # value: comma separated message ids
    for mid in [m.strip() for m in value.split(",") if m.strip()]:
        r = requests.post(f"{api}/deleteMessage", data={"chat_id": chat, "message_id": mid})
        print("delete", mid, r.status_code, r.text[:120])
elif action == "repin":
    # edit the current pinned post in place (no new notification); post + pin a new one if there isn't one
    pinned = (requests.get(f"{api}/getChat", params={"chat_id": chat}).json().get("result") or {}).get("pinned_message") or {}
    r = None
    if pinned.get("message_id"):
        r = requests.post(f"{api}/editMessageText", data={"chat_id": chat, "message_id": pinned["message_id"],
                                                         "text": value, "disable_web_page_preview": "true"})
        print("edit pinned", pinned["message_id"], r.status_code, r.text[:200])
    if not (r is not None and r.ok):
        r = requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": value, "disable_notification": "true",
                                                      "disable_web_page_preview": "true"})
        if r.ok:
            mid = r.json()["result"]["message_id"]
            if pinned.get("message_id"):
                requests.post(f"{api}/unpinChatMessage", data={"chat_id": chat, "message_id": pinned["message_id"]})
            r = requests.post(f"{api}/pinChatMessage", data={"chat_id": chat, "message_id": mid, "disable_notification": "true"})
else:
    sys.exit(f"unknown action {action}")
print(r.status_code, r.text)
sys.exit(0 if r.ok and r.json().get("ok") else 1)
