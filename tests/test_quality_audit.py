import unittest
import numpy as np
import pandas as pd
from quality_audit import audit_ohlc_bars, quality_overview
from engine import invalid_ohlc


class TestQualityAudit(unittest.TestCase):
    def setUp(self):
        self.df=pd.DataFrame({
            "open":[100.,102.,101.],"high":[105.,101.,103.],
            "low":[98.,99.,102.],"close":[103.,102.,101.],
            "volume":[1000.,1001.,1002.],
        },index=pd.bdate_range("2026-11-03",periods=3))
    
    def test_identifies_dates_prices_reasons_without_mutation(self):
        original=self.df.copy(deep=True)
        records=audit_ohlc_bars(self.df,"TEST.MI","Yahoo | no adjustments")
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]["Data"],"2026-11-04")
        self.assertIn("High inferiore",records[0]["Problema"])
        self.assertIn("Low superiore",records[1]["Problema"])
        self.assertEqual(records[0]["High"],101.)
        self.assertEqual(records[0]["Close"],102.)
        pd.testing.assert_frame_equal(self.df,original)
        self.assertEqual(invalid_ohlc(self.df).sum(),len(records))

    def test_clean_data_unmodified_and_identifiable(self):
        x=self.df.copy()
        x.loc[x.index[1],"high"]=104.
        x.loc[x.index[2],"low"]=99.
        summary,details=quality_overview({"TEST.MI":x}, "Import CSV", minimum_warmup=3)
        self.assertEqual(len(details),0)
        self.assertEqual(summary.iloc[0]["Stato"],"IDONEO — OHLC")
        self.assertEqual(summary.iloc[0]["Anomalie"],0)
        self.assertEqual(len(summary.iloc[0]["Impronta OHLC"]),16)

    def test_overview_excludes_broken_and_warns_short_series(self):
        clean=self.df.copy()
        clean.loc[clean.index[1],"high"]=104.
        clean.loc[clean.index[2],"low"]=99.
        summary,details=quality_overview({"BAD.MI":self.df,"SHORT.MI":clean}, "Yahoo",minimum_warmup=220)
        self.assertEqual(len(details),2)
        self.assertIn("ESCLUSO",summary.loc[summary.Ticker=="BAD.MI","Stato"].iloc[0])
        self.assertIn("storico insufficiente",summary.loc[summary.Ticker=="SHORT.MI","Stato"].iloc[0])


if __name__=="__main__":
    unittest.main()
