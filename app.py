import os
import streamlit as st
import gspread
import pandas as pd
import requests
import time
import re
import json
from datetime import datetime
from collections import Counter

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Albion Economy Manager", page_icon="⚔️", layout="wide")

# --- SÉCURITÉ ---
def check_password():
    """Vérifie le mot de passe avant d'afficher l'app."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.markdown("<h2 style='text-align: center; color: #ecf0f1; font-family: Cinzel, serif;'>🔒 Accès Sécurisé - Code Albion</h2>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            pwd = st.text_input("Mot de passe", type="password")
            submit = st.form_submit_button("Valider")
            
            if submit:
                if pwd == st.secrets.get("app_password", "Albion2024!"): 
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Mot de passe incorrect")
        return False
    return True

if not check_password():
    st.stop()

# --- STYLE CSS ---
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
    .plot-card { background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 15px; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 1.2em; text-transform: uppercase; font-weight: bold; letter-spacing: 1px; }
    .plot-value { font-family: 'Roboto', sans-serif; font-size: 1.6em; font-weight: 700; margin-top: 10px; }
    .archived-plot { opacity: 0.6; filter: grayscale(50%); border-color: rgba(255,255,255,0.05); }
    .archived-plot:hover { opacity: 1; filter: grayscale(0%); }
</style>
""", unsafe_allow_html=True)

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

def get_typology(name):
    if name in ["Taxe Guilde", "Autre"]: return "DIVERS"
    base = re.sub(r'[\d\s]+$', '', str(name)).strip().upper()
    return base if base else "INCONNU"

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
                        if val_fame > meilleur_fame: 
                            meilleur_fame = val_fame
                            infos_meilleur = d
                    time.sleep(0.05)
                except: pass
            if infos_meilleur:
                return {
                    "Pseudo": infos_meilleur.get('Name'), 
                    "Guilde": infos_meilleur.get('GuildName') or "Aucune",
                    "Alliance": infos_meilleur.get('AllianceName') or "-", 
                    "Craft Fame": meilleur_fame, 
                    "Trouve": True
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

tous_les_plots = [p for p in df_journal['Plot'].unique() if str(p).strip() not in ["", "Taxe Guilde", "Autre"]]
plots_clotures = df_journal[(df_journal['Type'] == 'Clôture') | (df_journal['Note'] == 'Clôture')]['Plot'].unique().tolist()
plots_actifs = [p for p in tous_les_plots if p not in plots_clotures]

if not plots_actifs:
    plots_actifs = ["Premier Plot"]

# --- INTERFACE PRINCIPALE ---
st.markdown("<h1>⚔️ Albion Economy Manager <span style='font-size:0.5em; color:#bdc3c7'>EU SERVER</span></h1>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["✍️ Opérations & Parc", "⚖️ Trésorerie & Archives", "🔮 Scanner Arion"])

# --- TAB 1 : SAISIE ET GESTION DU PARC ---
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
            nouveau_nom = st.text_input("Nom du plot (ex: Fibre Mars)")
            cout_initial = st.number_input("Coût d'achat initial (Silver)", step=1000000, format="%d", min_value=0)
            if st.button("Ouvrir ce plot", use_container_width=True):
                if nouveau_nom and nouveau_nom not in tous_les_plots:
                    try:
                        worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nouveau_nom, "Dépense (-)", cout_initial, "Ouverture"])
                        st.success(f"Plot '{nouveau_nom}' créé !")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")
                else:
                    st.warning("Nom invalide ou déjà utilisé. Utilisez un nom unique (ex: Tissu 2).")

        with st.expander("🔴 Clôturer / Vendre un plot", expanded=False):
            plot_a_fermer = st.selectbox("Plot à clôturer", plots_actifs)
            prix_revente = st.number_input("Prix de revente / récupération (Silver)", step=1000000, format="%d", min_value=0, value=0)
            if st.button("Confirmer la clôture", use_container_width=True):
                if plot_a_fermer:
                    try:
                        worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_a_fermer, "Recette (+)", prix_revente, "Clôture"])
                        st.success(f"Le plot '{plot_a_fermer}' a été vendu/archivé !")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur: {e}")

