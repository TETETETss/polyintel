#!/usr/bin/env python3
"""Pull open positions for tracked wallets, find markets with >=2 holders (excl. sports/weather). Writes overlap.json."""
import json, urllib.request, concurrent.futures as cf, os, time
D=os.path.dirname(os.path.abspath(__file__)); DUST=500
def get(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))
        except Exception as e: err=e; time.sleep(1)
    raise err
W=json.load(open(f"{D}/wallets.json"))
def positions(w):
    # Data API v2 (v1 retired Nov 2026): cursor pagination, snake_case fields, sorted by current value desc
    out,cur=[],None
    for _ in range(20):
        u=f"https://data-api.polymarket.com/v2/positions?user={w['wallet']}&limit=500"+(f"&cursor={cur}" if cur else "")
        d=get(u); rows=d.get("data",[])
        for x in rows:
            out.append(dict(conditionId=x["condition_id"],title=x["title"],slug=x["slug"],eventSlug=x["event_slug"],endDate=x.get("end_date"),icon=x.get("icon"),
              outcome=x["outcome"],size=x["current_size"],avgPrice=x["avg_price"],curPrice=x["current_price"],currentValue=x["current_value"],asset=x["token_id"],redeemable=x.get("redeemable")))
        pg=d.get("pagination") or {}
        if not pg.get("has_more") or not rows or rows[-1]["current_value"]<DUST: break
        cur=pg.get("next_cursor")
    return [x for x in out if not x.get("redeemable") and x["currentValue"]>=DUST]
with cf.ThreadPoolExecutor(8) as ex: P=dict(zip([w["name"] for w in W],ex.map(positions,W)))
by={}
for n,ps in P.items():
    for x in ps: by.setdefault(x["conditionId"],[]).append(dict(trader=n,**x))
cache_f=f"{D}/events_cache.json"; cache=json.load(open(cache_f)) if os.path.exists(cache_f) else {}
BAD={"sports","weather","soccer","nba","nfl","mlb","nhl","tennis","esports","cricket","golf","ufc","f1","climate & weather"}
res=[]
for cid,hs in by.items():
    if len({h["trader"] for h in hs})<2: continue
    es=hs[0]["eventSlug"]
    if es not in cache:
        ev=get(f"https://gamma-api.polymarket.com/events?slug={es}")
        cache[es]=[t["label"] for t in (ev[0].get("tags") or [])] if ev else []
    tags=cache[es]
    if any(t.lower() in BAD for t in tags): continue
    res.append(dict(conditionId=cid,title=hs[0]["title"],slug=hs[0]["slug"],eventSlug=es,tags=tags,endDate=hs[0].get("endDate"),icon=hs[0].get("icon") or hs[0].get("image"),
      total=sum(h["currentValue"] for h in hs),
      holders=[{k:h[k] for k in("trader","outcome","size","avgPrice","curPrice","currentValue","asset")} for h in hs]))
json.dump(cache,open(cache_f,"w"))
res.sort(key=lambda r:-r["total"]); json.dump(res,open(f"{D}/overlap.json","w"),indent=1)
print({n:len(p) for n,p in P.items()})
for r in res: print(f"${r['total']:,.0f} | {r['slug']} | {r['tags'][:4]} | "+"; ".join(f"{h['trader']} {h['outcome']} {h['size']:.0f}@{h['avgPrice']:.2f} cur{h['curPrice']}" for h in r["holders"]))
