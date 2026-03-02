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

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .stButton > button:hover { background: linear-gradient(180deg, #e67e22, #d35400); transform: scale(1.05); box-shadow: 0 0 15px rgba(211, 84, 0, 0.6); }
    h1, h2, h3, h4, .albion-font { font-family: 'Cinzel', serif !important; color: #ecf0f1 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px; border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); margin-bottom: 20px; }
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.2em; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 2px; }
    .metric-value { font-family: 'Cinzel', serif; font-size: 3.5em; font-weight: bold; text-shadow: 0 0 20px rgba(255,255,255,0.1); }
    .summary-card { padding: 15px; border-radius: 15px; text-align: center; border: 1px solid rgba(255,255,255,0.1); }
    .sc-green { background: rgba(46, 204, 113, 0.1); border-color: rgba(46, 204, 113, 0.3); }
    .sc-red { background: rgba(231, 76, 60, 0.1); border-color: rgba(231, 76, 60, 0.3); }
    .sc-title { font-family: 'Cinzel', serif; font-size: 0.9em; opacity: 0.8; margin-bottom: 5px; }
    .sc-val { font-family: 'Roboto', sans-serif; font-size: 1.4em; font-weight: bold; }
    .txt-green { color: #2ecc71; }
    .txt-red { color: #ff6b6b; }
    .val-pos { color: #2ecc71; text-shadow: 0 0 15px rgba(46, 204, 113, 0.4); } 
    .val-neg { color: #ff6b6b; text-shadow: 0 0 15px rgba(255, 107, 107, 0.5); } 
    .plot-card { background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.9em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif; font-size: 1.2em; font-weight: 700; margin-top: 5px; }
    .archived-plot { opacity: 0.6; filter: grayscale(50%); border-color: rgba(255,255,255,0.05); }
    .archived-plot:hover { opacity: 1; filter: grayscale(0%); }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "APP_PASSWORD" in st.secrets:
    if st.sidebar.text_input("🔒 Mot de passe", type="password") != st.secrets["APP_PASSWORD"]:
        st.sidebar.warning("Saisissez le mot de passe pour accéder.")
        st.stop()

# --- CONFIGURATION FICHIERS ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.2f}".format(float(valeur)).replace(",", " ").replace(".", ",")
    except: return str(valeur)

def format_nombre_entier(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

# --- API ALBION ---
def get_player_stats(pseudo):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            candidats = [p for p in data.get('players', []) if p['Name'].lower() == pseudo.lower()]
            if not candidats: return {"Pseudo": pseudo, "Trouve": False}
            meilleur_fame = -1
            infos_meilleur = {}
            for p in candidats[:3]:
                try:
                    r_det = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p['Id']}", headers=headers)
                    if r_det.status_code == 200:
                        d = r_det.json()
                        val_fame = d.get('LifetimeStatistics', {}).get('Crafting', {}).get('Total') or d.get('CraftFame') or 0
                        if val_fame > meilleur_fame: meilleur_fame = val_fame; infos_meilleur = d
                    time.sleep(0.05)
                except: pass
            if infos_meilleur:
                return {
                    "Pseudo": infos_meilleur.get('Name'), "Guilde": infos_meilleur.get('GuildName') or "Aucune",
                    "Alliance": infos_meilleur.get('AllianceName') or "-", "AllianceTag": infos_meilleur.get('AllianceTag') or "",
                    "Craft Fame": meilleur_fame, "Trouve": True
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
    st.error(f"❌ Erreur connexion Google Sheets : {e}")
    st.stop()

# --- ANALYSE DES PLOTS ---
data_journal = worksheet.get_all_records()
df_journal = pd.DataFrame(data_journal) if data_journal else pd.DataFrame(columns=['Date', 'Plot', 'Type', 'Montant', 'Note'])

# --- CALCUL DU RÉEL AVEC DÉTECTION DES DÉPENSES ---
def calc_reel(row):
    try:
        t = str(row.get('Type', '')).lower()
        n = str(row.get('Note', '')).lower()
        m = float(row.get('Montant', 0))
        # Détection Dépense, Ouverture ou Bid pour forcer le négatif
        if "dépense" in t or "ouverture" in t or "bid" in n:
            return -abs(m)
        return abs(m)
    except:
        return 0.0

if not df_journal.empty:
    df_journal['Reel'] = df_journal.apply(calc_reel, axis=1)
    df_journal['Date_Obj'] = pd.to_datetime(df_journal['Date'], format='%d/%m/%Y', errors='coerce')
    df_journal['Date_Obj'] = df_journal['Date_Obj'].fillna(pd.to_datetime(df_journal['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

tous_les_plots = [p for p in df_journal['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_journal[(df_journal['Type'] == 'Clôture') | (df_journal['Note'] == 'Clôture')]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

if not plots_actifs:
    plots_actifs = ["Premier Plot"]

# --- INTERFACE PRINCIPALE ---
st.markdown("<h1>⚔️ Albion Economy Manager <span style='font-size:0.5em; color:#bdc3c7'>EU SERVER</span></h1>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["✍️ Opérations & Parc", "⚖️ Trésorerie & Archives", "🔮 Scanner Arion"])

# --- TAB 1 : SAISIE ---
with tab1:
    col_saisie, col_gestion = st.columns([2, 1], gap="large")
    with col_saisie:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction 💰</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            options_cibles = plots_actifs + ["---", "Taxe Guilde", "Autre"]
            nom_plot = st.selectbox("📍 Cible de l'opération :", options_cibles)
            type_op = st.radio("Type d'opération", ["Recette (+)", "Dépense (-)"], horizontal=True)
            montant = st.number_input("Montant (Silver)", step=10000, format="%d", min_value=1)
            note = st.text_input("Description (Optionnel)")
            if st.button("Valider la transaction", type="primary", use_container_width=True):
                if nom_plot == "---":
                    st.warning("Veuillez sélectionner une cible valide.")
                else:
                    try:
                        worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nom_plot, type_op, montant, note])
                        st.success(f"✅ Transaction enregistrée pour {nom_plot} !")
                        time.sleep(1) 
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Erreur d'écriture: {e}")

    with col_gestion:
        st.markdown("<h3 class='albion-font'>Gestion du Parc 🏗️</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Acheter / Ouvrir un nouveau plot", expanded=False):
            nouveau_nom = st.text_input("Nom du plot")
            cout_initial = st.number_input("Coût d'achat initial", step=1000000, format="%d", min_value=0)
            if st.button("Ouvrir ce plot", use_container_width=True):
                if nouveau_nom and nouveau_nom not in tous_les_plots:
                    try:
                        worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nouveau_nom, "Dépense (-)", cout_initial, "Ouverture"])
                        st.success(f"Plot '{nouveau_nom}' créé !")
                        time.sleep(1); st.rerun()
                    except Exception as e: st.error(str(e))

# --- TAB 2 : TRÉSORERIE ---
with tab2:
    st.markdown("<h3 class='albion-font'>État des Finances</h3>", unsafe_allow_html=True)
    if not df_journal.empty:
        min_date_globale = df_journal['Date_Obj'].min().date()
        max_date_globale = datetime.today().date()
        
        if 'date_debut' not in st.session_state: st.session_state['date_debut'] = min_date_globale
        if 'date_fin' not in st.session_state: st.session_state['date_fin'] = max_date_globale

        col_d1, col_d2, col_btn = st.columns([2, 2, 1])
        with col_d1: date_debut = st.date_input("Début", key="date_debut")
        with col_d2: date_fin = st.date_input("Fin", key="date_fin")
        with col_btn: 
            st.write(""); st.write("")
            if st.button("🔄 Total", use_container_width=True):
                st.session_state['date_debut'] = min_date_globale
                st.session_state['date_fin'] = max_date_globale
                st.rerun()

        mask = (df_journal['Date_Obj'].dt.date >= date_debut) & (df_journal['Date_Obj'].dt.date <= date_fin)
        df_filtre = df_journal.loc[mask]

        if not df_filtre.empty:
            total = df_filtre['Reel'].sum()
            total_rec = df_filtre[df_filtre['Reel'] > 0]['Reel'].sum()
            total_dep = df_filtre[df_filtre['Reel'] < 0]['Reel'].sum()

            st.markdown(f'<div class="albion-metric-box"><div class="metric-label">TRÉSORERIE NETTE</div><div class="metric-value {"val-pos" if total >= 0 else "val-neg"}">{format_monetaire(total)} Silver</div></div>', unsafe_allow_html=True)
            
            c_g, c_p = st.columns(2)
            c_g.markdown(f'<div class="summary-card sc-green"><div class="sc-title">RECETTES</div><div class="sc-val txt-green">+{format_monetaire(total_rec)}</div></div>', unsafe_allow_html=True)
            c_p.markdown(f'<div class="summary-card sc-red"><div class="sc-title">DÉPENSES</div><div class="sc-val txt-red">{format_monetaire(total_dep)}</div></div>', unsafe_allow_html=True)

            st.markdown("<h4 class='albion-font'>🟢 Plots Actifs</h4>", unsafe_allow_html=True)
            stats_p = df_filtre.groupby('Plot')['Reel'].sum()
            cols = st.columns(4)
            for i, p_n in enumerate(plots_actifs + ["Taxe Guilde", "Autre"]):
                val = stats_p.get(p_n, 0)
                with cols[i % 4]:
                    st.markdown(f'<div class="plot-card"><div class="plot-title">{p_n}</div><div class="plot-value {"val-pos" if val >= 0 else "val-neg"}">{format_nombre_entier(val)}</div></div>', unsafe_allow_html=True)

            st.divider()
            # FIX KEYERROR : On utilise l'index pour trier si Date_Obj pose problème
            df_hist = df_filtre.copy().sort_index(ascending=False)
            st.dataframe(df_hist[['Date', 'Plot', 'Type', 'Montant', 'Note']], use_container_width=True)

# --- TAB 3 : SCANNER ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner de Guildes</h3>", unsafe_allow_html=True)
    raw_text = st.text_area("Permissions JSON/Texte", height=200)
    if st.button("Lancer l'Analyse", type="primary", use_container_width=True):
        raw_players = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))
        if raw_players:
            results = []
            bar = st.progress(0)
            for i, p_name in enumerate(raw_players):
                infos = get_player_stats(p_name)
                results.append(infos)
                bar.progress((i+1)/len(raw_players))
            st.session_state['data_display'] = pd.DataFrame(results)
            st.rerun()

    if st.session_state.get('data_display') is not None:
        st.dataframe(st.session_state['data_display'], use_container_width=True)