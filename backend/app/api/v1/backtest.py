import uuid
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class BacktestRequest(BaseModel):
    ticker: str
    from_date: str
    to_date: str
    debate_rounds: int = 1
    model: str = "claude-sonnet-4-6"


@router.post("/jobs")
async def submit_job(body: BacktestRequest):
    job_id = str(uuid.uuid4())
    return {"job_id": job_id, "status": "queued", "ticker": body.ticker}


@router.get("/jobs")
async def list_jobs():
    return []


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return {"job_id": job_id, "status": "completed", "progress": 100}


@router.get("/jobs/{job_id}/results")
async def get_results(job_id: str):
    return {
        "metrics": {
            "sharpe": 1.38,
            "cagr": 0.248,
            "max_drawdown": -0.062,
            "win_rate": 0.583,
            "profit_factor": 1.72,
            "total_trades": 48,
        },
        "equity_curve": [],
        "trades": [],
    }
