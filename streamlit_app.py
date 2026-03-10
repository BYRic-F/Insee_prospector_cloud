import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import glob
import time
import json
import httpx
import re
import asyncio
from io import StringIO, BytesIO
import google.genai as genai
from google.genai import types
from dotenv import load_dotenv
from tools.sirene_engine import fetch_sirene_data as fetch_sirene_data_raw
from tools.enricher_tools import read_prospects_csv, update_company_phone

load_dotenv()

st.set_page_config(page_title="IA Prospector Web", layout="wide")

# --- WRAPPER DE SÉCURITÉ POUR LE FICHIER ---
def fetch_sirene_data(q: str, append: bool = False) -> str:
    """Extrait les données Sirene. Le fichier est toujours 'sirene_export.csv'."""
    return fetch_sirene_data_raw(q=q, filename="sirene_export.csv", append=append)

# --- RÉFÉRENTIEL NAF 2025 ---
@st.cache_data
def load_naf_taxonomy():
    url = "https://www.insee.fr/fr/statistiques/fichier/8617910/Structure%20NAF%202025%20Maj%202024-10-04.xlsx"
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(url)
            df_raw = pd.read_excel(BytesIO(resp.content), engine="openpyxl", header=None)
            header_row = 0
            for i in range(min(15, len(df_raw))):
                row_vals = [str(x).lower() for x in df_raw.iloc[i]]
                if any("code" in v for v in row_vals) and any("libellé" in v for v in row_vals):
                    header_row = i
                    break
            df = pd.read_excel(BytesIO(resp.content), engine="openpyxl", header=header_row)
            code_col = next((c for c in df.columns if any(kw in str(c).lower() for kw in ['code', 'classe'])), df.columns[0])
            lib_col = next((c for c in df.columns if any(kw in str(c).lower() for kw in ['libellé', 'intitulé'])), df.columns[1])
            df = df[df[code_col].notna()].copy()
            df[code_col] = df[code_col].astype(str).str.strip()
            df = df[df[code_col].str.contains(r'\.', na=False)] 
            return df[[code_col, lib_col]].rename(columns={code_col: "code", lib_col: "libelle"})
    except: return pd.DataFrame(columns=["code", "libelle"])

NAF_DF = load_naf_taxonomy()

def get_full_naf_taxonomy(dummy: str = None) -> str:
    return NAF_DF.to_csv(index=False)

def search_naf_by_keyword(query: str) -> str:
    if NAF_DF.empty: return "Taxonomie non disponible."
    mask = NAF_DF['libelle'].str.contains(query, case=False, na=False)
    return NAF_DF[mask].head(50).to_csv(index=False)

# --- Configuration IA ---
with open("GEMINI.md", encoding="utf-8") as f:
    instruction_protocol = f.read()

expert_prompt = f"""Tu es un moteur d'extraction SIRENE de HAUTE PRÉCISION.
TON OBJECTIF : Délivrer des données d'une pureté absolue.

PROTOCOLE DE RIGUEUR (ZÉRO ERREUR) :
1. ANALYSE NAF : Identifie TOUS les codes pertinents via 'search_naf_by_keyword'. Ne devine jamais.
2. COPIER-COLLER : Si tu fais plusieurs appels (segmentation), tu DOIS copier-coller EXACTEMENT le même filtre NAF sur chaque appel. Toute omission d'un filtre sur un bloc est une faute grave.
3. PRÉCISION : Utilise les codes complets (ex: 62.01Z) ou les plages Solr explicites (ex: [10 TO 33]). Évite les jokers trop larges comme `52*` si tu as trouvé des codes plus précis.
4. SYNTAXE : Respecte le point dans les codes NAF. Toujours.

SEGMENTATION :
- Bloc de 10 codes postaux max. 
- Appel 1 : `append=False`. Suivants : `append=True`.

CORRESPONDANCE EFFECTIFS :
- > 20: [12 TO 53], > 50: [21 TO 53], > 100: [22 TO 53], > 200: [31 TO 53].

{instruction_protocol}"""

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
MODEL_ID = "gemini-3.1-flash-lite-preview"

