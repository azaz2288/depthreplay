import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.report import HEADER, analyze, render


class ResearchTests(unittest.TestCase):
    def dataset(self, n=200):
        rows = [",".join(HEADER)]
        for i in range(n):
            rows.append(
                f"{i + 1},{i * 10},{100 + i % 5},{110 + i % 5},{10 + i % 7},20,100,200,10"
            )
        return "\n".join(rows).encode()

    def test_chronological_purge_and_reproducibility(self):
        a = analyze(self.dataset(), 100)
        self.assertGreater(a["purged"], 0)
        self.assertEqual(a, analyze(self.dataset(), 100))
        self.assertIn("snapshot_sha256", a)
        self.assertIn("不是资金曲线", render(a))

    def test_future_changes_do_not_change_training_fit(self):
        raw = self.dataset()
        a = analyze(raw, 100)
        lines = raw.decode().splitlines()
        for i in range(160, 200):
            fields = lines[i + 1].split(",")
            fields[2] = str(int(fields[2]) + 50)
            fields[3] = str(int(fields[3]) + 50)
            lines[i + 1] = ",".join(fields)
        b = analyze("\n".join(lines).encode(), 100)
        self.assertEqual(a["model"], b["model"])

    def test_bad_invariants_refused(self):
        raw = self.dataset().replace(b"1,0,100,110", b"1,0,110,100")
        with self.assertRaisesRegex(ValueError, "invariant"):
            analyze(raw)

    def test_insufficient_and_nonpositive_horizon(self):
        with self.assertRaises(ValueError):
            analyze(self.dataset(10))
        with self.assertRaises(ValueError):
            analyze(self.dataset(), 0)
