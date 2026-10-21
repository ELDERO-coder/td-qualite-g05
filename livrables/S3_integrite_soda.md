# S3 · Soda Core : intégrité entre tables, portes en SodaCL

Groupe : Groupe 05 · Mesures : 21/10/2026 · Oussama : Data Owner et Rédacteur. Les décisions de statut et la définition métier CD-001 doivent être arbitrées et consignées par le Data Owner avant validation. Tag prévu : `seance-3`.

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Checks et configuration (US-12)

Fichiers : `soda/configuration.yml`; `soda/checks/client_checks.yml`; `soda/checks/contrat_checks.yml`; `soda/checks/sinistre_checks.yml`. Exécution : `docker exec dq_jupyter soda scan -d crm -c soda/configuration.yml soda/checks/<fichier>.yml`. Couche mesurée : CRM source. Les référentiels pays/postal/BAN existent dans Silver.

| Règle | Fichier de checks | Couche mesurée | Résultat Soda (PASSED, WARN, FAILED) | Valeur mesurée | Code retour du scan |
|---|---|---|---|---|---|
| RQ-003 | `client_checks.yml` | CRM | FAILED | 5 989 téléphones manquants/blancs sur les souscripteurs | 1 |
| RQ-005 | `client_checks.yml` | CRM | FAILED | 1 456 CP FR non conformes / 95 437 testés | 1 |
| RQ-007 | `client_checks.yml` | CRM | FAILED | 3 050 pays absents de `silver.ref_pays` | 1 |
| RQ-009, RQ-015 | `client_checks.yml` | CRM | FAILED | 200 types hors domaine; 479 prospects avec contrat | 1 |
| RQ-001, RQ-010, RQ-011, RQ-012, RQ-013 | `contrat_checks.yml` | CRM | FAILED | 800 périodes; 600 durées; 200 types contrat inconnus; 1 000 souscripteurs orphelins; 300 assurés orphelins après sentinelle | 1 |
| RQ-018 | `contrat_checks.yml` | CRM | PASSED | Écart 0 entre les trois comptages CD-001 (55 602 chacun) | 0 pour ce check |
| RQ-017 | `sinistre_checks.yml` | CRM | FAILED | 1 200 sinistres hors période de garantie | 1 |
| RQ-014 | `sinistre_checks.yml` | CRM | FAILED | Taux d'adresses non rapprochées à la BAN : 12,1 % (>10 %) | 1 |
| RQ-020, format CP et adresse non nulle | `sinistre_checks.yml` | CRM | PASSED | 3 checks passés : unicité sinistre, CP sur 5 chiffres, adresse non nulle | 0 pour ces checks |

Les exécutions observées renvoient un code non nul lorsque des checks échouent (`FAILED`); les seuils `warn`/`fail` sont déclarés pour les métriques RQ-018 et RQ-014. Un test isolé d'un scan contenant uniquement un avertissement n'a pas été réalisé; ne pas conclure ici sur ce mode.

RQ-001, RQ-003, RQ-005, RQ-009 et RQ-010 retrouvent les mêmes nombres d'échecs que GE (800, 5 989, 1 456, 200 et 600). Soda ajoute les contrôles inter-tables et le référentiel pays (RQ-007 : 3 050). Les dénominateurs diffèrent pour RQ-005 selon le traitement du sous-ensemble français; comparer les 1 456 échecs au dénominateur Soda de 95 437.

## 2. Bilan d'intégrité (US-16)

Aucune clé étrangère n'est déclarée dans la base : chaque relation est à vérifier.

