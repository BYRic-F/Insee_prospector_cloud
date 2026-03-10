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
from tools.sirene_engine import fetch_sirene_data_as_list

load_dotenv()

st.set_page_config(page_title="IA Prospector Web", layout="wide")

# --- GESTION RAM (SESSION STATE) ---
if 'results_df' not in st.session_state:
    st.session_state.results_df = None
if 'logs_history' not in st.session_state:
    st.session_state.logs_history = []

def fetch_sirene_data(q: str, append: bool = False) -> str:
    """
    Outil pour l'IA : Extrait les données et les stocke en RAM.
    Isolation totale par session utilisateur.
    """
    # Force l'exclusion des NN/00 si le filtre n'est pas présent
    if "trancheEffectifsEtablissement" not in q:
        q = f"({q}) AND trancheEffectifsEtablissement:[01 TO 53]"
    
    new_data = fetch_sirene_data_as_list(q)
    if not new_data:
        return "Aucun établissement trouvé pour cette requête."
    
    new_df = pd.DataFrame(new_data)
    
    if append and st.session_state.results_df is not None:
        # Fusion et suppression des doublons par SIRET
        combined_df = pd.concat([st.session_state.results_df, new_df], ignore_index=True)
        st.session_state.results_df = combined_df.drop_duplicates(subset=['Siret'])
    else:
        st.session_state.results_df = new_df
        
    return f"SUCCÈS : {len(new_data)} établissements récupérés en mémoire vive."

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
TON OBJECTIF : Délivrer des données d'une pureté totale en suivant scrupuleusement le protocole GEMINI.md.

{instruction_protocol}"""

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

# Modèles selon GEMINI.md
MODEL_SIRENE = "gemini-3-flash-preview"
MODEL_PHONE = "gemini-3.1-flash-lite-preview"

st.title("IA Prospector Web")
st.caption("Moteur d'extraction Intelligent - Haute Précision & Isolation RAM")
st.markdown("---")

user_prompt = st.text_input("Que recherchez-vous ?", placeholder="Ex: Les industries de plus de 50 salariés à Lyon...")
btn_run = st.button("🚀 Lancer la prospection", width='stretch')

if btn_run and user_prompt:
    if not client: st.error("Clé API manquante.")
    else:
        st.session_state.results_dcdf = None
        st.session_state.logs_history = []

        with st.status("🧠 Analyse et Extraction...", expanded=True) as status:
            try:
                st.write("🌍 Analyse du bassin d'emploi...")
                geo_agent = client.chats.create(model=MODEL_SIRENE, config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())], 
                    system_instruction="Liste TOUS les codes postaux de la ville et de son agglomération. Réponds uniquement par les codes séparés par des virgules."
                ))
                geo_resp = geo_agent.send_message(f"Codes postaux de l'agglomération de : {user_prompt}")
                geo_info = geo_resp.text.strip()
                st.info(f"📍 Zone : {geo_info}")

                st.write("📡 Extraction Sirene (Filtrage en cours)...")
                extraction_chat = client.chats.create(model=MODEL_SIRENE, config=types.GenerateContentConfig(
                    tools=[fetch_sirene_data, get_full_naf_taxonomy, search_naf_by_keyword], 
                    system_instruction=expert_prompt
                ))
                resp_ext = extraction_chat.send_message(f"Prospection : {user_prompt}. Zone : {geo_info}.")
                
                # Capture des logs et affichage dynamique des NAF
                history = extraction_chat.get_history()
                for entry in history:
                    for part in entry.parts:
                        if part.function_call:
                            # Détection et affichage des NAF extraits de la requête q
                            if part.function_call.name == "fetch_sirene_data":
                                q_arg = part.function_call.args.get("q", "")
                                naf_matches = re.findall(r'activitePrincipaleEtablissement:\[?([0-9.* TO ]+)\]?', q_arg)
                                if naf_matches:
                                    st.info(f"🧬 NAF identifiés : `{', '.join(naf_matches)}`")
                            
                            st.session_state.logs_history.append(f"🛠️ Appel : `{part.function_call.name}`\n```json\n{json.dumps(part.function_call.args, indent=2)}\n```")
                        if part.function_response: 
                            st.session_state.logs_history.append(f"📥 Réponse : {str(part.function_response.response)[:500]}...")
                        if part.text: 
                            st.session_state.logs_history.append(f"💬 IA: {part.text}")

                if st.session_state.results_df is not None:
                    total = len(st.session_state.results_df)
                    st.success(f"✅ {total} établissements trouvés.")
                    
                    # Annonce obligatoire du volume pour les logs
                    volume_msg = f"J'ai identifié {total} entreprises. Je lance l'enrichissement par lots de 5 avec {MODEL_PHONE}."
                    st.session_state.logs_history.append(f"📢 **Annonce** : {volume_msg}")
                    st.write(f"🔍 {volume_msg}")
                    
                    progress = st.progress(0)
                    
                    # Enrichissement par LOTS DE 5 (Modèle Lite)
                    for i in range(0, total, 5):
                        batch = st.session_state.results_df.iloc[i:i+5]
                        batch_info = "\n".join([f"- {row['Nom']} (SIRET: {row['Siret']}) à {row['Adresse']}" for _, row in batch.iterrows()])
                        
                        search_chat = client.chats.create(model=MODEL_PHONE, config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())], 
                            system_instruction="""Tu es un expert en OSINT et recherche de coordonnées d'entreprises. 
