from dataclasses import asdict,replace
from collections import OrderedDict
from feature_cache import cached_features
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
from engine import Indicators,Rules,MODULES,calculate,evaluate,backtest,parse_symbols,config_id,normalize_bars,invalid_ohlc,prepare_features,warmup_bars
from data_sources import yahoo,alpaca,read_import,completed_bars
from research_presets import PRESET_VERSION, PRESETS, EXIT_METHODS, PRESET_DESCRIPTIONS, prepare_preset_features, simulate_preset
from quality_audit import audit_ohlc_bars, quality_overview
st.set_page_config(page_title='G. Trend Lab',page_icon='🧪',layout='wide')
st.title('G. Trend Lab')
st.caption('v1.5.1 · Audit OHLC e confronto 2 ingressi × 5 uscite · esclusioni trasparenti')
# I risultati sono effimeri e dipendono dallo schema del motore, non solo dai parametri.
SESSION_SCHEMA = 'trend-lab-results-3'
def compatible_result(value):
    return (isinstance(value,dict) and value.get('schema')==2
        and all(k in value for k in ('stats','trades','equity','period','drawdown','run_config'))
        and all(isinstance(value.get(k),dict) for k in ('stats','period','drawdown','run_config'))
        and all(k in value['period'] for k in ('Prima barra calcolata','Ultima barra calcolata','Barre nel test'))
        and all(k in value['stats'] for k in ('Peggior trade %','Massimo perdite consecutive')))
if st.session_state.get('result_session_schema') != SESSION_SCHEMA:
    had_results=st.session_state.get('lab_results') is not None
    for name in ('lab_results','lab_features','bt_signature','comparison','compare_signature','compare_errors','feature_cache','export_cache'):
        st.session_state.pop(name,None)
    st.session_state.result_session_schema=SESSION_SCHEMA
    if had_results:st.info('App aggiornata: il precedente risultato è stato azzerato. Dati e impostazioni restano disponibili; premi Esegui backtest per ricalcolare.')

