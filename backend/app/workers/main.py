"""
Background worker entry point.

Runs 4 concurrent async loops:
  - position_monitor : stop-loss / take-profit enforcement (every 5 min)
  - trade_sync       : Alpaca fill reconciliation → DB (every 2 min)
  - equity_tracker   : portfolio equity snapshots (every 15 min)
  - scheduler        : auto-scan at market open + midday (checks every 60s)
"""
import asyncio
import structlog

log = structlog.get_logger()


async def main():
    from app.workers.position_monitor import run_position_monitor
    from app.workers.trade_sync import run_trade_sync
    from app.workers.equity_tracker import run_equity_tracker
    from app.workers.scheduler import run_scheduler

    log.info("workers.start",
             loops=["position_monitor", "trade_sync", "equity_tracker", "scheduler"])

    # Take an initial equity snapshot on startup so dashboard has data immediately
    try:
        from app.workers.equity_tracker import take_snapshot
        await take_snapshot()
        log.info("workers.initial_snapshot_done")
    except Exception as e:
        log.warning("workers.initial_snapshot_failed", error=str(e))

    await asyncio.gather(
        run_position_monitor(),
        run_trade_sync(),
        run_equity_tracker(),
        run_scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
