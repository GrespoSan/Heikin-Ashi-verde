"""Preset di ricerca A/B/C: segnali LONG Daily, separati dal motore operativo.

Non contiene ottimizzatori; non modifica screener e backtest esistenti.
Esegue segnali su chiusure confermate, ordini all'open successivo.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import numpy as np
import pandas as pd
from engine import Indicators, calculate

PRESET_VERSION = "ABC-2026-11-07-v1"
PRESETS = {
    "A": ("Standard", "Standard"),
    "B": ("Heikin Ashi", "Standard"),
    "C": ("Standard", "Heikin Ashi"),
}
PRESET_DESCRIPTIONS = {
    "A": "Ingresso Forces 7/7 Standard; uscita Forces 10/4 Standard",
    "B": "Ingresso Forces 7/7 Heikin Ashi; uscita Forces 10/4 Standard",
    "C": "Ingresso Forces 7/7 Standard; uscita Forces 10/4 Heikin Ashi",
}


def preset_id(code):
    """ID stabile che descrive anche i costi e la regola di entrata."""
    if code not in PRESETS:
        raise ValueError("Preset sconosciuto")
    obj = {"version": PRESET_VERSION, "code": code, "sources": PRESETS[code],
           "entry": "HA verde + Forces 7/7 crossing up zero + close > EMA200",
           "exit": "Forces 10/4 <= 0", "fees_per_side": 0.0015,
           "fill": "next session open", "one_position": True}
    return sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def prepare_preset_features(df):
    """Le serie devono contenere OHLC STANDARD, mai prezzi HA importati.

    Usa esattamente il calcolo Forces dell'engine applicato alle due sorgenti.
    La media 200 è calcolata su close standard. Richiede storico di warmup.
    """
    if len(df) < 220:
        raise ValueError("Servono almeno 220 sedute con OHLC standard per EMA200 e warmup.")
    required = {"open", "high", "low", "close"}
    if not required.issubset(df):
        raise ValueError("Mancano colonne OHLC standard")
    if (df[list(required)] <= 0).any().any():
        raise ValueError("OHLC non positivi")
    if ((df.high < df[["open","close","low"]].max(axis=1)) |
        (df.low > df[["open","close","high"]].min(axis=1))).any():
        raise ValueError("Barre OHLC incoerenti; dati da verificare")
    result = {}
    for source in ("Standard", "Heikin Ashi"):
        for sma, ema in ((7,7),(10,4)):
            cfg = Indicators(sma=sma,ema=ema,forces_source=source,trend_ema=200)
            x = calculate(df,cfg)
            result[(source,sma,ema)] = x.forces.to_numpy(dtype=float)
            if source == "Standard" and sma == 7:
                result["ha_green"] = x.ha.to_numpy(dtype=bool)
                result["ema200"] = x.price_ema.to_numpy(dtype=float)
    return result


def simulate_preset(df, features, code, start=None, end=None):
    """Costo 0,15% lato acquisto e vendita, composto, capitale teorico intero.

    La posizione aperta è riportata separatamente (mark-to-market), non come trade
    realizzato. Nessun nuovo ingresso all'open di un'uscita. Nessun intraday stop.
    """
    if code not in PRESETS:
        raise ValueError("Preset sconosciuto")
    in_source, out_source = PRESETS[code]
    entry_force = features[(in_source,7,7)]
    exit_force = features[(out_source,10,4)]
    ha = features["ha_green"]
    ema200 = features["ema200"]
    closes = df.close.to_numpy(dtype=float)
    opens = df.open.to_numpy(dtype=float)
    n = len(df)
    beginning = pd.Timestamp(start) if start is not None else df.index[0]
    finish = pd.Timestamp(end) if end is not None else df.index[-1]
    # Il calcolo usa dati precedenti anche a start (warmup); le esecuzioni no.
    equity = 1.0
    top = 1.0
    worst_dd = 0.0
    position = False
    entry_price = np.nan
    entry_idx = -1
    trades = []
    curve = []
    for i in range(201,n):
        if df.index[i] < beginning or df.index[i] > finish:
            continue
        previous = i - 1
        exited = False
        if position and np.isfinite(exit_force[previous]) and exit_force[previous] <= 0:
            sell = opens[i] * (1 - 0.0015)
            ret = sell / entry_price - 1
            equity *= 1 + ret
            trades.append({
                "Ingresso": df.index[entry_idx],
                "Uscita": df.index[i],
                "Prezzo ingresso": entry_price,
                "Prezzo uscita": sell,
                "Rendimento netto %": ret*100,
                "Sedute": i - entry_idx,
            })
            position = False
            exited = True
        entry_signal = (ha[previous] and np.isfinite(entry_force[previous])
                        and np.isfinite(entry_force[previous-1])
                        and entry_force[previous] > 0 and entry_force[previous-1] <= 0
                        and closes[previous] > ema200[previous])
        if not position and not exited and entry_signal:
            entry_price = opens[i] * (1 + 0.0015)
            entry_idx = i
            position = True
        marked = equity * (closes[i] * (1-0.0015) / entry_price) if position else equity
        top = max(top, marked)
        worst_dd = min(worst_dd, marked/top-1)
        curve.append({"Data":df.index[i], "Equity":marked})
    result_equity = equity
    last_index = next((i for i in range(n-1,200,-1)
                       if beginning <= df.index[i] <= finish), None)
    if last_index is None:
        raise ValueError("Il periodo selezionato non ha sedute sufficienti.")
    marked_last = (result_equity * closes[last_index] * (1-0.0015) / entry_price
                   if position else result_equity)
    ret = [t["Rendimento netto %"] for t in trades]
    return {
        "Preset": code, "ID": preset_id(code), "Descrizione": PRESET_DESCRIPTIONS[code],
        "Trade chiusi": len(trades),
        "Vincenti %": 100*sum(x>0 for x in ret)/len(ret) if ret else np.nan,
        "Durata media": float(np.mean([t["Sedute"] for t in trades])) if trades else np.nan,
        "Rendimento realizzato %": 100*(result_equity-1),
        "Rendimento con aperta %": 100*(marked_last-1),
        "Drawdown massimo %": 100*worst_dd,
        "Posizione aperta": position,
        "Operazioni": pd.DataFrame(trades),
        "Equity": pd.DataFrame(curve),
    }
