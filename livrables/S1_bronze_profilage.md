# S1 · Stack Docker, profilage, construction de bronze

Groupe : [05]  ·  Date : [14/10/2026]  ·  Rédacteur : [Dewanou EL0HOUNKPON]  ·  Étiquette : `seance-1`

Rappel : un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Inventaire des sources (US-01)

| Source | Table | Lignes | Clé primaire | Observation chiffrée |
|---|---|---|---|---|
| crm | client | 100 000 | `client_id` | Plus grande table CRM avec 100 000 enregistrements |
| crm | contrat | 100 000 | `contrat_id` | Même volume de ligne que crm.client soit 100 000 contrats |
| crm | sinistre | 100 000 | `sinistre_id` | Même volume que `crm.client` et `crm.contrat` : 100 000 sinistres |
| crm | type_contrat | 12 | `code_type` | 12 types de contrat référencés |
| cif | clients | 40 000 | `column0` | 40 000 identités dans le CI. |
| cif | compte | 45 000 | `column0` | 45 000 comptes, soit environ 1,125 compte par identité CIF en moyenne |
| cif | pays | 250 | `code_pays` | 250 lignes dans le référentiel pays |

Preuve : comptages exécutés sur les tables sources MariaDB et les clés primaires vérifiées dans `initdb/01_sources.sql`.

```sql
SELECT 'crm.client', COUNT(*) FROM crm.client
UNION ALL SELECT 'crm.contrat', COUNT(*) FROM crm.contrat
UNION ALL SELECT 'crm.sinistre', COUNT(*) FROM crm.sinistre
UNION ALL SELECT 'crm.type_contrat', COUNT(*) FROM crm.type_contrat
UNION ALL SELECT 'cif.clients', COUNT(*) FROM cif.clients
UNION ALL SELECT 'cif.compte', COUNT(*) FROM cif.compte
UNION ALL SELECT 'cif.pays', COUNT(*) FROM cif.pays;
```

## 2. Bronze et porte B (US-02, US-03)

Méthode d'ingestion en trois lignes (lecture, conversion, métadonnées, relance du lot) :
1. Le script lit en flux les sept tables sources dans l'ordre de leur clé primaire, par lots de 2 000 lignes;
2. Il convertit les valeurs en texte pour bronze, conserve les valeurs NULL et calcule un hash SHA-256 tronqué à 16 caractères hexadécimaux pour chaque ligne;
3. Il renseigne `_batch_id`, `_source_system`, `_ingested_at` (défaut MariaDB) et `_row_hash`, et enregistre le lot dans `dq.lot_ingestion`. Une relance avec le même lot de bach`batch_id` ne crée aucun doublons de ce lot.

Exécution US-02 : lot `L-2026-10-14` terminé ; 385 262 lignes copiées dans les sept tables bronze. Pour chaque table, les lignes du lot ont leur système source attendu et un `_row_hash` non nul.

Réconciliation RQ-021 (comptage) et RQ-022 (somme de contrôle), pour le lot mesuré :

| Table bronze | Lignes source | Lignes bronze | Écart de comptage | Écart de somme de contrôle |
|---|---|---|---|---|
| crm_client | 100 000 | 100 000 | 0 | 0 |
| crm_contrat | 100 000 | 100 000 | 0 | 0 |
| crm_sinistre | 100 000 | 100 000 | 0 | 0 |
| crm_type_contrat | 12 | 12 | 0 | 0 |
| cif_clients | 40 000 | 40 000 | 0 | 0 |
| cif_compte | 45 000 | 45 000 | 0 | 0 |
| cif_pays | 250 | 250 | 0 | 0 |

Preuve : `pipelines/check_bronze.py --batch-id L-2026-10-14`. Les 14 mesures RQ-021/RQ-022 (7 tables × 2 règles) sont enregistrées dans `dq.dq_history` avec 0 échec et 100 % de conformité.

Épreuves de la porte (à documenter, avec la preuve de chacune) :

| Épreuve | Résultat obtenu | Preuve |
|---|---|---|
| Relance du même lot : doublons créés | Non il n'y a pas de doublons, les volumes restent à 385 262 lignes au total et chaque volume par table est inchangé | `pipelines/load_bronze.py --batch-id L-2026-10-14`, puis comptage des lignes bronze du lot. |
| Écart introduit volontairement sur une copie : la porte échoue-t-elle ? | oui la porté échoue quand on introduit volontairement sur la copie | `pipelines/check_bronze.py --batch-id L-2026-10-14 --inject-mismatch` |
| Un problème de conversion rencontré (décimales, NULL, accents) et sa correction | Les valeurs typées source sont converties en texte ; aucun écart de hash n’est observé sur les sept tables. Les NULL restent NULL. | `pipelines/load_bronze.py` et mesures RQ-021 dans `dq.dq_history`. |

