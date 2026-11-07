"""Smoke test Streamlit senza internet né provider esterni.

Dopo il caricamento sintetico di barre OHLC, verifica che la sezione
Confronto uscite produca dieci righe e il registro delle esecuzioni.
"""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


def sample():
    idx=pd.bdate_range("2023-01-02", periods=360)
    z=np.arange(len(idx))
    cl=20+z*.018+1.4*np.sin(z/6)
    op=cl-.3*np.cos(z/3)
    return pd.DataFrame({
        "open":op, "high":np.maximum(op,cl)+.2,
        "low":np.minimum(op,cl)-.2, "close":cl, "volume":1000
    }, index=idx)


class StreamlitSmokeTest(unittest.TestCase):
    def test_comparison_produces_ten_rows(self):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        at.session_state["lab_data"]={"TEST.MI":sample()}
        at.session_state["lab_data_revision"]="fixture-1"
        at.session_state["lab_notes"]={"TEST.MI":"synthetic data"}
        at.session_state["lab_errors"]=[]
        at.run()
        self.assertEqual(len(at.exception),0)
        at.radio(key="section").set_value("Confronto uscite").run()
        self.assertEqual(len(at.exception),0)
        at.button(key="abc_run").click().run()
        self.assertEqual(len(at.exception),0)
        res=at.session_state.get("abc_results")
        self.assertIsNotNone(res)
        self.assertFalse(res["errors"],msg=str(res["errors"]))
        self.assertEqual(len(res["rows"]),10)
        self.assertEqual(set(x["Preset"] for x in res["rows"]),{"A","B"})
        self.assertEqual(len(set(x["Uscita"] for x in res["rows"])),5)


if __name__=="__main__":
    unittest.main()
