# Dossier Go/No-Go — Migration des données AssurConnect vers le CRM

**Groupe :** Groupe 05 · **Lot :** `L-2026-10-14` · **État du dossier :** NO-GO opérationnel déclaré; preuve de signature non jointe
**Destinataire :** Direction Générale · **Dernière mise à jour :** 18/11/2026

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

### État des exemples de traçabilité demandés

1. **Client — cas Meunier de Lille :** CRM `A-17929` et CIF `K385175` sont reliés chacun à Bronze, Silver et Gold dans [`S4_silver_gold.md`](./S4_silver_gold.md). Les coordonnées concordent, mais le pipeline les conserve dans deux Gold (`CLI-047477` et `CLI-022264`). C'est un candidat documenté, pas un golden record fusionné ni une validation légale.
2. **Code postal à zéro initial :** le pipeline ne restaure un zéro que si le couple code postal/commune existe dans le référentiel; aucun cas précis avec ses identifiants de ligne n'est encore vérifié.
3. **Adresse de sinistre :** source Bronze disponible; Silver/Gold des sinistres non implémentés, donc lineage complet non démontré.

## 3. Écarts et hypothèses ouvertes

### Mesure des contrats à examiner et impact sur les sinistres

Recomptage en lecture seule sur les 100 000 contrats CRM. L'union est calculée par identifiant de contrat afin de ne pas additionner deux fois les lignes présentant plusieurs motifs.

| Contrôle | Contrats concernés |
|---|---:|
| Fin antérieure ou égale au début (RQ-001) | 800 |
| Durée hors domaine (RQ-010) | 600 |
| Type absent du référentiel (RQ-011) | 200 |
| Souscripteur orphelin (RQ-012) | 1 000 |
| Assuré orphelin, sentinelle `0` exclue (RQ-013) | 300 |
| **Union : au moins un de ces motifs** | **2 892 / 100 000 (2,892 %)** |
| Sans aucun de ces cinq motifs | 97 108 / 100 000 (97,108 %) |

Il y a 2 900 occurrences de règles et 2 892 contrats distincts : huit contrats cumulent deux motifs. Parmi les 100 000 sinistres, 1 092 sont rattachés à un contrat ayant au moins un de ces motifs; 14 de ces sinistres sont aussi hors période de garantie. Tous motifs confondus, 1 200 sinistres sont hors garantie (RQ-017). Les données n'ont pas été mises en quarantaine : ce sont des volumes d'investigation, non une décision de suppression ou de rejet.

**Comment challenger le résultat sans masquer les anomalies :** conserver Bronze intact; établir en Silver une table de rejets/attente avec l'identifiant, le lot et un motif par règle; traiter les anomalies de référence (souscripteur/assuré/type) séparément des anomalies de dates/durée; rapprocher les 1 092 sinistres touchés avec les équipes métier; puis recalculer les cinq taux et les contrôles RQ-017 sur Silver/Gold. Comparer les volumes `Bronze = Silver accepté + attente/rejets`, vérifier les doublons de motifs et soumettre les corrections au Data Owner/Data Steward. Ces étapes sont une cible de travail, pas des traitements déjà exécutés; aucun seuil métier nouveau n'est présumé approuvé.

| Écart | Chiffre observé | Règle / couche | Conséquence pour le CRM | Responsable proposé |
|---|---:|---|---|---|
| Anomalies dans les données Gold | Contrats/sinistres Gold absents; état final non mesuré | RQ-001, RQ-011/012/013/017; S/G | Ne pas considérer le périmètre métier complet comme certifié | Ingénieur qualité |
| Contrats candidats à l'attente | 2 892 contrats distincts (2,892 %); quarantaine non implémentée | RQ-001/010/011/012/013; CRM | Conserver les lignes et examiner les motifs; ne pas annoncer qu'elles sont déjà isolées | Ingénieur qualité + Data Steward |
| Clients à surveiller | 41 510 clients marqués `A_SURVEILLER`; aucun rejet client dans `dq.rejets` | Silver | Les lignes sont conservées; statut distinct d'une quarantaine | Ingénieur qualité + Data Steward |
| Sinistres rattachés aux contrats candidats | 1 092/100 000; dont 14 également hors garantie | RQ-017; CRM | Revue conjointe contrats/sinistres avant toute correction ou exclusion | Data Steward |
| Alertes source | RQ-003 : 5 989; RQ-005 : 1 456; RQ-007 : 3 050; RQ-014 : 12,1 % d’adresses BAN non reconnues | CRM source | Qualification métier requise; pas de correction automatique | Data Steward |
| Couverture du certificat | 17/19 règles bloquantes non mesurées dans la couche attendue | Catalogue / certificat S5 | Publication interdite | Data Owner |
| Réconciliation après chargement | Non disponible; aucune ligne chargée | RQ-025 / CRM cible | Égalité des volumes et empreintes non prouvée | Ingénieur qualité |

**Hypothèses à valider par le métier :**

- définition unique CD-001 du client actif et périmètre souscripteur/assuré;
- convention `assure_id = 0` : sentinelle d’assuré non renseigné; 300 orphelins réels restent après son exclusion;
- statut par défaut des clients CIF et règle de survie des attributs (priorité CRM actuellement provisoire);
- autorisation ou interdiction de toute fusion floue : le seuil 0,85 est évalué sur 200 paires (99 % de précision, 98 % de rappel), mais aucune fusion floue n’est appliquée en production;
- fusion de personnes morales : le couple Meunier de Lille est un candidat solide sur les attributs observés, mais il manque un identifiant légal contrôlé et une approbation métier avant de ramener les deux `cli_id` Gold à une seule ligne;
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

**Décision NO-GO :** le groupe déclare qu’Oussama, Data Owner, a signé le dossier. La date et la preuve de signature ne sont toutefois pas jointes ici; le statut de signature est donc à documenter avant la remise définitive. Le certificat réel actuel reste `NO_GO` et son champ `signataire` demeure `NULL`; une signature du dossier ne modifie pas l’enregistrement du certificat.

## Références du dépôt

`livrables/S1_bronze_profilage.md`; `livrables/S2_regles_great_expectations.md`; `livrables/S3_integrite_soda.md`; `livrables/S4_silver_gold.md`; `livrables/S5_certificat_publication.md`; `livrables/JOURNAL_DECISIONS.md`; `AVANCEMENT.md`; `pipelines/certify_s5.py`; `pipelines/publish_s5.py`.
