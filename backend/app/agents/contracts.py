"""
Agent-to-agent contracts for the TradingAgents pipeline.

Every agent in the pipeline has a strictly typed Pydantic output schema.
Claude is forced into these schemas via structured outputs (tool_use / json mode).
Downstream agents receive clean typed objects — no free-form text parsing.

Flow:
  [Technical, Sentiment, News, Fundamental] → AnalystBundle
         ↓
  [Bull Researcher, Bear Researcher] → ResearcherDebate
         ↓
  [Risk Manager] → RiskAssessment
         ↓
  [Portfolio Manager] → FinalDecision
"""

from __future__ import annotations
import re
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class Signal(str, Enum):
    STRONG_BUY  = "STRONG_BUY"
    BUY         = "BUY"
    NEUTRAL     = "NEUTRAL"
    SELL        = "SELL"
    STRONG_SELL = "STRONG_SELL"


class Decision(str, Enum):
    BUY  = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class RiskLevel(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    REJECT = "REJECT"    # Risk manager vetoes the trade entirely


# ── Analyst Contracts ─────────────────────────────────────────────────────────

class TechnicalReport(BaseModel):
    """Output contract for the Technical Analyst agent."""
    ticker: str
    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)

    # Indicators (None = not computable / data unavailable)
    rsi_14: float | None = Field(default=None, description="RSI over 14 periods")
    rsi_signal: str | None = Field(default=None, description="oversold | neutral | overbought")
    macd_bullish_crossover: bool | None = None
    above_50d_ma: bool | None = None
    above_200d_ma: bool | None = None
    support_levels: list[float] = Field(default_factory=list, max_length=3)
    resistance_levels: list[float] = Field(default_factory=list, max_length=3)
    volume_trend: str | None = Field(default=None, description="increasing | decreasing | neutral")
    trend_direction: str | None = Field(default=None, description="uptrend | downtrend | sideways")

    key_points: list[str] = Field(default_factory=list, max_length=5, description="Top 3-5 technical observations")
    reasoning: str = Field(description="Concise technical reasoning, max 150 words")


class SentimentReport(BaseModel):
    """Output contract for the Sentiment Analyst agent."""
    ticker: str
    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)

    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0, description="-1 bearish to +1 bullish")
    retail_sentiment: str | None = Field(default=None, description="bullish | neutral | bearish")
    institutional_flow: str | None = Field(default=None, description="buying | neutral | selling")
    short_interest_pct: float | None = Field(default=None, description="Short interest as % of float")
    put_call_ratio: float | None = None
    social_volume_trend: str | None = Field(default=None, description="rising | flat | falling")

    key_points: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str = Field(description="Concise sentiment reasoning, max 150 words")


class NewsReport(BaseModel):
    """Output contract for the News Analyst agent."""
    ticker: str
    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)

    headline_sentiment: str | None = Field(default=None, description="positive | neutral | negative")
    material_news_exists: bool = False
    catalyst_upcoming: bool = Field(default=False, description="Earnings, product launch, regulatory decision etc.")
    catalyst_description: str | None = None
    risk_events: list[str] = Field(default_factory=list, max_length=3, description="Identified news-based risk events")

    key_points: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str = Field(description="Concise news reasoning, max 150 words")


class FundamentalReport(BaseModel):
    """Output contract for the Fundamental Analyst agent."""
    ticker: str
    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)

    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    revenue_growth_yoy: float | None = Field(default=None, description="YoY revenue growth as decimal e.g. 0.18 = 18%")
    gross_margin: float | None = Field(default=None, description="Gross margin as decimal")
    debt_to_equity: float | None = None
    fcf_yield: float | None = None
    vs_sector_pe: str | None = Field(default=None, description="premium | inline | discount")
    earnings_quality: str | None = Field(default=None, description="high | medium | low")

    key_points: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str = Field(description="Concise fundamental reasoning, max 150 words")


# ── Analyst Bundle — passed to Researcher ────────────────────────────────────

class AnalystBundle(BaseModel):
    """Aggregated output from all 4 analysts. Input to Researcher agents."""
    ticker: str
    analysis_date: str
    technical: TechnicalReport
    sentiment: SentimentReport
    news: NewsReport
    fundamental: FundamentalReport

    @property
    def analyst_signals(self) -> dict[str, Signal]:
        return {
            "technical": self.technical.signal,
            "sentiment": self.sentiment.signal,
            "news": self.news.signal,
            "fundamental": self.fundamental.signal,
        }

    @property
    def avg_confidence(self) -> float:
        scores = [self.technical.confidence, self.sentiment.confidence,
                  self.news.confidence, self.fundamental.confidence]
        return round(sum(scores) / len(scores), 3)

    def bullish_count(self) -> int:
        return sum(1 for s in self.analyst_signals.values() if s in (Signal.BUY, Signal.STRONG_BUY))

    def bearish_count(self) -> int:
        return sum(1 for s in self.analyst_signals.values() if s in (Signal.SELL, Signal.STRONG_SELL))


# ── Researcher Contracts ───────────────────────────────────────────────────────

