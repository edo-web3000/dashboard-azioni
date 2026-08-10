"""
fetch_stock_data.py
--------------------
Scarica giornalmente da Yahoo Finance:
  1. Prezzi storici (append incrementale) -> data/prices.csv
  2. Indici fondamentali (snapshot, sovrascritto ogni giorno) -> data/fundamentals.csv

Legge la lista di ticker da monitorare da data/tickers_watchlist.csv
e aggiunge automaticamente anche i ticker presenti in data/portfolio.csv
(cosi' anche i titoli in portafoglio hanno sempre prezzo e fondamentali aggiornati).

Pensato per essere eseguito ogni giorno da GitHub Actions (vedi daily_update.yml),
ma funziona identico anche lanciato a mano in locale:
    pip install -r requirements.txt
    python fetch_stock_data.py
"""

import os
import time
import datetime as dt

import pandas as pd
import yfinance as yf

DATA_DIR = "data"
TICKERS_FILE = os.path.join(DATA_DIR, "tickers_watchlist.csv")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.csv")
PRICES_FILE = os.path.join(DATA_DIR, "prices.csv")
FUNDAMENTALS_FILE = os.path.join(DATA_DIR, "fundamentals.csv")

# Colonne fondamentali che vogliamo estrarre da yf.Ticker(t).info
# (yfinance a volte non trova tutti i campi per ogni titolo/ETF: gestito con .get())
FUNDAMENTAL_FIELDS = {
    "shortName": "Nome",
    "sector": "Settore",
    "quoteType": "Tipo",              # EQUITY / ETF
    "currency": "Valuta",
    "marketCap": "MarketCap",
    "trailingPE": "PE_Trailing",
    "forwardPE": "PE_Forward",
    "pegRatio": "PEG",
    "priceToBook": "PriceToBook",
    "enterpriseToEbitda": "EV_EBITDA",
    "ebitda": "EBITDA",
    "profitMargins": "ProfitMargin",
    "returnOnEquity": "ROE",
    "returnOnAssets": "ROA",
    "debtToEquity": "DebtToEquity",
    "dividendYield": "DividendYield",
    "beta": "Beta",
    "fiftyTwoWeekHigh": "High52w",
    "fiftyTwoWeekLow": "Low52w",
    "trailingEps": "EPS",
    "revenueGrowth": "RevenueGrowth",
}


def load_tickers() -> list[str]:
    tickers = set()

    if os.path.exists(TICKERS_FILE):
        df = pd.read_csv(TICKERS_FILE)
        tickers.update(df["Ticker"].dropna().str.strip().str.upper().tolist())

    if os.path.exists(PORTFOLIO_FILE):
        df = pd.read_csv(PORTFOLIO_FILE)
        if "Ticker" in df.columns:
            tickers.update(df["Ticker"].dropna().str.strip().str.upper().tolist())

    return sorted(tickers)


def fetch_prices(tickers: list[str], lookback_days: int = 7) -> pd.DataFrame:
    """Scarica gli ultimi N giorni di prezzo per ogni ticker (ridondanza per coprire festivi/buchi)."""
    rows = []
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period=f"{lookback_days}d", interval="1d")
            if hist.empty:
                print(f"[WARN] nessun prezzo per {t}")
                continue
            hist = hist.reset_index()
            for _, r in hist.iterrows():
                rows.append({
                    "Date": r["Date"].strftime("%Y-%m-%d"),
                    "Ticker": t,
                    "Open": round(float(r["Open"]), 4),
                    "High": round(float(r["High"]), 4),
                    "Low": round(float(r["Low"]), 4),
                    "Close": round(float(r["Close"]), 4),
                    "Volume": int(r["Volume"]),
                })
        except Exception as e:
            print(f"[ERROR] prezzi {t}: {e}")
        time.sleep(0.3)  # piccola pausa per non martellare l'API

    return pd.DataFrame(rows)


def fetch_fundamentals(tickers: list[str]) -> pd.DataFrame:
    rows = []
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    for t in tickers:
        try:
            info = yf.Ticker(t).info
            row = {"Ticker": t}
            for src_field, dst_col in FUNDAMENTAL_FIELDS.items():
                row[dst_col] = info.get(src_field)
            row["LastUpdated"] = now
            rows.append(row)
        except Exception as e:
            print(f"[ERROR] fundamentals {t}: {e}")
            rows.append({"Ticker": t, "LastUpdated": now})
        time.sleep(0.3)

    return pd.DataFrame(rows)


def merge_prices(new_prices: pd.DataFrame):
    """Fa l'append dei nuovi prezzi al file storico, evitando duplicati Date+Ticker."""
    if os.path.exists(PRICES_FILE):
        old = pd.read_csv(PRICES_FILE)
        combined = pd.concat([old, new_prices], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date", "Ticker"], keep="last")
    else:
        combined = new_prices

    combined = combined.sort_values(["Ticker", "Date"])
    combined.to_csv(PRICES_FILE, index=False)
    print(f"[OK] prices.csv aggiornato: {len(combined)} righe totali")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    tickers = load_tickers()
    if not tickers:
        print("[WARN] nessun ticker trovato in tickers_watchlist.csv o portfolio.csv")
        return

    print(f"[INFO] ticker da aggiornare: {tickers}")

    new_prices = fetch_prices(tickers)
    if not new_prices.empty:
        merge_prices(new_prices)

    fundamentals = fetch_fundamentals(tickers)
    fundamentals.to_csv(FUNDAMENTALS_FILE, index=False)
    print(f"[OK] fundamentals.csv aggiornato: {len(fundamentals)} righe")


if __name__ == "__main__":
    main()