TODAY=pd.Timestamp.now(tz='Europe/Rome').date()
HELP={
'ha':'Ultima candela HA chiusa verde (close HA ≥ open HA). Non richiede una nuova inversione.',
'hull_signal':'Hull crescente con inversione recente: memoria 3 = barra del cambio e due successive.',
'hull_trend':'Hull crescente: non richiede un segnale recente.',
'forces_positive':'AV1−AV2 sopra zero, anche se la prevalenza rialzista si sta attenuando.',
'forces_strong':'Forces positivo e in aumento, oppure appena passato a positivo. Include già la prevalenza positiva.',
'ema_filter':'LONG: close standard della candela chiusa strettamente sopra la EMA del prezzo. Periodo modificabile, default 21. Non impone pendenza positiva o un nuovo incrocio. Influenza ingresso/screener, non l’uscita scelta. Con grafico HA usa comunque prezzi standard.',
'forces_direction':'Direzione Forces secondo ShortTerm/Lag. ShortTerm OFF coincide con la prevalenza positiva; ON può essere LONG anche sotto zero.',
}
def secrets_value(k):
    try:return str(st.secrets.get(k,''))
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):return ''
@st.cache_data(ttl=900,max_entries=120,show_spinner=False)
def fetch_cached(symbol,start,end,source,adjustment,feed,_key='',_secret='',account_scope='',repair=False):
    if source=='Yahoo':return yahoo(symbol,start,end,adjustment=='Tutti gli aggiustamenti',repair)
    return alpaca(symbol,start,end,_key,_secret,feed,'all' if adjustment=='Tutti gli aggiustamenti' else 'split',repair)
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
    fig.add_trace(go.Scatter(x=q.index,y=q.price_ema,name=f'EMA prezzo {int(ma_period)}',line={'color':'#287ac2','width':1.5}),row=1,col=1)
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
    repair_ohlc=st.checkbox('Correggi High/Low incoerenti',False,help='Solo se abilitato: amplia High/Low per includere Open e Close, senza modificare questi ultimi. Le barre originali vengono registrate e incluse nell’esportazione. Le correzioni possono influenzare segnali, stop e target; Se disattivato: screener solo sul tratto recente pulito; backtest bloccato se il periodo o il riscaldamento contengono anomalie.')
    st.caption('Per partire: Solo split; correzione High/Low disattivata. Su TradingView usa la stessa scelta per i dividendi. Le anomalie vengono segnalate, non corrette automaticamente.')
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
    ma_period=st.number_input('Periodo EMA prezzo',1,500,21,help='Media esponenziale sui close standard. Modifica il modulo Prezzo sopra EMA e la linea sul grafico. Il periodo EMA di Forces resta separato.')
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
ind=Indicators(int(sma),int(ema),fsource,short_term,int(lag),int(hull),int(memory),int(atr),int(ma_period))
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
data_signature=json.dumps(['1.2',source,market,timeframe,str(history_start),adjustment,feed,symbols,import_hash,repair_ohlc])
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
                raw=read_import(imported.getvalue(),imported.name,repair_ohlc)
            else:raw=fetch_cached(symbol,str(history_start),str(TODAY+timedelta(days=1)),source,adjustment,feed,key,secret,hashlib.sha256(key.encode()).hexdigest()[:12],repair_ohlc)
            raw=raw[raw.index>=pd.Timestamp(history_start)]
            closed,note=completed_bars(raw,symbol,market,timeframe,repair=repair_ohlc)
            corrections=closed.attrs.get('ohlc_corrections',[])
            if corrections:note+=f' High/Low corretti su {len(corrections)} barre (scelta esplicita).';closed.attrs['ohlc_corrections']=corrections
            data[symbol]=closed;notes[symbol]=note
        except Exception as exc:
            # Non stampare messaggi SDK che possono contenere richieste autenticate.
            if source=='Alpaca' and not isinstance(exc,ValueError):errors.append({'Ticker':symbol,'Errore':'Richiesta Alpaca fallita: verificare credenziali, feed e autorizzazioni.'})
            else:errors.append({'Ticker':symbol,'Errore':str(exc)[:250]})
        bar.progress((n+1)/max(1,len(symbols)))
    st.session_state.lab_data_revision=str(pd.Timestamp.now().value)
    st.session_state.feature_cache=OrderedDict()
    st.session_state.pop('export_cache',None)
    st.session_state.lab_data=data;st.session_state.lab_notes=notes;st.session_state.lab_errors=errors;st.session_state.pop('lab_results',None)
if st.session_state.get('lab_errors'):st.dataframe(pd.DataFrame(st.session_state.lab_errors),hide_index=True,width='stretch')
data=st.session_state.get('lab_data',{})
if not data:
    st.info('Carica la lista.txt oppure usa i ticker proposti, poi premi «Carica dati e aggiorna screener».')
    st.stop()
if 'lab_data_revision' not in st.session_state:st.session_state.lab_data_revision=str(pd.Timestamp.now().value)
if 'feature_cache' not in st.session_state:st.session_state.feature_cache=OrderedDict()
revision=st.session_state.lab_data_revision
def get_features(symbol,cfg,start=None,end=None):
    return cached_features(st.session_state.feature_cache,revision,symbol,cfg,data[symbol],start,end)
