import json,subprocess
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"
def g(u):
    try: return json.loads(subprocess.run(["curl","-s","-A",UA,u],capture_output=True,text=True,timeout=40).stdout)
    except Exception: return None
out=[]
for w in json.load(open('data/wallets.json')):
    W=w['wallet']; r={'n':w['name']}
    for k,p in (('pnl','ALL'),('mpnl','MONTH')):
        d=g(f"https://data-api.polymarket.com/v1/leaderboard?timePeriod={p}&orderBy=PNL&user={W}")
        r[k]=(d[0].get('pnl') if isinstance(d,list) and d else None)
    d=g(f"https://data-api.polymarket.com/v2/user-pnl?user={W}&interval=all&fidelity=1d")
    pts=(d or {}).get('data',{}).get('points',[]) if isinstance(d,dict) else []
    s=[p.get('economic_pnl',0) for p in pts]; r['days']=len(s)
    if len(s)>90: st=len(s)/90; s=[s[int(i*st)] for i in range(90)]+[s[-1]]
    if r.get('pnl') is None and s: r['pnl']=s[-1]
    if r.get('mpnl') is None and len(pts)>30: r['mpnl']=pts[-1].get('economic_pnl',0)-pts[-31].get('economic_pnl',0)
    r['s']=s; out.append(r); print(r['n'],r['pnl'],r['mpnl'],r['days'],s[-1] if s else None)
out.sort(key=lambda r:-(r['pnl'] or 0)); json.dump(out,open('traders.json','w'))
