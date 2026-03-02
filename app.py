import streamlit as st
import gspread
import pandas as pd
import requests
import time
import json
import re
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Albion Economy Manager", page_icon="⚔️", layout="wide")

# Injection du CSS (Ton design d'origine)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    h1, h2, h3, .albion-font { font-family: 'Cinzel', serif !important; color: #ecf0f1 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px; border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; margin-bottom: 20px; }
    .metric-value { font-family: 'Cinzel', serif; font-size: 3.5em; font-weight: bold; }
    .plot-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.85em; text-transform: uppercase; font-weight: bold; }
    .val-pos { color: #2ecc71; } .val-neg { color: #ff6b6b; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔒 Mot de passe", type="password") != st.secrets["app_password"]:
        st.sidebar.warning("Saisis le mot de passe pour accéder.")
        st.stop()

# --- CONFIGURATION ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"
SEUIL_FAME_MIN = 4000000 

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

def get_player_stats(pseudo):
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url_search, headers=headers).json()
        players = resp.get('players', [])
        candidats = [p for p in players if p['Name'].lower() == pseudo.lower()]
        if not candidats: return {"Pseudo": pseudo, "Trouve": False}
        p_id = candidats[0]['Id']
        d = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}", headers=headers).json()
        ls = d.get('LifetimeStatistics', {}).get('Crafting', {})
        return {"Pseudo": d['Name'], "Guilde": d.get('GuildName') or "Aucune", "Alliance": d.get('AllianceName') or "-", "AllianceTag": d.get('AllianceTag') or "", "Craft Fame": ls.get('Total', 0), "Trouve": True}
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- CONNEXION ---
try:
    if "gcp_service_account" in st.secrets:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    else:
        gc = gspread.service_account(filename='service_account.json')
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    ws_ref = sh.worksheet(NOM_ONGLET_REF)
except Exception as e: st.error(f"Erreur connexion : {e}"); st.stop()

# --- INTERFACE ---
st.markdown("<h1>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📜 Journal", "⚖️ Trésorerie", "🔮 Scanner"])

# --- TAB 1 : SAISIE (Stockage Valeur Absolue) ---
with tab1:
    st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
    with st.form("ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        type_op = c1.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
        batiment = c2.selectbox("Plot", ["Cook", "Hunter", "Weaver", "Mage", "Taxe Guilde", "Autre"])
        montant = st.number_input("Montant (Silver)", step=1000000, format="%d")
        note = st.text_input("Description (ex: Ouverture)")
        if st.form_submit_button("Valider"):
            worksheet.append_row([datetime.now().strftime("%d/%m"), batiment, type_op, abs(montant), note])
            st.cache_data.clear(); st.rerun()

# --- TAB 2 : TRÉSORERIE (Logique de Signe Interne) ---
with tab2:
    data = worksheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        
        # LOGIQUE RATIONNELLE : On traite les signes ICI, pas dans le Sheet
        def calculer_reel(row):
            m = float(str(row['Montant']).replace(' ', '').replace(',', '.'))
            t = str(row['Type']).lower()
            n = str(row['Note']).lower()
            # Si c'est une dépense, une ouverture ou un bid -> Négatif pour le calcul
            if "dépense" in t or "ouverture" in n or "bid" in n:
                return -abs(m)
            return abs(m)

        df['Reel'] = df.apply(calculer_reel, axis=1)
        total = df['Reel'].sum()
        
        # Affichage
        css = "val-pos" if total >= 0 else "val-neg"
        st.markdown(f'<div class="albion-metric-box"><div class="metric-label">SOLDE NET</div><div class="metric-value {css}">{format_monetaire(total)}</div></div>', unsafe_allow_html=True)
        
        # Récap par Plot
        stats = df.groupby('Plot')['Reel'].sum()
        cols = st.columns(5)
        targets = ["Cook", "Hunter", "Weaver", "Mage", "Taxe Guilde"]
        for i, t in enumerate(targets):
            val = stats.get(t, 0)
            color = "val-pos" if val >= 0 else "val-neg"
            cols[i].markdown(f'<div class="plot-card"><div class="plot-title">{t}</div><div class="plot-value {color}">{format_monetaire(val)}</div></div>', unsafe_allow_html=True)

# --- TAB 3 : SCANNER (Tri & Doublons) ---
with tab3:
    raw_text = st.text_area("Permissions JSON", height=150)
    if st.button("Lancer l'Analyse"):
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))
        res = []
        for p in players:
            inf = get_player_stats(p)
            inf['Analyse'] = "✅ Unique"
            if inf['Trouve'] and (inf['Guilde'].lower() in raw_text.lower() or inf['AllianceTag'].lower() in raw_text.lower()):
                inf['Analyse'] = "⚠️ Doublon"
            res.append(inf)
        df_res = pd.DataFrame(res).sort_values(by="Craft Fame", ascending=False)
        st.dataframe(df_res, use_container_width=True)
