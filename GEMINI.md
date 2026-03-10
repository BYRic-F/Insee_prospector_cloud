# Instructions Système - Mode Prospection Insee

## 1. Protocole d'Exécution & API
- **URL** : `https://api.insee.fr/api-sirene/3.11/siret`
- **Authentification** : Header `X-INSEE-Api-Key-Integration` avec `$DATAGOUV_API_KEY`.

## 2. Syntaxe de Requête (STABILITÉ CERTIFIÉE)
- **Structure Impérative** : `q=activitePrincipaleUniteLegale:XXXXX AND periode(etatAdministratifEtablissement:A) AND codePostalEtablissement:YYYYY AND trancheEffectifsEtablissement:[ZZ TO 53]`
- **POURQUOI CETTE SYNTAXE ?** : C'est la seule qui garantit 0 erreur 400 et qui élimine les pollutions commerciales (ex: Auchan). Elle cible le "cœur de métier" actuel de l'entreprise.
- **NAF OBLIGATOIRE** : Toujours inclure `activitePrincipaleUniteLegale` (format `XX.XX`).

## 3. Filtrage & Effectifs
- **Tranches** : 12 (>20), 21 (>50), 22 (>100), 31 (>200).
- **Plages NAF (Unité Légale)** :
  * Industrie : `activitePrincipaleUniteLegale:[10.00 TO 33.99]`
  * Logistique : `activitePrincipaleUniteLegale:[52.10 TO 52.29]`
  * BTP : `activitePrincipaleUniteLegale:[41.00 TO 43.99]`

## 4. Segmentation
- Découpage par BLOCS DE 10 codes postaux maximum.
- 1er appel : `append=False`. Suivants : `append=True`.

## 5. Règle du Zéro Résultat
- Si l'API retourne 404, assume le résultat. Ne jamais supprimer le filtre NAF.
