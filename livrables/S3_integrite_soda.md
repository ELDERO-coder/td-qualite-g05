# S3 · Soda Core : intégrité entre tables, portes en SodaCL

Groupe : [À COMPLÉTER]  ·  Date : [À COMPLÉTER]  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-3`

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Checks et configuration (US-12)

Fichiers (chemins) : configuration [soda/configuration.yml] ; checks client [soda/checks/bronze/client_checks.yml] ; contrat [soda/checks/bronze/contrat_checks.yml] ; sinistre [soda/checks/bronze/sinistre_checks.yml]

| Règle | Fichier de checks | Couche mesurée | Résultat Soda (PASSED, WARN, FAILED) | Valeur mesurée | Code retour du scan |
|---|---|---|---|---|---|
| RQ-003 | client_checks.yml | BRONZE | FAILED | 5989 | 2 |
| RQ-005 | client_checks.yml | BRONZE | FAILED | 1456 | 2 |
| RQ-007 | client_checks.yml | BRONZE | FAILED | 3050 | 2 |
| RQ-009 | client_checks.yml | BRONZE | FAILED | 200 | 2 |
| RQ-001 | contrat_checks.yml | BRONZE | FAILED | 800 | 2 |
| RQ-010 | contrat_checks.yml | BRONZE | FAILED | 600 | 2 |
| RQ-012 | contrat_checks.yml | BRONZE | FAILED | 1000 | 2 |
| RQ-013 | contrat_checks.yml | BRONZE | FAILED | 300 | 2 |
| RQ-016 | integrite_checks.yml | BRONZE | WARN | 955 | 1 |
| RQ-017 | sinistre_checks.yml | BRONZE | FAILED | 1200 | 2 |
| RQ-020 | sinistre_checks.yml | BRONZE | PASSED | 0 | 2 |

Un avertissement et un échec : à quelle condition le code retour du scan devient-il non nul ? 
Un scan soda renvoie un code nul lorsqu'un contrôle déclenche un avertissement ou un échec : 0 signifie conforme, 1 avertissement, 2 échec et 3 erreur d'exécution.

Les valeurs Soda sont-elles cohérentes avec celles de Great Expectations en S2 ? Écarts et explication :
Les valeurs soda sont cohérentes avec celles de Great Expectations en S2 pour les règles communes : RQ-001 (800), RQ-003 (5989), RQ-005 (1456), RQ-007 (3050), RQ-009 (200) et RQ-010 (600). Les contrôles de clés primaires RQ-020 ne détectent également aucune anomalie.


## 2. Bilan d'intégrité (US-16)

Aucune clé étrangère n'est déclarée dans la base : chaque relation est à vérifier.

| Relation | Lignes testées | Orphelins | Taux | Conclusion (anomalie, sentinelle, normal) |
|---|---|---|---|---|
| contrat.souscripteur_id vers client | 100 000 | 1000 | 1.00 % | Anomalie, souscripteurs absents de la table client |
| contrat.assure_id vers client | 60 000 | 300 | 0.50 % | Anomalie après exclusion de la sentinelle 0 |
| contrat.code_type vers type_contrat | 100 000 | 200 | 0.20 % | Anomalie, types de contrat absents du référentiel |
| sinistre.contrat_id vers contrat | 100 000 | 0 | 0.00 % | Normal, aucun orphelin détecté |
| client.pays vers ref_pays | 100 000 | 3 050 | 3.05 % | Anomalie, codes pays absents du référentiel |

## 3. Valeur sentinelle (US-17)

| Contrôle | Orphelins | Preuve |
|---|---|---|
| Sur `assure_id`, avant traitement de la sentinelle | 40 300 | Scan Soda RQ-013 sans filtre : 40.3 % des 100 000 contrats |
| Sur `assure_id`, après traitement | 300 | Scan Soda RQ-013 avec filtre "assure_id <> '0'" : 0.5 % des 60 000 contrats contrôlés |

Écart chiffré et convention écrite (comment la valeur sentinelle est traitée, par qui, dans quelle couche) : L'écart est de 40 000 orphelins, correspondant aux 40 000 contrats dont "assure_id" = 0. La convention est que cette valeur signifie "pas d'assuré distinct". Le Data Engineer devra la remplacer par "NULL" lors du passage de Bronze à Silver.

Pourquoi le premier contrôle est trompeur : Sans filtre, soda considère les 40 000 valeurs sentinelles comme des clés étrangères invalides. Il détecte donc 40 300 orphelins, alors que seuls 300 correspondent à des références réellement absentes après exclusion de la sentinelle. Le contrôle initial surestime fortement les anomalies d'intégrité référentielle.

## 4. Statuts et garantie (US-18, US-19)

| Règle | Couche | Lignes testées | Échecs | Taux |
|---|---|---|---|---|
| RQ-015 (prospect sans contrat) | … | … | … | … |
| RQ-016 | … | … | … | … |
| RQ-017 (sinistre hors garantie) | … | … | … | … |

Règle de correction du statut proposée au Data Owner (texte, rôle, date) : [À COMPLÉTER]. Reportez-la dans `JOURNAL_DECISIONS.md`.

## 5. Définition unique du client actif (US-14)

Requête (chemin) : [À COMPLÉTER]

| Direction | Chiffre obtenu avec la requête unique |
|---|---|
| Commerciale | … |
| Sinistres | … |
| Risques | … |

Contrôle RQ-018 (écart entre définitions) : [À COMPLÉTER]

## 6. Critères de fin

- [ ] Un scan renvoie un code retour non nul quand une règle bloquante échoue.
- [ ] Chaque contrôle porte l'identifiant de sa règle et la couche mesurée.
- [ ] Les trois directions obtiennent le même chiffre avec la requête unique.
- [ ] La valeur sentinelle est expliquée et traitée.

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : [À COMPLÉTER]

Point de reprise utilisé (oui / non, lequel) : [À COMPLÉTER]

Ce que nous ferions autrement : [À COMPLÉTER]
