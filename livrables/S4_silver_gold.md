# S4 · PySpark : construire silver puis gold

Groupe : [À COMPLÉTER]  ·  Date : [À COMPLÉTER]  ·  Rédacteur : [À COMPLÉTER]  ·  Étiquette : `seance-4`

Un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Silver et quarantaine (US-21, US-22)

Scripts ou notebooks (chemins) : [pipelines/S4_silver_gold.py]

Traitements appliqués (pays, code postal, identité, autres), avec le nombre de lignes touchées par chacun :

Le pipeline transforme les données BRONZE vers SILVER à l'aide de PySpark, puis charge les résultats dans MariaDB.

| Traitement | Table | Lignes modifiées | Garde-fou (ce que le traitement ne doit pas faire) |
|---|---|---|---|
| Normalisation des identités | silver.client | 98 156 | Ne pas inventer d'identité manquante |
| Normalisation des adresses et villes | silver.client, silver.sinistre | 99 350 | Ne pas inventer d'adresse ou de ville |
| Normalisation des pays | silver.client | 2 598 | Ne pas attribuer arbitrairement un pays |
| Normalisation des téléphones et courriels | silver.client | 25 111 | Ne pas inventer de coordonnées |
| Contrôle des règles bloquantes | Clients CRM et contrats | 2 050 | Ne pas intégrer les lignes invalides en silver |

Invariant silver + rejets = bronze :

| Table | Lignes bronze | Lignes silver | Lignes rejetées | Écart |
|---|---|---|---|---|
| client (crm) | 100 000 | 99 350 | 650 | 0 |
| client (cif) | 40 000 | 40 000 | 0 | 0 |
| contrat | 100 000 | 98 600 | 1 400 | 0 |
| sinistre | 100 000 | 100 000 | 0 | 0 |


Contrôle RQ-024 — Conservation des lignes

Le contrôle RQ-024 a été exécuté sur le batch L-2026-10-01, en comparant les volumes BRONZE, SILVER et les rejets distincts enregistrés dans dq.rejets (porte S).

Résultat : RQ-024 : OK.

Les quatre entités présentent un écart nul. L'invariant BRONZE = SILVER + rejets est donc respecté pour chaque entité et chaque source.

Aucune perte silencieuse de lignes n'a été constatée.

Rejets par règle (`dq.rejets`) :

| Règle | Table | Lignes rejetées | Raison métier |
|---|---|---|---|
| RQ-007 | client (crm) | 450 | Pays absent du référentiel après normalisation |
| RQ-009 | client (crm) | 200 | Type de personnes hors domaine |
| RQ-001 | contrat | 800 | Date de fin inférieure ou égale à la date de début |
| RQ-010 | contrat | 600 | Durée de garantie hors des valeurs autorisées (12, 24, 36, 60 mois) |

Idempotence : le traitement relancé deux fois donne le même résultat (preuve) : 

Le pipeline pipelines/S4_silver_gold.py a été exécuté deux fois successivement sur le même batch.

Les deux exécutions ont produit le même bilan :
Clients CRM : 99 350 lignes SILVER.
Clients CIF : 40 000 lignes SILVER.
Contrats : 98 600 lignes SILVER.
Sinistres : 100 000 lignes SILVER.
Rejets : 2 050 lignes.

## 2. Porte S : bronze contre silver (US-23)

| Règle | Sévérité | Taux bronze | Taux silver | Écart | Explication de l'écart |
|---|---|---|---|---|---|
| RQ-001 | BLOQUANTE | 99,2 % | 100 % | +0,800 pt | Les contrats avec une date de fin invalide ont été rejetés. |
| RQ-003 | AVERTISSEMENT | 93,999 % | 88,006 % | -5,993 pts | Les populations contrôlées diffèrent entre BRONZE et SILVER. Les souscripteurs sans téléphone restent présents. |
| RQ-005 | AVERTISSEMENT | 98,474 % | 100 % | +1,526 pt | Normalisation des données et conformité des codes postaux contrôlés. |
| RQ-007 | BLOQUANTE | 96,95 % | 100 % | +3,05 pts | Normalisation des pays et rejet des valeurs absentes du référentiel. |
| RQ-009 | BLOQUANTE | 99,8 % | 100 % | +0,2 pt | Les clients avec un type de personne invalide ont été rejetés. |
| RQ-010 | BLOQUANTE | 99,4 % | 100 % | +0,6 pt | Les contrats avec une durée de garantie invalide ont été rejetés. |

