"""
Amazon best-seller -> Telegram channel bot.

Every run it:
  1. sets the Amazon.com delivery location to Israel,
  2. reads the Best Sellers list of a few categories (rotating through all of them),
  3. opens each top item and keeps only those showing FREE delivery to Israel,
  4. posts new ones to your Telegram channel (no repeats within REPOST_AFTER_DAYS).

Settings live in config.json. Secrets come from environment variables:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (e.g. @mychannel), optional AMAZON_TAG.
Set DRY_RUN=1 to print posts instead of sending them.
"""

import html
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text())
STATE_FILE = ROOT / "data" / "state.json"
DEBUG_DIR = ROOT / "debug"
BASE = "https://www.amazon.com"

DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
OWNER_TEST = os.getenv("OWNER_TEST", "").lower() in ("1", "true", "yes")  # send test posts to Matt only
if OWNER_TEST:
    TG_CHAT = str(CONFIG.get("owner_chat_id", ""))
ALI_ON = bool(os.getenv("ALIEXPRESS_APP_KEY") and os.getenv("ALIEXPRESS_APP_SECRET"))
AMAZON_TAG = (os.getenv("AMAZON_TAG") or CONFIG.get("amazon_tag", "")).strip()


class Blocked(Exception):
    """Amazon served a captcha / robot check."""


# ---------------------------------------------------------------- utilities

def log(*a):
    print(*a, flush=True)


def save_debug(name, text):
    DEBUG_DIR.mkdir(exist_ok=True)
    (DEBUG_DIR / name).write_text(text or "", encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"next_category": 0, "posted": {}, "not_free": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))


def now():
    return datetime.now(timezone.utc)


def is_recent(iso, days):
    try:
        return now() - datetime.fromisoformat(iso) < timedelta(days=days)
    except Exception:
        return False


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def money(text):
    m = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    return float(m.group().replace(",", "")) if m else 0.0


def big_image(url):
    # Amazon image URLs carry a size token like ._AC_UL300_SR300,200_. ; removing it gives the full image
    return re.sub(r"\._[^/]*?_\.(jpg|jpeg|png|webp)$", r".\1", url or "", flags=re.I)


# ---------------------------------------------------------------- amazon

COLOR_SIZE = re.compile(r"\b(black|white|blue|red|green|pink|purple|grey|gray|denim|cherry|navy|beige|brown|gold|silver|"
                        r"rose|yellow|orange|teal|clear|small|medium|large|xl|xxl|xs|mini|kids|adult|men'?s|women'?s|"
                        r"\d+(\.\d+)?\s*(oz|ml|l|ft|in|inch|cm|mm|pack|pcs|count|ct|piece|pieces|pk)?)\b", re.I)


