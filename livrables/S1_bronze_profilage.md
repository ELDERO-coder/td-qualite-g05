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
| 1 | … | … | … | … |
| 2 | … | … | … | … |
| 3 | … | … | … | … |
| 4 | … | … | … | … |
| 5 | … | … | … | … |

Motifs (conformes / non conformes) :

| Attribut | Motif testé | Lignes conformes | Lignes non conformes | Exemple de valeur non conforme |
|---|---|---|---|---|
| Code postal | … | … | … | … |
| Téléphone | … | … | … | … |
| Pays | … | … | … | … |

Preuve (notebook, requête) : [À COMPLÉTER]

## 4. Dictionnaire du CIF (US-04)

| Colonne d'origine | Nom proposé | Type | Justification chiffrée (comment l'avez-vous déduit ?) |
|---|---|---|---|
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |
| … | … | … | … |

## 5. Trois définitions du « client actif » (US-09)

| Direction | Définition utilisée | Nombre de clients | Écart avec la définition de la fiche CD-001 |
|---|---|---|---|
| Commerciale | … | … | … |
| Sinistres | … | … | … |
| Risques | … | … | … |

Conséquence pour la gouvernance, en trois phrases : [À COMPLÉTER]

## 6. Critères de fin (cochez, avec la preuve si elle n'est pas dans une section ci-dessus)

- [ ] Les sept tables bronze existent et chaque ligne porte ses quatre métadonnées.
- [ ] La porte B ne montre aucun écart de comptage ni de somme de contrôle.
- [ ] Relancer l'ingestion du même lot ne crée aucun doublon.
- [ ] Un écart introduit volontairement fait échouer la porte.
- [ ] RQ-021 est écrite dans `dq.dq_history` (couche BRONZE).

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : [À COMPLÉTER]

Point de reprise utilisé (oui / non, lequel) : [À COMPLÉTER]

Ce que nous ferions autrement : [À COMPLÉTER]
