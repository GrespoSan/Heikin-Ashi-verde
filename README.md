# G. Trend Lab

## Studio Stop Loss e breakeven — ricerca esplorativa (08/11/2026)

**Obiettivo:** confrontare la rotazione *B completo + Supertrend 10x2 congelato* su 1/2/3 posizioni, con quote riservate e capitale iniziale nominale USD, rispetto a sei protezioni definite prima di vedere i risultati. Non cambia i moduli congelati di ricerca.

Sette scenari di uscita/protezione:

1. Nessuno stop aggiuntivo (baseline originale).
2. Stop fisso −5% dall'open d'ingresso.
3. Stop fisso −8% dall'open d'ingresso.
4. Stop pari a 2 × ATR Wilder(14) misurato alla candela di segnale, fissato all'ingresso.
5. Stop iniziale −8%; passaggio a breakeven netto dopo che il massimo di una candela chiusa raggiunge almeno +3% rispetto all'open d'ingresso.
6. Stop iniziale −8%; breakeven netto dopo +5%.
7. Stop iniziale −5%; breakeven netto dopo +3%.

**Esecuzione:** segnale all'ultima candela chiusa, acquisto alla successiva apertura. Se Supertrend è già ribassista, il suo ordine di vendita alla successiva apertura ha precedenza. Altrimenti, se l'apertura è sotto lo stop, esecuzione all'apertura (gap); se il minimo tocca lo stop, esecuzione allo stop. Il breakeven viene attivato soltanto dalla *seduta successiva* a una candela completata il cui massimo ha toccato il trigger (si evita di supporre se High sia stato precedente a Low sul Daily). Il livello di pareggio incorpora 0,15% di costo sia all'ingresso sia all'uscita; un gap può comunque produrre una perdita. Lo stop iniziale può essere colpito anche nella giornata di ingresso. Lo stop non è un ordine realmente trasmesso, ma una simulazione su OHLC Daily; non include slippage aggiuntivo, spread, liquidità e tasse.

Si confrontano 7 varianti × 3 capacità = **21 simulazioni** per un criterio di scelta fissato (priorità alfabetica deterministica oppure momentum 63 sedute), con stesso universo, periodo e fonte dati. La baseline senza stop viene confrontata numericamente con il motore storico; se diverge, il confronto si interrompe. Misure: CAGR, drawdown giornaliero mark-to-market, Calmar, esposizione, costi, turnover, numero di stop, operazioni. Sono disponibili CSV di riepilogo, equity e trade.

**Nessun risultato numerico storico può essere derivato dai soli CSV di trade ed equity già esportati**: occorrono barre complete `Open/High/Low/Close` per tutti i titoli. Dopo aver caricato i dati originali in Streamlit, utilizzare la scheda *Studio Stop Loss* ed esportare il riepilogo. I risultati sono retrospettivi, non out-of-sample; una variante vincente non va adottata senza test indipendenti e costi realistici.


## Rotazione capitale a quote riservate — 1 / 2 / 3 posizioni (v1.8.0, 07/11/2026)

**Scopo**: simula un unico capitale disponibile, per esempio **10.000 USD**, con possibilità di mantenere fino a 1, 2 o 3 posizioni simultanee. Si tratta di un modello alternativo al portafoglio a 19/63 quote fisse: non sommare o confondere i relativi CAGR.

- **Quote riservate**: per limite M∈{1,2,3}, si creano esattamente M slot di importo iniziale `capitale/M`. Una quota inutilizzata resta in cash. Quando una posizione viene venduta, lo stesso slot conserva ricavato e perdite/profitti e si libera per il successivo titolo. Gli slot non si scambiano liquidità.
- **Ingresso B congelato**: Forces HA 7/7 attraversa zero da <=0 a >0 + HA verde + close standard > EMA200, su candle chiusa. Compra all'open successivo; non apre se non c'è uno slot libero. Segnale non eseguito per capienza NON è posticipato.
- **Uscita congelata**: chiude il 100% al successivo open se Supertrend standard Wilder ATR10×2 è ribassista; come nello storico, verifica il regime e **non richiede un cambio bullish→bearish**. Slot venduto non può ricomprare nella stessa giornata.
- **Graduatorie concorrenti fissate ex ante**:
  1. Ordinamento alfabetico del ticker (baseline deterministica **non casuale, non ottimale**).
  2. Momentum delle precedenti 63 sedute, misurato da `close[t-1]/close[t-64]-1`. Ordina decrescente, ticker a parità. Non usa barre successive al segnale.
