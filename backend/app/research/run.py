"""
CLI entry point:  python -m app.research.run [--quick]

Runs the walk-forward policy tournament and writes the full report to
/tmp/research_report.json (also printed as a summary).
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--train-years", type=int, default=4)
    ap.add_argument("--test-years", type=int, default=1)
    ap.add_argument("--holdout-months", type=int, default=12)
    ap.add_argument("--quick", action="store_true",
                    help="small grid + shorter span, for smoke testing")
    args = ap.parse_args()

    from app.research.walkforward import run_walkforward, default_grid
    from app.research.engine import Policy

    grid = None
    start = args.start
    if args.quick:
        grid = [Policy(), Policy(regime_mode="off"), Policy(require_macd=False),
                Policy(allow_meanrev=False), Policy(allow_trend=False)]
        start = "2019-01-01"

    report = run_walkforward(start=start, train_years=args.train_years,
                             test_years=args.test_years,
                             holdout_months=args.holdout_months, grid=grid)

    with open("/tmp/research_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    m = report["meta"]
    print(f"\n=== Walk-forward tournament: {m['span']} | "
          f"{m['policies_tested']} policies | {len(m['folds'])} folds | "
          f"{m['elapsed_s']}s ===")
    print(f"Holdout (untouched): {m['holdout']}")
    print(f"\nTop policies by mean TEST Sharpe across folds "
          f"(live baseline rank: {report['live_baseline_rank']}):")
    for i, r in enumerate(report["leaderboard"], 1):
        print(f"{i:2}. {r['label']}")
        print(f"     test Sharpe {r['test_sharpe']:>5}  (train {r['train_sharpe']}, "
              f"gap {r['overfit_gap']})  CAGR {r['test_cagr_pct']}%  "
              f"maxDD {r['test_maxdd_pct']}%  WR {r['test_win_rate_pct']}%  "
              f"{r['test_trades_per_fold']} trades/fold")
    if report["holdout"]:
        h = report["holdout"]
        print(f"\nHOLDOUT (one shot, winner only): {h['policy']}")
        print(f"  {json.dumps(h['metrics'], indent=2, default=str)}")
        print(f"  SPY over same period: {h['spy_return_pct']}%")
    print(f"\nCaveats: {'; '.join(m['caveats'])}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
