"""Live Trades feed: v2 activity rows become the table polyintel renders."""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
import live_trades as lt

NOW = 1_700_000_000
CID = "0xabc"


def trade(addr, side, outcome, shares, ts, usd=None, title="Will it happen?", **kw):
    row = {
        "a": addr, "n": kw.get("n", addr), "avatar": kw.get("avatar", ""),
        "cid": kw.get("cid", CID), "t": title, "slug": kw.get("slug", "will-it"),
        "ev": kw.get("ev", "will-it-event"), "img": kw.get("img", "https://cdn.example/m.png"),
        "side": side, "out": outcome, "shares": shares, "price": (usd or shares) / shares,
        "usd": usd if usd is not None else float(shares), "ts": ts,
    }
    return row


class LiveTradesTest(unittest.TestCase):
    def test_against_consensus_and_down_arrow(self):
        # 6 wallets hold No, one buys Yes and is now the only Yes holder: Against 6/7 ↓
        yes = "0x" + "a" * 40
        nos = ["0x" + f"{i:040x}" for i in range(6)]
        idx = {yes: {CID: {"Yes": 100.0}}}
        for a in nos:
            idx[a] = {CID: {"No": 10.0}}
        rows = lt.build([trade(yes, "BUY", "Yes", 100, NOW, usd=40, n="Ada")], idx)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["chip"], "Against")
        self.assertEqual(r["split"], "6/7")
        self.assertEqual(r["arrow"], "↓")
        self.assertEqual(r["side"], "BUY")
        self.assertEqual(r["out"], "Yes")
        self.assertEqual(r["held"], 100)
        self.assertGreaterEqual(r["peak"], r["held"])
        self.assertTrue(r["url"].startswith("https://polymarket.com/event/"))
        self.assertEqual(r["img"], "https://cdn.example/m.png")
        self.assertEqual(r["t"], "Will it happen?")
        self.assertEqual(r["cid"], CID)
        self.assertEqual(r["slug"], "will-it")
        self.assertEqual(r["heldUsd"], 0)

    def test_holding_value_comes_from_current_position(self):
        a = "0x" + "b" * 40
        idx = {a: {CID: {"No": 5000.0}}}
        vals = {a: {CID: {"No": 3500.5}}}
        row = lt.build([trade(a, "BUY", "No", 10, NOW, usd=8, n="Bea")], idx, None, vals)[0]
        self.assertEqual(row["held"], 5000)
        self.assertEqual(row["heldUsd"], 3500.5)
        self.assertEqual(row["out"], "No")

    def test_inflows_keep_positive_nets_over_2000(self):
        cid = "0x" + "ab" * 32
        trades = [
            {"cid": cid, "side": "BUY", "out": "Yes", "usd": 3000, "price": 0.4, "name": "Ada", "avatar": "", "t": "Will it happen?", "slug": "will-it", "ev": "ev", "img": "i.png", "ts": 10},
            {"cid": cid, "side": "SELL", "out": "Yes", "usd": 500, "price": 0.5, "name": "Ada", "avatar": "a.png", "t": "Will it happen?", "slug": "will-it", "ev": "ev", "img": "i.png", "ts": 20},
            {"cid": cid, "side": "BUY", "out": "No", "usd": 100, "price": 0.6, "name": "Bea", "avatar": "", "t": "Will it happen?", "slug": "will-it", "ev": "ev", "img": "i.png", "ts": 15},
            {"cid": "0xsmall", "side": "BUY", "out": "Yes", "usd": 1500, "price": 0.2, "name": "Cy", "avatar": "", "t": "Small market", "slug": "small", "ev": "small", "img": "", "ts": 5},
        ]
        rows = lt.aggregate_inflows(trades)
        self.assertEqual([r["t"] for r in rows], ["Will it happen?"])
        self.assertEqual(rows[0]["yes"], 2500)
        self.assertEqual(rows[0]["no"], 100)
        self.assertEqual([(t["n"], t["out"], t["usd"]) for t in rows[0]["tr"]], [("Ada", "Yes", 2500), ("Bea", "No", 100)])
        # Buy 3000 at 40c is 7,500 shares; the 500 sell at 50c comes off the net, not the avg buy.
        self.assertEqual(rows[0]["tr"][0]["sh"], 6500)
        self.assertEqual(rows[0]["tr"][0]["avg"], 0.4)
        self.assertEqual(rows[0]["ysh"], 6500)
        self.assertEqual(rows[0]["yavg"], 0.4)
        self.assertEqual(rows[0]["nsh"], 166.67)
        self.assertEqual(rows[0]["navg"], 0.6)
        self.assertEqual(rows[0]["px"], 0.5)
        self.assertTrue(rows[0]["url"].startswith("https://polymarket.com/event/"))
        # A sell at 95c still counts against an inflow. That filter is outflows only.
        pricey = list(trades) + [{"cid": cid, "side": "SELL", "out": "Yes", "usd": 200, "price": 0.99, "name": "Ada", "avatar": "", "t": "Will it happen?", "slug": "will-it", "ev": "ev", "img": "i.png", "ts": 30}]
        self.assertEqual(lt.aggregate_inflows(pricey)[0]["yes"], 2300)
        sized = [dict(trades[0], sh=12400, usd=5332)]
        sized[0]["t"] = "Will it happen?"
        one = lt.aggregate_inflows(sized)[0]
        self.assertEqual(one["tr"][0]["sh"], 12400)
        self.assertEqual(one["tr"][0]["avg"], round(5332 / 12400, 4))
        self.assertEqual(one["ysh"], 12400)

    def test_outflows_skip_95c_sells_and_redemptions(self):
        cid = "0x" + "cd" * 32
        ada, bea = "0x" + "aa" * 20, "0x" + "bb" * 20
        base = {"cid": cid, "t": "Will it happen?", "slug": "will-it", "ev": "ev", "img": "", "avatar": ""}
        trades = [
            dict(base, side="SELL", out="Yes", usd=3000, price=0.5, name="Ada", addr=ada, ts=10),
            dict(base, side="SELL", out="Yes", usd=4000, price=0.95, name="Ada", addr=ada, ts=11),
            dict(base, side="SELL", out="No", usd=900, price=0.4, name="Bea", addr=bea, ts=12, redeem=True),
            dict(base, side="BUY", out="Yes", usd=8000, price=0.3, name="Cy", addr="0x" + "cc" * 20, ts=13),
            dict(base, side="SELL", out="No", usd=700, price=0.2, name="Bea", addr=bea, ts=14),
            dict(base, side="SELL", out="Yes", usd=500, price=0.949, name="Ada", addr=ada, ts=15),
            {"cid": "0xsmall", "side": "SELL", "out": "Yes", "usd": 1500, "price": 0.2, "name": "Cy", "addr": "0x" + "cc" * 20, "t": "Small market", "slug": "small", "ev": "small", "img": "", "ts": 5},
        ]
        held = {ada: {cid: {"Yes": 12.0}}}
        rows = lt.aggregate_outflows(trades, held)
        self.assertEqual([r["t"] for r in rows], ["Will it happen?"])
        self.assertEqual(rows[0]["yes"], 3500)
        self.assertEqual(rows[0]["no"], 700)
        by = {(t["n"], t["out"]): t for t in rows[0]["tr"]}
        self.assertFalse(by[("Ada", "Yes")]["exited"])
        self.assertTrue(by[("Bea", "No")]["exited"])
        # 3,000 at 50c is 6,000 shares; the 500 at 94.9c counts, the 95c sell does not.
        self.assertEqual(by[("Ada", "Yes")]["sh"], 6526.87)
        self.assertEqual(by[("Ada", "Yes")]["avg"], 0.5362)
        self.assertEqual(rows[0]["ysh"], 6526.87)
        self.assertEqual(rows[0]["yavg"], 0.5362)
        self.assertEqual(by[("Bea", "No")]["sh"], 3500)
        self.assertEqual(by[("Bea", "No")]["avg"], 0.2)

    def test_with_first_and_exited(self):
        a, b = "0x" + "1" * 40, "0x" + "2" * 40
        idx = {a: {CID: {"Yes": 50.0}}, b: {CID: {"Yes": 20.0}}}
        with_row = lt.build([trade(a, "BUY", "Yes", 5, NOW, n="Ann")], idx)[0]
        self.assertEqual(with_row["chip"], "With")
        self.assertEqual(with_row["split"], "2/2")
        first = lt.build([trade(a, "BUY", "Yes", 50, NOW, n="Ann")], {a: {CID: {"Yes": 50.0}}})[0]
        self.assertEqual(first["chip"], "First")
        self.assertEqual(first["split"], "")
        # Sold the whole position and nobody else holds it.
        exited = lt.build([trade(a, "SELL", "Yes", 50, NOW, n="Ann")], {})[0]
        self.assertEqual(exited["chip"], "Exited")
        self.assertEqual(exited["held"], 0)

    def test_groups_fills_and_keeps_newest_120(self):
        a = "0x" + "3" * 40
        burst = [trade(a, "BUY", "Yes", 2, NOW + i, usd=2, n="Bea") for i in (0, 30, 90)]
        far = [trade(a, "SELL", "No", 4, NOW + 1000, usd=3, n="Bea", cid="0xother", slug="other", ev="other-ev", title="Other market")]
        idx = {a: {CID: {"Yes": 6.0}}}
        rows = lt.build(burst + far, idx)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["t"], "Other market")
        grouped = rows[1]
        self.assertEqual(grouped["shares"], 6)
        self.assertEqual(len(grouped["fills"]), 3)
        self.assertEqual(grouped["usd"], 6)
        many = [trade(a, "BUY", "Yes", 1, NOW - i * 1000, usd=2, n="Bea", cid=f"0x{i:064x}", slug=f"m{i}", ev=f"e{i}", title=f"Market {i}") for i in range(150)]
        capped = lt.build(many, {})
        self.assertEqual(len(capped), 120)
        self.assertGreater(capped[0]["ts"], capped[-1]["ts"])

    def test_parse_v2_activity_shape(self):
        addr = "0x6bab41a0dc40d6dd4c1a915b8c01969479fd1292"
        raw = {
            "timestamp": NOW, "condition_id": CID, "type": "TRADE", "size": 10, "usdc_size": 7,
            "price": 0.7, "side": "BUY", "outcome_index": 0, "outcome": "Yes",
            "title": "Will the bill pass?", "slug": "bill", "event_slug": "bill",
            "icon": "https://polymarket-upload.s3.us-east-2.amazonaws.com/bill.png",
            "name": "SomeoneElse", "profile_image": "https://cdn.example/a.jpg",
        }
        dust = dict(raw, usdc_size=0.4, size=1, timestamp=NOW - 10)
        old = dict(raw, timestamp=NOW - int(lt.LIVE_HOURS * 3600) - 5)
        parsed = lt.parse_trades(addr, "Dropper", [raw, dust, old], now=NOW)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["n"], "Dropper")
        self.assertEqual(parsed[0]["img"], raw["icon"])
        self.assertEqual(parsed[0]["avatar"], raw["profile_image"])
        self.assertEqual(parsed[0]["usd"], 7)
        self.assertNotIn("/v1/", lt.V2)

    def test_partial_sell_shrinks_held_bar(self):
        a = "0x" + "4" * 40
        idx = {a: {CID: {"Yes": 40.0}}}
        row = lt.build([trade(a, "SELL", "Yes", 60, NOW, usd=30, n="Cy")], idx)[0]
        self.assertEqual(row["held"], 40)
        self.assertEqual(row["peak"], 100)
        self.assertLess(row["held"], row["peak"])

    def test_template_adds_live_trades_without_dropping_pages(self):
        html = (ROOT / "tpl.html").read_text(encoding="utf-8")
        self.assertIn('data-v="live"', html)
        self.assertIn(">Live Trades</a>", html)
        self.assertIn('id="v-live"', html)
        self.assertIn(">Markets</a>", html)
        self.assertIn(">Bookmarked", html)
        self.assertIn("function liveRender", html)
        self.assertIn(">Traders</a>", html)
        self.assertIn(">How to use</a>", html)
        self.assertIn("AI Model Analysis", html)
        self.assertIn('id="v-markets"', html)
        self.assertIn('id="v-tips"', html)
        self.assertIn('id="v-traders"', html)
        self.assertIn("__LIVE__", html)
        self.assertIn("__NLIVE__", html)
        self.assertIn('data-v="inflows"', html)
        self.assertIn(">Money Flow</a>", html)
        self.assertIn('id="v-inflows"', html)
        self.assertIn('id="iflist"', html)
        self.assertIn("function ifMode", html)
        self.assertIn("BIGGEST EXIT", html)
        self.assertIn("Sold · 24h", html)
        self.assertIn("Open market ↗", html)
        self.assertIn("function ifSh", html)
        self.assertIn('class="who"', html)
        self.assertIn('class="sub"', html)
        self.assertIn('class="if-sh"', html)
        self.assertIn("shares · avg", html)
        self.assertIn("#v-inflows .if-row .sub{display:block;margin:0;line-height:normal", html)
        self.assertIn("#v-inflows .if-sh .y,#v-inflows .if-sh .n{white-space:nowrap", html)
        self.assertIn("m.ysh", html)
        self.assertIn("Mostly sold ", html)
        self.assertIn("__INFLOW__", html)
        self.assertNotIn(">Top Inflows</a>", html)
        self.assertIn("const V='programs'", html)
        self.assertIn("https://polymarket.com?via=programs", html)
        self.assertNotIn("via=brams", html)
        self.assertNotIn("poly.market/brams", html)
        # markets search and how-to image stay put
        self.assertIn('id="q"', html)
        self.assertIn("read-a-market-card.webp", html)
        self.assertEqual(html.count('id="v-markets"'), 1)
        self.assertEqual(html.count('id="v-tips"'), 1)

    def test_build_injects_live_tokens_and_refresh_keeps_v2_positions(self):
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        refresh = (ROOT / "data" / "refresh.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "refresh.yml").read_text(encoding="utf-8")
        self.assertIn("__LIVE__", build)
        self.assertIn("__NLIVE__", build)
        self.assertIn("__INFLOW__", build)
        self.assertIn("publish_inflows", refresh)
        self.assertIn("data/live.json", build)
        self.assertIn("live_trades.publish", refresh)
        self.assertIn("/v2/positions?user=", refresh)
        self.assertIn('open(f"{D}/wallets.json")', refresh)
        self.assertNotIn("/v1/", refresh)
        self.assertNotIn("/v1/", build)
        # the 10-minute job is unchanged: refresh still runs, then build
        self.assertIn("python3 data/refresh.py", workflow)
        self.assertIn("python3 build.py", workflow)
        self.assertIn("*/10 * * * *", workflow)


if __name__ == "__main__":
    unittest.main()