def title_family(title):
    """Rough product-family key from a title: same brand + product words, ignoring color/size/pack details."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", (title or "").lower())
    t = re.split(r"[,|]| - ", t)[0]
    t = COLOR_SIZE.sub(" ", t)
    words = re.findall(r"[a-z][a-z'&+-]*", t)
    return " ".join(words[:4])


def price_text(el):
    """Text of an .a-price element: the hidden full price, or symbol + whole + fraction."""
    if el is None:
        return ""
    off = el.select_one(".a-offscreen")
    t = clean(off.get_text()) if off else ""
    if re.search(r"\d", t):
        return t
    whole = el.select_one(".a-price-whole")
    if whole:
        frac = el.select_one(".a-price-fraction")
        sym = el.select_one(".a-price-symbol")
        w = re.sub(r"[^\d,]", "", whole.get_text())
        return f"{clean(sym.get_text()) if sym else '$'}{w}.{clean(frac.get_text()) if frac else '00'}"
    t = clean(el.get_text())
    return t if re.search(r"\$\s*\d", t) else ""


def find_prices(soup, page):
    """(price, was) from a product page, trying the places Amazon puts prices for simple and multi-variant items."""
    price = was = ""
    for box_sel in ("#corePriceDisplay_desktop_feature_div", "#corePrice_feature_div", "#corePrice_desktop",
                    "#apex_desktop", "#apex_offerDisplay_desktop", "#desktop_buybox", "#buybox"):
        box = soup.select_one(box_sel)
        if not box:
            continue
        price = price or price_text(box.select_one(".priceToPay")) or price_text(
            next((e for e in box.select(".a-price") if "a-text-price" not in (e.get("class") or [])), None))
        was = was or price_text(box.select_one(".basisPrice .a-price, .a-price.a-text-price"))
        if price:
            break
    if not price:
        for sel in ("#priceblock_dealprice", "#priceblock_ourprice", "#priceblock_saleprice", "#price_inside_buybox",
                    "#tp_price_block_total_price_ww", "#sns-base-price", "#price"):
            el = soup.select_one(sel)
            if el:
                price = price_text(el) if el.select_one(".a-price, .a-offscreen") else clean(el.get_text())
                if re.search(r"\d", price):
                    break
                price = ""
    if not price:
        el = soup.select_one("#twister-plus-price-data-price")
        if el and el.get("value"):
            price = f"${float(el['value']):.2f}"
    if not price:
        m = re.search(r'"priceAmount"\s*:\s*([\d.]+)', page) or re.search(r'"displayPrice"\s*:\s*"\$([\d.,]+)"', page)
        if m:
            price = f"${float(m.group(1).replace(',', '')):.2f}"
    m = re.search(r"\$\s*[\d,]+(?:\.\d{2})?", price or "")
    price = m.group(0).replace(" ", "") if m else ""
    m = re.search(r"\$\s*[\d,]+(?:\.\d{2})?", was or "")
    was = m.group(0).replace(" ", "") if m else ""
    return price, was


CACHE_DIR = ROOT / ".cache"
COOKIES_F = CACHE_DIR / "amazon_cookies.json"
PRODUCTS_F = CACHE_DIR / "products.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


class Amazon:
    def save_cookies(self):
        CACHE_DIR.mkdir(exist_ok=True)
        jar = [{"name": c.name, "value": c.value, "domain": c.domain} for c in self.s.cookies.jar]
        COOKIES_F.write_text(json.dumps(jar))

    def load_cookies(self):
        for c in load_json(COOKIES_F, []):
            self.s.cookies.set(c["name"], c["value"], domain=c["domain"])

    def location_is_israel(self):
        """Check the delivery location using a Best Sellers page (one request)."""
        page = self.get(BASE + "/gp/bestsellers/").text
        el = BeautifulSoup(page, "html.parser").select_one("#glow-ingress-line2")
        where = clean(el.get_text()) if el else "?"
        log(f"  saved session delivers to: {where}")
        return "israel" in where.lower()

    def __init__(self, impersonate="safari"):
        self.s = cffi_requests.Session(impersonate=impersonate)
        self.s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
        # show prices in USD even with an Israeli delivery address
        self.s.cookies.set("i18n-prefs", "USD", domain=".amazon.com")
        self.requests_made = 0
        self.cache_hits = 0

    def get(self, url, **kw):
        if self.requests_made:
            time.sleep(random.uniform(*CONFIG["delay_seconds"]))
        self.requests_made += 1
        kw.setdefault("headers", {}).setdefault("referer", BASE + "/gp/bestsellers/")
        r = self.s.get(url, timeout=30, **kw)
        body = r.text
        if "validateCaptcha" in body or "Enter the characters you see below" in body or r.status_code == 503:
            save_debug("captcha.html", body)
            raise Blocked(f"robot check on {url} (HTTP {r.status_code})")
        return r

    def set_location_israel(self):
        # Amazon blocks the homepage for bots but serves Best Sellers pages, so start there
        home = self.get(BASE + "/gp/bestsellers/").text
        m = re.search(r'anti-csrftoken-a2z(?:&quot;|")\s*:\s*(?:&quot;|")(.*?)(?:&quot;|")', home)
        token1 = m.group(1) if m else ""
        sel = self.get(
            BASE + "/portal-migration/hz/glow/get-rendered-address-selections"
            "?deviceType=desktop&pageType=Gateway&storeContext=NoStoreName&actionSource=desktop-modal",
            headers={"anti-csrftoken-a2z": token1, "x-requested-with": "XMLHttpRequest"},
        ).text
        m2 = re.search(r'CSRF_TOKEN\s*:\s*"(.*?)"', sel)
        if not m2:
            save_debug("location_selector.html", sel)
            log("! could not find location token")
            return False
        self.requests_made += 1
        r = self.s.post(
            BASE + "/portal-migration/hz/glow/address-change?actionSource=glow",
            json={"locationType": "COUNTRY", "district": "IL", "countryCode": "IL",
                  "storeContext": "generic", "deviceType": "web", "pageType": "Gateway",
                  "actionSource": "glow"},
            headers={"anti-csrftoken-a2z": m2.group(1), "x-requested-with": "XMLHttpRequest"},
            timeout=30,
        )
        log(f"  location change -> HTTP {r.status_code}")
        check = BeautifulSoup(self.get(BASE + "/gp/bestsellers/").text, "html.parser").select_one("#glow-ingress-line2")
        where = clean(check.get_text()) if check else "?"
        log(f"  delivering to: {where}")
        return "israel" in where.lower()

    def search(self, query, require=()):
        """First organic (non-sponsored) search result whose title contains all `require` words. Returns ASIN or None."""
        from urllib.parse import quote_plus
        page = self.get(f"{BASE}/s?k={quote_plus(query)}").text
        soup = BeautifulSoup(page, "html.parser")
        for card in soup.select('div[data-component-type="s-search-result"][data-asin]'):
            asin = card.get("data-asin")
            if not re.fullmatch(r"[A-Z0-9]{10}", asin or "") or "AdHolder" in " ".join(card.get("class", [])):
                continue
            if card.select_one(".puis-sponsored-label-text, .s-sponsored-label-info-icon"):
                continue
            h = card.select_one("h2")
            title = (h.get_text(" ", strip=True) if h else "").lower()
            if all(w.lower() in title for w in require):
                return asin
        return None

    def search_all(self, query, require_any=()):
        """All organic search results whose title contains any of `require_any`: [(asin, title)]."""
        from urllib.parse import quote_plus
        soup = BeautifulSoup(self.get(f"{BASE}/s?k={quote_plus(query)}").text, "html.parser")
        out = []
        for card in soup.select('div[data-component-type="s-search-result"][data-asin]'):
            asin = card.get("data-asin")
            if not re.fullmatch(r"[A-Z0-9]{10}", asin or "") or "AdHolder" in " ".join(card.get("class", [])) \
                    or card.select_one(".puis-sponsored-label-text, .s-sponsored-label-info-icon"):
                continue
            # the h2 is sometimes just the brand ("Schylling"); match against the whole card text
            title = card.get_text(" ", strip=True)[:300]
            if not require_any or any(w.lower() in title.lower() for w in require_any):
                out.append((asin, title))
        return out

    def best_sellers(self, slug, page=1, kind="bestsellers"):
        url = f"{BASE}/gp/{kind}/{slug}/" + (f"?pg={page}" if page > 1 else "")
        page = self.get(url).text
        soup = BeautifulSoup(page, "html.parser")
        items, seen = [], set()

        # 1) the grid cards (rank badge + asin)
        for card in soup.select("#gridItemRoot, div.zg-grid-general-faceout, li.zg-item-immersion"):
            asin_el = card.select_one("[data-asin]") or card.select_one("div[id]")
            asin = asin_el.get("data-asin") or asin_el.get("id") if asin_el else None
            if not asin or not re.fullmatch(r"[A-Z0-9]{10}", asin or ""):
                link = card.select_one("a[href*='/dp/']")
                m = re.search(r"/dp/([A-Z0-9]{10})", link["href"]) if link else None
                asin = m.group(1) if m else None
            if not asin or asin in seen:
                continue
            seen.add(asin)
            rank = card.select_one(".zg-bdg-text")
            img = card.select_one("img")
            items.append({
                "asin": asin,
                "rank": int(re.sub(r"\D", "", rank.get_text()) or 0) if rank else len(items) + 1,
                "title": clean(img.get("alt")) if img else "",
                "image": big_image(img.get("src")) if img else "",
            })

        # 2) fallback: any product links in page order
        if not items:
            for m in re.finditer(r"/dp/([A-Z0-9]{10})", page):
                if m.group(1) not in seen:
                    seen.add(m.group(1))
                    items.append({"asin": m.group(1), "rank": len(items) + 1, "title": "", "image": ""})

        if not items:
            save_debug(f"bestsellers_{slug}.html", page)
        return sorted(items, key=lambda x: x["rank"])  # rank as shown on that list

    def product(self, asin):
        cache = load_json(PRODUCTS_F, {})
        hit = cache.get(asin)
        if hit and is_recent(hit.get("_at", ""), CONFIG.get("product_cache_hours", 6) / 24):
            self.cache_hits += 1
            return {k: v for k, v in hit.items() if k != "_at"}
        info = self._product(asin)
        if info["shipping"] in ("free", "paid", "no"):
            cache[asin] = {**info, "_at": now().isoformat()}
            cache = {a: v for a, v in cache.items() if is_recent(v.get("_at", ""), 1)}
            CACHE_DIR.mkdir(exist_ok=True)
            PRODUCTS_F.write_text(json.dumps(cache))
        return info

    def _product(self, asin):
        page = self.get(f"{BASE}/dp/{asin}").text
        soup = BeautifulSoup(page, "html.parser")

        def text(sel):
            el = soup.select_one(sel)
            return clean(el.get_text(" ")) if el else ""

        delivery = " ".join(filter(None, [
            text("#mir-layout-DELIVERY_BLOCK"),
            text("#deliveryBlockMessage"),
            text("#amazonGlobal_feature_div"),
            text("#exports_desktop_qualifiedBuybox_tlc_feature_div"),
        ]))
        if "israel" not in delivery.lower():
            # fallback: look for an Israel delivery message anywhere in the buy box area
            m = re.search(r"(FREE (?:delivery|Shipping)[^<]{0,120}Israel[^<]{0,80}|[^<>]{0,80}cannot be shipped to your selected delivery location)", page, re.I)
            if m:
                delivery += " " + clean(m.group(1))
        low = delivery.lower()
        if "cannot be shipped" in low or "currently unavailable" in text("#availability").lower():
            shipping = "no"
        elif "free" in low and "israel" in low:
            shipping = "free"
        elif "israel" in low:
            shipping = "paid"
        else:
            shipping = "unknown"
            save_debug(f"product_{asin}.html", page)

        price, was = find_prices(soup, page)
        if not price:
            save_debug(f"noprice_{asin}.html", page)
        discount = text("#corePriceDisplay_desktop_feature_div .savingsPercentage").lstrip("-")

        img = soup.select_one("#landingImage, #imgBlkFront")
        image = ""
        if img:
            image = img.get("data-old-hires") or ""
            if not image and img.get("data-a-dynamic-image"):
                try:
                    image = max(json.loads(img["data-a-dynamic-image"]).items(), key=lambda kv: kv[1][0])[0]
                except Exception:
                    pass
            image = image or img.get("src", "")

        gallery = []
        for u in re.findall(r'"hiRes":"(https://[^"]+?\.jpg)"', page):
            if u not in gallery and u != image:
                gallery.append(u)
        images = ([image] if image else []) + gallery[:CONFIG.get("photos_per_post", 3) - 1]
        vids = re.findall(r'"(https://m\.media-amazon\.com/images/S/[^"]+?\.mp4)"', page)
        video = vids[0] if vids else ""

        rating = text("#acrPopover .a-icon-alt").split(" out")[0]
        reviews = re.sub(r"[^\d,]", "", text("#acrCustomerReviewText"))

        m = re.search(r'"parentAsin"\s*:\s*"([A-Z0-9]{10})"', page)
        return {
            "parent_asin": m.group(1) if m else "",
            "title": text("#productTitle"),
            "price": price, "was": was if money(was) > money(price) > 0 else "", "discount": discount,
            "rating": rating, "reviews": reviews, "image": image, "images": images, "video": video,
            "shipping": shipping, "delivery_text": delivery[:200],
        }


# ---------------------------------------------------------------- telegram

def product_link(asin):
    return f"{BASE}/dp/{asin}" + (f"?tag={AMAZON_TAG}" if AMAZON_TAG else "")


_he_cache = {}


def to_hebrew(text):
    """Machine-translate a short English string to Hebrew; falls back to the original."""
    if not text:
        return text
    if text in _he_cache:
        return _he_cache[text]
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "en", "tl": "iw", "dt": "t", "q": text}, timeout=15)
        out = "".join(part[0] for part in r.json()[0] if part and part[0]).strip()
    except Exception as e:
        log(f"  (translation failed: {e})")
        out = ""
    _he_cache[text] = out or text
    return _he_cache[text]


def esc(text):
    return html.escape(text, quote=False)


def short(title, limit=140):
    return title if len(title) <= limit else title[:limit - 3].rsplit(" ", 1)[0] + "…"


def seasonal_lines(category_slug, lang):
    today = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    out = [x[lang] for x in CONFIG.get("seasons", []) if x["from"] <= today <= x["to"]]
    g = CONFIG.get("gift_season")
    if g and g["from"] <= today <= g["to"] and any(category_slug.startswith(c) for c in g["categories"]):
        out.append(g[lang])
        if today <= g.get("early_until", ""):
            out.append(g["early_" + lang])
    return out


def pick(options, v):
    """Pick variant v of a label (labels can be a single string or a list of variants)."""
    return options[v % len(options)] if isinstance(options, list) else options


def block(item, category, title, L, extra=(), v=0):
    ali = item.get("store") == "aliexpress"
    head = pick(L["pick_head"] if item.get("source") == "pick" else L["ali_head"] if ali
                else L["trending"] if item.get("source") == "movers-and-shakers" else L["rank"], v)
    intro = pick(L.get("intro", [""]), v // 3)
    lines = ([intro, ""] if intro else []) + [f"🔥 {esc(head.format(rank=item['rank'], category=category, sold=item.get('sold', '')))}", "",
                                              f"<b>{esc(short(title))}</b>", ""]
    if item.get("price"):
        p = f"💰 <b>{esc(shekels(item['price']))}</b>"
        if item.get("was"):
            p += f"  <s>{esc(shekels(item['was']))}</s>"
        if item.get("discount"):
            p += f"  ({esc(item['discount'])} {L['off']})"
        lines.append(p)
    cp = item.get("coupon")
    if cp:
        lines.append(f"🎟️ {pick(L['coupon'], v).format(code=f"<code>{esc(cp['code'])}</code>", off=f'${cp["off"]:g}', min=f'${cp["min"]:g}')}")
    if item.get("rating"):
        star = "👍" if ali else "⭐"
        lines.append(f"{star} {esc(item['rating'])}" + (f" ({item['reviews']})" if item.get("reviews") else ""))
    lines.append(f"🇮🇱 {pick(L['ali_shipping'] if ali else L['free_shipping'], v // 2)}")
    if extra:
        lines += ["", *extra]
    url = item.get("link") or product_link(item["asin"])
    lines.append(f'👉 <a href="{esc(url)}">{pick(L["ali_view"] if ali else L["view"], v // 4)}</a>')
    return "\n".join(lines)


XMAS = re.compile(r"\s*[-,|]?\s*\b(?:(?:great |perfect |cool |unique )?(?:christmas|xmas|holiday) (?:gifts?|presents?)(?: (?:for|ideas?)[^,|]*)?|stocking stuffers?(?: for [^,|]*)?|christmas|xmas)\b", re.I)


def drop_christmas(title):
    """Israeli audience: remove Christmas / stocking-stuffer wording from Amazon titles."""
    t = XMAS.sub("", title)
    return re.sub(r"\s{2,}", " ", re.sub(r"[\s,|-]+$", "", t)).strip() or title


def caption(item, category):
    L = CONFIG["labels"]
    title = strip_junk(drop_christmas(item["title"] or "Best seller"))
    if item.get("style_of"):  # unofficial "brand-style" item (e.g. NeeDoh-style squishy): never present it as the brand
        brand = item["style_of"]
        rest = re.sub(r"(?i)@|\bschylling\b|\bsuper\b(?=\s*nee)|\bnee[\s-]?doh\b", " ", title)
        rest = re.sub(r"\s{2,}", " ", rest).strip(" ,-|") or "squishy"
        title = f"{brand}-style {rest}"
        item["title"] = title  # the log and the website show the honest name too
        title_he = f"בסגנון {brand}: " + to_hebrew(short(rest))
    else:
        title_he = to_hebrew(short(title))
    item["title_he"] = title_he
    v = item.setdefault("variant", random.randrange(1000))  # same variant for both languages; stable on re-edits
    he = block(item, category["he"], title_he, L["he"], seasonal_lines(category["slug"], "he") + ([item["note_he"]] if item.get("note_he") else []), v)
    en = block(item, category["en"], title, L["en"], seasonal_lines(category["slug"], "en") + ([item["note_en"]] if item.get("note_en") else []), v)
    sep = pick(["〰️〰️〰️〰️〰️", "• • • • •", "➖➖➖➖➖", "✨✨✨"], v // 5)
    return he + f"\n\n{sep}\n\n" + en


def remember_post(item, category):
    """Save the post's details and product photo under data/ (used to make social videos)."""
    img_dir = ROOT / "data" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    try:
        if item.get("image"):
            r = requests.get(item["image"], timeout=30)
            if r.ok:
                (img_dir / f"{item['asin']}.jpg").write_bytes(r.content)
    except Exception as e:
        log(f"  (image save failed: {e})")
    log_file = ROOT / "data" / "posts.json"
    posts = json.loads(log_file.read_text()) if log_file.exists() else []
    posts.append({k: item.get(k, "") for k in ("asin", "title", "title_he", "price", "was", "discount", "rating", "reviews", "rank", "source", "message_id", "image", "variant", "store", "link", "sold", "album_ids", "coupon", "video")}
                 | {"category_slug": category["slug"], "category_en": category["en"], "category_he": category["he"],
                    "posted_at": now().isoformat()})
    posts = posts[-40:]
    keep = {p["asin"] for p in posts}
    for f in img_dir.glob("*.jpg"):
        if f.stem not in keep:
            f.unlink()
    log_file.write_text(json.dumps(posts, indent=1, ensure_ascii=False))


def is_big_deal(item):
    off = int(re.sub(r"\D", "", item.get("discount") or "") or 0)
    top = item.get("source") != "movers-and-shakers" and (item.get("rank") or 99) <= CONFIG.get("notify_max_rank", 3)
    return off >= CONFIG.get("notify_min_discount", 30) or top


