"""Dump recent posts of a public Telegram channel via t.me/s/ preview. usage: tg_scrape.py channel [n]"""
import sys, re, html, json, requests
ch = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
posts, before = {}, None
for _ in range(15):
    url = f"https://t.me/s/{ch}" + (f"?before={before}" if before else "")
    t = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    blocks = re.split(r'<div class="tgme_widget_message_wrap', t)[1:]
    ids = []
    for b in blocks:
        m = re.search(r'data-post="[^/]+/(\d+)"', b)
        if not m: continue
        pid = int(m.group(1)); ids.append(pid)
        tx = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', b, re.S)
        txt = html.unescape(re.sub(r"<br\s*/?>", " | ", re.sub(r"<(?!br)[^>]+>", "", tx.group(1)))) if tx else ""
        links = re.findall(r'href="(https?://(?:amzn|www\.amazon|a\.co|s\.click\.aliexpress|[a-z.]*aliexpress)[^"]*)"', b)
        dt = re.search(r'datetime="([^"]+)"', b)
        posts[pid] = (dt.group(1)[:16] if dt else "", txt[:400], links[:1])
    if not ids or len(posts) >= n: break
    before = min(ids)
for pid in sorted(posts, reverse=True)[:n]:
    d, txt, l = posts[pid]
    print(f"#{pid} {d} {txt} {l[0] if l else ''}")
print("TOTAL", len(posts))
