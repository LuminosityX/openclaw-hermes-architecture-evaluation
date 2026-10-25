def reconcile(events, cutoff=None):
    orders={}
    for e in events:
        oid=e['order_id']
        if e['type']=='create': orders[oid]={'order_id':oid,'currency':e['currency'],'captured':0.,'refunded':0.,'net':0.,'status':'open'}
        elif oid in orders:
            key='captured' if e['type']=='capture' else 'refunded'
            orders[oid][key]+=float(e['amount'])
            orders[oid]['net']=orders[oid]['captured']-orders[oid]['refunded']
    return {'orders':list(orders.values()),'rejected':[],'totals':[]}
