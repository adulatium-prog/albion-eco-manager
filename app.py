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

# --- SYSTÈME DE SÉCURITÉ (VIA SECRETS) ---
st.sidebar.markdown("## 🔒 Zone Sécurisée")
if "APP_PASSWORD" not in st.secrets:
    st.error("❌ CONFIGURATION MANQUANTE : Ajoutez 'APP_PASSWORD' dans les Secrets de Streamlit.")
    st.stop()

mdp_saisi = st.sidebar.text_input("Mot de passe :", type="password")
if mdp_saisi != st.secrets["APP_PASSWORD"]:
    st.warning("⚠️ Veuillez entrer le mot de passe pour accéder au Dashboard.")
    st.stop()

# --- STYLES CSS (ROBOTO POUR LES CHIFFRES) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    h1, h2, h3, h4, .albion-font { font-family: 'Cinzel', serif !important; color: #ecf0f1 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px; border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px; }
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.2em; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 2px; }
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.5em; font-weight: bold; text-shadow: 0 0 20px rgba(255,255,255,0.1); }
    .summary-card { padding: 15px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .sc-green { background: rgba(46, 204, 113, 0.1); border-color: rgba(46, 204, 113, 0.3); }
    .sc-red { background: rgba(231, 76, 60, 0.1); border-color: rgba(231, 76, 60, 0.3); }
    .sc-title { font-family: 'Cinzel', serif; font-size: 0.9em; opacity: 0.8; margin-bottom: 5px; }
    .sc-val { font-family: 'Roboto', sans-serif !important; font-size: 1.4em; font-weight: bold; }
    .txt-green { color: #2ecc71; }
    .txt-red { color: #ff6b6b; }
    .val-pos { color: #2ecc71; text-shadow: 0 0 15px rgba(46, 204, 113, 0.4); } 
    .val-neg { color: #ff6b6b; text-shadow: 0 0 15px rgba(255, 107, 107, 0.5); } 
    .plot-card { background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.2em; font-weight: 700; margin-top: 5px; }
    .archived-plot { opacity: 0.6; filter: grayscale(50%); border-color: rgba(255,255,255,0.05); }
    .archived-plot:hover { opacity: 1; filter: grayscale(0%); }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION FICHIERS ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"

def format_monetaire(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

# --- CONNEXION & CACHE ---
@st.cache_data(ttl=60)
def get_data():
    try:
        if os.path.exists('service_account.json'):
            gc = gspread.service_account(filename='service_account.json')
        else:
            gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
        sh = gc.open(NOM_DU_FICHIER_SHEET)
        ws = sh.worksheet(NOM_ONGLET_JOURNAL)
        data = ws.get_all_records()
        return pd.DataFrame(data), ws
    except Exception as e:
        st.error(f"Erreur de connexion : {e}")
        st.stop()

df_journal, worksheet = get_data()

# --- TRAITEMENT DES DONNÉES ---
def clean_money(val):
    try: return float(str(val).replace(' ', '').replace(',', '.'))
    except: return 0.0

df_journal['Reel'] = df_journal['Montant'].apply(clean_money)
# On crée la colonne Date_Obj pour le tri et les filtres
df_journal['Date_Obj'] = pd.to_datetime(df_journal['Date'], format='%d/%m/%Y', errors='coerce')

# --- ANALYSE DES PLOTS ---
tous_les_plots = [p for p in df_journal['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_journal[(df_journal['Type'] == 'Clôture') | (df_journal['Note'] == 'Clôture')]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

# --- INTERFACE TABS ---
st.markdown("<h1>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Opérations & Parc", "⚖️ Trésorerie & Bilan", "🔮 Scanner Arion"])

with tab1:
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction 💰</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            nom_p = st.selectbox("📍 Cible :", plots_actifs + ["Taxe Guilde", "Autre"])
            type_op = st.radio("Nature :", ["Recette (+)", "Dépense (-)"], horizontal=True)
            mnt = st.number_input("Montant (Silver)", min_value=0, step=1000000)
            note = st.text_input("Note")
            if st.button("Valider", use_container_width=True):
                val_f = mnt if "Recette" in type_op else -mnt
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nom_p, type_op, val_f, note])
                st.success("✅ Enregistré !")
                get_data.clear()
                time.sleep(1)
                st.rerun()

    with c2:
        st.markdown("<h3 class='albion-font'>Gestion du Parc 🏗️</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau plot"):
            n_n = st.text_input("Nom du plot")
            n_c = st.number_input("Coût achat", min_value=0)
            if st.button("Ouvrir"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), n_n, "Dépense (-)", -n_c, "Ouverture"])
                get_data.clear(); st.rerun()
        with st.expander("🔴 Vendre / Clôturer"):
            p_v = st.selectbox("Plot à vendre", plots_actifs)
            p_r = st.number_input("Prix revente", min_value=0)
            if st.button("Confirmer vente"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_v, "Recette (+)", p_r, "Clôture"])
                get_data.clear(); st.rerun()

with tab2:
    st.markdown("<h3 class='albion-font'>Bilan Financier Global</h3>", unsafe_allow_html=True)
    
    # Filtres
    c_d1, c_d2 = st.columns(2)
    d_start = c_d1.date_input("Début", df_journal['Date_Obj'].min().date())
    d_end = c_d2.date_input("Fin", datetime.now().date())
    
    mask = (df_journal['Date_Obj'].dt.date >= d_start) & (df_journal['Date_Obj'].dt.date <= d_end)
    df_f = df_journal.loc[mask]

    net_total = df_f['Reel'].sum()
    st.markdown(f"""
    <div class="albion-metric-box">
        <div class="metric-label">TRÉSORERIE NETTE</div>
        <div class="metric-value {'val-pos' if net_total >= 0 else 'val-neg'}">
            {format_monetaire(net_total)} Silver
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Détail par plot
    st.markdown("<h4 class='albion-font'>📊 Performance par Plot</h4>", unsafe_allow_html=True)
    stats = df_f.groupby('Plot')['Reel'].sum()
    cols = st.columns(4)
    for i, p_name in enumerate(tous_les_plots + ["Taxe Guilde", "Autre"]):
        val = stats.get(p_name, 0)
        if val != 0 or p_name in plots_actifs:
            with cols[i % 4]:
                st.markdown(f"""
                <div class="plot-card">
                    <div class="plot-title">{p_name}</div>
                    <div class="plot-value {'val-pos' if val >= 0 else 'val-neg'}">{format_monetaire(val)}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()
    st.markdown("<h4 class='albion-font'>📑 Historique</h4>", unsafe_allow_html=True)
    st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note']].sort_values(by=df_f.index, ascending=False), use_container_width=True)

with tab3:
    st.markdown("<h3 class='albion-font'>🔮 Scanner Arion</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("JSON / Texte brut", height=200)
    if st.button("Lancer Scan", type="primary"):
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        if not players:
            st.warning("Aucun pseudo trouvé.")
        else:
            res = []
            bar = st.progress(0)
            for i, p in enumerate(players):
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={p}", headers=headers).json()
                    p_dat = [x for x in r.get('players', []) if x['Name'].lower() == p.lower()][0]
                    res.append({"Pseudo": p_dat['Name'], "Guilde": p_dat['GuildName'], "Alliance": p_dat['AllianceTag'], "Fame Craft": p_dat.get('CraftingFame', 0)})
                except: res.append({"Pseudo": p, "Guilde": "Inconnu", "Alliance": "-", "Fame Craft": 0})
                bar.progress((i+1)/len(players))
            st.dataframe(pd.DataFrame(res), use_container_width=True)