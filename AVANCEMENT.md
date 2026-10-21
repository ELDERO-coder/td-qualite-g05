# Avancement du groupe

Groupe : Groupe 05

Mettez à jour ce tableau à chaque fin de séance (et dès qu'une story change d'état). Statut : `À faire`, `En cours`, `Fait`, `Bloqué`. La preuve est un chemin du dépôt (notebook, fichier de checks, requête) ou une commande ; pas de preuve, pas de `Fait`.

| Séance | Story | Intitulé | Statut | Preuve (chemin ou commande) | Remarque |
|---|---|---|---|---|---|
| S1 | US-01 | Inventorier les sources | Fait | `pipelines/profile_s1.py` | Volumes SQL mesurés le 20/10/2026. |
| S1 | US-02 | Alimenter bronze | Fait | `pipelines/load_bronze.py --batch-id L-2026-10-14` | 385 262 lignes sur sept tables. |
| S1 | US-03 | Porte B : réconcilier source et bronze | Fait | `pipelines/check_bronze.py --batch-id L-2026-10-14` | RQ-021/RQ-022 historisées; zéro écart après restauration du test. |
| S1 | US-04 | Dictionnaire du CIF | Fait | `pipelines/profile_s1.py`, `initdb/01_sources.sql` | Dictionnaire exploratoire; validation métier à poursuivre. |
| S1 | US-06 | Profil de crm.client | Fait | `pipelines/profile_s1.py` | Mesures CRM reproductibles. |
| S1 | US-07 | Motifs code postal, téléphone, pays | Fait | `pipelines/profile_s1.py` | Motifs et taux mesurés; règles métier à confirmer. |
| S1 | US-09 | Trois définitions du client actif | En cours | `pipelines/profile_s1.py`, `livrables/S1_bronze_profilage.md` | Vues calculées; définition officielle à valider par Data Owner. |
| S2 | US-10 | Règles en tests Great Expectations | Fait | `pipelines/run_ge_s2.py` | Expectations RQ-001/002/003/005/009/010/020 exécutées; anomalies réelles conservées. |
| S2 | US-11 | Lignes en échec | Fait | `pipelines/run_ge_s2.py`; exports locaux ignorés Git | Exports d'identifiants techniques et échantillon de 20; Data Steward doit qualifier les corrections. |
| S2 | US-13 | Âge à la date de début du contrat | Fait | `pipelines/run_ge_s2.py` | 301 souscripteurs mineurs à la signature; 152 sont majeurs aujourd'hui. |
| S2 | US-15 | Mesure de référence sur bronze | Fait | `dq.dq_history`, lot `L-2026-10-14` | Mesures GE historisées; le Data Owner doit arbitrer les exceptions métier. |
| S3 | US-12 | Checks Soda, une source par couche | En cours | `soda/checks/*.yml` | Scans CRM exécutés; checks Silver/Gold et taux de retour warning isolé manquants. |
| S3 | US-16 | Clés étrangères | Fait | `pipelines/profile_s3.py` | Orphelins comptés sur relations CRM; anomalies restent à traiter. |
| S3 | US-17 | Valeur sentinelle | Fait | `pipelines/profile_s3.py`; `contrat_checks.yml` | 40 000 sentinelles; 300 orphelins après exclusion; convention finale à approuver. |
| S3 | US-18 | Statuts de personne | Fait | Soda `client_checks.yml`; `pipelines/profile_s3.py` | 479 prospects avec contrat, 955 souscripteurs sans contrat; correction non décidée. |
| S3 | US-19 | Période de garantie | Fait | Soda `sinistre_checks.yml`; `pipelines/profile_s3.py` | 1 200 hors période; porte source en échec, pas de correction automatique. |
| S3 | US-14 | Définition unique du client actif | En cours | RQ-018 dans `contrat_checks.yml`; `pipelines/profile_s3.py` | 55 602 par direction et écart 0; approbation Data Owner à obtenir. |
| S4 | US-21 | Silver : standardiser | En cours | `pipelines/transform_s4.py` | 140 000 clients traités; contrat/sinistre non transformés. |
| S4 | US-22 | Quarantaine | En cours | `silver.client.statut_qualite` dans `transform_s4.py` | 41 510 clients `A_SURVEILLER`; `dq.rejets` et règles de rejet non implémentés. |
| S4 | US-23 | Porte S : re-mesurer sur silver | À faire | `livrables/S4_silver_gold.md` | Expectations Silver complètes manquantes; Data Owner ne peut pas encore approuver la porte. |
| S4 | US-24 | Dédoublonnage | En cours | `pipelines/evaluate_pairs_s4.py`; `pipelines/transform_s4.py` | Seuil 0,85 évalué; fusion production limitée à 13 967 clés exactes CRM-CIF non ambiguës. |
| S4 | US-25 | Golden record | En cours | `gold.client_unique`; `catalogue/gold_client_unique.md` | 126 033 clients; survie CRM prioritaire provisoire, validation Data Owner requise. |
| S4 | US-27 | Gold et client actif unique | En cours | `gold.client_unique` | 55 602 actifs; vue `v_client_actif` et contrats/sinistres certifiés manquants. |
| S4 | US-28 | Traçabilité de trois données | En cours | `gold.xref_identifiants` | Lignage client existe; les trois cas nominaux/CP/sinistre ne sont pas tous vérifiés. |
| S5 | US-29 | Historique des mesures | En cours | `pipelines/export_history_s5.py` | Export exécuté; seules couches BRONZE et CRM sont mesurées. |
| S5 | US-30 | Courbes d'évolution | En cours | `reports/s5_history.png` | Courbe partielle; Silver/Gold absents, donc aucune tendance inter-couche revendiquée. |
| S5 | US-31 | Certificat de qualité | En cours | `pipelines/certify_s5.py`; certificat `CERT-L20261014-132851` | NO_GO réel : 2/19 bloquantes mesurées et conformes, sans signataire. |
| S5 | US-32 | Publication vers le CRM | En cours | `pipelines/publish_s5.py` | Refus NO_GO testé; chargeur RQ-025 et tables cible absents. |
| S5 | US-34 | Catalogue, propriétaires, lineage | En cours | `catalogue/gold_client_unique.md` | Fiche et lineage préparés; Data Steward S5 et approbation des rôles à confirmer. |
| S5 | US-35 | Dossier go/no-go | À faire | … | |

Stories d'extension (facultatives) : US-05, US-08, US-20, US-26, US-33. Ajoutez une ligne si vous les traitez.
