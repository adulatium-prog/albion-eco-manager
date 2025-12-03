import streamlit as st
import gspread
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import time
import json
import re
from datetime import datetime

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

# --- FONCTIONS FORMATAGE ---
def format_monetaire(valeur):
    try: return "{:,.2f}".format(float(valeur)).replace(",", " ").replace(".", ",")
    except: return str(valeur)

def format_nombre_entier(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

# --- API ALBION ---
def get_albion_stats(pseudo):
    try:
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
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
                guild = target.get('GuildName') or "Aucune"
                
                url_stats = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}"
                resp_stats = requests.get(url_stats, headers=headers)
                
                craft_fame = 0
                if resp_stats.status_code == 200:
                    info = resp_stats.json()
                    ls = info.get('LifetimeStatistics', {})
                    crafting = ls.get('Crafting', {}) or ls.get('crafting', {})
                    candidates = [
                        info.get('CraftFame'), info.get('CraftingFame'),
                        crafting.get('CraftFame'), crafting.get('Total'), crafting.get('craftFame')
                    ]
                    for val in candidates:
                        if isinstance(val, (int, float)):
                            craft_fame = val
                            break
                return {"Pseudo": target['Name'], "Guilde": guild, "Craft Fame": craft_fame, "Statut": "✅ OK"}
            else:
                return {"Pseudo": pseudo, "Guilde": "-", "Craft Fame": 0, "Statut": "❌ Introuvable"}
        else:
            return {"Pseudo": pseudo, "Guilde": "-", "Craft Fame": 0, "Statut": "⚠️ Erreur API"}
    except:
        return {"Pseudo": pseudo, "Guilde": "-", "Craft Fame": 0, "Statut": "Erreur Script"}

# --- CONNEXION ---
try:
    if "gcp_service_account" in st.secrets:
        secret_content = st.secrets["gcp_service_account"].strip()
        dict_secrets = json.loads(secret_content)
        gc = gspread.service_account_from_dict(dict_secrets)
    else:
        gc = gspread.service_account(filename='service_account.json')
        
    try: sh = gc.open(NOM_DU_FICHIER_SHEET)
    except: 
        st.error(f"❌ Impossible d'ouvrir '{NOM_DU_FICHIER_SHEET}'. Vérifie le nom.")
        st.stop()

    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    try: ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except: ws_ref = None

except Exception as e:
    st.error(f"❌ Erreur connexion : {e}")
    st.stop()

# --- INTERFACE ---
st.set_page_config(page_title="Albion Manager", page_icon="💰", layout="wide")
st.title("🏹 Albion Economy Manager (EU)")

tab1, tab2, tab3 = st.tabs(["✍️ Saisie", "📊 Analyse", "🔍 Suivi Craft"])

# --- TAB 1 : SAISIE ---
with tab1:
    st.subheader("Nouvelle Opération")
    with st.form("ajout"):
        c1, c2 = st.columns(2)
        with c1: type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
        with c2: 
            plots = ["Cook", "Hunter", "Weaver", "Mage", "Autre"]
            batiment = st.selectbox("Plot", plots)
        montant = st.number_input("Montant", step=10000, format="%d")
        note = st.text_input("Note")
        if st.form_submit_button("Valider"):
            final = montant if type_op == "Recette (+)" else -montant
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            try:
                worksheet.append_row([date, batiment, type_op, final, note])
                st.success(f"✅ Enregistré : {format_monetaire(final)} Silver")
                st.cache_data.clear()
            except Exception as e: st.error(f"Erreur : {e}")

# --- TAB 2 : ANALYSE ---
with tab2:
    st.subheader("Tableau de bord")
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            
            # --- 1. KPI COULEUR ---
            if 'Montant' in df.columns:
                total = df['Montant'].sum()
                # Astuce : On utilise 'delta' pour colorer automatiquement
                # Si positif -> Vert, Si négatif -> Rouge
                st.metric(
                    label="💰 Trésorerie Totale", 
                    value=f"{format_monetaire(total)} Silver",
                    delta=f"{total:,.0f} (Global)" # Le delta colore le chiffre
                )

            st.write("---")
            
            # --- 2. GRAPHIQUE INTELLIGENT ---
            if 'Date' in df.columns and 'Montant' in df.columns:
                df_c = df.copy()
                df_c['Date'] = pd.to_datetime(df_c['Date'], errors='coerce')
                df_c = df_c.dropna(subset=['Date']).sort_values('Date')
                df_c['Cumul'] = df_c['Montant'].cumsum()
                
                if not df_c.empty:
                    st.caption("Évolution de la fortune")
                    fig, ax = plt.subplots(figsize=(10, 3))
                    
                    # DÉTERMINATION DE LA COULEUR
                    dernier_montant = df_c['Cumul'].iloc[-1]
                    # Si on est positif = Vert (#00CC96), sinon Rouge (#FF4B4B)
                    couleur_ligne = '#00CC96' if dernier_montant >= 0 else '#FF4B4B'
                    
                    # Tracer la ligne 0 (Repère visuel)
                    ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)
                    
                    # Tracer la courbe avec la bonne couleur
                    ax.plot(df_c['Date'], df_c['Cumul'], color=couleur_ligne, marker='o')
                    
                    ax.grid(True, alpha=0.3)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                    
                    # On évite la notation scientifique moche (1e8) sur l'axe Y
                    ax.ticklabel_format(style='plain', axis='y')
                    
                    st.pyplot(fig)
            
            # --- 3. TABLEAU ---
            df_disp = df.copy()
            if 'Montant' in df_disp.columns: df_disp['Montant'] = df_disp['Montant'].apply(format_monetaire)
            st.dataframe(df_disp.tail(10).sort_index(ascending=False), use_container_width=True)
    except Exception as e: st.warning(f"Chargement... {e}")

