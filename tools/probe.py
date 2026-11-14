"""Diagnostic: set Israel location via a best-sellers page, then try product-data endpoints."""
import re, time
from curl_cffi import requests as r
B = "https://www.amazon.com"
def blocked(t): return "validateCaptcha" in t or "Enter the characters" in t
for imp in ["chrome", "safari"]:
    print(f"===== {imp}", flush=True)
    s = r.Session(impersonate=imp); s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
    s.cookies.set("i18n-prefs", "USD", domain=".amazon.com")
    bs = s.get(B + "/gp/bestsellers/electronics/", timeout=20).text
    m = re.search(r'anti-csrftoken-a2z(?:&quot;|")\s*:\s*(?:&quot;|")(.*?)(?:&quot;|")', bs)
    print("bestsellers blocked:", blocked(bs), "token1:", bool(m))
    asins = list(dict.fromkeys(re.findall(r'/dp/([A-Z0-9]{10})', bs)))[:3]
    print("asins:", asins)
    t1 = m.group(1) if m else ""
    sel = s.get(B + "/portal-migration/hz/glow/get-rendered-address-selections?deviceType=desktop&pageType=Gateway&storeContext=NoStoreName&actionSource=desktop-modal",
                headers={"anti-csrftoken-a2z": t1, "x-requested-with": "XMLHttpRequest", "referer": B + "/gp/bestsellers/electronics/"}, timeout=20).text
    m2 = re.search(r'CSRF_TOKEN\s*:\s*"(.*?)"', sel)
    print("selector blocked:", blocked(sel), "token2:", bool(m2), len(sel))
    if m2:
        x = s.post(B + "/portal-migration/hz/glow/address-change?actionSource=glow",
                   json={"locationType": "COUNTRY", "district": "IL", "countryCode": "IL", "storeContext": "generic",
                         "deviceType": "web", "pageType": "Gateway", "actionSource": "glow"},
                   headers={"anti-csrftoken-a2z": m2.group(1), "x-requested-with": "XMLHttpRequest"}, timeout=20)
        print("address-change:", x.status_code, x.text[:150])
    bs2 = s.get(B + "/gp/bestsellers/electronics/", timeout=20).text
    loc = re.search(r'id="glow-ingress-line2"[^>]*>\s*([^<]*)', bs2)
    print("location now:", loc.group(1).strip() if loc else "?", "| page mentions Israel:", "Israel" in bs2)
    for a in asins[:2]:
        for path in [f"/dp/{a}?th=1&psc=1", f"/gp/product/{a}", f"/gp/aw/d/{a}",
                     f"/gp/product/ajax/aodAjaxMain/?asin={a}&pc=dp&experienceId=aodAjaxMain",
                     f"/gp/aod/ajax?asin={a}&pc=dp", f"/gp/product/ajax?asin={a}&experienceId=aodAjaxMain"]:
            time.sleep(3)
            try:
                x = s.get(B + path, timeout=20, headers={"referer": B + "/gp/bestsellers/electronics/"})
                t = x.text
                snip = ""
                mm = re.search(r'([^<>]{0,60}(?:FREE delivery|FREE Shipping|delivery)[^<>]{0,80}Israel[^<>]{0,60})', t, re.I) \
                     or re.search(r'([^<>]{0,80}cannot be shipped[^<>]{0,60})', t)
                if mm: snip = re.sub(r"\s+", " ", mm.group(1))[:160]
                print(f"  {x.status_code} {'BLOCKED' if blocked(t) else 'ok'} {len(t):>7} Israel:{'Israel' in t} {path[:55]:55} {snip}", flush=True)
            except Exception as e:
                print("  ERR", path, e, flush=True)
