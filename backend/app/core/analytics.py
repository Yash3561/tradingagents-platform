"""
Product analytics — fire-and-forget event tracking.

track() must never break the endpoint that calls it: it swallows every
exception and uses its own DB session.
"""
import logging

from app.core.postgres import AsyncSessionLocal
from app.db.models.analytics_event import AnalyticsEvent

logger = logging.getLogger(__name__)

# Event names in use (keep this list current — the admin dashboard groups by it):
#   signup, login, broker_connected, agent_run, scan_run, manual_order
async def track(event: str, user_id: int | None = None, **properties) -> None:
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AnalyticsEvent(event=event, user_id=user_id, properties=properties or None)
            )
            await session.commit()
    except Exception as exc:
        logger.warning("analytics.track failed for %s: %s", event, exc)
