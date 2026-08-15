import yfinance as yf

tickers = [
    "BISNIS27.JK", "IDXJII.JK", "PEFINDO25.JK", "SRIKEHATI.JK",
    "IDXPROPER.JK", "IDXSMCCOM.JK", "IDXSMCLIQ.JK", "IGRADE.JK",
    "MBX.JK", "DBX.JK", "IDXCYCLIC30.JK", "XCID",
    "COWL.JK", "DUCK.JK", "ENVY.JK", "GOLL.JK", "LCGP.JK",
    "LMAS.JK", "MABA.JK", "MTRA.JK", "SKYB.JK", "SRIL.JK",
    "SUGI.JK", "TDPM.JK",
]

for t in tickers:
    try:
        info = yf.Ticker(t).info
        qt = info.get("quoteType", "?")
        ms = info.get("marketState", "?")
        print(f"{t}: {qt} | {ms}")
    except Exception as e:
        print(f"{t}: ERROR {e}")
