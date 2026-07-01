"""
Market Regime Detector — determines current market environment.

4 regimes:
- BULL_TRENDING: Price > MA200, VIX < 20, breadth positive → momentum strategies
- BEAR_TRENDING: Price < MA200, VIX > 25 → defensive, short-biased
- HIGH_VOLATILITY: VIX > 30 → no new longs, tight stops, cash is king
- SIDEWAYS: Neither trending → mean reversion strategies work best

Used by scanner to switch strategies and by risk manager to adjust position sizes.
"""
from __future__ import annotations
import asyncio
import structlog
from datetime import datetime, UTC

log = structlog.get_logger()

_regime_cache: dict = {}
_cache_ts: datetime | None = None
CACHE_MINUTES = 15


async def get_market_regime() -> dict:
    """
    Returns current market regime + supporting data.
    Cached for 15 minutes.
    """
    global _regime_cache, _cache_ts

    now = datetime.now(UTC)
    if _cache_ts and (now - _cache_ts).seconds < CACHE_MINUTES * 60 and _regime_cache:
        return _regime_cache

    def _compute():
        import yfinance as yf
        import numpy as np

        # Fetch SPY (market proxy) and VIX
        spy = yf.Ticker("SPY")
        vix = yf.Ticker("^VIX")

        spy_hist = spy.history(period="1y", interval="1d")
        vix_hist = vix.history(period="5d", interval="1d")

        if spy_hist.empty:
            return {"regime": "UNKNOWN", "confidence": 0}

        spy_close = spy_hist["Close"]
        current = float(spy_close.iloc[-1])
        ma50 = float(spy_close.tail(50).mean())
        ma200 = float(spy_close.tail(200).mean()) if len(spy_close) >= 200 else float(spy_close.mean())

        vix_level = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0

        # RSI on SPY
        delta = spy_close.diff()
        gain = delta.clip(lower=0).tail(14).mean()
        loss = (-delta.clip(upper=0)).tail(14).mean()
        spy_rsi = float(100 - (100 / (1 + gain / loss))) if loss != 0 else 50.0

        # Advance/Decline proxy: % of last 20 days that were up
        returns = spy_close.pct_change().tail(20)
        breadth_score = float((returns > 0).mean())  # 0 to 1

        # ATR for volatility context
        high = spy_hist["High"].tail(14)
        low = spy_hist["Low"].tail(14)
        atr = float((high - low).mean())
        atr_pct = atr / current * 100

        # Momentum: 1-month and 3-month
        mom_1m = (current / float(spy_close.iloc[-22]) - 1) * 100 if len(spy_close) >= 22 else 0
        mom_3m = (current / float(spy_close.iloc[-66]) - 1) * 100 if len(spy_close) >= 66 else 0

        # ── Regime classification ─────────────────────────────────────────
        regime_scores = {
            "BULL_TRENDING": 0,
            "BEAR_TRENDING": 0,
            "HIGH_VOLATILITY": 0,
            "SIDEWAYS": 0,
        }

        # VIX signals
        if vix_level > 30:
            regime_scores["HIGH_VOLATILITY"] += 40
        elif vix_level > 20:
            regime_scores["HIGH_VOLATILITY"] += 15
            regime_scores["SIDEWAYS"] += 10
        else:
            regime_scores["BULL_TRENDING"] += 15

        # Trend signals
        if current > ma50 > ma200:
            regime_scores["BULL_TRENDING"] += 30
        elif current < ma50 < ma200:
            regime_scores["BEAR_TRENDING"] += 30
        elif current > ma200:
            regime_scores["BULL_TRENDING"] += 15
            regime_scores["SIDEWAYS"] += 10
        else:
            regime_scores["BEAR_TRENDING"] += 15
            regime_scores["SIDEWAYS"] += 10

        # Breadth
        if breadth_score > 0.65:
            regime_scores["BULL_TRENDING"] += 20
        elif breadth_score < 0.35:
            regime_scores["BEAR_TRENDING"] += 20
        else:
            regime_scores["SIDEWAYS"] += 15

        # Momentum
        if mom_1m > 3 and mom_3m > 8:
            regime_scores["BULL_TRENDING"] += 15
        elif mom_1m < -3 and mom_3m < -8:
            regime_scores["BEAR_TRENDING"] += 15
        else:
            regime_scores["SIDEWAYS"] += 10

        # RSI extreme
        if spy_rsi > 70:
            regime_scores["HIGH_VOLATILITY"] += 10
        elif spy_rsi < 35:
            regime_scores["BEAR_TRENDING"] += 10

        # Pick winning regime
        regime = max(regime_scores, key=lambda k: regime_scores[k])
        total = sum(regime_scores.values())
        confidence = round(regime_scores[regime] / total * 100, 1) if total > 0 else 0

        # Strategy recommendations per regime
        strategies = {
            "BULL_TRENDING": {
                "primary": "momentum",
                "description": "Strong uptrend — buy breakouts, ride momentum, sector leaders",
                "bias": "LONG",
                "max_position_pct": 5.0,
                "stop_multiplier": 1.0,  # normal stops
                "min_confidence": 0.65,
            },
            "BEAR_TRENDING": {
                "primary": "defensive",
                "description": "Downtrend — reduce exposure, no new longs, short broken stocks",
                "bias": "SHORT",
                "max_position_pct": 2.0,  # smaller positions
                "stop_multiplier": 0.7,   # tighter stops
                "min_confidence": 0.80,   # higher bar to trade
            },
            "HIGH_VOLATILITY": {
                "primary": "cash",
                "description": "VIX elevated — stay in cash, only high-conviction mean reversions",
                "bias": "NEUTRAL",
                "max_position_pct": 1.5,
                "stop_multiplier": 0.5,
                "min_confidence": 0.85,
            },
            "SIDEWAYS": {
                "primary": "mean_reversion",
                "description": "Range-bound — buy oversold, sell overbought, fade extremes",
                "bias": "NEUTRAL",
                "max_position_pct": 3.0,
                "stop_multiplier": 0.8,
                "min_confidence": 0.72,
            },
        }

        return {
            "regime": regime,
            "confidence": confidence,
            "spy_price": round(current, 2),
            "spy_ma50": round(ma50, 2),
            "spy_ma200": round(ma200, 2),
            "spy_rsi": round(spy_rsi, 1),
            "vix": round(vix_level, 2),
            "breadth_score": round(breadth_score, 3),
            "mom_1m_pct": round(mom_1m, 2),
            "mom_3m_pct": round(mom_3m, 2),
            "atr_pct": round(atr_pct, 2),
            "regime_scores": regime_scores,
            "strategy": strategies[regime],
            "computed_at": now.isoformat(),
        }

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _compute)
        _regime_cache = result
        _cache_ts = now
        log.info("regime_detector.computed", regime=result["regime"], confidence=result["confidence"])
        return result
    except Exception as e:
        log.warning("regime_detector.failed", error=str(e))
        return {
            "regime": "UNKNOWN",
            "confidence": 0,
            "vix": 20.0,
            "strategy": {"primary": "momentum", "bias": "LONG", "max_position_pct": 5.0, "stop_multiplier": 1.0, "min_confidence": 0.70},
        }
