"""Rotazione LONG con massimo 1/2/3 posizioni e quote riservate.

B + Supertrend 10x2 congelati. Segnali soltanto a barra chiusa (t-1),
esecuzioni alla successiva apertura del rispettivo titolo (t).
Valore azioni al close con costo ipotetico di liquidazione per coerenza
con la curva del preset congelato.
Ogni slot riceve capitale iniziale / max_posizioni; il ricavato resta
nello slot per l'ingresso successivo. No cassa condivisa, leva o FX.
"""
import numpy as np
import pandas as pd
from research_presets import prepare_preset_features
from portfolio_validation import _risk, FEE

ROTATION_VERSION = "ROTATION-STOP-LAB-2026-11-08-v2"
RANKING_METHODS = ("Ticker alfabetico (baseline deterministica)",
                   "Momentum 63 sedute alla chiusura precedente")
MAX_STALE_CALENDAR_DAYS = 10
STOP_MODES = (
    "Nessuno (baseline)",
    "Stop fisso 5%",
    "Stop fisso 8%",
    "Stop ATR14 x 2",
    "Stop 8% + BE +3%",
    "Stop 8% + BE +5%",
    "Stop 5% + BE +3%",
    "Stop immediato al prezzo ingresso (100%)",
)

def _atr14(bars):
    h=bars.high.to_numpy(float)
    l=bars.low.to_numpy(float)
    c=bars.close.to_numpy(float)
    n=len(c)
    tr=np.empty(n)
    tr[0]=h[0]-l[0]
    for i in range(1,n):
        tr[i]=max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
    out=np.full(n,np.nan)
    if n>=14:
        out[13]=tr[:14].mean()
        for i in range(14,n):out[i]=(out[i-1]*13+tr[i])/14
    return out

def _stop_parameters(mode, entry_open, atr_signal):
    if mode==STOP_MODES[0]:return None,None
    if mode==STOP_MODES[1]:return entry_open*.95,None
    if mode==STOP_MODES[2]:return entry_open*.92,None
    if mode==STOP_MODES[3]:
        if not np.isfinite(atr_signal):raise ValueError("ATR mancante")
        return entry_open-2*atr_signal,None
    if mode==STOP_MODES[4]:return entry_open*.92,.03
    if mode==STOP_MODES[5]:return entry_open*.92,.05
    if mode==STOP_MODES[6]:return entry_open*.95,.03
    if mode==STOP_MODES[7]:return entry_open,None
    raise ValueError("Stop sconosciuto")


def _priority(symbol, frame, i, method):
    if method == RANKING_METHODS[0]:
        return (symbol,)
    # Performance di 63 close -> soltanto da t-64 a t-1
    if i < 64:
        return None
    old = float(frame.close.iloc[i-64])
    recent = float(frame.close.iloc[i-1])
    if not np.isfinite(old) or not np.isfinite(recent) or old <= 0:
        return None
    return (-recent / old + 1., symbol)

def _prepare(data):
    allowed,excluded = {},[]
    for symbol, frame in sorted(data.items()):
        if symbol.upper() == "SPY":
            continue
        try:
            if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
                raise ValueError("Date non ordinate o duplicate")
            features = prepare_preset_features(frame)
            allowed[symbol] = {
                "bars":frame, "features":features,
                "positions":{day:i for i,day in enumerate(frame.index)},
                "atr14":_atr14(frame)
            }
        except Exception as exc:
            excluded.append({"Ticker":symbol,"Motivo":str(exc)[:240]})
    return allowed,pd.DataFrame(excluded,columns=["Ticker","Motivo"])

def _spy_reference(spy, dates, initial):
    """SPY acquisto al primo open del calendario comune, altrimenti N/D."""
    if spy is None or spy.empty:
        return pd.DataFrame(),None
    spy=spy.sort_index()
    days=pd.DatetimeIndex(dates)
    if days[0] not in spy.index:
        return pd.DataFrame(),None
    base = float(spy.loc[days[0],"open"])
    if base<=0:
        return pd.DataFrame(),None
    qty=initial/(base*(1+FEE))
    last=None
    rows=[]
    for day in days:
        if day in spy.index:
            last=float(spy.loc[day,"close"])
        if last is None:
            return pd.DataFrame(),None
        val=qty*last*(1-FEE)
        rows.append({"Data":day,"Patrimonio":val,
                     "Esposizione %":100.})
    reference=pd.DataFrame(rows)
    return reference,_risk(reference,initial)

