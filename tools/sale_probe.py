import sys
sys.path.insert(0, "tools")
import aliexpress as a
for q in ["SVBONY night vision binocular", "SVBONY SX31 night vision", "night vision binoculars SVBONY"]:
    try:
        ps = a.search(keywords=q, page_size=30)
        print("Q", q, len(ps))
        for p in ps[:6]:
            print("  ", p["product_id"], p.get("target_sale_price"), p.get("lastest_volume"), (p.get("product_title") or "")[:70])
    except Exception as e:
        print("Q", q, "ERR", e)
