import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
import time
import csv
import httpx
import google.genai as genai
from dotenv import load_dotenv
from tools.naf_search import search_naf_code
from tools.sirene_engine import fetch_sirene_data

load_dotenv()

st.set_page_config(page_title="IA Prospector Web", layout="wide")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
if not os.path.exists(EXPORT_DIR): os.makedirs(EXPORT_DIR)

if os.path.exists(os.path.join(BASE_DIR, "style.css")):
    with open(os.path.join(BASE_DIR, "style.css")) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

mapping_effectifs = {"NN": "Inconnu", "01": "1-2", "02": "3-5", "03": "6-9", "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199", "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999", "51": "2000-4999", "52": "5000-9999", "53": "10 000+"}

# --- PROMPT ---
with open("GEMINI.md", encoding="utf-8") as f:
    instruction_protocol = f.read()

expert_prompt = f"""Tu es un automate de prospection de haute précision. 
PROTOCOLE À SUIVRE :
{instruction_protocol}

TA MISSION :
Exécute la requête de prospection Insee demandée. Ne réponds à aucune question hors-sujet.
Si le secteur n'est pas clair ou si tu ne connais pas le code NAF, utilise l'outil search_naf_code."""

# --- CONFIGURATION IA ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

# --- INTERFACE ---
st.title("IA Prospector Web")
user_prompt = st.text_input("Que recherchez-vous ?", placeholder="Ex: Les entreprises du secteur bancaire à Lille avec plus de 20 salariés...")
btn_run = st.button("🚀 Analyser", width='stretch')

if btn_run and user_prompt:
    if not client:
        st.error("ERREUR : Clé API Google manquante.")
    else:
        with st.status("🧠 Réflexion de l'IA en cours...", expanded=True) as status:
            try:
                # Utilisation du modèle spécifique demandé par l'utilisateur
                chat = client.chats.create(
                    model="gemini-3.1-flash-lite-preview", 
                    config={
                        "tools": [fetch_sirene_data, search_naf_code],
                        "system_instruction": expert_prompt,
                    }
                )
                response = chat.send_message(user_prompt)
                st.markdown(response.text)
                status.update(label="✅ Analyse terminée !", state="complete")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

# --- AFFICHAGE (ROBUSTE) ---
st.markdown("---")
# On filtre les fichiers non vides (> 0 octets)
list_of_files = [f for f in glob.glob(os.path.join(EXPORT_DIR, "*.csv")) if os.path.getsize(f) > 0]

if list_of_files:
    latest_file = max(list_of_files, key=os.path.getctime)
    try:
        df = pd.read_csv(latest_file, dtype={'Siret': str})
        st.subheader(f"📊 Résultats : {len(df)} entreprises")
        st.dataframe(df, width='stretch')
        with open(latest_file, "rb") as f:
            st.download_button("📥 Télécharger CSV", f, os.path.basename(latest_file), "text/csv", width='stretch')
    except Exception as e:
        st.error(f"Erreur de lecture : {e}")
else:
    st.info("Aucune donnée disponible. Lancez une recherche.")
