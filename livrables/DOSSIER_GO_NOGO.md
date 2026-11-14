# Dossier Go/No-Go — Migration des données AssurConnect vers le CRM

**Groupe :** Groupe 05 · **Lot :** `L-2026-10-14` · **État du dossier :** NO-GO déclaré signé; date et preuve de signature à joindre
**Destinataire :** Direction Générale · **Date de préparation :** 14/11/2026

## 1. Recommandation

> **NO-GO pour la publication du lot `L-2026-10-14` vers le CRM cible.**

1. Le certificat réel `CERT-L20261014-132851` conclut à **NO_GO** : seulement **2 règles bloquantes sur 19** sont mesurées conformes dans leur couche attendue; 17 ne sont pas couvertes.
2. Les données clients seules sont transformées : **140 000** lignes dans Silver, dont **41 510** marquées `A_SURVEILLER`. Les traitements Silver/Gold des contrats et sinistres et la porte S complète ne sont pas implémentés.
3. La réconciliation de publication **RQ-025**, les tables CRM cibles et le chargeur transactionnel sont absents. Aucune publication vers le CRM n’a eu lieu.

Le refus de publication protège la cible; il ne signifie pas que toutes les données sources ont été corrigées ou que Gold est entièrement certifié.

## 2. Preuves de qualité par couche

Les résultats indiquent la couche réellement testée. **« Non mesuré » ne signifie pas « conforme ».** Les seuils de catalogue sont des propositions de travail; leur approbation par le Data Owner n’est pas consignée.

| Dimension / règle | Source ou Bronze | Silver | Gold / cible | Seuil de référence | Conclusion |
|---|---|---|---|---|---|
| Réconciliation et métadonnées (RQ-021/022) | 100 %; 385 262 lignes rapprochées, zéro écart sur 7 tables | Sans objet pour ces contrôles | Sans objet | 100 % | Conforme en Bronze seulement |
| Cohérence des dates (RQ-001) | Bronze : 99,200 %; 800 échecs sur 100 000 contrats | Non mesuré | Non mesuré | 100 % proposé | Non conforme en Bronze; porte S non évaluée |
| Complétude téléphone (RQ-003) | Bronze : 87,998 %; 5 989 échecs sur 49 898 souscripteurs | Non mesuré | Non mesuré | 98 % proposé | Sous le seuil proposé; avertissement |
| Validité code postal FR (RQ-005) | Bronze : 98,474 %; 1 456 échecs sur 95 437 lignes testées | Non mesuré par expectation | Non mesuré | 98 % proposé | Scan source en échec; pas de preuve Silver/Gold |
| Intégrité référentielle (RQ-011/012/013) | CRM : 200 types inconnus, 1 000 souscripteurs orphelins et 300 assurés orphelins après exclusion de la sentinelle `0` | Non mesuré | Contrats Gold non créés | 100 % proposé | Non certifiable |
| Traçabilité de publication (RQ-025) | Sans objet | Sans objet | Aucune réconciliation Gold → CRM cible | 100 % proposé | Non implémenté |

### Certificat et empreinte

| Champ du certificat `dq.certificat_qualite` | Valeur attestée dans le livrable S5 |
|---|---|
| `certificat_id` | `CERT-L20261014-132851` |
| `batch_id` | `L-2026-10-14` |
| `nb_bloquantes_testees` | 2 |
| `nb_bloquantes_ok` | 2 |
| `decision` | `NO_GO` |
| `empreinte_gold` (SHA-256) | `85b9884af4b72ecb46a8784e86402625befbc5e6eb41cc1091fbd6e9ae05e01e` |
| `signataire` | `NULL` / aucun signataire |

La ligne a été relue directement dans MariaDB, sans modifier la base. L’export de cette ligne est joint dans [`CERTIFICAT_QUALITE.csv`](./CERTIFICAT_QUALITE.csv). Il confirme le NO-GO, l’absence de signataire et l’empreinte Gold ci-dessus.

```sql
SELECT certificat_id, batch_id, nb_bloquantes_testees, nb_bloquantes_ok,
       empreinte_gold, decision, signataire, commentaire, emis_le
FROM dq.certificat_qualite
WHERE certificat_id = 'CERT-L20261014-132851';
```

### État des trois exemples de traçabilité demandés

1. **Client :** chaîne technique disponible `gold.xref_identifiants` → `silver.client` → `bronze.crm_client` ou `bronze.cif_clients`; exemple nominatif non sélectionné/validé.
2. **Code postal à zéro initial :** restauration autorisée uniquement si le couple code postal/commune figure dans le référentiel; identifiants de ligne d’un cas précis non vérifiés.
3. **Adresse de sinistre :** source Bronze disponible; Silver/Gold des sinistres non implémentés, donc lineage complet non démontré.

