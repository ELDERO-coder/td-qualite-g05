# S1 · Stack Docker, profilage, construction de Bronze

Groupe : Groupe 05 · Date de séance : 14/10/2026 · Rédacteur : Oussama (Data Owner et rédacteur) · Tag initial : `seance-1`


## 1. Inventaire des sources (US-01)

| Source | Table | Lignes mesurées | Clé primaire |
|---|---|---:|---|
| crm | client | 100 000 | `client_id` |
| crm | contrat | 100 000 | `contrat_id` |
| crm | sinistre | 100 000 | `sinistre_id` |
| crm | type_contrat | 12 | `code_type` |
| cif | clients | 40 000 | `column0` |
| cif | compte | 45 000 | `column0` |
| cif | pays | 250 | `code_pays` |

Preuve : `docker exec dq_jupyter python pipelines/profile_s1.py`. Les clés sont déclarées dans `initdb/01_sources.sql`. Total : 385 262 lignes.

## 2. Bronze et porte B (US-02, US-03)

Chargement : `docker exec dq_jupyter python pipelines/load_bronze.py --batch-id L-2026-10-14`. Le script lit les sources par blocs de 2 000 lignes, convertit les attributs en texte et conserve les NULL. Il écrit `_batch_id`, `_source_system`, `_ingested_at` et `_row_hash`. Le schéma Bronze limite `_row_hash` à 16 caractères : la valeur est tronquée aux 16 premiers caractères d'un SHA-256 calculé sur les valeurs JSON UTF-8; ce n'est pas une empreinte SHA-256 complète.
g
Contrôle : `docker exec dq_jupyter python pipelines/check_bronze.py --batch-id L-2026-10-14`. Le script compare les valeurs source et Bronze selon les clés primaires, recalcule les empreintes et vérifie les quatre métadonnées.

| Table Bronze | Source | Bronze (lot) | Écart de lignes | Lignes différentes |
|---|---:|---:|---:|---:|
| `crm_client` | 100 000 | 100 000 | 0 | 0 |
| `crm_contrat` | 100 000 | 100 000 | 0 | 0 |
| `crm_sinistre` | 100 000 | 100 000 | 0 | 0 |
| `crm_type_contrat` | 12 | 12 | 0 | 0 |
| `cif_clients` | 40 000 | 40 000 | 0 | 0 |
| `cif_compte` | 45 000 | 45 000 | 0 | 0 |
| `cif_pays` | 250 | 250 | 0 | 0 |
| **Total** | **385 262** | **385 262** | **0** | **0** |

RQ-021 (réconciliation) et RQ-022 (métadonnées) ont été enregistrées dans `dq.dq_history`, couche `BRONZE`, pour chacune des sept tables. Les 14 mesures du dernier contrôle sont conformes à 100 %. La relance du même lot recharge celui-ci sans augmenter les volumes. Pour tester l'échec, le nom du pays `AD` a été temporairement altéré dans Bronze : la porte a détecté une ligne différente et renvoyé le code d'échec. La valeur a été restaurée depuis `cif.pays`; le contrôle suivant a réussi avec zéro écart. Test effectué sur la base locale de travail.

## 3. Profil de `crm.client` (US-06, US-07)

Mesures sur 100 000 lignes à la référence du lot `2026-10-14`. Reproduction : `docker exec dq_jupyter python pipelines/profile_s1.py`. Motifs : CP `^[0-9]{5}$`, téléphone `^[+]?[0-9 ()-]{8,20}$`, pays `^[A-Z]{2}$`; les NULL sont comptés comme non conformes au motif.

| Indicateur | Mesure | Conséquence qualité |
|---|---:|---|
| `client_id` NULL / distincts | 0 / 100 000 | Identifiant présent et unique dans la table mesurée. |
| `email` NULL / chaîne vide | 19 365 (19,365 %) / 0 | Améliorer la collecte pour les usages qui exigent un contact par courriel. |
| `cp` conforme / non conforme | 97 683 / 2 317 (2,317 %) | Normaliser en Silver; le motif strict vise les codes postaux à cinq chiffres. |
| `telephone` conforme / non conforme | 85 295 / 14 705 (14,705 %), dont 5 999 NULL | Définir les formats admis et contrôler la joignabilité avant les relances. |
| `date_naissance` future | 0 | Aucun cas futur observé; les dates impossibles restent à contrôler. |
| `pays` conforme / non conforme | 97 000 / 3 000 (3 %) | Standardiser et rapprocher du référentiel pays. |