origin_label=f"{source} | {market} | {timeframe} | {adjustment} | correzione H/L: {'ON' if repair_ohlc else 'OFF'}"
quality_table,quality_bars=quality_overview(data,origin_label)
with st.expander("Qualità dati — titoli esclusi, date e prezzi OHLC anomali",expanded=bool(not quality_bars.empty)):
    st.caption("Diagnostica dei prezzi caricati. Lascia «Correggi High/Low incoerenti» su OFF per vedere le anomalie originali; con ON le barre possono essere già state corrette esplicitamente a monte. Il confronto non modifica mai i prezzi.")
    st.dataframe(quality_table,hide_index=True,width='stretch')
    st.download_button('Scarica riepilogo qualità CSV',csv_bytes(quality_table),'trend_lab_qualita_titoli.csv','text/csv',key='quality_overview_export')
    if not quality_bars.empty:
        st.warning(f"{quality_bars['Ticker'].nunique()} titoli hanno almeno una barra anomala. Non sono inclusi nel confronto completo.")
        st.dataframe(quality_bars,hide_index=True,width='stretch')
        st.download_button('Scarica dettaglio barre anomale CSV',csv_bytes(quality_bars),'trend_lab_barre_ohlc_anomale.csv','text/csv',key='quality_bars_export')
    else:
        st.success("Nessuna barra OHLC anomala rilevata negli storici caricati.")
section=st.radio('Sezione',['Screener','Backtest','Confronto uscite','Confronto','Dati e metodo'],horizontal=True,key='section')
if section=='Confronto uscite':
    st.subheader('Confronto uscite — 2 ingressi × 5 uscite')
    st.caption(f'Protocollo {PRESET_VERSION} · Daily LONG · ingresso A Standard 7/7 oppure B Heikin Ashi 7/7 · HA verde + Close sopra EMA 200 · 5 uscite · open successivo · costi 0,15% per lato.')
    st.info('10 combinazioni congelate, non un ottimizzatore. E2: uscita totale dopo due diminuzioni consecutive di Forces Standard 10/4 positivo, oppure allo zero. E5: 50% alla stessa attenuazione, restante 50% allo zero; se arriva allo zero prima, uscita integrale. Le vendite parziali hanno costi proporzionali. Supertrend da confrontare con TradingView.')
    if timeframe!='Daily':
        st.warning('Confronto disponibile solo su timeframe Daily.')
    elif instrument=='Futures (contratto singolo)':
        st.warning('Per adesso i preset simulano rendimenti percentuali azionari, non PnL futures: usa Azioni / ETF / spot.')
    else:
        first_date=min(frame.index[0].date() for frame in data.values())
        last_date=max(frame.index[-1].date() for frame in data.values())
        a,b=st.columns(2)
        period_from=a.date_input('Inizio test uscite',value=max(first_date,date(2010,1,1)),min_value=first_date,max_value=last_date,key='abc_start')
        period_to=b.date_input('Fine test uscite',value=last_date,min_value=first_date,max_value=last_date,key='abc_end')
        if period_from>period_to:
            st.error('La data iniziale deve precedere la data finale.')
        else:
            st.caption('L’EMA 200 e Forces richiedono barre di riscaldamento precedenti alla data iniziale. Le posizioni ancora aperte sono riportate separatamente; i rendimenti sono composti delle sole operazioni chiuse.')
            if st.button('Esegui confronto 2 ingressi × 5 uscite',type='primary',key='abc_run'):
                rows_abc=[]
                operations_abc=[]
                executions_abc=[]
                errors_abc=[]
                for symbol,frame in data.items():
                    try:
                        anomalies=audit_ohlc_bars(frame,symbol,origin_label)
                        if anomalies:
                            first=", ".join(row["Data"] for row in anomalies[:3])
                            raise ValueError(f"{len(anomalies)} barre OHLC anomale: {first}. Vedi audit e scarica CSV.")
                        if len(frame)<220:
                            raise ValueError(f"Solo {len(frame)} barre: ne servono almeno 220 per il confronto.")
                        f=prepare_preset_features(frame)
                        for preset in PRESETS:
                            for exit_method in EXIT_METHODS:
                                res=simulate_preset(frame,f,preset,period_from,period_to,exit_method=exit_method)
                                rows_abc.append({k:v for k,v in res.items() if k not in ('Operazioni','Esecuzioni','Equity')}|{'Ticker':symbol,'Prima seduta dati':str(frame.index[0].date()),'Ultima seduta dati':str(frame.index[-1].date()),'Impronta OHLC':quality_table.loc[quality_table.Ticker==symbol,'Impronta OHLC'].iloc[0],'Origine dati':origin_label})
                                if not res['Operazioni'].empty:
                                    tx=res['Operazioni'].copy()
                                    tx.insert(0,'Ticker',symbol)
                                    tx.insert(1,'Preset',preset)
                                    tx.insert(2,'Metodo uscita',exit_method)
                                    operations_abc.append(tx)
                                if not res['Esecuzioni'].empty:
                                    fills=res['Esecuzioni'].copy()
                                    fills.insert(0,'Ticker',symbol)
                                    executions_abc.append(fills)
                    except Exception as exc:
                        errors_abc.append({'Ticker':symbol,'Errore':str(exc)})
                st.session_state.abc_results={'rows':rows_abc,'trades':pd.concat(operations_abc,ignore_index=True) if operations_abc else pd.DataFrame(),'fills':pd.concat(executions_abc,ignore_index=True) if executions_abc else pd.DataFrame(),'errors':errors_abc,'periodo':(str(period_from),str(period_to)),'revision':revision,'protocol':PRESET_VERSION}
            abc=st.session_state.get('abc_results')
            if abc:
                if abc['revision']!=revision or abc['periodo']!=(str(period_from),str(period_to)) or abc.get('protocol')!=PRESET_VERSION:
                    st.warning('Risultati riferiti ad altri dati o date: ripeti il confronto.')
                else:
                    frame=pd.DataFrame(abc['rows'])
                    if not frame.empty:
                        st.dataframe(frame[['Ticker','Preset','Uscita','ID','Trade chiusi','Vincenti %','Durata media','Rendimento realizzato %','Rendimento con aperta %','Drawdown massimo %','Posizione aperta','Posizione residua %']],hide_index=True,width='stretch')
                        st.download_button('Scarica confronto uscite CSV',csv_bytes(frame),'trend_lab_confronto_uscite.csv','text/csv')
                        if not abc['trades'].empty:
                            st.download_button('Scarica operazioni per uscita CSV',csv_bytes(abc['trades']),'trend_lab_operazioni_per_uscita.csv','text/csv')
                        if not abc['fills'].empty:
                            st.download_button('Scarica tutte le esecuzioni, incluse le vendite 50%',csv_bytes(abc['fills']),'trend_lab_esecuzioni_parziali.csv','text/csv')
                        st.caption('E5 non è un’uscita completa al primo segnale: metà resta investita. Risultati storici esplorativi; il precedente +57,7% B3 non è confermato automaticamente. Posizioni aperte e dividendi richiedono verifica.')
                    if abc['errors']:
                        st.warning(f"{len(abc['errors'])} titoli esclusi dal confronto; i relativi risultati NON sono considerati.")
                        err_df=pd.DataFrame(abc['errors'])
                        st.dataframe(err_df,hide_index=True,width='stretch')
                        st.download_button('Scarica titoli esclusi CSV',csv_bytes(err_df),'trend_lab_titoli_esclusi.csv','text/csv',key='comparison_exclusions')
