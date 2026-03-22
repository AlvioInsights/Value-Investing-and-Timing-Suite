import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import logging
import concurrent.futures
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Tuple, List

# ==========================================
# 0. SETUP LOGGING & COSTANTI GLOBALI
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_TAX_RATE = 0.21
SAFE_INTEREST_COVERAGE = 100.0
TRADING_DAYS_YEAR = 252
MAX_CSV_ROWS = 100
MAX_WORKERS = 10  # Numero di thread simultanei per il download veloce

# ==========================================
# CONFIGURAZIONE PAGINA UI
# ==========================================
st.set_page_config(
    page_title="Value Investing & Timing Suite",
    page_icon="💎",
    layout="wide"
)

# ==========================================
# 1. MODELLI DATI (Dataclasses)
# ==========================================
@dataclass
class FundamentalMetrics:
    ticker: str
    company_name: str
    price: float
    fcf: float
    roic: float
    peg_ratio: Optional[float]
    peg_source: str
    pe_ratio: Optional[float]
    interest_coverage: float
    currency: str
    raw_data: Dict[str, Any]

    def to_ui_dict(self) -> Dict[str, Any]:
        """Converte il modello in un dizionario compatibile con l'interfaccia Pandas/Streamlit."""
        return {
            "Ticker": self.ticker,
            "Company Name": self.company_name,
            "Price": self.price,
            "Free Cash Flow": self.fcf,
            "ROIC": self.roic,
            "PEG Ratio": self.peg_ratio,
            "PEG Source": self.peg_source,
            "P/E Ratio": self.pe_ratio,
            "Interest Coverage": self.interest_coverage,
            "Currency": self.currency,
            "_raw_data": self.raw_data
        }

# ==========================================
# 2. HELPER FUNCTIONS & VALIDAZIONE
# ==========================================
def sanitize_ticker(ticker: str) -> str:
    """Pulisce e valida il ticker usando un'espressione regolare."""
    clean = str(ticker).strip().upper()
    if not re.match(r"^[A-Z0-9\-\.]+$", clean):
        raise ValueError(f"Ticker contiene caratteri non validi: {clean}")
    return clean

def normalize_ticker(ticker: str, suffix: str) -> str:
    """Aggiunge il suffisso di mercato con validazione stringente di sicurezza."""
    clean_ticker = sanitize_ticker(ticker)
    clean_suffix = str(suffix).strip().upper()
    
    if clean_suffix and not re.match(r"^\.[A-Z]+$", clean_suffix):
        logger.warning(f"Tentativo di injection o suffisso non valido ignorato: '{clean_suffix}'")
        clean_suffix = ""
        
    if clean_suffix and not clean_ticker.endswith(clean_suffix):
        return f"{clean_ticker}{clean_suffix}"
    return clean_ticker