st.title("IA Prospector Web")
st.caption("Intelligence Insee 2025 & Prospection Massive Segmentée")
st.markdown("---")

user_prompt = st.text_input("Que recherchez-vous ?", placeholder="Ex: Les industries de plus de 50 salariés à Nantes...")
btn_run = st.button("🚀 Lancer la prospection", width='stretch')

if btn_run and user_prompt:
    if not client: st.error("Clé API manquante.")
    else:
        with st.status("🧠 Analyse et Extraction...", expanded=True) as status:
            try:
                # 0. GÉO-ANALYSE
                st.write("🌍 Analyse du bassin d'emploi...")
                geo_agent = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())], 
                    system_instruction="Liste TOUS les codes postaux de la ville et de son agglomération. Réponds uniquement par les codes séparés par des virgules."
                ))
                geo_resp = geo_agent.send_message(f"Codes postaux de l'agglomération de : {user_prompt}")
                geo_info = geo_resp.text.strip()
                st.info(f"📍 Zone : {geo_info}")

                # 1. EXTRACTION
                st.write("📡 Extraction Sirene par blocs de 10...")
                extraction_chat = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(
                    tools=[fetch_sirene_data, get_full_naf_taxonomy, search_naf_by_keyword], 
                    system_instruction=expert_prompt
                ))
                resp_ext = extraction_chat.send_message(f"Prospection : {user_prompt}. Zone : {geo_info}.")
                
                # Logs
                history = extraction_chat.get_history()
                details = []
                for entry in history:
                    for part in entry.parts:
                        if part.function_call: details.append(f"🛠️ Appel : `{part.function_call.name}`\n```json\n{json.dumps(part.function_call.args, indent=2)}\n```")
                        if part.function_response: details.append(f"📥 Réponse : {str(part.function_response.response)[:500]}...")
                        if part.text: details.append(f"💬 IA: {part.text}")
                with open(os.path.join("exports", "last_logs.txt"), "w", encoding="utf-8") as f: f.write("\n\n---\n\n".join(details))

                # 2. CHARGEMENT
                target_path = os.path.join("exports", "sirene_export.csv")
                if os.path.exists(target_path):
                    df_temp = pd.read_csv(target_path)
                    st.success(f"✅ {len(df_temp)} établissements trouvés après segmentation.")
                    
                    # 3. ENRICHISSEMENT
                    st.write("🔍 Récupération des téléphones...")
                    progress = st.progress(0)
                    for i, row in df_temp.iterrows():
                        search_chat = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], system_instruction="Donne uniquement le téléphone."))
                        phone_resp = search_chat.send_message(f"Téléphone de {row['Nom']} à {row['Adresse']}")
                        update_company_phone("sirene_export.csv", str(row['Siret']), phone_resp.text.strip())
                        progress.progress((i + 1) / len(df_temp))
                    
                    status.update(label="Extraction terminée !", state="complete")
                    st.rerun()
                else: st.error("Aucun résultat.")
            except Exception as e: st.error(f"Erreur : {e}")

# --- RÉSULTATS ---
st.markdown("---")
csv_path = os.path.join("exports", "sirene_export.csv")
if os.path.exists(csv_path):
    df = pd.read_csv(csv_path, dtype={'Siret': str})
    t1, t2, t3 = st.tabs(["📋 Liste", "📊 Analyse", "📝 Journal IA"])
    with t1:
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Télécharger CSV", open(csv_path, "rb"), "prospects.csv")
    with t2:
        if 'Adresse' in df.columns:
            df['CP'] = df['Adresse'].str.extract(r'(\d{5})')
            st.plotly_chart(px.pie(df, names='CP', title="Répartition par Code Postal"))
    with t3:
        log_path = os.path.join("exports", "last_logs.txt")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f: st.markdown(f.read())
else:
    st.info("Lancez une recherche.")
