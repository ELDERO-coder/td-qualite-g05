# S3 · Soda Core : intégrité entre tables, portes en SodaCL

Groupe : 05  ·  Date : 21/10/2026  ·  Rédacteur : Data Steward  ·  Étiquette : `seance-3`

Mesures des règles inter-tables sur le lot Bronze `L-2026-10-14`. Les scans Soda sur `crm` et `bronze` ont été enregistrés dans `reports/us12_soda_crm_*.json` et `reports/us12_soda_bronze.json`.

## 1. Checks et configuration (US-12)

Configuration : `soda/configuration.yml` (sources séparées `crm`, `bronze`, `silver`, `gold`). Checks CRM : `soda/checks/client_checks.yml`, `contrat_checks.yml`, `sinistre_checks.yml`. Checks Bronze : `soda/checks/bronze_checks.yml`.

| Règle | Couche / table | Résultat Soda | Valeur mesurée | Code retour |
|---|---|---|---:|---:|
| RQ-001 | CRM et Bronze / contrat | FAILED | 800 dates de fin non postérieures au début | 2 |
| RQ-003 | CRM et Bronze / client | FAILED | 5 989 téléphones absents, vides ou blancs | 2 |
| RQ-005 | CRM et Bronze / client | FAILED | 1 456 codes postaux français non conformes | 2 |
| RQ-007 | CRM et Bronze / client | FAILED | 3 050 pays absents du référentiel | 2 |
| RQ-009 | CRM et Bronze / client | FAILED | 200 types de personne hors domaine | 2 |
| RQ-010 | CRM et Bronze / contrat | FAILED | 600 durées hors domaine | 2 |
| RQ-011 | CRM et Bronze / contrat | FAILED | 200 types de contrat inconnus | 2 |
| RQ-012 | CRM et Bronze / contrat | FAILED | 1 000 souscripteurs absents du référentiel client | 2 |
| RQ-013 | CRM et Bronze / contrat | FAILED | 300 assurés orphelins après exclusion de `0` | 2 |
| RQ-014 | CRM et Bronze / sinistre | PASSED (format et présence) ; FAILED (BAN) | 0 CP non conforme, 0 adresse absente ; 12,1 % non rapprochées BAN | 2 |
| RQ-015 | CRM et Bronze / client | FAILED | 479 prospects avec contrat | 2 |
| RQ-017 | CRM et Bronze / sinistre | FAILED | 1 200 sinistres hors période de garantie | 2 |
| RQ-018 | CRM et Bronze / contrat | PASSED | Écart nul entre les 3 directions après définition commune | 2* |
| RQ-020 | CRM et Bronze / client, contrat, sinistre | PASSED | 0 doublon et 0 NULL sur les 3 clés | 2* |

Chaque check porte son identifiant `RQ-xxx`. Les scans CRM et Bronze retournent le code `2` car au moins une règle échoue, même si certaines règles de ces scans sont `PASSED` (*). Le test isolé d'un doublon sur copie Soda donne 1 `WARNED`, 0 `FAILED` et le code `1` (`reports/us08_soda_duplicate_warning.txt`) ; un `FAILED` retourne le code `2`. La copie temporaire est supprimée par le test.

Les résultats Soda sur `crm` et `bronze` concordent avec GE sur les règles communes RQ-001, RQ-003, RQ-005, RQ-009, RQ-010 et RQ-020. Après construction des couches, le scan Silver passe **8/8 checks** (`reports/us12_soda_silver.json`) et le scan Gold passe **7/7 checks** (`reports/us12_soda_gold.json`). Le contrôle RQ-018 sur l'écart CD-001 est historisé séparément dans `dq.dq_history` et échoue en Gold : la vérification d'unicité de la vue ne prouve pas l'égalité de définition.

## 2. Bilan d'intégrité (US-16)