if section=='Screener':
    features={};screen_quality={}
    for symbol,df in data.items():
        try:
            xx=get_features(symbol,ind)
            if bool(xx.ready.iloc[-1]):features[symbol]=xx
            else:screen_quality[symbol]=f'Servono {warmup_bars(ind)} barre pulite consecutive prima di pubblicare il segnale.'
        except ValueError as exc:screen_quality[symbol]=str(exc)
    rows=[]
    for s,x in features.items():
        row=x.iloc[-1];known=bool(row.ready);ok=[MODULES[k] for k in mods if known and bool(row[k])];missing=[MODULES[k]+(' · N/D' if not known else '') for k in mods if not known or not bool(row[k])]
        extras=[MODULES[k] for k in MODULES if k not in mods and known and bool(row[k]) and not(k=='forces_positive' and ('forces_strong' in mods or bool(row.forces_strong)))]
        rows.append({'Ticker':s,'Data':str(x.index[-1].date()),'Esito':f'{len(ok)}/{len(mods)}' if mods else 'NESSUN FILTRO','Soddisfatte':' · '.join(ok) or '—','Mancanti':' · '.join(missing) or '—','Altre conferme · fuori filtro':' · '.join(extras) or '—','Forces':row.forces,'Qualità dati':('Storico pulito dal '+str(x.index[0].date())) if x.attrs.get('quality_restart') else 'OK','mancano':len(missing)})
    for symbol,reason in screen_quality.items():
        rows.append({'Ticker':symbol,'Data':str(data[symbol].index[-1].date()),'Esito':'N/D','Soddisfatte':'—','Mancanti':'Dati non verificabili','Altre conferme · fuori filtro':'—','Forces':np.nan,'Qualità dati':reason,'mancano':99})
    table=pd.DataFrame(rows).sort_values(['mancano','Ticker'])
    view=st.selectbox('Righe',['Tutte','Solo complete','Complete + manca una'])
    if view=='Solo complete':table=table[(table.mancano==0)&bool(mods)]
    if view=='Complete + manca una':table=table[(table.mancano<=1)&bool(mods)]
    st.dataframe(table.drop(columns='mancano'),hide_index=True,width='stretch')
    st.download_button('Scarica screener CSV',csv_bytes(table.drop(columns='mancano')),'screener.csv','text/csv')
    if features:
        s=st.selectbox('Dettaglio strumento',list(features),key='screen_symbol');show_chart(features[s],key='screen')
        st.caption(st.session_state.lab_notes.get(s,''))
