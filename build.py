import json,urllib.parse
d=json.load(open('data/overlap.json'))
def cat(m):
    s=(m['title']+' '+' '.join(m.get('tags',[]))).lower()
    if '2028' in s: return '2028'
    if any(k in s for k in ['iran','israel','netanyahu','gaza','hamas','likud']): return 'Iran/Israel'
    if any(k in s for k in ['senate','house','governor','midterm','election','mayor']) : return 'US elections'
    return 'Other'
out=[]
for m in d:
    if any(k in m['title'].lower() for k in ['avengers','box office']): continue
    hs=m['holders']; _o={}
    for h in hs: _o.setdefault(h['trader'],set()).add(h['outcome'])
    hs=[h for h in hs if len(_o[h['trader']])<2]
    if len(set(h['trader'] for h in hs))<2 or sum(h['currentValue'] for h in hs)<1000: continue
    m['total']=sum(h['currentValue'] for h in hs)
    if len(hs)<2: continue
    sides={}
    for h in hs: sides.setdefault(h['outcome'],set()).add(h['trader'])
    names=set(h['trader'] for h in hs)
    top=max(sides,key=lambda k:len(sides[k]))
    tr=[{'n':h['trader'],'side':h['outcome'],'sh':h['size'],'avg':h['avgPrice'],'val':h['currentValue'],'ex':None} for h in hs]
    tr+=[{'n':e['trader'],'side':e['outcome'],'sh':e['size'],'avg':None,'val':0,'ex':e['price']} for e in m.get('exits',[]) if e['trader'] not in {h['trader'] for h in hs}]
    url=f"https://polymarket.com/event/{m['eventSlug']}"+(f"/{m['slug']}" if m['slug']!=m['eventSlug'] else '')
    q=urllib.parse.quote_plus(m['title'].replace('Will ','').rstrip('?'))
    out.append(dict(t=m['title'],url=url,cat=cat(m),bid=m.get('bid'),ask=m.get('ask'),top=top,cnt=len(sides[top]),n=len(names),tot=m['total'],tr=tr,q=q,end=m.get('endDate',''),img=m.get('icon') or ''))
def _now(o):
    try: return float(o['ask']) if o['top']=='Yes' else 1-float(o['bid'])
    except: return None
out=[o for o in out if _now(o) is not None and _now(o)>=0.10]
out=[o for o in out if float(o['ask'])<=0.98]
out.sort(key=lambda x:(-x['cnt'],-x['cnt']/x['n'],-x['tot']))
#nocap
print([(o['t'][:40],o['cnt'],o['n'],o['cat']) for o in out])
html=open('tpl.html').read().replace('__DATA__',json.dumps(out)).replace('__TRADERS__',open('traders.json').read())
open('index.html.new','w').write(html)
