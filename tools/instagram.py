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


def whoami():
    if not TOKEN:
        sys.exit("IG_ACCESS_TOKEN secret is empty")
    print("token type:", TOKEN[:4] + "…", "length", len(TOKEN))
    checks = [
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
