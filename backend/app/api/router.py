from fastapi import APIRouter, Depends

from app.core.auth import require_user
from app.api.v1 import dashboard, agents, portfolio, trades, market, backtest, settings, websockets
from app.api.v1 import notifications, activity
from app.api.v1 import auth
from app.api.v1 import analytics
from app.api.v1 import alerts
from app.api.v1 import orders
from app.api.v1 import broker
from app.api.v1 import admin
from app.api.v1 import track_record
from app.api.v1 import monitor

api_router = APIRouter()

# Public: login/register + WebSocket (rooms are unguessable UUIDs)
# + anonymized AI track record (the shareable proof page)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(websockets.router, prefix="/ws", tags=["websockets"])
api_router.include_router(track_record.router, prefix="/track-record", tags=["track-record"])
# Read-only automated monitoring — own key-based auth (require_monitoring_key
# on each endpoint), deliberately NOT the JWT `AUTH` list below: no login,
# no password, for unattended cloud/cron agents. Fails closed if unset.
api_router.include_router(monitor.router, prefix="/monitor", tags=["monitor"])

# Everything else requires a valid JWT
AUTH = [Depends(require_user)]
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"], dependencies=AUTH)
api_router.include_router(agents.router, prefix="/agents", tags=["agents"], dependencies=AUTH)
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"], dependencies=AUTH)
api_router.include_router(trades.router, prefix="/trades", tags=["trades"], dependencies=AUTH)
api_router.include_router(orders.router, prefix="/orders", tags=["orders"], dependencies=AUTH)
api_router.include_router(market.router, prefix="/market", tags=["market"], dependencies=AUTH)
api_router.include_router(backtest.router, prefix="/backtest", tags=["backtest"], dependencies=AUTH)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=AUTH)
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"], dependencies=AUTH)
api_router.include_router(activity.router, prefix="/activity", tags=["activity"], dependencies=AUTH)
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"], dependencies=AUTH)
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"], dependencies=AUTH)
api_router.include_router(broker.router, prefix="/broker", tags=["broker"], dependencies=AUTH)
# Admin-only (each endpoint also depends on require_admin)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"], dependencies=AUTH)
