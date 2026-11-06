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

