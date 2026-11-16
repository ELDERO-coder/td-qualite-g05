# S5 · Certifier, publier vers le CRM, gouverner

Groupe : 05  ·  Date : 21/10/2026  ·  Rédacteur : Data Steward  ·  Étiquette : `seance-5`

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Historique des mesures (US-29, US-30)

Une ligne par règle mesurée ; laissez vide la couche où la règle ne s'applique pas, et dites pourquoi.

| Règle | Dimension | Taux bronze | Taux silver | Taux gold | Évolution (monte, stable, descend) | Explication |
|---|---|---|---|---|---|---|
| RQ-001 | Cohérence | 99,200 % | 100 % | 100 % | monte | Les dates invalides sont exclues de Silver puis Gold |
| RQ-002 | Validité métier | 99,673 % | — | 100 % | monte | Les contrats de souscripteurs physiques mineurs/non vérifiables sont mis en quarantaine Gold |
| RQ-003 | Complétude | 87,998 % | 88,022 % | — | stable | Téléphones absents restent en avertissement Silver ; non applicable au client Gold certifié |
| RQ-005 | Validité format | 98,474 % | 100 % | — | monte | 1 478 zéros initiaux restaurés ; les codes français incomplets restants ne subsistent pas |
| RQ-009 | Validité domaine | 99,800 % | 100 % | — | monte | Valeurs invalides éliminées de Silver |
| RQ-010 | Validité domaine | 99,400 % | 100 % | 100 % | monte | Les durées hors domaine sont rejetées en Silver |
| RQ-014 | Précision, cohérence | 88,049 % | 100 % | 100 % | monte | Les lignes sans rapprochement BAN sont écartées |
| RQ-017 | Cohérence inter-tables | 98,800 % | — | 100 % | monte | Les sinistres hors garantie ou sans contrat certifié sont écartés |
| RQ-018 | Cohérence de définition | 100 % | — | 0 % | descend | Gold publie 34 695 clients actifs contre 37 643 CD-001 ; bloque le GO |
| RQ-023 | Traçabilité | — | 100 % | 100 % | stable | Les liens Silver/Gold vers Bronze sont présents |
| RQ-024 | Complétude | — | 100 % | — | stable | Silver + rejets = Bronze sur les quatre entités |

Les tirets indiquent une couche où la règle ne s'applique pas ou n'a pas été mesurée. Les taux pondèrent les lignes testées et ne sont pas des moyennes de pourcentages. Preuves détaillées : `livrables/us29_historique_mesures.csv`, `livrables/us29_kpi_dimensions.csv`.

Courbe : `reports/us30_evolution_qualite.svg` (les points manquants signalent une règle non mesurée dans cette couche).

Écarts d'évolution : RQ-018 passe de 100 % Bronze à 0 % Gold, car la consolidation et les contrôles bloquants diminuent le périmètre publiable sous la définition CD-001. La baisse n'est pas masquée par une modification de la règle. Les anomalies Bronze éliminées en Silver/Gold sont explicitement comptées dans les rapports de quarantaine ; RQ-003, RQ-004, RQ-006 et RQ-008 restent des avertissements Silver.

## 2. Certificat de qualité (US-31)

| Élément | Valeur |
|---|---|
| Numéro du certificat | `CERT-L-2026-10-14` |
| Lot | `L-2026-10-14` |
| Décision (GO ou NO_GO) | **NO_GO** |
| Règles bloquantes testées | 21 contrôles couvrant 18 règles, plus les mesures Silver/Gold applicables |
| Règles bloquantes conformes | 20/21 ; RQ-018 échoue sur les trois directions |
| Écarts connus (avertissements) | Silver : RQ-003 5 902, RQ-004 866, RQ-006 694, RQ-008 1 191 ; Bronze RQ-016 : 955 cas |
| Empreinte du gold | `2df4249206e80b53f2d3e1eb789eb44fafff5f0838b4f2258f806348347de693` |
| Signataire (rôle) | Aucun : génération automatique, aucune signature Data Owner enregistrée |

Requête de décision et contrôles : `pipelines/run_s5.py certify`. Détail : `livrables/us31_controles_certificat.csv`. Le certificat et les mesures sont stockés dans `dq.certificat_qualite` et `dq.dq_history`.

Épreuve NO_GO : le test transactionnel dégrade volontairement un contrat Gold (`date_fin = date_debut`) ; RQ-001 échoue et la décision calculée est NO_GO (`livrables/us31_no_go_test.csv`). Le lot de référence est également NO_GO sur RQ-018. Aucun GO nominal artificiel n'a été créé : le lot réel doit d'abord satisfaire CD-001.

