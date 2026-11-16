import sys, collections
sys.path.insert(0, "tools")
import aliexpress as a
for b in ["Pop Mart", "Bandai", "Disney", "Hasbro", "Miniso", "Kayou"]:
    ps = a.search(keywords=b, page_size=50)
    shops = collections.Counter(p.get("shop_name") for p in ps)
    print("BRAND", b, shops.most_common(6))
