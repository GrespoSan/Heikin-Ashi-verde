"""Ablazioni isolate dell'ingresso, con uscita e costi del preset Supertrend storico.

Non modifica research_presets.py o il protocollo congelato AB-FIVE-EXITS.
L'uscita replica deliberatamente la condizione storica: regime ST ribassista
alla chiusura precedente (anche se non è un nuovo incrocio).
"""
import numpy as np
import pandas as pd
from research_presets import prepare_preset_features, simulate_preset
from validation_benchmarks import strategy_metrics, passive_metrics, matched_benchmark

ABLATION_VERSION = "ENTRY-ABLATION-2026-11-07-v1"
VARIANTS = {
    "B completo (riferimento)": ("Heikin Ashi", True, True, True),
    "B senza HA verde": ("Heikin Ashi", False, True, True),
    "B senza EMA200": ("Heikin Ashi", True, False, True),
    "B Forces positivo (non crossing)": ("Heikin Ashi", True, True, False),
    "A completo (Standard 7/7)": ("Standard", True, True, True),
}
SIDE_COST = 0.0015

def simulate_entry_ablation(df, features, variant, start=None, end=None):
    if variant not in VARIANTS:
        raise ValueError("Variante non prevista dal protocollo")
    src, need_ha, need_ema, need_cross = VARIANTS[variant]
    f = features[(src, 7, 7)]
    ha = features["ha_green"]
    ema200 = features["ema200"]
    st = features["supertrend_10x2"]
    dates = pd.DatetimeIndex(df.index)
    op = df.open.to_numpy(dtype=float)
    cl = df.close.to_numpy(dtype=float)
    a = pd.Timestamp(start) if start is not None else dates[0]
    b = pd.Timestamp(end) if end is not None else dates[-1]
    if a > b:
        raise ValueError("Date di test invertite")
    equity = 1.0
    invested = False
    entry_price = 0.0
    trade_capital = 0.0
    peak = 1.0
    worst = 0.0
    trades = []
    curve = []
    entry_count = 0
    for i in range(201,len(df)):
        if not a <= dates[i] <= b:
            continue
        prev = i-1
        exited = False
        if invested and np.isfinite(st[prev]) and st[prev] == 0.0:
            sell = op[i] * (1 - SIDE_COST)
            equity = trade_capital * (sell / entry_price)
            invested = False
            exited = True
            trades.append((dates[i], 100 * (sell / entry_price - 1)))
        eligible = (
            np.isfinite(f[prev]) and f[prev] > 0
            and (not need_cross or (np.isfinite(f[prev-1]) and f[prev-1] <= 0))
            and (not need_ha or bool(ha[prev]))
            and (not need_ema or cl[prev] > ema200[prev])
        )
        if not invested and not exited and eligible:
            entry_price = op[i] * (1 + SIDE_COST)
            trade_capital = equity
            invested = True
            entry_count += 1
        marked = trade_capital * cl[i] * (1-SIDE_COST) / entry_price if invested else equity
        peak = max(peak,marked)
        worst = min(worst,marked/peak-1)
        curve.append({"Data":dates[i],"Equity":marked,"Exposure":1.0 if invested else 0.0})
    if not curve:
        raise ValueError("Nessuna barra valutabile")
    frame = pd.DataFrame(curve)
    metrics = strategy_metrics(frame)
    metrics["Ingressi"] = entry_count
    metrics["Trade chiusi"] = len(trades)
    metrics["Posizione aperta"] = invested
    metrics["Operazioni complete equivalenti"] = len(trades) + (0.5 if invested else 0)
    metrics["Turnover approssimato (lati)"] = 2*len(trades)+(1 if invested else 0)
    return metrics, frame

def audit_reference_match(df, features, start, end, tolerance=1e-9):
    """Controllo obbligatorio: la B completa deve replicare il motore congelato."""
    metrics, curve = simulate_entry_ablation(df,features,"B completo (riferimento)",start,end)
    historic = simulate_preset(df,features,"B",start,end,exit_method="Supertrend 10x2")
    difference = abs(metrics["Rendimento %"] - historic["Rendimento con aperta %"])
    if not np.isfinite(difference) or difference > tolerance:
        raise AssertionError(f"Divergenza B congelato/ablazione: {difference:.10g} punti percentuali")
    dd_difference = abs(metrics["Drawdown %"] - historic["Drawdown massimo %"])
    if dd_difference > tolerance:
        raise AssertionError(f"Divergenza drawdown B congelato/ablazione: {dd_difference:.10g} pp")
    if metrics["Trade chiusi"] != historic["Trade chiusi"]:
        raise AssertionError("Numero operazioni non coerente con B congelato")
    return True

def evaluate_ablation_universe(data, start, end, benchmark=None):
    """Usa solo dati OHLC già caricati in app; nessun fetch/fallback o ottimizzazione."""
    results, rejected = [], []
    for ticker,df in data.items():
        try:
            features = prepare_preset_features(df)
            audit_reference_match(df,features,start,end)
            for variant in VARIANTS:
                metrics, curve = simulate_entry_ablation(df,features,variant,start,end)
                dates = pd.DatetimeIndex(curve["Data"])
                buy = passive_metrics(df,dates)
                spy = matched_benchmark(benchmark,dates)
                results.append({
                    "Ticker":ticker, "Variante":variant, **metrics,
                    "Buy & Hold CAGR %":buy["CAGR %"],
                    "Differenza CAGR vs titolo (pp)":metrics["CAGR %"]-buy["CAGR %"],
                    "SPY CAGR %":spy["CAGR %"] if spy else np.nan,
                    "Differenza CAGR vs SPY (pp)":metrics["CAGR %"]-spy["CAGR %"] if spy else np.nan
                })
        except Exception as exc:
            rejected.append({"Ticker":ticker,"Motivo":str(exc)[:300]})
    return pd.DataFrame(results), pd.DataFrame(rejected)
