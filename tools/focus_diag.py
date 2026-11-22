"""Why does the focus brand (NeeDoh) find nothing? Prints search hits and Amazon shipping per item."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot
a = bot.Amazon("safari"); a.load_cookies()
if not a.location_is_israel():
    a.set_location_israel()
fc = bot.CONFIG["focus"]
seen = []
for q in fc["queries"] + ["needoh", "nee doh squishy", "schylling nee doh"]:
    hits = a.search_all(q, fc["require_any"])
    print(f"Q {q!r}: {len(hits)} hits")
    for asin, t in hits:
        if asin not in seen:
            seen.append(asin)
for asin in seen[:14]:
    info = a.product(asin)
    print("ITEM", asin, info.get("price"), info.get("shipping"), (info.get("title") or "")[:70])
