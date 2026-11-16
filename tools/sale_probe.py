import sys;sys.path.insert(0,"tools");import aliexpress as a
l=a.sale_lists();print("SALE LISTS",l)
if l:
    ps=a.sale_products(l[0]);print("PRODUCTS",len(ps));[print(" ",p.get("target_sale_price"),(p.get("product_title") or "")[:60]) for p in ps[:5]]
