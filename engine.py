"""Motore LONG Daily/Weekly, indipendente da Streamlit e dalle fonti dati."""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import re
import numpy as np
import pandas as pd
MODULES = {
    'ha': 'HA verde', 'hull_signal': 'Hull LONG recente', 'hull_trend': 'Hull BULL',
    'forces_positive': 'Forces positivo', 'forces_strong': 'Forces in rafforzamento',
    'forces_direction': 'Forces direzione LONG', 'ema_filter': 'Prezzo sopra EMA',
}
@dataclass(frozen=True)
class Indicators:
    sma: int = 3
    ema: int = 3
    forces_source: str = 'Standard'
    short_term: bool = False
    lag: int = 1
    hull: int = 16
    memory: int = 3
    atr: int = 14
    trend_ema: int = 21
@dataclass(frozen=True)
class Rules:
    modules: tuple = ('ha', 'forces_positive')
    entry: str = 'Primo allineamento'
    exit: str = 'HA rossa'
    holding: int = 10
    stop: str = 'Nessuno'
    atr_multiple: float = 2.0
    stop_pct: float = 3.0
    target_r: float = 0.0
    capital: float = 10000.0
    allocation: float = 100.0
    commission_pct: float = 0.10
    commission_fixed: float = 0.0
    slippage_pct: float = 0.05
    tick: float = 0.001
    instrument: str = 'Azioni / ETF / spot'
    point_value: float = 1.0
    contracts: int = 1
    currency: str = 'EUR'
def config_id(ind, rules):
    return hashlib.sha256(json.dumps({'indicatori': asdict(ind), 'regole': asdict(rules)}, sort_keys=True).encode()).hexdigest()[:12]
def parse_symbols(text, market='Italia', source='Yahoo'):
    out=[]
    for line in text.lstrip('\ufeff').splitlines():
        line=line.split('#',1)[0].strip()
        if not line: continue
        if ';' in line or '\t' in line:
            parts=re.split(r'[;\t]',line); tokens=[parts[-1]]
        else: tokens=re.split(r'[,\s]+',line)
        for token in tokens:
            t=token.strip().strip('\"\'').upper()
            if not t or t in {'TICKER','TICKERS','SYMBOL','SIMBOLO'}: continue
            if t.startswith(('MIL:', 'MIL_LS:')): t=t.split(':',1)[1]+'.MI'
            elif ':' in t: t=t.split(':',1)[1]
            if source=='Yahoo' and market=='Italia' and '.' not in t and '=' not in t and not t.startswith('^'):
                t += '.MI'
            if source=='Alpaca' and (t.endswith('.MI') or '=F' in t):
                raise ValueError(f'{t}: Alpaca azioni copre i titoli USA; scegliere Yahoo o importazione.')
            if not re.fullmatch(r'[A-Z0-9.^=/_-]+',t): raise ValueError(f'Ticker non valido: {t}')
            if t not in out: out.append(t)
    return out
