import json,urllib.request,os,time
D=os.path.dirname(os.path.abspath(__file__)); R=json.load(open(f"{D}/overlap.json"))
def get(u):
    for i in range(3):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30))
        except Exception as e: err=e; time.sleep(1)
    raise err
M={}
ids=[r["conditionId"] for r in R]
for i in range(0,len(ids),40):
    for m in get("https://gamma-api.polymarket.com/markets?limit=100&"+"&".join("condition_ids="+c for c in ids[i:i+40])): M[m["conditionId"]]=m
for r in R:
    m=M.get(r["conditionId"]); r["bid"]=m.get("bestBid") if m else None; r["ask"]=m.get("bestAsk") if m else None
R=[r for r in R if r["ask"] is not None and r["bid"] is not None]
json.dump(R,open(f"{D}/overlap.json","w"),indent=1); print("priced",len(R))
