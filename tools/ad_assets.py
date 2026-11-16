"""Fetch a few good-looking AliExpress product photos for ad creatives into data/ad/."""
import sys, json, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import aliexpress as a
OUT = Path(__file__).resolve().parent.parent / "data" / "ad"
OUT.mkdir(parents=True, exist_ok=True)
picked = {}
for name, q, req in [("watch", "Amazfit smart watch", "amazfit"), ("earbuds", "Baseus wireless earbuds", "baseus"),
                     ("powerbank", "Baseus power bank magnetic", "baseus"), ("charger", "UGREEN GaN charger", "ugreen"),
                     ("speaker", "Xiaomi bluetooth speaker", "xiaomi")]:
    try:
        ps = [p for p in a.search(keywords=q, page_size=30) if req in (p.get("product_title") or "").lower()]
    except Exception as e:
        print(name, "failed", e); continue
    ps.sort(key=lambda p: -int(p.get("lastest_volume") or 0))
    for i, p in enumerate(ps[:2]):
        r = requests.get(p["product_main_image_url"], timeout=30)
        if r.ok:
            f = OUT / f"{name}{i + 1}.jpg"
            f.write_bytes(r.content)
            picked[f.name] = p.get("product_title", "")[:80]
print(json.dumps(picked, indent=1))
(OUT / "index.json").write_text(json.dumps(picked, indent=1))
