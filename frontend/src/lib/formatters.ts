const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
const pct = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmt = {
  usd: (v: number) => usd.format(v),
  pct: (v: number) => pct.format(v / 100),
  pctRaw: (v: number) => pct.format(v),
  compact: (v: number) => compact.format(v),
  sign: (v: number) => (v >= 0 ? "+" : "") + v.toFixed(2),
  signUsd: (v: number) => (v >= 0 ? "+" : "") + usd.format(Math.abs(v)) + (v < 0 ? "" : ""),
  price: (v: number) => v >= 1000 ? usd.format(v) : `$${v.toFixed(2)}`,
};
