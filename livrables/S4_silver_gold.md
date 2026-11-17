# S4 · PySpark : construire Silver puis Gold

Groupe : Groupe 05 · Mesures : 21/10/2026 · Oussama : Data Owner et Rédacteur. Les statuts CIF, règles de survie et fusions floues attendent toujours l'arbitrage du Data Owner. Tag prévu : `seance-4`.

## 1. Silver et quarantaine (US-21, US-22)

Script réellement exécuté : `pipelines/transform_s4.py --batch-id L-2026-10-14`. Malgré le titre du gabarit, l'implémentation actuelle est en pandas/SQLAlchemy, pas en PySpark; ne pas annoncer PySpark comme technologie exécutée.

| Traitement | Table | Lignes traitées | Garde-fou |
|---|---|---:|---|
| Nettoyage des espaces, casse et accents d'identité | clients CRM et CIF | 140 000 | Les valeurs sources restent en Bronze et les identifiants Bronze sont conservés. |
| Parse date, normalisation téléphone et email, mapping pays par référentiel | clients CRM et CIF | 140 000 | Aucune coordonnée n'est inventée; une valeur non reconnue reste à surveiller. |
| Restauration d'un zéro de CP seulement si le couple CP/commune est référencé | clients CRM et CIF | 140 000 évalués | Aucun zéro ajouté sans correspondance dans `silver.ref_postal`. |
| Classement de qualité | `silver.client` | 41 510 `A_SURVEILLER`, 98 490 `VALIDE` | Les cas à surveiller sont conservés, pas supprimés. |

Invariant :

| Table | Bronze | Silver | Rejetées | Écart |
|---|---:|---:|---:|---:|
| Clients CRM | 100 000 | 100 000 | 0 | 0 |
| Clients CIF | 40 000 | 40 000 | 0 | 0 |
| Contrats | 100 000 | non implémenté | non implémenté | non mesuré |
| Sinistres | 100 000 | non implémenté | non implémenté | non mesuré |

Le script ne remplit pas encore `dq.rejets`; les anomalies de client sont conservées avec `statut_qualite='A_SURVEILLER'`. Les contrats et sinistres ne sont pas transformés en Silver par ce pipeline.

Idempotence vérifiée par deux exécutions successives : 140 000 lignes Silver, 126 033 lignes Gold, 140 000 références xref, 13 967 paires CRM-CIF fusionnées à chaque exécution.

## 2. Porte S : bronze contre silver (US-23)

| Règle | Sévérité | Taux bronze mesuré | Taux silver | Écart | Explication |
|---|---|---:|---|---|---|
| RQ-001 | Bloquante | 99,200 % | non mesuré | n/a | Contrats non transformés. |
| RQ-003 | Avertissement | 87,998 % | non mesuré | n/a | Téléphones manquants conservés; le traitement n'est pas rejoué comme expectation. |
| RQ-005 | Avertissement | 98,474 % sur les adresses FR | non mesuré | n/a | Contrôle métier complet CP/commune non rejoué sur Silver. |
| RQ-009 | Bloquante | 99,800 % | type normalisé; taux non mesuré | n/a | Les 200 valeurs source inconnues restent à surveiller. |
| RQ-010 | Bloquante | 99,400 % | non mesuré | n/a | Contrats non transformés. |

La porte S complète n'est pas franchie : les attentes bloquantes doivent être exécutées sur Silver pour les entités et les règles concernées. Aucune amélioration de taux n'est revendiquée sans mesure.

## 3. Dédoublonnage et golden record (US-24, US-25)

| Paramètre | Valeur | Justification |
|---|---|---|
| Normalisation testée | Trim, minuscules, suppression d'accents | Évaluation reproductible par `pipelines/evaluate_pairs_s4.py`. |
| Clé exacte de rapprochement de production | Identité + prénom + naissance + CP, chaque valeur non vide et unique par système | Évite les homonymes ambigus; cas non uniques laissés séparés. |
| Score candidat évalué | RapidFuzz ratio pondéré : identité 55 %, prénom 15 %, naissance 20 %, CP 10 % | Mesuré sur le CSV des 200 paires étiquetées. |
| Seuil fuzzy testé | 0,85 | 200 paires : précision 99 % (1 FP), rappel 98 % (2 FN); CRM-CIF seul, 50 paires : 100 %/100 % dans cet échantillon. |
| Fusion fuzzy en production | Aucune | Une seule erreur de faux positif est déjà observée au global; décision Data Owner requise avant fusion. |

