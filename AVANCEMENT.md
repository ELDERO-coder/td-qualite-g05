# Avancement du groupe

Groupe : [À COMPLÉTER]

Mettez à jour ce tableau à chaque fin de séance (et dès qu'une story change d'état). Statut : `À faire`, `En cours`, `Fait`, `Bloqué`. La preuve est un chemin du dépôt (notebook, fichier de checks, requête) ou une commande ; pas de preuve, pas de `Fait`.

| Séance | Story | Intitulé | Statut | Preuve (chemin ou commande) | Remarque |
|---|---|---|---|---|---|
| S1 | US-01 | Inventorier les sources | Fait | `livrables/S1_bronze_profilage.md` §1 | Comptages MariaDB réalisés ; clés primaires recoupées avec le DDL |
| S1 | US-02 | Alimenter bronze | Fait | `pipelines/load_bronze.py` ; `docker exec dq_jupyter python pipelines/load_bronze.py --batch-id L-2026-10-14` | Lot TERMINE, 385 262 lignes ; les contrôles RQ-021/RQ-022 restent US-03 |
| S1 | US-03 | Porte B : réconcilier source et bronze | En cours | `pipelines/check_bronze.py --batch-id L-2026-10-14` | RQ-021/RQ-022 conformes sur 7 tables ; test négatif à confirmer |
| S1 | US-04 | Dictionnaire du CIF | Fait | `livrables/S1_bronze_profilage.md` §4 ; `reports/us04_cif_profiling.html` ; `reports/us04_cif_metrics.csv` | Profil YData exécuté sur 40 000 lignes ; 10 colonnes documentées avec longueurs, distincts, valeurs manquantes et motifs |
| S1 | US-06 | Profil de crm.client | Fait | `livrables/S1_bronze_profilage.md` §3 ; `reports/us06_crm_client_profiling.html` | Profil YData sur 100 000 lignes ; six constats chiffrés |
| S1 | US-07 | Motifs code postal, téléphone, pays | Fait | `livrables/S1_bronze_profilage.md` §3 ; `reports/us07_crm_motifs.csv` | Motifs mesurés ; valeurs manquantes/blanches séparées |
| S1 | US-08 | Seuils d'alerte sur les clés | Fait | `livrables/S1_bronze_profilage.md` §3 ; `pipelines/test_us08_key_alerts.py` ; `reports/us08_key_uniqueness.csv` ; `reports/us08_soda_duplicate_warning.txt` | 3 clés à 100 % uniques, 0 NULL ; GE échoue et Soda avertit sur le doublon ajouté à une copie |
| S1 | US-09 | Trois définitions du client actif | À faire | … | |
| S2 | US-10 | Règles en tests Great Expectations | À faire | … | |
| S2 | US-11 | Lignes en échec | À faire | … | |
| S2 | US-13 | Âge à la date de début du contrat | À faire | … | |
| S2 | US-15 | Mesure de référence sur bronze | À faire | … | |
| S3 | US-12 | Checks Soda, une source par couche | À faire | … | |
| S3 | US-16 | Clés étrangères | À faire | … | |
| S3 | US-17 | Valeur sentinelle | À faire | … | |
| S3 | US-18 | Statuts de personne | À faire | … | |
| S3 | US-19 | Période de garantie | À faire | … | |
| S3 | US-14 | Définition unique du client actif | À faire | … | |
| S4 | US-21 | Silver : standardiser | À faire | … | |
| S4 | US-22 | Quarantaine | À faire | … | |
| S4 | US-23 | Porte S : re-mesurer sur silver | À faire | … | |
| S4 | US-24 | Dédoublonnage | À faire | … | |
| S4 | US-25 | Golden record | À faire | … | |
| S4 | US-27 | Gold et client actif unique | À faire | … | |
| S4 | US-28 | Traçabilité de trois données | À faire | … | |
| S5 | US-29 | Historique des mesures | À faire | … | |
| S5 | US-30 | Courbes d'évolution | À faire | … | |
| S5 | US-31 | Certificat de qualité | À faire | … | |
| S5 | US-32 | Publication vers le CRM | À faire | … | |
| S5 | US-34 | Catalogue, propriétaires, lineage | À faire | … | |
| S5 | US-35 | Dossier go/no-go | À faire | … | |

Stories d'extension (facultatives) : US-05, US-08, US-20, US-26, US-33. Ajoutez une ligne si vous les traitez.
