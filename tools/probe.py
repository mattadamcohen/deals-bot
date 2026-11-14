"""Diagnostic: print the title of candidate Best Sellers sub-lists."""
import re, time, sys
from curl_cffi import requests as r
s = r.Session(impersonate="safari"); s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
for path in sys.argv[1:]:
    t = s.get(f"https://www.amazon.com/gp/bestsellers/{path}/", timeout=20).text
    m = re.search(r"<title>(.*?)</title>", t, re.S)
    n = len(set(re.findall(r'/dp/([A-Z0-9]{10})', t)))
    print(f"{path:28} items={n:3}  {m.group(1).strip()[:90] if m else '?'}", flush=True)
    time.sleep(3)
