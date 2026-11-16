# Avancement du groupe

Groupe : 05

Mettez à jour ce tableau à chaque fin de séance (et dès qu'une story change d'état). Statut : `À faire`, `En cours`, `Fait`, `Bloqué`. La preuve est un chemin du dépôt (notebook, fichier de checks, requête) ou une commande ; pas de preuve, pas de `Fait`.

| Séance | Story | Intitulé | Statut | Preuve (chemin ou commande) | Remarque |
|---|---|---|---|---|---|
| S1 | US-01 | Inventorier les sources | Fait | `livrables/S1_bronze_profilage.md` §1 | Comptages MariaDB réalisés ; clés primaires recoupées avec le DDL |
| S1 | US-02 | Alimenter bronze | Fait | `pipelines/load_bronze.py` ; `docker exec dq_jupyter python pipelines/load_bronze.py --batch-id L-2026-10-14` | Lot TERMINE, 385 262 lignes ; les contrôles RQ-021/RQ-022 restent US-03 |
| S1 | US-03 | Porte B : réconcilier source et bronze | Fait | `pipelines/check_bronze.py --batch-id L-2026-10-14` ; `pipelines/check_bronze.py --batch-id L-2026-10-14 --inject-mismatch` | RQ-021/RQ-022 conformes sur 7 tables ; le test d'écart simulé est détecté sans modifier les données |
| S1 | US-04 | Dictionnaire du CIF | Fait | `livrables/S1_bronze_profilage.md` §4 ; `reports/us04_cif_profiling.html` ; `reports/us04_cif_metrics.csv` | Profil YData exécuté sur 40 000 lignes ; 10 colonnes documentées avec longueurs, distincts, valeurs manquantes et motifs |
| S1 | US-06 | Profil de crm.client | Fait | `livrables/S1_bronze_profilage.md` §3 ; `reports/us06_crm_client_profiling.html` | Profil YData sur 100 000 lignes ; six constats chiffrés |
| S1 | US-07 | Motifs code postal, téléphone, pays | Fait | `livrables/S1_bronze_profilage.md` §3 ; `reports/us07_crm_motifs.csv` | Motifs mesurés ; valeurs manquantes/blanches séparées |
| S1 | US-08 | Seuils d'alerte sur les clés | Fait | `livrables/S1_bronze_profilage.md` §3 ; `pipelines/test_us08_key_alerts.py` ; `reports/us08_key_uniqueness.csv` ; `reports/us08_soda_duplicate_warning.txt` | 3 clés à 100 % uniques, 0 NULL ; GE échoue et Soda avertit sur le doublon ajouté à une copie |
| S1 | US-09 | Trois définitions du client actif | Fait | `pipelines/us09_client_actif.sql` ; `livrables/S1_bronze_profilage.md` §5 | Trois périmètres calculés sur bronze et comparés à CD-001 pour le lot `L-2026-10-14` |
| S2 | US-10 | Règles en tests Great Expectations | Fait | `pipelines/run_s2_quality.py` ; `reports/us10_ge_results.csv` | 7 règles exécutées ; RQ-020 mesurée sur les 3 clés, résultats détaillés dans `dq.dq_history` |
| S2 | US-11 | Lignes en échec | Fait | `reports/us11_echecs_complets.csv` ; `reports/us11_echantillon_20.csv` | Export complet des échecs et échantillon commenté de 20 lignes |
| S2 | US-13 | Âge à la date de début du contrat | Fait | `reports/us13_age_reference.csv` ; `livrables/S2_regles_great_expectations.md` §3 | 300 échecs à la date de début contre 148 à la date du jour ; 152 personnes ont eu 18 ans depuis |
| S2 | US-15 | Mesure de référence sur bronze | Fait | `dq.dq_history` ; `livrables/S2_regles_great_expectations.md` §4 | Mesures du lot `L-2026-10-14`, couches, règles, volumes et échecs historisés |
| S3 | US-12 | Checks Soda, une source par couche | Fait | `soda/configuration.yml` ; `soda/checks/bronze_checks.yml` ; `soda/checks/silver_checks.yml` ; `soda/checks/gold_checks.yml` ; `reports/us12_soda_silver.json` ; `reports/us12_soda_gold.json` | Checks Silver 8/8 et Gold 7/7 PASS ; RQ-018 de comparaison CD-001 reste non conforme, mesurée dans `dq.dq_history` |
| S3 | US-16 | Clés étrangères | Fait | `pipelines/run_s3_integrity.py` ; `reports/us16_integrite.csv` | 1 000 souscripteurs et 200 types de contrat absents ; aucun sinistre sans contrat |
| S3 | US-17 | Valeur sentinelle | Fait | `reports/us17_sentinelle.csv` ; `livrables/JOURNAL_DECISIONS.md` décision 2 | 40 000 sentinelles isolées ; 300 vrais orphelins après exclusion de `0` |
| S3 | US-18 | Statuts de personne | Fait | `reports/us18_statuts.csv` ; `livrables/JOURNAL_DECISIONS.md` décision 3 | 479 prospects avec contrat ; 955 souscripteurs sans contrat |
| S3 | US-19 | Période de garantie | Fait | `reports/us19_garantie.csv` ; `pipelines/run_s3_integrity.py` | 1 200 sinistres hors période sur 100 000 |
| S3 | US-14 | Définition unique du client actif | Fait | `pipelines/us14_client_actif.sql` ; `reports/us14_client_actif.csv` ; check RQ-018 | 37 643 clients par direction ; écart nul avec la définition commune CD-001 |
| S4 | US-21 | Silver : standardiser | Fait | `pipelines/build_silver.py` ; `reports/us21_standardisation.csv` | 1 478 codes postaux réparés ; transformations relançables |
| S4 | US-22 | Quarantaine | Fait | `reports/us22_quarantaine.csv` | 14 981 rejets S ; conservation vérifiée sur les quatre entités |
| S4 | US-23 | Porte S : re-mesurer sur silver | Fait | `reports/us23_bronze_vs_silver.csv` ; `dq.dq_history` | RQ-023/RQ-024 à 100 % ; les bloqueurs S sont conformes sur les lignes conservées |
| S4 | US-24 | Dédoublonnage | Fait | `pipelines/build_gold.py` ; `reports/us24_dedup_metrics.csv` ; `reports/us24_candidates_summary.csv` | Seuil 70/69 proposé ; rappel 94 % sur 200 paires, Data Owner à valider |
| S4 | US-25 | Golden record | Fait | `pipelines/build_gold.py` ; `reports/us25_survivorship.csv` | Survie par valeur valide/complète, CRM en cas d'égalité ; proposition Data Steward |
| S4 | US-27 | Gold et client actif unique | Bloqué | `gold.v_client_actif` ; `reports/us27_gold_counts.csv` ; `livrables/RQ018_rapprochement.md` | Écart expliqué en 562 sans mapping, 972 sans Gold actif et 1 414 consolidés ; validation du grain CD-001 et traitement des rejets requis avant GO |
| S4 | US-28 | Traçabilité de trois données | Fait | `reports/us28_trace.csv` | Société Meunier, code postal restauré et adresse de sinistre reliés aux lignes source |
| S5 | US-29 | Historique des mesures | Fait | `pipelines/run_s5.py history` ; `livrables/us29_historique_mesures.csv` ; `livrables/us29_kpi_dimensions.csv` | Mesures par règle et dimension, taux pondérés par lignes |
| S5 | US-30 | Courbes d'évolution | Fait | `reports/us30_evolution_qualite.svg` | Courbe Bronze/Silver/Gold/CRM ; un seul lot de référence disponible |
| S5 | US-31 | Certificat de qualité | Fait | `pipelines/run_s5.py certify` ; `livrables/us31_controles_certificat.csv` ; `dq.certificat_qualite` | Certificat `CERT-L-2026-10-14` NO_GO : 20/21 contrôles bloquants conformes ; RQ-018 échoue |
| S5 | US-32 | Publication vers le CRM | Fait | `pipelines/run_s5.py publish` ; `pipelines/run_s5.py self-test` ; `livrables/us32_self_test.csv` ; `livrables/us32_self_test_reconciliation.csv` | Publication réelle refusée ; 4 scénarios testés ; test GO transactionnel annulé, cible vide |
| S5 | US-34 | Catalogue, propriétaires, lineage | Bloqué | `catalogue/gold_client_unique.md` ; `reports/us28_trace.csv` | Catalogue et lineage documentés ; le Data Owner doit être désigné par le groupe ou l'enseignant |
| S5 | US-35 | Dossier go/no-go | Fait | `livrables/DOSSIER_GO_NOGO.md` | Recommandation NO-GO avec preuves, écarts et conditions de reprise |

Stories d'extension (facultatives) : US-05, US-08, US-20, US-26, US-33. Ajoutez une ligne si vous les traitez.
