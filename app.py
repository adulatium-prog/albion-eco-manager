import streamlit as st
import gspread
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import time
import json
from datetime import datetime

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    mot_de_passe_secret = st.secrets["app_password"]
    input_password = st.sidebar.text_input("🔒 Mot de passe", type="password")
    if input_password != mot_de_passe_secret:
        st.sidebar.warning("Saisis le mot de passe pour accéder.")
        st.stop()

# --- CONFIGURATION (PROD) ---
NOM_DU_FICHIER_SHEET = "Arion Plot"  # C'est ton vrai fichier
NOM_ONGLET_JOURNAL = "Journal_App"   # Pour les sous
NOM_ONGLET_REF = "Reference_Craft"   # Pour le suivi d'évolution

# --- FONCTION FORMATAGE ---
def format_fr(nombre):
    """Affiche 10000 -> 10 000,00"""
    try:
        return "{:,.2f}".format(float(nombre)).replace(",", " ").replace(".", ",")
    except:
        return str(nombre)

def format_entier_fr(nombre):
    """Affiche 10000 -> 10 000 (sans virgule)"""
    try:
        return "{:,.0f}".format(float(nombre)).replace(",", " ")
    except:
        return str(nombre)

# --- API ALBION (EU - ROBUSTE) ---
def get_albion_stats(pseudo):
    try:
        # URL AMS (Amsterdam) pour l'Europe
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        resp = requests.get(url_search, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            target = next((p for p in players if p['Name'].lower() == pseudo.lower()), None)
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
                    
                    # Recherche multichemin (comme ton script Sheet)
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
        
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    
    try:
        ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except:
        st.error(f"⚠️ L'onglet '{NOM_ONGLET_REF}' n'existe pas. Crée-le dans 'arion plot' !")
        ws_ref = None

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
        with c1:
            type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
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
                st.success(f"✅ Enregistré : {format_fr(final)} Silver")
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
                st.metric("💰 Trésorerie", f"{format_fr(df['Montant'].sum())} Silver")
            
            st.write("---")
            if 'Date' in df.columns and 'Montant' in df.columns:
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
            
            # Tableau historique formaté
            df_disp = df.copy()
            if 'Montant' in df_disp.columns:
                df_disp['Montant'] = df_disp['Montant'].apply(format_fr)
            st.dataframe(df_disp.tail(10).sort_index(ascending=False), use_container_width=True)
    except:
        st.warning("Chargement...")

# --- TAB 3 : SUIVI CRAFT ---
with tab3:
    st.subheader("🕵️ Suivi de Production")
    
    col_input, col_action = st.columns([2, 1])
    
    with col_input:
        raw_text = st.text_area("Colle le JSON des droits", height=100, placeholder="{ 'Player:...' }")
        
    with col_action:
        st.write("### Actions")
        scan_btn = st.button("🚀 Lancer le Scan", type="primary", use_container_width=True)
        st.write("")
        # Bouton de sauvegarde de référence
        save_ref_btn = st.button("💾 Sauvegarder cette réf.", help="Enregistre les scores actuels comme point de départ", use_container_width=True)

    # Logique de scan
    if scan_btn and raw_text:
        pseudos = []
        try:
            raw_text = raw_text.strip()
            if raw_text.startswith("{"): 
                data_json = json.loads(raw_text)
                for k in data_json.keys():
                    if k.startswith("Player:"):
                        pseudos.append(k.split(":", 1)[1])
            else:
                st.error("JSON invalide")
                st.stop()
        except:
            st.error("Erreur lecture")
            st.stop()
            
        res = []
        barre = st.progress(0)
        for i, p in enumerate(pseudos):
            res.append(get_albion_stats(p))
            time.sleep(0.15)
            barre.progress((i+1)/len(pseudos))
        barre.empty()
        
        # Création du DataFrame des résultats actuels
        df_res = pd.DataFrame(res)
        
        # CALCUL ÉVOLUTION SI POSSIBLE
        if ws_ref:
            try:
                ref_data = ws_ref.get_all_records()
                if ref_data:
                    df_ref = pd.DataFrame(ref_data)
                    # On s'assure que les colonnes existent
                    if 'Pseudo' in df_ref.columns and 'Craft Fame' in df_ref.columns:
                        # On renomme pour éviter les conflits
                        df_ref = df_ref[['Pseudo', 'Craft Fame']].rename(columns={'Craft Fame': 'Ref Fame'})
                        # Fusion (VLOOKUP)
                        df_res = pd.merge(df_res, df_ref, on='Pseudo', how='left')
                        # Calcul Diff
                        df_res['Ref Fame'] = df_res['Ref Fame'].fillna(0)
                        df_res['Progression'] = df_res['Craft Fame'] - df_res['Ref Fame']
            except Exception as e:
                st.warning(f"Impossible de comparer avec la référence : {e}")

        # Sauvegarde en mémoire pour le bouton de sauvegarde
        st.session_state['last_scan'] = df_res
        
        # Affichage
        st.success("Scan terminé !")
        
        # Configuration des colonnes pour l'affichage
        cols_config = {
            "Craft Fame": st.column_config.NumberColumn("Fame Actuelle", format="%d"),
            "Progression": st.column_config.NumberColumn(
                "📈 Progression", 
                format="%+d", # Affiche +100 ou -100
                help="Différence depuis la dernière sauvegarde"
            ),
            "Guilde": st.column_config.TextColumn("Guilde"),
            "Statut": st.column_config.TextColumn("Statut")
        }
        
        # Si la colonne progression n'existe pas (pas de ref), on l'enlève de la config
        if 'Progression' not in df_res.columns:
            del cols_config["Progression"]

        st.dataframe(df_res, column_config=cols_config, use_container_width=True)

    # Logique de sauvegarde
    if save_ref_btn:
        if 'last_scan' in st.session_state and not st.session_state['last_scan'].empty:
            if ws_ref:
                try:
                    df_to_save = st.session_state['last_scan'][['Pseudo', 'Craft Fame']]
                    ws_ref.clear()
                    # On réécrit tout : Titres + Données
                    ws_ref.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
                    st.success(f"✅ Nouvelle référence sauvegardée ! Prochain scan comparera à maintenant.")
                except Exception as e:
                    st.error(f"Erreur sauvegarde : {e}")
        else:
            st.warning("⚠️ Fais d'abord un scan avant de sauvegarder une référence !")