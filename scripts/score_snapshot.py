"""Score a midterm snapshot after resolution.
Usage: python3 scripts/score_snapshot.py data/snapshots/midterms-2026-11-04.json [--out report.json]
Resolution comes from the gamma API (closed market, outcomePrices of 1/0). Unresolved markets are listed as pending and left out of accuracy.
Accuracy = share of resolved positions that won (also $-weighted by cost). Realized PnL = shares*payout - cost basis (held to resolution)."""
import json,sys,urllib.request,time,collections
def get(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"polyintel"}),timeout=30))
        except Exception as e: err=e; time.sleep(2*(i+1))
    raise err
def resolutions(cids):
    R={}; cids=list(cids)
    for i in range(0,len(cids),40):
        q="&".join("condition_ids="+c for c in cids[i:i+40])
        for m in get(f"https://gamma-api.polymarket.com/markets?{q}&limit=100&closed=true")+get(f"https://gamma-api.polymarket.com/markets?{q}&limit=100"):
            outs=json.loads(m.get("outcomes") or "[]"); px=[float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
            done=bool(m.get("closed")) and px and max(px)>=0.99 and sum(px)<=1.01
            R[m["conditionId"]]=dict(resolved=done,payout=dict(zip(outs,px)) if done else None,winner=outs[px.index(max(px))] if done else None)
    return R
def main():
    S=json.load(open(sys.argv[1])); R=resolutions({p["condition_id"] for p in S["positions"]})
    T=collections.defaultdict(lambda:dict(n=0,won=0,cost=0,cost_won=0,payout=0)); pending=0; O=T["__ALL__"]
    for p in S["positions"]:
        r=R.get(p["condition_id"])
        if not r or not r["resolved"]: pending+=1; continue
        pay=p["shares"]*r["payout"].get(p["outcome"],0); win=r["winner"]==p["outcome"]
        for t in (T[p["trader"]],O): t["n"]+=1; t["won"]+=win; t["cost"]+=p["cost_basis"]; t["cost_won"]+=p["cost_basis"]*win; t["payout"]+=pay
    def fin(t): return dict(positions=t["n"],won=t["won"],accuracy_pct=round(100*t["won"]/t["n"],1) if t["n"] else None,
        cost_weighted_accuracy_pct=round(100*t["cost_won"]/t["cost"],1) if t["cost"] else None,cost=round(t["cost"],2),payout=round(t["payout"],2),
        pnl=round(t["payout"]-t["cost"],2),roi_pct=round(100*(t["payout"]-t["cost"])/t["cost"],1) if t["cost"] else None)
    lean=dict(n=0,right=0,cost=0,cost_right=0)
    for m in S["markets"]:
        r=R.get(m["condition_id"])
        if not r or not r["resolved"]: continue
        ok=r["winner"]==m["lean"]; lean["n"]+=1; lean["right"]+=ok; lean["cost"]+=m["total_cost"]; lean["cost_right"]+=m["total_cost"]*ok
    rep=dict(snapshot=S["snapshot_awst"],positions_total=len(S["positions"]),positions_pending=pending,
      markets_resolved=lean["n"],markets_total=len(S["markets"]),overall=fin(O),
      smart_money_lean=dict(markets=lean["n"],correct=lean["right"],accuracy_pct=round(100*lean["right"]/lean["n"],1) if lean["n"] else None,
        dollar_weighted_accuracy_pct=round(100*lean["cost_right"]/lean["cost"],1) if lean["cost"] else None),
      traders=sorted(({"trader":k,**fin(v)} for k,v in T.items() if k!="__ALL__"),key=lambda x:-x["pnl"]))
    js=json.dumps(rep,indent=1); print(js)
    if "--out" in sys.argv: open(sys.argv[sys.argv.index("--out")+1],"w").write(js)
main()
