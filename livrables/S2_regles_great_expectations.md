# S2 · Great Expectations : des règles en tests automatisés

Groupe : 05  ·  Date : 21/10/2026  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-2`

Mesure exécutée sur le lot Bronze `L-2026-10-14`. La requête SQL produit le prédicat de chaque règle ; Great Expectations vérifie ensuite que `conforme` vaut `True`. Chaque expectation porte `meta.rule_id`. Preuve : `pipelines/run_s2_quality.py`.

## 1. Règles en tests (US-10)

| Règle | Table bronze | Expectation GE | Lignes testées | Lignes en échec | Taux de réussite | Sévérité du catalogue* |
|---|---|---|---:|---:|---:|---|
| RQ-001 | `crm_contrat` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 800 | 99,200 % | Bloquante |
| RQ-002 | `crm_contrat` (souscripteurs personnes physiques) | `expect_column_values_to_be_in_set(conforme, [True])` | 91 802 | 300 | 99,673 % | Bloquante |
| RQ-003 | `crm_client` (souscripteurs) | `expect_column_values_to_be_in_set(conforme, [True])` | 49 898 | 5 989 | 87,998 % | Avertissement |
| RQ-005 | `crm_client` (pays `FR`) | `expect_column_values_to_be_in_set(conforme, [True])` | 95 437 | 1 456 | 98,474 % | Avertissement |
| RQ-009 | `crm_client` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 200 | 99,800 % | Bloquante |
| RQ-010 | `crm_contrat` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 600 | 99,400 % | Bloquante |
| RQ-020 | `crm_client` / `client_id` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 0 | 100,000 % | Bloquante |
| RQ-020 | `crm_contrat` / `contrat_id` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 0 | 100,000 % | Bloquante |
| RQ-020 | `crm_sinistre` / `sinistre_id` | `expect_column_values_to_be_in_set(conforme, [True])` | 100 000 | 0 | 100,000 % | Bloquante |

*Sévérités lues dans `dq.regle` / `initdb/02_dq_regles.sql` ; le fichier précise qu'elles restent à valider par le Data Owner. Les 9 résultats sont dans `reports/us10_ge_results.csv` et historisés dans `dq.dq_history` (couche `BRONZE`).

Pièges et traitement :

| Règle | Piège | Mesure avant correction | Après correction | Preuve |
|---|---|---:|---|---|
| RQ-003 | Ne pas confondre `NULL`, chaîne vide et espaces | 1 995 `NULL` + 3 994 vides/blancs parmi 49 898 souscripteurs | Aucune correction en Bronze ; les cas restent distincts dans le contrôle | `reports/us10_ge_results.csv`, `pipelines/run_s2_quality.py` |
| RQ-005 | Ne tester que les adresses françaises ; compter un CP absent comme échec | 1 456 échecs sur 95 437 adresses `FR` | Aucune correction en Bronze | `reports/us10_ge_results.csv` |
| RQ-009 | Comparaison exacte du domaine, sans normalisation silencieuse | 200 valeurs hors domaine sur 100 000 | Aucune correction en Bronze | `reports/us10_ge_results.csv` |
| RQ-010 | La durée est stockée en texte ; seuls `12`, `24`, `36`, `60` sont valides | 600 valeurs hors domaine sur 100 000 | Aucune correction en Bronze | `reports/us10_ge_results.csv` |

## 2. Lignes en échec (US-11)

Export complet : `reports/us11_echecs_complets.csv`. Échantillon équilibré de 20 lignes avec règle, identifiant Bronze, valeur contrôlée et motif : `reports/us11_echantillon_20.csv`.

| Règle | Famille d'erreur observée | Échecs | Cause probable | Action proposée |
|---|---|---:|---|---|
| RQ-001 | Fin de contrat antérieure ou égale au début | 800 | Dates incohérentes dans la source CRM | Faire vérifier le contrat par le gestionnaire CRM ; ne pas réécrire Bronze |
| RQ-002 | Souscripteur personne physique mineur à la date de début | 300 | Souscription avant 18 ans ou date de naissance à vérifier | Confirmer la règle et les exceptions métier avec le Data Owner |
| RQ-003 | Téléphone nul, vide ou blanc | 5 989 | Coordonnée absente ou non saisie | Demander une mise à jour au processus CRM ; ne pas inventer de numéro |
| RQ-005 | Code postal français absent ou différent de 5 chiffres | 1 456 | Saisie tronquée, zéro initial perdu ou valeur non conforme | Vérifier avec le référentiel postal en Silver |
| RQ-009 | Type de personne hors domaine exact | 200 | Variantes de casse, accent ou libellé (`client`, `SOUSCRIPTEUR`, etc.) | Normalisation contrôlée en Silver après validation du domaine |
| RQ-010 | Durée de garantie hors domaine | 600 | Valeurs observées : `6`, `9`, `18`, `48`, `120` | Vérifier les produits avec le Data Owner avant mapping |

## 3. Âge à la date de début du contrat (US-13, RQ-002)

| Date de référence | Définition | Lignes testées | Lignes en échec | Preuve |
|---|---|---:|---:|---|
| Date de début du contrat | Âge révolu à cette date, souscripteur personne physique | 91 802 | 300 | `reports/us13_age_reference.csv` |
| Date du jour de l'exécution | Même personne, âge révolu à la date courante de la base | 91 802 | 148 | `reports/us13_age_reference.csv` |

152 personnes étaient mineures au début du contrat mais ont atteint 18 ans depuis. Contrôler à la date du jour masque donc des non-conformités historiques ; la règle métier doit être évaluée à la date de début.

## 4. Mesure de référence sur Bronze (US-15)

Mesures du lot `L-2026-10-14` inscrites dans `dq.dq_history` avec couche, règle, table, lignes testées et échecs. Moyennes calculées par dimension à partir des règles exécutées :

| Dimension | Règles mesurées | Taux moyen | Règle la plus faible | Constat |
|---|---|---:|---|---|
| Unicité | RQ-020 | 100,000 % | Aucune différence : les 3 clés sont à 100 % | 0 doublon ou NULL observé |
| Complétude | RQ-003 | 87,998 % | RQ-003 : 87,998 % | 5 989 téléphones de souscripteurs absents, vides ou blancs |
| Validité | RQ-002, RQ-005, RQ-009, RQ-010 | 99,337 % | RQ-005 : 98,474 % | Les CP français sont le point faible de validité |
| Cohérence | RQ-001 | 99,200 % | RQ-001 : 99,200 % | 800 contrats ont des dates incohérentes |

**Synthèse :** pour ce lot Bronze, les trois clés sont uniques, mais la complétude des téléphones de souscripteurs atteint seulement 87,998 %. Le Data Steward documente les anomalies et propose leur traitement en Silver ; le Data Owner valide les sévérités et les règles métier.

## 5. Critères de fin

- [x] Chaque expectation porte l'identifiant de sa règle dans ses métadonnées.
- [ ] Relance sur une autre base possible par `--url`, mais les tables et règles restent définies dans le script.
- [x] Les mesures sont enregistrées dans `dq.dq_history` avec lot et couche.
- [x] Une commande exécute les règles, les exports d'échecs et la mesure d'âge.

Commande : `docker exec dq_jupyter python pipelines/run_s2_quality.py --batch-id L-2026-10-14`

## 6. Difficultés, écarts avec l'attendu, reprise

- Difficulté : traduire les contrôles multi-colonnes en prédicats vérifiables par GE ; les règles restent explicites dans le SQL du script et le booléen est validé par GE.
- Temps perdu : non chronométré.
- Point de reprise : aucun ; la mesure a utilisé le lot Bronze existant.
- À améliorer : rendre le périmètre base/table entièrement paramétrable avant de réutiliser la suite sur d'autres sources.