if section=='Backtest':
    s=st.selectbox('Strumento',list(data),key='bt_symbol');raw_test=data[s]
    bad=invalid_ohlc(raw_test)
    last_bad=np.flatnonzero(bad.to_numpy())
    clean_start=int(last_bad[-1])+1 if len(last_bad) else 0
    earliest=raw_test.index[min(len(raw_test)-1,clean_start+warmup_bars(ind))].date()
    with st.form('backtest_period_form'):
        c1,c2=st.columns(2)
        start=c1.date_input('Inizio test',value=earliest,min_value=raw_test.index[0].date(),max_value=raw_test.index[-1].date(),key='bt_start')
        end=c2.date_input('Fine test',value=raw_test.index[-1].date(),min_value=raw_test.index[0].date(),max_value=raw_test.index[-1].date(),key='bt_end')
        st.caption('Premi Esegui backtest per applicare le date. Il riepilogo sottostante riporta sempre il periodo dell’ultima esecuzione, non le modifiche ancora da inviare.')
        submitted=st.form_submit_button('Esegui backtest',disabled=not bool(mods))
    signature=json.dumps([config_id(ind,rules),s,str(start),str(end),data_signature,revision])
    if st.session_state.get('bt_signature')!=signature:st.session_state.pop('lab_results',None)
    if submitted:
        st.session_state.pop('lab_results',None)
        try:
            if '=F' in s and instrument=='Futures (contratto singolo)':raise ValueError('Il ticker Yahoo =F è una serie continua: scegliere Studio del segnale oppure importare un contratto singolo.')
            if instrument=='Azioni / ETF / spot' and '=F' in s:raise ValueError('Per una serie =F scegliere «Serie continua: studio del segnale».')
            if instrument=='Futures (contratto singolo)' and adjustment=='Tutti gli aggiustamenti':raise ValueError('Per un singolo contratto usare prezzi non rettificati per dividendi.')
            x=get_features(s,ind,str(start),str(end))
            st.session_state.lab_features=x
            result_run=backtest(x,rules,str(start),str(end))
            result_run['run_config']={'Ticker':s,'Timeframe':timeframe,'Configurazione':config_id(ind,rules),'Forces':fsource,'SMA':int(sma),'EMA':int(ema),'Uscita':exit_mode,'EMA prezzo':int(ma_period),'Filtro EMA':('ema_filter' in mods),'Calcolato':pd.Timestamp.now(tz='Europe/Rome').isoformat()}
            if not compatible_result(result_run):raise ValueError('Motore in aggiornamento: il risultato usa un formato precedente. Ricarica la pagina e ripeti Esegui backtest.')
            st.session_state.lab_results=result_run;st.session_state.bt_signature=signature
        except ValueError as exc:st.error(str(exc))
    result=st.session_state.get('lab_results')
    if result is not None and (not compatible_result(result) or 'lab_features' not in st.session_state):
        st.session_state.pop('lab_results',None)
        st.session_state.pop('bt_signature',None)
        result=None
        st.info('Il risultato salvato appartiene a una versione precedente o è incompleto. Premi Esegui backtest per ricalcolarlo con il nuovo formato.')
    if result:

        x=st.session_state.lab_features
        period=result['period'];run=result['run_config']
        st.success(f"Risultato calcolato: {run['Ticker']} · {run['Timeframe']} · {period['Prima barra calcolata']} → {period['Ultima barra calcolata']} · {period['Barre nel test']} barre")
        st.caption(f"Forces {run['Forces']} {run['SMA']}/{run['EMA']} · uscita {run['Uscita']} · calcolo {run['Calcolato']} · EMA prezzo {run['EMA prezzo']} ({'filtro ON' if run['Filtro EMA'] else 'filtro OFF'}) · ID {run['Configurazione']}")
        stats=result['stats'];cs=st.columns(4)
        for col,k in zip(cs,['Rendimento %','Max drawdown %','Trade chiusi','Win rate %']):
            label='Max drawdown conto %' if k=='Max drawdown %' else k
            help_text='Massimo calo cumulato dell’equity da un precedente picco, su tutto il periodo. Non è la perdita di un singolo trade. Comprende costi e posizioni aperte al close.' if k=='Max drawdown %' else None
            col.metric(label,f'{stats[k]:.2f}' if k!='Trade chiusi' else stats[k],help=help_text)
        worst=stats['Peggior trade %']
        st.caption(f"Peggior trade chiuso: {worst:.2f}% del capitale all’ingresso · massima sequenza di perdite: {stats['Massimo perdite consecutive']}" if worst is not None else 'Nessun trade chiuso nel periodo.')
        with st.expander('Come si forma il drawdown del conto'):
            detail=result['drawdown']
            peak_label=str(detail['Picco data'].date()) if detail['Picco data'] is not None else 'capitale iniziale'
            trough_label=str(detail['Minimo data'].date()) if detail['Minimo data'] is not None else 'inizio test'
            st.write(f"Picco: {detail['Picco equity']:.2f} {currency} ({peak_label}). Minimo successivo: {detail['Minimo equity']:.2f} {currency} ({trough_label}).")
            st.write(f"({detail['Minimo equity']:.2f} / {detail['Picco equity']:.2f} − 1) × 100 = {detail['Drawdown %']:.2f}%.")
            st.write('L’uscita HA rossa viene decisa alla chiusura della prima HA rossa ed eseguita all’open successivo. Non impedisce perdite nella candela rossa né gap avversi. Molte perdite piccole possono accumularsi nel conto.')
            if not result['trades'].empty:
                st.dataframe(result['trades'].sort_values('Netto % capitale ingresso').head(5),hide_index=True,width='stretch')
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
        meta={'version':'1.3','config_id':config_id(ind,rules),'indicatori':asdict(ind),'regole':asdict(rules),'fonte':source,'feed':feed if source=='Alpaca' else None,'prezzi':adjustment,'ticker':s,'inizio':str(start),'fine':str(end),'nota_chiusura':st.session_state.lab_notes.get(s),'inizio_storico_pulito':str(x.index[0].date()),'correzione_attiva':repair_ohlc,'stats':stats,'periodo_effettivo':result['period'],'drawdown_dettaglio':result['drawdown'],'esecuzione':result['run_config'],'correzioni_ohlc_originali':data[s].attrs.get('ohlc_corrections',[])}
        export_key=signature+run['Calcolato']
        if st.session_state.get('export_cache',{}).get('key')!=export_key:
            z=io.BytesIO()
            with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('configurazione.json',json.dumps(meta,indent=2,default=str))
                archive.writestr('operazioni.csv',csv_bytes(result['trades']))
                archive.writestr('indicatori_e_dati.csv',csv_bytes(x))
                archive.writestr('equity.csv',eq.to_csv())
            st.session_state.export_cache={'key':export_key,'bytes':z.getvalue()}
        st.download_button('Esporta test completo ZIP',st.session_state.export_cache['bytes'],f'test_{s}_{config_id(ind,rules)}.zip','application/zip')
