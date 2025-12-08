import streamlit as st
import gspread
import pandas as pd
import requests
import time
import json
import re
from datetime import datetime
from collections import Counter

# --- CONFIGURATION DE LA PAGE ET CSS ---
st.set_page_config(page_title="Albion Manager Pro", page_icon="🏰", layout="wide")

# Injection de CSS personnalisé pour le look "Pro"
st.markdown("""
<style>
    /* Fond d'écran en dégradé sombre */
    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #E0E0E0;
    }
    /* Style des boutons plus arrondis */
    .stButton > button {
        border-radius: 20px;
        font-weight: 600;
    }
    /* Style des expanders pour qu'ils ressortent mieux */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
    }
    /* Métriques plus grosses */
    [data-testid="stMetricValue"] {
        font-size: 2.5rem !important;
        color: #00CC96 !important;
    }
</style>
""", unsafe_allow_html=True)


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
    """ Formate 1000000 en '1 000 000' """
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

# --- API ALBION (CRAFTER PRIORITAIRE) ---
def get_player_stats(pseudo):
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url_search, headers=headers)
        
        target = None
        craft_fame_target = -1
        
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            candidats = [p for p in players if p['Name'].lower() == pseudo.lower()]
            
            if not candidats:
                return {"Pseudo": pseudo, "Guilde": "?", "Alliance": "?", "AllianceTag": "", "Craft Fame": 0, "Trouve": False}
            
            meilleur_fame = -1
            infos_meilleur = {}

            for p in candidats[:3]:
                p_id = p['Id']
                url_details = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}"
                try:
                    r_det = requests.get(url_details, headers=headers)
                    if r_det.status_code == 200:
                        d = r_det.json()
                        ls = d.get('LifetimeStatistics', {})
                        crafting = ls.get('Crafting', {}) or ls.get('crafting', {})
                        val_fame = 0
                        candidates_val = [d.get('CraftFame'), crafting.get('Total'), crafting.get('craftFame')]
                        for v in candidates_val:
                            if isinstance(v, (int, float)):
                                val_fame = v
                                break
                        
                        if val_fame > meilleur_fame:
                            meilleur_fame = val_fame
                            infos_meilleur = d
                    time.sleep(0.05)
                except: pass

            if infos_meilleur:
                target = infos_meilleur
                craft_fame_target = meilleur_fame
                
                p_name = target.get('Name')
                g_name = target.get('GuildName') or "Aucune"
                a_name = target.get('AllianceName') or "-"
                a_tag = target.get('AllianceTag') or ""
                
                return {
                    "Pseudo": p_name, 
                    "Guilde": g_name,
                    "Alliance": a_name,
                    "AllianceTag": a_tag,
                    "Craft Fame": craft_fame_target, 
                    "Trouve": True
                }

        return {"Pseudo": pseudo, "Guilde": "?", "Alliance": "?", "AllianceTag": "", "Craft Fame": 0, "Trouve": False}
    except: return {"Pseudo": pseudo, "Guilde": "?", "Alliance": "?", "AllianceTag": "", "Craft Fame": 0, "Trouve": False}

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

# --- INTERFACE PRINCIPALE ---
st.title("🏰 Albion Economy Manager (EU)")

# Utilisation de conteneurs pour structurer les onglets
with st.container():
    tab1, tab2, tab3 = st.tabs(["✍️ Saisie Opérations", "📊 Tableau de Bord", "🚀 Arion Scanner"])

