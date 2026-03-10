import csv
import logging
import os
import httpx
import time
from typing import List, Dict, Any

def fetch_sirene_data(q: str, filename: str = "sirene_export.csv", append: bool = False) -> str:
    """
    Fetch data from Insee Sirene API v3.11 with cursor pagination.
    If append is True, results are added to the existing CSV file.
    """
    api_key = os.getenv("DATAGOUV_API_KEY")
    if not api_key:
        return "Erreur : La variable d'environnement DATAGOUV_API_KEY n'est pas définie."

    base_url = "https://api.insee.fr/api-sirene/3.11/siret"
    headers = {
        "X-INSEE-Api-Key-Integration": api_key,
        "Accept": "application/json",
    }
    
    all_results = []
    sirets_seen = set()
    
    # Si on est en mode append, on charge les SIRET déjà présents pour éviter les doublons
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_dir = os.path.join(current_dir, "exports")
    filepath = os.path.join(export_dir, filename)
    
    if append and os.path.exists(filepath):
        try:
            with open(filepath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sirets_seen.add(row["Siret"])
        except: pass

    params = {
        "q": q,
        "nombre": 100,
        "curseur": "*"
    }

    try:
        with httpx.Client() as client:
            while True:
                resp = client.get(base_url, headers=headers, params=params, timeout=30.0)
                
                if resp.status_code != 200:
                    try: err = resp.json()
                    except: err = resp.text
                    return f"Erreur API Sirene ({resp.status_code}) : {err}"
                
                data = resp.json()
                etablissements = data.get("etablissements", [])
                
                if not etablissements:
                    break
                
                for etab in etablissements:
                    siret = etab.get("siret")
                    if not siret or siret in sirets_seen:
                        continue
                    sirets_seen.add(siret)

                    unite = etab.get("uniteLegale", {})
                    periodes = etab.get("periodesEtablissement", [{}])
                    periode0 = periodes[0] if periodes else {}
                    adresse = etab.get("adresseEtablissement", {})

                    nom = unite.get("denominationUniteLegale")
                    if not nom:
                        nom_p = f"{unite.get('nomUniteLegale', '')} {unite.get('prenom1UniteLegale', '')}".strip()
                        nom = nom_p if nom_p else periode0.get("enseigne1Etablissement")
                    
                    naf = periode0.get("activitePrincipaleEtablissement")
                    if not naf:
                        naf = unite.get("activitePrincipaleUniteLegale")
                    
                    effectifs = etab.get("trancheEffectifsEtablissement", "NN")
                    
                    addr_parts = [
                        adresse.get("numeroVoieEtablissement"),
                        adresse.get("typeVoieEtablissement"),
                        adresse.get("libelleVoieEtablissement"),
                        adresse.get("codePostalEtablissement"),
                        adresse.get("libelleCommuneEtablissement")
                    ]
                    full_address = " ".join([str(p) for p in addr_parts if p]).strip()

                    all_results.append({
                        "Siret": siret,
                        "Nom": nom or "Inconnu",
                        "Code NAF": naf or "Inconnu",
                        "Tranche Effectifs": effectifs,
                        "Adresse": full_address or "Inconnu"
                    })

                next_cursor = data.get("header", {}).get("curseurSuivant")
                if not next_cursor or next_cursor == params["curseur"] or len(all_results) >= 1000:
                    break
                params["curseur"] = next_cursor
                time.sleep(0.1)

    except Exception as e:
        return f"Erreur extraction : {str(e)}"

    if not all_results and not append:
        return "Aucun résultat trouvé."

    # Exportation (W pour nouveau, A pour ajout)
    try:
        mode = "a" if append and os.path.exists(filepath) else "w"
        write_header = not (append and os.path.exists(filepath))
        
        os.makedirs(export_dir, exist_ok=True)
        with open(filepath, mode=mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Siret", "Nom", "Code NAF", "Tranche Effectifs", "Adresse"])
            if write_header: writer.writeheader()
            writer.writerows(all_results)
        
        return f"SUCCÈS : {len(all_results)} nouveaux établissements ajoutés/exportés."
    except Exception as e:
        return f"Erreur écriture CSV : {str(e)}"