| Relation | Lignes testées | Orphelins | Taux de conformité | Conclusion |
|---|---:|---:|---:|---|
| `contrat.souscripteur_id` → client | 100 000 | 1 000 | 99,000 % | Anomalie réelle à corriger à la source ou à traiter en quarantaine |
| `contrat.assure_id` → client, avant traitement | 100 000 | 40 300 | 59,700 % | 40 000 sont la sentinelle `0`, 300 sont de vrais orphelins |
| `contrat.code_type` → `type_contrat` | 100 000 | 200 | 99,800 % | Anomalie de référence |
| `sinistre.contrat_id` → contrat | 100 000 | 0 | 100,000 % | Aucun orphelin observé |

Preuve : `reports/us16_integrite.csv` et `pipelines/run_s3_integrity.py`.

## 3. Valeur sentinelle (US-17)

| Contrôle | Lignes testées | Orphelins | Preuve |
|---|---:|---:|---|
| Avant exclusion de `assure_id = '0'` | 100 000 | 40 300 | `reports/us17_sentinelle.csv` |
| Après exclusion de la sentinelle | 60 000 | 300 | `reports/us17_sentinelle.csv` |

La valeur `0` crée 40 000 faux orphelins. Convention proposée : la convertir en `NULL` dans Silver avant le contrôle de clé étrangère, sans créer de client fictif ; les 300 vrais orphelins restent à examiner. Cette règle est proposée par le Data Steward et reste à faire valider par le Data Owner.

## 4. Statuts et garantie (US-18, US-19)

| Règle | Couche | Lignes testées | Échecs | Taux de conformité |
|---|---|---:|---:|---:|
| RQ-015 — prospect avec contrat | Bronze | 20 958 prospects | 479 | 97,714 % |
| RQ-016 — souscripteur sans contrat | Bronze | 49 898 souscripteurs | 955 | 98,086 % |
| RQ-017 — sinistre hors période de garantie | Bronze | 100 000 sinistres | 1 200 | 98,800 % |

Preuves : `reports/us18_statuts.csv`, `reports/us19_garantie.csv` et mesures `dq.dq_history`.

**Proposition du Data Steward au Data Owner (21/10/2026) :** ne pas écraser `type_personne` dans la source. Conserver le statut source, calculer un statut dérivé en Silver et mettre en revue les 479 prospects avec contrat et les 955 souscripteurs sans contrat avant toute correction CRM. Proposition inscrite au `livrables/JOURNAL_DECISIONS.md`, en attente d'approbation métier.

## 5. Définition unique du client actif (US-14)

Requête commune : `pipelines/us14_client_actif.sql`. À la date du 01/10/2026, elle reprend CD-001 : au moins un contrat en cours et une dernière cotisation depuis le 01/07/2026.

| Direction | Nombre de clients |
|---|---:|
| Commerciale | 37 643 |
| Sinistres | 37 643 |
| Risques | 37 643 |

Contrôle RQ-018 : écart maximal entre directions = **0** ; mesure CD-001 = **37 643**. Résultat reproductible : `reports/us14_client_actif.csv`. Les trois directions doivent réutiliser cette requête ; le Data Owner doit confirmer la définition comme règle métier commune.

## 6. Critères de fin

- [x] Un scan échoue avec un code retour non nul lorsqu'une règle bloquante échoue (code 2 sur les scans observés).
- [x] Les checks sont nommés avec leur identifiant RQ et la couche scannée.
- [x] Les checks ont également été exécutés après alimentation de Silver et Gold (8/8 et 7/7).
- [x] Les trois directions obtiennent le même nombre avec la définition commune (37 643).
- [x] La sentinelle `0` est expliquée ; sa conversion en `NULL` est proposée pour Silver.

## 7. Difficultés, écarts avec l'attendu, reprise

- Écart constaté avant US-14 : la définition commerciale seule dépassait CD-001 de 11 878 clients (mesure US-09). La requête commune supprime cet écart de définition, sans modifier les données CRM.
- Aucune réinitialisation de base ; les contrôles sont relançables sur le lot Bronze.
- Les checks ont été exécutés après construction : Silver 8/8 et Gold 7/7. Les propositions de traitement et la définition commune restent à faire approuver par le Data Owner.
