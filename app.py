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

# --- SYSTÈME DE SÉCURITÉ (STRICT - VIA SECRETS) ---
st.sidebar.markdown("## 🔒 Zone Sécurisée")
if "APP_PASSWORD" not in st.secrets:
    st.error("❌ ERREUR : Le secret 'APP_PASSWORD' n'est pas configuré sur Streamlit Cloud.")
    st.stop()

mdp_saisi = st.sidebar.text_input("Mot de passe :", type="password")
if mdp_saisi != st.secrets["APP_PASSWORD"]:
    st.warning("⚠️ Veuillez entrer le mot de passe dans le menu de gauche pour accéder au Dashboard.")
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

    /* Police Roboto pour les nombres : évite la confusion sur le chiffre 1 */
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

# --- FONCTIONS UTILITAIRES ---
def format_nombre(n):
    return "{:,.0f}".format(n).replace(",", " ")

# --- CHARGEMENT DATA AVEC CACHE (ANTI-429) ---
@st.cache_data(ttl=60)
def get_all_data():
    try:
        if "gcp_service_account" in st.secrets:
            creds = json.loads(st.secrets["gcp_service_account"])
            gc = gspread.service_account_from_dict(creds)
        else:
            gc = gspread.service_account(filename='service_account.json')
        sh = gc.open("Arion Plot")
        ws = sh.worksheet("Journal_App")
        data = ws.get_all_records()
        return pd.DataFrame(data), ws
    except Exception as e:
        st.error(f"❌ Erreur de connexion Google Sheets : {e}")
        st.stop()

# --- API ALBION (SCANNER DÉTAILLÉ) ---
def get_full_player_stats(pseudo):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # Recherche ID
        search_url = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        r = requests.get(search_url, headers=headers, timeout=5).json()
        p_list = [p for p in r.get('players', []) if p['Name'].lower() == pseudo.lower()]
        
        if not p_list: return {"Pseudo": pseudo, "Trouve": False}
        
        # Récupération détails (Fame Crafting)
        p_id = p_list[0]['Id']
        det_url = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}"
        d = requests.get(det_url, headers=headers, timeout=5).json()
        
        return {
            "Pseudo": d.get('Name'),
            "Guilde": d.get('GuildName') or "Aucune",
            "Alliance": f"[{d.get('AllianceTag')}] {d.get('AllianceName')}" if d.get('AllianceTag') else "-",
            "Craft Fame": d.get('LifetimeStatistics', {}).get('Crafting', {}).get('Total', 0),
            "Trouve": True
        }
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- INITIALISATION ---
df_raw, worksheet = get_all_data()

def clean_val(v):
    try: return float(str(v).replace(' ', '').replace(',', '.'))
    except: return 0.0

df_raw['Reel'] = df_raw['Montant'].apply(clean_val)
df_raw['Date_Obj'] = pd.to_datetime(df_raw['Date'], format='%d/%m/%Y', errors='coerce')
df_raw['Date_Obj'] = df_raw['Date_Obj'].fillna(pd.to_datetime(df_raw['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

# --- INTERFACE ---
st.markdown("<h1 class='albion-font'>⚔️ Arion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Saisie & Parc", "⚖️ Trésorerie & Bilan Plot", "🔮 Scanner Arion"])

# --- TAB 1 : GESTION COMPLÈTE ---
with tab1:
    col_input, col_park = st.columns([2, 1], gap="large")
    
    with col_input:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction 💰</h3>", unsafe_allow_html=True)
        with st.container(border=True):
            plots_actifs = sorted([p for p in df_raw['Plot'].unique() if p != ""])
            target = st.selectbox("📍 Plot cible :", plots_actifs)
            type_op = st.radio("Nature :", ["Recette (+)", "Dépense (-)"], horizontal=True)
            mnt = st.number_input("Montant (Silver)", min_value=0, step=1000000)
            note = st.text_input("Détails / Note")
            
            if st.button("Valider l'enregistrement", use_container_width=True):
                val_f = mnt if "Recette" in type_op else -mnt
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), target, type_op, val_f, note])
                st.success(f"✅ Enregistré pour {target} !")
                get_all_data.clear()
                time.sleep(1); st.rerun()

    with col_park:
        st.markdown("<h3 class='albion-font'>Gestion du Parc 🏗️</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Ouvrir un nouveau plot"):
            n_n = st.text_input("Nom du plot (ex: Butcher 2)")
            n_c = st.number_input("Prix d'achat", min_value=0)
            if st.button("Confirmer l'ouverture", use_container_width=True):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), n_n, "Dépense (-)", -n_c, "Ouverture"])
                get_all_data.clear(); st.rerun()
        
        with st.expander("🔴 Vendre / Clôturer un plot"):
            p_v = st.selectbox("Plot à vendre :", plots_actifs)
            p_r = st.number_input("Prix de revente :", min_value=0)
            if st.button("Confirmer la clôture", use_container_width=True):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_v, "Recette (+)", p_r, "Clôture"])
                get_all_data.clear(); st.rerun()

