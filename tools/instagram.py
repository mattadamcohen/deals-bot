"""Instagram helper. `python tools/instagram.py whoami` checks the IG_ACCESS_TOKEN and finds the account id."""
import json, os, sys
import requests

TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
V = "v23.0"


def get(url, **params):
    params["access_token"] = TOKEN
    try:
        r = requests.get(url, params=params, timeout=30)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def ig_id():
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text()).get("ig_user_id", "")


def whoami():
    iid = ig_id()
    for host in ("graph.facebook.com", "graph.instagram.com"):
        c, b = get(f"https://{host}/{V}/{iid}", fields="id,username,followers_count,media_count")
        print(f"{host} account:", c, json.dumps(b, ensure_ascii=False)[:300])
        c, b = get(f"https://{host}/{V}/{iid}/content_publishing_limit", fields="config,quota_usage")
        print(f"{host} publishing limit:", c, json.dumps(b, ensure_ascii=False)[:300])
    return

    if not TOKEN:
        sys.exit("IG_ACCESS_TOKEN secret is empty")
    print("token type:", TOKEN[:4] + "…", "length", len(TOKEN))
    code, body = get(f"https://graph.facebook.com/{V}/debug_token", input_token=TOKEN)
    d = body.get("data", {})
    print("debug_token:", code, json.dumps({k: d.get(k) for k in ("type", "app_id", "is_valid", "expires_at", "scopes", "granular_scopes")})[:900])
    ids = {t for g in d.get("granular_scopes", []) for t in g.get("target_ids", [])}
    for i in ids:
        c, b = get(f"https://graph.facebook.com/{V}/{i}", fields="id,username,name")
        print("target", i, c, json.dumps(b, ensure_ascii=False)[:300])
    checks = [
        ("facebook /me/businesses", f"https://graph.facebook.com/{V}/me/businesses",
         {"fields": "name,owned_instagram_accounts{id,username},instagram_business_accounts{id,username}"}),
        ("instagram login /me", f"https://graph.instagram.com/{V}/me", {"fields": "user_id,username,account_type"}),
        ("facebook /me", f"https://graph.facebook.com/{V}/me", {"fields": "id,name"}),
        ("facebook /me/accounts", f"https://graph.facebook.com/{V}/me/accounts",
         {"fields": "name,instagram_business_account{id,username}"}),
        ("facebook /me/instagram_accounts", f"https://graph.facebook.com/{V}/me/instagram_accounts", {"fields": "id,username"}),
    ]
    for name, url, p in checks:
        code, body = get(url, **p)
        print(f"\n== {name}: HTTP {code}\n{json.dumps(body, ensure_ascii=False)[:600]}")


if __name__ == "__main__":
    {"whoami": whoami}[sys.argv[1]]()
