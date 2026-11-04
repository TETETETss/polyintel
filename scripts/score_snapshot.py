#!/usr/bin/env python3
"""Score a midterm snapshot. Usage: score_snapshot.py SNAP.json [OUT.json]
Official = gamma market closed & outcomePrices 1/0 (or umaResolutionStatus resolved).
Provisional = official OR live price >=0.97 on one side."""
import json,sys,time,urllib.request,urllib.parse
from collections import defaultdict
snap=json.load(open(sys.argv[1])); out=sys.argv[2] if len(sys.argv)>2 else sys.argv[1].replace('.json','-score.json')
P=snap['positions']; cids=sorted({p['condition_id'] for p in P})
def get(u):
  for i in range(4):
    try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'polyintel'}),timeout=30))
    except Exception: time.sleep(2)
  return []
M={}
for i in range(0,len(cids),40):
  q='&'.join('condition_ids='+c for c in cids[i:i+40])
  for closed in ('true','false'):
    for m in get(f'https://gamma-api.polymarket.com/markets?limit=100&closed={closed}&{q}') or []:
      M[m['conditionId'].lower()]=m
def info(cid):
  m=M.get(cid.lower())
  if not m: return None
  pr=m.get('outcomePrices'); pr=json.loads(pr) if isinstance(pr,str) else pr
  pr=[float(x) for x in pr] if pr else None
  uma=(m.get('umaResolutionStatus') or '').lower()
  off=None
  if pr and (m.get('closed') or uma=='resolved'):
    if max(pr)>=0.999 and min(pr)<=0.001: off=pr.index(max(pr))
  prov=off
  if prov is None and pr and max(pr)>=0.97: prov=pr.index(max(pr))
  return dict(official=off,provisional=prov,prices=pr,closed=m.get('closed'),uma=uma)
I={c:info(c) for c in cids}
def score(key):
  tot=dict(n=0,win=0,cost=0,cost_win=0,payout=0); tr=defaultdict(lambda:dict(n=0,win=0,cost=0,cost_win=0,payout=0))
  for p in P:
    i=I[p['condition_id']]; w=i and i[key]
    if w is None: continue
    win=(w==p['outcome_index']); pay=p['shares'] if win else 0
    for d in (tot,tr[p['trader']]):
      d['n']+=1; d['win']+=win; d['cost']+=p['cost_basis']; d['cost_win']+=p['cost_basis']*win; d['payout']+=pay
  def fin(d):
    d['pnl']=round(d['payout']-d['cost'],2); d['roi_pct']=round(100*d['pnl']/d['cost'],2) if d['cost'] else None
    d['acc_count_pct']=round(100*d['win']/d['n'],1) if d['n'] else None
    d['acc_cost_pct']=round(100*d['cost_win']/d['cost'],1) if d['cost'] else None
    for k in ('cost','cost_win','payout'): d[k]=round(d[k],2)
    return d
  board=sorted(({'trader':t,**fin(d)} for t,d in tr.items()),key=lambda x:-x['pnl'])
  # smart money lean per market: side with more cost
  lean=defaultdict(lambda:defaultdict(float))
  for p in P: lean[p['condition_id']][p['outcome_index']]+=p['cost_basis']
  lh=ln=0
  for c,s in lean.items():
    w=I[c] and I[c][key]
    if w is None: continue
    ln+=1; lh+= max(s,key=s.get)==w
  mk=sum(1 for c in cids if I[c] and I[c][key] is not None)
  return dict(markets_decided=mk,markets_pending=len(cids)-mk,positions_decided=tot['n'],positions_pending=len(P)-tot['n'],
    overall=fin(tot),lean_hit=lh,lean_n=ln,lean_hit_pct=round(100*lh/ln,1) if ln else None,leaderboard=board)
keys=['democratic-party-control-the-house','republican-party-control-the-house','control-the-senate','texas-senate','governor']
key_races=[]
seen=set()
for p in P:
  s=p['slug']
  if p['condition_id'] in seen or not any(k in s for k in ('control-the-house','control-the-senate','texas','california-governor','becerra')): continue
  seen.add(p['condition_id']); i=I[p['condition_id']] or {}
  cost=sum(q['cost_basis'] for q in P if q['condition_id']==p['condition_id'])
  key_races.append(dict(title=p['title'],slug=s,smart_cost=round(cost,2),prices=i.get('prices'),closed=i.get('closed'),uma=i.get('uma'),official_winner_idx=i.get('official'),provisional_winner_idx=i.get('provisional')))
key_races.sort(key=lambda x:-x['smart_cost'])
R=dict(snapshot=sys.argv[1],scored_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),n_markets=len(cids),n_positions=len(P),
  markets_not_found=sum(1 for c in cids if I[c] is None),official=score('official'),provisional_97c=score('provisional'),key_races=key_races[:15],
  note='Assumes positions held to resolution. provisional_97c treats >=97c sides as decided and is NOT official.')
json.dump(R,open(out,'w'),indent=1); print(out)