# --- TAB 2 : TRÉSORERIE DÉTAILLÉE (TES 129M) ---
with tab2:
    st.markdown("<h3 class='albion-font'>Bilan Financier par Plot</h3>", unsafe_allow_html=True)
    
    # Filtres de dates
    c1, c2, c3 = st.columns([2, 2, 1])
    d_deb = c1.date_input("Début", df_raw['Date_Obj'].min().date())
    d_fin = c2.date_input("Fin", datetime.now().date())
    if c3.button("🔄 Reset Global", use_container_width=True):
        st.rerun()

    mask = (df_raw['Date_Obj'].dt.date >= d_deb) & (df_raw['Date_Obj'].dt.date <= d_fin)
    df_f = df_raw.loc[mask]

    # Global
    net_total = df_f['Reel'].sum()
    st.markdown(f"""
    <div class="albion-metric-box">
        <div class="metric-label">TRÉSORERIE NETTE (PÉRIODE)</div>
        <div class="metric-value roboto-val" style="color:{'#2ecc71' if net_total >= 0 else '#e74c3c'};">
            {format_nombre(net_total)} <span style="font-size:0.4em; color:#bdc3c7;">Silver</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # DÉTAIL PAR PLOT (SÉPARATION DES RECETTES G7:G33)
    st.markdown("<h4 class='albion-font'>📊 Performance par Plot</h4>", unsafe_allow_html=True)
    
    stats = df_f.groupby('Plot')['Reel'].agg([
        ('Rec', lambda x: x[x > 0].sum()),
        ('Dep', lambda x: x[x < 0].sum()),
        ('Net', 'sum')
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
                        <div class="roboto-val txt-green">+{format_nombre(row['Rec'])}</div>
                    </div>
                    <div style="flex: 1; text-align:center;">
                        <div class="label-sm">Dépenses (-)</div>
                        <div class="roboto-val txt-red">{format_nombre(row['Dep'])}</div>
                    </div>
                    <div style="flex: 1.5; text-align:right;">
                        <div class="label-sm">Bénéfice Net</div>
                        <div class="roboto-val" style="font-size:1.6em; color:{'#2ecc71' if row['Net'] >= 0 else '#e74c3c'};">
                            {format_nombre(row['Net'])}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

# --- TAB 3 : SCANNER ARION COMPLET ---
with tab3:
    st.markdown("<h3 class='albion-font'>🔮 Scanner de Crafters Arion</h3>", unsafe_allow_html=True)
    col_in, col_opt = st.columns([3, 1])
    
    with col_in:
        raw_input = st.text_area("Collez le JSON des permissions ou le texte brut ici :", height=250)
    
    with col_opt:
        st.write("### Options")
        lancer_scan = st.button("Lancer l'Analyse API", type="primary", use_container_width=True)

    if lancer_scan and raw_input:
        players = list(set(re.findall(r'"Player:([^"]+)"', raw_input)))
        if not players:
            st.warning("⚠️ Aucun pseudo détecté.")
        else:
            st.info(f"🔎 Analyse de {len(players)} joueurs via l'API Albion...")
            resultats = []
            progress_bar = st.progress(0)
            
            for idx, p_name in enumerate(players):
                info = get_full_player_stats(p_name)
                resultats.append(info)
                progress_bar.progress((idx + 1) / len(players))
                time.sleep(0.1)

            df_scan = pd.DataFrame(resultats)
            st.dataframe(df_scan, use_container_width=True, height=500)
            st.success("✅ Scan terminé avec succès.")

# HISTORIQUE COMPLET
with st.expander("📑 Journal Complet des Transactions"):
    st.dataframe(df_raw[['Date', 'Plot', 'Type', 'Montant', 'Note']].sort_values('Date_Obj', ascending=False), use_container_width=True)