"""
Entry point for background workers.
Run with: python -m app.workers.main
"""
import asyncio
import structlog

log = structlog.get_logger()


async def main():
    log.info("workers.start")
    # Workers will be initialized here as they're built out
    # e.g.: await asyncio.gather(market_ingestion(), agent_worker(), backtest_worker())
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
