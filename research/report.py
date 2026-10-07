"""Descriptive depth analysis and chronological holdout; no trading simulation."""

import argparse
import bisect
import csv
import hashlib
import html
import io
import json
import random
import statistics
from pathlib import Path

HEADER = [
    "seq",
    "time_ms",
    "bid_ticks",
    "ask_ticks",
    "bid_qty",
    "ask_qty",
    "bid_top5",
    "ask_top5",
    "open_orders",
]


def analyze(raw, horizon_ms=100):
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("Snapshot budget: 128 MiB")
    if type(horizon_ms) is not int or not 1 <= horizon_ms <= 86400000:
        raise ValueError("Horizon: 1..86400000 ms")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    if reader.fieldnames != HEADER:
        raise ValueError("Unexpected snapshot schema")
    rows = []
    previous = -1
    for row in reader:
        if len(rows) >= 1000000 or None in row:
            raise ValueError("Snapshot row budget/schema")
        try:
            values = [int(row[k]) for k in HEADER]
        except (TypeError, ValueError) as exc:
            raise ValueError("Snapshot integer required") from exc
        seq, time, bid, ask, bq, aq, b5, a5, orders = values
        if (
            seq != len(rows) + 1
            or time < previous
            or min(values) < 0
            or max(values) > 2**63 - 1
        ):
            raise ValueError("Sequence, timestamp or integer range violation")
        if (
            (bid == 0) != (bq == 0)
            or (ask == 0) != (aq == 0)
            or (bid and ask and bid >= ask)
            or b5 < bq
            or a5 < aq
        ):
            raise ValueError("Invalid book invariant")
        previous = time
        rows.append(values)
    if not rows:
        raise ValueError("No snapshots")
    valid = [r for r in rows if r[2] and r[3]]
    times = [r[1] for r in valid]
    mid = [(r[2] + r[3]) / 2 for r in valid]
    spreads = [r[3] - r[2] for r in valid]
    observations = []
    for i, row in enumerate(valid):
        future = bisect.bisect_left(times, row[1] + horizon_ms)
        if future < len(valid):
            imbalance = (row[4] - row[5]) / (row[4] + row[5])
            observations.append(
                (row[1], times[future], imbalance, mid[future] - mid[i])
            )
    if len(observations) < 40:
        raise ValueError("Need at least 40 two-sided, horizon-complete observations")
    cut = int(len(observations) * 0.7)
    boundary = observations[cut][0]
    train = [r for r in observations[:cut] if r[1] < boundary]
    test = [r for r in observations[cut:] if r[0] >= boundary]
    if len(train) < 20 or len(test) < 10:
        raise ValueError("Insufficient purged chronological train/test data")
    mean_x = statistics.mean(r[2] for r in train)
    mean_y = statistics.mean(r[3] for r in train)
    variance = sum((r[2] - mean_x) ** 2 for r in train)
    beta = sum((r[2] - mean_x) * (r[3] - mean_y) for r in train) / (variance + 1.0)
    pred = [mean_y + beta * (r[2] - mean_x) for r in test]
    losses = [abs(p - r[3]) - abs(mean_y - r[3]) for p, r in zip(pred, test)]
    rng = random.Random(19)
    block = min(20, len(test))
    means = []
    for _ in range(500):
        sample = []
        while len(sample) < len(losses):
            start = rng.randrange(len(losses))
            sample.extend(losses[(start + j) % len(losses)] for j in range(block))
        means.append(statistics.mean(sample[: len(losses)]))
    means.sort()
    points = [
        {
            "time_ms": r[1],
            "mid_ticks": (r[2] + r[3]) / 2,
            "spread_ticks": r[3] - r[2],
            "imbalance": (r[4] - r[5]) / (r[4] + r[5]),
        }
        for r in valid[:: max(1, len(valid) // 250)]
    ]
    return {
        "schema": 1,
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "events": len(rows),
        "two_sided": len(valid),
        "spread": {
            "mean_ticks": statistics.mean(spreads),
            "median_ticks": statistics.median(spreads),
            "max_ticks": max(spreads),
        },
        "horizon_ms": horizon_ms,
        "train": len(train),
        "test": len(test),
        "purged": cut - len(train),
        "test_start_ms": boundary,
        "model": {
            "feature": "best-level size imbalance",
            "train_mean_x": mean_x,
            "train_mean_y": mean_y,
            "ridge_beta": beta,
            "alpha": 1.0,
        },
        "holdout": {
            "mae": statistics.mean(abs(p - r[3]) for p, r in zip(pred, test)),
            "baseline_mae": statistics.mean(abs(mean_y - r[3]) for r in test),
            "mean_mae_delta": statistics.mean(losses),
            "moving_block_delta95": [means[12], means[487]],
            "block_size": block,
            "bootstrap_seed": 19,
            "bootstrap_reps": 500,
        },
        "series": points,
        "warnings": [
            "Demo feed is original synthetic maker events, not exchange data or profit evidence.",
            "Overlapping horizons are dependent. Block interval is descriptive; it does not correct model selection or repeated experiments.",
            "Only A/C/T normalized events, fixed integer ticks and best-price maker execution are supported. Queue priority, hidden liquidity, exchange recovery and fees are not modeled.",
            "No order submission, portfolio simulation or investment recommendation.",
        ],
    }


def render(report):
    points = report["series"]
    values = [p["mid_ticks"] for p in points]
    lo = min(values)
    hi = max(values)
    span = max(1, hi - lo)
    poly = " ".join(
        f"{40 + i * 900 / max(1, len(values) - 1):.1f},{220 - (v - lo) / span * 160:.1f}"
        for i, v in enumerate(values)
    )
    cards = [
        ("事件数", report["events"]),
        ("平均价差", f"{report['spread']['mean_ticks']:.2f} ticks"),
        ("训练 / 留出", f"{report['train']} / {report['test']}"),
        ("清除跨界标签", report["purged"]),
    ]
    metrics = "".join(
        f"<article><strong>{html.escape(str(value))}</strong><span>{label}</span></article>"
        for label, value in cards
    )
    warnings = "".join("<li>" + html.escape(w) + "</li>" for w in report["warnings"])
    holdout = report["holdout"]
    details = html.escape(
        json.dumps(
            {k: v for k, v in report.items() if k != "series"},
            indent=2,
            ensure_ascii=False,
        )
    )
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DepthReplay研究报告</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f5f1e9;color:#263936;font:15px "Segoe UI",sans-serif}}main{{max-width:1100px;padding:40px 22px;margin:auto}}header{{letter-spacing:.12em;color:#54716a}}h1{{font-size:46px}}p,li{{line-height:1.9;color:#65756e}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}}article,section{{background:#fff;border:1px solid #d9ddd2;border-radius:12px;padding:24px;margin-bottom:20px}}article strong{{display:block;font-size:28px}}article span{{font-size:13px;color:#6e8175}}svg{{width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}@media(max-width:650px){{.cards{{grid-template-columns:1fr 1fr}}h1{{font-size:31px}}}}
    </style><main><header>DEPTHREPLAY / C++20 × PYTHON</header><h1>盘口重建，研究先验真。</h1><p>这是原创合成事件的可复核演示。C++逐事件重建深度，Python按真实时间跨度生成标签并清除训练/测试边界泄漏。</p><div class="cards">{metrics}</div><section><h2>中间价观察（ticks）</h2><svg viewBox="0 0 980 260" role="img" aria-label="按时间顺序的中间价曲线"><path d="M40 220H940M40 40V220" fill="none" stroke="#c5cec4"/><polyline points="{poly}" fill="none" stroke="#2d796c" stroke-width="2"/></svg><p>展示抽样快照，纵轴范围 {lo}–{hi} ticks；不是资金曲线。</p></section><section><h2>时间留出评估</h2><p>特征：当前最优档数量不平衡。目标：{report["horizon_ms"]} ms后首个可观测中间价变化。训练参数仅从训练段拟合。</p><p>模型MAE：{holdout["mae"]:.6f} ticks；训练均值基线MAE：{holdout["baseline_mae"]:.6f} ticks。</p><p>模型减基线的MAE差：{holdout["mean_mae_delta"]:.6f}；块自助95%描述区间：{holdout["moving_block_delta95"][0]:.6f} 至 {holdout["moving_block_delta95"][1]:.6f}。负值代表模型误差更小。</p></section><section><h2>解释边界</h2><ul>{warnings}</ul><details><summary>完整复核数据与源摘要</summary><pre>{details}</pre></details></section></main></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshots")
    parser.add_argument("new_report_dir")
    parser.add_argument("--horizon-ms", type=int, default=100)
    args = parser.parse_args()
    try:
        report = analyze(Path(args.snapshots).read_bytes(), args.horizon_ms)
        directory = Path(args.new_report_dir)
        directory.mkdir()
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        (directory / "index.html").write_text(render(report), encoding="utf-8")
        print("Report:", directory / "index.html")
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
