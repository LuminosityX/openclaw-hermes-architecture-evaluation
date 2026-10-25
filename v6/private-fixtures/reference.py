from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

def instant(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("timestamp requires timezone")
    return d.astimezone(timezone.utc)

def reconcile(events, cutoff=None):
    latest={}
    end=instant(cutoff) if cutoff else None
    for e in events:
        if end is not None and instant(e["at"])>end: continue
        prev=latest.get(e["event_id"])
        if prev is None or int(e["revision"])>int(prev["revision"]):latest[e["event_id"]]=e
    orders={};rejected=[]
    for e in sorted(latest.values(),key=lambda x:(instant(x["at"]),x["event_id"])):
        typ=e["type"];oid=e["order_id"];cur=e["currency"]
        amount=Decimal(e["amount"]).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        reason=None;o=orders.get(oid)
        if amount<0:reason="negative_amount"
        elif typ=="create":
            if o:reason="duplicate_order"
            else:orders[oid]={"order_id":oid,"currency":cur,"limit":amount,"captured":Decimal(0),"refunded":Decimal(0),"void":False}
        elif o is None:reason="missing_order"
        elif cur!=o["currency"]:reason="currency_mismatch"
        elif typ not in ("capture","refund","void"):reason="unknown_type"
        elif o["void"]:reason="voided_order"
        elif typ=="capture":
            if o["captured"]+amount>o["limit"]:reason="over_capture"
            else:o["captured"]+=amount
        elif typ=="refund":
            if o["refunded"]+amount>o["captured"]:reason="over_refund"
            else:o["refunded"]+=amount
        else:
            if o["captured"]!=o["refunded"]:reason="outstanding_capture"
            else:o["void"]=True
        if reason:rejected.append({"event_id":e["event_id"],"reason":reason})
    out=[];totals={}
    for oid,o in sorted(orders.items()):
        c,r=o["captured"],o["refunded"];net=c-r
        status="void" if o["void"] else "refunded" if c>0 and net==0 else "paid" if c==o["limit"] and r==0 and c>0 else "partial" if c>0 else "open"
        out.append({"order_id":oid,"currency":o["currency"],"captured":f"{c:.2f}","refunded":f"{r:.2f}","net":f"{net:.2f}","status":status})
        t=totals.setdefault(o["currency"],[Decimal(0),Decimal(0),Decimal(0)])
        for i,v in enumerate((c,r,net)):t[i]+=v
    return {"orders":out,"rejected":rejected,"totals":[dict(currency=k,captured=f"{v[0]:.2f}",refunded=f"{v[1]:.2f}",net=f"{v[2]:.2f}") for k,v in sorted(totals.items())]}
