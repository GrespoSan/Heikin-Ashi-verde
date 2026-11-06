from dataclasses import asdict,replace
from datetime import date,timedelta
from pathlib import Path
import hashlib
import io
import itertools
import json
import zipfile
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from engine import Indicators,Rules,MODULES,calculate,evaluate,backtest,parse_symbols,config_id
from data_sources import yahoo,alpaca,read_import,completed_bars
st.set_page_config(page_title='G. Trend Lab',page_icon='🧪',layout='wide')
st.title('G. Trend Lab')
st.caption('v1.0 · Screener e laboratorio LONG · Heikin Ashi, Hull e Forces')
TODAY=pd.Timestamp.now(tz='Europe/Rome').date()
HELP={
'ha':'Ultima candela HA chiusa verde (close HA ≥ open HA). Non richiede una nuova inversione.',
'hull_signal':'Hull crescente con inversione recente: memoria 3 = barra del cambio e due successive.',
'hull_trend':'Hull crescente: non richiede un segnale recente.',
'forces_positive':'AV1−AV2 sopra zero, anche se la prevalenza rialzista si sta attenuando.',
'forces_strong':'Forces positivo e in aumento, oppure appena passato a positivo. Include già la prevalenza positiva.',
'forces_direction':'Direzione Forces secondo ShortTerm/Lag. ShortTerm OFF coincide con la prevalenza positiva; ON può essere LONG anche sotto zero.',
}
def secrets_value(k):
    try:return str(st.secrets.get(k,''))
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):return ''
@st.cache_data(ttl=900,max_entries=120,show_spinner=False)
def fetch_cached(symbol,start,end,source,adjustment,feed,_key='',_secret='',account_scope=''):
    if source=='Yahoo':return yahoo(symbol,start,end,adjustment=='Tutti gli aggiustamenti')
    return alpaca(symbol,start,end,_key,_secret,feed,'all' if adjustment=='Tutti gli aggiustamenti' else 'split')
def csv_bytes(df):return df.to_csv(index=True).encode('utf-8-sig')
def show_chart(x,result=None,key='chart'):
    chart_type=st.radio('Candele nel grafico',['Standard','Heikin Ashi'],horizontal=True,key=key+'_candles')
    if len(x)<30:
        st.info('Storico breve: indicatori e segnali potrebbero non essere pronti.')
        bars=len(x)
    else:
        bars=st.slider('Barre visibili',min(30,len(x)-1),min(max(31,len(x)),1500),min(180,len(x)),key=key+'_bars')
    q=x.tail(bars);prefix='ha_' if chart_type=='Heikin Ashi' else ''
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[.72,.28],vertical_spacing=.04)
    fig.add_trace(go.Candlestick(x=q.index,open=q[prefix+'open'],high=q[prefix+'high'],low=q[prefix+'low'],close=q[prefix+'close'],name=chart_type),row=1,col=1)
    fig.add_trace(go.Scatter(x=q.index,y=q.hull,name='Hull (prezzi standard)',line={'color':'#8b5e34','width':1.5}),row=1,col=1)
    fig.add_trace(go.Bar(x=q.index,y=q.forces,name='Forces',marker_color=np.where(q.forces>=0,'#00803d','#c82c3a')),row=2,col=1)
    if result is not None and not result['trades'].empty:
        t=result['trades'];t=t[t.Ingresso>=q.index[0]]
        fig.add_trace(go.Scatter(x=t.Ingresso,y=t['Prezzo ingresso'],mode='markers',name='Entry reale',marker={'symbol':'triangle-up','color':'#006b32','size':12}),row=1,col=1)
        fig.add_trace(go.Scatter(x=t.Uscita,y=t['Prezzo uscita'],mode='markers',name='Exit reale',marker={'symbol':'triangle-down','color':'#c52230','size':12}),row=1,col=1)
    if result is not None and result['open']:
        pos=result['open']
        if pos['Ingresso']>=q.index[0]:fig.add_trace(go.Scatter(x=[pos['Ingresso']],y=[pos['Prezzo']],mode='markers',name='Entry aperta',marker={'symbol':'triangle-up','color':'#006b32','size':12}),row=1,col=1)
    fig.update_layout(height=680,xaxis_rangeslider_visible=False,legend={'orientation':'h'},margin={'l':10,'r':10,'t':20,'b':10})
    st.plotly_chart(fig,width='stretch',key=key)
    if chart_type=='Heikin Ashi':st.caption('Le HA sono sintetiche. Frecce di entrata e uscita sono sempre sui prezzi standard di esecuzione.')
