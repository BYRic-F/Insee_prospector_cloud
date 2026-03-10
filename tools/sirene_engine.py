import logging
import os
import httpx
import time
from typing import List, Dict, Any

def fetch_sirene_data_as_list(q: str) -> List[Dict[str, Any]]:
    """
    Fetch data from Insee Sirene API v3.11 and returns a list of dicts.
    NO FILE IO. Pure RAM.
    """
    api_key = os.getenv("DATAGOUV_API_KEY")
    if not api_key:
        return []

    base_url = "https://api.insee.fr/api-sirene/3.11/siret"
    headers = {
        "X-INSEE-Api-Key-Integration": api_key,
        "Accept": "application/json",
    }
    
    results = []
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
                    break
                
                data = resp.json()
                etablissements = data.get("etablissements", [])
                if not etablissements:
                    break
                
                for etab in etablissements:
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

                    results.append({
                        "Siret": etab.get("siret"),
                        "Nom": nom or "Inconnu",
                        "Code NAF": naf or "Inconnu",
                        "Tranche Effectifs": effectifs,
                        "Adresse": full_address or "Inconnu",
                        "Téléphone": "" # Initialisé vide pour l'enrichissement
                    })

                next_cursor = data.get("header", {}).get("curseurSuivant")
                if not next_cursor or next_cursor == params["curseur"] or len(results) >= 1000:
                    break
                params["curseur"] = next_cursor
                time.sleep(0.1)
    except:
        pass

    return results
