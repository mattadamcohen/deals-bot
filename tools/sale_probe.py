import sys, json, datetime
sys.path.insert(0, "tools")
import aliexpress as a
end = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
start = datetime.datetime(2026, 11, 15)
f = "%Y-%m-%d %H:%M:%S"
for status in ["Payment Completed", "Buyer Confirmed Receipt", "Completed Settlement", "Invalid"]:
    try:
        r = a.call("aliexpress.affiliate.order.list", start_time=start.strftime(f), end_time=end.strftime(f),
                   status=status, page_size=50, page_no=1,
                   fields="order_id,order_status,paid_amount,estimated_paid_commission,product_title,paid_time,tracking_id")
        orders = ((r.get("orders") or {}).get("order") or [])
        print("ORDERS", status, len(orders))
        for o in orders:
            print("  ", o.get("paid_time"), o.get("paid_amount"), "commission:", o.get("estimated_paid_commission"), (o.get("product_title") or "")[:50])
    except Exception as e:
        print("ORDERS", status, "->", str(e)[:120])