with st.sidebar:
    st.header('Dati e universo')
    source=st.selectbox('Fonte',['Yahoo','Alpaca','CSV / JSON'])
    market=st.selectbox('Mercato',['Italia','USA','Commodity / altri'])
    timeframe=st.selectbox('Timeframe',['Daily','Weekly'])
    history_start=st.date_input('Inizio storico',value=date(2010,1,1),max_value=TODAY)
    adjustment=st.selectbox('Prezzi',['Solo split / non rettificare dividendi','Tutti gli aggiustamenti'],help='Yahoo auto_adjust=False: prezzi OHLC generalmente corretti per split. True: anche rettifica per dividendi. Il laboratorio non accredita dividendi separatamente: dichiarare sempre il tipo di serie.')
    feed='sip'
    if source=='Alpaca':
        feed=st.selectbox('Feed Alpaca',['sip','iex'],help='SIP consolidato; IEX singola borsa. Nessun fallback automatico. Le autorizzazioni dipendono dall’account.')
        st.caption('Secrets richiesti: ALPACA_API_KEY e ALPACA_SECRET_KEY. Solo dati: nessun ordine viene inviato.')
    list_file=st.file_uploader('Carica lista.txt',type=['txt'])
    defaults='A2A.MI, AMP.MI, CPR.MI, ENEL.MI, ENI.MI, ISP.MI, UCG.MI' if market=='Italia' else 'AAPL, MSFT, SPY' if market=='USA' else 'GC=F, CL=F, HG=F, ZC=F'
    text=st.text_area('Ticker',value=defaults,help='Una riga per ticker o lista con virgole. Accetta Nome;Ticker. Per Yahoo Italia aggiunge .MI ai simboli senza suffisso. Commodity: simboli Yahoo completi.')
    imported=st.file_uploader('Serie Daily CSV/JSON',type=['csv','json']) if source=='CSV / JSON' else None
    imported_symbol=st.text_input('Ticker della serie importata','A2A.MI') if source=='CSV / JSON' else ''
    if source=='CSV / JSON':st.caption('CSV: Date, Open, High, Low, Close, Volume opzionale. JSON: bars[] con t,o,h,l,c,v. Indicare un solo simbolo e prezzi standard. Date giornaliere di seduta, non HA.')
    if st.button('Aggiorna dati / svuota cache'):fetch_cached.clear();st.session_state.pop('lab_data',None);st.session_state.pop('lab_results',None)
    st.divider();st.header('Moduli LONG')
    mods=tuple(k for k in MODULES if st.checkbox(MODULES[k],value=k in ('ha','forces_positive'),help=HELP[k],key='mod_'+k))
    fsource=st.selectbox('Candele per Forces',['Standard','Heikin Ashi'],help='Sorgente comune ai tre moduli Forces. HA e Hull rimangono condizioni separate; esecuzioni sempre su prezzi standard.')
    sma=st.number_input('Forces SMA',1,100,3);ema=st.number_input('Forces EMA',1,100,3)
    short_term=st.checkbox('Forces ShortTerm',False,help='Solo modulo direzione: ON usa la pendenza dopo LagBars, altrimenti prevalenza. OFF usa sempre il segno Forces.')
    lag=st.number_input('Forces LagBars',1,100,1)
    hull=st.number_input('Hull periodo',2,200,16);memory=st.number_input('Hull memoria',1,20,3)
    atr=st.number_input('ATR periodo',2,100,14)
    st.divider();st.header('Ingresso e uscita')
    entry=st.selectbox('Ingresso',['Primo allineamento','Ogni allineamento da flat'],help='Primo: entra quando i moduli passano da incompleti a completi. Ogni: da flat entra se sono tutti completi. Esecuzione sempre all’open successivo.')
    exit_mode=st.selectbox('Uscita',['HA rossa','Hull BEAR','Forces non positivo','Allineamento perso','Numero barre'])
    holding=st.number_input('Numero barre',1,250,10,disabled=exit_mode!='Numero barre',help='Decisione al close della N-esima barra contando l’ingresso come 1; esecuzione all’open successivo.')
    stop=st.selectbox('Stop di prezzo',['Nessuno','Minimo candela segnale','ATR','Percentuale'])
    atr_multiple=st.number_input('Stop multiplo ATR',.1,20.,2.,.1,disabled=stop!='ATR')
    stop_pct=st.number_input('Stop %',.1,50.,3.,.1,disabled=stop!='Percentuale')
    target=st.number_input('Target in R (0 = spento)',0.,20.,0.,.5,disabled=stop=='Nessuno')
    st.divider();st.header('Capitale e costi')
    instrument=st.selectbox('Modello',['Azioni / ETF / spot','Serie continua: studio del segnale','Futures (contratto singolo)'])
    currency=st.selectbox('Valuta del conto/strumento',['EUR','USD'])
    capital=st.number_input('Capitale iniziale',100.,10000000.,10000.,100.)
    allocation=st.number_input('Capitale investito %',1.,100.,100.,1.,disabled=instrument=='Futures (contratto singolo)')
    point=st.number_input('Valore monetario di 1 punto',.0001,1000000.,1.,1.,format='%.4f',disabled=instrument!='Futures (contratto singolo)')
    contracts=st.number_input('Contratti',1,1000,1,disabled=instrument!='Futures (contratto singolo)')
    tick=st.number_input('Tick di prezzo',.000001,1000.,.001,format='%.6f',help='Per le azioni può cambiare nel tempo. Specificare quello del mercato/contratto; lo storico usa questo valore fisso.')
    commission_pct=st.number_input('Commissione % per lato',0.,5.,.10,.01)
    commission_fixed=st.number_input('Commissione per unità/contratto per lato',0.,100.,0.,.1)
    slip=st.number_input('Slippage % per lato',0.,5.,.05,.01)
