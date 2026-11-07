"""Benchmark di ricerca: usa esclusivamente OHLC standard e curve mark-to-market.

Nessuna ottimizzazione, nessun cambio di regole dei segnali.
SPY confrontato su date esattamente coincidenti; se mancano barre,
benchmark non disponibile invece di interpolare.
"""
import numpy as np
import pandas as pd

FINALISTS = ("Supertrend 10x2", "Forces HA + HA rossa + trailing 5%")
FEE = 0.0015

def _metrics(equity, dates, exposure):
    e = np.asarray(equity, dtype=float)
    if len(e) < 2 or not np.isfinite(e).all() or (e <= 0).any():
        raise ValueError("Curva equity insufficiente o non valida")
    t = pd.DatetimeIndex(dates)
    years = (t[-1] - t[0]).days / 365.2425
    if years <= 0:
        raise ValueError("Periodo insufficiente per annualizzare")
    # Equity di partenza 1; il primo giorno contiene eventuali costi.
    wealth = np.r_[1.0, e]
    high = np.maximum.accumulate(wealth)
    dd = float(np.min(wealth / high - 1.0))
    total = float(e[-1] - 1.0)
    cagr = float(e[-1] ** (1.0 / years) - 1.0)
    calmar = cagr / abs(dd) if dd < -1e-12 else np.nan
    return {
        "Rendimento %": 100 * total,
        "CAGR %": 100 * cagr,
        "Drawdown %": 100 * dd,
        "Esposizione media %": 100 * float(np.mean(exposure)),
        "Calmar": float(calmar) if np.isfinite(calmar) else np.nan,
        "Anni": round(years, 3),
        "Sedute": len(e),
        "Prima barra effettiva": str(t[0].date()),
        "Ultima barra effettiva": str(t[-1].date()),
    }

def strategy_metrics(curve):
    if curve.empty or "Exposure" not in curve.columns:
        raise ValueError("Curve senza esposizione: ricalcolare il confronto")
    t = pd.to_datetime(curve["Data"])
    return _metrics(curve["Equity"], t, curve["Exposure"])

def passive_metrics(prices, dates):
    """Buy & Hold: acquisto all'open primo giorno, valorizzazione al close,
    chiusura teorica all'ultimo close, costo 0.15% su entrambi i lati.
    Nessun dividendo cash separato. Nessuna reinvestimento.
    """
    t = pd.DatetimeIndex(pd.to_datetime(dates))
    p = prices.loc[t]
    if len(p) != len(t) or p[["open", "close"]].isna().any().any():
        raise ValueError("Benchmark: barre mancanti")
    initial = float(p["open"].iloc[0]) * (1 + FEE)
    if initial <= 0:
        raise ValueError("Benchmark: prezzi non validi")
    curve = p["close"].to_numpy(dtype=float, copy=True) / initial
    curve[-1] *= (1 - FEE)
    return _metrics(curve, t, np.ones(len(t)))

def matched_benchmark(prices, dates):
    """SPY su finestra di calendario coincidente, senza riempire festività
    dei mercati diversi: usa le sue sedute effettive e le dichiara.
    """
    t = pd.DatetimeIndex(pd.to_datetime(dates))
    if prices is None or prices.empty:
        return None
    same_window = prices.loc[(prices.index >= t[0]) & (prices.index <= t[-1])]
    if len(same_window) < 2:
        return None
    return passive_metrics(same_window, same_window.index)
