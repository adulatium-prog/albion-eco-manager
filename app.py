import os
import streamlit as st
import gspread
import pandas as pd
import requests
import time
import re
import json
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Albion Economy Manager", page_icon="⚔️", layout="wide")

# --- STYLE CSS AVANCÉ (CINZEL & ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

    /* Boutons Albion Style */
    .stButton > button {
        background: linear-gradient(180deg, #d35400, #a04000);
        color: white;
        border: 1px solid #e67e22;
        border-radius: 20px;
        font-family: 'Cinzel', serif;
        font-weight: bold;
        text-transform: uppercase;
        padding: 10px 24px;
        transition: all 0.2s;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stButton > button:hover {
        background: linear-gradient(180deg, #e67e22, #d35400);
        transform: scale(1.02);
        box-shadow: 0 0 15px rgba(211, 84, 0, 0.6);
    }

    h1, h2, h3, h4, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        font-weight: 700;
    }

    /* Onglets Custom */
    .stTabs [data-baseweb="tab-list"] {
        gap: 15px;
        background-color: rgba(0, 0, 0, 0.3);
        padding: 12px;
        border-radius: 25px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        color: #bdc3c7;
        font-family: 'Cinzel', serif;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 255, 255, 0.1);
        color: #ffffff;
        border-radius: 15px;
        font-weight: bold;
    }

    /* Boîtes de statistiques */
    .albion-metric-box {
        background: rgba(0, 0, 0, 0.4);
        padding: 25px;
        border-radius: 20px;
        border: 1px solid rgba(243, 156, 18, 0.3);
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    }
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.1em; text-transform: uppercase; letter-spacing: 2px; }
    
    /* Roboto pour les chiffres : lisibilité parfaite du 1 */
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.2em; font-weight: 700; margin-top: 10px; }
    .roboto-val { font-family: 'Roboto', sans-serif !important; }

    /* Cartes Plots */
    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        margin-bottom: 15px;
        transition: all 0.3s;
    }
    .plot-card:hover { border-color: #f39c12; transform: translateY(-5px); }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.3em; font-weight: 700; margin-top: 8px; }

    .val-pos { color: #2ecc71; text-shadow: 0 0 10px rgba(46, 204, 113, 0.2); } 
    .val-neg { color: #ff6b6b; text-shadow: 0 0 10px rgba(255, 107, 107, 0.2); }
    
    .summary-card { padding: 15px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .sc-green { background: rgba(46, 204, 113, 0.1); border-color: rgba(46, 204, 113, 0.3); }
    .sc-red { background: rgba(231, 76, 60, 0.1); border-color: rgba(231, 76, 60, 0.3); }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ (VIA SECRETS) ---
if "APP_PASSWORD" in st.secrets:
    if st.sidebar.text_input("🔒 Accès Sécurisé", type="password") != st.secrets["APP_PASSWORD"]:
        st.sidebar.warning("Identifiez-vous pour accéder à l'économie d'Arion.")
        st.stop()

# --- CONNEXION GOOGLE SHEETS ---
@st.cache_data(ttl=60)
def get_google_data():
    try:
        if "gcp_service_account" in st.secrets:
            gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"]))
        else:
            gc = gspread.service_account(filename='service_account.json')
        sh = gc.open("Arion Plot")
        ws = sh.worksheet("Journal_App")
        try: wr = sh.worksheet("Reference_Craft")
        except: wr = None
        return pd.DataFrame(ws.get_all_records()), ws, wr
    except Exception as e:
        st.error(f"Erreur de liaison GSheets : {e}"); st.stop()

df_raw, worksheet, ws_ref = get_google_data()

# --- LOGIQUE MATHÉMATIQUE DES SIGNES ---
def clean_money(val):
    try: return float(str(val).replace(' ', '').replace(',', '.'))
    except: return 0.0

def process_balance(df):
    if df.empty: return df
    # Respect strict du Journal_App
    df['Reel'] = df.apply(lambda x: -abs(clean_money(x['Montant'])) if "Dépense" in str(x['Type']) or "Ouverture" in str(x['Note']) or "Bid" in str(x['Note']) else abs(clean_money(x['Montant'])), axis=1)
    df['Date_Obj'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
    df['Date_Obj'] = df['Date_Obj'].fillna(pd.to_datetime(df['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))
    return df

df_proc = process_balance(df_raw.copy())

# Analyse des plots (Actifs vs Passés)
tous_les_plots = [p for p in df_proc['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_proc[df_proc['Note'].str.contains('Clôture', case=False, na=False)]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

# --- FONCTIONS UTILES ---
def format_num(n): return "{:,.0f}".format(n).replace(",", " ")

# --- INTERFACE ---
st.markdown("<h1 class='albion-font'>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📜 Page 1 : Opérations", "⚖️ Page 2 : Trésorerie", "🔮 Page 3 : Scanner"])

# --- PAGE 1 : DÉPENSES / RECETTES & PARC ---
with tab1:
    col_input, col_parc = st.columns([2, 1], gap="large")
    
    with col_input:
        st.markdown("<h3 class='albion-font'>Nouvelle Opération</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            with st.form("tx_form", clear_on_submit=True):
                c_a, c_b = st.columns(2)
                with c_a: type_op = st.radio("Nature", ["Recette (+)", "Dépense (-)"], horizontal=True)
                with c_b: plot_sel = st.selectbox("Plot Cible", plots_actifs + ["Taxe Guilde", "Autre"])
                mnt = st.number_input("Montant (Silver)", min_value=0, step=1000000)
                reason = st.text_input("Raison (Ex: Taxe, Achat, Bid...)")
                
                if st.form_submit_button("Enregistrer dans le Journal"):
                    # Ajout strict selon colonnes image
                    worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_sel, type_op, mnt, reason])
                    st.success("✅ Données transmises au Sheet.")
                    st.cache_data.clear(); time.sleep(1); st.rerun()

    with col_parc:
        st.markdown("<h3 class='albion-font'>Gestion du Parc 🏗️</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau Plot"):
            nn = st.text_input("Nom du Plot (ex: Butcher 1)")
            nc = st.number_input("Coût d'ouverture", min_value=0, step=1000000)
            if st.button("Ouvrir ce Plot", use_container_width=True):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", nc, "Ouverture"])
                st.cache_data.clear(); st.rerun()
                
        with st.expander("🔴 Vendre Plot"):
            pv = st.selectbox("Plot à clôturer", plots_actifs)
            pr = st.number_input("Prix de revente", min_value=0, step=1000000)
            if st.button("Vendre et Archiver", use_container_width=True):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), pv, "Recette (+)", pr, "Clôture"])
                st.cache_data.clear(); st.rerun()

# --- PAGE 2 : RÉCAP SILVER & BILAN PLOTS ---
with tab2:
    st.markdown("<h3 class='albion-font'>Analyse Décisionnelle</h3>", unsafe_allow_html=True)
    
    # Sélecteur de Cycle
    c1, c2 = st.columns(2)
    d_start = c1.date_input("Cycle début", df_proc['Date_Obj'].min().date())
    d_end = c2.date_input("Cycle fin", datetime.now().date())
    df_f = df_proc[(df_proc['Date_Obj'].dt.date >= d_start) & (df_proc['Date_Obj'].dt.date <= d_end)]

    # TOTAL HAUT (Bénéfice/Perte)
    net_val = df_f['Reel'].sum()
    st.markdown(f"""
    <div class="albion-metric-box">
        <div class="metric-label">SOLDE NET DU CYCLE</div>
        <div class="metric-value roboto-val {'val-pos' if net_val >= 0 else 'val-neg'}">
            {format_num(net_val)} Silver
        </div>
    </div>
    """, unsafe_allow_html=True)

    # RÉCAP PAR TYPE DE PLOT
    st.markdown("<h4 class='albion-font'>📊 Performance par Type</h4>", unsafe_allow_html=True)
    # Regroupement intelligent (Weaver, Hunter, Mage...)
    stats_type = df_f.groupby('Plot')['Reel'].sum().reset_index()
    
    cols = st.columns(4)
    for i, row in stats_type.iterrows():
        if row['Plot'] == "": continue
        with cols[i % 4]:
            st.markdown(f"""
            <div class="plot-card">
                <div class="plot-title">{row['Plot']}</div>
                <div class="plot-value roboto-val {'val-pos' if row['Reel'] >= 0 else 'val-neg'}">
                    {format_num(row['Reel'])}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    # HISTORIQUE ACTUEL / PASSÉ
    st.markdown("<h4 class='albion-font'>📑 Historique du Journal</h4>", unsafe_allow_html=True)
    st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)

# --- PAGE 3 : SCANNER ARION ---
with tab3:
    st.markdown("<h3 class='albion-font'>🔮 Scanner de Permissions</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("Collez le JSON ou le texte brut ici", height=200)
    
    if st.button("Lancer l'Audit API", type="primary"):
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        guilds_ref = set(re.findall(r'"Guild:([^"]+)"', raw_tx))
        alli_ref = set(re.findall(r'"Alliance:([^"]+)"', raw_tx))
        
        if not players: st.warning("Aucun pseudo détecté.")
        else:
            res = []
            bar = st.progress(0)
            for i, p in enumerate(players):
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={p}", headers=headers).json()
                    p_dat = [x for x in r.get('players', []) if x['Name'].lower() == p.lower()][0]
                    
                    status = "✅ Unique"
                    if p_dat.get('GuildName') in guilds_ref: status = "⚠️ Doublon Guilde"
                    elif p_dat.get('AllianceTag') in alli_ref: status = "⚠️ Doublon Alliance"
                    
                    res.append({
                        "Pseudo": p_dat['Name'],
                        "Guilde": p_dat.get('GuildName', '-'),
                        "Alliance": p_dat.get('AllianceTag', '-'),
                        "Fame Total": p_dat.get('CraftingFame', 0),
                        "Analyse": status
                    })
                except: res.append({"Pseudo": p, "Guilde": "Inconnu", "Alliance": "-", "Fame Total": 0, "Analyse": "API Error"})
                bar.progress((i+1)/len(players))
            
            df_scan = pd.DataFrame(res)
            # Tri par Fame décroissant par défaut
            df_scan = df_scan.sort_values(by="Fame Total", ascending=False)
            st.session_state['scan_res'] = df_scan

    if 'scan_res' in st.session_state:
        st.markdown("<h4 class='albion-font'>Audit de Permission</h4>", unsafe_allow_html=True)
        st.dataframe(st.session_state['scan_res'], use_container_width=True)
