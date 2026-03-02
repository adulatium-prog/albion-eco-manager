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
st.set_page_config(page_title="Albion Economy Manager", page_icon="⚔️", layout="wide")

# --- STYLE CSS INTEGRAL ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@400;700&display=swap');
    .stApp { background-image: linear-gradient(to right bottom, #0f0c29, #302b63, #24243e); color: #ecf0f1; font-family: 'Roboto', sans-serif; }
    .stButton > button { background: linear-gradient(180deg, #d35400, #a04000); color: white; border: 1px solid #e67e22; border-radius: 20px; font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase; padding: 10px 24px; transition: all 0.2s; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    h1, h2, h3, h4, .albion-font { font-family: 'Cinzel', serif !important; color: #ecf0f1 !important; text-shadow: 0 2px 4px rgba(0,0,0,0.5); font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(0, 0, 0, 0.2); padding: 10px; border-radius: 20px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: transparent; color: #bdc3c7; font-family: 'Cinzel', serif; border: none; }
    .stTabs [aria-selected="true"] { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border-radius: 10px; font-weight: bold; }
    .albion-metric-box { background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 20px; border: 1px solid rgba(236, 240, 241, 0.3); text-align: center; margin-bottom: 20px; }
    .metric-value { font-family: 'Roboto', sans-serif !important; font-size: 3.5em; font-weight: bold; }
    .plot-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 15px; text-align: center; margin-bottom: 10px; }
    .plot-value { font-family: 'Roboto', sans-serif !important; font-size: 1.2em; font-weight: 700; }
    .val-pos { color: #2ecc71; } .val-neg { color: #ff6b6b; }
</style>
""", unsafe_allow_html=True)

# --- SECURITE ---
if "APP_PASSWORD" in st.secrets:
    if st.sidebar.text_input("🔒 Accès", type="password") != st.secrets["APP_PASSWORD"]:
        st.sidebar.warning("Veuillez saisir le mot de passe.")
        st.stop()

# --- CONFIGURATION FICHIERS ---
NOM_DU_FICHIER_SHEET = "Arion Plot"
NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"

# --- FONCTIONS UTILITAIRES ---
def format_monetaire(valeur):
    try: return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except: return str(valeur)

def extraire_noms_et_tags(liste_brute):
    res = set()
    for item in liste_brute:
        txt = item.strip().lower()
        res.add(txt)
        match = re.search(r'^(.*?)\[(.*?)\]$', txt)
        if match:
            if match.group(1): res.add(match.group(1).strip())
            if match.group(2): res.add(match.group(2).strip())
    return res

# --- API ALBION ---
def get_player_stats(pseudo):
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}", headers=h).json()
        cand = [p for p in r.get('players', []) if p['Name'].lower() == pseudo.lower()]
        if not cand: return {"Pseudo": pseudo, "Trouve": False}
        p_id = cand[0]['Id']
        d = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{p_id}", headers=h).json()
        ls = d.get('LifetimeStatistics', {}).get('Crafting', {})
        return {
            "Pseudo": d.get('Name'), "Guilde": d.get('GuildName') or "Aucune",
            "Alliance": d.get('AllianceName') or "-", "AllianceTag": d.get('AllianceTag') or "",
            "Craft Fame": ls.get('Total', 0), "Trouve": True
        }
    except: return {"Pseudo": pseudo, "Trouve": False}

# --- CONNEXION ---
try:
    if os.path.exists('service_account.json'):
        gc = gspread.service_account(filename='service_account.json')
    else:
        gc = gspread.service_account_from_dict(json.loads(st.secrets["gcp_service_account"].strip()))
    sh = gc.open(NOM_DU_FICHIER_SHEET)
    worksheet = sh.worksheet(NOM_ONGLET_JOURNAL)
    try: ws_ref = sh.worksheet(NOM_ONGLET_REF)
    except: ws_ref = None
except Exception as e:
    st.error(f"Erreur Connexion : {e}"); st.stop()

# --- ANALYSE FINANCIERE ---
data_j = worksheet.get_all_records()
df_j = pd.DataFrame(data_j) if data_j else pd.DataFrame(columns=['Date', 'Plot', 'Type', 'Montant', 'Note'])

def calc_reel(row):
    try:
        t, n = str(row.get('Type', '')).lower(), str(row.get('Note', '')).lower()
        m = float(str(row.get('Montant', 0)).replace(' ', '').replace(',', '.'))
        if any(w in t or w in n for w in ["dépense", "ouverture", "bid"]): return -abs(m)
        return abs(m)
    except: return 0.0

if not df_j.empty:
    df_j['Reel'] = df_j.apply(calc_reel, axis=1)
    df_j['Date_Obj'] = pd.to_datetime(df_j['Date'], format='%d/%m/%Y', errors='coerce')
    df_j['Date_Obj'] = df_j['Date_Obj'].fillna(pd.to_datetime(df_j['Date'].astype(str) + f"/{datetime.now().year}", format='%d/%m/%Y', errors='coerce'))

plots_actifs = [p for p in df_j['Plot'].unique() if p != "" and p not in df_j[df_j['Note'].str.contains('Clôture', na=False)]['Plot'].unique()]

# --- INTERFACE ---
st.markdown("<h1 class='albion-font'>⚔️ Albion Economy Manager</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["✍️ Page 1 : Opérations", "⚖️ Page 2 : Trésorerie", "🔮 Page 3 : Scanner"])

# PAGE 1 & 2 (Restaurées)
with tab1:
    c_s, c_g = st.columns([2, 1], gap="large")
    with c_s:
        st.markdown("<h3 class='albion-font'>Nouvelle Transaction</h3>", unsafe_allow_html=True)
        with st.form("tx"):
            col1, col2 = st.columns(2); t_op = col1.radio("Type", ["Recette (+)", "Dépense (-)"]); plot_t = col2.selectbox("Plot", plots_actifs + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant", min_value=0, step=1000000); nt = st.text_input("Note")
            if st.form_submit_button("Valider"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), plot_t, t_op, mnt, nt]); st.cache_data.clear(); st.rerun()
    with c_g:
        st.markdown("<h3 class='albion-font'>Gestion Parc</h3>", unsafe_allow_html=True)
        with st.expander("🟢 Nouveau"):
            nn, nc = st.text_input("Nom"), st.number_input("Prix", min_value=0)
            if st.button("Ouvrir"): worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", nc, "Ouverture"]); st.cache_data.clear(); st.rerun()

with tab2:
    if not df_j.empty:
        c1, c2 = st.columns(2); d_s = c1.date_input("Début", df_j['Date_Obj'].min().date()); d_e = c2.date_input("Fin", datetime.now().date())
        df_f = df_j[(df_j['Date_Obj'].dt.date >= d_s) & (df_j['Date_Obj'].dt.date <= d_e)]
        net = df_f['Reel'].sum()
        st.markdown(f'<div class="albion-metric-box"><div class="metric-value {"val-pos" if net >= 0 else "val-neg"}">{format_monetaire(net)} Silver</div></div>', unsafe_allow_html=True)
        stats = df_f.groupby('Plot')['Reel'].sum(); cols = st.columns(4)
        for idx, p in enumerate(df_j['Plot'].unique()):
            val = stats.get(p, 0)
            with cols[idx % 4]: st.markdown(f'<div class="plot-card"><div class="plot-title">{p}</div><div class="plot-value {"val-pos" if val >= 0 else "val-neg"}">{format_monetaire(val)}</div></div>', unsafe_allow_html=True)
        st.divider(); st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note']].iloc[::-1], use_container_width=True)

# PAGE 3 : SCANNER (RESTAURATION COMPLETE DES DOUBLONS ET % EVOL)
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Arion v2</h3>", unsafe_allow_html=True)
    raw_tx = st.text_area("Permissions JSON", height=200)
    col_a, col_b = st.columns([1, 1])
    lancer = col_a.button("Lancer l'Audit", type="primary", use_container_width=True)
    save = col_b.button("Sauvegarder Référence", use_container_width=True)

    if lancer and raw_tx:
        raw_p = list(set(re.findall(r'"Player:([^"]+)"', raw_tx)))
        mem_g = extraire_noms_et_tags(re.findall(r'"Guild:([^"]+)"', raw_tx))
        mem_a = extraire_noms_et_tags(re.findall(r'"Alliance:([^"]+)"', raw_tx))
        
        # Récupération Référence Fame
        df_ref = pd.DataFrame(ws_ref.get_all_records()) if ws_ref else pd.DataFrame(columns=['Pseudo', 'Craft Fame'])

        res = []
        bar = st.progress(0)
        for i, p in enumerate(raw_p):
            inf = get_player_stats(p)
            status = "✅ Unique"
            if inf['Trouve']:
                if inf['Guilde'].lower() in mem_g: status = "⚠️ Doublon Guilde"
                elif inf['AllianceTag'].lower() in mem_a: status = "⚠️ Doublon Alliance"
            
            # Calcul Evolution
            inf['Analyse'] = status
            ref_val = df_ref[df_ref['Pseudo'] == inf['Pseudo']]['Craft Fame'].values
            if len(ref_val) > 0:
                diff = inf['Craft Fame'] - ref_val[0]
                inf['Progression'] = diff
                inf['% Évol.'] = f"{(diff/ref_val[0])*100:.1f}%" if ref_val[0] > 0 else "0%"
            else:
                inf['Progression'] = "✨ Nouveau"; inf['% Évol.'] = "-"
            
            res.append(inf)
            bar.progress((i+1)/len(raw_p))
        
        st.session_state['scan_res'] = pd.DataFrame(res).sort_values(by="Craft Fame", ascending=False)

    if 'scan_res' in st.session_state:
        df_res = st.session_state['scan_res']
        
        # Boutons pour les Doublons
        doublons = df_res[df_res['Analyse'].str.contains("Doublon")]
        if not doublons.empty:
            with st.expander(f"🗑️ {len(doublons)} Doublons détectés à retirer"):
                st.code(", ".join(doublons['Pseudo'].tolist()))
        
        st.dataframe(df_res[['Pseudo', 'Guilde', 'Alliance', 'Craft Fame', 'Progression', '% Évol.', 'Analyse']], use_container_width=True)

    if save and 'scan_res' in st.session_state and ws_ref:
        df_s = st.session_state['scan_res'][['Pseudo', 'Craft Fame']]
        ws_ref.clear(); ws_ref.update([df_s.columns.values.tolist()] + df_s.values.tolist())
        st.toast("Base de référence mise à jour !"); time.sleep(1); st.rerun()
