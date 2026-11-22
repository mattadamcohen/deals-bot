import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aliexpress
seen = set()
for q in ["needoh", "nee doh", "schylling needoh", "needoh nice cube", "needoh gumdrop"]:
    for p in aliexpress.search(keywords=q, page_size=50):
        pid = p.get("product_id")
        if pid in seen:
            continue
        seen.add(pid)
        t = (p.get("product_title") or "")
        if "doh" in t.lower():
            print("ALI", pid, p.get("target_sale_price"), p.get("lastest_volume"), p.get("evaluate_rate"), "|", p.get("shop_name") or p.get("shop_id"), "|", t[:80])
