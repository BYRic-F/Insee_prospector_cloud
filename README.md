# 🚀 IA Prospector Web

IA Prospector Web est un moteur d'extraction et d'enrichissement de données d'entreprises intelligent. Il combine la puissance de l'API Insee Sirene v3.11 avec les capacités de réflexion de Google Gemini pour offrir une précision chirurgicale dans la génération de listes de prospection.

## ✨ Fonctionnalités Clés

- **Ciblage Intelligent (NAF)** : L'IA identifie automatiquement les codes NAF les plus pertinents à partir d'un référentiel Excel dynamique.
- **Précision Géographique** : Stratégie de segmentation (batching) pour couvrir des zones denses (Paris, Lyon, Marseille) sans dilution départementale.
- **Filtrage de Qualité** : Exclusion automatique des établissements fermés (état administratif) et des entreprises sans salariés (NN/00).
- **Enrichissement OSINT (1-par-1)** : Recherche unitaire des numéros de téléphone via Google Search avec un taux de succès supérieur à 95%.
- **Normalisation Automatique** : Tous les numéros sont uniformisés au format français `0X XX XX XX XX`.
- **Zéro Persistance (RAM Pure)** : Les données sont traitées exclusivement en mémoire vive pour garantir la confidentialité des recherches.

## 🛠️ Architecture Technique

- **Interface** : Streamlit (Python)
- **Modèle Identification & Extraction** : `gemini-3-flash-preview`
- **Modèle Enrichissement Téléphonique** : `gemini-3.1-flash-lite-preview`
- **API Source** : Insee Sirene v3.11 (Authentification par clé API)
- **Moteur de Recherche** : Google Search (via Gemini Tools)

## 📋 Prérequis

- Python 3.10+
- Une clé API Insee (DataGouv / Sirene)
- Une clé API Google AI Studio (Gemini)

## 🚀 Installation

1. **Cloner le projet**
   ```bash
   git clone <url-du-repo>
   cd datagouv-prospector-web
   ```

2. **Configurer l'environnement**
   Copiez le fichier d'exemple et remplissez vos clés :
   ```bash
   cp .env.example .env
   ```
   *Modifier le fichier `.env` avec vos accès.*

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Lancer l'application**
   ```bash
   streamlit run streamlit_app.py
   ```

## 🧠 Workflow du Protocole (GEMINI.md)

L'outil suit scrupuleusement un protocole de décision en 4 étapes :
1. **Analyse Géo** : Identification des codes postaux dans un rayon de 5-10km.
2. **Analyse NAF** : Identification des codes sectoriels via la taxonomie Insee.
3. **Extraction** : Appels successifs à Sirene avec consolidation en RAM.
4. **Enrichissement** : Recherche individuelle des coordonnées téléphoniques.

## 📥 Exportation

À la fin de chaque prospection, vous pouvez télécharger les résultats au format **CSV** directement depuis l'interface. Les fichiers sont encodés en `utf-8-sig` pour une compatibilité parfaite avec Excel.

---
*Développé pour une prospection B2B de haute précision.*
