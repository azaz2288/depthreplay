"""Original valid maker-event stream, not a captured exchange feed."""

import argparse
import csv
import random
from pathlib import Path


def generate(path, count=10000, seed=19):
    rng = random.Random(seed)
    orders = {}
    next_id = 0
    seq = 0
    rows = []

    def add(side, price, qty):
        nonlocal next_id, seq
        next_id += 1
        seq += 1
        orders[next_id] = (side, price, qty)
        rows.append([seq, seq * 10, "A", next_id, side, price, qty])

    for _ in range(count):
        bids = [p for s, p, q in orders.values() if s == "B"]
        asks = [p for s, p, q in orders.values() if s == "S"]
        if len(orders) < 4 or rng.random() < 0.6:
            side = rng.choice("BS")
            price = (
                10000 - rng.randrange(1, 12)
                if side == "B"
                else 10000 + rng.randrange(1, 12)
            )
            add(side, price, rng.randrange(1, 100))
        elif rng.random() < 0.5:
            id = rng.choice(list(orders))
            seq += 1
            rows.append([seq, seq * 10, "C", id, "N", 0, 0])
            del orders[id]
        else:
            side = rng.choice("BS")
            levels = bids if side == "B" else asks
            if not levels:
                add(side, 9999 if side == "B" else 10001, 10)
                continue
            best = max(levels) if side == "B" else min(levels)
            eligible = [
                id for id, (s, p, q) in orders.items() if s == side and p == best
            ]
            id = rng.choice(eligible)
            s, p, q = orders[id]
            qty = rng.randint(1, q)
            seq += 1
            rows.append([seq, seq * 10, "T", id, s, p, qty])
            if qty == q:
                del orders[id]
            else:
                orders[id] = (s, p, q - qty)
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["seq", "time_ms", "action", "order_id", "side", "price_ticks", "quantity"]
        )
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.count <= 100000:
        parser.error("Count must be 1–100000")
    generate(args.output, args.count)