ind=Indicators(int(sma),int(ema),fsource,short_term,int(lag),int(hull),int(memory),int(atr))
rules=Rules(mods,entry,exit_mode,int(holding),stop,float(atr_multiple),float(stop_pct),float(target) if stop!='Nessuno' else 0.,float(capital),float(allocation),float(commission_pct),float(commission_fixed),float(slip),float(tick),instrument,float(point),int(contracts),currency)
if not mods:st.info('Attiva almeno un modulo per generare segnali.')
if 'hull_signal' in mods and 'hull_trend' in mods:st.caption('Hull segnale include già Hull trend: i due filtri sono ridondanti.')
if 'forces_strong' in mods and 'forces_positive' in mods:st.caption('Forces in rafforzamento include già Forces positivo.')
if 'forces_direction' in mods and 'forces_positive' in mods and not short_term:st.caption('Con ShortTerm OFF direzione e prevalenza Forces coincidono.')
if instrument=='Serie continua: studio del segnale':st.warning('Serie continua: risultati percentuali ipotetici, non PnL di un contratto futures. Rollover, costi di roll e margini non sono simulati.')
if instrument=='Futures (contratto singolo)':st.info('Solo serie di un singolo contratto. Valuta, tick, valore punto e contratti devono corrispondere allo strumento. Nessun roll automatico; margini e conversioni valutarie non simulati.')
# Caricamenti e risultati vengono invalidati quando cambia la loro configurazione.
list_text=list_file.getvalue().decode('utf-8-sig') if list_file else text
try:
    symbols=[imported_symbol.strip().upper()] if source=='CSV / JSON' else parse_symbols(list_text,market,source)
    if len(symbols)>150:raise ValueError('Massimo 150 ticker per esecuzione; suddividere la lista.')