## 3. Profil de crm.client (US-06, US-07)

Profil YData exécuté sur les 100 000 lignes de `crm.client` avec les longueurs et distincts sont calculés sur les valeurs non nulles:

| N° | Colonne | Indicateur (nulls, vides, distincts, motif…) | Valeur mesurée | Ce que cela change pour la qualité |
|---|---|---|---|---|
| 1 | `client_id` | Valeurs renseignées / distinctes | 100 000/100 000 ; longueur 6 à 7 | La clé est complète et distincte dans ce profil ; la règle d'unicité reste à contrôler à chaque ingestion(juste pour vérif)|
| 2 | `type_personne` | Nulls , distincts | 0 NULL ; 8 valeurs distinctes | Le DDL décrit un domaine de 3 valeurs ; les catégories observées doivent être examinées par le Data Steward avant normalisation |
| 3 | `nom`, `prenom`, `raison_sociale` | Nulls et distincts | `nom` et `prenom` : 4 277 NULL chacun ; `raison_sociale` : 95 723 NULL et 3 229 valeurs distinctes | Distinguer les personnes physiques des personnes morales avant d'appliquer des règles de complétude |
| 4 | `cp` | Valeurs distinctes et longueurs | 230 distinctes ; longueurs 4 à 8 (médiane 5) | Ne pas supposer que toutes les valeurs suivent le format français de 5 chiffres ( voir US-07) |
| 5 | `telephone` | Nulls, vides, valeurs distinctes | 5 999 NULL ; 4 000 vides ; 90 001 renseignées, 88 700 distinctes | Séparer complétude et validité du format ; les vides ne sont pas des NULL. |
| 6 | `email` | Nulls et cardinalité | 19 365 NULL (19,37 %) ; 80 635 renseignées, 77 795 distinctes | Mesurer la complétude et les doublons d'adresse séparément ; une adresse répétée oeut ne pas etre automatiquement considérée comme erronée  |

Motifs (conformes / non conformes) :

| Attribut | Motif testé | Lignes conformes | Lignes non conformes | Exemple de valeur non conforme |
|---|---|---|---|---|
| Code postal | `^\d{5}$`, toutes les valeurs renseignées | 97 683/100 000 (97,68 %) | 2 317 | `XXXX` (valeur masquée : longueur observée de 4 caractères). |
| Téléphone | `^0[1-9]\d{8}$`, valeurs renseignées des clients dont le pays normalisé vaut `FR` | 64 705/86 260 (75,01 %) | 21 555 ; 9 577 téléphones manquants ou vides dans ce périmètre | `XX-XX-XX-XX-XX` (valeur masquée, séparateurs observés) |
| Pays | `^[A-Z]{2}$` puis code présent exactement dans `ref_pays` ; valeurs renseignées | Forme : 97 000/99 600 ; référentiel : 96 950/99 600 (97,34 %) | Forme : 2 600 ; référentiel : 2 650 | `France` (valeur observée, non conforme au code alpha-2) |

Preuve reproductible : `docker exec dq_jupyter python pipelines/profile_crm_us06.py`. Rapport YData-Profiling : `reports/us06_crm_client_profiling.html` ; statistiques US-06 : `reports/us06_crm_client_metrics.csv` ; résultats des motifs US-07 : `reports/us07_crm_motifs.csv`. Les motifs portent sur les valeurs non vides ; les NULL et blancs sont comptés séparément.

### US-08 - Seuils d'alerte RQ-020 sur les clés

Seuil retenu : unicité à 100 % et zéro valeur NULL sur les trois clés primaires. Soda émet un avertissement dès qu'un doublon ou une valeur manquante est détecté (`warn: when > 0`) dans `soda/checks/client_checks.yml`, `soda/checks/contrat_checks.yml` et `soda/checks/sinistre_checks.yml`.

| Table | Clé | Lignes | NULL | Distinctes non nulles | Unicité | GE non nul / unique | Soda réel |
|---|---|---:|---:|---:|---:|---|---|
| `crm.client` | `client_id` | 100 000 | 0 | 100 000 | 100 % | Réussi / réussi | Les deux checks RQ-020 passent |
| `crm.contrat` | `contrat_id` | 100 000 | 0 | 100 000 | 100 % | Réussi / réussi | Les deux checks RQ-020 passent |
| `crm.sinistre` | `sinistre_id` | 100 000 | 0 | 100 000 | 100 % | Réussi / réussi | Les deux checks RQ-020 passent |

