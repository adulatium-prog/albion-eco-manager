import streamlit as st
import gspread
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import time
import json
from datetime import datetime

# --- SÉCURITÉ : MOT DE PASSE ---
# On vérifie si un mot de passe est défini dans les secrets
if "app_password" in st.secrets:
    mot_de_passe_secret = st.secrets["app_password"]
    
    # On affiche une barre latérale pour se connecter
    input_password = st.sidebar.text_input("🔒 Mot de passe", type="password")
    
    if input_password != mot_de_passe_secret:
        st.sidebar.warning("Saisis le mot de passe pour accéder à l'outil.")
        st.stop()  # <--- C'est ici que ça bloque tout le reste si le MDP est faux

# --- CONFIGURATION ---
# Mets le nom de ton vrai fichier ici
NOM_DU_FICHIER_SHEET = "Test Albion" 
# Mets le nom de l'onglet où tout est stocké
NOM_ONGLET = "Journal_App" 

# --- FONCTION API (SCANNER) ---
def get_albion_stats(pseudo):
    try:
        url_search = f"https://gameinfo.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0'} 
        resp = requests.get(url_search, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            target = next((p for p in players if p['Name'].lower() == pseudo.lower()), None)
            
            if target:
                player_id = target['Id']
                guild = target.get('GuildName', '')
                
                # 2ème requête pour la Fame Craft
                url_stats = f"https://gameinfo.albiononline.com/api/gameinfo/players/{player_id}"
                resp_stats = requests.get(url_stats, headers=headers)
                craft_fame = 0
                if resp_stats.status_code == 200:
                    stats_data = resp_stats.json()
                    craft_fame = stats_data.get('LifetimeStatistics', {}).get('Crafting', {}).get('Total', 0)
                
                return {
                    "Pseudo": target['Name'],
                    "Guilde": guild,
                    "Craft Fame": craft_fame,
                    "Statut": "✅ OK"
                }
            else:
                return {"Pseudo": pseudo, "Statut": "❌ Introuvable", "Craft Fame": 0}
        else:
            return {"Pseudo": pseudo, "Statut": "⚠️ Erreur API", "Craft Fame": 0}
    except Exception as e:
        return {"Pseudo": pseudo, "Statut": "Erreur", "Craft Fame": 0}

# --- CONNEXION (HYBRIDE PC/CLOUD) ---
try:
    # 1. Si on est sur le Cloud (Streamlit)
    if "gcp_service_account" in st.secrets:
        # On récupère le contenu brut (texte)
        secret_content = st.secrets["gcp_service_account"]
        # On le transforme de JSON (texte) vers Dictionnaire (Python)
        dict_secrets = json.loads(secret_content)
        gc = gspread.service_account_from_dict(dict_secrets)
        
    # 2. Si on est sur ton PC (Local)
    else:
        gc = gspread.service_account(filename='service_account.json')
        
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET)

except Exception as e:
    st.error(f"❌ Erreur de connexion : {e}")
    st.stop()
# --- INTERFACE ---
st.set_page_config(page_title="Albion Manager", page_icon="💰", layout="wide")
st.title("🏹 Albion Economy Manager")

tab1, tab2, tab3 = st.tabs(["✍️ Saisie", "📊 Analyse", "🔍 Scanner Droits"])

# --- TAB 1 : SAISIE ---
with tab1:
    st.subheader("Nouvelle Opération")
    with st.form("ajout"):
        c1, c2 = st.columns(2)
        with c1:
            type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
        with c2:
            plots = ["Cook", "Hunter", "Weaver", "Mage", "Autre"]
            batiment = st.selectbox("Plot", plots)
        
        montant = st.number_input("Montant", step=10000)
        note = st.text_input("Note")
        
        if st.form_submit_button("Valider"):
            final = montant if type_op == "Recette (+)" else -montant
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            try:
                worksheet.append_row([date, batiment, type_op, final, note])
                st.success("✅ Enregistré !")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Erreur : {e}")

# --- TAB 2 : ANALYSE ---
with tab2:
    st.subheader("Tableau de bord")
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if 'Montant' in df.columns:
                st.metric("💰 Trésorerie Totale", f"{df['Montant'].sum():,.0f} Silver")
            
            st.write("---")
            if 'Date' in df.columns and 'Montant' in df.columns:
                st.caption("Évolution de la fortune")
                df_c = df.copy()
                df_c['Date'] = pd.to_datetime(df_c['Date'], errors='coerce')
                df_c = df_c.dropna(subset=['Date']).sort_values('Date')
                df_c['Cumul'] = df_c['Montant'].cumsum()
                
                if not df_c.empty:
                    fig, ax = plt.subplots(figsize=(10, 3))
                    ax.plot(df_c['Date'], df_c['Cumul'], color='#00CC96', marker='o')
                    ax.grid(True, alpha=0.3)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                    st.pyplot(fig)
            
            st.dataframe(df.tail(10).sort_index(ascending=False), use_container_width=True)
    except Exception as e:
        st.warning(f"Chargement... ({e})")

# --- TAB 3 : SCANNER JSON ---
with tab3:
    st.subheader("🕵️ Scanner droits d'accès")
    st.caption("Colle le code JSON des droits d'accès (celui avec les accolades { }).")
    
    col_input, col_result = st.columns([1, 2])
    
    with col_input:
        raw_text = st.text_area("Colle le texte ici", height=200)
        bouton_scan = st.button("Lancer le scan")

    if bouton_scan and raw_text:
        pseudos_a_scanner = []
        
        # 1. ANALYSE DU TEXTE
        try:
            data_json = json.loads(raw_text)
            for key in data_json.keys():
                if key.startswith("Player:"):
                    nom = key.split(":", 1)[1]
                    pseudos_a_scanner.append(nom)
            
            st.success(f"{len(pseudos_a_scanner)} joueurs trouvés. Scan en cours...")
        except:
            st.error("Format invalide. Colle bien tout le texte JSON.")
            st.stop()
            
        # 2. SCAN API
        resultats = []
        barre = st.progress(0)
        
        for i, pseudo in enumerate(pseudos_a_scanner):
            info = get_albion_stats(pseudo)
            resultats.append(info)
            time.sleep(0.1) 
            barre.progress((i + 1) / len(pseudos_a_scanner))
        
        barre.empty()
        
        # 3. RÉSULTAT
        with col_result:
            df_res = pd.DataFrame(resultats)
            st.dataframe(
                df_res, 
                column_config={"Craft Fame": st.column_config.NumberColumn(format="%d")},
                use_container_width=True
            )