TON OBJECTIF : Trouver le numéro de téléphone direct de chaque établissement fourni.

STRATÉGIE DE RECHERCHE :
1. Pour chaque ligne, effectue une recherche Google ciblée : "[Nom de l'entreprise] [Ville] [Adresse] téléphone".
2. Analyse prioritairement les 'snippets' (extraits) Google Maps, Pages Jaunes, ou le site officiel.
3. Le numéro doit être au format français : 0X XX XX XX XX ou +33...
4. Sois persévérant : si une recherche ne donne rien, essaie avec le SIRET ou le nom seul.

CONTRAINTE DE RÉPONSE :
- Tu DOIS renvoyer un objet JSON pour CHAQUE SIRET du lot (exactement {len(batch)} objets).
- Si le téléphone est introuvable après 2 tentatives de recherche, mets "Non trouvé".
- Réponds UNIQUEMENT par un tableau JSON pur, sans texte avant ou après."""
                        ))
                        
                        phone_resp = search_chat.send_message(f"Lot de {len(batch)} recherches prioritaires :\n{batch_info}")
                        
                        try:
                            # Extraction du JSON
                            json_match = re.search(r'\[.*\]', phone_resp.text, re.DOTALL)
                            if json_match:
                                results = json.loads(json_match.group())
                                for res in results:
                                    # Nettoyage strict du SIRET (garde uniquement les chiffres)
                                    siret_raw = str(res.get('Siret', ''))
                                    siret_clean = re.sub(r'\D', '', siret_raw)
                                    
                                    if siret_clean:
                                        # Comparaison robuste avec les SIRET du DataFrame (eux aussi nettoyés)
                                        df_sirets = st.session_state.results_df['Siret'].astype(str).str.replace(r'\D', '', regex=True)
                                        idx = st.session_state.results_df[df_sirets == siret_clean].index
                                        if not idx.empty:
                                            tel = res.get('Telephone', 'Non trouvé')
                                            st.session_state.results_df.at[idx[0], 'Téléphone'] = tel
                        except Exception as e:
                            st.warning(f"Erreur lot {i//5 + 1}")
                            st.session_state.logs_history.append(f"⚠️ Erreur lot {i//5 + 1}: {str(e)}")

                        progress.progress(min((i + 5) / total, 1.0))
                    
                    # --- EXPORT PHYSIQUE ---
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    safe_prompt = re.sub(r'[^a-zA-Z0-9]', '_', user_prompt)[:30]
                    export_name = f"prospects_{safe_prompt}_{timestamp}"
                    
                    # Export CSV
                    csv_path = f"exports/{export_name}.csv"
                    st.session_state.results_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
                    
                    # Export Logs
                    log_path = f"exports/{export_name}_logs.txt"
                    with open(log_path, "w", encoding="utf-8") as f_log:
                        f_log.write("\n\n".join(st.session_state.logs_history))
                    
                    st.session_state.logs_history.append(f"💾 **Export physique terminé** : `{csv_path}` et `{log_path}`")
                    
                    status.update(label="Prospection terminée !", state="complete")
                    st.rerun()
                else: st.error("Aucun résultat.")
            except Exception as e: st.error(f"Erreur : {e}")

# --- RÉSULTATS (RAM) ---
st.markdown("---")
if st.session_state.results_df is not None:
    df = st.session_state.results_df
    st.subheader(f"📊 Résultats ({len(df)} entreprises)")
    
    t1, t2, t3 = st.tabs(["📋 Liste des prospects", "📈 Analyses graphiques", "📝 Journal IA"])
    
    with t1:
        st.dataframe(df, use_container_width=True)
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        st.download_button("📥 Télécharger CSV", data=csv_buffer.getvalue(), file_name="prospects.csv", mime="text/csv")
    
    with t2:
        col1, col2 = st.columns(2)
        effectifs_map = {
            'NN': 'Non renseigné', '00': '0 salarié', '01': '1-2 salariés', '02': '3-5 salariés',
            '03': '6-9 salariés', '11': '10-19 salariés', '12': '20-49 salariés', '21': '50-99 salariés',
            '22': '100-199 salariés', '31': '200-249 salariés', '32': '250-499 salariés',
            '41': '500-999 salariés', '42': '1000-1999 salariés', '51': '2000-4999 salariés',
            '52': '5000-9999 salariés', '53': '10000+ salariés'
        }
        df_plot = df.copy()
        df_plot['Label Effectifs'] = df_plot['Tranche Effectifs'].astype(str).map(effectifs_map).fillna('Inconnu')
        
        with col1:
            fig_pie = px.pie(df_plot, names='Label Effectifs', title="Répartition par Effectifs", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        if 'Adresse' in df.columns:
            df_plot['CP'] = df_plot['Adresse'].str.extract(r'(\d{5})').fillna('Inconnu').astype(str)
            cp_counts = df_plot['CP'].value_counts().reset_index()
            cp_counts.columns = ['Code Postal', 'Nombre']
            cp_counts = cp_counts.sort_values('Code Postal')
            with col2:
                fig_bar = px.bar(cp_counts, x='Code Postal', y='Nombre', title="Par Code Postal", color='Nombre')
                fig_bar.update_xaxes(type='category')
                st.plotly_chart(fig_bar, use_container_width=True)
                
    with t3:
        for log in st.session_state.logs_history:
            st.markdown(log)
else:
    st.info("Lancez une recherche ci-dessus.")
