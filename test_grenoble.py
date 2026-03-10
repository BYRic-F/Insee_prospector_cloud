import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def test_grenoble():
    api_key = os.getenv("DATAGOUV_API_KEY")
    base_url = "https://api.insee.fr/api-sirene/3.11/siret"
    headers = {"X-INSEE-Api-Key-Integration": api_key, "Accept": "application/json"}
    
    # Test 1: Exact code found by IA (26.11Y)
    q1 = "activitePrincipaleUniteLegale:26.11Y AND periode(etatAdministratifEtablissement:A) AND codePostalEtablissement:38*"
    # Test 2: Prefix with wildcard (26.11*)
    q2 = "activitePrincipaleUniteLegale:26.11* AND periode(etatAdministratifEtablissement:A) AND codePostalEtablissement:38*"
    
    for q in [q1, q2]:
        resp = httpx.get(base_url, headers=headers, params={"q": q, "nombre": 5})
        print(f"Query: {q}")
        if resp.status_code == 200:
            print(f"✅ {resp.json().get('header', {}).get('total', 0)} results.")
        else:
            print(f"❌ {resp.status_code}")

if __name__ == "__main__":
    test_grenoble()
