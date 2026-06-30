from fastapi import APIRouter
from app.api.v1 import dashboard, agents, portfolio, trades, market, backtest, settings, websockets
from app.api.v1 import notifications, activity
from app.api.v1 import auth
from app.api.v1 import analytics

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(trades.router, prefix="/trades", tags=["trades"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["backtest"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(websockets.router, prefix="/ws", tags=["websockets"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
