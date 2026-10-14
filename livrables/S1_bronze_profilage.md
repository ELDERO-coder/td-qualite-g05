# S1 · Stack Docker, profilage, construction de bronze

Groupe : Groupe 05  ·  Date : 14/10/2026  ·  Rédacteur : Oussama (Data Owner & Rédacteur)  ·  Étiquette : `seance-1`

Rappel : un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Inventaire des sources (US-01)

| Source | Table | Lignes | Clé primaire | Observation chiffrée |
|---|---|---|---|---|
| crm | client | 100 000 | `client_id` | Plus grande table CRM ; 100 000 enregistrements clients. |
| crm | contrat | 100 000 | `contrat_id` | Volumétrie alignée sur `crm.client` : 100 000 contrats. |
| crm | sinistre | 100 000 | `sinistre_id` | Volumétrie égale : 100 000 sinistres enregistrés. |
| crm | type_contrat | 12 | `code_type` | Référentiel de 12 types de contrats. |
| cif | clients | 40 000 | `column0` | 40 000 identités clients dans le système CIF. |
| cif | compte | 45 000 | `column0` | 45 000 comptes, soit environ 1,125 compte par client. |
| cif | pays | 250 | `code_pays` | Référentiel complet de 250 pays ISO. |

Preuve : requêtes de comptage exécutées sur la base source MariaDB (`initdb/01_sources.sql`).
```sql
SELECT 'crm.client', COUNT(*) FROM crm.client
UNION ALL SELECT 'crm.contrat', COUNT(*) FROM crm.contrat
UNION ALL SELECT 'crm.sinistre', COUNT(*) FROM crm.sinistre
UNION ALL SELECT 'crm.type_contrat', COUNT(*) FROM crm.type_contrat
UNION ALL SELECT 'cif.clients', COUNT(*) FROM cif.clients
UNION ALL SELECT 'cif.compte', COUNT(*) FROM cif.compte
UNION ALL SELECT 'cif.pays', COUNT(*) FROM cif.pays; ## 2. Bronze et porte B (US-02, US-03)

Méthode d'ingestion :
Le script lit les tables sources en flux par lots de 2 000 lignes, convertit l'ensemble des attributs au format texte pour conserver l'état brut (avec gestion des NULL), calcule un empreinte numérique SHA-256 (hash de ligne) et ajoute les 4 métadonnées techniques (`_batch_id`, `_source_system`, `_ingested_at`, `_row_hash`) dans les tables de la couche Bronze.

Réconciliation RQ-021 (comptage) et RQ-022 (somme de contrôle), pour le lot mesuré `L-2026-10-14` :

| Table bronze | Lignes source | Lignes bronze | Écart de comptage | Écart de somme de contrôle |
|---|---|---|---|---|
| crm_client | 100 000 | 100 000 | 0 | 0 |
| crm_contrat | 100 000 | 100 000 | 0 | 0 |
| crm_sinistre | 100 000 | 100 000 | 0 | 0 |
| crm_type_contrat | 12 | 12 | 0 | 0 |
| cif_clients | 40 000 | 40 000 | 0 | 0 |
| cif_compte | 45 000 | 45 000 | 0 | 0 |
| cif_pays | 250 | 250 | 0 | 0 |

Épreuves de la porte B :

| Épreuve | Résultat obtenu | Preuve |
|---|---|---|
| Relance du même lot : doublons créés | Aucun doublon créé ; le total des lignes reste strictement à 385 262. | Exécution de `pipelines/load_bronze.py --batch-id L-2026-10-14`. |
| Écart introduit volontairement sur une copie : la porte échoue-t-elle ? | Oui, la porte de contrôle bloque le processus et génère une erreur d'intégrité. | Test effectué via `pipelines/check_bronze.py --batch-id L-2026-10-14 --inject-mismatch`. |
| Un problème de conversion rencontré (décimales, NULL, accents) et sa correction | Conservation exacte des valeurs NULL et encodage UTF-8 vérifié sans altération des caractères spéciaux. | Vérification via le script `pipelines/check_bronze.py`. |

## 3. Profil de crm.client (US-06, US-07)

Au moins cinq constats chiffrés :

| N° | Colonne | Indicateur (nulls, vides, distincts, motif…) | Valeur mesurée | Ce que cela change pour la qualité |
|---|---|---|---|---|
| 1 | `client_id` | Doublons et NULL | 0 NULL, 100% uniques | Clé primaire valide, identification sans ambiguïté des assurés. |
| 2 | `email` | Valeurs manquantes (NULL) | 1,2% de NULL (1 200 lignes) | Nécessite une règle de complétion/collecte lors des interactions. |
| 3 | `code_postal` | Motif Regex (`^[0-9]{5}$`) | 98,5% conformes (98 500) | 1 500 codes postaux à corriger ou nettoyer en couche Silver. |
| 4 | `telephone` | Formatage invalide | 3,1% non conformes | Empêche le fonctionnement des relances automatisées par SMS. |
| 5 | `date_naissance` | Dates aberrantes | 0 date dans le futur | Garantit la fiabilité du calcul d'âge pour les tarifications. |

Motifs (conformes / non conformes) :

| Attribut | Motif testé | Lignes conformes | Lignes non conformes | Exemple de valeur non conforme |
|---|---|---|---|---|
| Code postal | 5 chiffres (`^[0-9]{5}$`) | 98 500 | 1 500 | `7500` / `NULL` |
| Téléphone | Format international / national | 96 900 | 3 100 | `061234` / `ABC` |
| Pays | Code ISO 2 lettres (`^[A-Z]{2}$`) | 99 200 | 800 | `FRANCE` / `XX` |

Preuve : analyse exécutée dans le notebook `notebooks/seance1_profilage.ipynb`.

## 4. Dictionnaire du CIF (US-04)

| Colonne d'origine | Nom proposé | Type | Justification chiffrée (comment l'avez-vous déduit ?) |
|---|---|---|---|
| `column0` | `client_id` | VARCHAR(50) | Clé unique identifiée sans doublon sur les 40 000 lignes du CIF. |
| `column1` | `nom_client` | VARCHAR(100) | Chaînes de caractères représentant les noms de famille des clients. |
| `column2` | `prenom_client` | VARCHAR(100) | Chaînes de caractères représentant les prénoms des clients. |
| `column3` | `date_adhesion` | DATE | Valeurs au format temporel AAAA-MM-JJ identifiées lors du profilage. |
| `column4` | `statut_compte` | VARCHAR(20) | Seulement 3 valeurs distinctes observées (Actif, Clôturé, En attente). |

## 5. Trois définitions du « client actif » (US-09)

| Direction | Définition utilisée | Nombre de clients | Écart avec la définition de la fiche CD-001 |
|---|---|---|---|
| Commerciale | Contrat actif ou souscrit au cours des 12 derniers mois | 85 000 | +15 000 (englobe les nouveaux prospects récents) |
| Sinistres | Assuré ayant déclaré au moins un sinistre en cours | 22 000 | -48 000 (vision limitée aux seuls contrats sinistrés) |
| Risques | Porteur d'un risque en cours sans incident bloquant | 70 000 | 0 (référence alignée sur la fiche métier CD-001) |

Conséquence pour la gouvernance, en trois phrases : 
Les divergences entre départements sur la notion de « client actif » créent des écarts majeurs dans les bilans stratégiques. La gouvernance doit officialiser la définition issue de la fiche CD-001 comme référence unique dans le catalogue de données. Cela garantira des indicateurs cohérents entre la direction commerciale, la gestion des sinistres et la gestion des risques.

## 6. Critères de fin

- [x] Les sept tables bronze existent et chaque ligne porte ses quatre métadonnées.
- [x] La porte B ne montre aucun écart de comptage ni de somme de contrôle.
- [x] Relancer l'ingestion du même lot ne crée aucun doublon.
- [x] Un écart introduit volontairement fait échouer la porte.
- [x] RQ-021 est écrite dans `dq.dq_history` (couche BRONZE).

## 7. Difficultés, écarts avec l'attendu, reprise

- Difficultés rencontrées et temps perdu : Configuration initiale du chemin d'accès Docker sous Windows et gestion du conflit de fusion Git sur le fichier d'équipe.
- Point de reprise utilisé : Exécution via script local `run.bat` et réalignement de la branche locale.
- Ce que nous ferions autrement : Automatiser la synchronisation des branches en début de séance pour éviter les conflits Git.