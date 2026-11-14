"""Change the Telegram channel's settings through the bot.
Usage: python tools/channel.py description "text" | title "text" | photo path/to/image.png
The bot must be a channel admin with the "Change channel info" permission."""
import os, sys, requests
token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
api = f"https://api.telegram.org/bot{token}"
action, value = sys.argv[1], sys.argv[2]
if action == "description":
    r = requests.post(f"{api}/setChatDescription", data={"chat_id": chat, "description": value})
elif action == "title":
    r = requests.post(f"{api}/setChatTitle", data={"chat_id": chat, "title": value})
elif action == "photo":
    with open(value, "rb") as f:
        r = requests.post(f"{api}/setChatPhoto", data={"chat_id": chat}, files={"photo": f})
else:
    sys.exit(f"unknown action {action}")
print(r.status_code, r.text)
sys.exit(0 if r.ok and r.json().get("ok") else 1)
