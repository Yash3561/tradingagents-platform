"""
Background worker entry point (worker container).

Runs ONLY the loops that are NOT started by the backend's lifespan, so nothing
runs twice:

  worker container : trade_sync (2 min), equity_tracker (15 min)
  backend lifespan : position_monitor, scheduler (+ intraday), overnight_agent,
                     price_feed — these stay in the API process because they
                     broadcast over the in-process WebSocket manager.

If you add a loop here, make sure it is not also started in app/main.py.
"""
import asyncio
import structlog

log = structlog.get_logger()


async def main():
    from app.workers.trade_sync import run_trade_sync
    from app.workers.equity_tracker import run_equity_tracker

    log.info("workers.start", loops=["trade_sync", "equity_tracker"])

    # Take an initial equity snapshot on startup so dashboard has data immediately
    try:
        from app.workers.equity_tracker import take_snapshot
        await take_snapshot()
        log.info("workers.initial_snapshot_done")
    except Exception as e:
        log.warning("workers.initial_snapshot_failed", error=str(e))

    await asyncio.gather(
        run_trade_sync(),
        run_equity_tracker(),
    )


if __name__ == "__main__":
    asyncio.run(main())