def square_photo(url):
    """Download the product photo and center it on a white square, so Telegram shows it uncropped."""
    from io import BytesIO
    from PIL import Image
    try:
        im = Image.open(BytesIO(requests.get(url, timeout=30).content)).convert("RGB")
    except Exception as e:
        log(f"  (photo download failed: {e})")
        return None
    side = 1080
    im.thumbnail((side - 80, side - 80), Image.LANCZOS)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    buf = BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def fetch_video(url):
    """Download a product video (mp4) if it's small enough for Telegram (bot upload limit ~50MB)."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=60, stream=True)
        if not r.ok or not (r.headers.get("content-type", "").startswith("video") or ".mp4" in url.lower()):
            return None
        data = b""
        for chunk in r.iter_content(1 << 20):
            data += chunk
            if len(data) > CONFIG.get("max_video_mb", 40) * (1 << 20):
                log("  (video too large, skipping it)")
                return None
        return data if len(data) > 50_000 else None
    except Exception as e:
        log(f"  (video download failed: {e})")
        return None


def send_telegram(item, category):
    """Post to the channel. Returns the Telegram message id (or True on a dry run), None on failure."""
    text = caption(item, category)
    if DRY_RUN:
        log("---- DRY RUN post ----\n" + text + f"\n[image] {item.get('image')}\n")
        return True
    api = f"https://api.telegram.org/bot{TG_TOKEN}"
    urls = [u for u in (item.get("images") or []) if u][:CONFIG.get("photos_per_post", 3)]
    video = fetch_video(item.get("video")) if CONFIG.get("post_videos", True) else None
    log(f"  photos available: {len(urls)}, video: {'yes' if video else 'no'}")
    if video and len(urls) >= 3:
        urls = urls[:2]  # main photo, video, one more photo
    if len(urls) >= 2 or (video and urls):
        photos = [ph for ph in (square_photo(u) for u in urls) if ph]
        if len(photos) >= 2 or (video and photos):
            files = {f"p{i}": (f"p{i}.jpg", ph, "image/jpeg") for i, ph in enumerate(photos)}
            media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(photos))]
            if video:
                files["v0"] = ("v0.mp4", video, "video/mp4")
                media.insert(1, {"type": "video", "media": "attach://v0", "supports_streaming": True})
            media[0].update(caption=text, parse_mode="HTML")
            r = requests.post(f"{api}/sendMediaGroup", data={
                "chat_id": TG_CHAT, "media": json.dumps(media),
                "disable_notification": "false" if is_big_deal(item) else "true"},
                files=files, timeout=180)
            if r.ok:
                msgs = r.json()["result"]
                item["album_ids"] = [m["message_id"] for m in msgs]
                log(f"  sent as an album of {len(msgs)} items" + (" (with video)" if video else ""))
                return msgs[0]["message_id"]
            log(f"  album post failed ({r.text[:150]}), sending a single photo")
    if item.get("image"):
        photo = square_photo(item["image"])
        data = {"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML",
                "disable_notification": "false" if is_big_deal(item) else "true"}
        if photo:
            r = requests.post(f"{api}/sendPhoto", data=data, files={"photo": ("deal.jpg", photo, "image/jpeg")}, timeout=60)
        else:
            r = requests.post(f"{api}/sendPhoto", data={**data, "photo": item["image"]}, timeout=30)
        if r.ok:
            return r.json()["result"]["message_id"]
        log(f"  photo post failed ({r.text[:150]}), sending as text")
    r = requests.post(f"{api}/sendMessage", data={
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
        "disable_notification": "false" if is_big_deal(item) else "true"}, timeout=30)
    if not r.ok:
        log(f"  ! telegram error: {r.text[:300]}")
        return None
    return r.json()["result"]["message_id"]


# ---------------------------------------------------------------- main

def discount_pct(info):
    m = re.search(r"\d+", info.get("discount") or "")
    if m:
        return int(m.group())
    was, price = money(info.get("was")), money(info.get("price"))
    return round((1 - price / was) * 100) if was > price > 0 else 0


def over_cap(info):
    """Israel: personal imports above $75 pay VAT/customs, so skip anything priced above the cap."""
    return money(info.get("price")) > CONFIG.get("max_price_usd", 75)


def arg(name, default=None):
    """--name value from the command line, else NAME env var, else default."""
    if f"--{name}" in sys.argv:
        return sys.argv[sys.argv.index(f"--{name}") + 1]
    return os.getenv(name.upper().replace("-", "_")) or default


POOL_F = ROOT / "data" / "pool.json"


def pool_add(it, info, category):
    pool = load_json(POOL_F, {})
    pool[it["asin"]] = {"it": it, "info": info, "category": category, "at": now().isoformat()}
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))


def pool_fresh(state):
    pool = load_json(POOL_F, {})
    fams = state.get("families", {})
    out = []
    for a, v in pool.items():
        if not is_recent(v["at"], CONFIG.get("reserve_hours", 12) / 24) or state["posted"].get(a) or over_cap(v["info"]):
            continue
        fs = [f for f in (v["info"].get("parent_asin"), title_family(v["info"].get("title"))) if f]
        if any(is_recent(fams.get(f, ""), CONFIG["repost_after_days"]) for f in fs):
            continue
        out.append(v)
    return out


def pool_take(state, keyfn=None):
    """Best still-fresh reserve deal that hasn't been posted (same product family rule applies)."""
    pool = {a: v for a, v in load_json(POOL_F, {}).items()
            if is_recent(v["at"], CONFIG.get("reserve_hours", 12) / 24) and not state["posted"].get(a) and not over_cap(v["info"])}
    def ok(v):
        fams = [f for f in (v["info"].get("parent_asin"), title_family(v["info"].get("title"))) if f]
        return not any(is_recent(state.get("families", {}).get(f, ""), CONFIG["repost_after_days"]) for f in fams)
    choices = [v for v in pool.values() if ok(v) and not clashes(state, v["info"].get("title"), (v.get("category") or {}).get("slug"))]
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
    if not choices:
        return None
    best = max(choices, key=keyfn or (lambda v: (discount_pct(v["info"]), -(v["it"].get("rank") or 99))))
    pool.pop(best["it"]["asin"], None)
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
    return best


# ---------------------------------------------------------------- aliexpress

# Family-friendly channel: never post adult, weapon, smoking/vape, drug or gambling items from AliExpress
ALI_BLOCK = re.compile(
    r"\b(sex\w*|adult|erotic\w*|lingerie|thong|g-?string|bdsm|fetish|bondage|nipple|vibrat\w*|dildo\w*|"
    r"masturbat\w*|condom\w*|lubric\w*|porn\w*|nude|naked|strip(?:per|tease)|seductive|18\+|"
    r"knife|knives|blade|dagger|machete|sword|gun|pistol|rifle|airsoft|ammo|bullet|holster|taser|stun|"
    r"pepper spray|brass knuckles?|baton|crossbow|slingshot|weapon\w*|tactical vest|"
    r"vape\w*|e-?cig\w*|cigarette\w*|hookah|shisha|bong|grinder|rolling paper|tobacco|smok(?:e|ing) pipe|"
    r"cannabis|weed|marijuana|420|kratom|gambling|casino|poker chips?|alcohol|beer|wine|vodka|whiskey|"
    r"tattoo|piercing|hair removal|breast|butt lift|slimming|diet pills?|fat burn\w*|weight loss|"
    r"halloween mask|skull|devil|satan\w*|zombie|blood|horror|creepy|scary|fnaf|five nights?|freddy|huggy|poppy playtime)\b", re.I)
# licensed characters / brands: on AliExpress these are almost always unofficial knockoffs,
# so they are only allowed from a brand's OFFICIAL store (see ali_queries entries with "official")
ALI_LICENSED = re.compile(
    r"\b(pok[eé]mon|pikachu|disney|marvel|spider-?man|avengers|"
    r"frozen|elsa|stitch|minnie|mickey|barbie|hello kitty|sanrio|kuromi|cinnamoroll|my melody|sonic|mario|"
    r"nintendo|minecraft|roblox|paw patrol|peppa|bluey|cocomelon|harry potter|star wars|naruto|anime|"
    r"labubu|squishmallows?|lego|nike|adidas|airpods?|stanley|owala|jellycat|uno|hot wheels|transformers|peppa pig|sesame street|tom and jerry|snoopy|garfield|batman|superman|dc comics)\b", re.I)
# what an official store may legitimately carry (licensed words must also come with the brand name in the title)
OFFICIAL_FAMILY = {
    "disney": {"disney", "marvel", "spider-man", "spiderman", "avengers", "frozen", "elsa", "stitch", "minnie", "mickey", "star wars"},
    "pop mart": {"labubu"}, "popmart": {"labubu"},
    "sanrio": {"sanrio", "hello kitty", "kuromi", "cinnamoroll", "my melody"},
}
ALI_BLOCK_CATS = re.compile(r"sex|adult|intimate|lingerie|underwear|tobacco|smok|cigarette|weapon|knife|knives|"
                            r"hunting|tattoo|novelty & special use", re.I)


JUNK = re.compile(r"\b(drop ?shipping|dropship|wholesale|free shipping|hot sale|hot selling|new arrivals?|best sellers?|"
                  r"factory (price|direct)|20\d\d new|new 20\d\d|in stock|fast delivery)\b[,;/ ]*", re.I)


def strip_junk(title):
    """Remove seller spam words AliExpress titles are full of (Dropshipping, Wholesale, 2025 New...)."""
    t = JUNK.sub("", title or "")
    return re.sub(r"\s{2,}", " ", t).strip(" ,-/|")


def blocked(title):
    return bool(CONFIG.get("block_keywords") and re.search(CONFIG["block_keywords"], title or "", re.I))


def ali_coupon(p):
    """Store coupon on the product, if it's worth showing (>= $2 off) and still valid."""
    info = p.get("promo_code_info") or {}
    code = info.get("promo_code")
    if not code:
        return None
    m = re.search(r"get USD ([\d.]+) off", info.get("code_value") or "")
    off, mini = (float(m.group(1)) if m else 0), money(info.get("code_mini_spend"))
    end = (info.get("code_availabletime_end") or "")[:10]
    if off < CONFIG.get("coupon_min_off_usd", 2) or (end and end < now().date().isoformat()):
        return None
    return {"code": code, "off": off, "min": mini, "until": end}


def official_store(p, brand):
    """True if the product is sold by the brand's own official/flagship store on AliExpress."""
    shop = (p.get("shop_name") or "").lower()
    norm = re.sub(r"[^a-z0-9]", "", shop)
    return re.sub(r"[^a-z0-9]", "", brand.lower()) in norm and bool(re.search(r"official|flagship", shop))


def ali_ok(p, official=False):
    """Age-appropriate, popular, well-rated, under the price cap."""
    text = " ".join(str(p.get(k) or "") for k in ("product_title", "first_level_category_name", "second_level_category_name"))
    if ALI_BLOCK.search(text):
        return False
    hits = {m.lower() for m in ALI_LICENSED.findall(text)}
    if hits:
        if not official:
            return False
        brand = str(official).lower()
        fam = OFFICIAL_FAMILY.get(brand, set())
        title = (p.get("product_title") or "").lower()
        if brand not in title or any(h not in fam and h != brand for h in hits):
            return False
    cats = f"{p.get('first_level_category_name') or ''} {p.get('second_level_category_name') or ''}"
    if ALI_BLOCK_CATS.search(cats):
        return False
    if blocked(p.get("product_title")):
        return False
    if CONFIG.get("ali_niche_block") and re.search(CONFIG["ali_niche_block"], (p.get("product_title") or "").lower()):
        return False  # parts / add-ons for one specific device or car: too niche for the channel
    if any(k in (p.get("product_title") or "").lower() for k, v in CONFIG.get("demote_keywords", {}).items() if v >= 35):
        return False  # bedding / linen: Matt wants much less of it
    price = money(p.get("target_sale_price"))
    if not price or price > CONFIG.get("max_price_usd", 75):
        return False
    title = (p.get("product_title") or "").lower()
    if price < CONFIG.get("ali_min_price_usd", 0) and not any(k in title for k in CONFIG.get("ali_min_price_exempt", [])):
        return False
    squishy = any(k in (p.get("product_title") or "").lower() for k in CONFIG.get("ali_min_price_exempt", []))
    if int(p.get("lastest_volume") or 0) < (CONFIG.get("ali_min_sold_exempt", 200) if squishy else CONFIG.get("ali_min_sold", 500)):
        return False
    # fake-capacity storage scam: "2TB" SD cards / flash drives / SSDs for a few dollars
    tl = (p.get("product_title") or "").lower()
    if re.search(r"\b(sd|tf|micro ?sd|memory|flash|usb|pen ?drive|ssd|hard drive|card)\b", tl) and \
            re.search(r"\b([1-9]\d*) ?tb\b", tl) and price < 60:
        return False
    return money(p.get("evaluate_rate")) >= CONFIG.get("ali_min_rating_pct", 90)