Les 18 règles bloquantes des portes B/S/G sont couvertes par le certificat ; RQ-025 est mesurée à l'exécution de publication seulement. Aucune règle C de rapprochement CRM n'est certifiée tant que le chargement réel n'a pas lieu.

## 3. Publication vers le CRM (US-32)

Script : `pipelines/run_s5.py publish`. Remplacement complet de l'instantané cible dans une transaction unique ; vérification du certificat, de l'empreinte Gold puis de RQ-025.

| Scénario | Message obtenu | Chargement effectué ? | Preuve |
|---|---|---|---|
| Sans certificat | Refus explicite : aucun certificat | Non | `livrables/us32_self_test.csv` |
| Certificat NO_GO | Refus explicite : certificat `NO_GO` | Non | `livrables/us32_self_test.csv` et tentative réelle `run_s5.py publish` |
| Empreinte périmée après modification de Gold | Refus : empreinte différente | Non | Test d'une empreinte obsolète (`livrables/us32_self_test.csv`) |
| Certificat GO et Gold intact | Publication simulée transactionnellement, RQ-025 conforme | Oui, simulation seulement ; rollback final | `livrables/us32_self_test.csv`, `livrables/us32_self_test_reconciliation.csv` |

Réconciliation après chargement (RQ-025) :

| Table | Lignes gold | Lignes CRM cible | Somme de contrôle gold | Somme de contrôle CRM cible | Écart |
|---|---|---|---|---|---|
| client | 114 417 | 114 417 (simulation) | `2293a2a92f32b4e724f58542b0881fb25cfb73704805e052b5f86e50a888cd14` | identique | 0 |
| contrat | 93 427 | 93 427 (simulation) | `ea5545cb0f1725522c6fba0c044729f0e3b42da7bc1e980b5e7ba50718ffacc3` | identique | 0 |
| sinistre | 82 790 | 82 790 (simulation) | `931b26aeeb2bf0c7bdb260402682e366a551cf03bba4d4bd23cac5342f9776a0` | identique | 0 |

Le chargement est tout-ou-rien : les trois tables cibles sont remplacées sous une transaction unique. Le chemin GO de test a été exécuté puis annulé volontairement ; les trois tables `crm_cible` sont restées à zéro ligne. Le lot NO_GO n'a pas été publié.

## 3 bis. Gouvernance (US-34)

Fiche de catalogue : `catalogue/gold_client_unique.md`.

| Élément | Valeur |
|---|---|
| Propriétaire (Data Owner) | À désigner/valider par le métier ; aucune approbation nominative disponible |
| Steward (Data Steward) | Groupe 05 |
| Définition de « client actif » rattachée à la fiche | Contrat en cours au 01/10/2026 et cotisation depuis le 01/07/2026 (CD-001) |
| Règles RQ rattachées à la table | RQ-007, RQ-009, RQ-018, RQ-019, RQ-023 |

Lineage : CRM.client → Bronze.crm_client → Silver.client → Gold.xref_identifiants → Gold.client_unique ; CIF.clients → Bronze.cif_clients → Silver.client → Gold.xref_identifiants → Gold.client_unique. Détails dans `catalogue/gold_client_unique.md` et `reports/us28_trace.csv`.

## 4. Décisions de la séance

Décision 8 ajoutée dans `JOURNAL_DECISIONS.md` : un certificat GO exige 100 % des contrôles bloquants applicables ; l'exécution automatique ne vaut pas signature du Data Owner. Nombre de décisions ajoutées en S5 : 1.

## 5. Critères de fin

- [x] Un Gold volontairement dégradé produit NO_GO ; le lot réel est également NO_GO.
- [x] Le lot nominal reste NO_GO : RQ-018 est non conforme (20/21 contrôles bloquants conformes).
- [x] La publication refuse sans certificat, avec NO_GO, ou avec une empreinte obsolète.
- [x] Le parcours GO de test réconcilie comptages et SHA-256 ; l'essai est ensuite annulé.
- [x] Les décisions de seuil et de certification sont attribuées au Data Steward ; l'approbation Data Owner reste ouverte.

## 6. Difficultés, écarts avec l'attendu, reprise

Écart bloquant : 34 695 clients actifs Gold contre 37 643 dans CD-001 (−2 948, −7,83 %). La décision de gouvernance est NO_GO, sans signature Data Owner.

Point de reprise utilisé : oui, reprise du lot `L-2026-10-14` par `pipelines/run_s5.py` ; la publication a été testée sans charger le CRM cible.

À faire avant GO : analyser les 2 948 clients d'écart, faire valider par le Data Owner la définition/rapprochement et relancer les contrôles avec un certificat conforme.
