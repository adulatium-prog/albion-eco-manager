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
st.set_page_config(
    page_title="Arion Economy Manager - Industrial Grade",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- DESIGN SYSTEM COMPLET (CINZEL & ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@300;400;700&family=Roboto+Mono&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #201b46, #1a1a2e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

    /* Boutons Style Albion Online */
    .stButton > button {
        background: linear-gradient(180deg, #d35400 0%, #a04000 100%);
        color: white; border: 1px solid #e67e22; border-radius: 4px;
        font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase;
        width: 100%; padding: 14px; transition: 0.3s;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    .stButton > button:hover {
        background: linear-gradient(180deg, #e67e22 0%, #d35400 100%);
        box-shadow: 0 0 20px rgba(211, 84, 0, 0.4);
        transform: translateY(-2px);
    }

    /* Typographie Strategique */
    h1, h2, h3, h4, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #f39c12 !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        letter-spacing: 2px;
    }

    /* Dashboard Metrics */
    .metric-container {
        background: rgba(0, 0, 0, 0.5);
        padding: 35px;
        border-radius: 12px;
        border: 1px solid rgba(243, 156, 18, 0.3);
        text-align: center;
        margin-bottom: 30px;
    }
    .metric-label { font-family: 'Cinzel', serif; font-size: 1.1em; color: #bdc3c7; }
    .metric-value { 
        font-family: 'Roboto', sans-serif !important; 
        font-size: 3.5em; font-weight: 700; color: #ffffff;
    }

    /* Cards de Plots Actuels/Clos */
    .plot-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(243, 156, 18, 0.2);
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        transition: 0.2s;
        height: 100%;
    }
    .plot-card:hover { background: rgba(255, 255, 255, 0.08); border-color: #f39c12; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; margin-bottom: 10px; }
    .plot-val { font-family: 'Roboto', sans-serif !important; font-size: 1.4em; font-weight: 700; }

    .val-pos { color: #2ecc71 !important; }
    .val-neg { color: #e74c3c !important; }

    /* Custom Dataframe & Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 15px; background-color: rgba(0, 0, 0, 0.4); padding: 12px; border-radius: 20px;
    }
    .stTabs [data-baseweb="tab"] { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1em; }
    .stTabs [aria-selected="true"] { color: #f39c12 !important; font-weight: bold; border-bottom: 2px solid #f39c12; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔑 CLÉ D'ACCÈS", type="password") != st.secrets["app_password"]:
        st.info("Veuillez saisir votre clé d'accès Arion.")
        st.stop()

# --- MOTEUR DE CONNEXION ---
@st.cache_resource
def init_connection():
    try:
        if "gcp_service_account" in st.secrets:
            info = json.loads(st.secrets["gcp_service_account"])
            return gspread.service_account_from_dict(info)
        return gspread.service_account(filename='service_account.json')
    except Exception as e:
        st.error(f"Erreur d'infrastructure : {e}"); return None

gc = init_connection()

# --- MOTEUR DE DONNÉES ROBUSTE (RECALCUL COHÉRENT) ---
def load_all_data():
    try:
        sh = gc.open("Arion Plot")
        ws = sh.worksheet("Journal_App")
        ws_ref = sh.worksheet("Reference_Craft")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(), ws, ws_ref

        # 1. NETTOYAGE PROFOND DES CHIFFRES (Robustesse face au formatage GSheet)
        # Supprime tout sauf les chiffres, points et signes moins
        df['M_Clean'] = df['Montant'].astype(str).str.replace(r'[\s\u00A0,]', '', regex=True).replace('', '0')
        df['M_Num'] = pd.to_numeric(df['M_Clean'], errors='coerce').fillna(0)

        # 2. LOGIQUE DE CALCUL ARION (Signes internes)
        # Dépenses = Dépenses + Ouverture + Bid
        # Revenus = Recette + Clôture
        def interpret_reel(row):
            t = str(row.get('Type', '')).lower()
            n = str(row.get('Note', '')).lower()
            val = abs(row['M_Num'])
            if "dépense" in t or "ouverture" in n or "bid" in n:
                return -val
            return val

        df['Reel'] = df.apply(interpret_reel, axis=1)
        df['Date_Obj'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        
        # 3. GROUPEMENT PAR FAMILLE (Butcher 1 + Butcher 2 = Butcher)
        df['Famille'] = df['Plot'].apply(lambda x: str(x).split()[0] if x else "Indéfini")
        
        return df, ws, ws_ref
    except Exception as e:
        st.error(f"Échec de lecture de la base : {e}"); return None, None, None

df, worksheet, ws_ref_sheet = load_all_data()

# --- IDENTIFICATION DU PARC ---
if not df.empty:
    plots_clos = df[df['Note'].str.contains('Clôture|Vente', case=False, na=False)]['Plot'].unique()
    tous_plots = [p for p in df['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
    plots_actuels = [p for p in tous_plots if p not in plots_clos]
else:
    plots_actuels = []

# --- INTERFACE MULTI-PAGES ---
tab_ops, tab_fin, tab_scan = st.tabs(["✍️ OPÉRATIONS & PARC", "📊 ANALYSE FINANCIÈRE", "🔮 SCANNER ANALYTIQUE"])

# --- PAGE 1 : OPÉRATIONS ---
with tab_ops:
    c_form, c_parc = st.columns([2, 1], gap="large")
    with c_form:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("main_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nature = col1.radio("Flux", ["Recette (+)", "Dépense (-)"], horizontal=True)
            p_sel = col2.selectbox("Plot Cible", plots_actuels + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant Silver", min_value=0, step=1000000)
            note = st.text_input("Note (Ex: Taxe Hebdo, Bid de plot...)")
            if st.form_submit_button("ENREGISTRER TRANSACTION"):
                # On écrit toujours en valeur ABSOLUE dans le sheet pour la propreté
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_sel, nature, abs(mnt), note])
                st.cache_data.clear(); time.sleep(1); st.rerun()

    with c_parc:
        st.markdown("<h3 class='albion-font'>Gestion du Parc</h3>", unsafe_allow_html=True)
        with st.expander("🏗️ Ouvrir Nouveau Plot"):
            nn = st.text_input("Désignation")
            if st.button("Valider Ouverture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", 0, "Ouverture"])
                st.cache_data.clear(); st.rerun()
        with st.expander("🔴 Clôturer Plot"):
            pc = st.selectbox("Plot à fermer", plots_actuels)
            if st.button("Confirmer Clôture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), pc, "Recette (+)", 0, "Clôture"])
                st.cache_data.clear(); st.rerun()

# --- PAGE 2 : ANALYSE (RECALCUL COHÉRENT) ---
with tab_fin:
    if not df.empty:
        st.markdown("<h3 class='albion-font'>État Major des Finances</h3>", unsafe_allow_html=True)
        
        # CALCUL DES TOTAUX DEMANDÉS
        total_depenses = abs(df[df['Reel'] < 0]['Reel'].sum())
        total_recettes = df[df['Reel'] > 0]['Reel'].sum()
        solde_net = total_recettes - total_depenses
        
        # Dashboard Principal
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="metric-container"><div class="metric-label">TOTAL DÉPENSES</div><div class="metric-value val-neg">{"{:,.0f}".format(total_depenses).replace(",", " ")}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-container"><div class="metric-label">TOTAL RECETTES</div><div class="metric-value val-pos">{"{:,.0f}".format(total_recettes).replace(",", " ")}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-container"><div class="metric-label">SOLDE NET GLOBAL</div><div class="metric-value {"val-pos" if solde_net >= 0 else "val-neg"}">{"{:,.0f}".format(solde_net).replace(",", " ")}</div></div>', unsafe_allow_html=True)

        # SOUS-TOTAL PAR FAMILLE (Butcher, Weaver, etc.)
        st.markdown("<h4 class='albion-font'>📊 Rentabilité par Métier (Consolidé)</h4>", unsafe_allow_html=True)
        stats_famille = df.groupby('Famille')['Reel'].sum().sort_values(ascending=False).reset_index()
        
        cols = st.columns(4)
        for i, row in stats_famille.iterrows():
            if row['Famille'] in ["Indéfini", ""]: continue
            with cols[i % 4]:
                st.markdown(f"""
                <div class="plot-card">
                    <div class="plot-title">{row['Famille']}</div>
                    <div class="plot-val {'val-pos' if row['Reel'] >= 0 else 'val-neg'}">
                        {"{:,.0f}".format(row['Reel']).replace(",", " ")}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.divider()
        # DISSOCIATION ACTUELS / CLOS
        ca, cb = st.columns(2)
        with ca:
            st.markdown("<h4 class='albion-font'>🟢 Plots Actuels</h4>", unsafe_allow_html=True)
            df_actu = df[df['Plot'].isin(plots_actuels)].groupby('Plot')['Reel'].sum().reset_index()
            st.dataframe(df_actu.sort_values(by="Reel", ascending=False), use_container_width=True)
        with cb:
            st.markdown("<h4 class='albion-font'>🔴 Plots Clos (Archives)</h4>", unsafe_allow_html=True)
            df_clos = df[df['Plot'].isin(plots_clos)].groupby('Plot')['Reel'].sum().reset_index()
            st.dataframe(df_clos, use_container_width=True)

# --- PAGE 3 : SCANNER ANALYTIQUE ---
with tab_scan:
    st.markdown("<h3 class='albion-font'>Scanner Arion v3.0</h3>", unsafe_allow_html=True)
    raw_input = st.text_area("Données de Permissions (JSON/Texte)", height=250)
    
    if st.button("LANCER L'AUDIT API", type="primary"):
        with st.spinner("Audit des serveurs Albion en cours..."):
            pseudos = list(set(re.findall(r'"Player:([^"]+)"', raw_input)))
            guilds = [g.lower() for g in re.findall(r'"Guild:([^"]+)"', raw_input)]
            alliances = [a.lower() for a in re.findall(r'"Alliance:([^"]+)"', raw_input)]
            
            ref_data = pd.DataFrame(ws_ref_sheet.get_all_records())
            
            audit_res = []
            p_bar = st.progress(0)
            for i, p in enumerate(pseudos):
                try:
                    h = {'User-Agent': 'Mozilla/5.0'}
                    r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={p}", headers=h).json()
                    p_info = [x for x in r.get('players', []) if x['Name'].lower() == p.lower()][0]
                    
                    # Doublon ?
                    status = "✅ Unique"
                    if p_info.get('GuildName', '').lower() in guilds: status = "⚠️ Doublon Guilde"
                    elif p_info.get('AllianceTag', '').lower() in alliances: status = "⚠️ Doublon Alliance"
                    
                    # Evolution Fame
                    fame_now = p_info.get('CraftingFame', 0)
                    old_row = ref_data[ref_data['Pseudo'] == p_info['Name']]
                    prog, evol = 0, "Nouveau"
                    if not old_row.empty:
                        f_old = old_row['Craft Fame'].values[0]
                        prog = fame_now - f_old
                        evol = f"{(prog/f_old)*100:.1f}%" if f_old > 0 else "0%"

                    audit_res.append({"Pseudo": p_info['Name'], "Fame": fame_now, "Progression": prog, "% Évol.": evol, "Guilde": p_info.get('GuildName', '-'), "Statut": status})
                except: audit_res.append({"Pseudo": p, "Statut": "❌ API ERROR"})
                p_bar.progress((i+1)/len(pseudos))
            
            st.session_state['last_audit'] = pd.DataFrame(audit_res).sort_values(by="Fame", ascending=False)

    if 'last_audit' in st.session_state:
        st.dataframe(st.session_state['last_audit'], use_container_width=True)
        if st.button("SAUVEGARDER COMME RÉFÉRENCE"):
            df_save = st.session_state['last_audit'][['Pseudo', 'Fame']].rename(columns={'Fame': 'Craft Fame'})
            ws_ref_sheet.clear()
            ws_ref_sheet.update([df_save.columns.values.tolist()] + df_save.values.tolist())
            st.success("Référence mise à jour.")