def ali_info(p):
    sold = int(p.get("lastest_volume") or 0)
    was = p.get("target_original_price")
    info = {"title": clean(p.get("product_title")), "price": f"${money(p.get('target_sale_price')):.2f}",
            "was": f"${money(was):.2f}" if money(was) > money(p.get("target_sale_price")) else "",
            "discount": p.get("discount") if money(p.get("discount")) >= 5 else "",
            "rating": p.get("evaluate_rate") or "", "image": p.get("product_main_image_url"),
            "images": ([p.get("product_main_image_url")] + [u for u in ((p.get("product_small_image_urls") or {}).get("string") or [])
                                                           if u != p.get("product_main_image_url")])[:CONFIG.get("photos_per_post", 3)],
            "link": p.get("promotion_link") or "", "store": "aliexpress",
            "sold": f"{sold // 1000},000" if sold >= 1000 else str(sold)}
    info["coupon"] = ali_coupon(p)
    info["video"] = p.get("product_video_url") or ""
    return info


def ali_pick(state):
    """Find one AliExpress deal: a random family-friendly search, best-selling first, not posted recently."""
    sys.path.insert(0, str(ROOT / "tools"))
    import aliexpress
    queries = CONFIG.get("ali_queries", [])
    tried = 0
    avoid = recent_themes(state)
    fresh = [x for x in queries if theme_of(None, x.get("en"), x.get("q")) not in avoid] or queries
    picks = random.choices(fresh, weights=[x.get("weight", 1) for x in fresh], k=min(4, len(fresh)))
    if arg("keyword"):  # targeted: e.g. --keyword "baseus security b1"
        kw = arg("keyword").lower()
        picks = [{"q": arg("keyword"), "require": arg("require", kw).lower(), "en": arg("category-en", "Top picks"), "he": arg("category-he", "בחירות שלנו")}]
    if not arg("keyword") and random.random() < CONFIG.get("ali_sale_share", 0.4):
        try:
            lists = aliexpress.sale_lists()
            if lists:
                name = random.choice(lists)
                picks = [{"q": name, "sale": True, "en": "AliExpress sale", "he": "מבצע אליאקספרס"}] + picks
        except Exception as e:
            log(f"  (AliExpress sale lists failed: {e})")
    for q in picks:
        tried += 1
        try:
            prods = aliexpress.sale_products(q["q"], page=random.randint(1, 5)) if q.get("sale") else \
                aliexpress.search(keywords=q["q"], page=1 if arg("keyword") else random.randint(1, 3), page_size=50)
        except Exception as e:
            log(f"  (AliExpress search '{q['q']}' failed: {e})")
            continue
        if q.get("official"):  # licensed toy brands: only from the brand's official store
            prods = [p for p in prods if official_store(p, q["official"])]
        good = [p for p in prods if ali_ok(p, official=q.get("official") or False)]
        if not good and arg("keyword") and arg("approved"):  # Matt approved this specific item: skip cap/sales filters
            good = [p for p in prods if not ALI_BLOCK.search(p.get("product_title") or "") and p.get("promotion_link")]
        if q.get("require"):  # brand searches: only that brand's own products, not "compatible with" items
            good = [p for p in good if q["require"] in (p.get("product_title") or "").lower()[:40]
                    and not re.search(r"\b(for|compatible)\b[^,]{0,25}" + re.escape(q["require"]), (p.get("product_title") or "").lower())]
        # most of the time prefer higher-value items ($25+) when the search has any
        dear = [p for p in good if money(p.get("target_sale_price")) >= CONFIG.get("preferred_min_price_usd", 25)]
        if dear and random.random() < CONFIG.get("higher_value_share", 0.6):
            good = dear
        log(f"[AliExpress · {q['q']}] {len(prods)} results, {len(good)} pass the filters")
        random.shuffle(good)
        good.sort(key=lambda p: -int(p.get("lastest_volume") or 0) * (1 + min(money(p.get("discount")), 60) / 100)
                  * (1.5 if p.get("product_video_url") else 1))
        for p in good[:15]:
            pid = f"ali-{p['product_id']}"
            fam = title_family(p.get("product_title"))
            if state["posted"].get(pid) or (fam and is_recent(state.get("families", {}).get(fam, ""), CONFIG["repost_after_days"])):
                continue
            if not p.get("promotion_link"):
                continue
            if clashes(state, p.get("product_title")):
                continue
            if (theme_of(None, q.get("en"), p.get("product_title")) or "") in avoid:
                continue
            info = ali_info(p)
            it = {"asin": pid, "rank": 0, "source": "aliexpress", "store": "aliexpress"}
            return it, info, {"slug": f"aliexpress/{q['q']}", "en": q["en"], "he": q["he"]}
    log(f"  no new AliExpress deal found in {tried} searches")
    return None


# ---------------------------------------------------------------- shekels

FX_F = ROOT / "data" / "fx.json"
_fx = {}


def usd_ils():
    """Today's USD->ILS rate (ECB via frankfurter, cached daily in data/fx.json). None if unknown."""
    if "rate" in _fx:
        return _fx["rate"]
    cached = load_json(FX_F, {})
    today = datetime.now(timezone.utc).date().isoformat()
    rate = cached.get("rate") if cached.get("date") == today else None
    if not rate:
        for url in ("https://api.frankfurter.app/latest?from=USD&to=ILS", "https://open.er-api.com/v6/latest/USD"):
            try:
                j = requests.get(url, timeout=15).json()
                rate = float((j.get("rates") or {}).get("ILS") or 0) or None
                if rate:
                    FX_F.write_text(json.dumps({"date": today, "rate": rate}))
                    break
            except Exception as e:
                log(f"  (exchange rate from {url.split('/')[2]} failed: {e})")
        if not rate and is_recent(cached.get("date", "") + "T00:00:00+00:00" if cached.get("date") else "", 7):
            rate = cached.get("rate")
    _fx["rate"] = rate
    return rate


def shekels(text):
    """'$12.99' -> '~₪47'. Leaves the text as is if it isn't dollars or the rate is unknown."""
    if not text or "$" not in text:
        return text
    usd, rate = money(text), usd_ils()
    if not usd or not rate:
        return text
    return f"~₪{round(usd * rate):,}"


# ---------------------------------------------------------------- variety

def product_type(title):
    t = f" {(title or '').lower()} "
    for k in CONFIG.get("product_types", []):  # list order matters: specific before generic
        if re.search(r"[\s\W]" + re.escape(k), t):
            return k
    return None


def brand_of(title):
    t = (title or "").lower()
    for b in CONFIG.get("brands", []):
        if t.startswith(b.lower() + " ") or f" {b.lower()} " in f" {t[:40]} ":
            return b.lower()
    return None


THEME_SLUGS = {
    "tech": ["electronics", "pc", "wireless", "photo", "videogames", "amazon-devices"],
    "kids": ["toys-and-games", "baby-products", "arts-crafts", "fashion/1040664", "fashion/1040666"],
    "fashion": ["fashion", "luggage"],
    "home": ["home-garden", "appliances", "hi", "lawn-garden", "industrial", "office-products"],
    "kitchen": ["kitchen"],
    "beauty": ["beauty", "hpc"],
    "sport": ["sporting-goods"],
    "pets": ["pet-supplies"],
    "car": ["automotive"],
}
THEME_LABELS = {  # AliExpress search labels (config ali_queries "en")
    "tech": ["tech", "work from home", "smart home", "gaming", "phone & tablet", "top brands"],
    "kids": ["squish", "fidget", "building", "kids", "plush", "arts & crafts", "baby", "official brand store"],
    "fashion": ["fashion", "bags", "accessories", "watches", "jewelry", "travel", "luggage"],
    "home": ["home", "outdoor lighting", "tools", "hanukkah", "school & office", "gift ideas"],
    "kitchen": ["kitchen", "coffee"],
    "sport": ["fitness", "outdoor"],
    "pets": ["pets"],
    "car": ["car"],
}
THEME_WORDS = [  # fallback from the product title
    ("kids", r"\b(kids?|children|toddler|baby|toy|toys|squish\w*|plush|lego|doll|puzzle|stem)\b"),
    ("tech", r"\b(charger|cable|power bank|earbuds|headphones?|speaker|mouse|keyboard|monitor|camera|usb|bluetooth|wifi|smart|ssd|phone|tablet|laptop|gaming)\b"),
    ("fashion", r"\b(shirt|t-shirt|hoodie|jacket|dress|pants|jeans|leggings|sweater|shoes|sneakers|slippers|boots|socks|bag|backpack|watch|jewelry|necklace|bracelet|earrings|sunglasses|wallet)\b"),
    ("kitchen", r"\b(kitchen|knife|pan|pot|blender|frother|coffee|espresso|air fryer|mug|tumbler|bottle|lunch)\b"),
    ("beauty", r"\b(skin|serum|moistur\w*|cleanser|hair|shampoo|makeup|lip|nail|perfume)\b"),
    ("sport", r"\b(fitness|yoga|gym|dumbbell|resistance band|massage gun|bike|camping|hiking)\b"),
    ("pets", r"\b(dog|cat|pet|puppy|kitten)\b"),
    ("car", r"\b(car|dash cam|vehicle)\b"),
    ("home", r"\b(lamp|light|decor|storage|organizer|curtain|rug|pillow|blanket|towel|vacuum|clean\w*|candle|frame|plant)\b"),
]


def theme_of(slug=None, label=None, title=None):
    slug = slug or ""
    for th, slugs in THEME_SLUGS.items():  # most specific slug first
        if slug in slugs:
            return th
    for th, slugs in THEME_SLUGS.items():
        if slug.split("/")[0] in slugs and slug.split("/")[0] != "fashion":
            return th
    if slug.startswith("fashion"):
        return "fashion"
    lab = (label or "").lower()
    for th, words in THEME_LABELS.items():
        if any(w in lab for w in words):
            return th
    for th, rx in THEME_WORDS:
        if re.search(rx, title or "", re.I):
            return th
    return None


def recent_themes(state):
    return state.get("recent_themes", [])[-CONFIG.get("theme_gap_posts", 2):]


def group_of(slug):
    g = (slug or "").split("/")[0]
    return None if g in ("aliexpress", "pick", "") else g


