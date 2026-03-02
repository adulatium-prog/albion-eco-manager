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

# Injection du CSS (Ton design complet conservé)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

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

    h1, h2, h3, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #ecf0f1 !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        font-weight: 700;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold;
    }

    .albion-metric-box {
        background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px;
        border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; margin-bottom: 20px;
    }
    .metric-value {
        font-family: 'Cinzel', serif; font-size: 3.5em; font-weight: bold;
    }

    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px;
    }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 0.85em; text-transform: uppercase; font-weight: bold; }
    .plot-value { font-family: 'Roboto', sans-serif; font-size: 1.1em; font-weight: 700; margin-top: 5px; }

    .val-pos { color: #2ecc71; } 
    .val-neg { color: #ff6b6b; } 
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔒 Mot de passe", type="password") != st.secrets["app_password"]:
        st.sidebar.warning("Saisis le mot de passe pour accéder.")
        st.stop()

# --- CONFIGURATION ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"
SEUIL_FAME_MIN = 4000000 

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
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
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            candidats = [p for p in players if p['Name'].lower() == pseudo.lower()]
            if not candidats: return {"Pseudo": pseudo, "Trouve": False}
            
            p_id = candidats[0]['Id']
            url_details = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}"
            r_det = requests.get(url_details, headers=headers)
            if r_det.status_code == 200:
                d = r_det.json()
                ls = d.get('LifetimeStatistics', {}).get('Crafting', {})
                return {
                    "Pseudo": d.get('Name'), "Guilde": d.get('GuildName') or "Aucune",
                    "Alliance": d.get('AllianceName') or "-", "AllianceTag": d.get('AllianceTag') or "",
                    "Craft Fame": ls.get('Total', 0), "Trouve": True
                }
        return {"Pseudo": pseudo, "Trouve": False}
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- CONNEXION ---
try:
    if "gcp_service_account" in st.secrets:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    else:
        gc = gspread.service_account(filename='service_account.json')
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    try: ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except: ws_ref = None
except Exception as e: st.error(f"Erreur connexion : {e}"); st.stop()

# --- INTERFACE ---
st.markdown("<h1>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["📜 Journal des Comptes", "⚖️ Trésorerie", "🔮 Scanner Arion"])

# --- TAB 1 : SAISIE ---
with tab1:
    st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
    with st.form("ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1: type_op = st.radio("Type", ["Recette (+)", "Dépense (-)"], horizontal=True)
        with c2: batiment = st.selectbox("Plot", ["Cook", "Hunter", "Weaver", "Mage", "Butcher", "Smelter", "Taxe Guilde", "Autre"])
        montant = st.number_input("Montant (Silver)", step=1000000, format="%d")
        note = st.text_input("Description (ex: Ouverture Weaver 2)")
        if st.form_submit_button("Valider"):
            worksheet.append_row([datetime.now().strftime("%d/%m"), batiment, type_op, abs(montant), note])
            st.toast("Transaction enregistrée !"); st.cache_data.clear(); st.rerun()

# --- TAB 2 : TRÉSORERIE (LOGIQUE AMÉLIORÉE) ---
with tab2:
    st.markdown("<h3 class='albion-font'>État des Finances</h3>", unsafe_allow_html=True)
    try:
        data = worksheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            
            # AMÉLIORATION : Nettoyage et calcul interne sans modifier le Sheet
            df['M_Num'] = df['Montant'].astype(str).str.replace(r'[\s,]', '', regex=True).astype(float)
            
            def logic_reel(row):
                t = str(row['Type']).lower()
                n = str(row['Note']).lower()
                if "dépense" in t or any(word in n for word in ["ouverture", "bid", "achat"]):
                    return -abs(row['M_Num'])
                return abs(row['M_Num'])
            
            df['Reel'] = df.apply(logic_reel, axis=1)
            total = df['Reel'].sum()
            
            # Affichage Metric
            color = "val-pos" if total >= 0 else "val-neg"
            st.markdown(f'<div class="albion-metric-box"><div class="metric-label">SOLDE NET</div><div class="metric-value {color}">{format_monetaire(total)}</div></div>', unsafe_allow_html=True)
            
            # Recap par Plot
            stats = df.groupby('Plot')['Reel'].sum()
            targets = ["Cook", "Hunter", "Weaver", "Mage", "Butcher", "Smelter", "Taxe Guilde"]
            cols = st.columns(len(targets))
            for i, t in enumerate(targets):
                val = stats.get(t, 0)
                c_class = "val-pos" if val >= 0 else "val-neg"
                cols[i].markdown(f'<div class="plot-card"><div class="plot-title">{t}</div><div class="plot-value {c_class}">{format_monetaire(val)}</div></div>', unsafe_allow_html=True)
            
            st.divider()
            st.dataframe(df[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)
    except: st.warning("Données inaccessibles.")

# --- TAB 3 : SCANNER (COMPLET CONSERVÉ) ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner de Permissions</h3>", unsafe_allow_html=True)
    raw_text = st.text_area("Permissions JSON/Texte", height=200)
    col_a, col_b = st.columns(2)
    scan_btn = col_a.button("Lancer l'Analyse", type="primary", use_container_width=True)
    save_btn = col_b.button("Sauvegarder Référence", use_container_width=True)

    if scan_btn and raw_text:
        with st.spinner("Audit en cours..."):
            raw_p = list(set(re.findall(r'"Player:([^"]+)"', raw_text)))
            mem_g = extraire_noms_et_tags(re.findall(r'"Guild:([^"]+)"', raw_text))
            mem_a = extraire_noms_et_tags(re.findall(r'"Alliance:([^"]+)"', raw_text))
            
            df_ref = pd.DataFrame(ws_ref.get_all_records()) if ws_ref else pd.DataFrame(columns=['Pseudo', 'Craft Fame'])
            
            res = []
            bar = st.progress(0)
            for i, p in enumerate(raw_p):
                inf = get_player_stats(p)
                status = "✅ Unique"
                if inf['Trouve']:
                    if inf['Guilde'].lower() in mem_g: status = "⚠️ Doublon Guilde"
                    elif inf['AllianceTag'].lower() in mem_a: status = "⚠️ Doublon Alliance"
                
                inf['Analyse'] = status
                # Calcul Evolution
                ref_val = df_ref[df_ref['Pseudo'] == inf['Pseudo']]['Craft Fame'].values
                if len(ref_val) > 0:
                    diff = inf['Craft Fame'] - ref_val[0]
                    inf['Progression'] = diff
                    inf['% Évol.'] = f"{(diff/ref_val[0])*100:.1f}%" if ref_val[0] > 0 else "0%"
                else:
                    inf['Progression'] = 0; inf['% Évol.'] = "Nouveau"
                
                res.append(inf)
                bar.progress((i+1)/len(raw_p))
            
            st.session_state['scan_res'] = pd.DataFrame(res).sort_values(by="Craft Fame", ascending=False)

    if 'scan_res' in st.session_state:
        df_res = st.session_state['scan_res']
        # Affichage Doublons
        doublons = df_res[df_res['Analyse'].str.contains("Doublon")]
        if not doublons.empty:
            with st.expander("🗑️ Pseudos à retirer"):
                st.code(", ".join(doublons['Pseudo'].tolist()))
        
        st.dataframe(df_res[['Pseudo', 'Guilde', 'Alliance', 'Craft Fame', 'Progression', '% Évol.', 'Analyse']], use_container_width=True)

    if save_btn and 'scan_res' in st.session_state:
        df_s = st.session_state['scan_res'][['Pseudo', 'Craft Fame']]
        ws_ref.clear(); ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
        st.toast("Référence mise à jour !")
