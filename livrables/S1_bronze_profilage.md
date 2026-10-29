# S1 · Stack Docker, profilage, construction de bronze

Groupe : [À COMPLÉTER]  ·  Date : [À COMPLÉTER]  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-1`

Rappel : un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Inventaire des sources (US-01)

| Source | Table | Lignes | Clé primaire | Observation chiffrée |
|---|---|---|---|---|
| crm | client | 13 | client_id | 100000 |
| crm | contrat | 9 | contrat_id | 100000 |
| crm | sinistre | 10 | sinistre_id | 100000 |
| crm | type_contrat | 3 | code_type | 12 |
| cif | clients | 10 | column0 | 40000 |
| cif | compte | 4 | column0 | 45000 |
| cif | pays | 2 | code_pays | 250 |

Preuve (notebook, requête) : [notebooks/S1_bronze_profilage.ipynb]

## 2. Bronze et porte B (US-02, US-03)

Méthode d'ingestion en trois lignes (lecture, conversion, métadonnées, relance du lot) : 

1. Lecture des sept tables CIF et CRM et conservant les valeurs d'origine avec coerce_float=False
2. Conversion des colonnes en texte, ajout des métadonnées _batch_id et _source_system
3. Suppression des lignes du lot dans Bronze, puis réinsertion des données. La relance ne crée aucun doublon

Réconciliation RQ-021 (comptage) et RQ-022 (somme de contrôle), pour le lot mesuré :

| Table bronze | Lignes source | Lignes bronze | Écart de comptage | Écart de somme de contrôle |
|---|---|---|---|---|
| crm_client | 100000 | 100000 | 0 | 0 |
| crm_contrat | 100000 | 100000 | 0 | 0 |
| crm_sinistre | 100000 | 100000 | 0 | 0 |
| crm_type_contrat | 12 | 12 | 0 | 0 |
| cif_clients | 40000 | 40000 | 0 | 0 |
| cif_compte | 45000 | 45000 | 0 | 0 |
| cif_pays | 250 | 250 | 0 | 0 |

Épreuves de la porte (à documenter, avec la preuve de chacune) :

| Épreuve | Résultat obtenu | Preuve |
|---|---|---|
| Relance du même lot : doublons créés | Pas de doublon, toujours 385 262 lignes | notebooks/S1_bronze_profilage.ipynb — cellules US-02 |
| Écart introduit volontairement sur une copie : la porte échoue-t-elle ? | Oui, cela a échoué | notebooks/S1_bronze_profilage.ipynb — test US-03 |
| Un problème de conversion rencontré (décimales, NULL, accents) et sa correction | Conversion de DECIMAL en flottant (184,10 -> 184,1). Prévention par coerce_float=False | pipelines/01_ingest_bronze.py |

## 3. Profil de crm.client (US-06, US-07)

Au moins cinq constats chiffrés.

| N° | Colonne | Indicateur (nulls, vides, distincts, motif…) | Valeur mesurée | Ce que cela change pour la qualité |
|---|---|---|---|---|
| 1 | nom | Valeurs manquantes | 4 277 | Absence pour les personnes morales qui possèdent une raison sociale |
| 2 | raison_sociale | Valeurs manquantes | 95 723 | Absence pour les personnes physiques qui possèdent un nom |
| 3 | cp | Codes postaus à 4 chiffres | 1 456 | certains codes ont perdu le 0 du début, qu'il faudra corriger |
| 4 | telephone | Numéro qui ne respecte pas le regex proposé | 886 | Il faudra réaliser une normalisation |
| 5 | pays | Valeurs absentes du référentiel | 3 050 | Des valeurs doivent êtres harmonisées avec les codes du référentiel |

Motifs (conformes / non conformes) :

| Attribut | Motif testé | Lignes conformes | Lignes non conformes | Exemple de valeur non conforme |
|---|---|---|---|---|
| Code postal | Exactement 5 chiffres pour les adresses françaises | 93 981 | 1 456 | 1000 pour Bourg-en-Bresse qui devrait être 01000 |
| Téléphone | Regex qui accepte les formats français et internationaux | 89 115 | 886 | 3397633710 |
| Pays | Appartenance au référentiel silver.ref_pays | 96 950 | 3 050 | France, fr, UK, ZZ |

Preuve (notebook, requête) : [notebooks/S1_bronze_profilage.ipynb - US-06 et US-07 + reports/ydata_profiling_client.html]

## 4. Dictionnaire du CIF (US-04)

| Colonne d'origine | Nom proposé | Type | Justification chiffrée (comment l'avez-vous déduit ?) |
|---|---|---|---|
| column0 | Identifient client CIF | VARCHAR(7) | 40000 Valeurs Distinctes sur 40000 lignes avec une longueure de 7 caractères |
| column1 | Nom | VARCHAR(50) | 731 VD, la longueure max trouvé est de 31, on peut mettre 50 en prévision |
| column2 | Prénom | VARCHAR(50) | 180 VD, la longueure max trouvé est de 31, on peut mettre 50 en prévision |
| column3 | Date de naissance | DATE | 21 081 VD, format JJ/MM/AAAA |
| column4 | Adresse | VARCHAR(50) | 9811 VD, peut être rapidement assez long, il faut prévoir large |
| column5 | Code postal | VARCHAR(8) | 188 VD, toujours de ;ongueur 4 ou 8 |
| column6 | Ville | VARCHAR(50) | 172 VD, des villes peuvent avoir un long nom |
| column7 | Pays | VARCHAR(2) | 9 VD, cela sera toujours à 2 d'après le référentiel |
| column8 | Téléphone | VARCHAR(10) | 33676 VD, cela sera toujours à 10 |
| column9 | Adresse e-mail | VARCHAR(50) | 21128 VD, peut-être rapidement long |

## 5. Trois définitions du « client actif » (US-09)

| Direction | Définition utilisée | Nombre de clients | Écart avec la définition de la fiche CD-001 |
|---|---|---|---|
| Commerciale | 50 508 | au moins un contrat | + 12 459 |
| Sinistres | 44 116 | un contrat en cours a la date de référence | + 6 067 |
| Risques | 38 049 | contrat en cours et à jour de cotisation sur 3 mois glissants | 0 (CD-01) |

Conséquence pour la gouvernance, en trois phrases : [À COMPLÉTER]

## 6. Critères de fin (cochez, avec la preuve si elle n'est pas dans une section ci-dessus)

- [x] Les sept tables bronze existent et chaque ligne porte ses quatre métadonnées. (aller voir US-02 et US-03)
- [x] La porte B ne montre aucun écart de comptage ni de somme de contrôle. (aller voir US-03, cellule 14)
- [x] Relancer l'ingestion du même lot ne crée aucun doublon.
- [x] Un écart introduit volontairement fait échouer la porte. (aller voir US-03, cellule 15)
- [x] RQ-021 est écrite dans `dq.dq_history` (couche BRONZE). (aller voir US-03 - preuve de l'enregistrement)

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : Surtout des problèmes concernant la compréhension de certains contrôles et certaines consignes.

Point de reprise utilisé (oui / non, lequel) : ?

Ce que nous ferions autrement : Mieux s'organiser surtout pour les rôles, mais difficiles à distance.