def clashes(state, title, slug=None):
    """Variety across BOTH stores: no same product type in the last few posts, no same brand back to back."""
    if "recent_titles" not in state:  # first run with this rule: start from the posts log
        state["recent_titles"] = [x.get("title", "") for x in load_json(ROOT / "data" / "posts.json", [])][-12:]
    recent = state["recent_titles"]
    typ, brand = product_type(title), brand_of(title)
    if typ and typ in [product_type(x) for x in recent[-CONFIG.get("diversity_posts", 6):]]:
        return f"another {typ} was posted recently"
    if typ and CONFIG.get("type_cooldown_hours"):
        since = (now() - timedelta(hours=CONFIG["type_cooldown_hours"])).isoformat()
        if any(x.get("posted_at", "") >= since and product_type(x.get("title")) == typ
               for x in load_json(ROOT / "data" / "posts.json", [])[-120:]):
            return f"a {typ} was posted in the last {CONFIG['type_cooldown_hours']}h"
    if brand and brand in [brand_of(x) for x in recent[-CONFIG.get("brand_gap_posts", 4):]]:
        return f"{brand} was posted recently"
    for cap in CONFIG.get("weekly_caps", []):
        ex = cap.get("exclude")
        hit = lambda t: re.search(cap["pattern"], t or "", re.I) and not (ex and re.search(ex, t or "", re.I))
        if hit(title):
            since = (now() - timedelta(days=cap.get("days", 7))).isoformat()
            n = sum(1 for x in load_json(ROOT / "data" / "posts.json", [])
                    if x.get("posted_at", "") >= since and hit(x.get("title")))
            if n >= cap.get("max", 1):
                return f"weekly cap reached for {cap['name']}"
    th = theme_of(slug if slug and not slug.startswith(("aliexpress", "pick")) else None, None, title)
    if th and th in recent_themes(state):
        return f"another {th} item was just posted"
    g = group_of(slug)
    if g and g in state.get("recent_groups", [])[-CONFIG.get("group_gap_posts", 2):]:
        return f"another {g} item was one of the last Amazon posts"
    return None


# ---------------------------------------------------------------- Matt's picks (links sent to the bot)

def tg_owner(text):
    owner = str(CONFIG.get("owner_chat_id", ""))
    if owner and TG_TOKEN and not DRY_RUN:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": owner, "text": text, "disable_web_page_preview": "true"}, timeout=20)
        except Exception:
            pass


def resolve(url):
    try:
        return requests.get(url, timeout=20, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}).url
    except Exception:
        return url


def parse_pick(url):
    """Amazon or AliExpress product link (incl. short links) -> ('amazon', ASIN) / ('aliexpress', id) / None."""
    u = url
    if re.search(r"amzn\.to|a\.co/|amzn\.eu|link\.amazon|s\.click\.aliexpress|a\.aliexpress\.com|aliexpress\.com/e/", u):
        u = resolve(u)
    m = re.search(r"amazon\.[a-z.]+/(?:[^/]+/)?(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", u)
    if m:
        return "amazon", m.group(1)
    m = re.search(r"aliexpress\.[a-z.]+/item/(\d+)\.html", u) or re.search(r"[?&]productIds?=(\d+)", u)
    if m:
        return "aliexpress", m.group(1)
    return None


def inbox(state):
    """Read messages Matt sent to the bot; product links go into the queue."""
    if not TG_TOKEN or DRY_RUN:
        return
    owner = str(CONFIG.get("owner_chat_id", ""))
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                         params={"offset": state.get("tg_offset", 0), "timeout": 0,
                                 "allowed_updates": json.dumps(["message", "chat_member"])}, timeout=30).json()
    except Exception as e:
        log(f"  (inbox failed: {e})")
        return
    for u in r.get("result", []):
        state["tg_offset"] = u["update_id"] + 1
        if u.get("chat_member"):
            giveaway_join(state, u["chat_member"])
            continue
        m = u.get("message") or {}
        if (m.get("text") or "").strip().lower() in ("/status", "סטטוס", "status") and giveaway_open():
            giveaway_status(state, m)
            continue
        if (m.get("text") or "").startswith("/start") or (m.get("text") or "").strip() in ("הגרלה", "giveaway"):
            if str((m.get("chat") or {}).get("id")) != owner or "giveaway" in (m.get("text") or ""):
                giveaway_start(state, m)
                continue
        if str((m.get("chat") or {}).get("id")) != owner:
            win = state.get("giveaway_winner") or {}
            if win and str((m.get("from") or {}).get("id")) == str(win.get("id")):
                tg_owner(f"📩 Message from the giveaway winner: {(m.get('text') or '')[:300]}")
                tg("sendMessage", chat_id=m["chat"]["id"], text="תודה! קיבלנו, נשלח לך את הגיפט קארד בקרוב 🎁")
            elif giveaway_open() and (m.get("text") or "").strip():
                giveaway_start(state, m)
            continue
        text = (m.get("text") or m.get("caption") or "")
        if m.get("forward_origin") or m.get("forward_from") or m.get("forward_from_chat") or m.get("forward_date"):
            continue  # forwarded posts are just for reference, never queued
        explicit = re.search(r"(?i)\b(post|queue|add)\b|פרסם|תפרסם|לפרסם|תעלה|להעלות", text)
        urls = re.findall(r"https?://\S+", text)
        for ent in (m.get("entities") or []) + (m.get("caption_entities") or []):
            if ent.get("url"):
                urls.append(ent["url"])
        if not urls:
            continue
        if not explicit:
            tg_owner("👀 Got the link, but I didn't queue it. To post it to the channel, send it again with the word "
                     "\"פרסם\" (or \"post\").")
            continue
        for url in dict.fromkeys(urls):
            found = parse_pick(url)
            if not found:
                tg_owner(f"🤔 I couldn't find an Amazon or AliExpress product in this link:\n{url}")
                continue
            store, pid = found
            q = state.setdefault("pick_queue", [])
            key = pid if store == "amazon" else f"ali-{pid}"
            if is_recent(state["posted"].get(key, ""), CONFIG["repost_after_days"]) and not re.search(r"(?i)again|שוב", text):
                tg_owner("🔁 This was already posted in the last 7 days, so I skipped it. Add \"שוב\" to post it again.")
                continue
            if any(x["store"] == store and x["id"] == pid for x in q):
                tg_owner("👍 Already in the queue")
                continue
            q.append({"store": store, "id": pid, "url": url, "at": now().isoformat()})
            tg_owner(f"✅ Added to the queue ({'Amazon' if store == 'amazon' else 'AliExpress'}). "
                     f"Position {len(q)}, it goes out on one of the next posting slots.")
            log(f"Queued Matt's pick: {store} {pid}")


# ---------------------------------------------------------------- $50 giveaway

def giveaway_cfg():
    g = CONFIG.get("giveaway") or {}
    return g if g.get("start") else None


def giveaway_open():
    g = giveaway_cfg()
    today = israel_now().date().isoformat()
    return bool(g) and g["start"] <= today <= g["end"]


def tg(method, **data):
    try:
        return requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", data=data, timeout=20).json()
    except Exception as e:
        log(f"  (telegram {method} failed: {e})")
        return {}


def is_member(user_id):
    r = tg("getChatMember", chat_id=TG_CHAT, user_id=user_id)
    return (r.get("result") or {}).get("status") in ("member", "administrator", "creator", "restricted")


def add_entrant(state, user, via):
    ent = state.setdefault("giveaway_entries", {})
    uid = str(user["id"])
    if uid in ent or user.get("is_bot"):
        return False
    ent[uid] = {"name": (user.get("first_name") or "")[:40], "username": user.get("username") or "",
                "via": via, "at": now().isoformat()}
    log(f"Giveaway entry #{len(ent)} ({via})")
    return True


REF_MAX = 10


def ref_link(state, uid):
    """Personal invite link for an entrant (created once by the bot, which is a channel admin)."""
    refs = state.setdefault("giveaway_refs", {})
    r = refs.setdefault(str(uid), {"link": "", "joined": []})
    if not r["link"]:
        res = tg("createChatInviteLink", chat_id=TG_CHAT, name=f"ref-{uid}"[:32])
        r["link"] = (res.get("result") or {}).get("invite_link", "")
        if r["link"]:
            state.setdefault("giveaway_link_owner", {})[r["link"]] = str(uid)
    return r["link"]


def share_buttons(link):
    from urllib.parse import quote
    msg = ("🎁 מגרילים גיפט קארד של $50 לאמזון! מצטרפים לערוץ הדילים IL Deals (אמזון ואליאקספרס עם משלוח לארץ) "
           "ונכנסים להגרלה אוטומטית 👇\n" + link)
    return json.dumps({"inline_keyboard": [
        [{"text": "📲 שיתוף בוואטסאפ", "url": "https://wa.me/?text=" + quote(msg)}],
        [{"text": "✈️ שיתוף בטלגרם", "url": "https://t.me/share/url?url=" + quote(link) + "&text=" + quote(msg.rsplit("\n", 1)[0])}],
    ]})


def entries_of(state, uid, check=False):
    joined = (state.get("giveaway_refs", {}).get(str(uid)) or {}).get("joined", [])
    if check:
        joined = [j for j in joined if is_member(j)]
    return 1 + min(REF_MAX, len(joined))


def giveaway_status(state, m):
    user, chat = m.get("from") or {}, (m.get("chat") or {}).get("id")
    uid = str(user.get("id"))
    if uid not in state.get("giveaway_entries", {}):
        return giveaway_start(state, m)
    link = ref_link(state, uid)
    n = entries_of(state, uid)
    tg("sendMessage", chat_id=chat, disable_web_page_preview="true", reply_markup=share_buttons(link) if link else None, text=(
        f"🎟️ יש לך {n} כרטיסים בהגרלה (מתוך 11 אפשריים)\n"
        f"👥 חברים שהצטרפו דרכך: {n - 1}\n\n"
        f"כל חבר שמצטרף דרך הקישור האישי שלך = עוד כרטיס 🎁\n👉 {link}"))


def giveaway_join(state, cm):
    """Someone joined the channel: enter them automatically while the giveaway is open."""
    if not giveaway_open():
        return
    new, old = cm.get("new_chat_member") or {}, cm.get("old_chat_member") or {}
    if new.get("status") == "member" and old.get("status") in ("left", "kicked", None):
        user = new.get("user") or {}
        uid = str(user.get("id"))
        seen = state.setdefault("giveaway_seen", [])
        first_time = uid not in seen and uid not in state.get("giveaway_entries", {})
        if uid not in seen:
            seen.append(uid)
        add_entrant(state, user, "join")
        link = ((cm.get("invite_link") or {}).get("invite_link") or "")
        owner = state.get("giveaway_link_owner", {}).get(link)
        if owner and owner != uid and first_time and not user.get("is_bot"):
            r = state["giveaway_refs"].setdefault(owner, {"link": link, "joined": []})
            if uid not in r["joined"]:
                r["joined"].append(uid)
                n = entries_of(state, owner)
                log(f"Giveaway referral: {owner} brought {uid} ({len(r['joined'])} so far)")
                name = (user.get("first_name") or "חבר/ה")[:30]
                more = "הגעת למקסימום, כל הכבוד! 🏆" if len(r["joined"]) >= REF_MAX else "ממשיכים? כל חבר נוסף = עוד כרטיס 👇"
                tg("sendMessage", chat_id=owner, text=f"🎉 {name} הצטרף/ה דרך הקישור שלך! יש לך עכשיו {n} כרטיסים בהגרלה.\n{more}")


