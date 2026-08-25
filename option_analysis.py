import pandas as pd
import numpy as np
import yfinance as yf

from vollib.black_scholes.greeks.analytical import (
    delta,
    gamma,
    theta,
    vega
)


# =========================
# CONFIG
# =========================

EXCEL_PATH = r"C:\Users\soysauce\OneDrive\桌面\Quant Port\portfolio.xlsx"

RISK_FREE_RATE = 0.04


# =========================
# TICKER CONVERSION
# =========================

def fix_ticker(ticker):

    canadian = [
        "CNQ",
        "SU",
        "CVE",
        "MFC",
        "TRP",
        "ENB"
    ]

    if ticker in canadian:
        return ticker + ".TO"

    return ticker



# =========================
# LOAD STOCKS
# =========================

tickers_df = pd.read_excel(
    EXCEL_PATH,
    sheet_name="Tickers"
)


tickers = (
    tickers_df["Ticker"]
    .dropna()
    .tolist()
)



analysis = pd.read_excel(
    EXCEL_PATH,
    sheet_name="Analysis"
)



stocks = analysis[
    analysis["Ticker"].isin(tickers)
]


stocks = stocks.sort_values(
    "Score",
    ascending=False
)



print(
    "Stocks to scan:",
    len(stocks)
)



# =========================
# RESULTS
# =========================

results = []


rejected = {

    "no_options":0,
    "liquidity":0,
    "moneyness":0,
    "spread":0,
    "delta":0,
    "theta":0,
    "iv":0,
    "greeks":0

}



# =========================
# MAIN SCANNER
# =========================

