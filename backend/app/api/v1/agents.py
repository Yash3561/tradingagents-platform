import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.postgres import get_db
from app.db.models.agent_run import AgentRun
from app.agents.structured_runner import run_structured_agent_analysis
from app.agents.contracts import get_all_schemas, get_contract_schema
from app.core.websocket_manager import ws_manager

router = APIRouter()


class RunRequest(BaseModel):
    ticker: str
    date: str | None = None        # defaults to today
    debate_rounds: int = 2
    model: str = "deepseek-ai/deepseek-v4-flash"          # analyst tier (Technical/Sentiment/News/Fundamental)
    senior_model: str | None = "deepseek-ai/deepseek-v4-pro"  # senior tier (Researcher/Risk/PM)


class RunResponse(BaseModel):
    run_id: str
    ticker: str
    status: str
    created_at: str


@router.post("/run", response_model=RunResponse)
async def trigger_run(
    body: RunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    run_id = str(uuid.uuid4())
    analysis_date = body.date or datetime.now(UTC).strftime("%Y-%m-%d")

    run = AgentRun(
        id=run_id,
        ticker=body.ticker.upper(),
        analysis_date=analysis_date,
        status="pending",
        llm_model=body.model,
        debate_rounds=body.debate_rounds,
    )
    db.add(run)
    await db.commit()

    background_tasks.add_task(run_structured_agent_analysis, run_id, body.ticker.upper(), analysis_date, body.debate_rounds, body.model, body.senior_model)

    return RunResponse(
        run_id=run_id,
        ticker=body.ticker.upper(),
        status="pending",
        created_at=run.created_at.isoformat(),
    )


@router.get("/runs")
async def list_runs(limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select, desc
    result = await db.execute(
        select(AgentRun).order_by(desc(AgentRun.created_at)).limit(limit).offset(offset)
    )
    runs = result.scalars().all()
    return [
        {
            "run_id": r.id,
            "ticker": r.ticker,
            "status": r.status,
            "decision": r.decision,
            "confidence": r.confidence,
            "analysis_date": r.analysis_date,
            "created_at": r.created_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "run_id": run.id,
        "ticker": run.ticker,
        "status": run.status,
        "decision": run.decision,
        "confidence": run.confidence,
        "summary": run.summary,
        "analysis_date": run.analysis_date,
        "debate_log": run.debate_log,
        "reasoning_json": run.reasoning_json,
        "model": run.llm_model,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


@router.get("/contracts")
async def list_contracts():
    """
    Returns the JSON schema for every agent's output contract.
    Frontend and agents use this to understand what each stage produces
    without reading source files.
    """
    return get_all_schemas()


@router.get("/contracts/{agent_name}")
async def get_agent_contract(agent_name: str):
    """Return the JSON schema for a specific agent contract."""
    try:
        return get_contract_schema(agent_name)
    except KeyError:
        raise HTTPException(404, f"No contract for agent: '{agent_name}'")


class ScanRequest(BaseModel):
    model: str = "deepseek-ai/deepseek-v4-flash"              # analyst tier
    senior_model: str | None = "deepseek-ai/deepseek-v4-pro"  # senior tier (Researcher/Risk/PM)
    max_candidates: int = 8
    watchlist: list[str] | None = None


@router.post("/scan")
async def trigger_scan(body: ScanRequest, background_tasks: BackgroundTasks):
    """
    Trigger a full market scan:
    1. Pre-screen 40+ stocks with technical analysis (free/fast)
    2. Run AI pipeline on top candidates
    3. Auto-execute approved trades on Alpaca paper account
    Returns scan_id for polling or use SSE to track progress.
    """
    import uuid as _uuid
    scan_id = str(_uuid.uuid4())

    async def _run():
        from app.workers.scanner import run_market_scan
        try:
            result = await run_market_scan(
                model=body.model,
                senior_model=body.senior_model,
                watchlist=body.watchlist,
                max_candidates=body.max_candidates,
                scan_id=scan_id,
            )
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_completed",
                "scan_id": scan_id,
                **result,
            })
        except Exception as e:
            await ws_manager.broadcast(f"scan:{scan_id}", {
                "type": "scan_error",
                "scan_id": scan_id,
                "error": str(e),
            })

    background_tasks.add_task(_run)
    return {"scan_id": scan_id, "status": "started"}


@router.get("/scan/prescreen")
async def prescreen_only():
    """
    Run only the free technical pre-screen on all watchlist stocks.
    No Claude calls — instant results (~10s for 40 stocks).
    """
    import asyncio
    from app.workers.scanner import WATCHLIST, _screen_ticker
    loop = asyncio.get_running_loop()

    def _run_all():
        results = []
        for t in WATCHLIST:
            r = _screen_ticker(t)
            if r:
                results.append(r)
        return sorted(results, key=lambda x: x["score"], reverse=True)

    results = await loop.run_in_executor(None, _run_all)
    return results


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("pending", "running"):
        raise HTTPException(400, f"Cannot cancel run in status: {run.status}")
    run.status = "cancelled"
    await db.commit()
    await ws_manager.broadcast(f"run:{run_id}", {"type": "status", "status": "cancelled"})
    return {"ok": True}