def giveaway_start(state, m):
    """User pressed the giveaway button (opens the bot with /start giveaway)."""
    user, chat = m.get("from") or {}, (m.get("chat") or {}).get("id")
    g = giveaway_cfg()
    if not g:
        return
    if not giveaway_open():
        tg("sendMessage", chat_id=chat, text="ההגרלה לא פעילה כרגע. עקבו אחרי הערוץ לדילים והגרלות הבאות 🙏\nt.me/ilamazondeals")
        return
    if not is_member(user.get("id")):
        tg("sendMessage", chat_id=chat, text="כמעט! 🙌 כדי להשתתף צריך להצטרף לערוץ קודם:\n👉 t.me/ilamazondeals\n\n"
                                             "אחרי שהצטרפתם, שלחו כאן \"הגרלה\" ונבדוק שוב.")
        return
    new = add_entrant(state, user, "bot")
    draw = g["draw"]
    link = ref_link(state, user.get("id"))
    n = entries_of(state, user.get("id"))
    tg("sendMessage", chat_id=chat, disable_web_page_preview="true",
       reply_markup=share_buttons(link) if link else None, text=(
        f"✅ {'אתם בהגרלה!' if new else 'אתם כבר רשומים להגרלה 👍'} יש לכם {n} {'כרטיס' if n == 1 else 'כרטיסים'}.\n\n"
        f"🚀 רוצים להגדיל את הסיכוי? הזמינו חברים!\n"
        f"כל חבר שמצטרף לערוץ דרך הקישור האישי שלכם = עוד כרטיס, עד 10 חברים (11 כרטיסים).\n\n"
        f"👇 הקישור האישי שלכם (או פשוט לחצו על הכפתורים לשיתוף):\n{link}\n\n"
        f"🎁 הפרס: {g.get('prize_he', 'גיפט קארד של $50 לאמזון')}\n"
        f"🗓️ ההגרלה ב-{draw[8:10]}/{draw[5:7]} בצהריים. רק חברים שעדיין בערוץ בזמן ההגרלה נספרים.\n"
        f"📊 לבדוק כמה כרטיסים יש לכם: שלחו כאן \"סטטוס\""))


def giveaway_draw(state):
    """On draw day (from 12:00), pick a random entrant who is still in the channel and announce."""
    g = giveaway_cfg()
    if not g or state.get("giveaway_winner") or DRY_RUN:
        return
    now_il = israel_now()
    if now_il.date().isoformat() < g["draw"] or now_il.hour < g.get("draw_hour", 12):
        return
    ent = state.get("giveaway_entries", {})
    # one ticket each + one per friend they brought who is still in the channel (max 10 extra)
    weights = {uid: entries_of(state, uid, check=True) for uid in ent}
    ids = []
    pool = dict(weights)
    while pool:  # weighted shuffle: draw without replacement
        uid = random.choices(list(pool), weights=list(pool.values()))[0]
        ids.append(uid)
        pool.pop(uid)
    tg_owner(f"🎟️ Draw tickets: {sum(weights.values())} across {len(weights)} entrants")
    for uid in ids:
        if is_member(uid):
            w = ent[uid]
            state["giveaway_winner"] = {"id": uid, **w, "at": now().isoformat()}
            shown = f"@{w['username']}" if w.get("username") else w.get("name") or "זוכה"
            tg("sendMessage", chat_id=TG_CHAT, parse_mode="HTML", text=(
                f"🎉 <b>יש לנו זוכה!</b>\n\nמזל טוב ל-{esc(shown)} שזכה/תה בגיפט קארד של $50 לאמזון! 🎁\n"
                f"השתתפו {len(ent)} חברי ערוץ. תודה לכולם, והגרלות נוספות בדרך 😉\n\n"
                f"לזוכה: שלחו לבוט הודעה תוך 72 שעות כדי לקבל את הפרס."))
            r = tg("sendMessage", chat_id=uid, text="🎉 זכית בהגרלה! שלח/י כאן את כתובת האימייל שלך ונשלח את הגיפט קארד של $50 לאמזון.")
            tg_owner(f"🎉 Giveaway winner: {shown} (id {uid}, entered via {w['via']}). "
                     f"{'Messaged them.' if r.get('ok') else 'Could not message them (never opened the bot); they were asked to message the bot.'} "
                     f"{len(ent)} entries in total.")
            return
    tg_owner("⚠️ Giveaway draw: no eligible entrants found.")


def focus_ali(fc, st):
    """Focus fallback on AliExpress (Matt, Nov 22): well-reviewed "brand-style" items, labelled as such."""
    a = fc.get("aliexpress") or {}
    if not a.get("queries"):
        return None
    sys.path.insert(0, str(ROOT / "tools"))
    import aliexpress
    cands, seen = [], set()
    for q in a["queries"]:
        try:
            prods = aliexpress.search(keywords=q, page_size=50)
        except Exception as e:
            log(f"  focus ali search failed: {e}")
            continue
        for p in prods:
            pid = str(p.get("product_id"))
            t = (p.get("product_title") or "").lower()
            if pid in seen or not p.get("promotion_link"):
                continue
            seen.add(pid)
            if not any(w in t for w in fc.get("require_any", [])) or ALI_BLOCK.search(t) \
                    or (a.get("avoid") and re.search(a["avoid"], t, re.I)):
                continue
            if money(p.get("evaluate_rate")) < a.get("min_rating", 95) or int(p.get("lastest_volume") or 0) < a.get("min_sold", 5000):
                continue
            key = f"ali-{pid}"
            if st.get("posted", {}).get(key) and is_recent(st["posted"][key], fc.get("repost_days", 14)):
                continue
            cands.append(p)
    if not cands:
        log("  focus ali: nothing suitable")
        return None
    p = random.choice(sorted(cands, key=lambda x: -int(x.get("lastest_volume") or 0))[:5])
    info = ali_info(p)
    info["style_of"] = fc.get("name", "")
    log(f"  focus ali: {p.get('product_id')} {info['title'][:60]}")
    return ({"asin": f"ali-{p['product_id']}", "rank": 0, "source": "pick", "store": "aliexpress"}, info,
            {"slug": "pick", "en": "Our pick", "he": "הבחירה שלנו"})


def pick_details(pick, amz_factory):
    """Look up a queued pick. Returns (it, info, category) or a string with the reason it can't be posted."""
    cat = {"slug": "pick", "en": "Our pick", "he": "הבחירה שלנו"}
    if pick["store"] == "aliexpress_search":
        sys.path.insert(0, str(ROOT / "tools"))
        import aliexpress
        req = [w.lower() for w in pick.get("require", [])]
        found = None
        for q in [pick["id"]] + pick.get("alt", []):
            for p in aliexpress.search(keywords=q, page_size=50):
                t = (p.get("product_title") or "").lower()
                if all(w in t for w in req) and p.get("promotion_link") and money(p.get("evaluate_rate")) >= 85 \
                        and not ALI_BLOCK.search(t) and not (pick.get("avoid") and re.search(pick["avoid"], t)):
                    found = p
                    break
            if found:
                break
        if not found:
            return f"couldn't find \"{pick['id']}\" on AliExpress"
        pick = {**pick, "store": "aliexpress", "id": str(found["product_id"])}
    if pick["store"] == "amazon_focus":  # a brand Matt wants a steady selection of (e.g. NeeDoh)
        amz = amz_factory()
        if not amz:
            return None
        fc = CONFIG.get("focus", {})
        st = load_json(STATE_FILE, {}) if not isinstance(pick.get("_state"), dict) else pick["_state"]
        recent_days = fc.get("repost_days", 14)
        seen = []
        for q in fc.get("queries", []):
            for asin, title in amz.search_all(q, fc.get("require_any", [])):
                if asin in seen or (fc.get("avoid") and re.search(fc["avoid"], title, re.I)):
                    continue
                seen.append(asin)
        fresh = [a for a in seen if not (st.get("posted", {}).get(a) and is_recent(st["posted"][a], recent_days))]
        if not fresh:
            return focus_ali(fc, st) or "no new %s items right now" % fc.get("name", "focus")
        tried = []
        log(f"  focus {fc.get('name')}: {len(seen)} search results, {len(fresh)} not posted recently")
        for asin in fresh[:8]:  # first one that actually has a price and ships free to Israel
            info = amz.product(asin)
            if not info.get("price") or info.get("shipping") in ("paid", "no"):
                tried.append(asin)
                continue
            if not info.get("discount") and discount_pct(info):
                info["discount"] = f"{discount_pct(info)}%"
            return {"asin": asin, "rank": 0, "source": "pick"}, info, cat
        ali = focus_ali(fc, st)
        if ali:
            return ali
        return f"none of {len(tried)} {fc.get('name', 'focus')} items had a price with free shipping to Israel"
    if pick["store"] == "amazon_search":
        amz = amz_factory()
        if not amz:
            return None
        asin = None
        for q in [pick["id"]] + pick.get("alt", []):
            asin = amz.search(q, pick.get("require", []))
            if asin:
                break
        if not asin:
            return f"couldn't find \"{pick['id']}\" on Amazon"
        pick = {**pick, "store": "amazon", "id": asin}
    if pick["store"] == "aliexpress":
        sys.path.insert(0, str(ROOT / "tools"))
        import aliexpress
        res = aliexpress.call("aliexpress.affiliate.productdetail.get", product_ids=pick["id"],
                              target_currency="USD", target_language="EN", country="IL",
                              tracking_id=aliexpress.TRACKING_ID)
        prods = aliexpress._products(res)
        if not prods:
            return "AliExpress didn't return this product (it may not be in the affiliate program)"
        p = prods[0]
        info = ali_info(p)
        if not info["link"]:
            info["link"] = aliexpress.link(f"https://www.aliexpress.com/item/{pick['id']}.html") or ""
        if not info["link"]:
            return "no affiliate link available for this product"
        return {"asin": f"ali-{pick['id']}", "rank": 0, "source": "pick", "store": "aliexpress"}, info, cat
    amz = amz_factory()
    if not amz:
        return None  # Amazon unavailable right now: try again later
    info = amz.product(pick["id"])
    if not info.get("price"):
        return "no price found on Amazon"
    if info.get("shipping") in ("paid", "no") and not pick.get("ship_ok"):  # ship_ok: Matt checked shipping himself
        return "Amazon doesn't ship it free to Israel"
    if not info.get("discount") and discount_pct(info):
        info["discount"] = f"{discount_pct(info)}%"
    return {"asin": pick["id"], "rank": 0, "source": "pick"}, info, cat


# ---------------------------------------------------------------- coupon posts

def bundle_post(state):
    """Every few days: 3 cheap, top-rated Amazon add-ons in one post (to fill a $49 free-shipping cart)."""
    today = israel_now().date()
    last = state.get("last_bundle_day")
    every = CONFIG.get("bundle_every_days", 3)
    if israel_now().hour < CONFIG.get("bundle_hour", 16) or (last and (today - date.fromisoformat(last)).days < every):
        return False
    lo, hi = CONFIG.get("bundle_price_usd", [6, 22])
    cands = []
    for v in pool_fresh(state):
        info = v["info"]
        usd = money(info.get("price"))
        if not (lo <= usd <= hi) or float(info.get("rating") or 0) < 4.3 or not info.get("image"):
            continue
        tl = (info.get("title") or "").lower()
        if blocked(tl) or (CONFIG.get("ali_niche_block") and re.search(CONFIG["ali_niche_block"], tl)) \
                or re.search(r"\b(bands?|straps?|case|cover|screen protector|refills?|compatible|for (apple|iphone|samsung|galaxy|ipad|airpods))\b", tl):
            continue
        cands.append(v)
    cands.sort(key=lambda v: int(re.sub(r"\D", "", v["info"].get("reviews") or "0") or 0), reverse=True)
    picks, themes = [], set()
    for v in cands:
        th = theme_of(v["category"].get("slug"), None, v["info"].get("title"))
        if th in themes:
            continue
        picks.append(v); themes.add(th)
        if len(picks) == 3:
            break
    if len(picks) < 3:
        log(f"Bundle post: only {len(picks)} suitable add-ons in the pool, skipping")
        return False
    total = sum(money(v["info"]["price"]) for v in picks)
    he = ["🛒 <b>מוצרי השלמה למשלוח חינם</b>", "3 רבי מכר זולים שמשתלם להוסיף לעגלה כדי לעבור את ה-$49 ולקבל משלוח חינם לארץ", ""]
    en = ["🛒 <b>Cart fillers for free shipping</b>", "3 cheap best sellers worth adding to reach $49 and get free shipping to Israel", ""]
    for i, v in enumerate(picks, 1):
        info, asin = v["info"], v["it"]["asin"]
        url = esc(product_link(asin))
        t_he = esc(to_hebrew(short(info["title"], 60)))
        t_en = esc(short(info["title"], 60))
        pr = f"{shekels(info['price'])} ({esc(info['price'])})"
        he.append(f'{i}. {t_he}: {pr} ⭐ {info.get("rating")}\n👉 <a href="{url}">לקנייה</a>')
        en.append(f'{i}. {t_en}: {pr}\n👉 <a href="{url}">Buy</a>')
    he.append(f"\nביחד: {shekels(f'${total:.2f}')} (${total:.2f})")
    text = "\n".join(he) + "\n\n〰️〰️〰️〰️〰️\n\n" + "\n".join(en)
    if len(text) > 1000:
        text = "\n".join(he)
    if DRY_RUN:
        log("---- DRY RUN bundle post ----\n" + text)
        return True
    media = [{"type": "photo", "media": v["info"]["image"]} for v in picks]
    media[0].update({"caption": text, "parse_mode": "HTML"})
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup",
                      data={"chat_id": TG_CHAT, "media": json.dumps(media), "disable_notification": "true"}, timeout=60)
    log(f"Bundle post: {r.status_code} {r.text[:120]}")
    if r.ok and not OWNER_TEST:
        state["last_bundle_day"] = today.isoformat()
        state["last_post_at"] = now().isoformat()
        for v in picks:
            state["posted"][v["it"]["asin"]] = now().isoformat()
            for f in (v["info"].get("parent_asin"), title_family(v["info"].get("title"))):
                if f:
                    state.setdefault("families", {})[f] = now().isoformat()
    return r.ok