def normalize_bars(df,repair=False,validate=True):
    x=df.copy()
    x.columns=[str(c).lower().strip() for c in x.columns]
    x=x.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume','t':'timestamp'})
    timecol=next((c for c in ('date','datetime','timestamp','time') if c in x),None)
    if timecol:
        vals=x.pop(timecol)
        if pd.api.types.is_numeric_dtype(vals):
            idx=pd.to_datetime(vals,unit='ms' if vals.abs().max()>1e11 else 's',utc=True)
        else: idx=pd.to_datetime(vals,utc=True)
        x.index=pd.DatetimeIndex(idx).tz_convert(None).normalize()
    else:
        idx=pd.DatetimeIndex(x.index)
        if idx.tz is not None: idx=idx.tz_localize(None)
        x.index=idx.normalize()
    if not all(k in x for k in ('open','high','low','close')): raise ValueError('Servono Date, Open, High, Low, Close (Volume opzionale).')
    if 'volume' not in x: x['volume']=0.0
    x=x[['open','high','low','close','volume']].apply(pd.to_numeric,errors='coerce')
    if x[['open','high','low','close']].isna().any().any(): raise ValueError('OHLC mancanti o non numerici: correggere la fonte.')
    if not np.isfinite(x[['open','high','low','close']].to_numpy()).all(): raise ValueError('OHLC non finiti.')
    if x.index.has_duplicates: raise ValueError('Date duplicate: caricare una sola serie Daily per simbolo.')
    bad=(x.high<x[['open','close','low']].max(axis=1)-1e-9)|(x.low>x[['open','close','high']].min(axis=1)+1e-9)
    if bad.any() and (validate or repair):
        if not repair:
            dates=', '.join(str(d.date()) for d in x.index[bad][:3])
            raise ValueError(f'{int(bad.sum())} barre OHLC incoerenti ({dates}). Scegli un periodo diverso o abilita la correzione esplicita High/Low.')
        originals=x.loc[bad].reset_index().copy()
        x.attrs['ohlc_corrections']=json.loads(originals.to_json(orient='records',date_format='iso'))
        x['high']=x[['high','open','close']].max(axis=1)
        x['low']=x[['low','open','close']].min(axis=1)
    return x.sort_index()