# --- TAB 3 : SUIVI CRAFT ---
with tab3:
    st.subheader("🕵️ Suivi de Production")
    col_input, col_action = st.columns([2, 1])
    with col_input:
        if 'json_input' not in st.session_state: st.session_state['json_input'] = ""
        raw_text = st.text_area("Colle TOUS les JSON ici", value=st.session_state['json_input'], height=100, key="json_area")
    with col_action:
        st.write("### Actions")
        scan_btn = st.button("🚀 Lancer le Scan", type="primary", use_container_width=True)
        st.write("")
        save_ref_btn = st.button("💾 Sauvegarder comme Réf.", help="Écrase l'onglet Référence", use_container_width=True)

    if 'data_display' not in st.session_state:
        st.session_state['data_display'] = None
        if ws_ref:
            try:
                ref_data = ws_ref.get_all_records()
                if ref_data:
                    df_load = pd.DataFrame(ref_data)
                    if 'Pseudo' in df_load.columns:
                        st.session_state['data_display'] = df_load
                        st.session_state['display_type'] = "Référence"
            except: pass

    if scan_btn and raw_text:
        matches = re.findall(r'"Player:([^"]+)"', raw_text)
        pseudos = list(set(matches))
        if not pseudos: st.warning("Aucun joueur trouvé.")
        else:
            st.info(f"Analyse de {len(pseudos)} joueurs...")
            res = []
            barre = st.progress(0)
            status = st.empty()
            for i, p in enumerate(pseudos):
                status.text(f"Scan de {p}...")
                res.append(get_albion_stats(p))
                time.sleep(0.15)
                barre.progress((i+1)/len(pseudos))
            barre.empty()
            status.empty()
            
            df_res = pd.DataFrame(res)
            
            if ws_ref:
                try:
                    ref_d = ws_ref.get_all_records()
                    if ref_d:
                        df_ref = pd.DataFrame(ref_d)
                        if 'Pseudo' in df_ref.columns and 'Craft Fame' in df_ref.columns:
                            df_ref = df_ref[['Pseudo', 'Craft Fame']].rename(columns={'Craft Fame': 'Ref Fame'})
                            df_ref['Ref Fame'] = pd.to_numeric(df_ref['Ref Fame'], errors='coerce').fillna(0)
                            df_res = pd.merge(df_res, df_ref, on='Pseudo', how='left')
                            df_res['Ref Fame'] = df_res['Ref Fame'].fillna(0)
                            df_res['Progression'] = df_res['Craft Fame'] - df_res['Ref Fame']
                except: pass

            st.session_state['data_display'] = df_res
            st.session_state['display_type'] = "Scan Direct"
            st.success("Terminé !")

    if save_ref_btn:
        if st.session_state['data_display'] is not None and not st.session_state['data_display'].empty:
            if ws_ref:
                try:
                    df_s = st.session_state['data_display']
                    if 'Pseudo' in df_s.columns and 'Craft Fame' in df_s.columns:
                        df_s = df_s[['Pseudo', 'Craft Fame']]
                        ws_ref.clear()
                        ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
                        st.success("✅ Référence sauvegardée !")
                        st.session_state['display_type'] = "Référence"
                except Exception as e: st.error(f"Erreur : {e}")
        else: st.warning("Rien à sauvegarder.")

    st.divider()
    if st.session_state['data_display'] is not None:
        st.caption(f"Affichage : **{st.session_state.get('display_type', '')}**")
        df_show = st.session_state['data_display'].copy()
        
        cols_conf = {
            "Craft Fame": st.column_config.NumberColumn("Fame Totale", format="%d"),
            "Progression": st.column_config.NumberColumn("📈 Progression", format="%+d"),
            "Guilde": st.column_config.TextColumn("Guilde"),
            "Statut": st.column_config.TextColumn("Statut")
        }
        cols_to_show = [c for c in df_show.columns if c not in ['Ref Fame']]
        df_show = df_show[cols_to_show]
        if 'Progression' not in df_show.columns and "Progression" in cols_conf: del cols_conf["Progression"]

        st.dataframe(df_show, column_config=cols_conf, use_container_width=True)
    else: st.info("Aucune donnée.")