# ==========================================
# 3. DATA ENGINE: ANALISI FONDAMENTALE
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_fundamental_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Scarica i dati di bilancio con logging degli errori specifici."""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        if not info or 'symbol' not in info:
            logger.warning(f"Ticker non trovato o delistato: {symbol}")
            return None
        return {
            "info": info,
            "financials": stock.financials,
            "balance_sheet": stock.balance_sheet,
            "cashflow": stock.cashflow,
            "symbol": symbol
        }
    except Exception as e:
        logger.error(f"Errore API Yahoo per {symbol}: {str(e)}")
        return None

def calculate_fundamental_metrics(raw_data: Dict[str, Any]) -> Optional[FundamentalMetrics]:
    """Orchestratore per il calcolo delle metriche. Ritorna una Dataclass sicura."""
    try:
        fin = raw_data["financials"]
        bs = raw_data["balance_sheet"]
        cf = raw_data["cashflow"]
        info = raw_data["info"]
        
        # 1. FCF
        op_cash = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0.0
        cap_ex = cf.loc['Capital Expenditure'].iloc[0] if 'Capital Expenditure' in cf.index else 0.0
        fcf = float(op_cash + cap_ex)

        # 2. ROIC
        total_debt = bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0.0
        equity = bs.loc['Stockholders Equity'].iloc[0] if 'Stockholders Equity' in bs.index else 1.0
        invested_cap = total_debt + equity

        ebit = fin.loc['EBIT'].iloc[0] if 'EBIT' in fin.index else 0.0
        tax_rate = DEFAULT_TAX_RATE
        if 'Tax Provision' in fin.index and 'Pretax Income' in fin.index:
            pretax_inc = fin.loc['Pretax Income'].iloc[0]
            if pretax_inc != 0:
                tax_rate = fin.loc['Tax Provision'].iloc[0] / pretax_inc
        roic = float((ebit * (1 - tax_rate)) / invested_cap)

        # 3. PEG & PE
        peg = info.get('pegRatio')
        pe = info.get('trailingPE')
        growth = info.get('earningsGrowth')
        peg_src = "N/A"
        
        if peg is not None:
            peg_src = "Official"
        elif pe is not None and growth is not None and growth > 0:
            try:
                peg = float(pe / (growth * 100))
                peg_src = "Estimated"
            except ZeroDivisionError:
                pass

        # 4. Interest Coverage
        int_exp = 0.0
        if 'Interest Expense' in fin.index:
            int_exp = fin.loc['Interest Expense'].iloc[0]
        elif 'Interest Expense Non Operating' in fin.index:
            int_exp = fin.loc['Interest Expense Non Operating'].iloc[0]
            
        int_cov = float(ebit / abs(int_exp)) if int_exp != 0 else SAFE_INTEREST_COVERAGE

        return FundamentalMetrics(
            ticker=raw_data["symbol"],
            company_name=info.get('longName', raw_data["symbol"]),
            price=float(info.get('currentPrice', 0.0)),
            fcf=fcf,
            roic=roic,
            peg_ratio=float(peg) if peg else None,
            peg_source=peg_src,
            pe_ratio=float(pe) if pe else None,
            interest_coverage=int_cov,
            currency=info.get('currency', 'USD'),
            raw_data=raw_data
        )
    except (KeyError, IndexError) as e:
        logger.warning(f"Struttura bilancio anomala per {raw_data['symbol']} (Manca: {e})")
        return None
    except Exception as e:
        logger.error(f"Errore critico calcolo metriche per {raw_data['symbol']}: {str(e)}")
        return None

def get_fcf_history(raw_data: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """Prepara la serie storica del Free Cash Flow."""
    try:
        cf = raw_data["cashflow"]
        if 'Operating Cash Flow' in cf.index and 'Capital Expenditure' in cf.index:
            fcf_series = (cf.loc['Operating Cash Flow'] + cf.loc['Capital Expenditure']).sort_index(ascending=True)
            df_chart = pd.DataFrame({"Free Cash Flow": fcf_series})
            df_chart.index = df_chart.index.year.astype(str)
            return df_chart
        return None
    except Exception as e:
        logger.warning(f"Impossibile generare FCF history: {str(e)}")
        return None

# ==========================================
# 4. DATA ENGINE: ANALISI TECNICA
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def get_technical_data(symbol: str) -> Optional[pd.DataFrame]:
    try:
        df = yf.download(symbol, period="2y", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) < 200:
            logger.warning(f"Dati storici insufficienti per {symbol} (< 200 giorni)")
            return None
        return df
    except Exception as e:
        logger.error(f"Errore download tecnico per {symbol}: {str(e)}")
        return None

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    data['SMA_50'] = ta.sma(data['Close'], length=50)
    data['SMA_200'] = ta.sma(data['Close'], length=200)
    data['RSI'] = ta.rsi(data['Close'], length=14)
    
    bb = ta.bbands(data['Close'], length=20, std=2)
    if bb is not None:
        data['BB_Lower'] = bb.iloc[:, 0]
        data['BB_Upper'] = bb.iloc[:, 2]
    else:
        data['BB_Lower'], data['BB_Upper'] = 0.0, 0.0
    return data

def calculate_timing_score(data: pd.DataFrame, current_price: float) -> Tuple[int, List[str]]:
    score = 0
    reasons =[]
    last_row = data.iloc[-1]
    
    if current_price > last_row['SMA_200']:
        score += 30
        reasons.append("✅ Trend Rialzista (Sopra SMA 200)")
    else:
        reasons.append("⚠️ Trend Ribassista (Sotto SMA 200)")

    rsi = last_row['RSI']
    if pd.notna(rsi):
        if rsi < 30:
            score += 30
            reasons.append("✅ Ipervenduto (RSI < 30) - Buy Opportunity")
        elif rsi < 45:
            score += 20
            reasons.append("✅ RSI Scarico (< 45)")
        elif rsi > 70:
            score -= 10
            reasons.append("🛑 Ipercomprato (RSI > 70) - Rischio Storno")
    
    if current_price <= last_row['BB_Lower'] * 1.02:
        score += 20
        reasons.append("✅ Prezzo su Banda Bollinger Inferiore")
    
    min_52w = data['Low'].tail(TRADING_DAYS_YEAR).min()
    if current_price <= min_52w * 1.05:
        score += 20
        reasons.append("✅ Vicino ai Minimi a 52 Settimane")
        
    return score, reasons

# ==========================================
# 5. UI COMPONENTS: GUIDE DIDATTICHE
# ==========================================
def render_fundamental_guide():
    """Mostra la guida all'analisi fondamentale."""
    with st.expander("📖 GUIDA: Come leggere l'Analisi Fondamentale"):
        st.markdown("""
        Questa sezione fa una radiografia alla salute dell'azienda per valutare la qualità del business e stimare se il prezzo attuale ha senso.
        
        *   **Free Cash Flow (FCF - La Cassa Vera):** È la quantità di denaro contante che rimane all'azienda dopo aver pagato le spese e gli investimenti necessari. Se l'utile contabile può essere manipolato, la cassa in banca è reale. Un FCF costantemente positivo e in crescita è il motore di dividendi e solidità.
        *   **ROIC (Efficienza e Moat):** Misura la bravura del management nel far fruttare il capitale investito. Un ROIC stabile sopra il 10-15% è storicamente il segnale più forte di un "Moat" (un vantaggio competitivo duraturo rispetto ai concorrenti).
        *   **PEG Ratio & P/E (Valutazione):** Il P/E indica quanto paghi oggi per 1 dollaro di utile. Il PEG contestualizza il P/E dividendolo per la crescita attesa. Un P/E di 30 può essere giustificato se l'azienda cresce del 40% annuo (PEG < 1). Un PEG tra 1.0 e 1.5 indica solitamente una valutazione ragionevole (*Fair Value*).
        *   **Interest Coverage (Sicurezza del Debito):** Indica quante volte l'azienda può coprire la spesa per interessi con i suoi guadagni operativi (EBIT). Un valore superiore a 3x è considerato un margine di sicurezza adeguato contro aumenti dei tassi o cali di fatturato.
        
        ⚠️ **Disclaimer:** *I dati fondamentali guardano al passato per stimare il futuro. Eventi macroeconomici o cambi di management possono alterare queste dinamiche.*
        """)

