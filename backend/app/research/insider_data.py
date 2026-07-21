"""
SEC EDGAR Form 4 data layer — insider open-market purchases.

A genuinely different information source than the price-pattern families in
engine.py/momentum.py: instead of technicals, this reads what a company's
own officers/directors/10%-owners actually did with their own cash. The
academic anchor (Lakonishok & Lee 2001, Jeng/Metrick/Zeckhauser 2003) finds
predictive value specifically in OPEN-MARKET PURCHASES (transaction code
"P") — voluntary, cash-out-of-pocket buys. Sales, option exercises, RSU
vesting, and tax withholding (codes S/M/A/F/...) are mechanical or driven by
liquidity/diversification needs and carry little-to-no signal; this module
filters to P transactions only.

Source: SEC EDGAR's public data.sec.gov / www.sec.gov endpoints, no key
required. Fair access policy caps requests at 10/sec — this stays well
under that (see _throttle). A descriptive User-Agent is REQUIRED by SEC
or requests get blocked.

Everything here is sync (called from thread executors, matching data.py's
convention) and disk-cached — a full-universe historical pull is a genuine
one-time cost (hundreds of filings per liquid large-cap), never repeated.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import threading
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import structlog

log = structlog.get_logger()

CACHE_DIR = Path("/tmp/research_cache/insider")
_SEC_HEADERS = {"User-Agent": "TradingAgentsResearch (research use; contact: admin@tradingagents-platform.dev)"}

# SEC's stated fair-access cap is 10 req/sec; stay comfortably under it.
_MIN_INTERVAL_S = 0.15
_last_call = [0.0]
_throttle_lock = threading.Lock()


def _throttle():
    with _throttle_lock:
        wait = _last_call[0] + _MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _get(url: str, timeout: float = 20.0) -> requests.Response:
    _throttle()
    r = requests.get(url, headers=_SEC_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def _cached_json(key: str, fetch_fn):
    path = _cache_path(key)
    if path.exists():
        return json.loads(path.read_text())
    result = fetch_fn()
    path.write_text(json.dumps(result))
    return result


_ticker_cik_map: dict[str, str] | None = None


def _load_ticker_cik_map() -> dict[str, str]:
    """Whole-market ticker->CIK map, one file, cached forever (SEC updates it
    periodically but tickers rarely change CIK)."""
    global _ticker_cik_map
    if _ticker_cik_map is not None:
        return _ticker_cik_map

    def _fetch():
        r = _get("https://www.sec.gov/files/company_tickers.json")
        raw = r.json()
        return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in raw.values()}

    _ticker_cik_map = _cached_json("ticker_cik_map_v1", _fetch)
    return _ticker_cik_map


def ticker_to_cik(ticker: str) -> str | None:
    return _load_ticker_cik_map().get(ticker.upper())


def _submissions(cik: str) -> dict:
    return _cached_json(f"submissions_{cik}", lambda: _get(
        f"https://data.sec.gov/submissions/CIK{cik}.json").json())


def _submissions_page(cik: str, filename: str) -> dict:
    return _cached_json(f"submissions_page_{filename}", lambda: _get(
        f"https://data.sec.gov/submissions/{filename}").json())


def list_form4_filings(ticker: str, start_date: str, end_date: str,
                       include_older_pages: bool = True) -> list[dict]:
    """
    [{accession, filing_date, primary_doc}] for every Form 4 this issuer's
    CIK filed in [start_date, end_date]. primary_doc is needed because the
    raw XML's filename is NOT a fixed "form4.xml" — it varies per filing
    agent (e.g. "wk-form4_1773786674.xml"); only its basename (after the
    XSL-rendering subfolder) is stable at the accession directory's root.
    The 'recent' block alone typically covers 10+ years for an active
    large-cap; include_older_pages walks the paginated history files SEC
    provides for anything before that.
    """
    cik = ticker_to_cik(ticker)
    if cik is None:
        return []
    sub = _submissions(cik)
    filings = sub.get("filings", {})

    out: list[dict] = []

    def _scan(block: dict):
        forms = block.get("form", [])
        dates = block.get("filingDate", [])
        accns = block.get("accessionNumber", [])
        docs = block.get("primaryDocument", [])
        for i, f in enumerate(forms):
            if f != "4":
                continue
            d = dates[i]
            if start_date <= d <= end_date:
                doc = docs[i] if i < len(docs) else ""
                out.append({"accession": accns[i], "filing_date": d,
                           "primary_doc": doc.rsplit("/", 1)[-1] if doc else "form4.xml"})

    _scan(filings.get("recent", {}))

    if include_older_pages:
        for page in filings.get("files", []):
            # Only fetch a page if it can possibly overlap the requested window
            if page.get("filingFrom", "9999") <= end_date and page.get("filingTo", "0000") >= start_date:
                _scan(_submissions_page(cik, page["name"]))

    return out


def fetch_form4_transactions(ticker: str, cik: str, accession: str,
                             primary_doc: str = "form4.xml") -> list[dict]:
    """Parse one Form 4 filing's raw XML. Returns ALL non-derivative
    transactions (caller filters to code=='P' for the purchase signal —
    kept unfiltered here so the raw data is inspectable/reusable)."""
    accession_nodash = accession.replace("-", "")
    cik_int = str(int(cik))  # SEC's Archives path wants the CIK without leading zeros
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{primary_doc}"

    def _fetch():
        r = _get(url)
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as e:
            log.debug("insider.xml_parse_failed", ticker=ticker, accession=accession, error=str(e))
            return []

        owner_el = root.find("reportingOwner")
        owner_name = owner_el.findtext("reportingOwnerId/rptOwnerName") if owner_el is not None else None
        # Some filings list the issuer itself (or a company-administered
        # benefit/DRIP plan) as the "reporting owner" — not a person. These
        # show up as e.g. 1 share at $0.01, nothing to do with insider
        # conviction. Flag via a corporate-suffix heuristic so callers can
        # exclude them without ticker-specific special-casing.
        _CORP_SUFFIXES = (" CORP", " CORPORATION", " INC", " CO", " LTD",
                         " LLC", " TRUST", " PLAN", " LP", " N.V.", " N V")
        _name_upper = re.sub(r"\s*/[A-Z]{2}/\s*$", "", (owner_name or "").upper())  # strip " /DE/" style suffix
        is_entity = bool(owner_name) and any(_name_upper.endswith(s) for s in _CORP_SUFFIXES)
        rel = owner_el.find("reportingOwnerRelationship") if owner_el is not None else None
        is_officer = (rel.findtext("isOfficer") == "true") if rel is not None else False
        is_director = (rel.findtext("isDirector") == "true") if rel is not None else False
        is_ten_pct = (rel.findtext("isTenPercentOwner") == "true") if rel is not None else False
        officer_title = rel.findtext("officerTitle") if rel is not None else None

        rows = []
        for tx in root.findall(".//nonDerivativeTransaction"):
            code = tx.findtext("transactionCoding/transactionCode")
            date = tx.findtext("transactionDate/value")
            shares_s = tx.findtext("transactionAmounts/transactionShares/value")
            price_s = tx.findtext("transactionAmounts/transactionPricePerShare/value")
            ad_code = tx.findtext("transactionAmounts/transactionAcquiredDisposedCode/value")
            shares_after_s = tx.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value")
            if not code or not date:
                continue
            try:
                shares = float(shares_s) if shares_s else None
                price = float(price_s) if price_s else None
                shares_after = float(shares_after_s) if shares_after_s else None
            except ValueError:
                shares = price = shares_after = None
            rows.append({
                "ticker": ticker, "accession": accession,
                "owner_name": owner_name, "is_officer": is_officer,
                "is_director": is_director, "is_ten_pct_owner": is_ten_pct,
                "is_entity": is_entity, "officer_title": officer_title,
                "transaction_code": code, "transaction_date": date,
                "shares": shares, "price": price, "acquired_disposed": ad_code,
                "shares_owned_after": shares_after,
            })
        return rows

    return _cached_json(f"tx_{ticker}_{accession}", _fetch)


# Real, individual conviction buys, empirically: BAC alone produced 569
# transactions from "BANK OF AMERICA CORP /DE/" filing as its own reporting
# owner (1 share at $0.01-0.02 — a benefit-plan/DRIP mechanism, not a
# person), against exactly 1 genuine transaction from a named director.
# TSM produced 139 from 32 real named individuals, but median notional was
# ~$3,800 — small, recurring purchase-plan activity, not conviction-sized.
# Both empirically confirmed 2026-07-20 against real SEC data.
MIN_PURCHASE_NOTIONAL_USD = 15_000.0


def fetch_insider_purchases(ticker: str, start_date: str, end_date: str,
                            min_notional: float = MIN_PURCHASE_NOTIONAL_USD) -> list[dict]:
    """
    The actual signal: every open-market purchase (code 'P') by a NAMED
    INDIVIDUAL officer, director, or 10%-owner of `ticker` in [start_date,
    end_date], with a known price and at least min_notional in size.
    Excludes: the issuer/a benefit-plan trust filing as its own reporting
    owner (is_entity — not a person, not conviction), and small routine
    purchases below min_notional (empirically dominated by recurring
    purchase-plan noise, not the "voluntary cash-out-of-pocket" signal the
    academic literature anchors on). One row per (insider, transaction).
    """
    cik = ticker_to_cik(ticker)
    if cik is None:
        log.warning("insider.no_cik", ticker=ticker)
        return []

    filings = list_form4_filings(ticker, start_date, end_date)
    purchases = []
    for f in filings:
        try:
            rows = fetch_form4_transactions(ticker, cik, f["accession"], f["primary_doc"])
        except Exception as e:
            log.debug("insider.filing_fetch_failed", ticker=ticker,
                     accession=f["accession"], error=str(e)[:150])
            continue
        for row in rows:
            if row["transaction_code"] != "P" or row["acquired_disposed"] != "A" \
                    or not row["price"] or not row["shares"]:
                continue
            if row.get("is_entity"):
                continue
            if row["shares"] * row["price"] < min_notional:
                continue
            row["filing_date"] = f["filing_date"]
            purchases.append(row)
    return purchases


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else datetime.today().strftime("%Y-%m-%d")
    t0 = time.time()
    purchases = fetch_insider_purchases(ticker, start, end)
    print(f"{ticker}: {len(purchases)} open-market purchases in [{start}, {end}] "
          f"({time.time()-t0:.1f}s)")
    for p in purchases[:10]:
        notional = p["shares"] * p["price"]
        print(f"  {p['transaction_date']} {p['owner_name']} "
              f"({p['officer_title'] or ('director' if p['is_director'] else 'owner')}): "
              f"{p['shares']:.0f} sh @ ${p['price']:.2f} = ${notional:,.0f}")
