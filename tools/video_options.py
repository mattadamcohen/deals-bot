"""Shortlist catchy AliExpress items that have a product video, download the videos for Matt to choose from.
Also prints recent IG video views so we can see what worked.
  python tools/video_options.py
Output: data/ad/vopt/<n>.mp4 + data/ad/vopt/options.json
"""
import json, os, sys, re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import bot, aliexpress

OUT = ROOT / "data/ad/vopt"; OUT.mkdir(parents=True, exist_ok=True)

# 1. which IG posts got views
T = os.getenv("IG_ACCESS_TOKEN", "").strip()
if T:
    ig = bot.CONFIG["ig_user_id"]
    r = requests.get(f"https://graph.facebook.com/v23.0/{ig}/media",
                     params={"fields": "id,timestamp,media_type,media_product_type,caption,like_count,comments_count", "limit": 30, "access_token": T})
    for m in r.json().get("data", []):
        v = requests.get(f"https://graph.facebook.com/v23.0/{m['id']}/insights", params={"metric": "views,reach", "access_token": T}).json()
        vals = {d["name"]: d["values"][0]["value"] for d in v.get("data", [])} if "data" in v else v.get("error", {}).get("message", "")[:60]
        print("IG", m["timestamp"][:16], m.get("media_product_type"), m["media_type"], vals, "likes", m.get("like_count"),
              (m.get("caption") or "")[:50].replace("\n", " "))

# 2. catchy AliExpress items with video
posted = set(json.load(open(ROOT / "data/state.json")).get("posted", {}))
KW = os.getenv("KW") or ("squishy|slow rising squishy|fidget toy|stress ball squeeze|needoh|robot dog toy|mini claw machine|"
                         "fruit peeler electric|magnetic train track|bubble machine|kinetic sand|slime kit|cute night light|"
                         "mini cotton candy machine|automatic pet toy|led galaxy projector|magnetic building blocks|"
                         "ice cream maker mini|portable blender|label printer|mini robot vacuum|crystal ball lamp")
seen, cands = set(), []
for kw in KW.split("|"):
    try:
        prods = aliexpress.search(keywords=kw, page_size=50)
    except Exception as e:
        print("search fail", kw, e); continue
    for p in prods:
        pid = str(p.get("product_id"))
        if pid in seen or not p.get("product_video_url") or not bot.ali_ok(p):
            continue
        seen.add(pid)
        title = bot.strip_junk(p.get("product_title"))
        cands.append({"kw": kw, "id": pid, "title": title, "price": p.get("target_sale_price"),
                      "sold": int(p.get("lastest_volume") or 0), "rating": p.get("evaluate_rate"),
                      "video": p["product_video_url"], "image": p.get("product_main_image_url"),
                      "link": p.get("promotion_link"), "posted_before": f"ali-{pid}" in posted})
    print(kw, "->", sum(1 for c in cands if c["kw"] == kw))

# best 2 per keyword by sold, then download
best = []
for kw in KW.split("|"):
    best += sorted([c for c in cands if c["kw"] == kw], key=lambda c: -c["sold"])[:2]
keep = []
for i, c in enumerate(best):
    try:
        r = requests.get(c["video"], timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        if not r.ok or len(r.content) < 50_000 or len(r.content) > 40_000_000:
            continue
        name = f"v{i:02d}"
        (OUT / f"{name}.mp4").write_bytes(r.content)
        c["file"] = f"{name}.mp4"; c["bytes"] = len(r.content)
        keep.append(c)
        print("OK", name, c["price"], c["sold"], c["rating"], c["title"][:70])
    except Exception as e:
        print("dl fail", c["id"], e)
(OUT / "options.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1))
print("saved", len(keep))