def render_technical_guide():
    """Mostra la guida all'analisi tecnica."""
    with st.expander("📖 GUIDA: Come leggere lo Score e il Grafico"):
        st.markdown("""
        L'Analisi Tecnica analizza il comportamento dei prezzi e i volumi per identificare i trend. Non prevede il futuro, ma aiuta a ottimizzare il rischio d'ingresso (il "Timing").

        ### 🚦 Il Timing Score (0-100)
        *   **🟢 80-100 (Area di Forza/Sconto):** Il trend primario è positivo, ma il prezzo ha subìto una correzione a breve termine. Statisticamente, è un'area di ingresso con un buon rapporto rischio/rendimento.
        *   **🟠 40-79 (Neutro):** Il prezzo è in equilibrio. Zona adatta per ingressi frazionati (PAC) senza esporsi troppo.
        *   **🔴 0-39 (Attesa/Pericolo):** Può indicare due scenari opposti ma ugualmente rischiosi: il trend è nettamente ribassista (meglio non afferrare un "coltello che cade"), oppure il titolo è salito verticalmente e necessita di scaricare l'eccesso (ipercomprato).

        ### 📉 Le Linee del Grafico (Prezzo)
        *   **Linea Blu (SMA 200):** Lo spartiacque del trend primario. Prezzi stabilmente SOPRA indicano un mercato rialzista ("Toro"). Prezzi SOTTO indicano debolezza ("Orso").
        *   **Linea Arancione (SMA 50):** Trend di medio periodo.
        *   **Linee Tratteggiate (Bande di Bollinger):** Misurano la volatilità. Il tocco della banda superiore indica un possibile allungo eccessivo (resistenza), il tocco di quella inferiore indica un'area di probabile supporto dinamico.

        ### 🟣 Il Grafico Inferiore (RSI a 14 periodi)
        L'RSI (Relative Strength Index) è un oscillatore di momentum.
        *   **Sopra 70 (Ipercomprato):** Fase di potenziale euforia. Il prezzo è salito in fretta e aumenta la probabilità di prese di beneficio (storni).
        *   **Sotto 30 (Ipervenduto):** Fase di potenziale panico. Il titolo è stato iper-venduto. *Attenzione: in un mercato "Orso" molto forte, l'RSI può restare sotto 30 per lunghi periodi.*
        
        ⚠️ **Disclaimer:** *L'Analisi Tecnica e il Timing Score si basano su probabilità statistiche storiche. Nessun indicatore garantisce il successo dell'operazione. Usa sempre il buon senso.*
        """)