def resample_weekly(df):
    agg={'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    if 'ohlc_valid' in df:agg['ohlc_valid']='all'
    result=df.resample('W-FRI').agg(agg).dropna(subset=['open'])
    result.attrs=dict(df.attrs)
    return result

def invalid_ohlc(df):
    bad=(df.high<df[['open','close','low']].max(axis=1)-1e-9)|(df.low>df[['open','close','high']].min(axis=1)+1e-9)
    if 'ohlc_valid' in df:bad=bad|~df.ohlc_valid
    return bad

def warmup_bars(cfg):
    return max(100,5*cfg.ema+cfg.sma,cfg.hull+int(math.sqrt(cfg.hull))+2,cfg.atr)

def prepare_features(df,cfg,start=None,end=None):
    # Lo screener riparte dall'ultimo tratto pulito. Il backtest non attraversa anomalie.
    x=df.loc[:pd.Timestamp(end)].copy() if end is not None else df.copy()
    if x.empty:raise ValueError('Nessuna barra nel periodo richiesto.')
    bad=invalid_ohlc(x)
    if start is not None:
        a=pd.Timestamp(start)
        relevant=bad & (x.index>=a)
        if relevant.any():
            dates=', '.join(str(v.date()) for v in x.index[relevant][:3])
            raise ValueError(f'{int(relevant.sum())} barre OHLC incoerenti nel periodo del test ({dates}). Riduci il periodo o scegli esplicitamente la correzione e ricarica i dati.')
        positions=np.flatnonzero(x.index>=a)
        if not len(positions):raise ValueError('Nessuna barra nel periodo del test.')
        first=int(positions[0])
        previous=np.flatnonzero(bad.to_numpy() & (np.arange(len(x))<first))
    else:previous=np.flatnonzero(bad.to_numpy())
    cut=int(previous[-1])+1 if len(previous) else 0
    segment=x.iloc[cut:].copy()
    if segment.empty:raise ValueError('Ultima candela chiusa incoerente: nessun segnale verificabile. Attendi dati aggiornati o valuta la correzione esplicita.')
    if start is not None and cut and int((segment.index<pd.Timestamp(start)).sum())<warmup_bars(cfg):
        suggested=segment.index[min(warmup_bars(cfg),len(segment)-1)].date()
        raise ValueError(f'Storico pulito insufficiente prima del test dopo l’ultima anomalia. Servono {warmup_bars(cfg)} barre di riscaldamento; prima data candidata: {suggested}.')
    result=calculate(segment,cfg)
    result.attrs['quality_restart']=str(segment.index[0].date()) if cut else None
    return result

def wma(s,n):
    weights=np.arange(1,n+1,dtype=float)
    return s.rolling(n).apply(lambda a: np.dot(a,weights)/weights.sum(),raw=True)
def calculate(df,cfg):
    if min(cfg.sma,cfg.ema,cfg.lag,cfg.memory,cfg.atr,cfg.trend_ema)<1 or cfg.hull<2: raise ValueError('Periodi non validi.')
    x=df.copy();hc=(x.open+x.high+x.low+x.close)/4
    ho=np.empty(len(x))
    if not len(x): raise ValueError('Nessuna barra disponibile.')
    ho[0]=(x.open.iloc[0]+x.close.iloc[0])/2
    for i in range(1,len(x)): ho[i]=(ho[i-1]+hc.iloc[i-1])/2
    x['ha_open']=ho; x['ha_close']=hc
    x['ha_high']=pd.concat([x.high,x.ha_open,hc],axis=1).max(axis=1)
    x['ha_low']=pd.concat([x.low,x.ha_open,hc],axis=1).min(axis=1)
    x['ha']=hc>=ho
    body=2*((hc-x.ha_open) if cfg.forces_source=='Heikin Ashi' else (x.close-x.open))
    up=body.clip(lower=0).rolling(cfg.sma).mean();dn=(-body).clip(lower=0).rolling(cfg.sma).mean()
    x['av1']=up.ewm(alpha=2/(cfg.ema+1),adjust=False).mean()
    x['av2']=dn.ewm(alpha=2/(cfg.ema+1),adjust=False).mean()
    f=x.av1-x.av2;x['forces']=f;x['forces_positive']=f>0
    x['forces_strong']=(f>0)&((np.sign(f)!=np.sign(f.shift()))|(f.abs()>f.shift().abs()))&f.shift().notna()
    slope=np.sign(f.diff().fillna(0));step=slope if cfg.short_term else np.sign(f.fillna(0));run=0;direction=[]
    for j,v in enumerate(step):
        if pd.notna(f.iloc[j]):run=0 if v==0 else (run+1 if run>0 else 1) if v>0 else (run-1 if run<0 else -1)
        direction.append(np.sign(run) if cfg.short_term and abs(run)>=cfg.lag else np.sign(f.iloc[j]))
    x['forces_direction']=np.array(direction)>0
    length=cfg.hull;hma=wma(2*wma(x.close,int(math.floor(length/2+0.5)))-wma(x.close,length),int(math.floor(math.sqrt(length)+0.5)))
    x['hull']=hma;x['hull_trend']=hma>hma.shift();age=[];last=None;prev=False
    for i,bull in enumerate(x.hull_trend):
        if bull!=prev:last=i
        age.append(i-last if last is not None else np.nan);prev=bull
    x['hull_age']=age;x['hull_signal']=x.hull_trend & (x.hull_age<cfg.memory)
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    # Wilder RMA inizializzata alla prima SMA completa (Pine ta.atr).
    atr=np.full(len(x),np.nan)
    if len(x)>=cfg.atr:
        atr[cfg.atr-1]=tr.iloc[:cfg.atr].mean()
        for i in range(cfg.atr,len(x)):atr[i]=atr[i-1]+(tr.iloc[i]-atr[i-1])/cfg.atr
    x['atr']=atr
    x['price_ema']=x.close.ewm(span=cfg.trend_ema,adjust=False).mean()
    x['ema_filter']=(x.close>x.price_ema)&(np.arange(len(x))>=cfg.trend_ema-1)
    x['ready']=np.arange(len(x))>=warmup_bars(cfg)
    return x
def evaluate(x,modules):
    if any(k not in MODULES for k in modules):raise ValueError('Modulo sconosciuto.')
    if not modules:return pd.Series(False,index=x.index)
    return x[list(modules)].all(axis=1)&x.ready

def backtest(x,rules,start=None,end=None):
    r=rules
    if r.capital<=0 or r.tick<=0 or r.point_value<=0 or not 0<r.allocation<=100:raise ValueError('Capitale, tick, valore punto e allocazione non validi.')
    if r.contracts<1 or r.holding<1 or r.stop_pct<=0 or r.atr_multiple<=0:raise ValueError('Quantità, barre e distanze stop devono essere positive.')
    if min(r.commission_pct,r.commission_fixed,r.slippage_pct,r.target_r)<0:raise ValueError('Costi o target negativi.')
    if r.target_r and r.stop=='Nessuno':raise ValueError('Un target in R richiede uno stop.')
    if (x[['open','close']]<=0).any().any():raise ValueError('Questa versione non supporta prezzi non positivi; scegliere una serie/periodo compatibile.')
    signal=evaluate(x,r.modules);a=pd.Timestamp(start) if start else x.index[0];b=pd.Timestamp(end) if end else x.index[-1]
    ids=np.flatnonzero((x.index>=a)&(x.index<=b))
    if len(ids)<2:raise ValueError('Periodo troppo breve: servono almeno due barre.')
    cash=r.capital;pos=None;pending_entry=None;pending_exit=False;trades=[];equity=[];skipped=0
    point=r.point_value if r.instrument=='Futures (contratto singolo)' else 1.0
    def fill(price,buy):return float(price)*(1+r.slippage_pct/100 if buy else 1-r.slippage_pct/100)
    def fee(price,qty):return abs(price*qty*point)*r.commission_pct/100+qty*r.commission_fixed
    def exit_position(i,raw,reason):
        nonlocal cash,pos
        out=fill(raw,False);cost=fee(out,pos['qty']);gross=(out-pos['entry'])*pos['qty']*point
        cash+=gross-cost;net=gross-cost-pos['entry_fee']
        trades.append({'Segnale':pos['signal_date'],'Ingresso':pos['date'],'Uscita':x.index[i], 'Prezzo ingresso':pos['entry'], 'Prezzo uscita':out,'Quantità':pos['qty'],'Stop':pos['stop'],'Target':pos['target'],'Motivo':reason,'PnL netto':net,'Costi':pos['entry_fee']+cost,'Barre':i-pos['i']+1,'Netto % capitale ingresso':net/pos['capital']*100})
        pos=None
    for i in ids:
        row=x.iloc[i]
        # Gli ordini decisi al close precedente si eseguono su open reale.
        if pos is not None and pending_exit:exit_position(i,row.open,'Uscita '+r.exit)
        pending_exit=False
        if pos is None and pending_entry is not None and cash>0:
            j=pending_entry;pending_entry=None;en=fill(row.open,True)
            stop=np.nan
            if r.stop=='Minimo candela segnale':stop=math.floor((x.low.iloc[j]-r.tick)/r.tick+1e-8)*r.tick
            elif r.stop=='ATR':stop=en-x.atr.iloc[j]*r.atr_multiple
            elif r.stop=='Percentuale':stop=en*(1-r.stop_pct/100)
            if np.isfinite(stop):stop=math.floor(stop/r.tick+1e-8)*r.tick
            if (r.stop!='Nessuno' and (not np.isfinite(stop) or row.open<=stop or en<=stop)):
                skipped+=1
            else:
                qty=float(r.contracts) if r.instrument=='Futures (contratto singolo)' else cash*r.allocation/100/(en*(1+r.commission_pct/100)+r.commission_fixed)
                cost=fee(en,qty);before=cash
                if qty>0 and cost<cash:
                    cash-=cost
                    pos={'entry':en,'qty':qty,'entry_fee':cost,'stop':stop,'target':en+(en-stop)*r.target_r if r.target_r and np.isfinite(stop) else np.nan,'date':x.index[i],'signal_date':x.index[j],'i':i,'capital':before}
        if pos is not None:
            stop=pos['stop'];target=pos['target']
            if np.isfinite(stop) and row.open<=stop:exit_position(i,row.open,'Gap stop')
            elif np.isfinite(target) and row.open>=target:exit_position(i,row.open,'Gap target')
            # Se high e low attraversano entrambi i livelli: stop prima, ipotesi prudente.
            elif np.isfinite(stop) and row.low<=stop:exit_position(i,stop,'Stop')
            elif np.isfinite(target) and row.high>=target:exit_position(i,target,'Target')
        if pos is not None:
            if r.exit=='HA rossa':pending_exit=not bool(row.ha)
            elif r.exit=='Hull BEAR':pending_exit=not bool(row.hull_trend)
            elif r.exit=='Forces non positivo':pending_exit=bool(row.forces<=0)
            elif r.exit=='Allineamento perso':pending_exit=not bool(signal.iloc[i])
            elif r.exit=='Numero barre':pending_exit=i-pos['i']+1>=r.holding
        # Permette un nuovo segnale al close dopo un'uscita intraday nella stessa barra.
        if pos is None and i<ids[-1] and signal.iloc[i] and cash>0:
            first=i>0 and not bool(signal.iloc[i-1])
            if r.entry=='Ogni allineamento da flat' or first:pending_entry=i
        marked=cash+(float(row.close)-pos['entry'])*pos['qty']*point if pos is not None else cash
        equity.append((x.index[i],marked))
    eq=pd.Series(dict(equity),name='Equity');t=pd.DataFrame(trades)
    pnl=t['PnL netto'] if len(t) else pd.Series(dtype=float)
    gains=pnl[pnl>0].sum();loss=-pnl[pnl<0].sum()
    values=np.r_[r.capital,eq.to_numpy()]
    peaks=np.maximum.accumulate(values);drawdowns=values/peaks-1
    trough_i=int(np.argmin(drawdowns));peak_i=int(np.argmax(values[:trough_i+1]))
    dd=float(drawdowns[trough_i])
    dd_peak_date=None if peak_i==0 else eq.index[peak_i-1]
    dd_trough_date=None if trough_i==0 else eq.index[trough_i-1]
    drawdown_detail={'Picco data':dd_peak_date,'Picco equity':float(values[peak_i]),'Minimo data':dd_trough_date,'Minimo equity':float(values[trough_i]),'Calo monetario':float(values[trough_i]-values[peak_i]),'Drawdown %':dd*100,'Formula':'(Equity minimo / Equity picco − 1) × 100'}
    worst_trade=float(t['Netto % capitale ingresso'].min()) if len(t) else None
    max_streak=streak=0
    for value in pnl:
        streak=streak+1 if value<0 else 0
        max_streak=max(max_streak,streak)
    stats={'Trade chiusi':len(t),'Rendimento %':(eq.iloc[-1]/r.capital-1)*100,'Max drawdown %':dd*100,'Win rate %':(pnl>0).mean()*100 if len(pnl) else 0.0,'Profit factor':gains/loss if loss else np.nan,'PnL chiuso':pnl.sum(),'Posizione aperta':pos is not None,'Ingressi saltati':skipped,'Equity finale':eq.iloc[-1],'Peggior trade %':worst_trade,'Massimo perdite consecutive':max_streak}
    period={'Inizio richiesto':str(a.date()),'Fine richiesta':str(b.date()),'Prima barra calcolata':str(eq.index[0].date()),'Ultima barra calcolata':str(eq.index[-1].date()),'Barre nel test':len(eq)}
    if len(t):
        if (t.Ingresso<eq.index[0]).any() or (t.Uscita>eq.index[-1]).any():raise ValueError('Risultati fuori periodo: ricalcolare il test.')
    opened=None
    if pos:
        opened={'Ingresso':pos['date'],'Prezzo':pos['entry'],'Quantità':pos['qty'],'Stop':pos['stop'],'Target':pos['target'],'PnL non realizzato':(x.close.iloc[ids[-1]]-pos['entry'])*pos['qty']*point,'Uscita al prossimo open':pending_exit}
    return {'schema':2,'stats':stats,'trades':t,'equity':eq,'open':opened,'signal':signal,'period':period,'drawdown':drawdown_detail}




