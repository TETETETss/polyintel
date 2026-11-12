import json,urllib.parse,re,os
def shown_in_markets(bid, ask, top):
    """Open positions stay listed through 100c. A consensus side under 10c stays off."""
    try:
        ask=float(ask); bid=float(bid)
    except (TypeError, ValueError):
        return False
    now=ask if top=='Yes' else 1-bid
    return now>=0.10 and ask<=1
d=json.load(open('data/overlap.json'))
MENTION=re.compile(r'\b(say|says|said|mention|mentions|mentioned|tweet|post)\b.*["\u201c]|\bmention')
CATS=[('Mention',MENTION.pattern),
 ('Pop culture',r'(movie|film|oscar|academy award|emmy|grammy|golden globe|james bond|halftime|super bowl|big game|album|song|spotify|netflix|box office|top grossing|actor|actress|best picture|searched|time person of the year|pregnant|marvel|avengers|spider-man|taylor swift|drake|kardashian|celebrity)'),
 ('Crypto',r'\b(bitcoin|btc|ethereum|eth|solana|xrp|crypto|doge|token|airdrop)\b'),
 ('Iran/Israel',r'(iran|israel|gaza|hamas|hezbollah|lebanon|netanyahu|khamenei|hormuz|knesset|likud)'),
 ('US politics',r'\b(trump|senate|house|governor|midterm|democrats?|republicans?|mayor|white house|press secretary|congress|epstein|vance|harris|newsom|mamdani|supreme court|cabinet|hegseth|alito|secretary)\b'),
 ('World',r'\b(putin|russia|ukraine|china|xi|takaichi|kim jong|brazil|bolsonaro|greece|prime minister|president of|election|ceasefire|nato|venezuela|maduro)\b'),
 ('Tech & economy',r'\b(openai|anthropic|ai model|ipo|fed|rate|inflation|recession|stock|market cap|oil|diesel|tariff|nvidia|apple|meta|google)\b')]
def cat(m):
    t=m['title'].lower()
    if '2028' in t: return '2028'
    for c,rx in CATS:
        if re.search(rx,t): return c
    return 'Other'
out=[]
for m in d:
    if any(k in m['title'].lower() for k in ['avengers','box office']): continue
    hs=m['holders']; _o={}
    for h in hs: _o.setdefault(h['trader'],set()).add(h['outcome'])
    hs=[h for h in hs if len(_o[h['trader']])<2]
    if len(set(h['trader'] for h in hs))<2 or (sum(h['currentValue'] for h in hs)<1000 and cat(m)!='Mention'): continue   # 2+ traders always; mention markets have no $ minimum
    m['total']=sum(h['currentValue'] for h in hs)
    if len(hs)<2: continue
    sides={}
    for h in hs: sides.setdefault(h['outcome'],set()).add(h['trader'])
    names=set(h['trader'] for h in hs)
    top=max(sides,key=lambda k:len(sides[k]))
    tr=[{'n':h['trader'],'side':h['outcome'],'sh':h['size'],'avg':h['avgPrice'],'val':h['currentValue'],'ex':None,'fe':h.get('fe')} for h in hs]
    tr+=[{'n':e['trader'],'side':e['outcome'],'sh':e['size'],'avg':None,'val':0,'ex':e['price']} for e in m.get('exits',[]) if e['trader'] not in {h['trader'] for h in hs}]
    url=f"https://polymarket.com/event/{m['eventSlug']}"+(f"/{m['slug']}" if m['slug']!=m['eventSlug'] else '')
    q=urllib.parse.quote_plus(m['title'].replace('Will ','').rstrip('?'))
    out.append(dict(t=m['title'],url=url,cat=cat(m),bid=m.get('bid'),ask=m.get('ask'),top=top,cnt=len(sides[top]),n=len(names),tot=m['total'],tr=tr,q=q,end=m.get('endDate',''),img=m.get('icon') or '',cid=m.get('conditionId') or '',slug=m.get('slug') or ''))
out=[o for o in out if shown_in_markets(o.get('bid'), o.get('ask'), o.get('top'))]
out.sort(key=lambda x:(-x['cnt'],-x['cnt']/x['n'],-x['tot']))
#nocap
print([(o['t'][:40],o['cnt'],o['n'],o['cat']) for o in out])
_live=json.load(open('data/live.json')) if os.path.exists('data/live.json') else []
_in=json.load(open('data/inflows.json')) if os.path.exists('data/inflows.json') else {'mk':[]}
def _js(o): return json.dumps(o,separators=(',',':')).replace('<','\\u003c')
html=open('tpl.html').read().replace('__INFLOW__',_js(_in)).replace('__NLIVE__',str(len(_live))).replace('__LIVE__',_js(_live)).replace('__DATA__',json.dumps(out)).replace('__TRADERS__',open('traders.json').read()).replace('{{BUILT}}',__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')).replace('{{NTRADERS}}',str(len(json.load(open('data/wallets.json')))))
open('index.html.new','w').write(html)
