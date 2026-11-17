import sys, json, datetime
sys.path.insert(0, "tools")
import aliexpress as a
end = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
start = end - datetime.timedelta(days=5)
f = "%Y-%m-%d %H:%M:%S"
for status in ["Payment Completed", "Buyer Confirmed Receipt"]:
    try:
        r = a.call("aliexpress.affiliate.order.list", start_time=start.strftime(f), end_time=end.strftime(f),
                   status=status, page_size=50, page_no=1,
                   fields="order_id,order_status,paid_amount,estimated_paid_commission,product_title,paid_time,tracking_id")
        print("ORDERS", status, json.dumps(r)[:800])
    except Exception as e:
        print("ORDERS", status, "ERROR", e)
