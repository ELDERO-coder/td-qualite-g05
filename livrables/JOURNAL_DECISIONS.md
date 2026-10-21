# Journal des décisions

Une ligne par décision de seuil, de sévérité, de définition ou de règle de survie. Une décision sans rôle ni justification chiffrée n'est pas une décision. Ce journal alimente la partie « La décision » du dossier go/no-go.

| N° | Date | Séance | Règle ou objet | Décision (ce qui est arrêté) | Justification chiffrée (preuve) | Rôle décideur | Alternative écartée |
|---|---|---|---|---|---|---|---|
| 1 | … | … | … | … | … | … | … |
| 2 | … | … | … | … | … | … | … |
| 3 | … | … | … | … | … | … | … |
| 4 | … | … | … | … | … | … | … |
| 5 | … | … | … | … | … | … | … |
| 6 | … | … | … | … | … | … | … |
| 7 | … | … | … | … | … | … | … |
| 8 | … | … | … | … | … | … | … |
| 9 | 2026-10-14 | S1 | Seuils d'alerte RQ-020 sur `client_id`, `contrat_id`, `sinistre_id` | Exiger 100 % d'unicité et 0 NULL ; Soda avertit dès le premier doublon ou NULL (`warn: when > 0`). | Les 3 clés source ont 100 000 lignes, 0 NULL et 100 000 valeurs distinctes chacune. Sur la copie client, 1 doublon ajouté donne 99,999 % d'unicité, GE échoue et Soda retourne WARNED (`check_value: 1`). Preuves : `reports/us08_key_uniqueness.csv`, `reports/us08_soda_duplicate_warning.txt`. | Data Steward | Tolérer les anomalies ou attendre plusieurs doublons avant le premier avertissement |
| 10 | 2026-10-21 | S3 | Sentinelle `contrat.assure_id = '0'` (US-17) | Proposition Data Steward : convertir `0` en `NULL` en Silver avant le contrôle de référence ; ne pas créer d'assuré fictif. À valider par le Data Owner. | 40 000 sentinelles sur 100 000 contrats ; l'écart d'orphelins passe de 40 300 à 300 après exclusion. Preuve : `reports/us17_sentinelle.csv`. | Data Steward (proposition) | Traiter `0` comme un véritable identifiant ou créer un client technique |
| 11 | 2026-10-21 | S3 | Statut prospect / souscripteur (US-18) | Proposition Data Steward : conserver le statut source, calculer un statut dérivé en Silver et soumettre les cas ambigus au Data Owner avant toute correction CRM. | 479 prospects ont un contrat ; 955 souscripteurs n'en ont aucun. Preuve : `reports/us18_statuts.csv`. | Data Steward (proposition) | Écraser automatiquement le statut dans la source |
| 12 | 2026-10-21 | S3 | Définition commune du client actif (US-14, RQ-018) | Proposition Data Steward : retenir CD-001 (contrat en cours au 01/10/2026 et cotisation depuis le 01/07/2026) pour les trois directions ; validation métier du Data Owner requise. | 37 643 clients pour chacune des directions ; écart RQ-018 = 0. Preuves : `pipelines/us14_client_actif.sql`, `reports/us14_client_actif.csv`. | Data Steward (proposition) | Maintenir des définitions et chiffres propres à chaque direction |
| 13 | 2026-10-21 | S4 | Seuils de rapprochement (US-24) | Proposition : fusion automatique à partir de 70/100 ; revue à 69/100 ; seuil soumis au Data Owner avant emploi métier. | Sur 200 paires étiquetées : 94 vrais positifs, 0 faux positif, rappel 94 % ; 5 paires positives ne sont pas générées. Preuves : `reports/us24_dedup_metrics.csv`, `reports/us24_candidates_summary.csv`. | Data Steward (proposition) | Seuil 55/100, qui produit 104 171 fusions automatiques sans gain de précision mesuré sur l'échantillon |
| 14 | 2026-10-21 | S4 | Survie des attributs du golden record (US-25) | Proposition : retenir par attribut la valeur valide la plus complète ; CRM en cas d'égalité ; pas de priorité CRM si sa valeur est absente ou invalide. À valider par le Data Owner. | Source gagnante comptabilisée pour le nom, l'adresse, le téléphone et le courriel ; par exemple le nom est pris du CRM pour 91 139 groupes et du CIF pour 23 278. Preuve : `reports/us25_survivorship.csv`. | Data Steward (proposition) | Préférer systématiquement CRM, même si sa valeur est moins complète |
| 15 | 2026-10-21 | S4 | Écart du client actif Gold à CD-001 (RQ-018) | Recommandation : suspendre la publication ; ne pas masquer l'écart en modifiant la définition. Demander au Data Owner d'arbitrer après analyse des 2 948 clients d'écart. | Vue Gold : 34 695 ; CD-001 Bronze : 37 643 ; RQ-018 échoue sur les trois directions. Preuves : `reports/us27_gold_counts.csv`, mesure `dq.dq_history`. | Data Steward (recommandation) | Publier malgré l'écart ou supprimer les filtres de certification |

Ajoutez des lignes autant que nécessaire. Exemples de décisions attendues : sévérité d'une règle, seuil d'avertissement, définition unique du client actif, convention de la valeur sentinelle, seuils de rapprochement, règle de survie par attribut, seuil de la porte G.