if section=='Confronto':
    st.write('Confronta la configurazione corrente su più ticker, oppure tutte le combinazioni di un piccolo insieme di moduli. Ogni titolo ha un capitale indipendente: non è un portafoglio.')
    chosen=st.multiselect('Ticker da confrontare',list(data),default=list(data)[:min(10,len(data))])
    compare_modes=st.radio('Configurazioni',['Solo corrente','Combinazioni dei moduli scelti'],horizontal=True)
    pool=st.multiselect('Moduli candidati',list(MODULES),default=['ha','forces_positive','hull_trend'],format_func=lambda k:MODULES[k],disabled=compare_modes=='Solo corrente')
    c1,c2=st.columns(2);cstart=c1.date_input('Inizio confronto',value=max(history_start,date(2015,1,1)),min_value=history_start,max_value=TODAY,key='cmp_start');cend=c2.date_input('Fine confronto',value=TODAY,min_value=history_start,max_value=TODAY,key='cmp_end')
    split=st.date_input('Inizio periodo di verifica',value=max(history_start,min(TODAY,date(2023,1,1))),min_value=history_start,max_value=TODAY,help='La graduatoria usa solo la selezione precedente a questa data. Il periodo successivo è mostrato separatamente; dopo averlo osservato non è più una riserva incontaminata.')
    mintr=st.number_input('Minimo trade chiusi in selezione',1,1000,30)
    source_compare=st.checkbox('Confronta Forces Standard e Heikin Ashi',False)
    compare_signature=json.dumps([config_id(ind,rules),chosen,compare_modes,pool,str(cstart),str(cend),str(split),mintr,source_compare,data_signature,revision])
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
                    cfg=replace(ind,forces_source=src)
                    for combo in combos:
                        rr=replace(rules,modules=tuple(combo));row={'Ticker':symbol,'Moduli':' + '.join(MODULES[k] for k in combo),'Forces':src,'ID':config_id(cfg,rr)}
                        try:
                            for label,begin,finish in [('Selezione',cstart,split-timedelta(days=1)),('Verifica',split,cend)]:
                                xx=get_features(symbol,cfg,str(begin),str(finish))
                                res=backtest(xx,rr,str(begin),str(finish))
                                row.update({label+' · '+k:v for k,v in res['stats'].items() if k in ['Trade chiusi','Rendimento %','Max drawdown %','Profit factor']})
                            output.append(row)
                        except ValueError as exc:errors.append({'Ticker':symbol,'Errore':str(exc)})
                        done+=1;p.progress(done/total)
            if not output:
                st.session_state.compare_errors=errors
                if errors:st.dataframe(pd.DataFrame(errors).drop_duplicates(),hide_index=True)
                raise ValueError('Nessun test valido: controllare disponibilità dati e periodi.')
            df=pd.DataFrame(output);df['Campione sufficiente']=df['Selezione · Trade chiusi']>=mintr
            df=df.sort_values(['Campione sufficiente','Selezione · Rendimento %'],ascending=[False,False])
            st.session_state.comparison=df;st.session_state.compare_errors=errors;st.session_state.compare_signature=compare_signature
        except ValueError as exc:st.error(str(exc))
    if st.session_state.get('comparison') is not None:
        df=st.session_state.comparison;st.dataframe(df,hide_index=True,width='stretch')
        st.caption('Ordine solo per selezione e campione minimo. Rendimento include mark-to-market delle posizioni aperte. Nessuna ottimizzazione automatica su verifica; titoli di valute diverse non vengono aggregati.')
        st.download_button('Scarica confronto CSV',csv_bytes(df),'confronto.csv','text/csv')
        if st.session_state.get('compare_errors'):st.dataframe(pd.DataFrame(st.session_state.compare_errors).drop_duplicates(),hide_index=True)