## 4. Dictionnaire exploratoire CIF (US-04)

Hypothèses tirées des distributions observées et des commentaires dans `initdb/01_sources.sql`; les noms proposés restent à valider par le métier.

| Colonne | Nom proposé | Indice mesuré / justification |
|---|---|---|
| `cif.clients.column0` | `id_cif` | 40 000 valeurs distinctes sur 40 000 lignes; clé primaire déclarée. |
| `cif.clients.column1` | `nom_ou_raison_sociale` | Champ texte; domaine attendu indiqué dans le schéma. |
| `cif.clients.column2` | `prenom` | Champ texte; domaine attendu indiqué dans le schéma. |
| `cif.clients.column3` | `date_naissance` | 39 355 renseignées et 21 081 distinctes; format observé `JJ/MM/AAAA`. |
| `cif.clients.column4` | `adresse` | 9 811 valeurs distinctes. |
| `cif.clients.column5` | `code_postal` | 188 valeurs distinctes; rapprochement postal à réaliser. |
| `cif.clients.column6` | `ville` | 172 valeurs distinctes. |
| `cif.clients.column7` | `code_pays` | 9 valeurs distinctes; rapprochement pays à réaliser. |
| `cif.clients.column8` | `telephone` | 33 676 valeurs distinctes; contact probable. |
| `cif.clients.column9` | `email` | 21 128 valeurs distinctes; contact probable. |

À distinguer de `cif.compte` : `column0` est l'identifiant de compte (39 611 distincts), `column1` l'identifiant CIF lié (40 000 distincts), `column2` la date d'ouverture, `column3` le statut (`O` : 39 611; `F` : 5 389). Preuves : `pipelines/profile_s1.py` et `initdb/01_sources.sql`.

## 5. Trois vues exploratoires de « client actif » (US-09)

Comptages au 14/10/2026, limités aux identifiants présents dans `crm.client`. Reproduction : `docker exec dq_jupyter python pipelines/profile_s1.py`. Ce sont des vues opérationnelles exploratoires, pas des définitions métier approuvées.

| Vue | Définition calculée | Clients CRM | Limite |
|---|---|---:|---|
| Commerciale | Souscripteur ou assuré d'un contrat en cours à la référence ou commencé dans les 12 mois précédents | 67 431 | Ne définit pas spécifiquement l'activité d'un prospect. |
| Sinistres | Assuré ayant au moins un sinistre relié à un de ses contrats | 23 070 | La source n'indique pas si le sinistre est en cours; ce compte couvre l'historique disponible. |
| Risques / proxy CD-001 | Souscripteur ou assuré d'un contrat en cours et cotisation enregistrée dans les trois derniers mois | 55 602 | Interprétation calculable de CD-001 à faire valider par le Data Owner. |

Les écarts arithmétiques au proxy risques sont +11 829 pour la vue commerciale et -32 532 pour la vue sinistres. Les périmètres étant différents, ces écarts ne prouvent pas une divergence métier à périmètre identique. Décision proposée, non actée : faire valider CD-001 et le traitement des rôles souscripteur/assuré avant de publier une définition unique.

## 6. État des preuves S1

- [x] Sources inventoriées et comptées.
- [x] Sept tables Bronze chargées avec les quatre métadonnées; total de 385 262 lignes.
- [x] RQ-021 et RQ-022 contrôlées et historisées; dernier contrôle à zéro écart.
- [x] Relance du même lot vérifiée sans hausse de volume.
- [x] Écart temporaire détecté; donnée restaurée et contrôle final réussi.
- [x] Profil CRM et dictionnaire CIF basés sur des mesures reproductibles.
- [x] Trois vues d'activité calculées et limites documentées.

## 7. Difficultés et reprise

- Difficultés rencontrées : configuration initiale du chemin Docker sous Windows et conflit de fusion Git sur le fichier d'équipe.
- Point de reprise déclaré : utilisation de `run.bat` et réalignement de branche; à confirmer par les membres concernés.
- À améliorer : synchroniser les branches puis vérifier les mesures réelles avant de figer le livrable.
