import re, sys, requests
for u in sys.argv[1:]:
    r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, allow_redirects=True)
    chain = [h.headers.get("location", "") for h in r.history] + [r.url]
    asin = next((m.group(1) for c in chain for m in [re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", c)] if m), "")
    print("URL", u, "->", r.url[:160], "ASIN", asin)
