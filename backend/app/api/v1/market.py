from fastapi import APIRouter, HTTPException
import httpx
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Latest quote from Alpaca data API."""
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.alpaca_data_url}/v2/stocks/{ticker.upper()}/quotes/latest",
                headers=headers,
                timeout=5.0,
            )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, r.text)
    except httpx.TimeoutException:
        raise HTTPException(504, "Data feed timeout")


@router.get("/search")
async def search_ticker(q: str):
    return []