except ValueError as e:st.error(str(e));st.stop()
import_hash=hashlib.sha256(imported.getvalue()).hexdigest() if imported else ''
data_signature=json.dumps([source,market,timeframe,str(history_start),adjustment,feed,symbols,import_hash])
if st.session_state.get('data_signature')!=data_signature:
    st.session_state.pop('lab_data',None);st.session_state.pop('lab_results',None)
st.session_state.data_signature=data_signature
st.caption(f"{len(symbols)} ticker · {timeframe} · Forces {fsource} {sma}/{ema} · solo candele chiuse · configurazione {config_id(ind,rules)}")
if st.button('Carica dati e aggiorna screener',type='primary'):
    data={};errors=[];notes={};bar=st.progress(0)
    key=secrets_value('ALPACA_API_KEY');secret=secrets_value('ALPACA_SECRET_KEY')
    for n,symbol in enumerate(symbols):
        try:
            if source=='CSV / JSON':
                if imported is None:raise ValueError('Carica una serie CSV/JSON.')
                raw=read_import(imported.getvalue(),imported.name)
            else:raw=fetch_cached(symbol,str(history_start),str(TODAY+timedelta(days=1)),source,adjustment,feed,key,secret,hashlib.sha256(key.encode()).hexdigest()[:12])
            raw=raw[raw.index>=pd.Timestamp(history_start)]
            closed,note=completed_bars(raw,symbol,market,timeframe)
            data[symbol]=closed;notes[symbol]=note
        except Exception as exc:
            # Non stampare messaggi SDK che possono contenere richieste autenticate.
            if source=='Alpaca' and not isinstance(exc,ValueError):errors.append({'Ticker':symbol,'Errore':'Richiesta Alpaca fallita: verificare credenziali, feed e autorizzazioni.'})
            else:errors.append({'Ticker':symbol,'Errore':str(exc)[:250]})
        bar.progress((n+1)/max(1,len(symbols)))
    st.session_state.lab_data=data;st.session_state.lab_notes=notes;st.session_state.lab_errors=errors;st.session_state.pop('lab_results',None)
if st.session_state.get('lab_errors'):st.dataframe(pd.DataFrame(st.session_state.lab_errors),hide_index=True,width='stretch')
data=st.session_state.get('lab_data',{})
if not data:
    st.info('Carica la lista.txt oppure usa i ticker proposti, poi premi «Carica dati e aggiorna screener».')
    st.stop()
features={s:calculate(df,ind) for s,df in data.items()}
tabs=st.tabs(['Screener','Backtest','Confronto','Dati e metodo'])
with tabs[0]:
    rows=[]
    for s,x in features.items():
        row=x.iloc[-1];known=bool(row.ready);ok=[MODULES[k] for k in mods if known and bool(row[k])];missing=[MODULES[k]+(' · N/D' if not known else '') for k in mods if not known or not bool(row[k])]
        extras=[MODULES[k] for k in MODULES if k not in mods and known and bool(row[k]) and not(k=='forces_positive' and ('forces_strong' in mods or bool(row.forces_strong)))]
        rows.append({'Ticker':s,'Data':str(x.index[-1].date()),'Esito':f'{len(ok)}/{len(mods)}' if mods else 'NESSUN FILTRO','Soddisfatte':' · '.join(ok) or '—','Mancanti':' · '.join(missing) or '—','Altre conferme · fuori filtro':' · '.join(extras) or '—','Forces':row.forces,'mancano':len(missing)})
    table=pd.DataFrame(rows).sort_values(['mancano','Ticker'])
    view=st.selectbox('Righe',['Tutte','Solo complete','Complete + manca una'])
    if view=='Solo complete':table=table[(table.mancano==0)&bool(mods)]
    if view=='Complete + manca una':table=table[(table.mancano<=1)&bool(mods)]
    st.dataframe(table.drop(columns='mancano'),hide_index=True,width='stretch')
    st.download_button('Scarica screener CSV',csv_bytes(table.drop(columns='mancano')),'screener.csv','text/csv')
    s=st.selectbox('Dettaglio strumento',list(features),key='screen_symbol');show_chart(features[s],key='screen')
    st.caption(st.session_state.lab_notes.get(s,''))
