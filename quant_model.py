import pandas as pd
import yfinance as yf
import numpy as np

# =========================
# CONFIG
# =========================
EXCEL_PATH = r"C:\Users\soysauce\OneDrive\桌面\Quant Port\portfolio.xlsx"

# =========================
# 1. LOAD TICKERS
# =========================
tickers_df = pd.read_excel(EXCEL_PATH, sheet_name="Tickers")
tickers = tickers_df["Ticker"].dropna().tolist()

results = []

# =========================
# 2. DOWNLOAD DATA SAFELY
# =========================
for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)

        # retry loop (fixes Yahoo glitches like SQ)
        hist = None
        for _ in range(3):
            hist = stock.history(period="6mo", interval="1d", auto_adjust=True)
            if hist is not None and not hist.empty:
                break

        if hist is None or hist.empty or len(hist) < 60:
            print(f"Skipping {ticker} (no valid data)")
            continue

        info = stock.info

        current = hist["Close"].iloc[-1]
        price_3m = hist["Close"].iloc[-63] if len(hist) >= 63 else hist["Close"].iloc[0]
        price_6m = hist["Close"].iloc[0]

        mom3 = (current / price_3m) - 1
        mom6 = (current / price_6m) - 1

        results.append({
            "Ticker": ticker,
            "Current Price": current,
            "P/E": info.get("trailingPE"),
            "P/B": info.get("priceToBook"),
            "ROE": info.get("returnOnEquity"),
            "Debt to Equity": info.get("debtToEquity"),
            "Dividend Yield": info.get("dividendYield"),
            "3M Momentum": mom3,
            "6M Momentum": mom6
        })

    except Exception as e:
        print(f"Error with {ticker}: {e}")

df = pd.DataFrame(results)

# =========================
# 3. CLEAN DATA
# =========================
df = df.replace([np.inf, -np.inf], np.nan)

# drop rows missing key inputs
df = df.dropna(subset=["P/E", "P/B", "ROE", "3M Momentum", "6M Momentum"])

if len(df) < 2:
    print("Not enough valid stocks after cleaning.")
    exit()

# safe std (avoid divide-by-zero crashes)
def safe_zscore(series, invert=False):
    if series.std() == 0:
        return 0
    z = (series - series.mean()) / series.std()
    return -z if invert else z

# =========================
# 4. FACTOR SCORES
# =========================

# VALUE (lower is better)
df["Z_PE"] = safe_zscore(df["P/E"], invert=True)
df["Z_PB"] = safe_zscore(df["P/B"], invert=True)
value = (df["Z_PE"] + df["Z_PB"]) / 2

# MOMENTUM
df["Z_Mom3M"] = safe_zscore(df["3M Momentum"])
df["Z_Mom6M"] = safe_zscore(df["6M Momentum"])
momentum = (df["Z_Mom3M"] + df["Z_Mom6M"]) / 2

# QUALITY
df["Z_ROE"] = safe_zscore(df["ROE"])
quality = df["Z_ROE"]

# GROWTH (proxy = momentum for now)
growth = df["Z_Mom6M"]

# LOW RISK
df["Z_Debt"] = safe_zscore(df["Debt to Equity"], invert=True)
risk = df["Z_Debt"]

# =========================
# 5. COMPOSITE SCORE
# =========================
df["Score"] = (
    0.25 * value +
    0.25 * momentum +
    0.20 * quality +
    0.20 * growth +
    0.10 * risk
)

# =========================
# 6. RANKING
# =========================
df = df.sort_values("Score", ascending=False)
df["Rank"] = range(1, len(df) + 1)

# =========================
# 7. EXPORT TO EXCEL
# =========================
with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    df.to_excel(writer, sheet_name="Analysis", index=False)

print("Done — Analysis updated successfully.")