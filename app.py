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

# --- STYLE CSS INTEGRAL (DESIGN PREMIUM + FIX ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

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
        transform: scale(1.05);
        box-shadow: 0 0 15px rgba(211, 84, 0, 0.6);
    }

    h1, h2, h3, h4, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        font-weight: 700;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold;
    }

    .albion-metric-box {
        background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px;
        border: 1px solid rgba(236, 240, 241, 0.3); text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px;
    }
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.2em; text-transform: uppercase; letter-spacing: 2px; }
    
    /* FIX ROBOTO POUR LES CHIFFRES */
    .metric-value { 
        font-family: 'Roboto', sans-serif !important; 
        font-size: 3.5em; font-weight: bold; color: #ffffff;
        text-shadow: 0 0 20px rgba(255,255,255,0.1); 
    }

    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px;
        text-align: center; margin-bottom: 10px;
    }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.2em; font-weight: 700; margin-top: 5px; }

    .val-pos { color: #2ecc71 !important; } 
    .val-neg { color: #ff6b6b !important; }

    .summary-card { padding: 15px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .sc-green { background: rgba(46, 204, 113, 0.1); border-color: rgba(46, 204, 113, 0.3); }
    .sc-red { background: rgba(231, 76, 60, 0.1); border-color: rgba(231, 76, 60, 0.3); }
    .sc-val { font-family: 'Roboto', sans-serif !important; font-size: 1.4em; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- SECURITE ---
if "APP_PASSWORD" in st.secrets:
    if st.sidebar.text_input("🔒 Accès", type="password") != st.secrets["APP_PASSWORD"]:
        st.sidebar.warning("Veuillez saisir le mot de passe.")
        st.stop()

# --- CONFIGURATION FICHIERS ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"
SEUIL_FAME_MIN = 4000000

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

def extraire_noms_et_tags(liste_brute):
    resultat = set()
    for item in liste_brute:
        txt = item.strip().lower()
        resultat.add(txt)
        match = re.search(r'^(.*?)\[(.*?)\]$', txt)
        if match:
            nom_seul = match.group(1).strip()
            tag_seul = match.group(2).strip()
            if nom_seul: resultat.add(nom_seul)
            if tag_seul: resultat.add(tag_seul)
    return resultat

# --- API ALBION ---
def get_player_stats(pseudo):
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url_search, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            candidats = [p for p in players if p['Name'].lower() == pseudo.lower()]
            if not candidats: return {"Pseudo": pseudo, "Trouve": False}
            
            p_id = candidats[0]['Id']
            url_details = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}"
            r_det = requests.get(url_details, headers=headers, timeout=5)
            if r_det.status_code == 200:
                d = r_det.json()
                ls = d.get('LifetimeStatistics', {}).get('Crafting', {})
                return {
                    "Pseudo": d.get('Name'), "Guilde": d.get('GuildName') or "Aucune",
                    "Alliance": d.get('AllianceName') or "-", "AllianceTag": d.get('AllianceTag') or "",
                    "Craft Fame": ls.get('Total', 0), "Trouve": True
                }
        return {"Pseudo": pseudo, "Trouve": False}
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- CONNEXION GOOGLE SHEETS ---
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
    st.error(f"Erreur Connexion : {e}"); st.stop()

# --- ANALYSE DES PLOTS ---
data_journal = worksheet.get_all_records()
df_journal = pd.DataFrame(data_journal) if data_journal else pd.DataFrame(columns=['Date', 'Plot', 'Type', 'Montant', 'Note'])

def calc_reel(row):
    try:
        t = str(row.get('Type', '')).lower()
        n = str(row.get('Note', '')).lower()
        m = float(str(row.get('Montant', 0)).replace(' ', '').replace(',', '.'))
        if any(w in t or w in n for w in ["dépense", "ouverture", "bid"]):
            return -abs(m)
        return abs(m)
    except: return 0.0

if not df_journal.empty:
    df_journal['Reel'] = df_journal.apply(calc_reel, axis=1)
    df_journal['Date_Obj'] = pd.to_datetime(df_journal['Date'], format='%d/%m/%Y', errors='coerce')
    df_journal['Date_Obj'] = df_journal['Date_Obj'].fillna(pd.to_datetime(df_journal['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

tous_les_plots = [p for p in df_journal['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_journal[(df_journal['Note'].str.contains('Clôture', case=False, na=False))]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

# --- INTERFACE ---
st.markdown("<h1>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Page 1 : Opérations", "⚖️ Page 2 : Trésorerie", "🔮 Page 3 : Scanner"])

# --- PAGE 1 ---
with tab1:
    c_s, c_g = st.columns([2, 1], gap="large")
    with c_s:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("ajout_tx", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1: t_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
            with col2: plot_target = st.selectbox("Plot", plots_actifs + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant (Silver)", min_value=0, step=1000000)
            nt = st.text_input("Note (Raison)")
            if st.form_submit_button("Valider"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_target, t_op, mnt, nt])
                st.cache_data.clear(); st.rerun()
    with c_g:
        st.markdown("<h3 class='albion-font'>Gestion Parc</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau Plot"):
            nn = st.text_input("Nom"); nc = st.number_input("Coût", min_value=0)
            if st.button("Ouvrir"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", nc, "Ouverture"])
                st.cache_data.clear(); st.rerun()
        with st.expander("🔴 Vendre"):
            pv = st.selectbox("Plot", plots_actifs)
            pr = st.number_input("Revente", min_value=0)
            if st.button("Vendre"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), pv, "Recette (+)", pr, "Clôture"])
                st.cache_data.clear(); st.rerun()

# --- PAGE 2 ---
with tab2:
    if not df_journal.empty:
        c1, c2 = st.columns(2)
        d_start = c1.date_input("Début Cycle", df_journal['Date_Obj'].min().date())
        d_end = c2.date_input("Fin Cycle", datetime.now().date())
        df_f = df_journal[(df_journal['Date_Obj'].dt.date >= d_start) & (df_journal['Date_Obj'].dt.date <= d_end)]
        
        net = df_f['Reel'].sum()
        st.markdown(f'<div class="albion-metric-box"><div class="metric-label">TRÉSORERIE NETTE</div><div class="metric-value {"val-pos" if net >= 0 else "val-neg"}">{format_monetaire(net)} Silver</div></div>', unsafe_allow_html=True)
        
        stats = df_f.groupby('Plot')['Reel'].sum()
        cols = st.columns(4)
        for idx, p in enumerate(tous_les_plots + ["Taxe Guilde", "Autre"]):
            val = stats.get(p, 0)
            if val != 0 or p in plots_actifs:
                with cols[idx % 4]:
                    st.markdown(f'<div class="plot-card"><div class="plot-title">{p}</div><div class="plot-value {"val-pos" if val >= 0 else "val-neg"}">{format_monetaire(val)}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)

# --- PAGE 3 (INTELLIGENCE COMPLETE) ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Arion v2</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("Permissions JSON", height=200)
    if st.button("Lancer l'Audit"):
        raw_p = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        mem_g = extraire_noms_et_tags(re.findall(r'"Guild:([^"]+)"', raw_tx))
        mem_a = extraire_noms_et_tags(re.findall(r'"Alliance:([^"]+)"', raw_tx))
        
        if raw_p:
            res = []
            bar = st.progress(0)
            for i, p in enumerate(raw_p):
                inf = get_player_stats(p)
                status = "✅ Unique"
                if inf['Trouve']:
                    if inf['Guilde'].lower() in mem_g: status = "⚠️ Doublon Guilde"
                    elif inf['AllianceTag'].lower() in mem_a: status = "⚠️ Doublon Alliance"
                inf['Analyse'] = status
                res.append(inf)
                bar.progress((i+1)/len(raw_p))
                time.sleep(0.05)
            
            df_res = pd.DataFrame(res)
            # Tri par Fame Décroissant
            df_res = df_res.sort_values(by="Craft Fame", ascending=False)
            st.session_state['scan_res'] = df_res

    if 'scan_res' in st.session_state:
        st.dataframe(st.session_state['scan_res'], use_container_width=True)
