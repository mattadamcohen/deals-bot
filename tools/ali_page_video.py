"""Find product videos on an AliExpress item page (when the API has none).
  IDS="1005..." python tools/ali_page_video.py
"""
import os, re, sys
from pathlib import Path
import requests
OUT = Path(__file__).resolve().parent.parent / "data/ad/vopt"; OUT.mkdir(parents=True, exist_ok=True)
UAS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"]
for pid in os.environ.get("IDS", "").split():
    found = []
    for host in ("www.aliexpress.com", "he.aliexpress.com", "m.aliexpress.com"):
        for ua in UAS:
            try:
                t = requests.get(f"https://{host}/item/{pid}.html", headers={"User-Agent": ua, "Accept-Language": "en"}, timeout=30).text
            except Exception as e:
                print(host, e); continue
            t2 = t.replace("\\/", "/").replace("\\u002F", "/")
            urls = set(re.findall(r'https?://[^"\'\s]+?\.mp4[^"\'\s]*', t2))
            vids = set(re.findall(r'"videoId"\s*:\s*"?(\d+)', t2)) | set(re.findall(r'"videoUid"\s*:\s*"([^"]+)"', t2))
            print(host, ua[:20], len(t), "mp4:", len(urls), "videoIds:", vids)
            for u in urls:
                found.append(u)
            for v in vids:
                found.append(f"https://video.aliexpress-media.com/play/u/ae_sg_item/{v}.mp4")
                found.append(f"https://cloud.video.taobao.com/play/u/null/p/1/e/6/t/1/{v}.mp4")
        if found:
            break
    for i, u in enumerate(dict.fromkeys(found)):
        try:
            r = requests.get(u, headers={"User-Agent": UAS[0], "Referer": "https://www.aliexpress.com/"}, timeout=60)
            print("try", u[:120], r.status_code, len(r.content))
            if r.ok and len(r.content) > 100_000:
                (OUT / f"{pid}.mp4").write_bytes(r.content); print("SAVED", u); break
        except Exception as e:
            print("fail", u[:100], e)