def coupon_post(state):
    """At most one coupon post a day, only while codes from config 'coupons' are valid. Returns True if posted."""
    today = israel_now().date().isoformat()
    active = [c for c in CONFIG.get("coupons", []) if c.get("from", "") <= today <= c.get("until", "")]
    if not active or state.get("last_coupon_day") == today or israel_now().hour < CONFIG.get("coupon_hour", 11):
        return False
    by_store = {}
    for c in active:
        by_store.setdefault(c.get("store", "aliexpress"), []).append(c)
    he, en = ["🎟️ <b>קופונים שווים להיום</b>", ""], ["🎟️ <b>Today's coupon codes</b>", ""]
    names = {"aliexpress": ("אליאקספרס", "AliExpress"), "amazon": ("אמזון", "Amazon")}
    for store, cs in by_store.items():
        nh, ne = names.get(store, (store, store))
        he.append(f"<b>{nh}:</b>")
        en.append(f"<b>{ne}:</b>")
        for c in cs:
            he.append(f"• ${c['off']:g} הנחה בקנייה מעל ${c['min']:g}: <code>{esc(c['code'])}</code>")
            en.append(f"• ${c['off']:g} off ${c['min']:g}+: <code>{esc(c['code'])}</code>")
        he.append("")
        en.append("")
    until = min(c["until"] for c in active)
    he += [f"⏰ בתוקף עד {until[8:10]}/{until[5:7]} (או עד שנגמר)", "📋 לחצו על הקוד כדי להעתיק, והדביקו בתשלום"]
    en += [f"⏰ Valid until {until[8:10]}/{until[5:7]} (while codes last)", "📋 Tap a code to copy it, paste at checkout"]
    if any(c.get("link") for c in active):
        url = next(c["link"] for c in active if c.get("link"))
        he.append(f'👉 <a href="{esc(url)}">לכל המבצעים</a>')
        en.append(f'👉 <a href="{esc(url)}">See the sale</a>')
    text = "\n".join(he) + "\n\n〰️〰️〰️〰️〰️\n\n" + "\n".join(en)
    if DRY_RUN:
        log("---- DRY RUN coupon post ----\n" + text)
        return True
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true",
        "disable_notification": "true"}, timeout=30)
    log(f"Coupon post: {r.status_code} {r.text[:120]}")
    if r.ok and not OWNER_TEST:
        state["last_coupon_day"] = today
        state["last_post_at"] = now().isoformat()
    return r.ok


def israel_now():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Jerusalem"))


def post_due(state):
    """Spread ~posts_per_day posts evenly across the posting window. The trigger fires every 15 minutes."""
    if arg("category") or arg("force") or DRY_RUN or OWNER_TEST:
        return True
    local = israel_now()
    start, end = CONFIG.get("post_window", [7, 23])
    if not (start <= local.hour < end):
        log(f"Outside posting hours ({start}:00-{end}:00 Israel), nothing to do")
        return False
    per_day = CONFIG.get("posts_per_day", 20)
    today = local.date().isoformat()
    if state.get("day_counts", {}).get(today, 0) >= per_day:
        log("Daily post limit reached")
        return False
    # Pace by schedule, not by a fixed gap: the trigger only fires every ~15 minutes, so a fixed gap
    # would round up to 30 minutes and cap the day at ~32 posts whatever posts_per_day says.
    gap = (end - start) * 60 / per_day
    done_today = state.get("day_counts", {}).get(today, 0)
    elapsed = (local.hour - start) * 60 + local.minute
    expected = per_day * elapsed / ((end - start) * 60)
    last = state.get("last_post_at")
    since = (now() - datetime.fromisoformat(last)).total_seconds() / 60 if last else 1e9
    if since < min(12, gap - 4) or (done_today >= expected + 1 and since < gap - 8):
        log(f"On schedule ({done_today} posted, ~{expected:.0f} due by now; last {since:.0f} min ago), waiting")
        return False
    if state.get("blocked_until", "") > now().isoformat():
        log(f"Amazon cooldown until {state['blocked_until'][11:16]} UTC: posting from the reserve instead")
        return "reserve"
    return True


