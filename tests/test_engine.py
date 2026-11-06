from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from engine import Indicators,Rules,normalize_bars,calculate,backtest,parse_symbols
from data_sources import completed_bars,read_import

def synthetic():
    x=pd.DataFrame({'open':[10.]*8,'high':[11.]*8,'low':[9.]*8,'close':[10.]*8,'volume':[1.]*8},index=pd.date_range('2025-01-01',periods=8))
    x=calculate(x,Indicators());x['ready']=True;x['ha']=[False,True,True,False,False,False,False,False];x['forces_positive']=True
    return x

def test_next_open_and_exit_after_red():
    x=synthetic();x.loc[x.index[2],'open']=10.3;x.loc[x.index[4],'open']=10.8
    r=Rules(modules=('ha',),commission_pct=0,slippage_pct=0)
    result=backtest(x,r)
    t=result['trades'].iloc[0]
    assert t.Ingresso==x.index[2] and t.Uscita==x.index[4]
    assert t['Prezzo ingresso']==10.3 and t['Prezzo uscita']==10.8

def test_forces_negative_does_not_exit_ha_rule():
    x=synthetic();x['ha']=[False,True,True,True,True,True,True,True];x['forces_positive']=[False,True,False,False,False,False,False,False]
    result=backtest(x,Rules())
    assert result['trades'].empty and result['open'] is not None

def test_gap_stop_and_no_ha_synthetic_fill():
    x=synthetic();x['ha']=True;x.loc[x.index[0],'ha']=False
    x.loc[x.index[3],['open','high','low','close']]=[8.,9.,7.,8.]
    r=Rules(modules=('ha',),stop='Minimo candela segnale',tick=.1,commission_pct=0,slippage_pct=0)
    result=backtest(x,r);t=result['trades'].iloc[0]
    assert t.Motivo=='Gap stop' and t['Prezzo uscita']==8.

def test_stop_wins_ambiguous_bar():
    x=synthetic();x['ha']=True;x.loc[x.index[0],'ha']=False
    x.loc[x.index[2],['high','low']]=[13.,8.]
    r=Rules(modules=('ha',),stop='Percentuale',stop_pct=10,target_r=1,commission_pct=0,slippage_pct=0,tick=.1)
    t=backtest(x,r)['trades'].iloc[0]
    assert t.Motivo=='Stop' and t['Prezzo uscita']==9.

def test_capital_accounting_costs_and_open_mark():
    x=synthetic();x['ha']=True;x.loc[x.index[0],'ha']=False
    r=Rules(modules=('ha',),capital=1000,commission_pct=.1,slippage_pct=.05)
    result=backtest(x,r);pos=result['open']
    qty=1000/(10*1.0005*1.001)
    assert np.isclose(pos['Quantità'],qty)
    assert np.isclose(result['equity'].iloc[-1],qty*10)

def test_prefix_invariance():
    rng=np.random.default_rng(33);c=100+np.cumsum(rng.normal(size=220));o=c+rng.normal(size=220)
    df=pd.DataFrame({'open':o,'close':c,'high':np.maximum(o,c)+1,'low':np.minimum(o,c)-1,'volume':1},index=pd.date_range('2020-01-01',periods=220))
    for source in ['Standard','Heikin Ashi']:
        a=calculate(df,Indicators(forces_source=source));b=calculate(df.iloc[:180],Indicators(forces_source=source))
        pd.testing.assert_frame_equal(a.iloc[:180],b)

def test_parse_and_import():
    assert parse_symbols('Nome;Ticker\nAmplifon;AMP\nMIL:A2A,AMP.MI\n#comment','Italia')==['AMP.MI','A2A.MI']
    with pytest.raises(ValueError):parse_symbols('A2A.MI','Italia','Alpaca')
    df=read_import(b'Date,Open,High,Low,Close\n2025-01-01,10,11,9,10\n','test.csv')
    assert len(df)==1 and df.volume.iloc[0]==0
    with pytest.raises(ValueError):normalize_bars(pd.concat([df,df]))

