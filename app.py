import os
import streamlit as st
import gspread
import pandas as pd
import requests
import time
import re
import json
from datetime import datetime

# --- CONFIGURATION STRUCTURELLE ---
st.set_page_config(page_title="Arion Economy - Industrial Grade", page_icon="⚔️", layout="wide")

# --- DESIGN SYSTEM (CINZEL & ROBOTO) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Roboto:wght@300;400;700&display=swap');

    .stApp {
        background-image: linear-gradient(to right bottom, #0f0c29, #201b46, #1a1a2e);
        color: #ecf0f1;
        font-family: 'Roboto', sans-serif;
    }

    /* Boutons Albion Style */
    .stButton > button {
        background: linear-gradient(180deg, #d35400, #a04000);
        color: white; border: 1px solid #e67e22; border-radius: 4px;
        font-family: 'Cinzel', serif; font-weight: bold; text-transform: uppercase;
        width: 100%; padding: 12px; transition: 0.3s;
    }
    .stButton > button:hover {
        background: linear-gradient(180deg, #e67e22, #d35400);
        box-shadow: 0 0 20px rgba(211, 84, 0, 0.4);
    }

    /* En-têtes */
    h1, h2, h3, h4, .albion-font {
        font-family: 'Cinzel', serif !important;
        color: #f39c12 !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    }

    /* Métriques de Trésorerie */
    .metric-container {
        background: rgba(0, 0, 0, 0.5);
        padding: 30px;
        border-radius: 10px;
        border-left: 5px solid #f39c12;
        margin-bottom: 30px;
    }
    .metric-label { font-family: 'Cinzel', serif; font-size: 1.2em; color: #bdc3c7; }
    .metric-value { 
        font-family: 'Roboto', sans-serif !important; 
        font-size: 3.8em; font-weight: 700; color: #ffffff;
    }

    /* Cartes de Plots */
    .plot-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(243, 156, 18, 0.2);
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        transition: 0.2s;
    }
    .plot-card:hover { background: rgba(255, 255, 255, 0.07); border-color: #f39c12; }
    .plot-title { font-family: 'Cinzel', serif; color: #f39c12; font-size: 1em; margin-bottom: 10px; }
    .plot-val { font-family: 'Roboto', sans-serif !important; font-size: 1.5em; font-weight: 700; }

    .val-pos { color: #2ecc71 !important; }
    .val-neg { color: #e74c3c !important; }

    /* Scanner */
    .scanner-log { font-family: 'Roboto Mono', monospace; font-size: 0.85em; background: #000; padding: 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- SÉCURITÉ ---
if "app_password" in st.secrets:
    if st.sidebar.text_input("🔑 Clé d'accès Arion", type="password") != st.secrets["app_password"]:
        st.info("Système d'économie Arion en attente d'authentification...")
        st.stop()

# --- MOTEUR DE CONNEXION ---
@st.cache_resource
def init_connection():
    try:
        if "gcp_service_account" in st.secrets:
            info = json.loads(st.secrets["gcp_service_account"])
            return gspread.service_account_from_dict(info)
        return gspread.service_account(filename='service_account.json')
    except Exception as e:
        st.error(f"Erreur d'infrastructure : {e}")
        return None

gc = init_connection()

# --- MOTEUR DE DONNÉES (ROBUSTESSE MAXIMALE) ---
def load_data():
    try:
        sh = gc.open("Arion Plot")
        ws = sh.worksheet("Journal_App")
        ref = sh.worksheet("Reference_Craft")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return pd.DataFrame(columns=['Date', 'Plot', 'Type', 'Montant', 'Note', 'Reel']), ws, ref

        # Robustesse : Nettoyage forcé des formats numériques (espaces, virgules, etc.)
        df['Montant_Clean'] = df['Montant'].astype(str).str.replace(r'[\s\u00A0,]', '', regex=True).replace('', '0')
        df['Montant_Num'] = pd.to_numeric(df['Montant_Clean'], errors='coerce').fillna(0)

        # Logique métier des signes :
        # Interprétation interne pour Streamlit sans modifier le Sheet
        def apply_logic(row):
            t = str(row['Type']).lower()
            n = str(row['Note']).lower()
            # Si c'est marqué comme dépense OU une opération d'ouverture/enchère
            if "dépense" in t or "ouverture" in n or "bid" in n or "achat" in n:
                return -abs(row['Montant_Num'])
            return abs(row['Montant_Num'])

        df['Reel'] = df.apply(apply_logic, axis=1)
        df['Date_Obj'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
        
        return df, ws, ref
    except Exception as e:
        st.error(f"Échec de lecture de la base : {e}")
        return None, None, None

df, worksheet, ws_ref = load_data()

# --- LOGIQUE DE PARC IMMOBILIER ---
# On identifie les plots qui n'ont pas encore été "clôturés" (vendus)
if not df.empty:
    clotures = df[df['Note'].str.contains('Clôture', case=False, na=False)]['Plot'].unique()
    tous_plots = [p for p in df['Plot'].unique() if p not in ["", "Taxe Guilde", "Autre"]]
    plots_actifs = [p for p in tous_plots if p not in clotures]
else:
    plots_actifs = []

# --- INTERFACE MULTI-PAGES ---
tab1, tab2, tab3 = st.tabs(["🏗️ GESTION & OPÉRATIONS", "📊 ANALYSE FINANCIÈRE", "🔮 SCANNER ANALYTIQUE"])

# --- PAGE 1 : CONSOLE D'ADMINISTRATION ---
with tab1:
    st.markdown("<h3 class='albion-font'>Console d'Opérations</h3>", unsafe_allow_html=True)
    
    col_input, col_parc = st.columns([2, 1], gap="large")
    
    with col_input:
        st.markdown("#### Saisie Journalière")
        with st.form("main_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            t_op = c1.radio("Nature", ["Recette (+)", "Dépense (-)"], horizontal=True)
            p_sel = c2.selectbox("Plot", plots_actifs + ["Taxe Guilde", "Autre"])
            mnt = st.number_input("Montant Silver", min_value=0, step=1000000)
            note = st.text_input("Note (Ex: Taxe Hebdo, Bid de Plot...)")
            
            if st.form_submit_button("ENREGISTRER LA TRANSACTION"):
                # On écrit toujours en valeur ABSOLUE dans le sheet pour la propreté
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), p_sel, t_op, abs(mnt), note])
                st.success("Données synchronisées avec succès.")
                st.cache_data.clear(); time.sleep(1); st.rerun()

    with col_parc:
        st.markdown("#### Gestion du Parc")
        with st.expander("🟢 Nouveau Plot (Ouverture)"):
            nn = st.text_input("Nom du Plot (ex: Weaver 3)")
            nc = st.number_input("Investissement Initial", min_value=0)
            if st.button("Valider l'Ouverture"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), nn, "Dépense (-)", abs(nc), "Ouverture"])
                st.cache_data.clear(); st.rerun()
                
        with st.expander("🔴 Vendre Plot (Clôture)"):
            pv = st.selectbox("Plot à liquider", plots_actifs)
            pr = st.number_input("Prix de Revente", min_value=0)
            if st.button("Confirmer la Vente"):
                worksheet.append_row([datetime.now().strftime("%d/%m/%Y"), pv, "Recette (+)", abs(pr), "Clôture"])
                st.cache_data.clear(); st.rerun()

# --- PAGE 2 : ANALYSE FINANCIÈRE (LE DÉCISIONNEL) ---
with tab2:
    if not df.empty:
        st.markdown("<h3 class='albion-font'>État Major des Finances</h3>", unsafe_allow_html=True)
        
        # Filtre Temporel
        c1, c2 = st.columns(2)
        start_d = c1.date_input("Depuis le", df['Date_Obj'].min().date() if not df['Date_Obj'].isnull().all() else datetime.now().date())
        end_d = c2.date_input("Jusqu'au", datetime.now().date())
        
        df_f = df[(df['Date_Obj'].dt.date >= start_d) & (df['Date_Obj'].dt.date <= end_d)]
        
        # RÉCAP GLOBAL (LE JUGE DE PAIX)
        net_worth = df_f['Reel'].sum()
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-label">SOLDE NET RÉEL (CYCLE ACTUEL)</div>
            <div class="metric-value {'val-pos' if net_worth >= 0 else 'val-neg'}">
                {"{:,.0f}".format(net_worth).replace(",", " ")} Silver
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # GROUPEMENT PAR FAMILLE
        st.markdown("#### Performance par Secteur d'Activité")
        # On extrait le premier mot (Weaver 1 -> Weaver)
        df_f['Famille'] = df_f['Plot'].apply(lambda x: str(x).split()[0] if x else "Inconnu")
        stats = df_f.groupby('Famille')['Reel'].sum().reset_index()
        
        cols = st.columns(4)
        for i, row in stats.iterrows():
            with cols[i % 4]:
                st.markdown(f"""
                <div class="plot-card">
                    <div class="plot-title">{row['Famille']}</div>
                    <div class="plot-val {'val-pos' if row['Reel'] >= 0 else 'val-neg'}">
                        {"{:,.0f}".format(row['Reel']).replace(",", " ")}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.divider()
        st.markdown("#### Journal d'Audit")
        st.dataframe(df_f[['Date', 'Plot', 'Type', 'Montant', 'Note', 'Reel']].iloc[::-1], use_container_width=True)
    else:
        st.warning("Aucune donnée disponible pour l'analyse.")

# --- PAGE 3 : SCANNER ARION (AUDIT API) ---
with tab3:
    st.markdown("<h3 class='albion-font'>Scanner Arion v3.0</h3>", unsafe_allow_html=True)
    raw_input = st.text_area("Collez le bloc JSON ou texte brut des permissions ici", height=250)
    
    c_btn1, c_btn2 = st.columns(2)
    run_audit = c_btn1.button("LANCER L'AUDIT ANALYTIQUE", use_container_width=True)
    save_ref = c_btn2.button("SAUVEGARDER COMME RÉFÉRENCE", use_container_width=True)

    if run_audit and raw_input:
        with st.spinner("Analyse des serveurs Albion en cours..."):
            # Extraction par Regex (plus robuste que le parsing JSON simple)
            found_players = list(set(re.findall(r'"Player:([^"]+)"', raw_input)))
            found_guilds = [g.lower() for g in re.findall(r'"Guild:([^"]+)"', raw_input)]
            found_alliances = [a.lower() for a in re.findall(r'"Alliance:([^"]+)"', raw_input)]
            
            # Charger les anciennes valeurs de Fame
            ref_data = pd.DataFrame(ws_ref.get_all_records())
            
            audit_results = []
            progress = st.progress(0)
            
            for i, pseudo in enumerate(found_players):
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    # Recherche du joueur sur l'API
                    r = requests.get(f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}", headers=headers).json()
                    p_info = [x for x in r.get('players', []) if x['Name'].lower() == pseudo.lower()][0]
                    
                    # Logique de doublon
                    status = "✅ Unique"
                    if p_info.get('GuildName', '').lower() in found_guilds: status = "⚠️ Doublon Guilde"
                    elif p_info.get('AllianceTag', '').lower() in found_alliances: status = "⚠️ Doublon Alliance"
                    
                    # Calcul d'évolution
                    fame_now = p_info.get('CraftingFame', 0)
                    old_row = ref_data[ref_data['Pseudo'] == p_info['Name']]
                    prog, evol = 0, "Nouveau"
                    if not old_row.empty:
                        f_old = old_row['Craft Fame'].values[0]
                        prog = fame_now - f_old
                        evol = f"{(prog/f_old)*100:.1f}%" if f_old > 0 else "0%"

                    audit_results.append({
                        "Pseudo": p_info['Name'],
                        "Fame Craft": fame_now,
                        "Progression": prog,
                        "% Évolution": evol,
                        "Guilde": p_info.get('GuildName', '-'),
                        "Analyse": status
                    })
                except:
                    audit_results.append({"Pseudo": pseudo, "Analyse": "❌ API ERROR"})
                
                progress.progress((i+1)/len(found_players))
            
            res_df = pd.DataFrame(audit_results).sort_values(by="Fame Craft", ascending=False)
            st.session_state['last_scan'] = res_df

    if 'last_scan' in st.session_state:
        st.markdown("#### Résultats de l'Audit")
        st.dataframe(st.session_state['last_scan'], use_container_width=True)
        
        # Suggestion de nettoyage
        to_remove = st.session_state['last_scan'][st.session_state['last_scan']['Analyse'].str.contains("Doublon")]
        if not to_remove.empty:
            st.warning(f"Nettoyage suggéré : {len(to_remove)} joueurs sont déjà couverts par une règle de guilde/alliance.")
            st.code(", ".join(to_remove['Pseudo'].tolist()))

    if save_ref and 'last_scan' in st.session_state:
        df_to_save = st.session_state['last_scan'][['Pseudo', 'Fame Craft']].rename(columns={'Fame Craft': 'Craft Fame'})
        ws_ref.clear()
        ws_ref.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
        st.success("Base de référence mise à jour pour le prochain calcul d'évolution.")
