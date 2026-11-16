# S4 · Construire Silver et Gold

Groupe : 05  ·  Date : 21/10/2026  ·  Rédacteur : Data Steward  ·  Étiquette : `seance-4`

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Silver et quarantaine (US-21, US-22)

Scripts : `pipelines/build_silver.py`, `pipelines/build_gold.py`. Lot : `L-2026-10-14`.

Traitements appliqués (pays, code postal, identité, autres), avec le nombre de lignes touchées par chacun :

| Traitement | Table | Lignes modifiées | Garde-fou (ce que le traitement ne doit pas faire) |
|---|---|---|---|
| Restauration du zéro initial du code postal | `crm_client` | 1 478 | Ne pas modifier un code déjà complet ou non numérique |
| Normalisation des identités, pays, téléphones, courriels et dates | clients CRM/CIF | valeurs renseignées | Bronze reste inchangé ; signaler les anomalies restantes |
| Conversion de `assure_id='0'` en `NULL` | contrat | 40 000 sentinelles repérées en Bronze | Ne pas créer d'assuré fictif |

Invariant silver + rejets = bronze :

| Table | Lignes bronze | Lignes silver | Lignes rejetées | Écart |
|---|---|---|---|---|
| client (CRM) | 100 000 | 98 470 | 1 530 | 0 |
| client (CIF) | 40 000 | 40 000 | 0 | 0 |
| contrat | 100 000 | 98 600 | 1 400 | 0 |
| sinistre | 100 000 | 88 049 | 11 951 | 0 |

Rejets par règle (`dq.rejets`) :

| Règle | Table | Lignes rejetées | Raison métier |
|---|---|---|---|
| RQ-007 | client CRM | 1 450 | Pays absent ou non reconnu après normalisation |
| RQ-009 | client CRM | 80 | Type de personne hors domaine |
| RQ-001 | contrat | 800 | Dates absentes ou date de fin non postérieure au début |
| RQ-010 | contrat | 600 | Durée de garantie hors domaine |
| RQ-014 | sinistre | 11 951 | Adresse non rapprochée de la BAN |

Idempotence : relance de `build_silver.py`, mêmes comptages et mêmes rapports. SHA-256 : `us21_standardisation.csv` `472aff0f…`, `us22_quarantaine.csv` `85665548…`, `us23_bronze_vs_silver.csv` `a1a86f62…`.

## 2. Porte S : bronze contre silver (US-23)

| Règle | Sévérité | Taux bronze | Taux silver | Écart | Explication de l'écart |
|---|---|---|---|---|---|
| RQ-001 dates du contrat | Bloquante | 99,200 % (800/100 000) | 100 % (0/98 600) | +0,800 pt | Les 800 contrats non conformes sont en quarantaine |
| RQ-003 téléphone souscripteur | Avertissement | 87,998 % (5 989/49 898) | 88,021 % (5 902/49 275) | +0,023 pt | Le dénominateur change après quarantaine ; les téléphones absents restent visibles en Silver |
| RQ-005 code postal français | Avertissement | 98,474 % (1 456/95 437) | 100 % (0/136 360) | +1,526 pt | 1 478 codes ont retrouvé leur zéro initial ; le périmètre Silver inclut CRM et CIF |
| RQ-009 type de personne | Bloquante | 99,800 % (200/100 000) | 100 % (0/98 470 CRM) | +0,200 pt | Les valeurs hors domaine restantes sont rejetées |
| RQ-010 durée de garantie | Bloquante | 99,400 % (600/100 000) | 100 % (0/98 600) | +0,600 pt | Les 600 contrats hors domaine sont en quarantaine |
| RQ-014 rapprochement BAN | Bloquante | 88,049 % (11 951/100 000) | 100 % (0/88 049) | +11,951 pt | Les sinistres sans rapprochement BAN sont rejetés |

Les dénominateurs sont ceux des lignes applicables à chaque règle. RQ-007 : Soda compte 3 050 valeurs pays non canoniques en Bronze ; la normalisation reconnaît les alias, puis 1 450 pays irrécupérables sont rejetés. Avertissements conservés en Silver : RQ-003 5 902, RQ-004 866, RQ-006 694 et RQ-008 1 191 (`pipelines/build_silver.py`).

Toutes les règles bloquantes de la porte S sont conformes sur les lignes conservées : RQ-001, RQ-007, RQ-009, RQ-010 et RQ-014. RQ-020 (unicité), RQ-023 (traçabilité) et RQ-024 (conservation) ont zéro écart. Les erreurs métier de porte G restent à traiter avant publication.

## 3. Dédoublonnage et golden record (US-24, US-25)

| Paramètre | Valeur retenue | Justification |
|---|---|---|
| Normalisation appliquée avant comparaison | Valeurs Silver : casse, espaces, accents et formats normalisés | Comparaison CRM/CIF cohérente |
| Clé(s) de blocage | Identité normalisée, courriel exact ou date de naissance exacte | 1 131 869 candidates ; évite le produit cartésien |
| Mesure de similarité | RapidFuzz : nom 50 %, naissance 20 %, CP 15 %, ville 10 %, courriel 5 % | Score reproductible |
| Seuil de fusion automatique | 70/100 | Plancher conservateur ; zéro faux positif sur les 200 paires étiquetées |
| Seuil de la zone de revue | 69/100 | 99 paires candidates à 69 proposées à revue |

