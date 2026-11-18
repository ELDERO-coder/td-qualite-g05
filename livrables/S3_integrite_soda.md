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

## 2 bis. Mesure des contrats candidats à la quarantaine

Recomptage en lecture seule des contrats CRM, en appliquant les cinq contrôles ci-dessous. Ces volumes sont des **candidats à la mise en attente**, pas une quarantaine réellement exécutée : le pipeline contrat n'est pas implémenté et aucun rejet de contrat n'a été enregistré dans `dq.rejets`.

| Règle | Motif | Contrats concernés |
|---|---|---:|
| RQ-001 | Fin antérieure ou égale au début | 800 |
| RQ-010 | Durée de garantie hors domaine | 600 |
| RQ-011 | Type de contrat absent du référentiel | 200 |
| RQ-012 | Souscripteur orphelin | 1 000 |
| RQ-013 | Assuré orphelin, sentinelle `0` exclue | 300 |
| **Union des cinq règles** | **Contrats distincts concernés** | **2 892 / 100 000 (2,892 %)** |

Les cinq comptages donnent 2 900 occurrences de règles. Huit contrats cumulent deux motifs : quatre « assuré orphelin + durée invalide », deux « période invalide + assuré orphelin », un « durée invalide + type inconnu » et un « assuré orphelin + type inconnu ». Il reste 97 108 contrats sans l'un de ces cinq motifs; cela ne vaut pas certification, les autres règles restant à mesurer.

**Impact sinistres à prendre en compte :** 1 092 sinistres sont rattachés à un contrat ayant au moins un de ces motifs; 14 de ces sinistres sont également hors période de garantie. Au total, 1 200 sinistres sont hors garantie (RQ-017). Ces chiffres mesurent un impact potentiel; ils ne justifient pas de supprimer les contrats ou sinistres. Il faut conserver les lignes, tracer le motif et arbitrer le traitement métier avant toute mise en quarantaine.

Requête de contrôle en lecture seule, exécutable dans MariaDB sur la base chargée. La colonne `contrats_distincts_avec_motif` déduplique les motifs par contrat; les trois dernières colonnes mesurent l'impact sur les sinistres.

```sql
WITH contrat_flags AS (
    SELECT c.contrat_id,
           (c.date_fin <= c.date_debut) AS periode_invalide,
           (c.duree_garantie_mois IS NULL
             OR c.duree_garantie_mois NOT IN (12, 24, 36, 60)) AS duree_invalide,
           (c.code_type IS NOT NULL AND t.code_type IS NULL) AS type_inconnu,
           (c.souscripteur_id IS NOT NULL AND sub.client_id IS NULL) AS souscripteur_orphelin,
           (c.assure_id IS NOT NULL AND c.assure_id <> '0'
             AND ass.client_id IS NULL) AS assure_orphelin
    FROM crm.contrat c
    LEFT JOIN crm.type_contrat t ON t.code_type = c.code_type
    LEFT JOIN crm.client sub ON sub.client_id = c.souscripteur_id
    LEFT JOIN crm.client ass ON ass.client_id = c.assure_id
), sinistre_flags AS (
    SELECT s.sinistre_id,
           (f.periode_invalide OR f.duree_invalide OR f.type_inconnu
             OR f.souscripteur_orphelin OR f.assure_orphelin) AS contrat_avec_motif,
           (s.date_survenance < c.date_debut
             OR s.date_survenance > c.date_fin) AS hors_garantie
    FROM crm.sinistre s
    JOIN crm.contrat c ON c.contrat_id = s.contrat_id
    JOIN contrat_flags f ON f.contrat_id = c.contrat_id
)
SELECT
    (SELECT COUNT(*) FROM crm.contrat) AS contrats_total,
    (SELECT SUM(periode_invalide) FROM contrat_flags) AS RQ_001,
    (SELECT SUM(duree_invalide) FROM contrat_flags) AS RQ_010,
    (SELECT SUM(type_inconnu) FROM contrat_flags) AS RQ_011,
    (SELECT SUM(souscripteur_orphelin) FROM contrat_flags) AS RQ_012,
    (SELECT SUM(assure_orphelin) FROM contrat_flags) AS RQ_013,
    (SELECT SUM(periode_invalide OR duree_invalide OR type_inconnu
                OR souscripteur_orphelin OR assure_orphelin)
       FROM contrat_flags) AS contrats_distincts_avec_motif,
    (SELECT SUM(contrat_avec_motif) FROM sinistre_flags) AS sinistres_lies_aux_contrats_avec_motif,
    (SELECT SUM(hors_garantie) FROM sinistre_flags) AS RQ_017,
    (SELECT SUM(contrat_avec_motif AND hors_garantie) FROM sinistre_flags)
        AS sinistres_avec_les_deux_motifs;
```

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
