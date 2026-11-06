# G. Trend Lab

Trasformazione dello screener Heikin Ashi in laboratorio LONG multi-ticker Daily/Weekly.
Nessuna condizione Balance. Il progetto Balance-Screener rimane separato.

## Ripristino

Backup integrale precedente: branch `backup/pre-trend-lab-2026-11-06`, commit
`ae3073e09545abbd09223a4e9455f0f4b49eaa0b`.
Per ripristinare l'app precedente, riconfigurare temporaneamente Streamlit su quel branch.
L'entrypoint corrente è `app.py`; anche `app 1.py` rimanda alla nuova app, per compatibilità
con eventuali impostazioni precedenti del deployment.

## Avvio

```bash
pip install -r requirements.txt
streamlit run app.py
```

Caricare `lista.txt` (ticker uno per riga, separati da virgole, o `Nome;Ticker`).
Yahoo Italia: suffisso `.MI`, applicato automaticamente ai simboli semplici con mercato Italia.
Liste miste e commodity: scegliere Commodity / altri e usare simboli completi.

Scegliere Yahoo, Alpaca oppure CSV/JSON Daily con prezzi standard.
Le etichette delle date importate devono essere date di seduta, non timestamp intraday.
Non caricare OHLC Heikin Ashi come se fossero prezzi standard.

## Alpaca (solo lettura dati azionari USA)

Nei Secrets di Streamlit, direttamente sul servizio (mai nel repository):

```toml
ALPACA_API_KEY = "la-tua-chiave"
ALPACA_SECRET_KEY = "il-tuo-segreto"
```

Feed SIP o IEX esplicito, senza fallback. Accesso secondo autorizzazioni dell'account;
richieste storiche terminate almeno 20 minuti prima di adesso. Nessun ordine inviato.
Il plugin ChatGPT non fornisce automaticamente credenziali all'app.

## Regole

- HA, Hull segnale recente, Hull trend, Forces prevalenza, rafforzamento, direzione.
- Forces SMA3/EMA3 e ShortTerm OFF di default. Sorgente Standard o HA selezionabile.
- HA doji classificata verde, come nel Pine screener. HMA WMA16 con arrotondamento Pine.
- Tutti i moduli attivi devono passare. Fuori filtro non influenza il segnale.
- Primo allineamento oppure ogni allineamento da flat; fill all'open successivo.
- Uscita HA rossa, Hull BEAR, Forces non positivo, perdita allineamento o numero barre.
  Per Numero barre: decisione al close della N-esima barra; fill all'open successivo.
- Stop fisso nessuno/minimo segnale/ATR/percentuale; target facoltativo in R.
  Per ATR: distanza fissata usando ATR della candela segnale e prezzo ingresso.
- Gap sullo stop: open effettivo. Stop e target toccati insieme: stop prima.
- Nessuna liquidazione artificiale finale. Equity include PnL aperto al close.
- Segnali su candele chiuse, esecuzioni su OHLC standard, anche visualizzando HA.
- Warm-up almeno 100 barre, elevato secondo i parametri. Il filtro HA usa la candela
  stessa del segnale: non un ulteriore shift, dato che l'esecuzione è già il giorno dopo.

## Dati e limiti

Equity: calendari XMIL/XNYS e attesa 15 minuti dopo il close. Futures/24h: esclusione
prudente dell'intera data UTC corrente; non ricostruisce tutte le sessioni futures.
Weekly: settimana corrente esclusa fino al sabato UTC.

Yahoo auto_adjust=False mantiene gli OHLC forniti da Yahoo, di norma corretti per split;
auto_adjust=True rettifica anche per dividendi. Nessun accredito separato di dividendi.
Alpaca: split/all esplicito. Non confondere prezzi adjusted con esecuzioni storiche nominali.

Modello spot: capitale indipendente per ticker, allocazione percentuale, quote frazionarie.
Futures singolo contratto: quantità intera fissa e valore punto esplicito; niente roll,
margini o conversione FX. Il conto deve essere nella valuta dello strumento.
Serie Yahoo `=F`: solo studio percentuale del segnale, non PnL di futures negoziabili.
I prezzi non positivi non sono supportati da questa versione.

Il confronto non è un portafoglio: ogni ticker riparte dal suo capitale iniziale.
Graduatoria sul solo periodo di selezione, separato dalla verifica. Il periodo di verifica
cessa di essere incontaminato dopo averlo usato per scegliere altre configurazioni.
Nessun aggiustamento per survivorship bias della lista odierna, interessi o imposte.
Drawdown calcolato al close, non intraday. I risultati restano sperimentali fino al confronto
barra per barra con TradingView e alla validazione su periodi/strumenti indipendenti.

## Test

```bash
pip install pytest
python -m pytest tests -q
```

Test: calcolo causale senza look-ahead, calendari, parser/import, esecuzioni next-open,
stop/gap e ambiguità OHLC, costi, mark-to-market, valore punto futures.
Il caso A2A 09/10/2026 → 28/10/2026 è verificato durante lo sviluppo sullo storico
TradingView disponibile nella sessione; non include file privati nel repository.

Riferimenti:
- https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html
- https://docs.streamlit.io/develop/api-reference/app-testing
