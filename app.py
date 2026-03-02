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

# --- STYLE CSS D'ORIGINE (RESTAURÉ ET COMPLET) ---
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
        color: white; border: 1px solid #e67e22; border-radius: 20px;
        font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase;
        padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stButton > button:hover { transform: scale(1.05); box-shadow: 0 0 15px rgba(211, 84, 0, 0.6); }

    h1, h2, h3, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px;
    }
    .stTabs [data-baseweb="tab"] { color: #bdc3c7; font-family: 'Cinzel', serif; border: none; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; }

    .albion-metric-box {
        background: rgba(0, 0, 0, 0.3); padding: 25px; border-radius: 20px;
        border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; margin-bottom: 20px;
    }
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.5em; font-weight: bold; }

    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px;
        text-align: center; margin-bottom: 10px; transition: transform 0.2s;
    }
    .plot-card:hover { border-color: #f39c12; transform: translateY(-5px); }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.2em; font-weight: 700; }

    .val-pos { color: #2ecc71; } .val-neg { color: #ff6b6b; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ (RESTAURÉE) ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔒 Accès", type="password") != st.secrets["app_password"]:
        st.sidebar.info("Veuillez saisir le code d'accès Arion.")
        st.stop()

# --- CONNEXION & LECTURE EXHAUSTIVE ---
try:
    if "gcp_service_account" in st.secrets:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    else:
        gc = gspread.service_account(filename='service_account.json')
    
    sh = gc.open("Arion Plot")
    worksheet = sh.worksheet("Journal_App")
    ws_ref = sh.worksheet("Reference_Craft")

    # Lecture sans sauts de lignes (on récupère tout jusqu'à la dernière ligne remplie)
    data_raw = worksheet.get_all_records()
    df = pd.DataFrame(data_raw)
except Exception as e:
    st.error(f"Erreur Connexion : {e}"); st.stop()

# --- MOTEUR DE CALCUL RATIONNEL ---
if not df.empty:
    # 1. Nettoyage des prix (Espaces, virgules)
    df['M_Num'] = df['Montant'].astype(str).str.replace(r'[\s\u00A0,]', '', regex=True).replace('', '0').astype(float)
    
    # 2. Logique de Signe (Sheet Positif / Streamlit Signé)
    def define_reel(row):
        t, n = str(row['Type']).lower(), str(row['Note']).lower()
        # Si c'est une dépense, une ouverture ou un bid -> Négatif
        if "dépense" in t or any(x in n for x in ["ouverture", "bid", "achat"]):
            return -abs(row['M_Num'])
        return abs(row['M_Num'])
    
    df['Reel'] = df.apply(define_reel, axis=1)

    # 3. Intelligence des Dates (Gère 12/03 et 12/03/2026)
    def parse_date(d):
        d = str(d).strip()
        try:
            if len(d) <= 5: # Format dd/mm
                return datetime.strptime(f"{d}/{datetime.now().year}", "%d/%m/%Y")
            return datetime.strptime(d, "%d/%m/%Y")
        except: return datetime.now()

    df['Date_Obj'] = df['Date'].apply(parse_date)
    df = df.sort_values('Date_Obj')

# --- INTERFACE ---
st.markdown("<h1>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Opérations", "⚖️ Trésorerie", "🔮 Scanner"])

# --- PAGE 1 : SAISIE & PARC ---
with tab1:
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("add_tx", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            t_op = col_a.radio("Flux", ["Recette (+)", "Dépense (-)"], horizontal=True)
            # On récupère les plots dynamiquement pour le sélecteur
            active_plots = [p for p in df['Plot'].unique() if p != "" and p not in df[df['Note'].str.contains('Clôture', na=False)]['Plot'].unique()]
            plot_sel = col_b.selectbox("Plot", active_plots + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant", min_value=0, step=1000000)
            reason = st.text_input("Note (ex: Bid)")
            if st.form_submit_button("Enregistrer"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_sel, t_op, abs(mnt), reason])
                st.cache_data.clear(); st.rerun()
    with c2:
        st.markdown("<h3 class='albion-font'>Parc</h3>", unsafe_allow_html=True)
        with st.expander("🏗️ Nouveau Plot"):
            nn = st.text_input("Nom")
            if st.button("Ouvrir"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", 0, "Ouverture"])
                st.rerun()
        with st.expander("💰 Vendre Plot"):
            ps = st.selectbox("Cible", active_plots)
            if st.button("Vendre"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), ps, "Recette (+)", 0, "Clôture"])
                st.rerun()

# --- PAGE 2 : BILAN (LES VRAIS CHIFFRES) ---
with tab2:
    if not df.empty:
        net = df['Reel'].sum()
        color = "val-pos" if net >= 0 else "val-neg"
        st.markdown(f'<div class="albion-metric-box"><div class="albion-font" style="color:#bdc3c7">SOLDE NET GLOBAL</div><div class="metric-value {color}">{net:,.0f} Silver</div></div>'.replace(",", " "), unsafe_allow_html=True)
        
        # Groupement par famille (Weaver, Hunter...)
        df['Famille'] = df['Plot'].apply(lambda x: str(x).split()[0])
        stats = df.groupby('Famille')['Reel'].sum()
        cols = st.columns(4)
        for i, (fam, val) in enumerate(stats.items()):
            if fam == "": continue
            f_color = "val-pos" if val >= 0 else "val-neg"
            with cols[i % 4]:
                st.markdown(f'<div class="plot-card"><div class="plot-title">{fam}</div><div class="plot-value {f_color}">{val:,.0f}</div></div>'.replace(",", " "), unsafe_allow_html=True)
        
        st.divider()
        st.dataframe(df[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)

# --- PAGE 3 : SCANNER (RESTAURÉ) ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Analytique</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("JSON", height=200)
    if st.button("Lancer Scan", type="primary"):
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        res = []
        bar = st.progress(0)
        for i, p in enumerate(players):
            try:
                r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={p}").json()
                p_dat = [x for x in r.get('players', []) if x['Name'].lower() == p.lower()][0]
                res.append({"Pseudo": p_dat['Name'], "Guilde": p_dat.get('GuildName', '-'), "Fame": p_dat.get('CraftingFame', 0)})
            except: res.append({"Pseudo": p, "Guilde": "Inconnu", "Fame": 0})
            bar.progress((i+1)/len(players))
        st.dataframe(pd.DataFrame(res).sort_values(by="Fame", ascending=False), use_container_width=True)