with tabs[1]:
    s=st.selectbox('Strumento',list(features),key='bt_symbol');x=features[s]
    earliest=x.index[min(len(x)-1,max(100,5*int(ema)+int(sma),int(hull)+int(np.sqrt(hull))+2,int(atr)))].date()
    c1,c2=st.columns(2)
    start=c1.date_input('Inizio test',value=earliest,key='bt_start')
    end=c2.date_input('Fine test',value=x.index[-1].date(),key='bt_end')
    signature=json.dumps([config_id(ind,rules),s,str(start),str(end),data_signature])
    if st.session_state.get('bt_signature')!=signature:st.session_state.pop('lab_results',None)
    if st.button('Esegui backtest',disabled=not bool(mods)):
        try:
            if '=F' in s and instrument=='Futures (contratto singolo)':raise ValueError('Il ticker Yahoo =F è una serie continua: scegliere Studio del segnale oppure importare un contratto singolo.')
            if instrument=='Azioni / ETF / spot' and '=F' in s:raise ValueError('Per una serie =F scegliere «Serie continua: studio del segnale».')
            if instrument=='Futures (contratto singolo)' and adjustment=='Tutti gli aggiustamenti':raise ValueError('Per un singolo contratto usare prezzi non rettificati per dividendi.')
            st.session_state.lab_results=backtest(x,rules,str(start),str(end));st.session_state.bt_signature=signature
        except ValueError as exc:st.error(str(exc))
    result=st.session_state.get('lab_results')
    if result:
        stats=result['stats'];cs=st.columns(4)
        for col,k in zip(cs,['Rendimento %','Max drawdown %','Trade chiusi','Win rate %']):col.metric(k,f'{stats[k]:.2f}' if k!='Trade chiusi' else stats[k])
        st.caption(f"Profit factor: {stats['Profit factor']:.2f} · Equity finale: {stats['Equity finale']:.2f} {currency} · Include valorizzazione delle posizioni aperte; nessuna liquidazione artificiale a fine test.")
        show_chart(x.loc[:pd.Timestamp(end)],result,key='backtest')
        eq=result['equity'];base=x.loc[eq.index,'close']/x.loc[eq.index[0],'open']*capital
        ef=go.Figure([go.Scatter(x=eq.index,y=eq,name='Strategia'),go.Scatter(x=base.index,y=base,name='Buy & hold prezzo lordo')]);ef.update_layout(height=300);st.plotly_chart(ef,width='stretch')
        st.caption('Buy & hold: riferimento lordo di prezzo con stessa serie e capitale; senza costi, dividendi separati o leva. Non è un benchmark total return; per i futures è solo un indice di prezzo.')
        st.dataframe(result['trades'],hide_index=True,width='stretch')
        if result['open']:st.info('Posizione ancora aperta alla fine dei dati:');st.write(result['open'])
        with st.expander('Perché è entrato / uscito?'):
            if not result['trades'].empty:
                trades=result['trades'];choice=st.selectbox('Operazione',range(len(trades)),format_func=lambda j:f"{trades.iloc[j]['Ingresso'].date()} → {trades.iloc[j]['Uscita'].date()}")
                t=trades.iloc[choice];st.write({k:t[k] for k in ['Segnale','Ingresso','Uscita','Motivo','Stop','Target','PnL netto']})
                st.dataframe(x.loc[t.Segnale:t.Uscita,['open','high','low','close','ha_open','ha_close','forces','hull']+list(MODULES)],width='stretch')
        meta={'version':'1.0','config_id':config_id(ind,rules),'indicatori':asdict(ind),'regole':asdict(rules),'fonte':source,'feed':feed if source=='Alpaca' else None,'prezzi':adjustment,'ticker':s,'inizio':str(start),'fine':str(end),'nota_chiusura':st.session_state.lab_notes.get(s),'stats':stats}
        z=io.BytesIO()
        with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('configurazione.json',json.dumps(meta,indent=2,default=str))
            archive.writestr('operazioni.csv',csv_bytes(result['trades']))
            archive.writestr('indicatori_e_dati.csv',csv_bytes(x))
            archive.writestr('equity.csv',eq.to_csv())
        st.download_button('Esporta test completo ZIP',z.getvalue(),f'test_{s}_{config_id(ind,rules)}.zip','application/zip')