- Per ciascuna graduatoria esegue M=1,2,3: **6 simulazioni**. Export sintesi, equity giornaliera, esecuzioni, posizioni, esclusioni.
- **Costi** 0,15% a lato; mark-to-market include il costo ipotetico di liquidazione del titolo in portafoglio, coerentemente con `simulate_preset`. Cash a rendimento 0, quote frazionarie, nessuna leva.
- **Rischio** CAGR portafoglio, DD massimo mark-to-market, esposizione, Calmar, numero segnali scartati, turnover nozionale e confronto SPY a capitale interamente investito dalla prima data del periodo comune; se SPY non copre l'inizio, N/D.
- **Dati**: solo storici Daily già caricati in app. Caricamento Alpaca/Yahoo come negli altri moduli; serie con anomalie OHLC o dati insufficienti vengono escluse esplicitamente. Se una posizione rimane senza prezzo aggiornato per oltre dieci giorni di calendario, la simulazione viene bloccata (non si può supporre un prezzo dopo un delisting).
- **Cambio**: il modello esegue la contabilità in **USD nominali** per azioni USA. Un investimento reale di 10.000 EUR richiede conversione del capitale iniziale e finale con FX storico, commissioni di cambio e profilo EUR/USD; ciò non è ancora disponibile. Imposte, spread effettivi, dividendi, FX, market impact e settlement non simulati. Quote frazionarie potrebbero non essere acquistabili presso il broker.
- **Validazione**: elenco Core/Satellite scelto oggi (non point-in-time) e dati 2016–2026 già esaminati; questo non costituisce un out-of-sample. Per operatività reale servono test indipendenti, regole del broker (liquidità da vendite / settlement), gestione del rischio per gap e confronto rischio-normalizzato.
- Test di regressione in `tests/test_rotation_reserved.py`: 1 slot/1 simbolo deve replicare la curva del preset B congelato, 1–3 slot mai oltre capienza, cash e patrimonio riconciliati, nessun look-ahead da prezzi futuri, 6 test sullo stesso universo.


## Validazione Portafoglio una tantum (v1.7.0, 07/11/2026)

**Modello implementato e da collaudare in Streamlit:** 1 solo versamento iniziale, ripartito in N quote uguali tra i simboli validi. Ogni quota conserva cash e posizioni del suo ticker; non può prendere capitale da altre quote. Modello coerente con il precedente studio «19 quote iniziali uguali», ma adesso con una curva giornaliera mark-to-market delle posizioni aperte e della liquidità. Non è riallocazione dinamica della cassa.

