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
        # --- PURGE TOTALE DE LA RAM ---
        st.session_state.results_df = None
        st.session_state.logs_history = []

        with st.status("🧠 Analyse et Extraction...", expanded=True) as status:
            try:
                st.write("🌍 Analyse du bassin d'emploi...")
                geo_agent = client.chats.create(model=MODEL_SIRENE, config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())], 
                    system_instruction="""Tu es un expert en géographie française. 
TON OBJECTIF : Lister les codes postaux d'une zone demandée.
RÈGLES STRICTES :
1. Limite-toi à la ville demandée et ses communes limitrophes DIRECTES (rayon de 5-10km max).
2. Ne liste JAMAIS tout un département (ex: pas de jokers 13*).
3. Si la zone est trop vaste, privilégie les centres économiques.
4. Réponds uniquement par les codes séparés par des virgules."""
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
                    volume_msg = f"J'ai identifié {total} entreprises. Je lance l'enrichissement individuel (1 par 1) avec {MODEL_PHONE}."
                    st.session_state.logs_history.append(f"📢 **Annonce** : {volume_msg}")
                    st.write(f"🔍 {volume_msg}")
                    
                    progress = st.progress(0)
                    
                    # Enrichissement INDIVIDUEL (1 par 1)
                    for i in range(total):
                        row = st.session_state.results_df.iloc[i]
                        etab_info = f"- {row['Nom']} (SIRET: {row['Siret']}) à {row['Adresse']}"
                        
                        search_chat = client.chats.create(model=MODEL_PHONE, config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())], 
                            system_instruction="""Tu es un expert en OSINT. 
TON OBJECTIF : Trouver le téléphone direct de CET établissement.
RECHERCHE : "[Nom] [Ville] [Adresse] téléphone".
RÉPONSE : Un objet JSON unique {"Siret": "...", "Telephone": "..."}.
Si introuvable : "Non trouvé"."""
                        ))
                        
                        phone_resp = search_chat.send_message(f"Trouve le téléphone pour cet établissement :\n{etab_info}")
                        
                        try:
                            # Extraction robuste du JSON
                            clean_text = phone_resp.text
                            if "```json" in clean_text:
                                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                            elif "```" in clean_text:
                                clean_text = clean_text.split("```")[1].split("```")[0].strip()
                            
                            json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                            if json_match:
                                res = json.loads(json_match.group())
                                res_norm = {k.lower(): v for k, v in res.items()}
                                tel_raw = str(res_norm.get('telephone', 'Non trouvé'))
                                
                                # --- NORMALISATION DU TÉLÉPHONE ---
                                if tel_raw and tel_raw != "Non trouvé":
                                    # Garde uniquement les chiffres
                                    digits = re.sub(r'\D', '', tel_raw)
                                    # Gestion +33
                                    if digits.startswith('33') and len(digits) > 10:
                                        digits = '0' + digits[2:]
                                    # Formatage 0X XX XX XX XX
                                    if len(digits) == 10:
                                        tel = f"{digits[0:2]} {digits[2:4]} {digits[4:6]} {digits[6:8]} {digits[8:10]}"
                                    else:
                                        tel = tel_raw # Garde tel quel si format inconnu
                                else:
                                    tel = "Non trouvé"
                                
                                st.session_state.results_df.at[i, 'Téléphone'] = tel
                                st.session_state.logs_history.append(f"📞 `{row['Nom']}` : {tel}")
                        except:
                            st.session_state.results_df.at[i, 'Téléphone'] = "Erreur"

                        progress.progress(min((i + 1) / total, 1.0))
                    
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
