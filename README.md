# G. Trend Lab

## Confronto essenziale — due ingressi e tre uscite (07/11/2026)

Ramo sperimentale: non modifica la versione attualmente pubblicata su Streamlit.
Nel menu **Confronto uscite**, caricare uno storico Daily di OHLC Standard e
cliccare **Esegui confronto 2 ingressi × 3 uscite**.

**Ingressi congelati**
- **A**: Forces Standard SMA7/EMA7 passa da <=0 a >0; HA verde; Close Standard > EMA200.
- **B**: Forces Heikin Ashi SMA7/EMA7 passa da <=0 a >0; HA verde; Close Standard > EMA200.

**Uscite** (applicate indipendentemente a ciascun ingresso)
1. **Forces 10/4 Standard <=0** al close, vendi all'open successivo.
2. **Supertrend ATR Wilder 10, fattore 2** ribassista al close, vendi all'open successivo.
3. **Forces HA 10/4 <=0 E candela HA rossa, O trailing 5%**: il trailing si attiva
   se la massima CHIUSURA Standard durante il trade supera il prezzo d'ingresso
   corretto per i costi e se (max_close - close_attuale) / prezzo_ingresso >= 5%.
   Segnale al close e vendita all'open successivo, non è uno stop intraday.

**Perché non compare il preset C?** L'ingresso del vecchio preset C era
identico a quello di A: differiva solo la sorgente Forces dell'uscita.
Il laboratorio deve confrontare ingressi distinti, non duplicati; l'uscita
Forces HA rimane disponibile nella terza opzione.

Il valore storico **+57,7% mediano, 12/16 titoli positivi** riguardava B con
l'uscita 3, non è ancora replicato/verificato con questo motore. **Non** è il
risultato attuale di tutta la matrice.

Modello: una posizione alla volta per titolo, ingresso/uscita all'open
successivo, costo stimato 0,15% per lato, nessun rientro nello stesso open
di uscita; posizioni aperte riportate separatamente. I risultati si riferiscono
a prezzi azionari Daily e non simulano margini/rollover futures. Il backtest
dell'app e le altre sezioni restano autonomi.

**Prima di pubblicare:** eseguire test automatici, allineare barra per barra
Supertrend con TradingView Pine `ta.supertrend(2,10)`, confrontare Forces/HA
e trading signals, verificare feed/corporate actions, e non selezionare
parametri usando il periodo successivamente dichiarato fuori campione.

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

## Prestazioni e filtro EMA (v1.3)

Il Backtest non ricalcola l'intero universo quando cambia un parametro.
Calcola gli indicatori del solo titolo selezionato al submit, con cache LRU per sessione
(revisione dati, titolo, parametri indicatori e periodo). Modifiche a costi, stop,
uscite e moduli riutilizzano gli indicatori. Anche il confronto riusa i calcoli fra
combinazioni. Export ZIP costruito una volta per esecuzione. Ricaricare i dati invalida
la cache; cache limitata a 96 serie per sessione.

Nuovo modulo facoltativo Prezzo sopra EMA, default OFF: close standard strettamente
superiore alla EMA configurata (periodo iniziale 21). La EMA è inizializzata al primo
close disponibile; il filtro richiede almeno il numero di barre del periodo.
Non richiede incrocio né pendenza positiva, e non aggiunge uscite automatiche.
EMA disegnata sul grafico e inclusa nelle esportazioni e nei confronti.

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

## Controllo qualità OHLC

Impostazioni iniziali consigliate: Solo split / non rettificare dividendi, correzione
High/Low disattivata. Se TradingView usa rettifica per dividendi, allineare anche quella
scelta per un confronto equivalente: split-only non garantisce OHLC identici fra provider.

Le barre aperte vengono escluse prima della validazione OHLC.
Le vecchie anomalie non escludono l'intero ticker: lo screener riparte dal primo giorno
successivo all'ultima anomalia e pubblica il segnale solo dopo il warm-up pulito necessario.
La colonna Qualità dati dichiara il riavvio; con anomalia recente il risultato è N/D.

Il backtest controlla il periodo richiesto e il riscaldamento precedente. Si blocca in
presenza di barre incoerenti nel test o di warm-up pulito insufficiente. I dati successivi
alla fine del test non influiscono sulla valutazione. La Weekly conserva la segnalazione
di una Daily incoerente anche se l'aggregato settimanale appare valido.

L'opzione esplicita Correggi High/Low incoerenti amplia il range ai prezzi Open/Close,
senza modificare Open e Close. I valori originali sono visibili in Dati e metodo e
nell'esportazione ZIP. Non è una ricostruzione dei veri estremi intraday; può cambiare
segnali, stop e target. Ripetere i confronti mantenendo la stessa politica dati.

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


