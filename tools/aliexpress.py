"""AliExpress Affiliate API client (Open Platform, api-sg gateway).

Usage (test):  python tools/aliexpress.py test [keywords]
Needs env ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET, optional ALIEXPRESS_TRACKING_ID.
"""
import hashlib
import hmac
import json
import os
import sys
import time

import requests

GATEWAY = "https://api-sg.aliexpress.com/sync"
TRACKING_ID = os.environ.get("ALIEXPRESS_TRACKING_ID") or "ilamazondeals"


class AliError(Exception):
    pass


def _sign(params, secret):
    base = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest().upper()


def call(method, **biz):
    key = os.environ.get("ALIEXPRESS_APP_KEY", "").strip()
    secret = os.environ.get("ALIEXPRESS_APP_SECRET", "").strip()
    if not key or not secret:
        raise AliError("ALIEXPRESS_APP_KEY / ALIEXPRESS_APP_SECRET not set")
    params = {
        "app_key": key,
        "method": method,
        "timestamp": str(int(time.time() * 1000)),
        "sign_method": "sha256",
        "format": "json",
        "v": "2.0",
    }
    params.update({k: str(v) for k, v in biz.items() if v is not None and v != ""})
    params["sign"] = _sign(params, secret)
    r = requests.post(GATEWAY, data=params, timeout=30)
    try:
        data = r.json()
    except ValueError:
        raise AliError(f"HTTP {r.status_code}: {r.text[:300]}")
    if "error_response" in data:
        raise AliError(json.dumps(data["error_response"])[:500])
    resp = data.get(method.replace(".", "_") + "_response", data)
    result = resp.get("resp_result", resp)
    code = result.get("resp_code")
    if code not in (None, 200, "200"):
        raise AliError(f"resp_code {code}: {result.get('resp_msg')}")
    return result.get("result", result)


def _products(result):
    prods = (result or {}).get("products") or {}
    if isinstance(prods, dict):
        prods = prods.get("product") or []
    return prods


def hot_products(keywords=None, category_ids=None, page=1, page_size=50,
                 sort="LAST_VOLUME_DESC", ship_to="IL", min_price=None, max_price=None):
    """Hot (high-commission, popular) products shipping to Israel, with affiliate links."""
    res = call(
        "aliexpress.affiliate.hotproduct.query",
        keywords=keywords, category_ids=category_ids,
        page_no=page, page_size=page_size, sort=sort,
        ship_to_country=ship_to, target_currency="USD", target_language="EN",
        tracking_id=TRACKING_ID,
        min_sale_price=min_price, max_sale_price=max_price,
        fields="product_id,product_title,product_main_image_url,target_sale_price,"
               "target_original_price,discount,promotion_link,lastest_volume,"
               "evaluate_rate,first_level_category_name,second_level_category_name,shop_id",
    )
    return _products(res)


def search(keywords=None, category_ids=None, page=1, page_size=50,
           sort="LAST_VOLUME_DESC", ship_to="IL"):
    res = call(
        "aliexpress.affiliate.product.query",
        keywords=keywords, category_ids=category_ids,
        fields="product_id,product_title,product_main_image_url,product_small_image_urls,target_sale_price,"
               "target_original_price,discount,promotion_link,lastest_volume,evaluate_rate,"
               "first_level_category_name,second_level_category_name,shop_id,promo_code_info,product_video_url",
        page_no=page, page_size=page_size, sort=sort,
        ship_to_country=ship_to, target_currency="USD", target_language="EN",
        tracking_id=TRACKING_ID,
    )
    return _products(res)


def sale_lists():
    """AliExpress's own curated lists for the sale running today, e.g. '1101-1118 11.11 Sale - Bestsellers'."""
    import datetime, re as _re
    today = datetime.date.today().strftime("%m%d")
    res = call("aliexpress.affiliate.featuredpromo.get")
    promos = (res.get("promos") or {}).get("promo") or []
    out = []
    for p in promos:
        n = p.get("promo_name") or ""
        m = _re.match(r"(\d{4})-(\d{4})\s", n)
        if m and m.group(1) <= today <= m.group(2) and _re.search(r"bestseller|big save|top brand|hot", n, _re.I):
            out.append(n)
    return out


def sale_products(name, page=1, page_size=50, ship_to="IL"):
    res = call("aliexpress.affiliate.featuredpromo.products.get", promotion_name=name,
               page_no=page, page_size=page_size, sort="LAST_VOLUME_DESC",
               ship_to_country=ship_to, target_currency="USD", target_language="EN", tracking_id=TRACKING_ID,
               fields="product_id,product_title,product_main_image_url,product_small_image_urls,target_sale_price,"
                      "target_original_price,discount,promotion_link,lastest_volume,evaluate_rate,"
                      "first_level_category_name,second_level_category_name,shop_id,promo_code_info,product_video_url")
    return _products(res)


def link(url):
    """Turn any AliExpress URL into an affiliate link."""
    res = call("aliexpress.affiliate.link.generate", promotion_link_type=0,
               source_values=url, tracking_id=TRACKING_ID)
    links = (res.get("promotion_links") or {}).get("promotion_link") or []
    return links[0]["promotion_link"] if links else None


def promos():
    """What promotion data the API gives us: featured promos + per-product promo codes."""
    for m, kw in (("aliexpress.affiliate.featuredpromo.get", {}),):
        try:
            print("==", m, json.dumps(call(m, **kw), ensure_ascii=False)[:1500])
        except AliError as e:
            print("==", m, "ERROR", e)
    res = call("aliexpress.affiliate.product.query", keywords="power bank", page_size=50, ship_to_country="IL",
               target_currency="USD", target_language="EN", tracking_id=TRACKING_ID,
               fields="product_id,product_title,promo_code_info,target_sale_price")
    prods = _products(res)
    withcode = [p for p in prods if p.get("promo_code_info")]
    print(f"== product promo codes: {len(withcode)}/{len(prods)} products have one")
    for p in withcode[:5]:
        print("  ", p.get("target_sale_price"), (p.get("product_title") or "")[:50], json.dumps(p["promo_code_info"])[:300])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "promos":
        return promos()
    if len(sys.argv) < 2 or sys.argv[1] != "test":
        print(__doc__)
        return
    kw = " ".join(sys.argv[2:]) or None
    ok = True
    for name, fn in (("hotproduct", hot_products), ("product.query", search)):
        try:
            items = fn(keywords=kw, page_size=10)
            print(f"== {name}: {len(items)} products")
            for p in items[:10]:
                print(f"  {p.get('target_sale_price')} USD (was {p.get('target_original_price')}, "
                      f"-{p.get('discount')}) sold {p.get('lastest_volume')} | "
                      f"{(p.get('product_title') or '')[:70]}")
                print(f"     link ok: {bool(p.get('promotion_link'))}")
        except AliError as e:
            if "InsufficientPermission" in str(e):
                print(f"== {name}: not enabled for this app yet (needs the Apply Online approval)")
                continue
            ok = False
            print(f"== {name}: ERROR {e}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
