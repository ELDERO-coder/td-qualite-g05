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

Ajoutez des lignes autant que nécessaire. Exemples de décisions attendues : sévérité d'une règle, seuil d'avertissement, définition unique du client actif, convention de la valeur sentinelle, seuils de rapprochement, règle de survie par attribut, seuil de la porte G.
