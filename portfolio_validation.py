"""One-time funded, fixed-sleeve portfolio for frozen B + Supertrend 10x2.

Shared initial capital split equally into N independent cash sleeves; unused cash
is NOT redistributed. No deposits, withdrawals, interest, leverage or FX.
All events are decided on the previous CLOSED candle of the same ticker,
executed at its next available session open; portfolio valued at daily closes.
The frozen historical exit checks bearish regime, not just a fresh crossover.
"""
import numpy as np
import pandas as pd
from research_presets import prepare_preset_features

PORTFOLIO_VERSION = "LUMP-SUM-FIXED-SLEEVES-2026-11-07-v1"
FEE = 0.0015

def _risk(curve, initial):
    value = curve["Patrimonio"].to_numpy(dtype=float)
    if not len(value) or np.any(~np.isfinite(value)) or np.any(value <= 0):
        raise ValueError("Curva patrimonio non valida")
    t = pd.DatetimeIndex(curve["Data"])
    years = (t[-1] - t[0]).days / 365.2425
    if years <= 0: raise ValueError("Periodo non annualizzabile")
    peak = np.maximum.accumulate(np.r_[float(initial), value])
    drawdown = np.r_[float(initial), value] / peak - 1
    final = float(value[-1])
    cagr = (final / initial) ** (1 / years) - 1
    dd = float(drawdown.min())
    return {
        "Capitale iniziale":round(float(initial),2),
        "Capitale finale":round(final,2),
        "Rendimento totale %":100*(final/initial-1),
        "CAGR %":100*cagr,
        "Drawdown massimo MTM %":100*dd,
        "Esposizione media %":float(curve["Esposizione %"].mean()),
        "Calmar":cagr/abs(dd) if dd < -1e-12 else np.nan,
        "Sedute":len(curve),
        "Anni":years
    }

