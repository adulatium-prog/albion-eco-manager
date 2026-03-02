import os
import streamlit as st
import gspread
import pandas as pd
import requests
import time
import re
import json
from datetime import datetime

# --- CONFIGURATION STRUCTURELLE ---
st.set_page_config(page_title="Arion Economy - Command Center", page_icon="⚔️", layout="wide")

# --- DESIGN SYSTEM ARION (CINZEL & ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@300;400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 12px 24px; transition: 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .stButton > button:hover { transform: scale(1.05); box-shadow: 0 0 15px rgba(211, 84, 0, 0.6); }
    h1, h2, h3, .albion-font { font-family: 'Cinzel', serif !important; color: #f39c12 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
    .stTabs [data-baseweb="tab-list"] { gap: 15px; background-color: rgba(0, 0, 0, 0.3); padding: 12px; border-radius: 25px; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.4); padding: 30px; border-radius: 20px; border: 1px solid rgba(243, 156, 18, 0.3); text-align: center; margin-bottom: 25px; }
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.5em; font-weight: 700; color: #ffffff; }
    .plot-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 15px; }
    .plot-title { font-family: 'Cinzel', serif; color: #bdc3c7; font-size: 0.9em; text-transform: uppercase; }
    .val-pos { color: #2ecc71 !important; } .val-neg { color: #ff6b6b !important; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔑 ACCÈS", type="password") != st.secrets["app_password"]:
        st.info("Système Arion en attente d'authentification.")
        st.stop()

# --- CONNEXION & MOTEUR DE DONNÉES ---
try:
    if "gcp_service_account" in st.secrets:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    else:
        gc = gspread.service_account(filename='service_account.json')
    sh = gc.open("Arion Plot")
    ws_journal = sh.worksheet("Journal_App")
    ws_ref = sh.worksheet("Reference_Craft")
    
    # Récupération de l'intégralité du GSheet (aucune ligne sautée)
    df = pd.DataFrame(ws_journal.get_all_records())
except Exception as e:
    st.error(f"Erreur d'infrastructure : {e}"); st.stop()

# --- MOTEUR DE CALCUL RATIONNEL ---
if not df.empty:
    # 1. Nettoyage mathématique
    df['M_Num'] = df['Montant'].astype(str).str.replace(r'[\s\u00A0,]', '', regex=True).replace('', '0').astype(float)
    
    # 2. Application de TA FORMULE (Logic Signe)
    # Dépenses = Dépenses + Ouverture + Bid
    # Revenus = Recette + Clôture
    def apply_arion_logic(row):
        t = str(row['Type']).lower()
        n = str(row['Note']).lower()
        val = abs(row['M_Num'])
        
        if "dépense" in t or "ouverture" in n or "bid" in n:
            return -val # C'est une dépense
        return val # C'est un revenu (Recette ou Clôture)
    
    df['Reel'] = df.apply(apply_arion_logic, axis=1)
    
    # 3. Séparation Plots Actuels / Clos
    plots_clos = df[df['Note'].str.contains('Clôture|Vente', case=False, na=False)]['Plot'].unique()
    tous_les_plots = [p for p in df['Plot'].unique() if p != "" and p not in ["Taxe Guilde", "Autre"]]
    plots_actuels = [p for p in tous_les_plots if p not in plots_clos]
    
    # 4. Groupement par Famille (Butcher 1 + Butcher 2 = Butcher)
    df['Famille'] = df['Plot'].apply(lambda x: str(x).split()[0] if x else "Autre")

# --- INTERFACE ---
st.markdown("<h1>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ OPÉRATIONS", "⚖️ TRÉSORERIE", "🔮 SCANNER"])

# --- PAGE 1 : OPÉRATIONS & PARC ---
with tab1:
    c_form, c_parc = st.columns([2, 1], gap="large")
    with c_form:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("main_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            nature = col_a.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
            p_sel = col_b.selectbox("Plot Cible", plots_actuels + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant Silver", min_value=0, step=1000000)
            note = st.text_input("Note (ex: Bid, Ouverture, Taxe...)")
            if st.form_submit_button("PUBLIER TRANSACTION"):
                ws_journal.append_row([datetime.now().strftime("%d/%m/%Y"), p_sel, nature, abs(mnt), note])
                st.cache_data.clear(); st.rerun()

    with c_parc:
        st.markdown("<h3 class='albion-font'>Gestion Parc</h3>", unsafe_allow_html=True)
        with st.expander("🏗️ Ouvrir Plot"):
            nn = st.text_input("Désignation")
            if st.button("Valider Ouverture"):
                ws_journal.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", 0, "Ouverture"])
                st.rerun()
        with st.expander("🔴 Clôturer Plot"):
            pc = st.selectbox("Plot à fermer", plots_actuels)
            if st.button("Confirmer Clôture"):
                ws_journal.append_row([datetime.now().strftime("%d/%m/%Y"), pc, "Recette (+)", 0, "Clôture"])
                st.rerun()

# --- PAGE 2 : TRÉSORERIE (CALCULS COHÉRENTS) ---
with tab2:
    if not df.empty:
        # CALCUL DES TOTAUX SELON TA FORMULE
        total_depenses = abs(df[df['Reel'] < 0]['Reel'].sum())
        total_revenus = df[df['Reel'] > 0]['Reel'].sum()
        solde_net = total_revenus - total_depenses
        
        # Dashboard Principal
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="albion-metric-box"><div class="metric-label">TOTAL DÉPENSES</div><div class="plot-val val-neg">{"{:,.0f}".format(total_depenses).replace(",", " ")}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="albion-metric-box"><div class="metric-label">TOTAL REVENUS</div><div class="plot-val val-pos">{"{:,.0f}".format(total_revenus).replace(",", " ")}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="albion-metric-box"><div class="metric-label">SOLDE GLOBAL</div><div class="plot-val {"val-pos" if solde_net >= 0 else "val-neg"}">{"{:,.0f}".format(solde_net).replace(",", " ")}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("<h4 class='albion-font'>📊 Rentabilité par Secteur (Sous-totaux)</h4>", unsafe_allow_html=True)
        
        # SOUS-TOTAL PAR FAMILLE (Butcher 1 & 2 sont liés ici)
        familles = df.groupby('Famille')['Reel'].sum().sort_values(ascending=False)
        cols = st.columns(4)
        for i, (fam, val) in enumerate(familles.items()):
            if fam in ["", "Autre"]: continue
            with cols[i % 4]:
                st.markdown(f'<div class="plot-card"><div class="plot-title">{fam}</div><div class="plot-val {"val-pos" if val >= 0 else "val-neg"}">{"{:,.0f}".format(val).replace(",", " ")}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("<h4 class='albion-font'>Dissociation du Parc</h4>", unsafe_allow_html=True)
        ca, cb = st.columns(2)
        with ca:
            st.markdown("🟢 **Plots Actuels**")
            st.dataframe(df[df['Plot'].isin(plots_actuels)].groupby('Plot')['Reel'].sum().sort_values(ascending=False), use_container_width=True)
        with cb:
            st.markdown("🔴 **Plots Clos (Archives)**")
            st.dataframe(df[df['Plot'].isin(plots_clos)].groupby('Plot')['Reel'].sum(), use_container_width=True)

# --- PAGE 3 : SCANNER (ROBUSTE) ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Arion v3.0</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("Données Permissions", height=200)
    if st.button("Lancer l'Audit", type="primary"):
        pseudos = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        res = []
        bar = st.progress(0)
        for i, p in enumerate(pseudos):
            try:
                r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={p}").json()
                p_dat = [x for x in r.get('players', []) if x['Name'].lower() == p.lower()][0]
                res.append({"Pseudo": p_dat['Name'], "Fame": p_dat.get('CraftingFame', 0), "Guilde": p_dat.get('GuildName', '-')})
            except: res.append({"Pseudo": p, "Fame": 0, "Guilde": "Erreur"})
            bar.progress((i+1)/len(pseudos))
        st.dataframe(pd.DataFrame(res).sort_values(by="Fame", ascending=False), use_container_width=True)