Épreuve sur copie : ajout volontaire d'une ligne client en doublon, sans modifier `crm.client`. La copie contient 100 001 lignes et 100 000 clés distinctes (unicité 99,999 %) ; GE passe la non-nullité et échoue l'unicité. Soda retourne `WARNED` avec `check_value: 1`. Le script supprime la copie après le scan et vérifie sa suppression.

Preuve reproductible : `docker exec dq_jupyter python pipelines/test_us08_key_alerts.py`. Mesures GE : `reports/us08_key_uniqueness.csv` ; résultat Soda : `reports/us08_soda_duplicate_warning.txt` ; seuils Soda : `soda/checks/client_checks.yml`, `soda/checks/contrat_checks.yml` et `soda/checks/sinistre_checks.yml`.

## 4. Dictionnaire du CIF (US-04)

YData-Profiling a analysé les 40 000 lignes et les 10 colonnes. Les colonnes sont physiquement stockées en texte dans la source (`VARCHAR`) ; le type indiqué ci-dessous est le type logique proposé. Les longueurs et distincts sont calculés sur les valeurs non nulles et non blanches ; aucune chaîne vide ou blanche n'a été observée.

| Colonne d'origine | Nom proposé | Type | Justification chiffrée (comment l'avez-vous déduit ?) |
|---|---|---|---|
| `column0` | `id_cif` | Identifiant texte | 40 000/40 000 distinctes ; longueur min/médiane/max = 7/7/7 ; 40 000/40 000 suivent `K` + 6 chiffres. Indice d'une clé d'identité |
| `column1` | `nom_ou_raison_sociale` | Nom / raison sociale, texte | 0 NULL ; 731 valeurs distinctes ; longueurs 3 à 31, médiane 6. Valeurs courtes de type nom, avec une plage longue compatible avec des raisons sociales |
| `column2` | `prenom` | Prénom, texte | 645 NULL (1,61 %) ; 180 valeurs distinctes parmi 39 355 renseignées ; longueurs 3 à 10, médiane 6. Cardinalité et longueurs compatibles avec des prénoms |
| `column3` | `date_naissance` | Date logique, texte `JJ/MM/AAAA` | 645 NULL ; les 39 355 valeurs renseignées ont une longueur de 10, correspondent au motif `NN/NN/NNNN` et sont des dates valides ; 21 081 dates distinctes. |
| `column4` | `adresse` | Adresse postale, texte | 9 811 valeurs distinctes ; longueurs 11 à 31, médiane 19, plage compatible avec des adresses de voirie |
| `column5` | `code_postal` | Code postal, texte | 188 valeurs distinctes ; longueurs 4 à 8, médiane 5 ; 39 659/40 000 suivent `5 chiffres` (99,15 %), 341 n'y correspondent pas. Le stockage texte conserve notamment les zéros initiaux |
| `column6` | `ville` | Commune, texte | 172 valeurs distinctes ; longueurs 3 à 24, médiane 8, profil compatible avec des noms de communes |
| `column7` | `code_pays` | Code pays, texte | 9 valeurs distinctes ; les 40 000/40 000 valeurs ont deux lettres majuscules, forme compatible avec un code pays alpha-2. |
| `column8` | `telephone` | Téléphone, texte | 6 324 NULL (15,81 %) ; 33 676 valeurs renseignées, toutes distinctes, de longueur 10 et conformes au motif `10 chiffres`. Texte nécessaire pour préserver le zéro initial |
| `column9` | `email` | Adresse électronique, texte | 18 872 NULL (47,18 %) ; 21 128 valeurs renseignées, toutes distinctes, longueurs 18 à 35 ; 21 128/21 128 correspondent au motif simple d'adresse électronique testé. Le motif ne prouve pas la délivrabilité |

Preuve reproductible : `docker exec dq_jupyter python pipelines/profile_cif_us04.py`,  Rapport YData-Profiling : `reports/us04_cif_profiling.html` ; métriques détaillées : `reports/us04_cif_metrics.csv`.
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

Difficultés rencontrées et temps perdu : La configuration Soda a demandé plusieurs essais : la comparaison `duplicate_count(...) = 0` produisait un échec au lieu d'un avertissement ; il a fallu utiliser la métrique seule avec `warn: when > 0`. Une indentation YAML incorrecte sur les checks des sinistres a également empêché le scan. Le temps perdu n'a pas été chronométré.

Point de reprise utilisé (oui / non, lequel) : Non, aucun point de reprise ni réinitialisation de la base n'a été nécessaire ; le test du doublon a utilisé une copie temporaire ensuite supprimée

Ce que nous ferions autrement : Tester d'abord la syntaxe et le statut d'alerte Soda sur une copie isolée, puis reporter la configuration validée sur les trois clés. Nous conserverions aussi la sortie de chaque commande avec son résultat dès son exécution.