- Ingresso congelato **B**: Forces HA 7/7 che attraversa da non positivo a positivo, HA verde, close standard > EMA200. Buy all'open della seduta successiva dello stesso ticker.
- Uscita congelata Supertrend 10×2: vendita al successivo open se **regime ribassista**, anche se il cambio di regime è avvenuto prima. Lo storico non richiedeva un nuovo crossover.
- Fee 0,15% per lato, in aggiunta al prezzo di esecuzione standard, sul nozionale; nessun ulteriore slippage o costo di gestione. Quantità frazionarie, senza leva, finanziamento o depositi successivi. Cash con rendimento zero.
- Per ogni giorno di negoziazione: patrimonio netto, cassa, valore investito, percentuale di esposizione e numero di posizioni. La curva valorizza ogni strumento all'ultimo close disponibile quando il mercato è chiuso; non si eseguono ordini in giorni senza OHLC per quel ticker.
- Benchmark SPY: capitale interamente investito al primo open della finestra, stessi 0,15% per lato; periodo comune, giorni mancanti senza interpolare prezzi. Se SPY non copre l'inizio, benchmark N/D (non viene nascosto il disallineamento).
- Output: KPI portafoglio (CAGR, DD MTM, Calmar, turnover nozionale, costi), curva equity, esecuzioni reali simulate, posizioni finali, esclusioni, benchmark SPY se disponibile.
- Titoli troppo giovani o invalidi per 220 barre vengono esclusi dal capitale e il denominatore N viene ricalcolato **prima della simulazione**. Simboli inclusi ma non ancora quotati nel periodo restano con la propria quota in cassa sino a quando la strategia ha segnali eleggibili; questa è una semplificazione ex post.
- **Limiti metodologici:** esclusi delistati/IPO point-in-time, spread, slippage aggiuntivo, tassazione, cambi FX, liquidità, differenze di calendario e total-return dividend cash. Non è possibile dichiarare un edge investibile da questi risultati.
- I test automatici sono in `tests/test_portfolio_validation.py`. Test e deployment devono ancora essere confermati con un'esecuzione verificata.

**Investimento una tantum:** indica un solo versamento, NON un solo acquisto per sempre. La strategia richiede successivi ordini condizionati; mantenimento passivo senza negoziare è un benchmark Buy & Hold differente.


## Audit ingresso Forces — ablazioni isolate (07/11/2026)

**Sorgente verificato:** `research_presets.py`, protocollo `AB-FIVE-EXITS-2026-11-07-v4`. I preset A e B differiscono soltanto per la sorgente del Forces **all'ingresso**: A Standard 7/7, B Heikin Ashi 7/7. Entrambi richiedono HA verde e close Standard sopra EMA200 e un attraversamento Forces da <=0 a >0. Fill alla barra successiva.

**Scostamento descrittivo importante:** l'uscita del motore congelato `Supertrend 10x2` verifica semplicemente `st_bull[prev] == 0`, non il cambio di regime bullish→bearish in quella barra. Le ablazioni replicano volutamente la **logica realmente testata**, e non modificano i risultati storici.

Nuovo pannello `Ablazione ingressi` — 5 strategie fisse:

- B completo, riferimento
- B senza candela HA verde
- B senza filtro EMA200
- B con Forces positivo al posto di crossing dello zero
- A completo (Forces Standard 7/7, resto identico)

Uscita unica: Supertrend ATR10×2, vendita al successivo open, costi 0,15% per lato. Motore separato: `entry_ablation.py`. Ogni simbolo deve superare il confronto automatico con `simulate_preset(..., "B", ..., "Supertrend 10x2")`, per rendimento mark-to-market, massimo drawdown e numero di trade chiusi. In caso di mancata equivalenza, il simbolo è escluso: nessun fallback.

Metriche per ticker/variante: rendimento, CAGR, drawdown giornaliero mark-to-market, esposizione media, Calmar, numero di ingressi, trade chiusi, lato di turnover indicativo e differenze CAGR rispetto a Buy & Hold e SPY con stessa finestra di calendario. **Turnover indicativo per numero di lati non è turnover nozionale monetario**, e il confronto non genera una curva di portafoglio a capitale comune dinamico.

**Validazione:** la nuova scheda è una prova *retrospettiva*, non ancora un walk-forward fuori campione. Storici 2016–2026 e i 19 titoli satellite/growth USA sono già stati osservati. Per produrre nuove ablazioni sono obbligatori OHLC Daily originali; export delle sole operazioni/benchmark non consentono di ricostruire ingressi scartati. Le serie devono usare stessa fonte, rettifiche e quality audit. Universo point-in-time/delistati da verificare.


## Validazione finaliste e azioni satellite (v1.6.0, 07/11/2026)

