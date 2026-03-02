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
st.set_page_config(page_title="Arion Economy Manager - Enterprise Edition", page_icon="⚔️", layout="wide")

# --- DESIGN SYSTEM EXHAUSTIF (CINZEL & ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@300;400;700&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

    /* Boutons Albion Style */
    .stButton > button {
        background: linear-gradient(180deg, #d35400, #a04000);
        color: white; border: 1px solid #e67e22; border-radius: 20px;
        font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase;
        padding: 12px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stButton > button:hover {
        background: linear-gradient(180deg, #e67e22, #d35400);
        transform: scale(1.05); box-shadow: 0 0 15px rgba(211, 84, 0, 0.6);
    }

    h1, h2, h3, h4, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        font-weight: 700;
    }

    /* Onglets (Tabs) Custom */
    .stTabs [data-baseweb="tab-list"] {
        gap: 15px; background-color: rgba(0, 0, 0, 0.3); padding: 12px; border-radius: 25px;
    }
    .stTabs [data-baseweb="tab"] { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.1em; }
    .stTabs [aria-selected="true"] { 
        background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; 
    }

    /* Boîtes de statistiques */
    .albion-metric-box {
        background: rgba(0, 0, 0, 0.4); padding: 25px; border-radius: 20px;
        border: 1px solid rgba(243, 156, 18, 0.3); text-align: center; margin-bottom: 25px;
    }
    .metric-value { 
        font-family: 'Roboto', sans-serif !important; 
        font-size: 3.8em; font-weight: 700; color: #ffffff;
    }

    /* Cartes Plots */
    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px;
        text-align: center; margin-bottom: 15px; transition: all 0.3s;
    }
    .plot-card:hover { border-color: #f39c12; transform: translateY(-5px); }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.4em; font-weight: 700; margin-top: 8px; }

    .val-pos { color: #2ecc71 !important; } 
    .val-neg { color: #ff6b6b !important; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔑 Accès", type="password") != st.secrets["app_password"]:
        st.info("Veuillez saisir le code d'accès Arion.")
        st.stop()

# --- CONNEXION GOOGLE SHEETS ---
@st.cache_resource
def init_gs_connection():
    try:
        if "gcp_service_account" in st.secrets:
            gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
        else:
            gc = gspread.service_account(filename='service_account.json')
        return gc
    except Exception as e:
        st.error(f"Erreur d'infrastructure : {e}"); return None

gc = init_gs_connection()

# --- MOTEUR DE DONNÉES ROBUSTE ---
def load_and_recalculate_data():
    try:
        sh = gc.open("Arion Plot")
        ws = sh.worksheet("Journal_App")
        ref_ws = sh.worksheet("Reference_Craft")
        
        # Récupération exhaustive pour éviter les sauts de lignes (7 à 101)
        raw_data = ws.get_all_records()
        df = pd.DataFrame(raw_data)
        
        if df.empty:
            return df, ws, ref_ws
            
        # 1. NETTOYAGE DES CHIFFRES (Robustesse)
        def clean_money(val):
            try: return float(str(val).replace(' ', '').replace('\xa0', '').replace(',', '.'))
            except: return 0.0
            
        df['M_Num'] = df['Montant'].apply(clean_money)
        
        # 2. LOGIQUE COHÉRENTE DES SIGNES (Calcul Interne)
        def apply_logic(row):
            t = str(row['Type']).lower()
            n = str(row['Note']).lower()
            # Si Dépense OU Ouverture OU Bid -> Négatif pour le calcul
            if "dépense" in t or any(w in n for w in ["ouverture", "bid", "achat"]):
                return -abs(row['M_Num'])
            return abs(row['M_Num'])
            
        df['Reel'] = df.apply(apply_logic, axis=1)
        df['Date_Obj'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        
        # 3. EXTRACTION DES FAMILLES (Sous-totaux)
        # Ex: "Weaver 1" devient "Weaver"
        df['Famille'] = df['Plot'].apply(lambda x: str(x).split()[0] if x else "Inconnu")
        
        return df, ws, ref_ws
    except Exception as e:
        st.error(f"Échec du moteur de calcul : {e}"); return None, None, None

df, worksheet, ws_ref = load_and_recalculate_data()

# --- GESTION DU PARC (DISSOCIATION ACTUELS / CLOS) ---
if not df.empty:
    plots_clotures = df[df['Note'].str.contains('Clôture|Vendu', case=False, na=False)]['Plot'].unique()
    tous_les_plots = [p for p in df['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
    plots_actuels = [p for p in tous_les_plots if p not in plots_clotures]
else:
    plots_actuels = []

# --- INTERFACE ---
st.markdown("<h1>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Page 1 : Opérations", "⚖️ Page 2 : Trésorerie", "🔮 Page 3 : Scanner"])

# --- PAGE 1 : ADMINISTRATION DU PARC ---
with tab1:
    c_form, c_parc = st.columns([2, 1], gap="large")
    
    with c_form:
        st.markdown("<h3 class='albion-font'>Journal de Saisie</h3>", unsafe_allow_html=True)
        with st.form("main_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nature = col1.radio("Flux", ["Recette (+)", "Dépense (-)"], horizontal=True)
            target = col2.selectbox("Plot", plots_actuels + ["Taxe Guilde", "Autre"])
            valeur = st.number_input("Montant (Silver)", min_value=0, step=1000000)
            note_tx = st.text_input("Note (Ex: Taxe Hebdo, Bid de plot...)")
            
            if st.form_submit_button("PUBLIER TRANSACTION"):
                # On écrit toujours en valeur ABSOLUE dans le GSheet
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), target, nature, abs(valeur), note_tx])
                st.toast("Synchronisation GSheet terminée."); st.cache_data.clear(); st.rerun()

    with c_parc:
        st.markdown("<h3 class='albion-font'>Vie du Parc</h3>", unsafe_allow_html=True)
        with st.expander("🏗️ Ouvrir Plot (Investissement)"):
            new_name = st.text_input("Désignation")
            cost = st.number_input("Capital investi", min_value=0)
            if st.button("Valider Ouverture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), new_name, "Dépense (-)", abs(cost), "Ouverture"])
                st.cache_data.clear(); st.rerun()
                
        with st.expander("💰 Vendre Plot (Liquidation)"):
            p_to_close = st.selectbox("Plot à fermer", plots_actuels)
            rev_val = st.number_input("Prix de revente", min_value=0)
            if st.button("Confirmer Clôture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_to_close, "Recette (+)", abs(rev_val), "Clôture"])
                st.cache_data.clear(); st.rerun()

# --- PAGE 2 : BILAN & COHÉRENCE ---
with tab2:
    if not df.empty:
        # SOLDE NET GLOBAL (Toutes périodes / Tous plots)
        total_global = df['Reel'].sum()
        status_color = "val-pos" if total_global >= 0 else "val-neg"
        
        st.markdown(f"""
        <div class="albion-metric-box">
            <div class="albion-font" style="color:#bdc3c7; font-size:1.2em;">TRÉSORERIE NETTE TOTALE</div>
            <div class="metric-value {status_color}">{"{:,.0f}".format(total_global).replace(",", " ")} Silver</div>
        </div>
        """, unsafe_allow_html=True)

        # SOUS-TOTAUX PAR MÉTIER (Groupement Weaver, Hunter, etc.)
        st.markdown("<h4 class='albion-font'>📊 Rentabilité par Type (Sous-totaux)</h4>", unsafe_allow_html=True)
        stats_famille = df.groupby('Famille')['Reel'].sum().reset_index()
        
        cols = st.columns(4)
        for i, row in stats_famille.iterrows():
            if row['Famille'] in ["Inconnu", ""]: continue
            f_color = "val-pos" if row['Reel'] >= 0 else "val-neg"
            with cols[i % 4]:
                st.markdown(f"""
                <div class="plot-card">
                    <div class="plot-title">{row['Famille']}</div>
                    <div class="plot-value {f_color}">{"{:,.0f}".format(row['Reel']).replace(",", " ")}</div>
                </div>
                """, unsafe_allow_html=True)

        # DISSOCIATION ACTUELS / CLOS
        st.divider()
        c_actu, c_clos = st.columns(2)
        with c_actu:
            st.markdown("<h4 class='albion-font'>🟢 Plots Actuels</h4>", unsafe_allow_html=True)
            df_actu = df[df['Plot'].isin(plots_actuels)].groupby('Plot')['Reel'].sum().reset_index()
            st.dataframe(df_actu.sort_values(by="Reel", ascending=False), use_container_width=True)
            
        with c_clos:
            st.markdown("<h4 class='albion-font'>🔴 Plots Clos (Historique)</h4>", unsafe_allow_html=True)
            df_clos = df[df['Plot'].isin(plots_clotures)].groupby('Plot')['Reel'].sum().reset_index()
            st.dataframe(df_clos, use_container_width=True)

# --- PAGE 3 : SCANNER ARION ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Analytique v3.0</h3>", unsafe_allow_html=True)
    raw_input = st.text_area("Données Permissions", height=200)
    
    if st.button("Lancer l'Audit"):
        # Extraction robuste
        raw_pseudos = list(set(re.findall(r'"Player:([^"]+)"', raw_input)))
        raw_guilds = [g.lower() for g in re.findall(r'"Guild:([^"]+)"', raw_input)]
        raw_alliances = [a.lower() for a in re.findall(r'"Alliance:([^"]+)"', raw_input)]
        
        df_reference = pd.DataFrame(ws_ref.get_all_records())
        
        final_audit = []
        p_bar = st.progress(0)
        
        for i, pseudo in enumerate(raw_pseudos):
            try:
                h = {'User-Agent': 'Mozilla/5.0'}
                r_api = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}", headers=h).json()
                p_info = [x for x in r_api.get('players', []) if x['Name'].lower() == pseudo.lower()][0]
                
                # Doublon ?
                statut = "✅ Unique"
                if p_info.get('GuildName', '').lower() in raw_guilds: statut = "⚠️ Doublon Guilde"
                elif p_info.get('AllianceTag', '').lower() in raw_alliances: statut = "⚠️ Doublon Alliance"
                
                # Evolution Fame
                fame_now = p_info.get('CraftingFame', 0)
                old_entry = df_reference[df_reference['Pseudo'] == p_info['Name']]
                prog, pct = 0, "Nouveau"
                if not old_entry.empty:
                    f_old = float(old_entry['Craft Fame'].values[0])
                    prog = fame_now - f_old
                    pct = f"{(prog/f_old)*100:.1f}%" if f_old > 0 else "0%"

                final_audit.append({"Pseudo": p_info['Name'], "Fame": fame_now, "Progression": prog, "% Évol.": pct, "Guilde": p_info.get('GuildName', '-'), "Statut": statut})
            except: final_audit.append({"Pseudo": pseudo, "Statut": "❌ API ERROR"})
            p_bar.progress((i+1)/len(raw_pseudos))
            
        st.session_state['res_audit'] = pd.DataFrame(final_audit).sort_values(by="Fame", ascending=False)

    if 'res_audit' in st.session_state:
        st.dataframe(st.session_state['res_audit'], use_container_width=True)
