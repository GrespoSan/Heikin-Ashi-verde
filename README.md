# G. Trend Lab

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


