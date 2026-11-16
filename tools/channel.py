"""Change the Telegram channel's settings through the bot.
Usage: python tools/channel.py description "text" | title "text" | photo path/to/image.png
The bot must be a channel admin with the "Change channel info" permission."""
import os, sys, requests
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
