# IA Prospector

**Ce projet a été développé spécifiquement pour l'entreprise RH Performances afin de lui permettre d'enrichir sa base de données CRM avec des prospects.** 

**Lien pour tester l'application :**
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://inseeprospectorcloud.streamlit.app/)

Dans le cadre du recrutement et du conseil RH, il était impératif d'obtenir des résultats d'une pertinence absolue. Ce travail de développement s'est concentré sur l'élimination du "bruit" numérique pour ne livrer que des entreprises actives, structurées (avec salariés) et correspondant précisément aux métiers cibles.

---

## Aperçu de l'application

### Interface de résultats et Export CSV
La page d'accueil permet de visualiser instantanément les entreprises identifiées et de télécharger le fichier structuré pour une intégration CRM directe.

![Page d'accueil - Résultats et CSV](images/Page_accueil1.png)

### Analyses et Visualisations Graphiques
L'application génère des graphiques dynamiques pour analyser la répartition géographique et sectorielle des prospects identifiés.

![Page Graphique - Visualisations](images/Page_graphique2.png)

---

## Optimisations de Haute Précision (V3.0)

Suite à une batterie de 50 tests intensifs couvrant l'industrie, les services et le commerce, les améliorations suivantes ont été intégrées :

### Nomenclature NAF 2008 (Sirene Native)
- **Remplacement de la NAF 2025** : Le moteur utilise désormais la nomenclature NAF rév. 2 de 2008, garantissant une compatibilité à 100% avec les codes réels de l'API Sirene actuelle (ex: `47.78A` pour l'optique).
- **Moteur de chargement robuste** : Détection intelligente des colonnes, insensible aux accents, aux espaces invisibles ou aux changements d'en-têtes.
- **Stratégie de "Persévérance"** : Si la recherche par mot-clé échoue, l'IA scanne l'intégralité des 1700 codes NAF pour identifier la cible exacte.

### Enrichissement OSINT & "Pro Tip" Mobile
- **Liens cliquables (`tel:`)** : Tous les numéros de téléphone sont désormais générés sous forme de liens URI `tel:`. Dans le **Journal IA**, un simple clic sur le numéro lance l'appel (idéal pour la prospection sur smartphone).
- **Normalisation Unitaires** : Chaque établissement est traité individuellement par `gemini-3.1-flash-lite-preview` pour distinguer les agences locales des sièges sociaux.

### Extraction Sirene Stabilisée
- **Usage de `periode()`** : Application systématique de la fonction Insee `periode()` pour filtrer l'état administratif actif et l'activité principale.
- **Filtrage des effectifs** : Traduction automatique des besoins métiers (ex: "plus de 10 salariés") en tranches techniques Insee (ex: `[11 TO 53]`).
- **Segmentation Géo (Batching)** : Découpage intelligent des requêtes pour les zones denses (Paris, Lyon, Marseille) afin d'éviter les erreurs de saturation de l'API. Gestion des différentes granularité : Région/Département/Agglomeration

---

## Architecture & Modèles

- **Interface** : Streamlit (Python)
- **Modèle Recherche NAF & Sirene** : `gemini-3-flash-preview`
- **Modèle Enrichissement Téléphonique** : `gemini-3.1-flash-lite-preview`
- **Source de vérité** : Fichier NAF 2008 Insee (Converti et nettoyé en CSV)

## Utilisation pour RH Performances

1. **Précision** : Indiquez le métier et la taille d'entreprise (ex: "Cabinets d'avocats de plus de 10 salariés à Lille").
2. **Validation** : Vérifiez dans le **Journal IA** (Onglet 3) les codes NAF identifiés par l'IA.
3. **Action** : Utilisez les liens `tel:` dans les logs pour contacter directement les décideurs.
4. **Export** : Téléchargez le CSV final pour l'importer dans votre CRM.

---
*Développé pour une prospection B2B de haute précision — Validé par 50 tests sectoriels (100% de succès).*
