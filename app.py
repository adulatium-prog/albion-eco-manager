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
st.set_page_config(page_title="Arion Economy Manager", page_icon="⚔️", layout="wide")

# --- SYSTÈME DE SÉCURITÉ (OBLIGATOIRE VIA SECRETS) ---
st.sidebar.markdown("## 🔒 Accès Sécurisé")
if "APP_PASSWORD" not in st.secrets:
    st.error("❌ CONFIGURATION MANQUANTE : Ajoutez 'APP_PASSWORD' dans les Secrets de Streamlit.")
    st.stop()

mdp_saisi = st.sidebar.text_input("Mot de passe :", type="password")
if mdp_saisi != st.secrets["APP_PASSWORD"]:
    st.warning("⚠️ Veuillez entrer le mot de passe pour accéder au Dashboard.")
    st.stop()

# --- STYLES CSS COMPLET (DESIGN ALBION + ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    
    h1, h2, h3, h4, .albion-font { 
        font-family: 'Cinzel', serif !important; 
        color: #f39c12 !important; 
        text-shadow: 0 2px 4px rgba(0,0,0,0.5); 
        font-weight: 700; 
        text-transform: uppercase;
    }

    /* Roboto pour les chiffres : évite la confusion sur le chiffre 1 */
    .roboto-val { font-family: 'Roboto', sans-serif !important; font-weight: 700; }

    .albion-metric-box { 
        background: rgba(0, 0, 0, 0.4); 
        padding: 30px; 
        border-radius: 25px; 
        border: 1px solid rgba(243, 156, 18, 0.3); 
        text-align: center; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.5); 
        margin-bottom: 30px; 
    }
    
    .metric-label { color: #bdc3c7; font-family: 'Cinzel', serif; font-size: 1.3em; letter-spacing: 2px; }
    .metric-value { font-family: 'Roboto', sans-serif; font-size: 3.8em; font-weight: bold; margin-top: 10px; }

    .plot-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.2) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
        transition: all 0.3s ease;
    }
    .plot-card:hover { border-color: #f39c12; transform: translateY(-5px); box-shadow: 0 5px 15px rgba(243, 156, 18, 0.2); }

    .label-sm { color: #bdc3c7; font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .txt-green { color: #2ecc71; text-shadow: 0 0 10px rgba(46, 204, 113, 0.3); }
    .txt-red { color: #e74c3c; text-shadow: 0 0 10px rgba(231, 76, 60, 0.3); }

    .stTabs [data-baseweb="tab-list"] { gap: 15px; background-color: rgba(0, 0, 0, 0.3); padding: 12px; border-radius: 25px; }
    .stTabs [data-baseweb="tab"] { height: 50px; color: #bdc3c7; font-family: 'Cinzel', serif; }
    .stTabs [aria-selected="true"] { background-color: rgba(243, 156, 18, 0.2); color: #f39c12; border-radius: 15px; }

    .stButton > button { 
        background: linear-gradient(180deg, #d35400, #a04000); 
        color: white; border-radius: 25px; font-family: 'Cinzel';
        border: 1px solid #e67e22; padding: 12px 30px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION & CONNEXION ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"

def format_nombre(n):
    return "{:,.0f}".format(n).replace(",", " ")

# --- CHARGEMENT DATA AVEC CACHE ---
@st.cache_data(ttl=60)
def get_data():
    try:
        if "gcp_service_account" in st.secrets:
            creds = json.loads(st.secrets["gcp_service_account"])
            gc = gspread.service_account_from_dict(creds)
        else:
            gc = gspread.service_account(filename='service_account.json')
        sh = gc.open(NOM_DU_FICHIER_SHEET)
        ws = sh.worksheet(NOM_ONGLET_JOURNAL)
        data = ws.get_all_records()
        return pd.DataFrame(data), ws
    except Exception as e:
        st.error(f"❌ Erreur de connexion Google Sheets : {e}")
        st.stop()

# --- API ALBION (FONCTION SCANNER) ---
def get_player_info(pseudo):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # On cherche le match exact
            p_data = [p for p in data.get('players', []) if p['Name'].lower() == pseudo.lower()]
            if p_data:
                return {"Pseudo": p_data[0]['Name'], "Guilde": p_data[0]['GuildName'] or "-", "Fame": p_data[0].get('CraftFame', 0)}
        return {"Pseudo": pseudo, "Guilde": "Inconnu", "Fame": 0}
    except: return {"Pseudo": pseudo, "Guilde": "Erreur", "Fame": 0}

# --- INITIALISATION ---
df_raw, worksheet = get_data()

# Nettoyage
def clean_money(val):
    try: return float(str(val).replace(' ', '').replace(',', '.'))
    except: return 0.0

df_raw['Reel'] = df_raw['Montant'].apply(clean_money)
df_raw['Date_Obj'] = pd.to_datetime(df_raw['Date'], format='%d/%m/%Y', errors='coerce')

# --- DASHBOARD ---
st.markdown("<h1 class='albion-font'>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["✍️ Saisie & Parc", "⚖️ Trésorerie & Bilan Plot", "🔮 Scanner Arion"])

# --- TAB 1 : OPÉRATIONS ---
with tab1:
    col_left, col_right = st.columns([2, 1], gap="large")
    
    with col_left:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction 💰</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            plots_actifs = sorted([p for p in df_raw['Plot'].unique() if p != ""])
            nom_p = st.selectbox("📍 Plot cible :", plots_actifs)
            type_op = st.radio("Nature :", ["Recette (+)", "Dépense (-)"], horizontal=True)
            montant = st.number_input("Montant (Silver)", min_value=0, step=1000000)
            note = st.text_input("Détails / Note")
            
            if st.button("Valider l'enregistrement", use_container_width=True):
                val_finale = montant if "Recette" in type_op else -montant
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nom_p, type_op, val_finale, note])
                st.success(f"✅ Enregistré pour {nom_p} !")
                get_data.clear()
                time.sleep(1)
                st.rerun()

    with col_right:
        st.markdown("<h3 class='albion-font'>Gestion du Parc 🏗️</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau terrain"):
            n_nom = st.text_input("Nom du plot")
            n_cout = st.number_input("Coût achat", min_value=0)
            if st.button("Ouvrir"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), n_nom, "Dépense (-)", -n_cout, "Ouverture"])
                get_data.clear(); st.rerun()

# --- TAB 2 : LES CHIFFRES (TES 129M) ---
with tab2:
    st.markdown("<h3 class='albion-font'>Bilan Financier par Cycle</h3>", unsafe_allow_html=True)
    
    # Filtres de dates
    c1, c2, c3 = st.columns([2, 2, 1])
    d_deb = c1.date_input("Depuis le", df_raw['Date_Obj'].min().date())
    d_fin = c2.date_input("Jusqu'au", datetime.now().date())
    if c3.button("🔄 Reset Global", use_container_width=True):
        st.rerun()

    mask = (df_raw['Date_Obj'].dt.date >= d_deb) & (df_raw['Date_Obj'].dt.date <= d_fin)
    df_f = df_raw.loc[mask]

    # Global
    net_total = df_f['Reel'].sum()
    st.markdown(f"""
    <div class="albion-metric-box">
        <div class="metric-label">TRÉSORERIE NETTE GLOBALE</div>
        <div class="metric-value roboto-val" style="color:{'#2ecc71' if net_total >= 0 else '#e74c3c'};">
            {format_nombre(net_total)} <span style="font-size:0.4em; color:#bdc3c7;">Silver</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # DÉTAIL PAR PLOT (SÉPARATION DES RECETTES G7:G33)
    st.markdown("<h4 class='albion-font'>📊 Performance par Plot</h4>", unsafe_allow_html=True)
    
    # On groupe pour isoler chaque plot et voir ses Revenus vs Dépenses
    stats = df_f.groupby('Plot')['Reel'].agg([
        ('Revenu', lambda x: x[x > 0].sum()),
        ('Depense', lambda x: x[x < 0].sum()),
        ('Solde', 'sum')
    ]).reset_index()

    for _, row in stats.iterrows():
        if row['Plot'] == "": continue
        with st.container():
            st.markdown(f"""
            <div class="plot-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1.5;"><span class="albion-font" style="font-size:1.4em;">{row['Plot']}</span></div>
                    <div style="flex: 1; text-align:center;">
                        <div class="label-sm">Recettes (+)</div>
                        <div class="roboto-val txt-green">+{format_nombre(row['Revenu'])}</div>
                    </div>
                    <div style="flex: 1; text-align:center;">
                        <div class="label-sm">Dépenses (-)</div>
                        <div class="roboto-val txt-red">{format_nombre(row['Depense'])}</div>
                    </div>
                    <div style="flex: 1.5; text-align:right;">
                        <div class="label-sm">Bénéfice Net</div>
                        <div class="roboto-val" style="font-size:1.6em; color:{'#2ecc71' if row['Solde'] >= 0 else '#e74c3c'};">
                            {format_nombre(row['Solde'])}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- TAB 3 : SCANNER ARION ---
with tab3:
    st.markdown("<h3 class='albion-font'>🔮 Scanner de Crafters Arion</h3>", unsafe_allow_html=True)
    col_in, col_opt = st.columns([3, 1])
    
    with col_in:
        raw_input = st.text_area("Collez le JSON des permissions ou le texte brut ici :", height=250)
    
    with col_opt:
        st.write("### Options")
        lancer_scan = st.button("Lancer l'Analyse API", type="primary", use_container_width=True)
        if st.button("Effacer tout"):
            st.rerun()

    if lancer_scan and raw_input:
        # Regex pour extraire les pseudos
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_input)))
        if not players:
            st.warning("⚠️ Aucun pseudo détecté. Vérifiez le format (Player:Pseudo).")
        else:
            st.info(f"🔎 Analyse de {len(players)} joueurs via l'API Albion...")
            resultats = []
            progress_bar = st.progress(0)
            
            for idx, p_name in enumerate(players):
                info = get_player_info(p_name)
                resultats.append(info)
                progress_bar.progress((idx + 1) / len(players))
                time.sleep(0.1) # Respecter l'API

            df_scan = pd.DataFrame(resultats)
            st.dataframe(df_scan, use_container_width=True, height=500)
            st.success("✅ Scan terminé avec succès.")

# HISTORIQUE COMPLET
with st.expander("📑 Consulter le Journal_App (Source)"):
    st.dataframe(df_raw[['Date', 'Plot', 'Type', 'Montant', 'Note']].sort_values('Date', ascending=False), use_container_width=True)