with tabs[2]:
    st.write('Confronta la configurazione corrente su più ticker, oppure tutte le combinazioni di un piccolo insieme di moduli. Ogni titolo ha un capitale indipendente: non è un portafoglio.')
    chosen=st.multiselect('Ticker da confrontare',list(features),default=list(features)[:min(10,len(features))])
    compare_modes=st.radio('Configurazioni',['Solo corrente','Combinazioni dei moduli scelti'],horizontal=True)
    pool=st.multiselect('Moduli candidati',list(MODULES),default=['ha','forces_positive','hull_trend'],format_func=lambda k:MODULES[k],disabled=compare_modes=='Solo corrente')
    c1,c2=st.columns(2);cstart=c1.date_input('Inizio confronto',value=max(history_start,date(2015,1,1)),key='cmp_start');cend=c2.date_input('Fine confronto',value=TODAY,key='cmp_end')
    split=st.date_input('Inizio periodo di verifica',value=date(2023,1,1),help='La graduatoria usa solo la selezione precedente a questa data. Il periodo successivo è mostrato separatamente; dopo averlo osservato non è più una riserva incontaminata.')
    mintr=st.number_input('Minimo trade chiusi in selezione',1,1000,30)
    source_compare=st.checkbox('Confronta Forces Standard e Heikin Ashi',False)
    compare_signature=json.dumps([config_id(ind,rules),chosen,compare_modes,pool,str(cstart),str(cend),str(split),mintr,source_compare,data_signature])
    if st.session_state.get('compare_signature')!=compare_signature:st.session_state.pop('comparison',None)
    if st.button('Esegui confronto',disabled=not bool(chosen)):
        try:
            if not cstart<split<=cend:raise ValueError('La data di verifica deve essere successiva all’inizio e non oltre la fine.')
            if instrument=='Futures (contratto singolo)' and any('=F' in s for s in chosen):raise ValueError('Confronto futures monetario richiede singoli contratti importati, non serie =F.')
            if instrument=='Azioni / ETF / spot' and any('=F' in s for s in chosen):raise ValueError('Scegliere Studio del segnale per serie =F.')
            combos=[mods] if compare_modes=='Solo corrente' else [c for n in range(1,len(pool)+1) for c in itertools.combinations(pool,n) if not({'hull_signal','hull_trend'}<=set(c)) and not({'forces_strong','forces_positive'}<=set(c)) and not(not short_term and {'forces_direction','forces_positive'}<=set(c))]
            if not combos or not combos[0]:raise ValueError('Selezionare almeno un modulo.')
            ftypes=['Standard','Heikin Ashi'] if source_compare else [fsource]
            if len(combos)*len(chosen)*len(ftypes)>400:raise ValueError('Massimo 400 test doppi per esecuzione; ridurre ticker o moduli.')
            output=[];errors=[];p=st.progress(0);total=len(combos)*len(chosen)*len(ftypes);done=0
            for symbol in chosen:
                for src in ftypes:
                    cfg=replace(ind,forces_source=src);xx=calculate(data[symbol],cfg)
                    for combo in combos:
                        rr=replace(rules,modules=tuple(combo));row={'Ticker':symbol,'Moduli':' + '.join(MODULES[k] for k in combo),'Forces':src,'ID':config_id(cfg,rr)}
                        try:
                            for label,begin,finish in [('Selezione',cstart,split-timedelta(days=1)),('Verifica',split,cend)]:
                                res=backtest(xx,rr,str(begin),str(finish))
                                row.update({label+' · '+k:v for k,v in res['stats'].items() if k in ['Trade chiusi','Rendimento %','Max drawdown %','Profit factor']})
                            output.append(row)
                        except ValueError as exc:errors.append({'Ticker':symbol,'Errore':str(exc)})
                        done+=1;p.progress(done/total)
            if not output:raise ValueError('Nessun test valido: controllare disponibilità dati e periodi.')
            df=pd.DataFrame(output);df['Campione sufficiente']=df['Selezione · Trade chiusi']>=mintr
            df=df.sort_values(['Campione sufficiente','Selezione · Rendimento %'],ascending=[False,False])
            st.session_state.comparison=df;st.session_state.compare_errors=errors;st.session_state.compare_signature=compare_signature
        except ValueError as exc:st.error(str(exc))
    if st.session_state.get('comparison') is not None:
        df=st.session_state.comparison;st.dataframe(df,hide_index=True,width='stretch')
        st.caption('Ordine solo per selezione e campione minimo. Rendimento include mark-to-market delle posizioni aperte. Nessuna ottimizzazione automatica su verifica; titoli di valute diverse non vengono aggregati.')
        st.download_button('Scarica confronto CSV',csv_bytes(df),'confronto.csv','text/csv')
        if st.session_state.get('compare_errors'):st.dataframe(pd.DataFrame(st.session_state.compare_errors).drop_duplicates(),hide_index=True)