if section=='Dati e metodo':
    st.markdown('''**Regole di esecuzione**: decisioni su candele chiuse; entrate e uscite da indicatore all’apertura successiva. Stop e target possono eseguire intrabar. Se entrambi sono toccati nella stessa barra, si assume lo stop prima. Le HA generano segnali: non sono prezzi di esecuzione.

**Storico e disponibilità**: almeno 100 barre di riscaldamento, aumentate per periodi EMA/Hull elevati. Il backtest non ricostruisce gli universi storici: una lista di titoli odierni introduce survivorship bias. La posizione finale resta aperta e valorizzata al close.

**Fonti**: Yahoo e Alpaca possono produrre OHLC diversi. Non unire feed o aggiustamenti nella stessa prova. Gli errori sono mostrati, senza sostituzioni silenziose. CSV/JSON deve contenere prezzi standard Daily e date di seduta coerenti.

**Costi e rischio**: costi per lato; quote frazionarie nel modello spot; nel modello futures quantità fissa e valore punto esplicito. Niente margini, FX, rollover, interessi o imposte. Dividendi non accreditati separatamente. Il drawdown è al close e può sottostimare quello intraday.

**Validazione**: confrontare prima gli indicatori con TradingView, poi scegliere sul periodo di selezione e controllare la verifica. Una combinazione migliore nello storico non è automaticamente robusta. Nessuna condizione Balance è presente.

**EMA prezzo**: modulo facoltativo, default OFF, periodo 21 modificabile. Close standard sopra EMA, senza vincolo di incrocio o pendenza. La regola di uscita resta quella scelta. La media disegnata usa sempre prezzi standard.

**Prestazioni**: nel Backtest gli indicatori vengono calcolati solo premendo Esegui, per il titolo scelto. Costi/stop/uscite riutilizzano gli indicatori; il confronto riutilizza gli stessi calcoli fra combinazioni. La cache viene invalidata al ricaricamento dei dati.

**Anomalie OHLC**: lo screener usa soltanto l’ultimo tratto pulito con riscaldamento sufficiente. Il backtest viene bloccato se il periodo contiene anomalie o lo storico pulito precedente non basta. La correzione High/Low è facoltativa ed esplicita. Le candele aperte sono escluse prima di controllare gli OHLC.''')
    quality=[]
    for s,df in data.items():quality.append({'Ticker':s,'Prima barra':str(df.index[0].date()),'Ultima chiusa':str(df.index[-1].date()),'Barre':len(df),'Barre anomale non corrette':int(invalid_ohlc(df).sum()),'Ultima anomalia':str(df.index[invalid_ohlc(df)][-1].date()) if invalid_ohlc(df).any() else '—','Chiusura':st.session_state.lab_notes.get(s,'')})
    st.dataframe(pd.DataFrame(quality),hide_index=True,width='stretch')
    for symbol,df in data.items():
        bad=invalid_ohlc(df)
        if bad.any():
            with st.expander('Barre anomale originali · '+symbol):st.dataframe(df.loc[bad],width='stretch')
        if df.attrs.get('ohlc_corrections'):
            with st.expander('Barre originali corrette · '+symbol):st.dataframe(pd.DataFrame(df.attrs['ohlc_corrections']),width='stretch')
    st.download_button('Scarica lista di esempio',Path(__file__).with_name('lista_esempio.txt').read_bytes(),'lista_esempio.txt','text/plain')




