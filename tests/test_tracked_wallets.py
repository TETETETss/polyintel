"""Tracked-wallet invariants for data/wallets.json.

Duplicates are the same on-chain address after lowercasing, including when an
entry stores a username that resolves to that address.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WALLETS = ROOT / "data" / "wallets.json"
ADDR = re.compile(r"0x[0-9a-fA-F]{40}$")

# Live gamma public-profile name + proxyWallet, checked 2026-11-07.
# Lolakis was already tracked; the other five were not.
REQUESTED = {
    "0x154794795d978c5890b3f69264311f0bd966d066": "PMTraderAdam",
    "0x9ad091ca2e8f1bd69f27662edcb49dceeaa5bf3d": "PaddyAlpha",
    "0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9": "Lolakis",
    "0xc004b035b67be284e0d1db56c39e865df6cac095": "lamyk",
    "0x0787a58e205a70320db638113fe8da18c8800ca3": "melonmanm",
    "0xc4c46d8e1f58c360c4607de7f70f89880f9c393d": "Martinus-",
}
ALREADY_TRACKED = {
    "0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9": "Lolakis",
}
BEFORE_DISTINCT = 36


def canonical_address(wallet, username_to_address=None):
    """Return the lowercase 0x address for an address or a known username."""
    raw = wallet.strip()
    if ADDR.fullmatch(raw):
        return raw.lower()
    aliases = username_to_address or {}
    if raw not in aliases and raw.lower() not in aliases:
        raise KeyError(raw)
    resolved = aliases.get(raw, aliases.get(raw.lower()))
    if not ADDR.fullmatch(resolved.strip()):
        raise ValueError(resolved)
    return resolved.strip().lower()


def index_wallets(entries, username_to_address=None):
    """Map canonical address -> entry. Raise if two entries share an address."""
    by_addr = {}
    for entry in entries:
        addr = canonical_address(entry["wallet"], username_to_address)
        if addr in by_addr:
            prev = by_addr[addr]
            raise AssertionError(
                f"duplicate address {addr}: {prev['name']!r} and {entry['name']!r}"
            )
        by_addr[addr] = entry
    return by_addr


class TrackedWalletsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads(WALLETS.read_text())
        cls.by_addr = index_wallets(cls.entries)

    def test_requested_profiles_present_once(self):
        for addr, name in REQUESTED.items():
            self.assertIn(addr, self.by_addr)
            self.assertEqual(self.by_addr[addr]["name"], name)
            self.assertEqual(self.by_addr[addr]["wallet"], addr)

    def test_lolakis_not_duplicated(self):
        lolakis = [
            e for e in self.entries
            if canonical_address(e["wallet"]) == "0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9"
            or e["name"].lower() == "lolakis"
        ]
        self.assertEqual(lolakis, [{
            "name": "Lolakis",
            "wallet": "0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9",
        }])

    def test_distinct_count_before_and_after(self):
        added = set(REQUESTED) - set(ALREADY_TRACKED)
        self.assertEqual(len(added), 5)
        self.assertEqual(len(self.entries), BEFORE_DISTINCT + len(added))
        self.assertEqual(len(self.by_addr), BEFORE_DISTINCT + len(added))
        self.assertEqual(len(self.by_addr), 41)

    def test_existing_entries_are_addresses_not_usernames(self):
        for entry in self.entries:
            self.assertRegex(entry["wallet"], ADDR)
            self.assertEqual(entry["wallet"], entry["wallet"].lower())
            self.assertTrue(entry["name"])

    def test_names_unique(self):
        names = [e["name"] for e in self.entries]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len({n.lower() for n in names}), len(names))

    def test_username_and_casing_count_as_same_address(self):
        entries = [
            {"name": "Lolakis", "wallet": "lolakis"},
            {"name": "lolakis-copy", "wallet": "0x401EE31E9EBF9AB9F6315CD95FACA5F950436FC9"},
            {"name": "PMTraderAdam", "wallet": "0x154794795d978c5890b3f69264311f0bd966d066"},
        ]
        aliases = {"lolakis": "0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9"}
        with self.assertRaises(AssertionError) as caught:
            index_wallets(entries, aliases)
        self.assertIn("0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9", str(caught.exception))
        kept = entries[:1] + entries[2:]
        indexed = index_wallets(kept, aliases)
        self.assertEqual(len(indexed), 2)
        self.assertEqual(indexed["0x401ee31e9ebf9ab9f6315cd95faca5f950436fc9"]["name"], "Lolakis")

    def test_consumers_read_wallets_for_aggregation_and_pnl(self):
        refresh = (ROOT / "data" / "refresh.py").read_text()
        traders = (ROOT / "mktraders.py").read_text()
        build = (ROOT / "build.py").read_text()
        enrich = (ROOT / "data" / "enrich.py").read_text()
        snapshot = (ROOT / "scripts" / "snapshot_midterms.py").read_text()
        workflow = (ROOT / ".github" / "workflows" / "refresh.yml").read_text()

        self.assertIn('open(f"{D}/wallets.json")', refresh)
        self.assertIn("w['wallet']", refresh)
        self.assertIn("/v2/positions?user=", refresh)

        self.assertIn("data/wallets.json", traders)
        self.assertIn("w['wallet']", traders)
        self.assertIn("/v2/user-pnl?user=", traders)
        self.assertIn("traders.json", traders)

        self.assertIn("data/wallets.json", build)
        self.assertIn("{{NTRADERS}}", build)
        self.assertIn("traders.json", build)

        self.assertIn("wallets.json", enrich)
        self.assertIn("w['wallet']", enrich)
        self.assertIn("wallets.json", snapshot)
        self.assertIn("w['wallet']", snapshot)
        self.assertIn("/v2/positions?user=", snapshot)

        self.assertIn("python3 data/refresh.py", workflow)
        self.assertIn("python3 mktraders.py", workflow)
        self.assertIn("python3 build.py", workflow)


if __name__ == "__main__":
    unittest.main()
