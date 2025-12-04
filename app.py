import streamlit as st
import gspread
import pandas as pd
import requests
import time
import json
import re
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    mot_de_passe_secret = st.secrets["app_password"]
    input_password = st.sidebar.text_input("🔒 Mot de passe", type="password")
    if input_password != mot_de_passe_secret:
        st.sidebar.warning("Saisis le mot de passe pour accéder.")
        st.stop()

# --- CONFIGURATION ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"
SEUIL_FAME_MIN = 4000000 

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.2f}".format(float(valeur)).replace(",", " ").replace(".", ",")
    except: return str(valeur)

def format_nombre_entier(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

# --- API ALBION ---
def get_player_stats(pseudo):
    """ 
    Récupère les stats et surtout la Guilde/Alliance actuelle pour vérifier les doublons.
    """
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url_search, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            
            # Recherche exacte
            target = None
            for p in players:
                if p['Name'].lower() == pseudo.lower():
                    target = p
                    break
            if not target and players: target = players[0]
            
            if target:
                player_id = target['Id']
                
                # Noms officiels (API)
                guild_name = target.get('GuildName') or "Aucune"
                alliance_name = target.get('AllianceName') or "-"

                # Appel détail pour la Fame
                url_stats = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}"
                resp_stats = requests.get(url_stats, headers=headers)
                craft_fame = 0
                
                if resp_stats.status_code == 200:
                    info = resp_stats.json()
                    if info.get('AllianceName'): alliance_name = info.get('AllianceName')
                    
                    ls = info.get('LifetimeStatistics', {})
                    crafting = ls.get('Crafting', {}) or ls.get('crafting', {})
                    candidates = [info.get('CraftFame'), crafting.get('Total'), crafting.get('craftFame')]
                    for val in candidates:
                        if isinstance(val, (int, float)):
                            craft_fame = val
                            break
                            
                return {
                    "Pseudo": target['Name'], 
                    "Guilde": guild_name,
                    "Alliance": alliance_name,
                    "Craft Fame": craft_fame, 
                    "Trouve": True
                }
        return {"Pseudo": pseudo, "Guilde": "?", "Alliance": "?", "Craft Fame": 0, "Trouve": False}
    except: return {"Pseudo": pseudo, "Guilde": "?", "Alliance": "?", "Craft Fame": 0, "Trouve": False}

# --- CONNEXION ---
try:
    if "gcp_service_account" in st.secrets:
        secret_content = st.secrets["gcp_service_account"].strip()
        dict_secrets = json.loads(secret_content)
        gc = gspread.service_account_from_dict(dict_secrets)
    else:
        gc = gspread.service_account(filename='service_account.json')
    try: sh = gc.open(NOM_DU_FICHIER_SHEET)
    except: st.error(f"❌ Impossible d'ouvrir '{NOM_DU_FICHIER_SHEET}'."); st.stop()
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    try: ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except: ws_ref = None
except Exception as e: st.error(f"❌ Erreur connexion : {e}"); st.stop()

# --- INTERFACE ---
st.set_page_config(page_title="Albion Manager", page_icon="💰", layout="wide")
st.title("🏹 Albion Economy Manager (EU)")
tab1, tab2, tab3 = st.tabs(["✍️ Saisie", "📊 Analyse", "🔍 Détection Doublons"])

# --- TAB 1 : SAISIE ---
with tab1:
    st.subheader("Nouvelle Opération")
    with st.form("ajout"):
        c1, c2 = st.columns(2)
        with c1: type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
        with c2: batiment = st.selectbox("Plot", ["Cook", "Hunter", "Weaver", "Mage", "Autre"])
        montant = st.number_input("Montant", step=10000, format="%d")
        note = st.text_input("Note")
        if st.form_submit_button("Valider"):
            try:
                worksheet.append_row([datetime.now().strftime("%d/%m"), batiment, type_op, montant, note])
                st.success("✅ Enregistré"); st.cache_data.clear()
            except Exception as e: st.error(str(e))

# --- TAB 2 : ANALYSE ---
with tab2:
    st.subheader("Tableau de bord")
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            df['Reel'] = df.apply(lambda x: -x['Montant'] if "Dépense" in str(x['Type']) else x['Montant'], axis=1)
            total = df['Reel'].sum()
            st.metric("💰 Trésorerie", f"{format_monetaire(total)}", delta=f"{total:,.0f}")
            st.dataframe(df.tail(10), use_container_width=True)
    except: st.warning("Pas de données.")

