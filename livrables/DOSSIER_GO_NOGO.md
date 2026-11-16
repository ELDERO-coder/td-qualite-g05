# Dossier go/no-go : migration des données consolidées vers le CRM

Groupe : 05  ·  Date de remise : 21/10/2026  ·  Étiquette : `rendu-final`

Destinataire : la Directrice Générale. Registre : un rapport court, sans jargon, quatre pages au plus hors annexes. Chaque chiffre renvoie à une preuve du dépôt (livrable de séance, requête, fichier).

## 1. Recommandation

Recommandation (GO, NO-GO, ou GO sous conditions) et trois raisons chiffrées, en dix lignes au plus :

**Recommandation : NO-GO pour la publication CRM.**

1. RQ-018 échoue : la vue Gold compte **34 695** clients actifs, contre **37 643** selon CD-001 (−2 948, −7,83 %).
2. Le certificat `CERT-L-2026-10-14` est NO_GO : **20 contrôles bloquants conformes sur 21**.
3. Le parcours de publication refuse ce certificat ; les tables CRM cible restent vides. Le succès technique simulé a été annulé après vérification des sommes de contrôle.

## 2. Les preuves

Qualité mesurée par couche et par dimension (reprise de S5, avec la courbe) :

| Dimension | Bronze | Silver | Gold | Seuil visé | Atteint ? |
|---|---|---|---|---|---|
| Complétude / intégrité | 99,20 % (RQ-001) | 100 % (RQ-001, RQ-024) | 100 % hors RQ-018 | 100 % | Partiellement : RQ-018 échoue |
| Validité / exactitude | 87,998 % (RQ-003) | 88,022 % (RQ-003) ; 99,491 % (RQ-006) | 100 % pour les bloqueurs applicables | Seuils catalogue | À arbitrer pour les avertissements |
| Traçabilité | 100 % RQ-022 | 100 % RQ-023 | 100 % RQ-023 | 100 % | Oui sur les contrôles mesurés |
| Cohérence métier | 98,800 % RQ-017 | — | 0 % RQ-018 ; autres contrôles Gold 100 % | 100 % | Non |

Certificat joint : numéro `CERT-L-2026-10-14`, décision **NO_GO**, empreinte `2df4249206e80b53f2d3e1eb789eb44fafff5f0838b4f2258f806348347de693`.

Trois données retracées (détail : `livrables/S4_silver_gold.md`, section 5) :
- Société Meunier, CRM/CIF → CLI-012703.
- Code postal `7200` restauré en `07200`.
- Adresse du sinistre `85 RUE DU COMMERCE` reliée à sa ligne Bronze.

## 3. Les écarts

| Écart | Chiffre | Règle | Conséquence pour le CRM | Qui doit agir |
|---|---|---|---|---|
| Rapprochement CD-001 / Gold | Écart net de 2 948 : 562 identifiants sans Gold, 972 sans Gold actif, et 1 414 identifiants source regroupés par consolidation | RQ-018 | Écart expliqué, mais grain source vs Golden Record à faire valider ; ne pas publier | Data Owner + Data Steward |
| Lignes mises en quarantaine, par règle | S : RQ-007 1 450 ; RQ-009 80 ; RQ-001 800 ; RQ-010 600 ; RQ-014 11 951. G : RQ-002 1 594 ; RQ-011 199 ; RQ-012 2 487 ; RQ-013 1 257 ; RQ-015 1 009 ; RQ-017 5 259 | Règles indiquées | Données exclues du Gold ; traiter les causes métier à la source | Data Owners source |
| Avertissements restants | Silver : RQ-003 5 902 ; RQ-004 866 ; RQ-006 694 ; RQ-008 1 191 | RQ-003/004/006/008 ; Bronze RQ-016 955 | Garder visibles, arbitrer les seuils avant usage | Data Owner |
| Règles non mesurées ou non couvertes par le certificat | RQ-025 pas de chargement réel ; aucun nom/signature Data Owner | RQ-025 | Réconciliation exécutée uniquement en simulation transactionnelle | Data Owner + équipe migration |

Hypothèses à faire valider : seuils de rapprochement 70/69 ; survie par attribut et préférence CRM en cas d'égalité ; grain attendu par CD-001 après consolidation ; sévérité des quarantaines métier. Le détail du rapprochement RQ-018 est dans `RQ018_rapprochement.md`. Un test de dégradation volontaire (RQ-001) produit NO_GO ; le lot réel reste NO-GO tant que le Data Owner n'a pas arbitré l'écart et que la certification n'est pas conforme.

## 4. La décision

Seuils retenus et justifications : décisions 5–8 de `JOURNAL_DECISIONS.md`. Ils sont des propositions Data Steward, sauf la décision opérationnelle de suspendre la publication du lot non conforme.

Rôles : le Data Owner métier arbitre les définitions et seuils ; le Data Steward contrôle qualité, lineage et écarts ; l'équipe CRM exécute le chargement certifié. Le Data Owner et l'équipe CRM restent à nommer.

Conditions à lever avant migration, avec échéance et responsable :

| Condition | Responsable | Échéance |
|---|---|---|
| RQ-018 conforme à CD-001 et écart expliqué | Data Owner + Data Steward | Avant toute publication |
| Seuils Golden Record et règles de survie approuvés | Data Owner | Avant toute fusion métier |
| Nouveau certificat GO et publication RQ-025 réussie | Data Steward + équipe CRM | Après correction et recontrôle |

Signature du Data Owner (nom, rôle, date) : **non obtenue — décision NO-GO**.

## Annexes

Liens vers les livrables : `livrables/S1_bronze_profilage.md`, `S2_regles_great_expectations.md`, `S3_integrite_soda.md`, `S4_silver_gold.md`, `S5_certificat_publication.md`, `JOURNAL_DECISIONS.md`, `AVANCEMENT.md`.