# --- TAB 2 : TRÉSORERIE & ARCHIVES ---
with tab2:
    st.markdown("<h3 class='albion-font'>État des Finances</h3>", unsafe_allow_html=True)
    if not df_journal.empty:
        def calc_reel(row):
            t = str(row['Type']).lower()
            m = float(row.get('Montant', 0))
            if "dépense" in t: return -m
            elif "recette" in t: return m
            return 0
            
        df_journal['Reel'] = df_journal.apply(calc_reel, axis=1)
        df_journal['Date_Obj'] = pd.to_datetime(df_journal['Date'], format='%d/%m/%Y', errors='coerce')
        df_journal['Date_Obj'] = df_journal['Date_Obj'].fillna(pd.to_datetime(df_journal['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

        min_date_globale = df_journal['Date_Obj'].min().date()
        max_date_globale = max(df_journal['Date_Obj'].max().date(), datetime.today().date())

        if 'date_debut' not in st.session_state: st.session_state['date_debut'] = min_date_globale
        if 'date_fin' not in st.session_state: st.session_state['date_fin'] = max_date_globale

        def reset_dates_totales(d_min, d_max):
            st.session_state['date_debut'] = d_min
            st.session_state['date_fin'] = d_max

        st.markdown("<div style='background:rgba(255,255,255,0.05); padding:15px; border-radius:10px; margin-bottom:20px;'>", unsafe_allow_html=True)
        col_d1, col_d2, col_btn = st.columns([2, 2, 1])
        with col_d1: date_debut = st.date_input("Début", key="date_debut")
        with col_d2: date_fin = st.date_input("Fin", key="date_fin")
        with col_btn:
            st.write("")
            st.write("")
            st.button("🔄 Afficher le Total", on_click=reset_dates_totales, args=(min_date_globale, max_date_globale), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        mask = (df_journal['Date_Obj'].dt.date >= date_debut) & (df_journal['Date_Obj'].dt.date <= date_fin)
        df_filtre = df_journal.loc[mask]

        if not df_filtre.empty:
            total = df_filtre['Reel'].sum()
            total_recettes = df_filtre[df_filtre['Reel'] > 0]['Reel'].sum()
            total_depenses = df_filtre[df_filtre['Reel'] < 0]['Reel'].sum() 

            css_class = "val-pos" if total >= 0 else "val-neg"
            st.markdown(f"""
            <div class="albion-metric-box">
                <div class="metric-label">TRÉSORERIE NETTE (PÉRIODE)</div>
                <div class="metric-value {css_class}">{format_monetaire(total)} <span style="font-size:0.4em; vertical-align:middle; color:#bdc3c7;">Silver</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            c_gains, c_pertes = st.columns(2)
            with c_gains: st.markdown(f'<div class="summary-card sc-green"><div class="sc-title">RECETTES (+)</div><div class="sc-val txt-green">+{format_monetaire(total_recettes)}</div></div>', unsafe_allow_html=True)
            with c_pertes: st.markdown(f'<div class="summary-card sc-red"><div class="sc-title">DÉPENSES & ACHATS (-)</div><div class="sc-val txt-red">{format_monetaire(total_depenses)}</div></div>', unsafe_allow_html=True)

            st.divider()

            # --- PLOTS ACTIFS CONSOLIDÉS PAR FAMILLE ---
            st.markdown(f"<h4 class='albion-font'>🟢 Bilan Consolidé par Famille</h4>", unsafe_allow_html=True)
            
            # Préparation des données par famille
            df_filtre_family = df_filtre.copy()
            df_filtre_family['Famille'] = df_filtre_family['Plot'].apply(get_typology)
            
            # On ne garde que les transactions des plots actuellement actifs ou des frais divers
            plots_autorises = plots_actifs + ["Taxe Guilde", "Autre"]
            df_filtre_actifs = df_filtre_family[df_filtre_family['Plot'].isin(plots_autorises)]
            
            # Regroupement et somme
            stats_familles = df_filtre_actifs.groupby('Famille')['Reel'].sum().reset_index()
            
            if not stats_familles.empty:
                cols_fam = st.columns(3) # Affichage sur 3 colonnes pour des étiquettes plus larges
                idx = 0
                for row in stats_familles.itertuples():
                    if row.Reel != 0 or row.Famille != "DIVERS":
                        color_class = "val-pos" if row.Reel >= 0 else "val-neg"
                        with cols_fam[idx % 3]:
                            st.markdown(f"""
                            <div class="plot-card">
                                <div class="plot-title">{row.Famille}</div>
                                <div class="plot-value {color_class}">{format_nombre_entier(row.Reel)}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        idx += 1

            st.divider()
            st.markdown("<h4 class='albion-font'>Historique Détaillé</h4>", unsafe_allow_html=True)
            df_display = df_filtre.sort_values(by='Date_Obj', ascending=False).copy()
            st.dataframe(df_display[['Date', 'Plot', 'Type', 'Montant', 'Note']], use_container_width=True, column_config={"Montant": st.column_config.NumberColumn(format="%d 💰")})

# --- TAB 3 : ARION SCANNER ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner de Guildes & Alliances</h3>", unsafe_allow_html=True)
    col_input, col_action = st.columns([3, 1], gap="medium")
    with col_input:
        if 'json_input' not in st.session_state: st.session_state['json_input'] = ""
        raw_text = st.text_area("Permissions JSON/Texte", value=st.session_state['json_input'], height=200, help="Collez ici l'export de votre plot.")
    with col_action:
        st.write("### Actions")
        scan_btn = st.button("Lancer l'Analyse", type="primary", use_container_width=True)
        st.write("")
        save_ref_btn = st.button("Sauvegarder la référence", use_container_width=True)

    if 'data_display' not in st.session_state: st.session_state['data_display'] = None

    if scan_btn and raw_text:
        with st.spinner("Consultation des archives et comptage des membres..."):
            raw_players_all = re.findall(r'"Player:([^"]+)"', raw_text)
            counts = Counter([p.lower() for p in raw_players_all])
            raw_players = list(set(raw_players_all))
            
            ref_players = []
            if ws_ref:
                try:
                    ref_data = ws_ref.get_all_records()
                    ref_players = [str(r.get('Pseudo', '')).lower() for r in ref_data]
                except: pass

            if not raw_players: 
                st.warning("Aucun joueur trouvé.")
            else:
                resultats = []
                barre = st.progress(0)
                for i, p_name in enumerate(raw_players):
                    infos = get_player_stats(p_name)
                    p_lower = str(infos.get('Pseudo', p_name)).lower()
                    
                    infos['Occurrences'] = counts.get(p_lower, 1)
                    infos['Statut'] = "✅ Connu" if p_lower in ref_players else "🆕 Nouveau"
                    
                    resultats.append(infos)
                    barre.progress((i+1)/len(raw_players))
                    time.sleep(0.05)
                    
                barre.empty()
                st.toast("Scan terminé !", icon="✅")
                st.session_state['data_display'] = pd.DataFrame(resultats)

    if st.session_state['data_display'] is not None:
        df_res = st.session_state['data_display']
        
        # --- BOUTON D'ALERTE DOUBLON ---
        top_guilds = df_res[df_res['Guilde'] != 'Aucune']['Guilde'].value_counts()
        if not top_guilds.empty:
            guilde_cible = top_guilds.index[0]
            nb_joueurs = top_guilds.iloc[0]
            
            if nb_joueurs > 1:
                st.markdown("<br>", unsafe_allow_html=True)
                st.button(f"🚨 DOUBLON À PURGER : {guilde_cible} ({nb_joueurs} joueurs)", type="primary", use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)
            
        st.markdown("#### 📋 Détail des joueurs")
        st.dataframe(
            df_res, 
            use_container_width=True, 
            height=400,
            column_config={
                "Guilde": st.column_config.TextColumn("Guilde 🛡️"),
                "Alliance": st.column_config.TextColumn("Alliance ⚔️"),
                "Occurrences": st.column_config.NumberColumn("Doublons 🔄"),
                "Statut": st.column_config.TextColumn("Statut Réf. 📌")
            }
        )
