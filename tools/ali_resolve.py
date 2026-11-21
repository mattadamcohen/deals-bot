"""Resolve AliExpress links (short or full) to product details + download the product video.
  URLS="https://s.click.aliexpress.com/e/_xxx ..." python tools/ali_resolve.py
Writes data/ad/vopt/<id>.json (+ <id>.mp4 when there's a video).
"""
import json, os, re, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import aliexpress

OUT = ROOT / "data/ad/vopt"; OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"}


def product_id(url):
    m = re.search(r"/item/(\d{8,})", url) or re.search(r"productIds?=(\d{8,})", url)
    if m:
        return m.group(1)
    r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
    for u in [h.headers.get("location", "") for h in r.history] + [r.url, r.text[:200000]]:
        m = re.search(r"/item/(\d{8,})", u) or re.search(r"productIds?=(\d{8,})", u) or re.search(r"[?&]x_object_id[=:%3A]+(\d{8,})", u)
        if m:
            return m.group(1)
    print("could not resolve", url, r.url[:200])


for url in os.environ.get("URLS", "").split():
    pid = product_id(url)
    if not pid:
        continue
    res = aliexpress.call("aliexpress.affiliate.productdetail.get", product_ids=pid, target_currency="USD",
                          target_language="EN", country="IL", tracking_id=aliexpress.TRACKING_ID)
    prods = aliexpress._products(res)
    if not prods:
        print("no affiliate data for", pid, str(res)[:300]); continue
    p = prods[0]
    p["short_link"] = aliexpress.link(f"https://www.aliexpress.com/item/{pid}.html")
    p["source_url"] = url
    (OUT / f"{pid}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1))
    print("PRODUCT", pid, p.get("target_sale_price"), p.get("lastest_volume"), p.get("evaluate_rate"), p.get("product_title"))
    print("short", p["short_link"], "video", p.get("product_video_url"))
    v = p.get("product_video_url")
    if v:
        r = requests.get(v, headers=UA, timeout=60)
        if r.ok and len(r.content) > 50_000:
            (OUT / f"{pid}.mp4").write_bytes(r.content); print("video saved", len(r.content))
