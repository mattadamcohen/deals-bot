"""Diagnostic: which request styles does Amazon let through from this machine?"""
import time
from curl_cffi import requests as r
URLS = ["https://www.amazon.com/", "https://www.amazon.com/gp/bestsellers/electronics/",
        "https://www.amazon.com/dp/B0BSHF7WHW"]
for imp in ["chrome", "chrome131", "safari", "safari_ios", "firefox", "edge"]:
    for u in URLS:
        try:
            s = r.Session(impersonate=imp)
            s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
            x = s.get(u, timeout=20)
            blocked = "validateCaptcha" in x.text or "Enter the characters" in x.text
            print(f"{imp:11} {x.status_code} {'BLOCKED' if blocked else 'ok     '} {len(x.text):>8}  {u}", flush=True)
        except Exception as e:
            print(f"{imp:11} ERR {e}  {u}", flush=True)
        time.sleep(2)
