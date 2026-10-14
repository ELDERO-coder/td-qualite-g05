# S1 · Stack Docker, profilage, construction de bronze

Groupe : [À COMPLÉTER]  ·  Date : [À COMPLÉTER]  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-1`

Rappel : un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Inventaire des sources (US-01)

| Source | Table | Lignes | Clé primaire | Observation chiffrée |
|---|---|---|---|---|
| crm | client | 100 000 | `client_id` | Plus grande table CRM ; 100 000 enregistrements. |
| crm | contrat | 100 000 | `contrat_id` | Même volume que `crm.client` : 100 000 contrats. |
| crm | sinistre | 100 000 | `sinistre_id` | Même volume que `crm.client` et `crm.contrat` : 100 000 sinistres. |
| crm | type_contrat | 12 | `code_type` | 12 types de contrat référencés. |
| cif | clients | 40 000 | `column0` | 40 000 identités dans le CIF. |
| cif | compte | 45 000 | `column0` | 45 000 comptes, soit 1,125 compte par identité CIF en moyenne (ratio de volumes, pas une vérification de rattachement). |
| cif | pays | 250 | `code_pays` | 250 lignes dans le référentiel pays. |

Preuve : comptages exécutés sur les tables sources MariaDB ; clés primaires vérifiées dans `initdb/01_sources.sql`.

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

Méthode d'ingestion :
1. Le script lit en flux les sept tables sources dans l'ordre de leur clé primaire, par lots de 2 000 lignes.
2. Il convertit les valeurs en texte pour bronze, conserve les valeurs NULL et calcule un hash SHA-256 tronqué à 16 caractères hexadécimaux pour chaque ligne.
3. Il renseigne `_batch_id`, `_source_system`, `_ingested_at` (défaut MariaDB) et `_row_hash`, et enregistre le lot dans `dq.lot_ingestion`. Une relance avec le même `batch_id` remplace les lignes de ce lot.

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
| Relance du même lot : doublons créés | Non : les volumes restent à 385 262 lignes au total et chaque volume par table est inchangé. | `pipelines/load_bronze.py --batch-id L-2026-10-14`, puis comptage des lignes bronze du lot. |
| Écart introduit volontairement sur une copie : la porte échoue-t-elle ? | À confirmer : mode de simulation disponible, sortie de son exécution non vérifiée. | `pipelines/check_bronze.py --batch-id L-2026-10-14 --inject-mismatch` |
| Un problème de conversion rencontré (décimales, NULL, accents) et sa correction | Les valeurs typées source sont converties en texte ; aucun écart de hash n’est observé sur les sept tables. Les NULL restent NULL. | `pipelines/load_bronze.py` et mesures RQ-021 dans `dq.dq_history`. |

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

- [x] Les sept tables bronze existent et chaque ligne porte ses quatre métadonnées.
- [x] La porte B ne montre aucun écart de comptage ni de somme de contrôle.
- [x] Relancer l'ingestion du même lot ne crée aucun doublon.
- [ ] Un écart introduit volontairement fait échouer la porte.
- [x] RQ-021 est écrite dans `dq.dq_history` (couche BRONZE).

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : [À COMPLÉTER]

Point de reprise utilisé (oui / non, lequel) : [À COMPLÉTER]

Ce que nous ferions autrement : [À COMPLÉTER]
