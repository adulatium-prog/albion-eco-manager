import streamlit as st
import gspread
import pandas as pd
import requests
import time
import json
import re
from datetime import datetime
from collections import Counter

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

# --- FONCTION INTELLIGENTE (EXTRACTION) ---
def extraire_noms_et_tags(liste_brute):
    """
    Sépare les Noms et les Tags pour que le croisement fonctionne dans tous les cas.
    Exemple entrée : ["Dog Walkers [WALKR]"]
    Sortie mémoire : {"dog walkers [walkr]", "dog walkers", "walkr"}
    """
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
    """ Récupère les stats et les infos d'affiliation (Guilde + Alliance) """
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url_search, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            
            target = None
            for p in players:
                if p['Name'].lower() == pseudo.lower():
                    target = p
                    break
            if not target and players: target = players[0]
            
            if target:
                player_id = target['Id']
                
                # Infos préliminaires
                guild_name = target.get('GuildName') or "Aucune"
                alliance_name = target.get('AllianceName') or "-"
                alliance_tag = target.get('AllianceTag') or ""

                # Appel détail
                url_stats = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}"
                resp_stats = requests.get(url_stats, headers=headers)
                craft_fame = 0
                
                if resp_stats.status_code == 200:
                    info = resp_stats.json()
                    
                    if info.get('AllianceName'): alliance_name = info.get('AllianceName')
                    if info.get('AllianceTag'): alliance_tag = info.get('AllianceTag')
                    
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
                    "AllianceTag": alliance_tag,
                    "Craft Fame": craft_fame, 
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

# --- INTERFACE ---
st.set_page_config(page_title="Albion Manager", page_icon="💰", layout="wide")
st.title("🏹 Albion Economy Manager (EU)")

tab1, tab2, tab3 = st.tabs(["✍️ Saisie", "📊 Analyse", "🚀 Arion Scanner"])

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

# --- TAB 3 : ARION SCANNER ---
with tab3:
    st.subheader("🚀 Arion Scanner")
    st.info("💡 Colle les permissions. Le scanner détecte les doublons ET suggère les regroupements pertinents (si plusieurs guildes d'une même alliance sont trouvées).")
    
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
        # 1. Analyse Input
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
            status = st.empty()
            
            # Pour l'intelligence de groupe
            groupe_stats = {} # Clé = Nom Alliance, Valeur = Set de guildes
            
            for i, p_name in enumerate(raw_players):
                status.text(f"Analyse : {p_name}...")
                infos = get_player_stats(p_name)
                
                status_doublon = "✅ Unique"
                detail_doublon = ""

                if infos['Trouve']:
                    # Données en minuscule
                    g_api = infos['Guilde'].lower()
                    a_name_api = infos['Alliance'].lower()
                    a_tag_api = infos['AllianceTag'].lower()
                    
                    # 1. Check Doublons (Liste Input)
                    if g_api in memoire_guildes:
                        status_doublon = "⚠️ Doublon (Guilde)"
                        detail_doublon = f"Déjà inclus via Guilde"
                    elif (a_name_api != "-" and a_name_api in memoire_alliances) or \
                         (a_tag_api != "" and a_tag_api in memoire_alliances):
                        status_doublon = "⚠️ Doublon (Alliance)"
                        detail_doublon = f"Déjà inclus via Alliance"

                    # 2. Collecte pour Intelligence de Groupe
                    if infos['Alliance'] != "-":
                        nom_alli_propre = infos['Alliance']
                        if infos['AllianceTag']: nom_alli_propre += f" [{infos['AllianceTag']}]"
                        
                        if nom_alli_propre not in groupe_stats:
                            groupe_stats[nom_alli_propre] = set()
                        groupe_stats[nom_alli_propre].add(infos['Guilde'])

                infos['Analyse'] = status_doublon
                infos['Détail'] = detail_doublon
                
                # Affichage propre
                if infos['AllianceTag'] and infos['AllianceTag'].lower() not in infos['Alliance'].lower():
                    infos['Alliance_Display'] = f"{infos['Alliance']} [{infos['AllianceTag']}]"
                else:
                    infos['Alliance_Display'] = infos['Alliance']

                resultats.append(infos)
                time.sleep(0.12)
                barre.progress((i+1)/len(raw_players))

            barre.empty()
            status.success(f"Scan terminé !")

            # --- INTELLIGENCE DE GROUPE (FILTRÉE) ---
            regroupements_possibles = []
            for alliance, guildes in groupe_stats.items():
                
                # Vérif si déjà couvert
                alliance_clean = alliance.split(" [")[0].lower()
                tag_clean = ""
                if "[" in alliance: tag_clean = alliance.split("[")[1].replace("]", "").lower()
                
                is_already_covered = (alliance_clean in memoire_alliances) or (tag_clean in memoire_alliances and tag_clean != "")
                
                # LA MODIF EST ICI : len(guildes) > 1 
                # On ne propose QUE si il y a plus d'une guilde différente
                if not is_already_covered and len(guildes) > 1:
                     nb_joueurs = sum(1 for r in resultats if r.get('Alliance_Display') == alliance)
                     regroupements_possibles.append({
                         "Alliance": alliance,
                         "Nb_Guildes": len(guildes),
                         "Guildes": ", ".join(list(guildes)),
                         "Nb_Joueurs": nb_joueurs
                     })

            if regroupements_possibles:
                st.info(f"📢 **{len(regroupements_possibles)} Regroupements Suggérés :** Ces alliances contiennent plusieurs guildes distinctes. Vous devriez les ajouter à votre liste.")
                cols_sugg = st.columns(len(regroupements_possibles)) if len(regroupements_possibles) < 4 else st.columns(3)
                
                for idx, item in enumerate(regroupements_possibles):
                    with cols_sugg[idx % 3]:
                        st.markdown(f"""
                        **🛡️ {item['Alliance']}**
                        * {item['Nb_Joueurs']} joueurs concernés
                        * **{item['Nb_Guildes']} Guildes :** {item['Guildes']}
                        """)
            else:
                # Optionnel : petit message si rien à regrouper mais que le scan a marché
                if resultats:
                    st.caption("✅ Aucun regroupement multi-guildes évident détecté.")

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

            df_res['Avis'] = df_res['Craft Fame'].apply(lambda x: "🟢 Productif" if x > SEUIL_FAME_MIN else "🔴 Faible")
            st.session_state['data_display'] = df_res

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
        
        c_search, c_filter = st.columns(2)
        with c_search: search = st.text_input("🔎 Filtrer", "")
        with c_filter: show_only_dup = st.checkbox("Montrer uniquement les Doublons", False)

        if search: df_show = df_show[df_show['Pseudo'].str.contains(search, case=False) | df_show['Guilde'].str.contains(search, case=False)]
        if show_only_dup: df_show = df_show[df_show['Analyse'].str.contains("Doublon")]

        cols_conf = {
            "Craft Fame": st.column_config.NumberColumn("Fame Totale", format="%d"),
            "Alliance_Display": st.column_config.TextColumn("Alliance"),
            "Analyse": st.column_config.TextColumn("État Liste"),
            "Détail": st.column_config.TextColumn("Raison")
        }
        final_cols = ['Pseudo', 'Avis', 'Craft Fame', 'Progression', '% Évol.', 'Guilde', 'Alliance_Display', 'Analyse', 'Détail']
        st.dataframe(df_show[[c for c in final_cols if c in df_show.columns]], column_config=cols_conf, use_container_width=True)