with tabs[3]:
    st.markdown('''**Regole di esecuzione**: decisioni su candele chiuse; entrate e uscite da indicatore all’apertura successiva. Stop e target possono eseguire intrabar. Se entrambi sono toccati nella stessa barra, si assume lo stop prima. Le HA generano segnali: non sono prezzi di esecuzione.

**Storico e disponibilità**: almeno 100 barre di riscaldamento, aumentate per periodi EMA/Hull elevati. Il backtest non ricostruisce gli universi storici: una lista di titoli odierni introduce survivorship bias. La posizione finale resta aperta e valorizzata al close.

**Fonti**: Yahoo e Alpaca possono produrre OHLC diversi. Non unire feed o aggiustamenti nella stessa prova. Gli errori sono mostrati, senza sostituzioni silenziose. CSV/JSON deve contenere prezzi standard Daily e date di seduta coerenti.

**Costi e rischio**: costi per lato; quote frazionarie nel modello spot; nel modello futures quantità fissa e valore punto esplicito. Niente margini, FX, rollover, interessi o imposte. Dividendi non accreditati separatamente. Il drawdown è al close e può sottostimare quello intraday.

**Validazione**: confrontare prima gli indicatori con TradingView, poi scegliere sul periodo di selezione e controllare la verifica. Una combinazione migliore nello storico non è automaticamente robusta. Nessuna condizione Balance è presente.''')
    quality=[]
    for s,df in data.items():quality.append({'Ticker':s,'Prima barra':str(df.index[0].date()),'Ultima chiusa':str(df.index[-1].date()),'Barre':len(df),'Chiusura':st.session_state.lab_notes.get(s,'')})
    st.dataframe(pd.DataFrame(quality),hide_index=True,width='stretch')
    st.download_button('Scarica lista di esempio',Path(__file__).with_name('lista_esempio.txt').read_bytes(),'lista_esempio.txt','text/plain')