# ==========================================
# 6. UI COMPONENTS: PROMPT AI E STYLING
# ==========================================
def _build_ai_prompt(row: pd.Series) -> str:
    fcf = row.get('Free Cash Flow', 0.0)
    fcf_str = f"{fcf/1e9:.2f}B" if abs(fcf)>1e9 else f"{fcf/1e6:.2f}M"
    pe = f"{row.get('P/E Ratio'):.2f}" if pd.notnull(row.get('P/E Ratio')) else "N/A"
    peg = f"{row.get('PEG Ratio'):.2f}" if pd.notnull(row.get('PEG Ratio')) else "N/A"
    
    return f"""Agisci come un Senior Financial Analyst ed esperto di Value Investing.
Sto analizzando l'azienda **{row['Company Name']} ({row['Ticker']})** con uno script Python (dati Yahoo Finance).

Vorrei che tu revisionassi i miei calcoli e mi fornissi un parere sulla valutazione attuale.

**1. I Miei Dati:**
* Prezzo: {row.get('Currency', 'USD')} {row.get('Price', 0):.2f}
* P/E Ratio (TTM): {pe}
* PEG Ratio: {peg} (Fonte: {row.get('PEG Source', 'N/A')})
* ROIC: {row.get('ROIC', 0)*100:.2f}%
* Free Cash Flow: {row.get('Currency', 'USD')} {fcf_str}
* Interest Coverage: {row.get('Interest Coverage', 0):.2f}x

**2. La Tua Missione:**
1. **Data Audit:** Confronta i miei numeri con i tuoi dati recenti. Ci sono discrepanze?
2. **Valuation Check:** Il titolo è Sottovalutato, Fair Value o Sopravalutato?
3. **The Moat:** L'azienda ha un vantaggio competitivo durevole? Rischi principali?

Rispondi in modo sintetico con elenchi puntati.
"""