for _, row in stocks.iterrows():


    original_ticker = row["Ticker"]

    ticker = fix_ticker(
        original_ticker
    )

    stock_score = row["Score"]


    print(
        "\nScanning",
        ticker
    )


    try:

        stock = yf.Ticker(ticker)


        hist = stock.history(
            period="5d"
        )


        if hist.empty:
            continue


        current_price = (
            hist["Close"]
            .iloc[-1]
        )


        expirations = stock.options


        if len(expirations) == 0:

            rejected["no_options"] += 1

            continue



    except Exception as e:

        print(
            ticker,
            e
        )

        continue



    today = pd.Timestamp.today().normalize()



    # =========================
    # EXPIRATIONS
    # =========================

    for expiry in expirations:


        expiry_date = pd.to_datetime(
            expiry
        )


        days = (
            expiry_date - today
        ).days



        if days < 1 or days > 45:

            continue



        try:

            chain = stock.option_chain(
                expiry
            )


            # =====================
            # TEMP DEBUG — raw chain inspection
            # Prints the FULL unfiltered call chain for NVDA's first
            # matching expiry so we can see where real volume/OI sits
            # relative to spot, before any of our filters touch it.
            # Remove this block once we've diagnosed the issue.
            # =====================

            if ticker == "NVDA":

                debug_chain = chain.calls.copy()

                debug_chain["moneyness"] = (
                    debug_chain["strike"] / current_price
                )

                print(
                    "\n===== RAW CHAIN DEBUG:",
                    ticker,
                    expiry,
                    "spot:",
                    round(current_price, 2),
                    "====="
                )

                print(
                    debug_chain[
                        ["strike", "moneyness", "volume", "openInterest", "bid", "ask", "impliedVolatility"]
                    ].to_string()
                )

                print(
                    "===== END RAW CHAIN DEBUG =====\n"
                )


            calls = chain.calls



            calls = calls[
                (calls["bid"] > 0)
                &
                (calls["ask"] > 0)
            ]



            if calls.empty:

                continue



            calls["volume"] = (
                calls["volume"]
                .fillna(0)
            )


            calls["openInterest"] = (
                calls["openInterest"]
                .fillna(0)
            )



            # =====================
            # LIQUIDITY
            # =====================

            calls = calls[

                (calls["volume"] >= 1)

                |

                (calls["openInterest"] >= 5)

            ]



            if calls.empty:

                rejected["liquidity"] += 1

                continue



            # =====================
            # OPTIONS LOOP
            # =====================

            for _, option in calls.iterrows():


                strike = float(
                    option["strike"]
                )


                bid = float(
                    option["bid"]
                )


                ask = float(
                    option["ask"]
                )


                volume = option["volume"]

                oi = option["openInterest"]


                iv = float(
                    option["impliedVolatility"]
                )



                # Fix IV format

                if iv > 5:

                    iv = iv / 100

                # Filter out garbage/stale IV quotes (too low or too high
                # to be real market data)
                if iv < 0.05 or iv > 3:
                    continue

                # =====================
                # MONEYNESS FILTER
                # =====================

                moneyness = (
                    strike / current_price
                )
                print(
                    ticker,
                    "Stock:",
                     round(current_price,2),
                     "Strike:",
                    strike,
                    "Moneyness:",
                    round(moneyness,3)
                )



                if (
                    moneyness < 0.7
                    or
                    moneyness > 1.5
                ):

                    rejected["moneyness"] += 1

                    continue



                premium = (

                    bid + ask

                ) / 2



                if premium <= 0:

                    continue



                spread = (

                    ask - bid

                ) / premium



                if spread > 0.20:

                    rejected["spread"] += 1

                    continue



                t = days / 365



                try:


                    d = delta(

                        "c",

                        current_price,

                        strike,

                        t,

                        RISK_FREE_RATE,

                        iv

                    )


                    g = gamma(

                        "c",

                        current_price,

                        strike,

                        t,

                        RISK_FREE_RATE,

                        iv

                    )


                    th = theta(

                        "c",

                        current_price,

                        strike,

                        t,

                        RISK_FREE_RATE,

                        iv

                    )


                    v = vega(

                        "c",

                        current_price,

                        strike,

                        t,

                        RISK_FREE_RATE,

                        iv

                    )



                except Exception:

                    rejected["greeks"] += 1

                    continue



                # Debug

                print(

                    ticker,

                    "Strike:",
                    strike,

                    "Delta:",
                    round(d,3),

                    "IV:",
                    round(iv,3)

                )



                # =====================
                # GREEK FILTERS
                # =====================


                if d < 0.5 or d > 0.9:
                    print(f"  REJECTED delta={round(d,3)} strike={strike} moneyness={round(moneyness,3)}")
                    rejected["delta"] += 1

                    continue


                if iv > 0.7:

                    rejected["iv"] += 1

                    continue

                if th < -0.10:
                    print(f"  REJECTED theta={round(th,4)} strike={strike}")
                    rejected["theta"] += 1

                    continue


                # =====================
                # OPTION SCORE
                # =====================


                liquidity_score = (

                    np.log1p(volume)

                    +

                    np.log1p(oi)

                )


                delta_score = (

                    1 -

                    abs(d - 0.60)

                )


                theta_score = (

                    1 + th

                )


                iv_score = (

                    1 - iv

                )



                option_score = (

                    0.35 * stock_score

                    +

                    0.25 * delta_score

                    +

                    0.20 * liquidity_score

                    +

                    0.10 * theta_score

                    +

                    0.10 * iv_score

                )



                results.append({

                    "Ticker": original_ticker,

                    "Yahoo Ticker": ticker,

                    "Stock Score": stock_score,

                    "Option Score": option_score,

                    "Stock Price": current_price,

                    "Expiry": expiry,

                    "Days": days,

                    "Strike": strike,

                    "Premium": premium,

                    "Delta": d,

                    "Gamma": g,

                    "Theta": th,

                    "Vega": v,

                    "IV": iv,

                    "Volume": volume,

                    "Open Interest": oi,

                    "Spread": spread

                })



        except Exception as e:

            print(
                ticker,
                expiry,
                e
            )



# =========================
# EXPORT
# =========================

df = pd.DataFrame(results)



if not df.empty:

    df = df.sort_values(
        "Option Score",
        ascending=False
    )



with pd.ExcelWriter(

    EXCEL_PATH,

    engine="openpyxl",

    mode="a",

    if_sheet_exists="replace"

) as writer:


    df.to_excel(

        writer,

        sheet_name="OptionAnalysis",

        index=False

    )



print(
    "\n========== COMPLETE =========="
)


print(
    len(df),
    "contracts saved"
)


print(
    "\nRejection Report"
)


print(
    rejected
)



if not df.empty:

    print(
        "\nTOP OPTIONS"
    )

    print(
        df.head(20)
    )
    import yfinance as yf

t = yf.Ticker("AAPL")
expiries = t.options
print("Expiries:", expiries[:3])

chain = t.option_chain(expiries[0])
print(chain.calls[["strike", "bid", "ask", "volume", "openInterest", "impliedVolatility"]].head(20))