-- TimescaleDB initialization
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- OHLCV bars
CREATE TABLE IF NOT EXISTS ohlcv_bars (
    time        TIMESTAMPTZ NOT NULL,
    ticker      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL DEFAULT '1Min',
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      BIGINT,
    vwap        DOUBLE PRECISION
);
SELECT create_hypertable('ohlcv_bars', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_time ON ohlcv_bars (ticker, time DESC);

-- Tick data
CREATE TABLE IF NOT EXISTS tick_data (
    time        TIMESTAMPTZ NOT NULL,
    ticker      TEXT        NOT NULL,
    price       DOUBLE PRECISION,
    size        INTEGER,
    bid         DOUBLE PRECISION,
    ask         DOUBLE PRECISION
);
SELECT create_hypertable('tick_data', 'time', if_not_exists => TRUE);

-- Portfolio equity curve
CREATE TABLE IF NOT EXISTS equity_curve (
    time        TIMESTAMPTZ NOT NULL,
    equity      DOUBLE PRECISION,
    cash        DOUBLE PRECISION,
    day_pnl     DOUBLE PRECISION
);
SELECT create_hypertable('equity_curve', 'time', if_not_exists => TRUE);