- La dicitura Forces Standard/HA 3/3 in alto si riferiva esclusivamente a Screener/Backtest manuale: ora l'interfaccia distingue esplicitamente i parametri configurabili da quelli del confronto congelato A/B 7/7.
- In Confronto uscite, dopo «Esegui confronto», la sezione «Validazione preliminare» presenta le **due uscite finaliste**: Supertrend 10x2 e Forces HA + HA rossa + trailing 5%, con entrambi gli ingressi A/B, e i benchmark Buy & Hold del ticker e SPY.
- Dati e benchmark devono usare la stessa fonte/prezzi rettificati e lo stesso intervallo di calendario. SPY è recuperato dalla medesima fonte/feed del confronto; se non disponibile è N/D, senza fallback. SPY usa le proprie sedute realmente disponibili nella finestra comune (festività USA/Italia diverse).
- Metriche: rendimento totale **mark-to-market** delle posizioni ancora aperte, CAGR annualizzato sulla durata effettiva, drawdown close-to-close, quota media del capitale investita (0/100% per A/B finaliste) e Calmar = CAGR/|drawdown|. Include costo 0,15% per lato e acquisto iniziale all'open per i benchmark passivi.
- Esporre il benchmark **non prova un edge**, né elimina survivorship bias, corporate actions o il rischio cambio EUR/USD nei confronti Italia/SPY.
- Per provare il secondo gruppo storico di **39 azioni satellite italiane**, selezionare Mercato Italia, Fonte Yahoo e attivare «Universo storico: 39 azioni satellite Italia». Avviare caricamento e confronto; verificare il pannello esclusioni. I 39 simboli sono un elenco storico di ricerca, non un universo investibile point-in-time validato. Ticker delistati o mutati possono essere indisponibili.
- La precedente lista USA di 63 titoli non include SPY: la nuova versione tenta il caricamento separato di SPY per i benchmark, senza aggiungerlo ai titoli della strategia.


## Laboratorio LONG — 2 ingressi × 5 uscite (07/11/2026)

La scheda **Confronto uscite** confronta **10 configurazioni congelate** su
dati OHLC Standard Daily. Per eseguire: caricare i dati e selezionare
**Esegui confronto 2 ingressi × 5 uscite**. Il resto dello screener e del
backtest configurabile è indipendente.

**Ingressi:**
- A: HA verde, Forces su prezzi Standard 7/7 che attraversa zero verso l'alto, Close Standard > EMA200.
- B: HA verde, Forces su prezzi Heikin Ashi 7/7 che attraversa zero verso l'alto, Close Standard > EMA200.

**Uscite:**
1. Forces Standard 10/4 diventa non positivo; ordine all'open successivo.
2. Supertrend Wilder ATR10 moltiplicatore 2 diventa ribassista; ordine all'open successivo.
3. Forces HA 10/4 non positivo **e** HA rossa, **oppure** trailing 5% dalla massima chiusura, calcolato rispetto al prezzo d'ingresso; ordine all'open successivo. Il trailing **non** è uno stop intraday.
4. E2: Forces Standard 10/4 ancora positivo, ma in diminuzione per due chiusure consecutive **dopo l'ingresso**; vendita completa al prossimo open. Se Forces diventa non positivo prima, vendita completa di sicurezza.
5. E5: stessa attenuazione E2, vendita del **50%** al prossimo open; restante 50% venduto quando Forces Standard 10/4 diventa non positivo. Se prima del parziale Forces arriva a zero, si vende direttamente il 100%. La liquidità del parziale resta ferma, senza reinvestimento.

Tutte le vendite usano un costo ipotizzato dello 0,15% per lato e prezzo
effettivo all'open successivo; E5 registra ciascuna esecuzione e calcola i
costi proporzionalmente alla quantità venduta. Una sola posizione long per
titolo. I trade chiusi e le posizioni ancora aperte sono distinguibili,
con CSV dettagliato di **tutte le esecuzioni**.

**Limitazioni:** il +57,7% mediano storico su B con uscita 3 è una stima
esplorativa, non un risultato certificato della presente versione.
Verificare equivalenza Supertrend rispetto a TradingView, fonti dati,
dividendi e corporate actions; non confondere backtest in-sample con edge
fuori campione. Il motore di confronto è azionario e non replica il PnL
dei futures o il relativo rollover.

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


