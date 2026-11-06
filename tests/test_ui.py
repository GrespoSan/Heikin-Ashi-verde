from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

def test_app_screener_backtest_comparison():
    rng=np.random.default_rng(7);idx=pd.bdate_range('2010-01-01','2026-10-30');c=20+np.cumsum(rng.normal(0,.03,len(idx)));o=c+rng.normal(0,.03,len(idx))
    data=pd.DataFrame({'open':o,'high':np.maximum(o,c)+.02,'low':np.minimum(o,c)-.02,'close':c,'volume':100},index=idx)
    with patch('data_sources.yahoo',return_value=data):
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
        assert not at.exception
        for b in at.button:
            if b.label=='Carica dati e aggiorna screener':b.click().run();break
        assert not at.exception
        assert len(at.session_state['lab_data'])==7
        for label,state,section in [('Esegui backtest','lab_results','Backtest'),('Esegui confronto','comparison','Confronto')]:
            at.radio(key='section').set_value(section).run()
            for b in at.button:
                if b.label==label:b.click().run();break
            assert not at.exception
            assert at.session_state[state] is not None



def test_submitted_period_is_displayed_and_previous_stats_are_replaced():
    from datetime import date
    rng=np.random.default_rng(77);idx=pd.bdate_range('2010-01-01','2026-10-30');c=20+np.cumsum(rng.normal(0,.03,len(idx)));o=c+rng.normal(0,.03,len(idx))
    data=pd.DataFrame({'open':o,'high':np.maximum(o,c)+.02,'low':np.minimum(o,c)-.02,'close':c,'volume':100},index=idx)
    with patch('data_sources.yahoo',return_value=data):
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
        next(b for b in at.button if b.label=='Carica dati e aggiorna screener').click().run()
        at.radio(key='section').set_value('Backtest').run()
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        before=at.session_state['lab_results']['stats']['Trade chiusi']
        at.date_input(key='bt_start').set_value(date(2024,7,19))
        at.date_input(key='bt_end').set_value(date(2026,10,30))
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        assert not at.exception
        result=at.session_state['lab_results']
        assert result['period']['Inizio richiesto']=='2024-07-19'
        assert result['period']['Prima barra calcolata']=='2024-07-19'
        assert result['stats']['Trade chiusi']<before
        assert any('2024-07-19' in s.value and 'Risultato calcolato' in s.value for s in at.success)


def test_old_result_in_warm_session_is_discarded_without_losing_data():
    idx=pd.bdate_range('2010-01-01','2026-10-30');c=20+np.sin(np.arange(len(idx))/5)
    data=pd.DataFrame({'open':c-.1,'high':c+.5,'low':c-.5,'close':c,'volume':100},index=idx)
    with patch('data_sources.yahoo',return_value=data):
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
        next(b for b in at.button if b.label=='Carica dati e aggiorna screener').click().run()
        at.radio(key='section').set_value('Backtest').run()
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        # Simula un risultato pre-v1.2 con gli stessi parametri della pagina.
        result=at.session_state['lab_results'].copy();result.pop('period');result.pop('schema')
        at.session_state['lab_results']=result
        at.run()
        assert not at.exception
        assert 'lab_results' not in at.session_state
        assert len(at.session_state['lab_data'])==7
        assert any('versione precedente' in item.value for item in at.info)
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        assert not at.exception
        assert at.session_state['lab_results']['schema']==2
        assert 'period' in at.session_state['lab_results']

def test_session_schema_upgrade_clears_only_results():
    idx=pd.bdate_range('2010-01-01','2026-10-30');c=20+np.sin(np.arange(len(idx))/5)
    data=pd.DataFrame({'open':c-.1,'high':c+.5,'low':c-.5,'close':c,'volume':100},index=idx)
    with patch('data_sources.yahoo',return_value=data):
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
        next(b for b in at.button if b.label=='Carica dati e aggiorna screener').click().run()
        at.radio(key='section').set_value('Backtest').run()
        at.session_state['result_session_schema']='old'
        at.session_state['lab_results']={'stats':{}}
        at.run()
        assert not at.exception
        assert 'lab_results' not in at.session_state
        assert len(at.session_state['lab_data'])==7
        assert any('App aggiornata' in item.value for item in at.info)


def test_parameter_changes_in_backtest_do_not_rescan_universe():
    from engine import prepare_features
    idx=pd.bdate_range('2010-01-01','2026-10-30');c=20+np.sin(np.arange(len(idx))/5)
    data=pd.DataFrame({'open':c-.1,'high':c+.5,'low':c-.5,'close':c,'volume':100},index=idx)
    with patch('data_sources.yahoo',return_value=data),patch('feature_cache.prepare_features',wraps=prepare_features) as calc:
        at=AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=60).run()
        next(b for b in at.button if b.label=='Carica dati e aggiorna screener').click().run()
        assert calc.call_count==7 # prima scansione richiesta
        at.radio(key='section').set_value('Backtest').run()
        baseline=calc.call_count
        at.number_input[0] # il test usa le etichette per non dipendere dall’ordine
        next(n for n in at.number_input if n.label=='Forces SMA').set_value(4).run()
        next(n for n in at.number_input if n.label=='Periodo EMA prezzo').set_value(55).run()
        at.checkbox(key='mod_ema_filter').check().run()
        assert not at.exception
        assert calc.call_count==baseline # nessun calcolo prima di Esegui
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        assert not at.exception
        assert calc.call_count==baseline+1 # solo il ticker selezionato
        next(n for n in at.number_input if n.label=='Commissione % per lato').set_value(.2).run()
        assert calc.call_count==baseline+1
        next(b for b in at.button if b.label=='Esegui backtest').click().run()
        assert not at.exception
        assert calc.call_count==baseline+1 # stessi indicatori riutilizzati
        assert at.session_state['lab_results']['run_config']['EMA prezzo']==55
        assert at.session_state['lab_results']['run_config']['Filtro EMA'] is True