def portfolio_lump_sum(data, start, end, capital=100000.0, spy=None):
    if not data or capital <= 0 or not np.isfinite(capital):
        raise ValueError("Capitale e universo devono essere validi")
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if start >= end: raise ValueError("Il periodo deve contenere almeno due date distinte")
    instruments={}
    excluded=[]
    for symbol,frame in sorted(data.items()):
        try:
            if symbol == "SPY": continue
            if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
                raise ValueError("Date duplicate o non ordinate")
            features=prepare_preset_features(frame)
            instruments[symbol]={"frame":frame,"features":features,"cash":0.,
                                 "shares":0.,"last_close":None,"date_to_pos":{d:i for i,d in enumerate(frame.index)},
                                 "last_seen":None}
        except Exception as exc:
            excluded.append({"Ticker":symbol,"Motivo":str(exc)[:250]})
    if not instruments: raise ValueError("Nessuna serie valida dopo audit OHLC/warmup")
    slot = float(capital) / len(instruments)
    for item in instruments.values(): item["cash"]=slot
    calendars=[f.index[(f.index>=start)&(f.index<=end)] for f in data.values()]
    if spy is not None and not spy.empty:
        calendars.append(spy.index[(spy.index>=start)&(spy.index<=end)])
    days=pd.DatetimeIndex(sorted(set().union(*(set(x) for x in calendars))))
    if len(days)<2: raise ValueError("Periodo senza sedute")
    fills=[];curve=[]
    for day in days:
        for symbol,item in instruments.items():
            ix=item["date_to_pos"].get(day)
            if ix is None: continue
            df=item["frame"];f=item["features"]
            # Only closed-bar signals. No fills before the strategy's 201-bar warm-up.
            if ix >= 201:
                prev=ix-1
                exited=False
                if item["shares"]>0 and np.isfinite(f["supertrend_10x2"][prev]) and f["supertrend_10x2"][prev]==0:
                    px=float(df.open.iloc[ix]); qty=item["shares"]
                    proceeds=qty*px*(1-FEE)
                    item["cash"]+=proceeds
                    item["shares"]=0.
                    fills.append({"Data":day,"Ticker":symbol,"Lato":"SELL",
                                  "Quantita":qty,"Prezzo open":px,"Costo":qty*px*FEE,
                                  "Controvalore":qty*px})
                    exited=True
                force=f[("Heikin Ashi",7,7)]
                eligible=(np.isfinite(force[prev]) and np.isfinite(force[prev-1]) and
                          force[prev]>0 and force[prev-1]<=0 and bool(f["ha_green"][prev])
                          and float(df.close.iloc[prev])>float(f["ema200"][prev]))
                if item["shares"]==0 and not exited and eligible and item["cash"]>0:
                    px=float(df.open.iloc[ix])
                    qty=item["cash"]/(px*(1+FEE))
                    if qty>0:
                        cost=qty*px*FEE
                        item["cash"]-=qty*px+cost
                        item["shares"]=qty
                        fills.append({"Data":day,"Ticker":symbol,"Lato":"BUY",
                                      "Quantita":qty,"Prezzo open":px,"Costo":cost,
                                      "Controvalore":qty*px})
            item["last_close"]=float(df.close.iloc[ix])
        cash=sum(it["cash"] for it in instruments.values())
        invested=sum(it["shares"]*(it["last_close"] if it["last_close"] is not None else 0.)
                     for it in instruments.values())
        total=cash+invested
        curve.append({"Data":day,"Patrimonio":total,"Liquidita":cash,
                      "Investito":invested,"Esposizione %":100*invested/total if total>0 else np.nan,
                      "Posizioni aperte":sum(it["shares"]>0 for it in instruments.values())})
    portfolio_curve=pd.DataFrame(curve)
    metrics=_risk(portfolio_curve,capital)
    all_fills=pd.DataFrame(fills,columns=["Data","Ticker","Lato","Quantita","Prezzo open","Costo","Controvalore"])
    metrics["Operazioni BUY"]=int((all_fills.Lato=="BUY").sum())
    metrics["Operazioni SELL"]=int((all_fills.Lato=="SELL").sum())
    metrics["Costi commissioni totali"]=float(all_fills.Costo.sum())
    metrics["Turnover nozionale / capitale iniziale"]=float(all_fills.Controvalore.sum()/capital)
    metrics["Titoli ammessi"]=len(instruments)
    metrics["Titoli esclusi"]=len(excluded)
    metrics["Modello"]="Una tantum; quote iniziali fisse; cassa per titolo non riallocata"
    benchmark_curve=pd.DataFrame()
    benchmark_metrics=None
    if spy is not None and not spy.empty:
        # S&P 500 benchmark: entire capital invested at the first available SPY open,
        # cash before that date. Same initial capital, calendar and fees.
        sp=spy.sort_index()
        sp=sp.loc[(sp.index>=days[0])&(sp.index<=days[-1])]
        if len(sp)>=2 and sp.index[0]==days[0]:
            sp_qty=capital/(float(sp.open.iloc[0])*(1+FEE))
            last_sp=None;points=[]
            for d in days:
                if d in sp.index:
                    last_sp=float(sp.loc[d,"close"])
                marked=sp_qty*last_sp*(1-FEE) if last_sp is not None else capital
                points.append({"Data":d,"Patrimonio":marked,
                               "Esposizione %":100 if last_sp is not None else 0})
            benchmark_curve=pd.DataFrame(points)
            benchmark_metrics=_risk(benchmark_curve,capital)
    # Audit total capital conservation for sleeve balances; no capital creation.
    holdings=pd.DataFrame([{"Ticker":s,"Liquidita":it["cash"],"Azioni":it["shares"],
                            "Ultimo close":it["last_close"],"Valore":it["cash"]+
                            it["shares"]*(it["last_close"] or 0.)}
                           for s,it in instruments.items()])
    return {"curve":portfolio_curve,"fills":all_fills,"holdings":holdings,
            "metrics":metrics,"spy_curve":benchmark_curve,"spy_metrics":benchmark_metrics,
            "excluded":pd.DataFrame(excluded,columns=["Ticker","Motivo"])}
