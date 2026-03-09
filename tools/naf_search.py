import httpx
import os

def search_naf_code(sector_query: str) -> str:
    """
    Recherche DYNAMIQUE d'un code NAF (APE) via l'API Tabular de data.gouv.fr.
    Source : Nomenclature d'activités française (NAF rev. 2)
    """
    # ID de la ressource NAF sur data.gouv.fr (Nomenclature Insee)
    # https://www.data.gouv.fr/fr/datasets/nomenclature-dactivites-francaise-naf/
    resource_id = "387034c5-8463-4475-802c-4712066d588f" 
    
    # Détermination de l'URL de l'API
    env = os.getenv("DATAGOUV_API_ENV", "prod").lower()
    base_url = "https://tabular-api.data.gouv.fr/api/" if env == "prod" else "https://tabular-api.preprod.data.gouv.fr/api/"
    url = f"{base_url}resources/{resource_id}/data/"
    
    params = {
        "page": 1,
        "page_size": 10,
        "Libellé__icontains": sector_query # Recherche insensible à la casse dans le libellé
    }
    
    try:
        with httpx.Client() as client:
            resp = client.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            records = data.get("data", [])
            if not records:
                return f"Aucun code NAF trouvé pour '{sector_query}'. Essayez un synonyme."
            
            results = []
            for rec in records:
                code = rec.get("Code")
                libelle = rec.get("Libellé")
                if code and libelle:
                    results.append(f"- {code} : {libelle}")
            
            return "Résultats trouvés dans la nomenclature Insee :\n" + "\n".join(results)
            
    except Exception as e:
        return f"Erreur lors de la recherche NAF : {str(e)}"
