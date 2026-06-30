from fastapi import APIRouter

router = APIRouter()


@router.get("/positions")
async def get_positions():
    return []


@router.get("/allocation")
async def get_allocation():
    return []


@router.get("/risk-metrics")
async def risk_metrics():
    return {
        "sharpe": 1.42,
        "sortino": 1.87,
        "max_drawdown": -0.084,
        "beta": 0.92,
        "var_95": 1248.0,
        "calmar": 2.31,
    }
