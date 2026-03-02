import streamlit as st
import gspread
import pandas as pd
import requests
import time
import json
import re
import os
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Albion Economy Manager", page_icon="⚔️", layout="wide")

# Injection du CSS (Roboto pour les chiffres, Cinzel pour Albion)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .stButton > button:hover { background: linear-gradient(180deg, #e67e22, #d35400); transform: scale(1.05); box-shadow: 0 0 15px rgba(211, 84, 0, 0.6); }
    h1, h2, h3, .albion-font { font-family: 'Cinzel', serif !important; color: #ecf0f1 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px; border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px; }
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.2em; text-transform: uppercase; letter-spacing: 2px; }
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.5em; font-weight: bold; text-shadow: 0 0 20px rgba(255,255,255,0.1); }
    .summary-card { padding: 15px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .sc-green { background: rgba(46, 204, 113, 0.1); border-color: rgba(46, 204, 113, 0.3); }
    .sc-red { background: rgba(231, 76, 60, 0.1); border-color: rgba(231, 76, 60, 0.3); }
    .sc-val { font-family: 'Roboto', sans-serif !important; font-size: 1.4em; font-weight: bold; }
    .plot-card { background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.85em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.1em; font-weight: 700; margin-top: 5px; }
    .val-pos { color: #2ecc71; } .val-neg { color: #ff6b6b; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "APP_PASSWORD" in st.secrets:
    if st.sidebar.text_input("🔒 Mot de passe", type="password") != st.secrets["APP_PASSWORD"]:
        st.sidebar.warning("Veuillez saisir le mot de passe.")
        st.stop()

# --- CONFIGURATION ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"

# --- CONNEXION ---
try:
    if os.path.exists('service_account.json'):
        gc = gspread.service_account(filename='service_account.json')
    else:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    try: ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except: ws_ref = None
except Exception as e:
    st.error(f"Erreur Connexion: {e}"); st.stop()

# --- CHARGEMENT DATA ---
data = worksheet.get_all_records()
df_journal = pd.DataFrame(data) if data else pd.DataFrame(columns=['Date', 'Plot', 'Type', 'Montant', 'Note'])

# --- LOGIQUE MATHÉMATIQUE (SIGNES) ---
def calc_reel(row):
    try:
        t = str(row.get('Type', '')).lower()
        n = str(row.get('Note', '')).lower()
        m = float(str(row.get('Montant', 0)).replace(' ', '').replace(',', '.'))
        # Détection Dépenses, Bids et Ouvertures pour le négatif
        if "dépense" in t or "ouverture" in t or "bid" in n:
            return -abs(m)
        return abs(m)
    except: return 0.0

if not df_journal.empty:
    df_journal['Reel'] = df_journal.apply(calc_reel, axis=1)
    df_journal['Date_Obj'] = pd.to_datetime(df_journal['Date'], format='%d/%m/%Y', errors='coerce')
    df_journal['Date_Obj'] = df_journal['Date_Obj'].fillna(pd.to_datetime(df_journal['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

tous_les_plots = [p for p in df_journal['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_journal[(df_journal['Type'] == 'Clôture') | (df_journal['Note'].str.contains('Clôture', na=False))]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

def extraire_noms_et_tags(liste_brute):
    res = set()
    for i in liste_brute:
        txt = i.strip().lower()
        res.add(txt)
        m = re.search(r'^(.*?)\[(.*?)\]$', txt)
        if m: 
            if m.group(1): res.add(m.group(1).strip())
            if m.group(2): res.add(m.group(2).strip())
    return res

# --- API ALBION ---
def get_player_stats(pseudo):
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}", headers=h).json()
        candidats = [p for p in r.get('players', []) if p['Name'].lower() == pseudo.lower()]
        if not candidats: return {"Pseudo": pseudo, "Trouve": False}
        p_id = candidats[0]['Id']
        d = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}", headers=h).json()
        return {
            "Pseudo": d.get('Name'), "Guilde": d.get('GuildName') or "Aucune",
            "Alliance": d.get('AllianceName') or "-", "AllianceTag": d.get('AllianceTag') or "",
            "Craft Fame": d.get('LifetimeStatistics', {}).get('Crafting', {}).get('Total', 0), "Trouve": True
        }
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- INTERFACE ---
st.markdown("<h1>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Saisie & Parc", "⚖️ Trésorerie", "🔮 Scanner Arion"])

with tab1:
    c_s, c_g = st.columns([2, 1], gap="large")
    with c_s:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("add_tx", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1: t_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
            with col2: plot_target = st.selectbox("Plot", plots_actifs + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant", min_value=0, step=1000000)
            nt = st.text_input("Note")
            if st.form_submit_button("Valider"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_target, t_op, mnt, nt])
                st.cache_data.clear(); st.rerun()
    with c_g:
        st.markdown("<h3 class='albion-font'>Gestion Parc</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau Plot"):
            n_n = st.text_input("Nom"); n_c = st.number_input("Prix", min_value=0)
            if st.button("Ouvrir Plot"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), n_n, "Dépense (-)", n_c, "Ouverture"])
                st.cache_data.clear(); st.rerun()
        with st.expander("🔴 Clôturer Plot"):
            p_clot = st.selectbox("Cible", plots_actifs)
            p_rev = st.number_input("Revente", min_value=0)
            if st.button("Confirmer Clôture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_clot, "Recette (+)", p_rev, "Clôture"])
                st.cache_data.clear(); st.rerun()

with tab2:
    st.markdown("<h3 class='albion-font'>Bilan Trésorerie</h3>", unsafe_allow_html=True)
    if not df_journal.empty:
        c_d1, c_d2 = st.columns(2)
        d_start = c_d1.date_input("Début", df_journal['Date_Obj'].min().date())
        d_end = c_d2.date_input("Fin", datetime.now().date())
        df_f = df_journal[(df_journal['Date_Obj'].dt.date >= d_start) & (df_journal['Date_Obj'].dt.date <= d_end)]
        
        net = df_f['Reel'].sum()
        st.markdown(f'<div class="albion-metric-box"><div class="metric-label">SOLDE NET</div><div class="metric-value {"val-pos" if net >= 0 else "val-neg"}">{format_monetaire(net)} Silver</div></div>', unsafe_allow_html=True)
        
        st.markdown("<h4 class='albion-font'>🟢 Plots Actifs</h4>", unsafe_allow_html=True)
        stats = df_f.groupby('Plot')['Reel'].sum()
        cols = st.columns(4)
        for idx, p in enumerate(plots_actifs + ["Taxe Guilde", "Autre"]):
            val = stats.get(p, 0)
            with cols[idx % 4]:
                st.markdown(f'<div class="plot-card"><div class="plot-title">{p}</div><div class="plot-value {"val-pos" if val >= 0 else "val-neg"}">{format_monetaire(val)}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("<h4 class='albion-font'>Historique</h4>", unsafe_allow_html=True)
        st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)

with tab3:
    st.markdown("<h3 class='albion-font'>Scanner de Guildes</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("Permissions JSON/Texte", height=200)
    if st.button("Lancer l'Analyse"):
        raw_p = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        mem_g = extraire_noms_et_tags(re.findall(r'"Guild:([^"]+)"', raw_tx))
        mem_a = extraire_noms_et_tags(re.findall(r'"Alliance:([^"]+)"', raw_tx))
        
        res = []
        bar = st.progress(0)
        for i, p in enumerate(raw_p):
            inf = get_player_stats(p)
            status = "✅ Unique"
            if inf['Trouve']:
                if inf['Guilde'].lower() in mem_g: status = "⚠️ Doublon (Guilde)"
                elif inf['AllianceTag'].lower() in mem_a: status = "⚠️ Doublon (Alliance)"
            inf['Analyse'] = status
            res.append(inf)
            bar.progress((i+1)/len(raw_p))
        st.session_state['data_display'] = pd.DataFrame(res)
    
    if st.session_state.get('data_display') is not None:
        st.dataframe(st.session_state['data_display'], use_container_width=True)