# --- TAB 1 : SAISIE ---
with tab1:
    with st.container(border=True):
        st.subheader("Nouvelle Opération")
        with st.form("ajout", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: type_op = st.radio("Type d'opération", ["Recette (+)", "Dépense (-)"], horizontal=True)
            with c2: batiment = st.selectbox("Plot concerné", ["Cook", "Hunter", "Weaver", "Mage", "Autre"])
            montant = st.number_input("Montant (Silver)", step=10000, format="%d")
            note = st.text_input("Note (Optionnel)")
            
            submitted = st.form_submit_button("✅ Valider l'opération", use_container_width=True)
            if submitted:
                try:
                    worksheet.append_row([datetime.now().strftime("%d/%m"), batiment, type_op, montant, note])
                    st.toast(f"Succès : {format_monetaire(montant)} Silver enregistrés !", icon="🎉")
                    st.cache_data.clear()
                except Exception as e: st.error(str(e))

# --- TAB 2 : ANALYSE ---
with tab2:
    st.subheader("📊 Synthèse Financière")
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            df['Reel'] = df.apply(lambda x: -x['Montant'] if "Dépense" in str(x['Type']) else x['Montant'], axis=1)
            total = df['Reel'].sum()
            
            # Métrique mise en avant
            with st.container(border=True):
                col_metric, col_graph = st.columns([1, 2])
                with col_metric:
                     st.metric("💰 Trésorerie Globale", f"{format_monetaire(total)}", delta="Solde actuel")
                with col_graph:
                    # Placeholder pour un futur graphique si besoin
                    st.caption("Aperçu des dernières transactions ci-dessous.")

            st.divider()
            st.subheader("📜 Dernières Transactions")
            st.dataframe(df.tail(10).sort_index(ascending=False), use_container_width=True)
    except: st.warning("Pas encore de données.")

# --- TAB 3 : ARION SCANNER (LA NOUVELLE INTERFACE) ---
with tab3:
    with st.container(border=True):
        st.subheader("🚀 Arion Scanner")
        st.info("💡 Colle tes permissions. Le scanner identifie les joueurs inutiles (doublons) et suggère des alliances pour simplifier ta liste.")
        
        col_input, col_action = st.columns([3, 1], gap="medium")
        with col_input:
            if 'json_input' not in st.session_state: st.session_state['json_input'] = ""
            raw_text = st.text_area("Colle les permissions ici", value=st.session_state['json_input'], height=200, placeholder="{ Player:V3L0... Guild:Arion... }")
        with col_action:
            st.write("### Contrôles")
            scan_btn = st.button("🕵️‍♂️ Lancer l'Analyse", type="primary", use_container_width=True)
            st.write("")
            save_ref_btn = st.button("💾 Sauvegarder Réf.", help="Met à jour l'onglet de référence", use_container_width=True)

    if 'data_display' not in st.session_state:
        st.session_state['data_display'] = None
        if ws_ref:
            try:
                ref_data = ws_ref.get_all_records()
                if ref_data: st.session_state['data_display'] = pd.DataFrame(ref_data)
            except: pass

    if scan_btn and raw_text:
        # --- LOGIQUE DU SCAN (Inchangée, juste encapsulée) ---
        with st.spinner("Analyse en cours..."):
            guildes_brutes = re.findall(r'"Guild:([^"]+)"', raw_text)
            alliances_brutes = re.findall(r'"Alliance:([^"]+)"', raw_text)
            
            memoire_guildes = extraire_noms_et_tags(guildes_brutes)
            memoire_alliances = extraire_noms_et_tags(alliances_brutes)
            
            raw_players = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))

            if not raw_players:
                st.warning("Aucun joueur trouvé.")
            else:
                resultats = []
                barre = st.progress(0)
                
                # Pour l'intelligence de groupe
                groupe_stats = {} 
                
                for i, p_name in enumerate(raw_players):
                    infos = get_player_stats(p_name)
                    status_doublon = "✅ Unique"
                    detail_doublon = ""

                    # Construction nom alli
                    if infos['Trouve'] and infos['Alliance'] != "-":
                        if infos['AllianceTag'] and infos['AllianceTag'].lower() not in infos['Alliance'].lower():
                            nom_alli_display = f"{infos['Alliance']} [{infos['AllianceTag']}]"
                        else:
                            nom_alli_display = infos['Alliance']
                    else:
                        nom_alli_display = infos['Alliance']
                    infos['Alliance_Display'] = nom_alli_display

                    if infos['Trouve']:
                        g_api = infos['Guilde'].lower()
                        a_name_api = infos['Alliance'].lower()
                        a_tag_api = infos['AllianceTag'].lower()
                        
                        # Check Doublons
                        if g_api in memoire_guildes:
                            status_doublon = "⚠️ Doublon (Guilde)"
                            detail_doublon = f"Déjà inclus via Guilde"
                        elif (a_name_api != "-" and a_name_api in memoire_alliances) or \
                             (a_tag_api != "" and a_tag_api in memoire_alliances):
                            status_doublon = "⚠️ Doublon (Alliance)"
                            detail_doublon = f"Déjà inclus via Alliance"

                        # Collecte Groupe
                        if infos['Alliance'] != "-":
                            if nom_alli_display not in groupe_stats:
                                groupe_stats[nom_alli_display] = set()
                            groupe_stats[nom_alli_display].add(infos['Guilde'])

                    infos['Analyse'] = status_doublon
                    infos['Détail'] = detail_doublon
                    
                    resultats.append(infos)
                    barre.progress((i+1)/len(raw_players))
                    time.sleep(0.05)

                barre.empty()
                st.toast("Scan terminé avec succès !", icon="✅")

                # --- PRÉPARATION DES DONNÉES POUR L'AFFICHAGE ---
                # 1. Doublons
                joueurs_doublons = [r['Pseudo'] for r in resultats if "Doublon" in r.get('Analyse', '')]
                
                # 2. Regroupements
                regroupements_possibles = []
                for alliance, guildes in groupe_stats.items():
                    alliance_clean = alliance.split(" [")[0].lower()
                    tag_clean = ""
                    if "[" in alliance: tag_clean = alliance.split("[")[1].replace("]", "").lower()
                    is_already_covered = (alliance_clean in memoire_alliances) or (tag_clean in memoire_alliances and tag_clean != "")
                    
                    if not is_already_covered and len(guildes) > 1:
                         joueurs_concernes = [r['Pseudo'] for r in resultats if r.get('Alliance_Display') == alliance]
                         regroupements_possibles.append({
                             "Alliance": alliance,
                             "Nb_Guildes": len(guildes),
                             "Guildes": ", ".join(list(guildes)),
                             "Nb_Joueurs": len(joueurs_concernes),
                             "Liste_Joueurs": joueurs_concernes
                         })

                # --- NOUVELLE DISPOSITION EN 2 COLONNES ---
                st.divider()
                col_left, col_right = st.columns(2, gap="large")

                # === COLONNE GAUCHE : À REGROUPER ===
                with col_left:
                    with st.container(border=True):
                        st.subheader("📢 À Regrouper (Simplification)")
                        st.info("Ajoutez ces Alliances à votre liste pour remplacer les joueurs individuels.")
                        
                        if regroupements_possibles:
                            for item in regroupements_possibles:
                                with st.expander(f"🛡️ {item['Alliance']} ({item['Nb_Joueurs']} joueurs)"):
                                    st.caption(f"Guildes concernées : {item['Guildes']}")
                                    st.markdown("Current Players to replace:")
                                    st.code(", ".join(item['Liste_Joueurs']), language="text")
                        else:
                            st.caption("✅ Aucun regroupement multi-guildes évident à suggérer.")

                # === COLONNE DROITE : À SUPPRIMER ===
                with col_right:
                    with st.container(border=True):
                        st.subheader("🗑️ À Supprimer (Nettoyage)")
                        st.warning("Ces joueurs sont déjà couverts par votre liste actuelle. Ils sont inutiles.")
                        
                        if joueurs_doublons:
                             with st.expander(f"⚠️ Voir les {len(joueurs_doublons)} noms à supprimer"):
                                st.write("Copiez cette liste pour les retirer de votre fichier :")
                                st.code(", ".join(joueurs_doublons), language="text")
                        else:
                             st.caption("✨ Votre liste est propre. Aucun doublon détecté.")

                # --- TABLEAU FINAL ---
                st.divider()
                st.subheader("🔍 Détail des Résultats")
                df_res = pd.DataFrame(resultats)
                # (Calcul progression inchangé...)
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
                df_res['Avis'] = df_res['Craft Fame'].apply(lambda x: "🟢 Productif" if x > SEUIL_FAME_MIN else "🔴 Faible")
                st.session_state['data_display'] = df_res

    # SAUVEGARDE
    if save_ref_btn and st.session_state['data_display'] is not None:
        try:
            df_s = st.session_state['data_display'][['Pseudo', 'Craft Fame']]
            ws_ref.clear(); ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
            st.toast("Référence mise à jour !", icon="💾")
        except Exception as e: st.error(f"Erreur: {e}")

    # AFFICHAGE TABLEAU
    if st.session_state['data_display'] is not None:
        df_show = st.session_state['data_display'].copy()
        if 'Craft Fame' in df_show.columns:
            df_show['Craft Fame'] = df_show['Craft Fame'].apply(format_nombre_entier)
        
        with st.container(border=True):
            c_search, c_filter = st.columns(2)
            with c_search: search = st.text_input("🔎 Recherche dans le tableau", placeholder="Pseudo, Guilde...")
            with c_filter: show_only_dup = st.checkbox("Filtre : Montrer uniquement les Doublons", False)

            if search: df_show = df_show[df_show['Pseudo'].str.contains(search, case=False) | df_show['Guilde'].str.contains(search, case=False)]
            if show_only_dup: df_show = df_show[df_show['Analyse'].str.contains("Doublon")]

            cols_conf = {
                "Craft Fame": st.column_config.TextColumn("Fame Totale"), 
                "Alliance_Display": st.column_config.TextColumn("Alliance"),
                "Analyse": st.column_config.TextColumn("État Liste"),
                "Détail": st.column_config.TextColumn("Raison")
            }
            final_cols = ['Pseudo', 'Avis', 'Craft Fame', 'Progression', '% Évol.', 'Guilde', 'Alliance_Display', 'Analyse', 'Détail']
            st.dataframe(df_show[[c for c in final_cols if c in df_show.columns]], column_config=cols_conf, use_container_width=True, height=500)