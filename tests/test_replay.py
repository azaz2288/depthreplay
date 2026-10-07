import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.generate_demo import generate


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = Path(
            os.environ.get(
                "DEPTHREPLAY_EXE",
                "build/depthreplay.exe" if os.name == "nt" else "build/depthreplay",
            )
        ).resolve()
        self.assertTrue(self.exe.is_file(), "Compile C++ executable before tests")

    def invoke(self, rows):
        source = self.root / "events.csv"
        output = self.root / "snapshots.csv"
        with source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "seq",
                    "time_ms",
                    "action",
                    "order_id",
                    "side",
                    "price_ticks",
                    "quantity",
                ]
            )
            writer.writerows(rows)
        result = subprocess.run(
            [str(self.exe), str(source), str(output)], capture_output=True, text=True
        )
        return result, output

    def test_random_independent_reference_every_snapshot(self):
        source = self.root / "random.csv"
        rows = generate(source, 5000)
        output = self.root / "snapshots.csv"
        result = subprocess.run(
            [str(self.exe), str(source), str(output)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        orders = {}
        expected = []
        for seq, time, action, id, side, price, qty in rows:
            if action == "A":
                orders[id] = [side, price, qty]
            elif action == "C":
                del orders[id]
            else:
                orders[id][2] -= qty
                if not orders[id][2]:
                    del orders[id]
            # Independent full rebuild, no incremental aggregate map.
            bids = {}
            asks = {}
            for s, p, q in orders.values():
                levels = bids if s == "B" else asks
                levels[p] = levels.get(p, 0) + q
            bid = max(bids, default=0)
            ask = min(asks, default=0)
            expected.append(
                [
                    seq,
                    time,
                    bid,
                    ask,
                    bids.get(bid, 0),
                    asks.get(ask, 0),
                    sum(bids[p] for p in sorted(bids, reverse=True)[:5]),
                    sum(asks[p] for p in sorted(asks)[:5]),
                    len(orders),
                ]
            )
        with output.open() as stream:
            actual = [[int(v) for v in row.values()] for row in csv.DictReader(stream)]
        self.assertEqual(actual, expected)

    def test_partial_trade_cancel_exact_aggregates(self):
        result, output = self.invoke(
            [
                [1, 0, "A", 1, "B", 100, 10],
                [2, 1, "A", 2, "B", 100, 20],
                [3, 2, "T", 1, "B", 100, 4],
                [4, 3, "C", 2, "N", 0, 0],
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with output.open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["bid_qty"] for r in rows], ["10", "30", "26", "6"])

    def test_invalid_streams_leave_no_output(self):
        cases = [
            [[2, 0, "A", 1, "B", 100, 10]],
            [[1, 0, "C", 9, "N", 0, 0]],
            [[1, 0, "A", 1, "B", 100, 0]],
            [[1, 0, "A", 1, "B", 100, 2], [2, 1, "A", 1, "B", 99, 2]],
            [[1, 2, "A", 1, "B", 100, 2], [2, 1, "A", 2, "B", 99, 2]],
            [[1, 0, "A", 1, "B", 100, 2], [2, 1, "T", 1, "B", 100, 3]],
            [[1, 0, "A", 1, "B", 100, 2], [2, 1, "A", 2, "S", 100, 2]],
            [
                [1, 0, "A", 1, "B", 100, 2],
                [2, 1, "A", 2, "B", 99, 2],
                [3, 2, "T", 2, "B", 99, 1],
            ],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                result, output = self.invoke(rows)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(output.exists())
                self.assertEqual(list(self.root.glob("*.tmp-*")), [])

    def test_output_not_overwritten(self):
        output = self.root / "snapshots.csv"
        output.write_text("keep")
        result, _ = self.invoke([[1, 0, "A", 1, "B", 100, 1]])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output.read_text(), "keep")

    def test_empty_side_and_huge_integer(self):
        result, output = self.invoke(
            [[1, 0, "A", 1, "S", 101, 1], [2, 1, "C", 1, "N", 0, 0]]
        )
        self.assertEqual(result.returncode, 0)
        output.unlink()  # only this test's own temporary output
        result, output = self.invoke(
            [[1, 0, "A", 1, "B", "999999999999999999999999", 1]]
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