def rotate_reserved(data,start,end,capital=10000.,max_positions=1,
                    ranking=RANKING_METHODS[0],spy=None,_prepared=None,stop_mode=STOP_MODES[0]):
    if max_positions not in (1,2,3):
        raise ValueError("Massimo posizioni ammesso: 1, 2 o 3")
    if ranking not in RANKING_METHODS:
        raise ValueError("Graduatoria non prevista")
    if stop_mode not in STOP_MODES:
        raise ValueError("Stop sconosciuto")
    if not np.isfinite(capital) or capital<=0:
        raise ValueError("Capitale non valido")
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if start>=end:
        raise ValueError("Intervallo temporale non valido")
    universe,excluded=_prepare(data) if _prepared is None else _prepared
    if not universe:
        raise ValueError("Nessun ticker valido: controllare OHLC e warm-up")
    calendars=[info["bars"].index[(info["bars"].index>=start)&
                (info["bars"].index<=end)] for info in universe.values()]
    days=pd.DatetimeIndex(sorted(set().union(*(set(x) for x in calendars))))
    if len(days)<2:
        raise ValueError("Meno di due sessioni di mercato nel periodo")
    # Quote iniziali uguali; nessun travaso di capitale fra slot.
    slots=[{"id":i+1,"cash":float(capital)/max_positions,
            "shares":0.,"symbol":None,"last_close":None,"last_date":None,
            "entry_date":None,"entry_fill":None,
            "entry_open":None,"stop_base":None,
            "be_trigger":None,"completed_high":None} for i in range(max_positions)]
    fills=[]
    equity=[]
    eligible_count=0
    missed_count=0
    for day in days:
        just_exited=set()
        exited_tickers=set()
        # Prima aggiorna le uscite di tutte le posizioni aperte.
        for slot in slots:
            symbol=slot["symbol"]
            if symbol is None:
                continue
            info=universe[symbol];i=info["positions"].get(day)
            if i is not None:
                bars=info["bars"];feat=info["features"]
                reason=None
                px=None
                if i >= 201 and np.isfinite(feat["supertrend_10x2"][i-1]) and feat["supertrend_10x2"][i-1]==0.:
                    px=float(bars.open.iloc[i])
                    reason="Supertrend"
                elif stop_mode!=STOP_MODES[0] and slot["stop_base"] is not None:
                    stop=float(slot["stop_base"])
                    # Trigger BE based on high of completed sessions only,
                    # effective from the next open: no unknown intrabar path.
                    if (slot["be_trigger"] is not None
                        and slot["completed_high"] is not None
                        and slot["completed_high"] >= slot["entry_open"]*(1+slot["be_trigger"])):
                        stop=max(stop,slot["entry_fill"]/(1-FEE))
                    if float(bars.open.iloc[i])<=stop:
                        px=float(bars.open.iloc[i])
                        reason="Stop gap"
                    elif float(bars.low.iloc[i])<=stop:
                        px=stop
                        reason="Stop intraday"
                if reason is not None:
                    gross=slot["shares"]*px
                    fee=gross*FEE
                    slot["cash"]+=gross-fee
                    fills.append({"Data":day,"Segnale":bars.index[i-1],
                                  "Slot":slot["id"],"Ticker":symbol,"Lato":"SELL",
                                  "Prezzo open":px,"Quantita":slot["shares"],
                                  "Nozionale":gross,"Costo":fee,"Motivo":reason})
                    slot["shares"]=0.
                    slot["symbol"]=None
                    slot["last_close"]=None
                    slot["last_date"]=None
                    slot["entry_open"]=None
                    slot["stop_base"]=None
                    slot["be_trigger"]=None
                    slot["completed_high"]=None
                    just_exited.add(slot["id"])
                    exited_tickers.add(symbol)
                else:
                    slot["last_close"]=float(bars.close.iloc[i])
                    slot["last_date"]=day
                    if slot["completed_high"] is not None:
                        slot["completed_high"]=max(slot["completed_high"],float(bars.high.iloc[i]))
            if slot["symbol"] is not None and slot["last_date"] is not None:
                if (day-slot["last_date"]).days > MAX_STALE_CALENDAR_DAYS:
                    raise ValueError(f"Prezzo non aggiornato per posizione {slot['symbol']} da oltre {MAX_STALE_CALENDAR_DAYS} giorni: modello sospeso")
        # I segnali appartengono al close precedente e scadono se non acquistati
        held={slot["symbol"] for slot in slots if slot["symbol"] is not None}
        candidates=[]
        for symbol, info in universe.items():
            if symbol in held or symbol in exited_tickers:
                continue
            i=info["positions"].get(day)
            if i is None or i<201:
                continue
            feat=info["features"];bars=info["bars"];p=i-1
            force=feat[("Heikin Ashi",7,7)]
            signal=(np.isfinite(force[p]) and np.isfinite(force[p-1])
                    and force[p]>0 and force[p-1]<=0
                    and bool(feat["ha_green"][p])
                    and float(bars.close.iloc[p])>float(feat["ema200"][p]))
            if not signal:
                continue
            priority=_priority(symbol,bars,i,ranking)
            if priority is not None:
                candidates.append((priority,symbol,i))
        eligible_count+=len(candidates)
        candidates.sort(key=lambda item:item[0])
        available=[s for s in slots if s["symbol"] is None and s["id"] not in just_exited]
        for slot,(_,symbol,i) in zip(available,candidates):
            bars=universe[symbol]["bars"]
            px=float(bars.open.iloc[i])
            if px<=0: raise ValueError("Prezzo open non positivo")
            qty=slot["cash"]/(px*(1+FEE))
            if qty<=0:continue
            notional=qty*px
            fee=notional*FEE
            slot["cash"]=max(0.,slot["cash"]-notional-fee)
            slot["shares"]=qty
            slot["symbol"]=symbol
            slot["last_close"]=float(bars.close.iloc[i])
            slot["last_date"]=day
            slot["entry_date"]=day
            slot["entry_fill"]=px*(1+FEE)
            slot["entry_open"]=px
            slot["stop_base"],slot["be_trigger"]=_stop_parameters(
                stop_mode,px,universe[symbol]["atr14"][i-1])
            slot["completed_high"]=float(bars.high.iloc[i])
            fills.append({"Data":day,"Segnale":bars.index[i-1],
                          "Slot":slot["id"],"Ticker":symbol,"Lato":"BUY",
                          "Prezzo open":px,"Quantita":qty,"Nozionale":notional,"Costo":fee,"Motivo":"Ingresso B"})
            # Initial protective stop may execute on entry day.
            # For stop at entry price, require Low < Open: Low == Open alone
            # does not prove a downtick occurred after the entry fill.
            # Break-even trigger from the entry day only applies next session.
            if (slot["stop_base"] is not None
                and (float(bars.low.iloc[i])<slot["stop_base"]
                     if stop_mode==STOP_MODES[7] else
                     float(bars.low.iloc[i])<=slot["stop_base"])):
                stop_px=float(slot["stop_base"])
                gross_exit=qty*stop_px
                slot["cash"]+=gross_exit*(1-FEE)
                slot["shares"]=0.
                slot["symbol"]=None
                slot["last_close"]=None
                slot["last_date"]=None
                slot["entry_open"]=None
                slot["stop_base"]=None
                slot["be_trigger"]=None
                slot["completed_high"]=None
                fills.append({"Data":day,"Segnale":day,
                              "Slot":slot["id"],"Ticker":symbol,"Lato":"SELL",
                              "Prezzo open":stop_px,"Quantita":qty,
                              "Nozionale":gross_exit,"Costo":gross_exit*FEE,
                              "Motivo":"Stop seduta ingresso"})
        missed_count+=max(0,len(candidates)-len(available))
        invested=sum(s["shares"]*(s["last_close"] or 0.)*(1-FEE) for s in slots)
        cash=sum(s["cash"] for s in slots)
        value=invested+cash
        if value<=0: raise ValueError("Patrimonio non positivo")
        equity.append({"Data":day,"Patrimonio":value,
                       "Liquidita":cash,"Investito":invested,
                       "Esposizione %":100*invested/value,
                       "Posizioni aperte":sum(s["symbol"] is not None for s in slots)})
    curve=pd.DataFrame(equity)
    trades=pd.DataFrame(fills,columns=["Data","Segnale","Slot","Ticker","Lato","Prezzo open","Quantita","Nozionale","Costo","Motivo"])
    summary=_risk(curve,float(capital))
    summary.update({"Capacita":max_positions,"Priorita":ranking,
                    "Titoli universo":len(universe),
                    "Segnali candidati":eligible_count,
                    "Segnali non eseguiti per capacita":missed_count,
                    "Acquisti":int((trades.Lato=="BUY").sum()),
                    "Vendite":int((trades.Lato=="SELL").sum()),
                    "Costi totali":float(trades.Costo.sum()),
                    "Turnover nozionale":float(trades.Nozionale.sum()/capital),
                    "Modello":ROTATION_VERSION,"Stop":stop_mode,
                    "Uscite stop":int(((trades.Lato=="SELL") &
                    trades.Motivo.str.startswith("Stop")).sum())})
    holdings=pd.DataFrame([{"Slot":s["id"],"Ticker":s["symbol"] or "LIQUIDO",
                            "Contante":s["cash"],"Quantita":s["shares"],
                            "Valore":s["cash"]+s["shares"]*(s["last_close"] or 0.)*(1-FEE)}
                           for s in slots])
    spy_curve,spy_metrics=_spy_reference(spy,days,float(capital))
    return {"metrics":summary,"curve":curve,"fills":trades,"holdings":holdings,
            "spy_curve":spy_curve,"spy_metrics":spy_metrics,"excluded":excluded}

def compare_capacities(data,start,end,capital=10000.,rankings=RANKING_METHODS,spy=None):
    output={}
    prepared=_prepare(data)
    for method in rankings:
        for capacity in (1,2,3):
            output[(capacity,method)]=rotate_reserved(data,start,end,capital,capacity,method,spy,_prepared=prepared)
    summary=pd.DataFrame([r["metrics"] for r in output.values()])
    return summary,output