## 3. Écarts et hypothèses ouvertes

| Écart | Chiffre observé | Règle / couche | Conséquence pour le CRM | Responsable proposé |
|---|---:|---|---|---|
| Anomalies dans les données Gold | Contrats/sinistres Gold absents; état final non mesuré | RQ-001, RQ-011/012/013/017; S/G | Ne pas considérer le périmètre métier complet comme certifié | Ingénieur qualité |
| Quarantaine formelle | Non implémentée; 41 510 clients sont `A_SURVEILLER` | RQ-022/024; Silver | Les lignes sont conservées; ne pas annoncer qu’elles sont rejetées ou isolées | Ingénieur qualité + Data Steward |
| Alertes source | RQ-003 : 5 989; RQ-005 : 1 456; RQ-007 : 3 050; RQ-014 : 12,1 % d’adresses BAN non reconnues | CRM source | Qualification métier requise; pas de correction automatique | Data Steward |
| Couverture du certificat | 17/19 règles bloquantes non mesurées dans la couche attendue | Catalogue / certificat S5 | Publication interdite | Data Owner |
| Réconciliation après chargement | Non disponible; aucune ligne chargée | RQ-025 / CRM cible | Égalité des volumes et empreintes non prouvée | Ingénieur qualité |

**Hypothèses à valider par le métier :**

- définition unique CD-001 du client actif et périmètre souscripteur/assuré;
- convention `assure_id = 0` : sentinelle d’assuré non renseigné; 300 orphelins réels restent après son exclusion;
- statut par défaut des clients CIF et règle de survie des attributs (priorité CRM actuellement provisoire);
- autorisation ou interdiction de toute fusion floue : le seuil 0,85 est évalué sur 200 paires (99 % de précision, 98 % de rappel), mais aucune fusion floue n’est appliquée en production;
- sévérités et seuils du catalogue : les valeurs inscrites dans `initdb/02_dq_regles.sql` sont à approuver par le Data Owner.

## 4. Décision, rôles et conditions avant toute publication

Le journal `livrables/JOURNAL_DECISIONS.md` ne contient actuellement aucune décision signée. Les seuils de 100 % pour les règles bloquantes, de 98 % pour les avertissements et l’écart nul de RQ-018 sont des **propositions de référence**, pas des décisions approuvées.

| Rôle | Attribution de travail à confirmer |
|---|---|
| Décideur / Data Owner | Oussama (rôle S5 confirmé par le groupe) |
| Contrôle métier / Data Steward | Romeo (Dewano dans le dépôt), rôle S5 confirmé par le groupe |
| Exécution des contrôles et pipeline | Paul, Ingénieur qualité (rôle S5 confirmé); contributions détaillées à partager dans `livrables/00_equipe.md` |

| Condition avant demande de GO | Responsable proposé | Échéance |
|---|---|---|
| Compléter les transformations et les tests Silver/Gold pour contrats et sinistres; exécuter les 19 contrôles bloquants dans leurs couches cibles | Ingénieur qualité; revue Data Steward | Avant toute nouvelle certification |
| Faire arbitrer et consigner CD-001, sentinelle, statuts CIF, règles de survie et sévérités | Data Owner, avec le Data Steward | Avant le gel de Gold |
| Implémenter RQ-025 et le chargeur transactionnel; vérifier empreinte, refus NO-GO, atomicité et égalité avec la cible CRM | Ingénieur qualité | Avant toute publication |
| Réexécuter le certificat et joindre son export direct pour toute nouvelle décision (l’export NO-GO actuel est joint) | Ingénieur qualité; signature Data Owner seulement si la décision le permet | Avant remise / nouvelle bascule |

**Décision NO-GO : signature déclarée comme effectuée par Oussama, Data Owner, selon la confirmation du groupe.**
Date et preuve de signature : à joindre/indiquer sur la copie remise par le Data Owner. Le certificat réel actuel reste NO_GO et son champ `signataire` demeure NULL; cette signature de dossier ne modifie pas l’enregistrement du certificat.

## Références du dépôt

`livrables/S1_bronze_profilage.md`; `livrables/S2_regles_great_expectations.md`; `livrables/S3_integrite_soda.md`; `livrables/S4_silver_gold.md`; `livrables/S5_certificat_publication.md`; `livrables/JOURNAL_DECISIONS.md`; `AVANCEMENT.md`; `pipelines/certify_s5.py`; `pipelines/publish_s5.py`.
