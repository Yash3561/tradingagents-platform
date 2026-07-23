"""
Day P&L math — one place, because every call site that computed this inline
independently had the same bug: Alpaca's account.last_equity is 0 (not
missing, an actual 0) for a freshly created or freshly reset paper account,
until the platform has a real prior-session close to compare against.
`acct.get("last_equity", equity)` only catches a MISSING key, not an
explicitly-zero one, so equity - 0 silently became "today's profit is your
entire account" on the dashboard for exactly the accounts most likely to be
shown to someone new (2026-07-23).
"""


def compute_day_pnl(equity: float, last_equity: float) -> tuple[float, float]:
    """(day_pnl_dollars, day_pnl_pct). Returns (0.0, 0.0) when last_equity
    isn't a usable baseline yet, instead of treating the whole account as
    today's move."""
    if last_equity <= 0:
        return 0.0, 0.0
    day_pnl = equity - last_equity
    return day_pnl, day_pnl / last_equity * 100
