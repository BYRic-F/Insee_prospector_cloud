import pandas as pd
import os

def read_prospects_csv(filename: str) -> str:
    """Lit le CSV de prospection pour l'IA."""
    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
    filepath = os.path.join(export_dir, filename)
    
    if not os.path.exists(filepath):
        return f"Erreur : Le fichier {filename} n'existe pas."
    
    try:
        df = pd.read_csv(filepath, dtype={'Siret': str})
        return df.to_json(orient="records")
    except Exception as e:
        return f"Erreur lors de la lecture : {str(e)}"

def update_company_phone(filename: str, siret: str, phone: str) -> str:
    """Met à jour le téléphone dans le CSV."""
    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
    filepath = os.path.join(export_dir, filename)
    
    if not os.path.exists(filepath):
        return f"Erreur : Le fichier {filename} n'existe pas."
    
    try:
        df = pd.read_csv(filepath, dtype={'Siret': str})
        
        if 'Téléphone' not in df.columns:
            df['Téléphone'] = ""
            
        df.loc[df['Siret'].astype(str) == str(siret), 'Téléphone'] = phone
        df.to_csv(filepath, index=False, encoding='utf-8')
        return f"Succès : Téléphone mis à jour pour {siret}."
    except Exception as e:
        return f"Erreur lors de la mise à jour : {str(e)}"