def get_dataframe_styler(cfg: Dict[str, Any]):
    def highlight_rows(row):
        styles =[''] * len(row)
        cols = row.index.tolist()
        
        def set_color(col_name, condition, fallback_yellow=False):
            if col_name in cols:
                idx = cols.index(col_name)
                val = row.get(col_name)
                if pd.isna(val):
                    styles[idx] = 'background-color: #fff3cd; color: #856404' if fallback_yellow else ''
                else:
                    styles[idx] = 'background-color: #d4edda; color: green' if condition else 'background-color: #f8d7da; color: darkred'

        try:
            set_color('ROIC', row['ROIC'] >= cfg["roic"]/100)
            set_color('Free Cash Flow', row['Free Cash Flow'] >= cfg["fcf"])
            set_color('Interest Coverage', row['Interest Coverage'] >= cfg["int_cov"])
            set_color('PEG Ratio', row.get('PEG Ratio', 0) <= cfg["peg"], fallback_yellow=True)
            set_color('P/E Ratio', row.get('P/E Ratio', 0) <= cfg["pe"])
        except Exception:
            pass
        return styles
    return highlight_rows

def setup_sidebar() -> Dict[str, Any]:
    st.sidebar.header("1. Selezione Asset")
    input_mode = st.sidebar.radio("Modalità:",["Manuale", "Batch (CSV)"], horizontal=True)
    
    file, manual = None, None
    if input_mode == "Batch (CSV)":
        file = st.sidebar.file_uploader(f"Carica CSV (Max {MAX_CSV_ROWS} righe)", type=["csv"])
    else:
        manual = st.sidebar.text_input("Ticker", value="PST").upper().strip()

    st.sidebar.header("2. Mercato")
    market = st.sidebar.selectbox("Borsa:",["USA", "Italia (.MI)", "Francia (.PA)", "Germania (.DE)", "Londra (.L)", "Custom"], index=1)
    suffix = "" if market == "USA" else (".MI" if "Italia" in market else (".PA" if "Francia" in market else (".DE" if "Germania" in market else (".L" if "Londra" in market else ""))))
    if market == "Custom": suffix = st.sidebar.text_input("Suffisso", value="")
    
    st.sidebar.markdown("---")
    analyze_btn = st.sidebar.button("🚀 Avvia Analisi Completa", use_container_width=True)

    with st.sidebar.expander("⚙️ Parametri Fondamentali", expanded=False):
        cfg = {
            "roic": st.number_input("Min ROIC %", 10.0, step=0.5),
            "fcf": st.number_input("Min FCF (Mld $)", 0.0) * 1e9,
            "peg": st.number_input("Max PEG Ratio", 1.5, step=0.1),
            "pe": st.number_input("Max P/E (Fallback)", 25.0),
            "int_cov": st.number_input("Min Int. Coverage", 3.0),
            "perfect_only": st.checkbox("🏆 Solo 'All Green'")
        }
        
    return {"mode": input_mode, "file": file, "manual": manual, "suffix": suffix, "btn": analyze_btn, "cfg": cfg}

# ==========================================
# 7. ORCHESTRATORE PRINCIPALE (MAIN)
# ==========================================
def process_single_ticker(ticker: str, suffix: str) -> Optional[Dict[str, Any]]:
    try:
        clean_t = normalize_ticker(ticker, suffix)
        raw_data = get_fundamental_data(clean_t)
        if raw_data:
            metrics = calculate_fundamental_metrics(raw_data)
            if metrics:
                return metrics.to_ui_dict()
    except Exception as e:
        logger.error(f"Errore elaborazione thread per {ticker}: {str(e)}")
    return None