class ResearcherArgument(BaseModel):
    """Single round argument from Bull or Bear researcher."""
    stance: str = Field(description="bull | bear")
    thesis: str = Field(description="Core investment thesis, max 120 words")
    strongest_points: list[str] = Field(max_length=4)
    rebuttals: list[str] = Field(default_factory=list, max_length=3, description="Counter to opposing stance")
    conviction: float = Field(ge=0.0, le=1.0, description="Researcher conviction in own thesis")


class ResearcherDebate(BaseModel):
    """Full bull/bear debate output. Input to Risk Manager."""
    ticker: str
    rounds: list[dict] = Field(description="List of {bull: ResearcherArgument, bear: ResearcherArgument} per round")
    bull_final_thesis: str
    bear_final_thesis: str
    debate_winner: str | None = Field(default=None, description="bull | bear | draw — based on argument strength")
    suggested_signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)
    key_risks: list[str] = Field(default_factory=list, max_length=5)
    key_catalysts: list[str] = Field(default_factory=list, max_length=5)


# ── Risk Manager Contract ─────────────────────────────────────────────────────

class RiskAssessment(BaseModel):
    """Output contract for the Risk Manager agent. Input to Portfolio Manager."""
    ticker: str
    risk_level: RiskLevel
    approved: bool = Field(description="Whether trade is approved to proceed to PM")

    # le=40: deterministic engines run concentrated books (momentum rotation
    # ~24-38%/name, earnings aggression arm 25%). LLM agents are still held to
    # ~5% by the risk-manager prompt rules; this schema bound is the hard stop.
    recommended_position_pct: float | None = Field(
        default=None, ge=0.0, le=40.0,
        description="Recommended position size as % of portfolio"
    )
    max_position_pct: float | None = Field(
        default=None, ge=0.0, le=20.0,
        description="Hard maximum position size"
    )
    stop_loss_pct: float | None = Field(
        default=None, ge=0.0, le=50.0,
        description="Recommended stop-loss as % below entry"
    )
    take_profit_pct: float | None = Field(
        default=None,
        description="Suggested take-profit as % above entry"
    )

    portfolio_var_impact: str | None = Field(
        default=None, description="low | medium | high — estimated VaR impact"
    )
    correlation_risk: str | None = Field(
        default=None, description="low | medium | high — correlation with existing positions"
    )
    concentration_risk: str | None = Field(
        default=None, description="low | medium | high"
    )

    rejection_reason: str | None = Field(
        default=None, description="Required if approved=False"
    )
    risk_notes: list[str] = Field(default_factory=list, max_length=5)
    reasoning: str = Field(description="Risk assessment reasoning, max 150 words")

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def _strip_chain_of_thought(cls, v):
        """Some models leak <think> blocks / raw deliberation into this field;
        it is shown to users and stored on the run row, so keep it terse."""
        if not isinstance(v, str):
            return v
        v = re.sub(r"<think(?:ing)?>.*?(?:</think(?:ing)?>|$)", "", v,
                   flags=re.DOTALL | re.IGNORECASE).strip()
        if len(v) > 400:
            v = v[:397].rstrip() + "..."
        return v or None


# ── Final Decision Contract ───────────────────────────────────────────────────

class FinalDecision(BaseModel):
    """Portfolio Manager's final output. This is what triggers order execution."""
    ticker: str
    analysis_date: str
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)

    # Order parameters (None if HOLD)
    order_side: str | None = Field(default=None, description="buy | sell")
    # le=40: see RiskAssessment.recommended_position_pct — concentrated
    # deterministic engines exceed the old 20 cap by design
    position_size_pct: float | None = Field(
        default=None, ge=0.0, le=40.0,
        description="Actual position size to use, % of portfolio"
    )
    order_type: str = Field(default="market", description="market | limit | twap")
    limit_price: float | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None

    # Rationale
    primary_reason: str = Field(description="Single sentence primary reason for decision")
    supporting_factors: list[str] = Field(default_factory=list, max_length=5)
    key_risks_acknowledged: list[str] = Field(default_factory=list, max_length=3)
    summary: str = Field(description="Full PM rationale, max 200 words")

    # Metadata
    analyst_signals: dict[str, str] = Field(default_factory=dict)
    debate_winner: str | None = None
    risk_level: str | None = None
    risk_approved: bool = True


# ── Contract Registry — for API exposure and agent self-description ────────────

AGENT_CONTRACTS: dict[str, type[BaseModel]] = {
    "technical_analyst":  TechnicalReport,
    "sentiment_analyst":  SentimentReport,
    "news_analyst":       NewsReport,
    "fundamental_analyst": FundamentalReport,
    "analyst_bundle":     AnalystBundle,
    "researcher_debate":  ResearcherDebate,
    "risk_assessment":    RiskAssessment,
    "final_decision":     FinalDecision,
}


def get_contract_schema(agent_name: str) -> dict:
    """Return the JSON schema for a given agent contract."""
    contract = AGENT_CONTRACTS.get(agent_name)
    if not contract:
        raise KeyError(f"No contract for agent: {agent_name}")
    return contract.model_json_schema()


def get_all_schemas() -> dict[str, dict]:
    """Return all agent contract schemas — used by /agents/contracts endpoint."""
    return {name: cls.model_json_schema() for name, cls in AGENT_CONTRACTS.items()}
