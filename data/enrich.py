#!/usr/bin/env python3
"""Add bid/ask/endDate and recent exits (last 7d sells by tracked traders not holding) to overlap.json."""
import json, urllib.request, time, os
D=os.path.dirname(os.path.abspath(__file__))
def get(u):
    for i in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))
        except Exception as e: err=e; time.sleep(3*(i+1))
    raise err
W=json.load(open(f"{D}/wallets.json")); R=json.load(open(f"{D}/overlap.json")); now=time.time()
for r in R:
    m=get(f"https://gamma-api.polymarket.com/markets?condition_ids={r['conditionId']}")[0]
    r.update(bid=m.get("bestBid"),ask=m.get("bestAsk"),end=m.get("endDate"),question=m.get("question"))
    held={h["trader"] for h in r["holders"]}; r["exits"]=[]
    for w in W:
        if w["name"] in held: continue
        a=get(f"https://data-api.polymarket.com/activity?user={w['wallet']}&market={r['conditionId']}&limit=50")
        s=[x for x in a if x.get("side")=="SELL" or x.get("type") in("REDEEM","MERGE")]
        if s and now-s[0]["timestamp"]<7*86400: r["exits"].append(dict(trader=w["name"],outcome=s[0].get("outcome"),size=sum(x.get("size",0) for x in a if x.get("side")=="BUY"),price=(lambda ss:(sum(x["size"]*x["price"] for x in ss)/sum(x["size"] for x in ss)) if ss else None)([x for x in a if x.get("side")=="SELL" and x.get("size")]),mtype=s[0].get("type"),t=s[0]["timestamp"]))
json.dump(R,open(f"{D}/overlap.json","w"),indent=1)
for r in R: print(r["slug"][:60],r["bid"],r["ask"],(r["end"] or "")[:10],r["exits"])
