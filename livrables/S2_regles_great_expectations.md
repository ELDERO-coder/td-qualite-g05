# S2 · Great Expectations : des règles en tests automatisés

Groupe : Groupe 05 · Date des mesures : 21/10/2026 · Oussama : Data Owner et Rédacteur. Les décisions métier restent à arbitrer et à consigner par le Data Owner avant validation de la porte. Étiquette prévue : `seance-2`.

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Règles en tests (US-10)

Une ligne par règle. L'expectation porte son `rule_id` ; la base et la table visées sont des paramètres.

| Règle | Table bronze | Expectation (type) | Lignes testées | Lignes en échec | Taux de réussite | Sévérité retenue (bloquante / avertissement) |
|---|---|---|---|---|---|---|
| RQ-001 | `bronze.crm_contrat` | `expect_column_pair_values_A_to_be_greater_than_B` | 100 000 | 800 | 99,200 % | Bloquante |
| RQ-002 | `bronze.crm_contrat` | âge révolu >= 18 au début du contrat | 92 996 | 301 | 99,676 % | Bloquante |
| RQ-003 | `bronze.crm_client` souscripteurs | indicateur non NULL/vide/blanc dans le domaine `[True]` | 49 898 | 5 989 | 87,998 % | Avertissement |
| RQ-005 | `bronze.crm_client` pays FR | `expect_column_values_to_match_regex` `^[0-9]{5}$` | 95 437 | 1 456 | 98,474 % | Avertissement |
| RQ-009 | `bronze.crm_client` | `expect_column_values_to_be_in_set` prospect/souscripteur/assure | 100 000 | 200 | 99,800 % | Bloquante |
| RQ-010 | `bronze.crm_contrat` | `expect_column_values_to_be_in_set` 12/24/36/60 | 100 000 | 600 | 99,400 % | Bloquante |
| RQ-020 | `bronze.crm_client` et `bronze.crm_contrat` | non-nullité et unicité des clés, contrôlées séparément | 200 000 au total | 0 | 100 % | Bloquante |

Pièges rencontrés et traitement (nul, vide, blanc ; adresses étrangères ; comparaisons exactes) :

| Règle | Piège | Chiffre avant correction | Chiffre après correction | Preuve |
|---|---|---|---|---|
| RQ-003 | NULL, vide et blanc ne sont pas équivalents; tous trois échouent à la règle | 1 995 NULL + 3 994 vides/blancs | 0 après mesure logique du prédicat (aucune correction des données) | `pipelines/run_ge_s2.py` |
| RQ-005 | Le motif ne s'applique qu'aux adresses françaises | 4 563 clients sont hors du sous-ensemble FR | 1 456 échecs parmi 95 437 clients FR | `pipelines/run_ge_s2.py` |

Suite de validation : `pipelines/run_ge_s2.py`; invocation `docker exec dq_jupyter python pipelines/run_ge_s2.py --batch-id L-2026-10-14`. Écrit dans `dq.dq_history`, couche BRONZE. Le code retour `1` est attendu en présence des échecs aux règles bloquantes RQ-001, RQ-002, RQ-009 et RQ-010.

## 2. Lignes en échec (US-11)

Export complet local : `reports/s2_failures.json` (ignoré par Git). Échantillon technique de 20 lignes : `reports/s2_failures_sample.json` (ignoré par Git). Les deux fichiers sont reproductibles et ne contiennent que les identifiants de ligne Bronze et les règles, sans coordonnées ni noms.

| Règle | Famille d'erreur observée | Nombre de lignes de l'échantillon | Cause probable | Action proposée (à qui ?) |
|---|---|---|---|---|
| RQ-001 | Date de fin antérieure ou égale au début | 3 de l'échantillon | Incohérence des bornes du contrat | Data Steward : qualifier la correction; ne pas corriger automatiquement. |
| RQ-002 | Souscripteur mineur à la date de souscription | 3 de l'échantillon | Contrat antérieur à 18 ans ou date d'identité erronée | Data Owner : confirmer exceptions et interprétation métier. |
| RQ-003 | Téléphone absent, vide ou blanc | 3 de l'échantillon | Coordonnée manquante ou inutilisable | Data Steward : définir collecte et traitement sans inventer de valeur. |
| RQ-005/RQ-009/RQ-010 | CP non conforme, domaine personne ou durée hors liste | 11 au total dans l'échantillon | Formats/domaines sources à qualifier | Data Steward et Data Owner : valider les normalisations autorisées. |

## 3. Âge à la date de début du contrat (US-13, RQ-002)

| Date de référence | Définition de l'âge | Lignes en échec | Preuve |
|---|---|---|---|
| Date de début du contrat | Âge révolu à la signature, calculé avec mois/jour d'anniversaire | 301 sur 92 996 | `pipelines/run_ge_s2.py`, RQ-002 |
| Date du jour (21/10/2026) | 152 des 301 cas mineurs à la signature sont devenus majeurs | 149 personnes restent mineures aujourd'hui parmi les 92 996 testées | `pipelines/run_ge_s2.py`, comparaison `age_debut`/`age_jour` |

Un âge calculé à la date du jour effacerait les 152 cas devenus majeurs depuis la signature; RQ-002 porte sur l'éligibilité lors de la souscription et doit utiliser `date_debut`.

## 4. Mesure de référence sur bronze (US-15)

Écrite dans `dq.dq_history`, couche BRONZE, lot `L-2026-10-14`; les taux ci-dessus proviennent de la dernière exécution GE du 21/10/2026.

| Dimension | Règles | Taux moyen | Règle la plus faible | Constat |
|---|---|---|---|---|
| Unicité | RQ-020 | 100 % | RQ-020 | Zéro échec sur les clés client et contrat, 200 000 tests combinés. |
| Complétude | RQ-003 | 87,998 % | RQ-003 | Sous le seuil avertissement de 98 % pour téléphone souscripteur. |
| Validité | RQ-002, RQ-005, RQ-009, RQ-010 | Moyenne non agrégée : périmètres et sévérités distincts | RQ-002 (99,676 %) parmi ces règles | RQ-002/RQ-009/RQ-010 échouent au seuil bloquant de 100 %; RQ-005 atteint 98,474 %. |
| Cohérence | RQ-001 | 99,200 % | RQ-001 | 800 périodes invalides; sous le seuil bloquant de 100 %. |

Synthèse : « Voici la qualité de ce qui nous est livré : les clés CRM sont uniques, mais le brut contient des anomalies bloquantes de période, d'âge, de domaine et de durée; elles doivent être traitées ou mises en quarantaine avant Silver/Gold. »

## 5. Critères de fin

- [x] Chaque expectation porte l'identifiant de sa règle.
- [x] Le runner accepte `--batch-id` et `--url` pour les bases compatibles.
- [x] La mesure de référence est dans `dq.dq_history` avec lot, couche, table, lignes testées et échecs.
- [x] Les règles sont exécutables d'un seul geste; code retour non nul pour les échecs bloquants.

## 6. Difficultés, écarts avec l'attendu, reprise

Difficultés : les colonnes Bronze sont du texte; parsing explicite des dates nécessaire. Première écriture GE a aussi révélé une contrainte de taux calculé en base, corrigée en utilisant le vrai nombre d'éléments testés.

Point de reprise : aucun point de restauration de base utilisé; lot Bronze S1 conservé.

À améliorer : faire valider par le Data Owner les cas d'âge et les transformations autorisées avant de franchir la porte S.
