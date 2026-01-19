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

# Injection du CSS (Style "Silver" + Fond Dégradé + Boutons Arrondis + NOUVELLES CARTES)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');

    /* --- 1. FOND D'ÉCRAN --- */
    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

    /* --- 2. BOUTONS ARRONDIS --- */
    .stButton > button {
        background: linear-gradient(180deg, #d35400, #a04000);
        color: white;
        border: 1px solid #e67e22;
        border-radius: 20px;
        font-family: 'Cinzel', serif;
        font-weight: bold;
        text-transform: uppercase;
        padding: 10px 24px;
        transition: all 0.2s;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stButton > button:hover {
        background: linear-gradient(180deg, #e67e22, #d35400);
        transform: scale(1.05);
        box-shadow: 0 0 15px rgba(211, 84, 0, 0.6);
    }

    /* --- 3. TYPOGRAPHIE --- */
    h1, h2, h3, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        font-weight: 700;
    }

    /* --- ELEMENTS D'INTERFACE --- */
    .stTextInput > div > div > input, .stNumberInput > div > div > input, .stSelectbox > div > div > div {
        background-color: rgba(255, 255, 255, 0.05);
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 10px;
    }
    
    /* --- ONGLETS (TABS) --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: rgba(0, 0, 0, 0.2);
        padding: 10px;
        border-radius: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: transparent;
        color: #bdc3c7;
        font-family: 'Cinzel', serif;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 255, 255, 0.1);
        color: #ffffff;
        border-radius: 10px;
        font-weight: bold;
    }

    /* --- CONTAINERS & BOITES --- */
    [data-testid="stExpander"], [data-testid="stForm"], [data-testid="stMetricValue"] {
        background-color: rgba(0, 0, 0, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
    }
    
    /* --- CUSTOM METRIC (TRÉSORERIE) --- */
    .albion-metric-box {
        background: rgba(0, 0, 0, 0.3);
        padding: 20px;
        border-radius: 20px;
        border: 1px solid rgba(236, 240, 241, 0.3);
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-label {
        color: #bdc3c7;
        font-family: 'Cinzel', serif;
        font-size: 1.2em;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .metric-value {
        font-family: 'Cinzel', serif;
        font-size: 3.5em;
        font-weight: bold;
        text-shadow: 0 0 20px rgba(255,255,255,0.1);
    }
    
    /* --- NOUVEAU : CARTES PLOTS / ACTIVITÉS --- */
    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 15px;
        text-align: center;
        transition: transform 0.2s;
        margin-bottom: 10px;
    }
    .plot-card:hover {
        border-color: #f39c12; /* Bordure dorée au survol */
        transform: translateY(-5px);
        background: rgba(255,255,255,0.08);
    }
    .plot-icon { font-size: 2em; margin-bottom: 5px; display: block;}
    .plot-title {
        font-family: 'Cinzel', serif;
        color: #f39c12;
        font-size: 0.85em;
        text-transform: uppercase;
        font-weight: bold;
    }
    .plot-value {
        font-family: 'Roboto', sans-serif;
        font-size: 1.1em;
        font-weight: 700;
        margin-top: 5px;
    }

    /* Couleurs conditionnelles */
    .val-pos { color: #2ecc71; text-shadow: 0 0 15px rgba(46, 204, 113, 0.4); } 
    .val-neg { color: #ff6b6b; text-shadow: 0 0 15px rgba(255, 107, 107, 0.5); } 

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

# --- API ALBION ---
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
st.markdown("<h1>⚔️ Albion Economy Manager <span style='font-size:0.5em; color:#bdc3c7'>EU SERVER</span></h1>", unsafe_allow_html=True)

# Utilisation de conteneurs pour structurer les onglets
with st.container():
    tab1, tab2, tab3 = st.tabs(["📜 Journal des Comptes", "⚖️ Trésorerie", "🔮 Scanner Arion"])

# --- TAB 1 : SAISIE ---
with tab1:
    with st.container():
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("ajout", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1: type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
            with c2: batiment = st.selectbox("Plot / Activité", ["Cook", "Hunter", "Weaver", "Mage", "Taxe Guilde", "Autre"])
            
            montant = st.number_input("Montant (Silver)", step=10000, format="%d")
            note = st.text_input("Description (Optionnel)")
            
            submitted = st.form_submit_button("Valider (Signer)", use_container_width=True)
            if submitted:
                try:
                    worksheet.append_row([datetime.now().strftime("%d/%m"), batiment, type_op, montant, note])
                    st.toast(f"Transaction de {format_monetaire(montant)} Silver enregistrée !", icon="📜")
                    st.cache_data.clear()
                except Exception as e: st.error(str(e))

# --- TAB 2 : ANALYSE (MISE A JOUR) ---
with tab2:
    st.markdown("<h3 class='albion-font'>État des Finances</h3>", unsafe_allow_html=True)
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            # Calcul du Montant Réel (Positif ou Négatif)
            df['Reel'] = df.apply(lambda x: -x['Montant'] if "Dépense" in str(x['Type']) else x['Montant'], axis=1)
            total = df['Reel'].sum()
            
            # --- 1. GLOBAL ---
            css_class = "val-pos" if total >= 0 else "val-neg"
            st.markdown(f"""
            <div class="albion-metric-box">
                <div class="metric-label">TRÉSORERIE TOTALE</div>
                <div class="metric-value {css_class}">{format_monetaire(total)} <span style="font-size:0.4em; vertical-align:middle; color:#bdc3c7;">Silver</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            if total < 0:
                st.warning("⚠️ Attention : Votre solde est négatif (Dette).")

            st.divider()

            # --- 2. DÉTAIL PAR PLOT (Weaver, Mage, Hunter, Cook...) ---
            st.markdown("<h4 class='albion-font'>Rentabilité par Activité</h4>", unsafe_allow_html=True)

            # Configuration des cibles à afficher
            targets = {
                "Weaver": "🧵",
                "Mage": "🔮",
                "Hunter": "🏹",
                "Cook": "🍖",
                "Taxe Guilde": "🏰"
            }

            # Groupement par 'Plot / Activité' et somme de 'Reel'
            stats_plots = df.groupby('Plot / Activité')['Reel'].sum()

            # Affichage en colonnes dynamiques
            cols = st.columns(len(targets))
            
            for idx, (plot_name, icon) in enumerate(targets.items()):
                valeur = stats_plots.get(plot_name, 0) # 0 si aucune transaction trouvée pour ce plot
                color_class = "val-pos" if valeur >= 0 else "val-neg"
                
                with cols[idx]:
                    st.markdown(f"""
                    <div class="plot-card">
                        <span class="plot-icon">{icon}</span>
                        <div class="plot-title">{plot_name}</div>
                        <div class="plot-value {color_class}">{format_nombre_entier(valeur)}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # --- 3. HISTORIQUE ---
            st.divider()
            st.markdown("<h4 class='albion-font'>Historique Récent</h4>", unsafe_allow_html=True)
            
            # Copie pour affichage propre (sans la colonne 'Reel' visible)
            df_display = df.tail(10).sort_index(ascending=False).copy()
            df_display = df_display[['Date', 'Plot / Activité', 'Type', 'Montant', 'Note']]
            
            st.dataframe(
                df_display, 
                use_container_width=True,
                column_config={
                    "Montant": st.column_config.NumberColumn(format="%d 💰")
                }
            )

    except Exception as e: 
        st.warning("Le livre de comptes est vide ou inaccessible.")
        # st.error(f"Debug: {e}")

# --- TAB 3 : ARION SCANNER ---
with tab3:
    with st.container():
        st.markdown("<h3 class='albion-font'>Scanner de Guildes</h3>", unsafe_allow_html=True)
        st.info("Collez vos permissions ci-dessous. Le système détectera les doublons pour optimiser vos listes d'accès.")
        
        col_input, col_action = st.columns([3, 1], gap="medium")
        with col_input:
            if 'json_input' not in st.session_state: st.session_state['json_input'] = ""
            raw_text = st.text_area("Permissions JSON/Texte", value=st.session_state['json_input'], height=200, placeholder="{ Player:Pseudo... Guild:Nom... }")
        with col_action:
            st.write("### Actions")
            scan_btn = st.button("Lancer l'Analyse", type="primary", use_container_width=True)
            st.write("")
            save_ref_btn = st.button("Sauvegarder", help="Met à jour la base de référence", use_container_width=True)

    if 'data_display' not in st.session_state:
        st.session_state['data_display'] = None
        if ws_ref:
            try:
                ref_data = ws_ref.get_all_records()
                if ref_data: st.session_state['data_display'] = pd.DataFrame(ref_data)
            except: pass

    if scan_btn and raw_text:
        # --- LOGIQUE SCAN ---
        with st.spinner("Consultation des archives Albion..."):
            guildes_brutes = re.findall(r'"Guild:([^"]+)"', raw_text)
            alliances_brutes = re.findall(r'"Alliance:([^"]+)"', raw_text)
            
            memoire_guildes = extraire_noms_et_tags(guildes_brutes)
            memoire_alliances = extraire_noms_et_tags(alliances_brutes)
            
            raw_players = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))

            if not raw_players:
                st.warning("Aucun joueur trouvé dans le texte.")
            else:
                resultats = []
                barre = st.progress(0)
                groupe_stats = {} 
                
                for i, p_name in enumerate(raw_players):
                    infos = get_player_stats(p_name)
                    status_doublon = "✅ Unique"
                    detail_doublon = ""

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
                        
                        if g_api in memoire_guildes:
                            status_doublon = "⚠️ Doublon (Guilde)"
                            detail_doublon = f"Déjà inclus via Guilde"
                        elif (a_name_api != "-" and a_name_api in memoire_alliances) or \
                             (a_tag_api != "" and a_tag_api in memoire_alliances):
                            status_doublon = "⚠️ Doublon (Alliance)"
                            detail_doublon = f"Déjà inclus via Alliance"

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
                st.toast("Scan terminé !", icon="✅")

                joueurs_doublons = [r['Pseudo'] for r in resultats if "Doublon" in r.get('Analyse', '')]
                
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

                st.divider()
                col_left, col_right = st.columns(2, gap="large")

                with col_left:
                    with st.container():
                        st.markdown("<h4 class='albion-font'>📢 Suggestions de Regroupement</h4>", unsafe_allow_html=True)
                        if regroupements_possibles:
                            for item in regroupements_possibles:
                                with st.expander(f"🛡️ {item['Alliance']} ({item['Nb_Joueurs']} joueurs)"):
                                    st.caption(f"Guildes : {item['Guildes']}")
                                    st.code(", ".join(item['Liste_Joueurs']), language="text")
                        else:
                            st.caption("Aucun regroupement évident.")

                with col_right:
                    with st.container():
                        st.markdown("<h4 class='albion-font'>🗑️ Joueurs Inutiles (Doublons)</h4>", unsafe_allow_html=True)
                        if joueurs_doublons:
                             with st.expander(f"⚠️ {len(joueurs_doublons)} pseudos à retirer"):
                                st.code(", ".join(joueurs_doublons), language="text")
                        else:
                            st.caption("Aucun doublon détecté.")

                st.divider()
                st.markdown("<h4 class='albion-font'>Détails Complets</h4>", unsafe_allow_html=True)
                df_res = pd.DataFrame(resultats)
                
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

    if save_ref_btn and st.session_state['data_display'] is not None:
        try:
            df_s = st.session_state['data_display'][['Pseudo', 'Craft Fame']]
            ws_ref.clear(); ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
            st.toast("Base de référence mise à jour !", icon="💾")
        except Exception as e: st.error(f"Erreur: {e}")

    if st.session_state['data_display'] is not None:
        df_show = st.session_state['data_display'].copy()
        if 'Craft Fame' in df_show.columns:
            df_show['Craft Fame'] = df_show['Craft Fame'].apply(format_nombre_entier)
        
        c_search, c_filter = st.columns(2)
        with c_search: search = st.text_input("Recherche", placeholder="Nom ou Guilde...")
        with c_filter: show_only_dup = st.checkbox("Montrer uniquement les doublons", False)

        if search: df_show = df_show[df_show['Pseudo'].str.contains(search, case=False) | df_show['Guilde'].str.contains(search, case=False)]
        if show_only_dup: df_show = df_show[df_show['Analyse'].str.contains("Doublon")]

        cols_conf = {
            "Craft Fame": st.column_config.TextColumn("Fame"), 
            "Alliance_Display": st.column_config.TextColumn("Alliance"),
            "Analyse": st.column_config.TextColumn("Statut"),
            "Détail": st.column_config.TextColumn("Info")
        }
        final_cols = ['Pseudo', 'Avis', 'Craft Fame', 'Progression', '% Évol.', 'Guilde', 'Alliance_Display', 'Analyse', 'Détail']
        st.dataframe(df_show[[c for c in final_cols if c in df_show.columns]], column_config=cols_conf, use_container_width=True, height=500)