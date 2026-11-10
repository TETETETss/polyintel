#!/usr/bin/env python3
"""Latest trades for polyintel's tracked wallets, from Polymarket data-api v2.

v1 routes return HTTP 410. This writes data/live.json (~120 newest fills) for
build.py. data/refresh.py calls publish() after positions are already loaded,
so the existing 10-minute Actions run picks the feed up without a new job.
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = "https://data-api.polymarket.com/v2/"
LIVE_HOURS = float(os.environ.get("LIVE_HOURS", 36))
LIVE_PAGES = int(os.environ.get("LIVE_PAGES", 3))
LIVE_ROWS = int(os.environ.get("LIVE_ROWS", 120))
FILL_GAP = 120
MIN_TRADE_USD = 1.0

def F(p, *names, default=None):
    for n in names:
        if isinstance(p, dict) and n in p and p[n] is not None:
            return p[n]
    return default

def rows_of(d):
    if isinstance(d, list):
        return d, None
    if isinstance(d, dict):
        r = d.get("data")
        if isinstance(r, dict):
            r = r.get("positions") or r.get("items") or r.get("data") or []
        return (r or []), (d.get("pagination") or {}).get("next_cursor")
    return [], None

def get(url, tries=3):
    err = "error"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read()[:180].decode("utf-8", "replace")
            err = f"{e.code} {body}"
            if e.code < 500 and e.code != 429:
                print("  live http", e.code, url[:90], body)
                return None
        except Exception as e:
            err = str(e)
        time.sleep(0.8 * (i + 1))
    print("  live failed", url[:90], err)
    return None

def norm_ts(x):
    t = F(x, "timestamp", "ts", "time")
    if t is None:
        return 0
    try:
        t = float(t)
    except (TypeError, ValueError):
        return 0
    if t > 1e11:
        t /= 1000
    return int(t)

def market_url(slug, event_slug):
    slug, ev = slug or "", event_slug or ""
    path = f"{ev}/{slug}" if ev and slug and ev != slug else (slug or ev)
    return "https://polymarket.com/event/" + path if path else "https://polymarket.com/"

def activity_pages(addr, now=None):
    """Recent TRADE rows. Activity first, then v2 trades. Never v1."""
    now = time.time() if now is None else now
    cutoff = now - LIVE_HOURS * 3600
    rows, cur = [], None
    for _ in range(max(1, LIVE_PAGES)):
        q = {"user": addr, "limit": 100, "type": "TRADE"}
        if cur:
            q["cursor"] = cur
        d = get(V2 + "activity?" + urllib.parse.urlencode(q))
        if d is None:
            break
        r, cur = rows_of(d)
        rows += r or []
        if not r or not cur:
            break
        if min(norm_ts(x) or cutoff for x in r) < cutoff:
            break
    trades = [x for x in rows if str(F(x, "type", default="TRADE")).upper() == "TRADE"
              and str(F(x, "side", default="")).upper() in ("BUY", "SELL") and norm_ts(x) >= cutoff]
    if trades or rows:
        return trades
    rows, cur = [], None
    for _ in range(max(1, LIVE_PAGES)):
        q = {"user": addr, "limit": 100, "taker_only": "false"}
        if cur:
            q["cursor"] = cur
        d = get(V2 + "trades?" + urllib.parse.urlencode(q))
        if d is None:
            break
        r, cur = rows_of(d)
        rows += r or []
        if not r or not cur:
            break
        if min(norm_ts(x) or cutoff for x in r) < cutoff:
            break
    return [x for x in rows if str(F(x, "side", default="")).upper() in ("BUY", "SELL") and norm_ts(x) >= cutoff]

def parse_trades(addr, name, rows, now=None):
    now = time.time() if now is None else now
    cutoff = now - LIVE_HOURS * 3600
    out = []
    for x in rows or []:
        ts = norm_ts(x)
        side = str(F(x, "side", default="")).upper()
        if side not in ("BUY", "SELL") or not ts or ts < cutoff:
            continue
        if str(F(x, "type", default="TRADE")).upper() not in ("TRADE", ""):
            continue
        try:
            shares = float(F(x, "size", default=0) or 0)
            price = float(F(x, "price", default=0) or 0)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        usd = F(x, "usdc_size", "usdcSize")
        try:
            usd = float(usd) if usd is not None else shares * price
        except (TypeError, ValueError):
            usd = shares * price
        if usd < MIN_TRADE_USD:
            continue
        cid = F(x, "condition_id", "conditionId") or ""
        if not cid:
            continue
        outcome = F(x, "outcome") or ("Yes" if str(F(x, "outcome_index", "outcomeIndex")) == "0" else "No")
        out.append({
            "a": addr.lower(),
            "n": name or F(x, "name") or F(x, "pseudonym") or (addr[:6] + "…" + addr[-4:]),
            "avatar": F(x, "profile_image", "profileImage", "profile_image_optimized") or "",
            "cid": cid,
            "t": F(x, "title", "market_title", "question") or "Market",
            "slug": F(x, "slug", "market_slug") or "",
            "ev": F(x, "event_slug", "eventSlug") or "",
            "img": F(x, "icon", "image") or "",
            "side": side, "out": outcome, "shares": shares, "price": price, "usd": usd, "ts": ts,
        })
    return out

def pos_index(raw_by_addr):
    """addr -> condition -> outcome -> shares. Also a cid -> title/slug/icon fallback."""
    idx, meta, vals = {}, {}, {}
    for addr, rows in (raw_by_addr or {}).items():
        addr = addr.lower()
        for p in rows or []:
            if F(p, "redeemable") in (True, "True", "true", 1):
                continue
            try:
                sh = float(F(p, "size", "current_size", default=0) or 0)
            except (TypeError, ValueError):
                continue
            if sh <= 0.01:
                continue
            cid = F(p, "conditionId", "condition_id")
            if not cid:
                continue
            out = F(p, "outcome") or ("Yes" if str(F(p, "outcome_index", "outcomeIndex")) == "0" else "No")
            slot = idx.setdefault(addr, {}).setdefault(cid, {})
            slot[out] = slot.get(out, 0.0) + sh
            try:
                cv = F(p, "currentValue", "current_value")
                cv = float(cv) if cv is not None else sh * float(F(p, "curPrice", "current_price", "cur_price", default=0) or 0)
            except (TypeError, ValueError):
                cv = 0.0
            vslot = vals.setdefault(addr, {}).setdefault(cid, {})
            vslot[out] = vslot.get(out, 0.0) + cv
            m = meta.setdefault(cid, {"t": "", "slug": "", "ev": "", "img": ""})
            m["t"] = m["t"] or F(p, "title", default="") or ""
            m["slug"] = m["slug"] or F(p, "slug", default="") or ""
            m["ev"] = m["ev"] or F(p, "eventSlug", "event_slug", default="") or ""
            m["img"] = m["img"] or F(p, "icon", "image", default="") or ""
    return idx, meta, vals

def _holders(state):
    """One wallet on both outcomes is a hedge and is left out of the count."""
    h = {}
    for addr, sides in state.items():
        live = {o: sh for o, sh in sides.items() if sh > 0.01}
        if len(live) != 1:
            continue
        o = next(iter(live))
        h.setdefault(o, set()).add(addr)
    return h

def _summary(holders):
    if not holders:
        return {"n": 0, "cnt": 0, "top": None, "frac": 0.0}
    counts = {o: len(s) for o, s in holders.items()}
    top = max(counts, key=lambda o: (counts[o], o))
    n = sum(counts.values())
    return {"n": n, "cnt": counts[top], "top": top, "frac": counts[top] / n if n else 0.0}

def _arrow(before, now):
    if now["n"] == 0:
        return "↓" if before["n"] else ""
    if before["n"] == 0:
        return "↑"
    if before["top"] != now["top"]:
        return "↑" if now["frac"] >= before["frac"] else "↓"
    if abs(now["frac"] - before["frac"]) < 1e-9 and now["cnt"] == before["cnt"]:
        return ""
    if now["frac"] > before["frac"] + 1e-9 or (abs(now["frac"] - before["frac"]) < 1e-9 and now["cnt"] > before["cnt"]):
        return "↑"
    if now["frac"] < before["frac"] - 1e-9 or now["cnt"] < before["cnt"]:
        return "↓"
    return ""

def _chip(side, outcome, summary, addr, holders):
    if summary["n"] == 0:
        return "Exited", ""
    only = next(iter(next(iter(holders.values())))) if summary["n"] == 1 else None
    if summary["n"] == 1 and side == "BUY" and only == addr:
        return "First", ""
    supports = (side == "BUY" and outcome == summary["top"]) or (side == "SELL" and outcome != summary["top"])
    return ("With" if supports else "Against"), f"{summary['cnt']}/{summary['n']}"

def _held_peak(held, events):
    """Peak shares of this outcome in the window, so a partial sell shrinks the bar."""
    sh = held
    for t in reversed(events):
        sh += -t["shares"] if t["side"] == "BUY" else t["shares"]
        if sh < 0:
            sh = 0.0
    peak, cur = max(held, sh), sh
    for t in events:
        cur += t["shares"] if t["side"] == "BUY" else -t["shares"]
        if cur < 0:
            cur = 0.0
        if cur > peak:
            peak = cur
    return max(peak, held)

def build(trades, idx, meta=None, vals=None):
    meta = meta or {}
    vals = vals or {}
    by_cid = {}
    for t in trades:
        by_cid.setdefault(t["cid"], []).append(t)
    cons, arrows = {}, {}
    for cid, evs in by_cid.items():
        state = {}
        for addr, markets in idx.items():
            sides = {o: sh for o, sh in (markets.get(cid) or {}).items() if sh > 0.01}
            if sides:
                state[addr] = dict(sides)
        now_h = _holders(state)
        now = _summary(now_h)
        for t in sorted(evs, key=lambda z: z["ts"], reverse=True):
            sides = state.setdefault(t["a"], {})
            cur = sides.get(t["out"], 0.0)
            cur += -t["shares"] if t["side"] == "BUY" else t["shares"]
            if cur <= 0.01:
                sides.pop(t["out"], None)
            else:
                sides[t["out"]] = cur
            if not sides:
                state.pop(t["a"], None)
        before = _summary(_holders(state))
        cons[cid] = (now, now_h)
        arrows[cid] = _arrow(before, now)
    groups = []
    for t in sorted(trades, key=lambda z: (z["a"], z["cid"], z["side"], z["out"], z["ts"])):
        g = groups[-1] if groups else None
        if g and g["a"] == t["a"] and g["cid"] == t["cid"] and g["side"] == t["side"] and g["out"] == t["out"] and t["ts"] - g["ts"] <= FILL_GAP:
            g["fills"].append(t)
            g["ts"] = t["ts"]
        else:
            groups.append({"a": t["a"], "cid": t["cid"], "side": t["side"], "out": t["out"], "ts": t["ts"], "fills": [t]})
    ev_key = {}
    for t in trades:
        ev_key.setdefault((t["a"], t["cid"], t["out"]), []).append(t)
    for k in ev_key:
        ev_key[k].sort(key=lambda z: z["ts"])
    rows = []
    for g in groups:
        fills = sorted(g["fills"], key=lambda z: z["ts"])
        head = max(fills, key=lambda z: z["ts"])
        usd, shares = sum(f["usd"] for f in fills), sum(f["shares"] for f in fills)
        price = usd / shares if shares else head["price"]
        held = float((idx.get(g["a"], {}).get(g["cid"], {}) or {}).get(g["out"], 0.0) or 0.0)
        if held <= 0.01:
            held = 0.0
        held_usd = float((vals.get(g["a"], {}).get(g["cid"], {}) or {}).get(g["out"], 0.0) or 0.0) if held else 0.0
        peak = _held_peak(held, ev_key.get((g["a"], g["cid"], g["out"]), []))
        now, holders = cons.get(g["cid"], (_summary({}), {}))
        chip, split = _chip(g["side"], g["out"], now, g["a"], holders)
        title, slug, ev, img = head["t"], head["slug"], head["ev"], head["img"]
        fb = meta.get(g["cid"]) or {}
        if title == "Market":
            title = fb.get("t") or title
        slug = slug or fb.get("slug") or ""
        ev = ev or fb.get("ev") or ""
        img = img or fb.get("img") or ""
        rows.append({
            "n": head["n"], "avatar": head["avatar"] or "", "t": title, "url": market_url(slug, ev), "img": img or "",
            "cid": g["cid"], "slug": slug or "",
            "side": g["side"], "out": g["out"], "price": round(price, 4), "usd": round(usd, 2),
            "shares": round(shares, 2), "ts": head["ts"], "held": round(held, 2), "heldUsd": round(held_usd, 2), "peak": round(max(peak, held), 2),
            "chip": chip, "split": split, "arrow": arrows.get(g["cid"], ""),
            "fills": [{"ts": f["ts"], "usd": round(f["usd"], 2), "shares": round(f["shares"], 2), "price": round(f["price"], 4)} for f in fills] if len(fills) > 1 else [],
        })
    rows.sort(key=lambda r: -r["ts"])
    rows = [r for r in rows if r["t"] and r["t"] != "Market" and r["url"].startswith("https://polymarket.com/event/")]
    rows = rows[:max(1, LIVE_ROWS)]
    for i, r in enumerate(rows):
        r["id"] = i
    return rows

def publish(wallets, raw_by_addr, path=None, now=None):
    names, addrs = {}, []
    seen = set()
    for w in wallets:
        a = w["wallet"].lower()
        if w.get("name"):
            names.setdefault(a, w["name"])
        if a in seen:
            continue
        seen.add(a)
        addrs.append(a)
    print(f"live trades: {len(addrs)} wallets, last {LIVE_HOURS:g}h")
    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as ex:
        fetched = list(ex.map(lambda a: activity_pages(a, now=now), addrs))
    trades = []
    for addr, rows in zip(addrs, fetched):
        trades += parse_trades(addr, names.get(addr), rows, now=now)
    print(f"  activity rows priced >= ${MIN_TRADE_USD:g}: {len(trades)} in {time.time() - t0:.0f}s")
    idx, meta, vals = pos_index(raw_by_addr)
    rows = build(trades, idx, meta, vals)
    if not rows:
        print("live trades: no rows, keeping previous data/live.json")
        return 0
    path = path or os.path.join(HERE, "live.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    os.replace(tmp, path)
    s = rows[0]
    print(f"live trades: {len(rows)} -> {path}")
    print(f"  newest: {s['n']} {s['side']} {s['out']} ${s['usd']} · {s['chip']} {s['split']} {s['arrow']} · img={'yes' if s['img'] else 'no'} · {s['t'][:70]}")
    return len(rows)

def fetch_positions(addr):
    """Unfiltered v2 positions (dust included) so the held bar and consensus see every share."""
    out, cur = [], None
    for _ in range(20):
        q = {"user": addr, "limit": 500}
        if cur:
            q["cursor"] = cur
        d = get(V2 + "positions?" + urllib.parse.urlencode(q))
        if d is None:
            break
        rows, cur = rows_of(d)
        for x in rows or []:
            out.append(dict(
                conditionId=x.get("condition_id"), title=x.get("title") or "", slug=x.get("slug") or "",
                eventSlug=x.get("event_slug") or "", icon=x.get("icon") or "", outcome=x.get("outcome") or "",
                size=x.get("current_size") or 0, redeemable=x.get("redeemable"),
            ))
        if not cur or not rows:
            break
    return out

def main():
    W = json.load(open(os.path.join(HERE, "wallets.json"), encoding="utf-8"))
    print(f"positions for {len(W)} wallets", flush=True)
    done = {"n": 0}
    def one(w):
        rows = fetch_positions(w["wallet"])
        done["n"] += 1
        if done["n"] % 8 == 0 or done["n"] == len(W):
            print(f"  positions {done['n']}/{len(W)}", flush=True)
        return rows
    with cf.ThreadPoolExecutor(8) as ex:
        raw_rows = list(ex.map(one, W))
    raw = {w["wallet"].lower(): rows for w, rows in zip(W, raw_rows)}
    n = publish(W, raw)
    if not n:
        sys.exit("No recent trades came back from the Polymarket data API. data/live.json was NOT changed.")

if __name__ == "__main__":
    main()