# --- TAB 3 : SCAN JOUEURS & DOUBLONS ---
with tab3:
    st.subheader("🕵️ Scan des Joueurs & Détection des Doublons")
    st.info("💡 Ce scan vérifie si les joueurs listés individuellement ('Player:...') sont déjà couverts par une Guilde ou une Alliance présente dans la liste.")
    
    col_input, col_action = st.columns([2, 1])
    with col_input:
        if 'json_input' not in st.session_state: st.session_state['json_input'] = ""
        raw_text = st.text_area("Colle les permissions ici", value=st.session_state['json_input'], height=150)
    with col_action:
        st.write("### Actions")
        scan_btn = st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True)
        save_ref_btn = st.button("💾 Sauvegarder Réf.", use_container_width=True)

    if 'data_display' not in st.session_state:
        st.session_state['data_display'] = None
        if ws_ref:
            try:
                ref_data = ws_ref.get_all_records()
                if ref_data: st.session_state['data_display'] = pd.DataFrame(ref_data)
            except: pass

    if scan_btn and raw_text:
        # 1. Mise en mémoire des Groupes (Guildes/Alliances) présents dans le texte
        # On stocke en minuscule pour comparer sans souci
        memoire_guildes_input = set(g.strip().lower() for g in re.findall(r'"Guild:([^"]+)"', raw_text))
        memoire_alliances_input = set(a.strip().lower() for a in re.findall(r'"Alliance:([^"]+)"', raw_text))
        
        raw_players = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))

        if memoire_guildes_input or memoire_alliances_input:
            st.toast(f"ℹ️ Comparaison avec : {len(memoire_guildes_input)} Guildes et {len(memoire_alliances_input)} Alliances trouvées dans le texte.")
        
        if not raw_players:
            st.warning("Aucun joueur trouvé.")
        else:
            resultats = []
            barre = st.progress(0)
            status = st.empty()
            
            for i, p_name in enumerate(raw_players):
                status.text(f"Analyse : {p_name}...")
                
                # Appel API
                infos = get_player_stats(p_name)
                
                # LOGIQUE DE DÉTECTION DE DOUBLON
                status_doublon = "✅ Unique" # Par défaut
                detail_doublon = ""

                if infos['Trouve']:
                    g_api = infos['Guilde'].lower()
                    a_api = infos['Alliance'].lower()
                    
                    # Est-ce que la guilde du joueur est dans le texte collé ?
                    if g_api in memoire_guildes_input:
                        status_doublon = "⚠️ Doublon (Guilde)"
                        detail_doublon = f"Déjà inclus via guilde '{infos['Guilde']}'"
                    
                    # Est-ce que l'alliance du joueur est dans le texte collé ?
                    elif a_api in memoire_alliances_input:
                        status_doublon = "⚠️ Doublon (Alliance)"
                        detail_doublon = f"Déjà inclus via alliance '{infos['Alliance']}'"

                infos['Analyse'] = status_doublon
                infos['Détail'] = detail_doublon
                
                resultats.append(infos)
                time.sleep(0.12)
                barre.progress((i+1)/len(raw_players))

            barre.empty()
            status.success(f"Terminé !")

            df_res = pd.DataFrame(resultats)
            
            # --- CALCUL PROGRESSION ---
            if ws_ref:
                try:
                    ref_d = ws_ref.get_all_records()
                    if ref_d:
                        df_ref = pd.DataFrame(ref_d)
                        if 'Pseudo' in df_ref.columns and 'Craft Fame' in df_ref.columns:
                            df_ref = df_ref[['Pseudo', 'Craft Fame']].rename(columns={'Craft Fame': 'Ref Fame'})
                            df_ref['Ref Fame'] = pd.to_numeric(df_ref['Ref Fame'], errors='coerce').fillna(0)
                            df_res = pd.merge(df_res, df_ref, on='Pseudo', how='left')
                            df_res['Progression_Value'] = df_res['Craft Fame'] - df_res['Ref Fame'].fillna(0)
                            df_res['Progression'] = df_res.apply(lambda x: x['Progression_Value'] if x['Ref Fame'] > 0 else "✨ Nouveau", axis=1)
                            df_res['% Évol.'] = df_res.apply(lambda x: f"{(x['Progression_Value']/x['Ref Fame'])*100:.1f}%" if x['Ref Fame'] > 0 else "-", axis=1)
                except: pass

            if 'Progression' not in df_res.columns: df_res['Progression'] = "✨ Nouveau"; df_res['% Évol.'] = "-"

            # --- AVIS ---
            df_res['Avis'] = df_res['Craft Fame'].apply(lambda x: "🟢 Productif" if x > SEUIL_FAME_MIN else "🔴 Faible")

            st.session_state['data_display'] = df_res
            st.session_state['display_type'] = "Analyse Doublons"

    # SAUVEGARDE
    if save_ref_btn and st.session_state['data_display'] is not None:
        try:
            df_s = st.session_state['data_display'][['Pseudo', 'Craft Fame']]
            ws_ref.clear(); ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
            st.success("✅ Référence mise à jour !")
        except Exception as e: st.error(f"Erreur: {e}")

    # AFFICHAGE
    if st.session_state['data_display'] is not None:
        df_show = st.session_state['data_display'].copy()
        
        # Filtres
        c_search, c_filter = st.columns(2)
        with c_search: search = st.text_input("🔎 Filtrer", "")
        with c_filter: show_only_dup = st.checkbox("Montrer uniquement les Doublons", False)

        if search: 
            df_show = df_show[df_show['Pseudo'].str.contains(search, case=False) | df_show['Guilde'].str.contains(search, case=False)]
        
        if show_only_dup:
             df_show = df_show[df_show['Analyse'].str.contains("Doublon")]

        cols_conf = {
            "Craft Fame": st.column_config.NumberColumn("Fame Totale", format="%d"),
            "Progression": st.column_config.TextColumn("Progression"),
            "Guilde": st.column_config.TextColumn("Guilde"),
            "Alliance": st.column_config.TextColumn("Alliance"),
            "Analyse": st.column_config.TextColumn("État Liste"),
            "Détail": st.column_config.TextColumn("Raison")
        }
        final_cols = ['Pseudo', 'Avis', 'Craft Fame', 'Progression', '% Évol.', 'Guilde', 'Analyse', 'Détail']
        st.dataframe(df_show[[c for c in final_cols if c in df_show.columns]], column_config=cols_conf, use_container_width=True)