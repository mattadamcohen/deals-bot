"""Print recent IG media and status of given ids."""
import json, os, sys, requests
T = os.getenv("IG_ACCESS_TOKEN", "").strip()
ig = json.load(open("config.json"))["ig_user_id"]
r = requests.get(f"https://graph.facebook.com/v23.0/{ig}/media", params={"fields": "id,permalink,timestamp,media_type,caption", "limit": 8, "access_token": T})
for m in r.json().get("data", []):
    print(m["id"], m["timestamp"], m["media_type"], m.get("permalink"), (m.get("caption") or "")[:40].replace("\n", " "))
for i in sys.argv[1:]:
    print(i, requests.get(f"https://graph.facebook.com/v23.0/{i}", params={"fields": "permalink,timestamp,is_shared_to_feed,username", "access_token": T}).text[:300])
for i in sys.argv[1:]:
    for c in requests.get(f"https://graph.facebook.com/v23.0/{i}/comments", params={"fields": "id,text", "access_token": T}).json().get("data", []):
        print("COMMENT", c["id"], len(c["text"]), c["text"][:140].replace("\n", " "))