def main():
    if "--test-telegram" in sys.argv:
        ok = send_telegram({"asin": "B0BSHF7WHW", "rank": 1, "title": "Test post from your deals bot",
                            "price": "$0.00", "image": ""}, {"slug": "test", "en": "Setup", "he": "בדיקה"})
        sys.exit(0 if ok else 1)

    if not DRY_RUN and not (TG_TOKEN and TG_CHAT):
        sys.exit("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or set DRY_RUN=1)")

    state = load_state()
    inbox(state)
    giveaway_draw(state)
    due = post_due(state)
    if not due:
        save_state(state)
        return
    cats = CONFIG["categories"]
    only = arg("category")              # e.g. --category toys-and-games for a one-off targeted post
    keyword = (arg("keyword") or "").lower()  # e.g. --keyword lego: only items whose title contains it
    targeted = bool(only)
    min_discount = int(arg("min-discount", 0) or 0)
    max_posts = int(arg("max-posts", CONFIG["max_posts_per_run"]))
    budget = int(arg("check", 60 if targeted else CONFIG["checks_per_run"]))
    preferred = min_discount or CONFIG["preferred_discount"]

    if targeted:
        lists = [(c, "bestsellers", 1) for c in cats if c["slug"] == only] or \
                [({"slug": only, "en": only.replace("-", " ").title(), "he": only}, "bestsellers", 1)]
        c0 = lists[0][0]
        lists += [(c0, "bestsellers", 2), (c0, "movers-and-shakers", 1), (c0, "movers-and-shakers", 2)]
    else:
        # weighted random pick of lists; avoid the categories used in the last few runs
        recent = state.get("recent_categories", [])
        groups = state.get("recent_groups", [])[-CONFIG.get("group_gap_posts", 2):]
        pool = [c for c in cats if c["slug"] not in recent and group_of(c["slug"]) not in groups
                and theme_of(c["slug"]) not in recent_themes(state)] or \
            [c for c in cats if c["slug"] not in recent and group_of(c["slug"]) not in groups] or \
            [c for c in cats if c["slug"] not in recent] or cats
        order = []
        while pool and len(order) < CONFIG["max_lists_per_run"]:
            pick = random.choices(pool, weights=[c.get("weight", 1) for c in pool])[0]
            pool.remove(pick)
            order.append(pick)
        # half the time look at what's trending (Movers & Shakers) rather than plain best sellers
        lists = [(c, random.choice(["bestsellers", "bestsellers", "movers-and-shakers"]), 1) for c in order]

    amz = None
    posted_now = 0
    candidates = []
    brands = [b.lower() for b in CONFIG.get("brands", [])]

    today = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    discount_weight = max([p.get("discount_weight", 1) for p in CONFIG.get("promo_periods", [])
                           if p["from"] <= today <= p["to"]] or [1])

    def score(it, info):
        """Popularity first (best-seller rank, trending), then discount and known brands as bonuses."""
        title = (info.get("title") or it.get("title") or "").lower()
        branded = any(title.startswith(b) or f" {b} " in f" {title[:40]} " for b in brands)
        r = it.get("rank") or 99
        popularity = 40 if r <= 3 else 30 if r <= 10 else 20 if r <= 20 else 10
        trending = 15 if it.get("source") == "movers-and-shakers" else 0
        boost = sum(v for k, v in CONFIG.get("boost_keywords", {}).items() if k in title)
        boost -= max([v for k, v in CONFIG.get("demote_keywords", {}).items() if k in title] or [0])
        pr = money(info.get("price"))
        value = CONFIG.get("higher_value_bonus", 25) if pr >= CONFIG.get("preferred_min_price_usd", 25) else \
            CONFIG.get("higher_value_bonus", 25) // 2 if pr >= 15 else 0
        return popularity + trending + min(discount_pct(info), 50) * discount_weight + (CONFIG.get("brand_bonus", 15) if branded else 0) + boost + value

    def post(it, info, category):
        nonlocal posted_now
        merged = {**it, **{k: v for k, v in info.items() if v}}
        if not merged.get("discount") and discount_pct(info):
            merged["discount"] = f"{discount_pct(info)}%"
        msg_id = send_telegram(merged, category)
        if msg_id:
            if not DRY_RUN and not OWNER_TEST:  # dry/test runs shouldn't stop the item being posted for real later
                state["posted"][it["asin"]] = now().isoformat()
                merged["message_id"] = msg_id
                remember_post(merged, category)
                state["last_post_at"] = now().isoformat()
                pool = load_json(POOL_F, {})
                if pool.pop(it["asin"], None):
                    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
                for f in (info.get("parent_asin"), title_family(info.get("title"))):
                    if f:
                        state.setdefault("families", {})[f] = now().isoformat()
                today = israel_now().date().isoformat()
                state["day_counts"] = {today: state.get("day_counts", {}).get(today, 0) + 1}
                state["recent_categories"] = (state.get("recent_categories", []) + [category["slug"]])[-4:]
                state["recent_titles"] = (state.get("recent_titles", []) + [merged.get("title") or ""])[-12:]
                th = theme_of(category.get("slug") if not str(category.get("slug", "")).startswith(("aliexpress", "pick")) else None,
                              category.get("en"), merged.get("title"))
                state["recent_themes"] = (state.get("recent_themes", []) + [th or "other"])[-8:]
                if group_of(category.get("slug")):
                    state["recent_groups"] = (state.get("recent_groups", []) + [group_of(category["slug"])])[-6:]
                if it.get("store") != "aliexpress":
                    state["since_ali"] = state.get("since_ali", 0) + 1
            posted_now += 1
            time.sleep(3)

    def post_ali(reason):
        if not ALI_ON:
            return False
        try:
            found = ali_pick(state)
        except Exception as e:
            log(f"  (AliExpress failed: {e})")
            return False
        if not found:
            return False
        it, info, category = found
        log(f"{reason}: posting AliExpress deal {info['price']} sold {info['sold']} {info['title'][:50]}")
        before = posted_now
        post(it, info, category)
        if OWNER_TEST:
            state["posted"][it["asin"]] = now().isoformat()  # in memory only, so the 2nd test is a different item
        if posted_now > before and not DRY_RUN and not OWNER_TEST:
            state["since_ali"] = 0
        return posted_now > before

    def post_reserve(reason):
        v = pool_take(state, lambda v: score(v["it"], v["info"]))
        if v:
            log(f"{reason}: posting reserve deal {v['it']['asin']} {v['info']['title'][:50]}")
            post(v["it"], v["info"], v["category"])
        else:
            log(f"{reason}: reserve is empty")
            post_ali(f"{reason} (Amazon stock empty)")

    # picks scheduled in config (e.g. from Matt's screenshots) join the queue once
    done = set(state.get("scheduled_picks_done", []))
    for sp in CONFIG.get("scheduled_picks", []):
        if sp["sid"] not in done:
            state.setdefault("pick_queue", []).append(dict(sp))
            state["scheduled_picks_done"] = sorted(done | {sp["sid"]})
            done.add(sp["sid"])
    # focus brand (config "focus"): a few posts a day at fixed Israel hours, ahead of the normal mix
    fc = CONFIG.get("focus") or {}
    if fc.get("hours"):
        today, hr = israel_now().date().isoformat(), israel_now().hour
        fdone = set(state.get("focus_done", []))
        for h in fc["hours"]:
            sid = f"focus-{today}-{h}"
            if hr >= h and sid not in fdone and not any(x.get("sid") == sid for x in state.get("pick_queue", [])):
                state.setdefault("pick_queue", []).append({"store": "amazon_focus", "id": fc.get("name", "focus"),
                                                              "url": "focus", "over_cap_ok": True, "sid": sid, "focus": True})
                fdone.add(sid)
        state["focus_done"] = sorted(fdone)[-30:]
    # Matt's own picks (links he sent the bot) go first
    pk = None
    if due and not targeted and not OWNER_TEST and state.get("pick_queue"):
        def amz_factory():
            if state.get("blocked_until", "") > now().isoformat():
                return None
            a = Amazon("safari")
            a.load_cookies()
            if COOKIES_F.exists() and a.location_is_israel():
                return a
            for profile in ("safari", "chrome"):
                a = Amazon(profile)
                if a.set_location_israel():
                    a.save_cookies()
                    return a
            return None
        ready = [x for x in state["pick_queue"] if x.get("not_before", "") <= now().isoformat()]
        pk = ready[0] if ready else None
    if due and not targeted and not OWNER_TEST and state.get("pick_queue") and pk:
        try:
            found = pick_details(pk, amz_factory)
        except Blocked:
            state["blocked_until"] = (now() + timedelta(minutes=CONFIG.get("block_cooldown_minutes", 60))).isoformat()
            found = None
        except Exception as e:
            found = f"lookup failed ({e})"
        if isinstance(found, tuple) and state["posted"].get(found[0]["asin"]) and \
                is_recent(state["posted"][found[0]["asin"]], CONFIG["repost_after_days"]):
            state["pick_queue"].remove(pk)
            if not pk.get("focus"):
                tg_owner(f"🔁 Skipped your pick ({pk.get('id')}): it was already posted in the last 7 days")
            found = None
        if isinstance(found, tuple):
            it, info, category = found
            if pk.get("title"):  # Matt-approved honest title (e.g. drop "4K"/brand claims the listing can't back up)
                info["title"] = pk["title"]
            if pk.get("style_of"):  # unofficial brand-style item: label it "בסגנון X"
                info["style_of"] = pk["style_of"]
            for k in ("note_he", "note_en"):  # a line Matt wants added (e.g. import charges)
                if pk.get(k):
                    info[k] = pk[k]
            state["pick_queue"].remove(pk)
            before = posted_now
            post(it, info, category)
            if posted_now > before:
                if not pk.get("focus"):
                    tg_owner(f"📢 Posted your pick: {info['title'][:60]}")
                save_state(state)
                return
            log(f"Matt's pick {pk.get('id')}: Telegram send failed")
            if pk.get("tries", 0) < 2:
                state["pick_queue"].insert(0, {**pk, "tries": pk.get("tries", 0) + 1})
            else:
                tg_owner(f"⚠️ Couldn't send your pick to the channel after 3 tries: {info['title'][:60]}")
        elif isinstance(found, str):
            state["pick_queue"].remove(pk)
            log(f"Matt's pick {pk.get('id')} dropped: {found}")
            if not pk.get("focus"):
                tg_owner(f"⚠️ Couldn't post your pick ({pk['url'][:80]}): {found}")
        else:
            log("Matt's pick (Amazon) waiting: Amazon isn't reachable right now")

    if due is True and not targeted and not OWNER_TEST and (coupon_post(state) or bundle_post(state)):
        save_state(state)
        return

    if OWNER_TEST:
        for i in range(int(arg("max-posts", 2) or 2)):
            post_ali(f"Owner test {i + 1}")
        return

    # Mix: every Nth post comes from AliExpress (falls back to Amazon if nothing suitable is found)
    every = CONFIG.get("aliexpress_every", 3)
    if not targeted and ALI_ON and (arg("store") == "aliexpress" or state.get("since_ali", 0) >= every - 1):
        if post_ali("AliExpress turn"):
            save_state(state)
            return

    if due == "reserve":
        post_reserve("Amazon cooldown")
        save_state(state)
        return

    # Collect-then-post: check Amazon only every few hours (a bigger batch), post from the stock in between
    harvest = targeted
    if not targeted:
        stock = len(pool_fresh(state))
        last_h = state.get("last_harvest_at", "")
        if stock >= CONFIG.get("reserve_min", 3) and is_recent(last_h, CONFIG.get("harvest_every_hours", 4) / 24):
            log(f"{stock} deals in stock (last Amazon check {last_h[11:16]} UTC): posting from stock")
            post_reserve("Stock")
            save_state(state)
            return
        harvest = True
        budget = int(arg("check", CONFIG.get("harvest_checks", 30)))
        log(f"Stock is {stock}: checking Amazon for new deals (up to {budget} products)")
        lists = lists + [(c, random.choice(["bestsellers", "movers-and-shakers"]), 1)
                         for c in random.choices(cats, weights=[c.get("weight", 1) for c in cats],
                                                 k=CONFIG.get("harvest_extra_lists", 3))]

    try:
        log("Setting delivery location to Israel…")
        amz = Amazon("safari")
        amz.load_cookies()
        reused = COOKIES_F.exists() and amz.location_is_israel()
        for attempt, profile in enumerate([] if reused else ["safari", "chrome", "safari"], 1):
            amz = Amazon(profile)
            if amz.set_location_israel():
                break
            log(f"  attempt {attempt}: location not set to Israel yet")
            time.sleep(5)
        else:
            if not reused:
                log("! Couldn't set delivery to Israel this run")
                post_reserve("No Israel location")
                save_state(state)
                return
        amz.save_cookies()

        for asin in filter(None, (arg("backfill", "") or "").split(",")):
            info = amz.product(asin.strip())
            item = {"asin": asin.strip(), "rank": 0, **{k: v for k, v in info.items() if v}}
            item["title_he"] = to_hebrew(short(item.get("title", "")))
            if not item.get("discount") and discount_pct(info):
                item["discount"] = f"{discount_pct(info)}%"
            remember_post(item, {"slug": "", "en": arg("backfill-category", ""), "he": arg("backfill-category-he", "")})
            log(f"  backfilled {asin}")
        if arg("backfill"):
            return

        checked = 0
        for category, kind, page in lists:
            if posted_now >= max_posts or checked >= budget:
                break
            try:
                items = amz.best_sellers(category["slug"], page, kind)
            except Blocked:
                raise
            except Exception as e:
                log(f"  ({category['slug']} {kind} p{page} failed: {e})")
                continue
            for i in items:
                i["source"] = kind
            log(f"\n[{category['en']} · {kind} p{page}] {len(items)} items")
            for it in items:
                if checked >= budget or posted_now >= max_posts:
                    break
                if keyword and keyword not in (it.get("title") or "").lower():
                    continue
                asin = it["asin"]
                low_t = (it.get("title") or "").lower()
                days = min([d for k, d in CONFIG.get("repost_days_override", {}).items() if k in low_t] or [CONFIG["repost_after_days"]])
                if is_recent(state["posted"].get(asin, ""), days):
                    continue
                if is_recent(state["not_free"].get(asin, ""), CONFIG["recheck_not_free_after_days"]):
                    continue
                checked += 1
                info = amz.product(asin)
                log(f"  #{it['rank']} {asin} shipping={info['shipping']} off={discount_pct(info)}%  {info['title'][:55]}")
                if info["shipping"] != "free":
                    if info["shipping"] in ("paid", "no"):
                        state["not_free"][asin] = now().isoformat()
                    continue
                if not info.get("price"):
                    log("     no price found, skipping")
                    continue
                if blocked(info.get("title")):
                    log("     blocked keyword, skipping")
                    continue
                if CONFIG.get("ali_niche_block") and re.search(CONFIG["ali_niche_block"], (info.get("title") or "").lower()):
                    log("     niche part/accessory, skipping")
                    continue
                if over_cap(info):
                    log(f"     {info['price']} is over the ${CONFIG.get('max_price_usd', 75)} cap, skipping")
                    continue
                fams = [f for f in (info.get("parent_asin"), title_family(info.get("title"))) if f]
                low = (info.get("title") or "").lower()
                days = min([d for k, d in CONFIG.get("repost_days_override", {}).items() if k in low] or [CONFIG["repost_after_days"]])
                if any(is_recent(state.get("families", {}).get(f, ""), days) for f in fams):
                    log("     same product (other color/size) was posted recently, skipping")
                    continue
                if discount_pct(info) < min_discount:
                    continue
                if targeted and discount_pct(info) >= preferred:
                    post(it, info, category)          # targeted run: first match wins
                else:
                    candidates.append((score(it, info), it, info, category))
                    pool_add(it, info, category)
                    if len(candidates) >= CONFIG.get("harvest_target", 25):
                        break
            if len(candidates) >= CONFIG.get("harvest_target", 25):
                break
        if not targeted:
            state["last_harvest_at"] = now().isoformat()
            log(f"\nStocked {len(candidates)} deal(s); {len(pool_fresh(state))} in stock")

        # scheduled runs: post the highest-scoring free-shipping item (popularity, trending, discount, brand)
        if posted_now < max_posts and candidates and not targeted:
            candidates.sort(key=lambda c: -c[0])
            for sc, it, info, category in candidates[:3]:
                log(f"  candidate score={sc} #{it['rank']} {it.get('source')} off={discount_pct(info)}% {info['title'][:50]}")
            varied = [c for c in candidates if not clashes(state, c[2].get("title"), c[3].get("slug"))]
            if varied:
                _, it, info, category = varied[0]
                post(it, info, category)
            else:
                log("  every candidate repeats a recent product type/brand; posting from stock instead")
                post_reserve("Variety")
    except Blocked as e:
        mins = CONFIG.get("block_cooldown_minutes", 60)
        log(f"\n! Amazon showed a robot check ({e}). Pausing Amazon requests for {mins} minutes.")
        state["blocked_until"] = (now() + timedelta(minutes=mins)).isoformat()
        if posted_now == 0 and not targeted:
            post_reserve("Blocked")
        save_state(state)
        return
    finally:
        # forget very old entries so the state file stays small
        for key, days in (("posted", 60), ("not_free", 30), ("families", 30)):
            state[key] = {a: t for a, t in state.get(key, {}).items() if is_recent(t, days)}
        save_state(state)

    if amz:
        amz.save_cookies()
    log(f"\nDone. Posted {posted_now} item(s). {amz.requests_made if amz else 0} Amazon requests"
        f" ({amz.cache_hits if amz else 0} products from cache).")


if __name__ == "__main__":
    main()