| Mesure | Résultat |
|---|---:|
| Paires étiquetées | 200 (100 positives, 100 négatives; 150 CRM-CRM et 50 CRM-CIF) |
| Paires exactes CRM-CIF fusionnées dans ce lot | 13 967 |
| Groupes Gold | 126 033 |
| Paires dans une file de revue | Non implémentée; les candidats flous ne sont pas fusionnés. |
| Paires labels évaluées à 0,85 : précision / rappel | 99 % / 98 % global; 100 % / 100 % sur 50 CRM-CIF |

Le CSV des labels ne contient que 50 cas CRM-CIF; ces taux ne garantissent pas la performance sur toute la population. Le cas « Société Meunier » n'est pas isolé dans le livrable faute d'une sélection métier vérifiée; le script actuel ne doit pas être interprété comme preuve de son golden record.

Règle technique provisoire de survie : CRM prioritaire, sinon CIF, puis première valeur non nulle pour identité, adresse, téléphone et email. Ce n'est pas une décision validée. Les statuts CIF et les valeurs métier conflictuelles doivent être arbitrés par le Data Owner avant diffusion.

## 4. Gold et client actif (US-27)

| Table Gold | Lignes | Écart/rejet | État |
|---|---:|---:|---|
| `gold.client_unique` | 126 033 | 0 rejet au chargement | Construit; 13 967 rapprochements exacts CRM-CIF. |
| `gold.xref_identifiants` | 140 000 | 0 orphelin | Chaque xref référence un client Gold. |
| `contrat_certifie` | non créée | non mesuré | À implémenter. |
| `sinistre_certifie` | non créée | non mesuré | À implémenter. |

Le nombre `ACTIF` Gold est 55 602, comme le calcul CD-001 du lot (contrat en cours et cotisation à jour dans les trois derniers mois, à la référence 14/10/2026). La vue SQL `v_client_actif` n'est pas créée. Les CIF sans type de personne sont provisoirement classés `INACTIF`; cette convention doit être validée par le Data Owner, donc le statut Gold ne doit pas encore être publié.

Les clients ne sont pas rejetés; ils sont conservés et parfois marqués à surveiller. L'impact sur les contrats orphelins n'est pas calculé puisque les tables Gold contrat/sinistre n'existent pas.

## 5. Traçabilité (US-28)

| Donnée attendue | État de la preuve |
|---|---|
| Société Meunier | À sélectionner et valider avec le groupe; ne pas choisir un homonyme automatiquement. |
| Code postal à zéro initial | Aucun `00000` dans CRM mesuré; cas précis et identifiants de ligne à retrouver dans les sources avant revendication. |
| Adresse de sinistre | Bronze existe, mais transformation Silver/BAN et Gold sinistre non implémentées. |

Pour les clients, la chaîne technique disponible est `gold.xref_identifiants` → `silver.client` → `bronze.crm_client` ou `bronze.cif_clients`; elle conserve `silver_row_id`, `bronze_row_id` et le lot en Silver. Les trois exemples demandés ne sont donc pas tous prouvés à ce stade.

## 6. Critères de fin

- [x] Conservation des clients CRM/CIF : Silver + rejets = Bronze.
- [x] Deux exécutions reproduisent les mêmes volumes clients Silver/Gold/xref.
- [ ] Porte S complète : tests manquants sur les règles bloquantes et tables contrat/sinistre.
- [ ] Tables certifiées et vue unique `v_client_actif`.
- [ ] Trois exemples de lineage validés, dont contrat et sinistre.

## 7. Difficultés et reprise

- Difficultés : clés normalisées répétées, contrainte FK entre xref et Gold, et limites de taille des insertions SQL; la fusion est limitée aux clés uniques et les écritures sont faites en blocs.
- Reprise : script rejoué idempotemment sur le lot `L-2026-10-14`; pas de restauration du volume de données.
- À faire autrement : approuver les statuts et règles de survie avant de traiter le résultat comme Gold publiable.