| Mesure | Valeur |
|---|---|
| Groupes de doublons trouvés | 21 544 |
| Paires fusionnées automatiquement | 26 672 |
| Paires en zone de revue | 99 |
| Précision sur les 200 paires étiquetées | 100 % (94 vrais positifs, 0 faux positif) |
| Rappel sur les 200 paires étiquetées | 94 % (6 faux négatifs) |
| Identités distinctes obtenues | 114 417 |

Golden record de la Société Meunier :

| Identifiant source | Système | CLI attribué |
|---|---|---|
| A-17929 | CRM | CLI-012703 |
| K385175 | CIF | CLI-012703 |

Règle de survie par attribut :

| Attribut | Source retenue | Règle (priorité, plus récent, non nul) | Cas où la règle se trompe |
|---|---|---|---|
| Nom | CRM 91 139 groupes ; CIF 23 278 | Valeur la plus complète ; CRM en cas d'égalité | Le nom le plus long peut être erroné |
| Adresse | CRM 90 392 groupes ; CIF 24 025 | Valeur la plus complète ; CRM en cas d'égalité | La longueur ne prouve pas que l'adresse est actuelle |
| Téléphone | CRM 82 642 groupes ; CIF 20 957 | Format valide puis valeur présente ; CRM en cas d'égalité | Un numéro valide peut être obsolète |
| Courriel | CRM 75 181 groupes ; CIF 14 175 | Format valide puis valeur présente ; CRM en cas d'égalité | Le format n'atteste pas que la boîte existe |

Les seuils et la survie sont consignés comme propositions Data Steward dans `JOURNAL_DECISIONS.md` (décisions 5 et 6), en attente du Data Owner.

## 4. Gold et client actif (US-27)

| Table gold | Lignes | Lignes écartées (porte G) | Règles responsables |
|---|---|---|---|
| client_unique | 114 417 | 0 | aucune |
| xref_identifiants | 138 470 | 0 | aucune |
| contrat_certifie | 93 427 | 5 173 | RQ-002, RQ-011, RQ-012, RQ-013, RQ-015 |
| sinistre_certifie | 82 790 | 5 259 | RQ-017 |

Orphelins Gold (contrat sans client, sinistre sans contrat) : **0, 0**.

La vue unique `gold.v_client_actif` publie **34 695** entités Gold actives, contre **37 643** identifiants source CD-001 : écart net **−2 948 (−7,83 %)**. Le diagnostic détaillé décompose l'écart en **562** identifiants sans mapping Gold, **972** identifiants mappés à une entité Gold non active, et **1 414** identifiants actifs source regroupés par consolidation (36 109 identifiants rattachés à 34 695 entités Gold actives). Les 972 identifiants concernés ont 1 187 contrats actifs Bronze : 127 sont rejetés en Silver (RQ-010) et 1 060 passent en Silver, mais aucun n'est certifié Gold. Les motifs de rejet G se cumulent sur certains contrats ; ne pas additionner leurs volumes pour compter des contrats distincts. RQ-018 échoue en Gold : ne pas déclarer le lot conforme.

Effet de la quarantaine : aucun orphelin Gold. Les contrats dont le client manque (RQ-012) et les sinistres hors garantie ou liés à un contrat non certifié (RQ-017) sont rejetés.

## 5. Traçabilité de trois données (US-28)

| Donnée | Valeur dans gold | Silver (identifiants de ligne) | Bronze (identifiants de ligne, lot) | Source (table, clé) |
|---|---|---|---|---|
| Société Meunier | `SOCIETE MEUNIER S.A.R.L.` (CLI-012703) | 111 243 (CIF), 8 595 (CRM) | 52 773, 108 723 — `L-2026-10-14` | `bronze.cif_clients`, K385175 ; `bronze.crm_client`, A-17929 |
| Code postal à zéro initial | `07200` (Bronze `7200`) | 67 292 | 168 336 — `L-2026-10-14` | `bronze.crm_client`, H-35779 |
| Adresse de sinistre | `85 RUE DU COMMERCE` | 4 | 100 005 — `L-2026-10-14` | `bronze.crm_sinistre`, SIN0000005 |

Export reproductible : `reports/us28_trace.csv`, produit par `pipelines/build_gold.py`.

## 6. Critères de fin

- [x] Pour chaque table, silver + rejets = bronze, sans suppression silencieuse.
- [x] Relancer Silver donne les mêmes comptages et rapports.
- [x] Les règles bloquantes de la porte S sont conformes sur Silver.
- [x] Gold ne contient aucun orphelin ; le client actif est publié par une seule vue.
- [x] Les trois traces remontent du Gold à la source avec identifiants de ligne et de lot.
- [ ] RQ-018 reste à résoudre ou faire valider avant un GO.

## 7. Difficultés, écarts avec l'attendu, reprise

Écarts principaux : rappel de 94 % sur les paires étiquetées, 5 paires positives non générées, et différence de 2 948 clients entre Gold et CD-001 après consolidation et porte G.

Point de reprise utilisé : oui, relance idempotente de `build_silver.py` sur `L-2026-10-14`, puis reconstruction Gold.

À reprendre : revue humaine des 99 paires proches du seuil, investigation des 5 positives non générées, et validation Data Owner du seuil, de la survie et de la définition active Gold.