Toute règle dont le taux baisse de bronze à silver doit être expliquée : 

Seule RQ-003 présente une baisse parmi les règles comparées, passant de 93,999 % à 88,006 %. Les populations contrôlées et les dénominateurs diffèrent entre BRONZE et SILVER. Les 5 960 souscripteurs CRM sans téléphone restent présents dans SILVER, car cette anomalie ne fait pas partie des motifs de rejet du pare-feu qualité. Cette baisse ne prouve donc pas une dégradation des données lors de la transformation.


Règles bloquantes de la porte S toutes conformes sur silver ? Sinon, lesquelles et pourquoi : 

Non. Les règles RQ-001, RQ-007, RQ-009, RQ-010, RQ-020, RQ-023 et RQ-024 sont conformes aux contrôles réalisés.

En revanche, RQ-014 présente une non-conformité sur le rapprochement avec le référentiel BAN : 46 716 adresses sur 100 000 ne sont pas reconnues, soit un taux d'erreur de 46,716 %, supérieur au seuil d'échec de 10 %. Les contrôles de format et de complétude réussissent.

La porte S ne peut donc pas être considérée comme entièrement validée.

## 3. Dédoublonnage et golden record (US-24, US-25)

| Paramètre | Valeur retenue | Justification |
|---|---|---|
| Normalisation appliquée avant comparaison | … | … |
| Clé(s) de blocage | … | … |
| Mesure de similarité | … | … |
| Seuil de fusion automatique | … | … |
| Seuil de la zone de revue | … | … |

| Mesure | Valeur |
|---|---|
| Groupes de doublons trouvés | … |
| Paires fusionnées automatiquement | … |
| Paires en zone de revue | … |
| Précision sur les 200 paires étiquetées | … |
| Rappel sur les 200 paires étiquetées | … |
| Identités distinctes obtenues | … |

Golden record de la Société Meunier :

| Identifiant source | Système | CLI attribué |
|---|---|---|
| … | … | … |
| … | … | … |
| … | … | … |
| … | … | … |

Règle de survie par attribut :

| Attribut | Source retenue | Règle (priorité, plus récent, non nul) | Cas où la règle se trompe |
|---|---|---|---|
| Nom | … | … | … |
| Adresse | … | … | … |
| Téléphone | … | … | … |
| Courriel | … | … | … |

Reportez les seuils et la règle de survie dans `JOURNAL_DECISIONS.md`, avec le rôle qui les a décidés.

## 4. Gold et client actif (US-27)

| Table gold | Lignes | Lignes écartées (porte G) | Règles responsables |
|---|---|---|---|
| client_unique | … | … | … |
| xref_identifiants | … | … | … |
| contrat_certifie | … | … | … |
| sinistre_certifie | … | … | … |

Orphelins dans gold (contrat sans client, sinistre sans contrat) : [À COMPLÉTER]

Client actif publié par la vue `v_client_actif` : [À COMPLÉTER]. Écart avec la définition de la fiche CD-001 : [À COMPLÉTER]

Effet de la quarantaine sur l'intégrité en aval (un client écarté laisse-t-il des contrats orphelins ?) : [À COMPLÉTER]

## 5. Traçabilité de trois données (US-28)

| Donnée | Valeur dans gold | Silver (identifiants de ligne) | Bronze (identifiants de ligne, lot) | Source (table, clé) |
|---|---|---|---|---|
| Société Meunier | … | … | … | … |
| Un code postal à zéro initial | … | … | … | … |
| Une adresse de sinistre | … | … | … | … |

Requête de traçabilité (chemin) : [À COMPLÉTER]

## 6. Critères de fin

- [ ] Pour chaque table, silver + rejets = bronze, sans suppression silencieuse.
- [ ] Relancer le traitement deux fois donne le même résultat.
- [ ] Les règles bloquantes de la porte S sont conformes sur silver.
- [ ] Le gold ne contient aucun orphelin ; le client actif est publié par une seule vue.
- [ ] Les trois traces remontent du gold à la source avec identifiants de ligne et de lot.

## 7. Difficultés, écarts avec l'attendu, reprise

Difficultés rencontrées et temps perdu : [À COMPLÉTER]

Point de reprise utilisé (oui / non, lequel, à quel moment) : [À COMPLÉTER]

Ce que nous ferions autrement : [À COMPLÉTER]
