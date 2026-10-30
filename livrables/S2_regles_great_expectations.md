# S2 · Great Expectations : des règles en tests automatisés

Groupe : [À COMPLÉTER]  ·  Date : [À COMPLÉTER]  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-2`

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Règles en tests (US-10)

Une ligne par règle. L'expectation porte son `rule_id` ; la base et la table visées sont des paramètres.

| Règle | Table bronze | Expectation (type) | Lignes testées | Lignes en échec | Taux de réussite | Sévérité retenue (bloquante / avertissement) |
|---|---|---|---|---|---|---|
| RQ-001 | crm_contrat | expect_column_pair_values_a_to_be_greater_than_b | 100 000 | 800 | 99.2 % | Bloquante |
| RQ-002 | crm_contrat | expect_column_values_to_be_between | 100 000 | 301 | 99.7 % | Bloquante |
| RQ-003 | crm_client | expect_column_values_to_not_be_null + expect_column_values_to_match_regex | 99 796 | 5 989 | 94 % | Avertissement |
| RQ-005 | crm_client | expect_column_values_to_match_regex | 95 437 | 1 456 | 98.5 % | Avertissement |
| RQ-009 | crm_client | expect_column_values_to_be_in_set | 100 000 | 200 | 99.8 % | Bloquante |
| RQ-010 | crm_contrat | expect_column_values_to_be_in_set | 100 000 | 600 | 99.4 % | Bloquante |
| RQ-020 | crm_sinistre + crm_contrat + crm_client + cif_clients | expect_column_values_to_not_be_null + expect_column_values_to_be_unique | 2 tests par ligne | 0 | 100 % | Bloquante |

Pièges rencontrés et traitement (nul, vide, blanc ; adresses étrangères ; comparaisons exactes) :

| Règle | Piège | Chiffre avant correction | Chiffre après correction | Preuve |
|---|---|---|---|---|
| RQ-003 | Distinguer les téléphones nuls, vides et blancs | Non mesuré | 5 989 échecs | Résultat cellule 23 US-10 |
| RQ-005 | Limiter le contrôle postal aux adresse française | Non mesuré | 1 456 échecs sur 95 437 adresse fr | Résultat cellule 23 US-10 |

Suites de validation (chemins) : 
- reports/ge/gx/expectations/assurconnect_bronze_cif_clients_suite.json
- reports/ge/gx/expectations/assurconnect_bronze_crm_client_suite.json
- reports/ge/gx/expectations/assurconnect_bronze_crm_contrat_suite.json
- reports/ge/gx/expectations/assurconnect_bronze_crm_sinistre_suite.json

## 2. Lignes en échec (US-11)

Export complet : [reports/echecs/lignes_en_echec_RQ-*.csv]. Échantillon commenté de 20 lignes : [reports/echecs/echantillon_20_lignes_RQ009.csv]

| Règle | Famille d'erreur observée | Nombre de lignes de l'échantillon | Cause probable | Action proposée (à qui ?) |
|---|---|---|---|---|
| RQ-009 | Casse incorrect (souscripteur, SOUSCRIPTEUR) | 6 | Saisie non standardisé | Normaliser la casse (Data Engineer) |
| RQ-009 | Accent non conforme | 8 | Différence avec le référentiel | Harmoniser les valeurs (Data Steward) |
| RQ-009 | Abréviation | 2 | Absence de liste contrôlée à la saisie | Imposer une liste de valeur |
| RQ-009 | Valeur hors domaine | 4 | Mélange entre statut et type de personne | Revoir les catégories (Data Owner) |

## 3. Âge à la date de début du contrat (US-13, RQ-002)

| Date de référence | Définition de l'âge | Lignes en échec | Preuve |
|---|---|---|---|
| Date de début du contrat | Age révolu du souscripteur à la signature du contrat | 301 | Résultats US-13 du notebook |
| Date du jour (1/10/26) | Age révolu du souscripteur à la date référence fixe | 157 | Résultats US-13 du notebook |

Un cas où « à la date du jour » donne un autre résultat, et pourquoi :
Sur 92 996 contrats, 144 changent de verdict selon la date utilisée. Une personne peut avoir été mineur au moment de la signature, et être majeure à la date de référence. Il pourrait être considéré à tort comme conforme si on utilise l'âge de la date de référence.

## 4. Mesure de référence sur bronze (US-15)

Écrite dans `dq.dq_history`, couche BRONZE, lot : L-2026-10-01

| Dimension | Règles | Taux moyen | Règle la plus faible | Constat |
|---|---|---|---|---|
| Unicité | RQ-020 | 100 % | RQ-020 | Aucun doublon de clé primaire détecté |
| Complétude | RQ-003 | 94 % | RQ-033 | 5 989 téléphones manquants chez les souscripteurs |
| Validité | RQ-002, RQ-005, RQ-009, RQ-010 | 99.23 % | RQ-005, 98.47 % | Codes postaus invalides, mineurs à la signature et valeurs hors domaine |
| Cohérence | RQ-001, RQ-002 | 99.20 % | RQ-001 | 800 contrats présentent une incohérence entre les dates de début et de fin |

Phrase de synthèse (« Voici la qualité de ce qui nous est livré : … ») : 
Les clés primaires sont conformes à 100 %, mais nous avons vus des anomalies, comme les 5 989 téléphones manquants. Certaines règles bloquantes restent sous leur seuil de conformité.

## 5. Critères de fin

- [x] Chaque expectation porte l'identifiant de sa règle.
- [x] La même suite se relance sur une autre base ou table sans modification de code.
- [x] La mesure de référence est dans `dq.dq_history` avec le lot, la couche, les lignes testées et les échecs.
- [x] Les règles sont exécutables d'un seul geste (script ou notebook relançable de bout en bout).

## 6. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : PLus ou moins la mêê choses que pour la séance 1 avec l'organisation et la compréhension des tâches à réaliser.

Point de reprise utilisé (oui / non, lequel) : Non

Ce que nous ferions autrement : On pourrait mieux s'organiser, mais avec le distanciel, cela n'est pas forcément facile.
