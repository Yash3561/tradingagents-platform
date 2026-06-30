from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


@router.get("/")
async def get_settings_view():
    return {
        "agents": {"model": "claude-sonnet-4-6", "debate_rounds": 2, "online_tools": True},
        "risk": {"max_position_pct": 5, "stop_loss_pct": 8, "daily_loss_pct": 3},
        "data_sources": {"market_data": "alpaca", "fundamentals": "yfinance"},
    }


class AgentConfigUpdate(BaseModel):
    model: str | None = None
    debate_rounds: int | None = None
    online_tools: bool | None = None


@router.patch("/agents")
async def update_agent_config(body: AgentConfigUpdate):
    return {"ok": True}


@router.post("/api-keys/test")
async def test_api_keys(provider: str):
    return {"ok": True, "provider": provider}
