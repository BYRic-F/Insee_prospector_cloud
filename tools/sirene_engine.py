import csv
import logging
import os
import httpx
from typing import Optional

def fetch_sirene_data(q: str, filename: str = "sirene_export.csv") -> str:
    api_key = os.getenv("DATAGOUV_API_KEY")
    if not api_key: return "Erreur : Clé API manquante."

    base_url = "https://api.insee.fr/api-sirene/3.11/siret"
    headers = {"X-INSEE-Api-Key-Integration": api_key, "Accept": "application/json"}
    params = {"q": q, "nombre": 100}

    with httpx.Client() as client:
        try:
            resp = client.get(base_url, headers=headers, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e: return f"Erreur API : {str(e)}"

    etablissements = data.get("etablissements", [])
    if not etablissements: return "Aucun résultat trouvé."

    # Force le dossier exports à la racine du projet
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_dir = os.path.join(current_dir, "exports")
    if not os.path.exists(export_dir): os.makedirs(export_dir)
    
    # Nettoyage du nom de fichier pour éviter les caractères interdits
    safe_filename = "".join([c for c in filename if c.isalnum() or c in ('.', '_')]).strip()
    filepath = os.path.join(export_dir, safe_filename)

    results = []
    for etab in etablissements:
        unite = etab.get("uniteLegale", {})
        periode0 = etab.get("periodesEtablissement", [{}])[0]
        adresse = etab.get("adresseEtablissement", {})
        nom = unite.get("denominationUniteLegale") or f"{unite.get('nomUniteLegale', '')} {unite.get('prenom1UniteLegale', '')}".strip() or periode0.get("enseigne1Etablissement")
        addr_parts = [adresse.get("numeroVoieEtablissement"), adresse.get("typeVoieEtablissement"), adresse.get("libelleVoieEtablissement"), adresse.get("codePostalEtablissement"), adresse.get("libelleCommuneEtablissement")]
        full_address = " ".join([str(p) for p in addr_parts if p]).strip()

        results.append({
            "Siret": etab.get("siret"),
            "Nom": nom or "Inconnu",
            "Code NAF": periode0.get("activitePrincipaleEtablissement") or unite.get("activitePrincipaleUniteLegale") or "Inconnu",
            "Tranche Effectifs": etab.get("trancheEffectifsEtablissement") or "Inconnu",
            "Adresse": full_address or "Inconnu"
        })

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Siret", "Nom", "Code NAF", "Tranche Effectifs", "Adresse"])
        writer.writeheader()
        writer.writerows(results)
    
    return f"SUCCÈS_EXTRACTION : {len(results)} entreprises dans {safe_filename}"
