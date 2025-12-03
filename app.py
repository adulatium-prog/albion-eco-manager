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

# --- CONFIGURATION ---
# ⚠️ REMPLACE L'ID CI-DESSOUS PAR CELUI DE TON GOOGLE SHEET
SHEET_ID = "COLLE_TON_ID_ICI" 

NOM_ONGLET_JOURNAL = "Journal_App"
NOM_ONGLET_REF = "Reference_Craft"

# --- FONCTIONS DE FORMATAGE ---
def format_monetaire(valeur):
    """Affiche: 10 000,00"""
    try:
        return "{:,.2f}".format(float(valeur)).replace(",", " ").replace(".", ",")
    except:
        return str(valeur)

def format_nombre_entier(valeur):
    """Affiche: 10 000 000"""
    try:
        return "{:,.0f}".format(float(valeur)).replace(",", " ")
    except:
        return str(valeur)

# --- API ALBION (EU / AMS) ---
def get_albion_stats(pseudo):
    try:
        # URL Serveur Europe (Amsterdam)
        url_search = f"https://gameinfo-ams.albiononline.com/api/gameinfo/search?q={pseudo}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        resp = requests.get(url_search, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            players = data.get('players', [])
            target = next((