def test_calendar_before_after_close_and_weekend():
    df=synthetic()[['open','high','low','close','volume']].copy()
    df.index=pd.date_range('2026-11-02',periods=8)
    early,_=completed_bars(df,'AMP.MI','Italia',now='2026-11-06T14:00Z')
    late,_=completed_bars(df,'AMP.MI','Italia',now='2026-11-06T19:00Z')
    assert str(early.index[-1].date())=='2026-11-05'
    assert str(late.index[-1].date())=='2026-11-06'
    weekend,_=completed_bars(df,'AMP.MI','Italia',now='2026-11-08T12:00Z')
    assert str(weekend.index[-1].date())=='2026-11-06'

def test_futures_pnl_point_value():
    x=synthetic();x.loc[x.index[4],'open']=10.8
    r=Rules(modules=('ha',),instrument='Futures (contratto singolo)',point_value=100,contracts=2,commission_fixed=1,commission_pct=0,slippage_pct=0)
    t=backtest(x,r)['trades'].iloc[0]
    assert np.isclose(t['PnL netto'],(.8*100*2)-4)

def test_no_modules_no_trades():
    assert backtest(synthetic(),Rules(modules=()))['trades'].empty

def test_ohlc_repair_is_explicit_and_audited():
    x=pd.DataFrame({'date':['2025-01-01'],'open':[10.],'high':[9.9],'low':[9.],'close':[9.5]})
    with pytest.raises(ValueError):normalize_bars(x)
    corrected=normalize_bars(x,repair=True)
    assert corrected.high.iloc[0]==10.
    assert corrected.open.iloc[0]==10.
    assert corrected.attrs['ohlc_corrections'][0]['high']==9.9


def long_daily():
    idx=pd.bdate_range('2024-01-01',periods=350)
    return pd.DataFrame({'open':10.,'high':11.,'low':9.,'close':10.5,'volume':1.},index=idx)

def test_old_bad_bar_does_not_block_current_screener():
    from engine import prepare_features
    df=long_daily();df.loc[df.index[5],'high']=9.8
    x=prepare_features(df,Indicators())
    assert x.ready.iloc[-1] and x.index[0]==df.index[6]
    assert df.high.iloc[5]==9.8 # nessuna rettifica nascosta

def test_backtest_rejects_bad_in_range_and_accepts_earlier_anomaly():
    from engine import prepare_features
    df=long_daily();df.loc[df.index[5],'high']=9.8
    with pytest.raises(ValueError,match='nel periodo del test'):
        prepare_features(df,Indicators(),str(df.index[0].date()))
    good=prepare_features(df,Indicators(),str(df.index[150].date()))
    assert good.ready.loc[df.index[150]]
    with pytest.raises(ValueError,match='riscaldamento'):
        prepare_features(df,Indicators(),str(df.index[20].date()))

def test_future_anomaly_does_not_change_past_features():
    from engine import prepare_features
    df=long_daily();reference=prepare_features(df,Indicators(),str(df.index[120].date()),str(df.index[200].date()))
    df.loc[df.index[250],'high']=9.8
    actual=prepare_features(df,Indicators(),str(df.index[120].date()),str(df.index[200].date()))
    pd.testing.assert_frame_equal(actual,reference)

def test_incomplete_bad_daily_excluded_before_validation_or_repair():
    df=long_daily().iloc[:5].copy();df.index=pd.bdate_range('2026-11-02',periods=5)
    df.loc[df.index[-1],'high']=9.8
    for repair in (False,True):
        closed,_=completed_bars(df,'AMP.MI','Italia',now='2026-11-06T14:00Z',repair=repair)
        assert closed.index[-1]==pd.Timestamp('2026-11-05')
        assert not closed.attrs.get('ohlc_corrections')

def test_weekly_keeps_bad_daily_quality_even_if_aggregate_looks_valid():
    df=long_daily().iloc[:5].copy();df.index=pd.bdate_range('2026-10-26',periods=5)
    df.loc[df.index[1],'high']=9.8
    closed,_=completed_bars(df,'AMP.MI','Italia',timeframe='Weekly',now='2026-11-01T14:00Z')
    assert len(closed)==1 and not closed.ohlc_valid.iloc[0]