| Relation | Lignes testées | Orphelins | Taux | Conclusion (anomalie, sentinelle, normal) |
|---|---|---|---|---|
| `contrat.souscripteur_id` vers client | 100 000 | 1 000 | 99,000 % | Anomalies RQ-012; à traiter/quarantainer avant Gold. |
| `contrat.assure_id` vers client, sentinelle exclue | 60 000 | 300 | 99,500 % | 40 000 lignes portent la sentinelle `0`; 300 orphelins réels restent. |
| `contrat.code_type` vers type_contrat | 100 000 | 200 | 99,800 % | RQ-011 bloquante; valeurs à qualifier. |
| `sinistre.contrat_id` vers contrat | 100 000 | 0 | 100 % | Aucune référence de contrat orpheline observée. |
| `sinistre` dans période de garantie du contrat | 100 000 | 1 200 | 98,800 % | RQ-017 bloquante; date hors période ou dates de contrat à investiguer. |

## 3. Valeur sentinelle (US-17)

| Contrôle | Orphelins | Preuve |
|---|---|---|
| Sur `assure_id`, sans exclure la sentinelle | 40 300 faux orphelins (40 000 sentinelles + 300 références invalides) | `pipelines/profile_s3.py` |
| Sur `assure_id`, après exclusion de `0` | 300 orphelins non sentinelles sur 60 000 références testées | `pipelines/profile_s3.py`; Soda filter `assure_id <> '0'` |

Convention technique issue de RQ-013 : traiter `assure_id='0'` comme « assuré non renseigné » et l'exclure du contrôle de référence; le garder brut en CRM/Bronze, sans réécrire la source. RQ-013 reste à arbitrer formellement par le Data Owner pour Silver.

Le contrôle naïf prend chaque `0` pour une clé client étrangère orpheline : il afficherait 40 300 écarts au lieu des 300 références non sentinelles réellement orphelines.

## 4. Statuts et garantie (US-18, US-19)

| Règle | Couche | Lignes testées | Échecs | Taux |
|---|---|---|---|---|
| RQ-015 (prospect sans contrat) | CRM source | 20 958 prospects | 479 prospects avec contrat (97,714 % conformes) | 97,714 % |
| RQ-016 (souscripteur avec contrat) | CRM source | 49 898 souscripteurs | 955 sans contrat (98,086 % conformes) | 98,086 % |
| RQ-017 (sinistre dans garantie) | CRM source | 100 000 sinistres joints | 1 200 hors période (98,800 % conformes) | 98,800 % |

Pas de correction automatique du statut décidée : RQ-015 est bloquante (479 cas) et RQ-016 avertissement (955 cas). Proposition au Data Owner : ne pas modifier `type_personne` à partir de la seule présence d'un contrat; qualifier les cas puis corriger via règle tracée en Silver. Décision non signée; à inscrire au journal après validation.

## 5. Définition unique du client actif (US-14)

Requête calculée par `pipelines/profile_s3.py` et par le check Soda RQ-018 dans `soda/checks/contrat_checks.yml`, référence `2026-10-14`.

| Direction | Chiffre obtenu avec la requête unique |
|---|---|
| Commerciale | 55 602 |
| Sinistres | 55 602 |
| Risques | 55 602 |

Contrôle RQ-018 : écart mesuré 0; le check Soda corrigé passe. Définition technique selon catalogue : contrat en cours ET cotisation à jour sur trois mois, client souscripteur ou assuré, `assure_id='0'` exclu. Validation Data Owner de cette interprétation à confirmer.

## 6. Critères de fin

- [x] Un scan renvoie un code retour non nul quand une règle en échec est détectée.
- [x] Les checks exécutés portent l'identifiant RQ et sont associés à la source CRM; RQ-021/Soda layers complémentaires à étendre.
- [x] Les trois directions obtiennent le même chiffre avec la requête unique : 55 602.
- [x] La sentinelle est quantifiée et exclue du test de référence; validation formelle de convention encore requise.

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés : RQ-018 était figée au 01/10/2026 et ne prenait que les souscripteurs; corrigée pour le lot 14/10 et le CD-001. Les scans restent en échec sur les anomalies source mesurées.

Point de reprise : aucun.

À améliorer : versionner les rapports de scan expurgés et faire approuver par le Data Owner les conventions sentinelle/statut avant Silver.
