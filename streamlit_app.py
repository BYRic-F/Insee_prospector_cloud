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
from tools.enricher_tools import update_company_phone

load_dotenv()

st.set_page_config(page_title="IA Prospector Web", layout="wide")

# --- INITIALISATION RAM ---
if 'results_df' not in st.session_state:
    st.session_state.results_df = None
if 'logs_history' not in st.session_state:
    st.session_state.logs_history = []

# --- WRAPPER DE SÉCURITÉ (MODE RAM) ---
def fetch_sirene_data(q: str, append: bool = False) -> str:
    """
    Extrait les données Sirene. 
    Les données sont écrites dans un fichier temporaire puis chargées en RAM.
    """
    filename = "sirene_export_temp.csv"
    res = fetch_sirene_data_raw(q=q, filename=filename, append=append)
    
    # Après chaque appel, on synchronise le fichier avec la RAM
    target_path = os.path.join("exports", filename)
    if os.path.exists(target_path):
        st.session_state.results_df = pd.read_csv(target_path, dtype={'Siret': str})
    
    return res

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

# --- Configuration IA (VERROUILLÉ) ---
with open("GEMINI.md", encoding="utf-8") as f:
    instruction_protocol = f.read()

expert_prompt = f"""Tu es un moteur d'extraction SIRENE de HAUTE PRÉCISION.
TON OBJECTIF : Délivrer des données d'une pureté absolue (Zéro pollution commerciale).

SYNTAXE CERTIFIÉE (STRICTE - ZÉRO ERREUR 400) :
1. FILTRE NAF : Tu DOIS utiliser `activitePrincipaleUniteLegale` (le siège social).
2. STRUCTURE : `q=activitePrincipaleUniteLegale:XXXXX AND periode(etatAdministratifEtablissement:A) AND codePostalEtablissement:YYYYY AND trancheEffectifsEtablissement:[ZZ TO 53]`
3. PLAGES : Pour les secteurs larges, utilise les plages Solr sur l'unité légale (ex: `activitePrincipaleUniteLegale:[52.10 TO 52.29]`).
4. JOKER INTERDIT : Ne jamais utiliser `*`. Le format `XX.XX` est obligatoire.

RÈGLES TECHNIQUES :
- Segmentation : Blocs de 10 codes postaux maximum. 
- Toujours répéter l'intégralité du filtre sur chaque bloc.
- Effectifs : >20=[12 TO 53], >50=[21 TO 53], >100=[22 TO 53], >200=[31 TO 53].

{instruction_protocol}"""

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
MODEL_ID = "gemini-3.1-flash-lite-preview"

st.title("IA Prospector Web")
st.caption("Moteur d'extraction Intelligent - Cloud Ready (RAM Only)")
st.markdown("---")

user_prompt = st.text_input("Que recherchez-vous ?", placeholder="Ex: Les entreprises de logistique à Marseille de plus de 200 salariés...")
btn_run = st.button("🚀 Lancer la prospection", width='stretch')

if btn_run and user_prompt:
    if not client: st.error("Clé API manquante.")
    else:
        # Nettoyage RAM avant nouvelle recherche
        st.session_state.results_df = None
        st.session_state.logs_history = []
        
        # Supprimer le fichier temporaire précédent s'il existe
        temp_file = os.path.join("exports", "sirene_export_temp.csv")
        if os.path.exists(temp_file): os.remove(temp_file)

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
                st.write("📡 Extraction Sirene (Filtrage en cours)...")
                extraction_chat = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(
                    tools=[fetch_sirene_data, get_full_naf_taxonomy, search_naf_by_keyword], 
                    system_instruction=expert_prompt
                ))
                resp_ext = extraction_chat.send_message(f"Prospection : {user_prompt}. Zone : {geo_info}.")
                
                # Persistence Logs RAM
                history = extraction_chat.get_history()
                for entry in history:
                    for part in entry.parts:
                        if part.function_call: 
                            st.session_state.logs_history.append(f"🛠️ Appel : `{part.function_call.name}`\n```json\n{json.dumps(part.function_call.args, indent=2)}\n```")
                        if part.function_response: 
                            st.session_state.logs_history.append(f"📥 Réponse : {str(part.function_response.response)[:500]}...")
                        if part.text: 
                            st.session_state.logs_history.append(f"💬 IA: {part.text}")

                # 2. CHARGEMENT (Synchronisation finale)
                if st.session_state.results_df is not None:
                    total = len(st.session_state.results_df)
                    st.success(f"✅ {total} établissements trouvés.")
                    
                    # 3. ENRICHISSEMENT (Direct RAM via st.session_state)
                    st.write("🔍 Récupération des contacts...")
                    progress = st.progress(0)
                    for i, row in st.session_state.results_df.iterrows():
                        search_chat = client.chats.create(model=MODEL_ID, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], system_instruction="Donne uniquement le téléphone."))
                        phone_resp = search_chat.send_message(f"Téléphone de {row['Nom']} à {row['Adresse']}")
                        
                        # Mise à jour directe de la RAM
                        st.session_state.results_df.at[i, 'Téléphone'] = phone_resp.text.strip()
                        progress.progress((i + 1) / total)
                    
                    status.update(label="Prospection terminée !", state="complete")
                    st.rerun()
                else: st.error("Aucun résultat.")
            except Exception as e: st.error(f"Erreur : {e}")

# --- RÉSULTATS (AFFICHAGE DEPUIS LA RAM) ---
st.markdown("---")
if st.session_state.results_df is not None:
    df = st.session_state.results_df
    st.subheader(f"📊 Résultats ({len(df)} entreprises)")
    
    t1, t2, t3 = st.tabs(["📋 Liste", "📊 Analyse", "📝 Journal IA"])
    with t1:
        st.dataframe(df, use_container_width=True)
        # Génération du CSV en mémoire pour le téléchargement
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        st.download_button("📥 Télécharger CSV", data=csv_buffer.getvalue(), file_name="prospects.csv", mime="text/csv")
    with t2:
        if 'Adresse' in df.columns:
            df['CP'] = df['Adresse'].str.extract(r'(\d{5})')
            st.plotly_chart(px.pie(df, names='CP', title="Répartition géographique"))
    with t3:
        for log in st.session_state.logs_history:
            st.markdown(log)
else:
    st.info("Utilisez la barre de recherche ci-dessus pour démarrer.")
