import sys, json
sys.path.insert(0, "tools")
import aliexpress as a
ps = a.search(keywords="squishy toy", page_size=50)
print("KEYS", sorted(ps[0].keys()) if ps else None)
v = [p for p in ps if p.get("product_video_url")]
print("WITH VIDEO", len(v), "/", len(ps), [p["product_video_url"][:90] for p in v[:3]])
res = a.call("aliexpress.affiliate.productdetail.get", product_ids=",".join(str(p["product_id"]) for p in ps[:10]),
             target_currency="USD", target_language="EN", country="IL", tracking_id=a.TRACKING_ID)
d = a._products(res)
print("DETAIL KEYS", sorted(d[0].keys()) if d else res)
print("DETAIL VIDEOS", [p.get("product_video_url", "")[:90] for p in d if p.get("product_video_url")][:3])