def main() -> None:
    st.title("💎 Value Investing & Timing Suite")
    st.markdown("Analisi Fondamentale (Cosa comprare) + Analisi Tecnica (Quando entrare)")

    if 'batch_results' not in st.session_state: st.session_state.batch_results = None
    if 'selected_ticker' not in st.session_state: st.session_state.selected_ticker = None

    ui_config = setup_sidebar()
    cfg = ui_config["cfg"]

    # Esecuzione Analisi Fondamentale
    if ui_config["btn"]:
        targets =[]
        if ui_config["mode"] == "Batch (CSV)" and ui_config["file"]:
            try:
                df_in = pd.read_csv(ui_config["file"], nrows=MAX_CSV_ROWS + 1)
                if "Ticker" in df_in.columns: 
                    targets = df_in["Ticker"].dropna().unique().tolist()
                    if len(targets) > MAX_CSV_ROWS:
                        st.warning(f"File troppo grande. Verranno analizzate solo le prime {MAX_CSV_ROWS} righe.")
                        targets = targets[:MAX_CSV_ROWS]
            except Exception as e:
                st.error("Errore lettura CSV")
                logger.error(f"Errore caricamento CSV: {str(e)}")
        elif ui_config["mode"] == "Manuale" and ui_config["manual"]:
            targets = [ui_config["manual"]]
            
        if targets:
            results =[]
            progress_bar = st.progress(0, text="Scaricamento e analisi dati in corso...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_ticker = {executor.submit(process_single_ticker, t, ui_config["suffix"]): t for t in targets}
                for i, future in enumerate(concurrent.futures.as_completed(future_to_ticker)):
                    res = future.result()
                    if res:
                        results.append(res)
                    progress_bar.progress((i + 1) / len(targets), text=f"Elaborati {i+1}/{len(targets)} ticker...")
            
            progress_bar.empty()

            if results:
                st.session_state.batch_results = pd.DataFrame(results)
                if ui_config["mode"] == "Manuale":
                    st.session_state.selected_ticker = results[0]["Ticker"]
            else:
                st.error("Nessun dato valido trovato per i ticker forniti.")

    # Rendering Interfaccia a Schede
    tab_fund, tab_tech = st.tabs(["📊 ANALISI FONDAMENTALE", "📉 TIMING TECNICO"])

    with tab_fund:
        # Mostra la Guida Fondamentale
        render_fundamental_guide()
        
        df_res = st.session_state.batch_results
        if df_res is not None:
            if cfg["perfect_only"]:
                mask = (df_res["ROIC"] >= cfg["roic"]/100) & (df_res["Free Cash Flow"] >= cfg["fcf"]) & (df_res["Interest Coverage"] >= cfg["int_cov"])
                df_display = df_res[mask].copy()
            else:
                df_display = df_res.copy()

            st.subheader(f"Screener Fondamentale ({len(df_display)} risultati)")
            
            styler_func = get_dataframe_styler(cfg)
            event = st.dataframe(
                df_display.drop(columns=["_raw_data"], errors='ignore').style.apply(styler_func, axis=1),
                column_config={
                    "Free Cash Flow": st.column_config.NumberColumn(format="$%.2f"),
                    "ROIC": st.column_config.NumberColumn(format="%.2f%%"),
                    "PEG Ratio": st.column_config.NumberColumn(format="%.2f"),
                    "P/E Ratio": st.column_config.NumberColumn(format="%.2f"),
                    "Interest Coverage": st.column_config.NumberColumn(format="%.2fx"),
                },
                on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True
            )

            if len(event.selection["rows"]) > 0:
                row = df_display.iloc[event.selection["rows"][0]]
                st.session_state.selected_ticker = row["Ticker"]
                
                st.divider()
                st.markdown(f"## {row['Company Name']} ({row['Ticker']})")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("ROIC", f"{row['ROIC']*100:.2f}%")
                fcf = row['Free Cash Flow']
                c2.metric("FCF", f"${fcf/1e9:.2f}B" if abs(fcf)>1e9 else f"${fcf/1e6:.2f}M")
                peg = row.get('PEG Ratio')
                c3.metric("PEG", f"{peg:.2f}" if pd.notnull(peg) else "N/A", f"Src: {row.get('PEG Source')}")
                c4.metric("Int. Cov.", f"{row['Interest Coverage']:.2f}x")
                
                with st.expander("🤖 Genera Prompt AI (Copia & Incolla)"):
                    st.code(_build_ai_prompt(row), language="markdown")

                st.markdown("### 📊 Trend Cash Flow Storico")
                fcf_chart = get_fcf_history(row["_raw_data"])
                if fcf_chart is not None: st.bar_chart(fcf_chart)

                with st.expander("📚 Analisi Avanzata (Bilanci Completi)"):
                    info = row["_raw_data"]["info"]
                    t1, t2, t3, t4 = st.tabs(["💰 Conto Ec.", "🏛️ Patrimoniale", "💸 Cash Flow", "🏢 Profilo"])
                    with t1: st.dataframe(row["_raw_data"]["financials"])
                    with t2: st.dataframe(row["_raw_data"]["balance_sheet"])
                    with t3: st.dataframe(row["_raw_data"]["cashflow"])
                    with t4:
                        c_a, c_b = st.columns(2)
                        c_a.write(f"**Settore:** {info.get('sector','-')}\n**Industria:** {info.get('industry','-')}")
                        c_b.write(f"**Beta:** {info.get('beta','-')}\n**Web:** {info.get('website','-')}")
                        st.write(info.get('longBusinessSummary','-'))
        else:
            st.info("Esegui l'analisi dalla Sidebar per vedere i risultati.")

    with tab_tech:
        ticker = st.session_state.selected_ticker
        if not ticker:
            st.info("👈 Seleziona prima un'azienda dal tab 'Analisi Fondamentale'.")
        else:
            st.markdown(f"## 📉 Analisi Tecnica: {ticker}")
            
            # Mostra la Guida Tecnica sotto al titolo
            render_technical_guide()

            with st.spinner("Calcolo indicatori tecnici in corso..."):
                df_tech = get_technical_data(ticker)
                
                if df_tech is not None:
                    df_calc = calculate_technical_indicators(df_tech)
                    price = df_calc['Close'].iloc[-1]
                    score, reasons = calculate_timing_score(df_calc, price)
                    
                    st.divider()
                    col_score, col_reasons = st.columns([1, 2])
                    with col_score:
                        color = "green" if score >= 80 else ("orange" if score >= 40 else "red")
                        safe_color = str(color)
                        safe_score = int(score)
                        
                        st.markdown(f"""
                        <div style="text-align: center; border: 2px solid {safe_color}; padding: 20px; border-radius: 10px;">
                            <h1 style="color: {safe_color}; margin:0;">{safe_score}/100</h1><p>TIMING SCORE</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    with col_reasons:
                        st.markdown("### 📝 Analisi Algoritmica")
                        for r in reasons: st.markdown(f"- {r}")
                        st.markdown(f"**RSI (14):** {df_calc['RSI'].iloc[-1]:.2f}")

                    # Disegno grafico interattivo
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                        vertical_spacing=0.1, subplot_titles=(f'{ticker} Price & SMA', 'RSI (14)'),
                                        row_width=[0.2, 0.7])
                    plot_data = df_calc.tail(TRADING_DAYS_YEAR)
                    
                    fig.add_trace(go.Candlestick(x=plot_data.index, open=plot_data['Open'], high=plot_data['High'],
                                                 low=plot_data['Low'], close=plot_data['Close'], name='Price'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data['SMA_50'], line=dict(color='orange', width=1), name='SMA 50'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data['SMA_200'], line=dict(color='blue', width=2), name='SMA 200'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB Lower'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=plot_data.index, y=plot_data['RSI'], line=dict(color='purple', width=2), name='RSI'), row=2, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
                    fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("Dati storici insufficienti per l'analisi tecnica.")

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; padding: 10px; color: gray;'>"
        "Ideato da <a href='https://alvioinsights.com' target='_blank' style='text-decoration: none; color: #4CAF50; font-weight: bold;'>Alvioinsights.com</a> "
        "sviluppato con Google Gemini AI"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()