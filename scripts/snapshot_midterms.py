"""Snapshot tracked wallets' open positions on US 2026 midterm markets -> data/snapshots/midterms-<date>.json/.csv"""
import json,re,csv,sys,time,datetime as dt,urllib.request,concurrent.futures as cf,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KW=re.compile(r"midterm|senate|house|governor|gubernatorial|congress|congressional|\bdistrict\b|-district|\b[A-Z]{2}-\d{1,2}\b|attorney general|secretary of state|balance of power|ballot measure|proposition",re.I)
EXCL=re.compile(r"israel|uk |british|canad|japan|australia|brazil|france|german|india|white house|house of (lords|commons|representatives of (?!the united))|fed |shutdown|mortgage|nigeria|ogun|lagos|mexic|michoacan|puebla|veracruz|tlaxcala|sonora|colima|chihuahua|chiapas|zacatecas|jalisco|guanajuato|oaxaca|guerrero|morelos|tabasco|yucatan|quintana|campeche|sinaloa|durango|nayarit|coahuila|nuevo-leon|tamaulipas|hidalgo|queretaro|aguascalientes|san-luis-potosi|baja-california|cdmx|congress-election-winner|20260803170329|humanitys|earthquake|aircraft|new-zealand|serbia|solana|mamdani|scotus|gemini",re.I)
def get(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"polyintel"}),timeout=30))
        except Exception as e: err=e; time.sleep(2*(i+1))
    raise err
def positions(w):
    out,cur=[],None
    for _ in range(30):
        d=get(f"https://data-api.polymarket.com/v2/positions?user={w['wallet']}&limit=500"+(f"&cursor={cur}" if cur else ""))
        out+=d.get("data",[]); pg=d.get("pagination") or {}
        if not pg.get("has_more") or not d.get("data"): break
        cur=pg.get("next_cursor")
    return out
def is_mid(x):
    t=f"{x.get('title','')} {x.get('event_slug','')} {x.get('slug','')}"
    if EXCL.search(t): return False
    return bool(KW.search(t)) and ("2026" in t or "midterm" in t.lower() or (x.get("end_date") or "")[:4] in ("2026","2027"))
def main():
    W=json.load(open(f"{ROOT}/data/wallets.json")); now=dt.datetime.now(dt.timezone.utc)
    rows,failed=[],[]
    with cf.ThreadPoolExecutor(8) as ex:
        futs={ex.submit(positions,w):w for w in W}
        for f in cf.as_completed(futs):
            w=futs[f]
            try: P=f.result()
            except Exception as e: failed.append(dict(name=w["name"],wallet=w["wallet"],error=str(e))); continue
            for x in P:
                if x.get("status","OPEN")!="OPEN" or x.get("redeemable") or x["current_value"]<1 or not is_mid(x): continue
                rows.append(dict(trader=w["name"],wallet=w["wallet"],title=x["title"],slug=x["slug"],event_slug=x["event_slug"],condition_id=x["condition_id"],
                  token_id=x["token_id"],outcome=x["outcome"],outcome_index=x.get("outcome_index"),shares=round(x["current_size"],4),avg_price=x["avg_price"],
                  current_price=x["current_price"],cost_basis=round(x["total_cost_usdc"] if x.get("total_cost_usdc") is not None else x["current_size"]*x["avg_price"],2),
                  current_value=round(x["current_value"],2),unrealized_pnl=round(x["unrealized_pnl"],2),end_date=x.get("end_date"),snapshot_utc=now.isoformat(timespec="seconds")))
    M={}
    for r in rows:
        m=M.setdefault(r["condition_id"],dict(condition_id=r["condition_id"],title=r["title"],slug=r["slug"],event_slug=r["event_slug"],end_date=r["end_date"],sides={}))
        s=m["sides"].setdefault(r["outcome"],dict(outcome=r["outcome"],traders=0,cost=0,value=0,shares=0,price=r["current_price"]))
        s["traders"]+=1; s["cost"]+=r["cost_basis"]; s["value"]+=r["current_value"]; s["shares"]+=r["shares"]
    for m in M.values():
        for s in m["sides"].values(): s["cost"]=round(s["cost"],2); s["value"]=round(s["value"],2); s["shares"]=round(s["shares"],2)
        sd=sorted(m["sides"].values(),key=lambda s:-s["cost"]); m["total_cost"]=round(sum(s["cost"] for s in sd),2)
        m["total_value"]=round(sum(s["value"] for s in sd),2); m["lean"]=sd[0]["outcome"]; m["lean_pct"]=round(100*sd[0]["cost"]/m["total_cost"],1) if m["total_cost"] else None
        m["lean_price"]=sd[0]["price"]; m["sides"]=sd
    mk=sorted(M.values(),key=lambda m:-m["total_cost"])
    out=dict(snapshot_utc=now.isoformat(timespec="seconds"),snapshot_awst=now.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M AWST"),
      wallets_checked=len(W),failed=failed,traders_with_positions=len({r["wallet"] for r in rows}),n_positions=len(rows),n_markets=len(mk),
      total_cost=round(sum(r["cost_basis"] for r in rows),2),total_value=round(sum(r["current_value"] for r in rows),2),positions=sorted(rows,key=lambda r:-r["current_value"]),markets=mk)
    d=f"{ROOT}/data/snapshots"; os.makedirs(d,exist_ok=True); base=f"{d}/midterms-{sys.argv[1] if len(sys.argv)>1 else now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()}"
    json.dump(out,open(base+".json","w"),indent=1)
    with open(base+".csv","w",newline="") as f:
        if rows: c=csv.DictWriter(f,fieldnames=list(rows[0])); c.writeheader(); c.writerows(out["positions"])
    with open(base+"-markets.csv","w",newline="") as f:
        c=csv.writer(f); c.writerow(["condition_id","title","slug","end_date","total_cost","total_value","lean","lean_pct","lean_price","sides"])
        for m in mk: c.writerow([m["condition_id"],m["title"],m["slug"],m["end_date"],m["total_cost"],m["total_value"],m["lean"],m["lean_pct"],m["lean_price"],"; ".join(f"{s['outcome']}:{s['traders']}t ${s['cost']:.0f}" for s in m["sides"])])
    print(base, out["snapshot_awst"], len(rows), len(mk), out["total_cost"], out["total_value"], "failed", failed)
main()
