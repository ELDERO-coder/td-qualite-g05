# S5 · Certifier, publier vers le CRM, gouverner

Groupe : Groupe 05 · Mesures : 21/10/2026 · Oussama : Data Owner et Rédacteur. Aucun certificat GO n'est signé; le certificat réel du lot est NO_GO. État du lot : `L-2026-10-14`.

## 1. Historique des mesures (US-29, US-30)

Export : `docker exec dq_jupyter python pipelines/export_history_s5.py --batch-id L-2026-10-14 --output-dir reports`.

| Règle | Dimension | Taux Bronze | Taux Silver | Taux Gold | Évolution | Explication |
|---|---|---:|---:|---:|---|---|
| RQ-001 | Cohérence | 99,200 % | non mesuré | non mesuré | indisponible | Contrat Silver/Gold non implémenté. |
| RQ-002 | Validité métier | 99,676 % | non mesuré | non mesuré | indisponible | Test sur bronze; âge au début du contrat. |
| RQ-003 | Complétude | 87,998 % | non mesuré | non mesuré | indisponible | Mesure du téléphone des souscripteurs. |
| RQ-005 | Validité format | 98,474 % | non mesuré | non mesuré | indisponible | CP français; Silver n'a pas encore d'expectation RQ-005. |
| RQ-009 | Validité domaine | 99,800 % | non mesuré | non mesuré | indisponible | 200 variantes source signalées à surveiller. |
| RQ-010 | Validité domaine | 99,400 % | non mesuré | non mesuré | indisponible | Contrats non normalisés en Silver. |
| RQ-021/RQ-022 | Complétude / traçabilité | 100 % | sans objet | sans objet | stable sur Bronze | Réconciliation et métadonnées de Bronze. |
| RQ-011/RQ-012/RQ-013/RQ-015/RQ-016/RQ-017/RQ-018 | Intégrité / cohérence | sans objet | sans objet | CRM : voir S3 | non comparable | Mesures sur la source CRM; pas sur Gold. |

Courbe et CSV : `reports/s5_history.png` et `reports/s5_history.csv` (exports locaux). La courbe ne montre que les couches disposant de mesures; elle ne compare pas Bronze/Silver/Gold. Aucune baisse inter-couche ne peut être interprétée tant que Silver/Gold n'est pas couvert.

## 2. Certificat de qualité (US-31)

| Élément | Valeur mesurée |
|---|---|
| Numéro | `CERT-L20261014-132851` |
| Lot | `L-2026-10-14` |
| Décision | `NO_GO` |
| Règles bloquantes du catalogue | 19 |
| Mesurées dans leur couche attendue | 2 (RQ-021, RQ-022) |
| Conformes dans leur couche attendue | 2; les 17 autres ne sont pas couvertes et certaines ont des échecs mesurés sur Bronze/CRM |
| Avertissements connus | RQ-003 : 5 989 échecs; RQ-005 : 1 456 échecs dans le périmètre FR; Soda RQ-007 : 3 050 valeurs pays non référencées; RQ-014 BAN : 12,1 % d'adresses non reconnues |
| SHA-256 du Gold (client_unique + xref) | `85b9884af4b72ecb46a8784e86402625befbc5e6eb41cc1091fbd6e9ae05e01e` |
| Signataire | Aucun; le Data Owner doit signer, aucun nom n'est attribué par ce script. |

Preuve : `pipelines/certify_s5.py --batch-id L-2026-10-14`; le certificat réel est enregistré dans `dq.certificat_qualite`. Le script renvoie un code 2 pour NO_GO.

Épreuve NO_GO : les résultats réels du lot nominal donnent NO_GO car 17 règles bloquantes ne sont pas mesurées dans leur couche cible et le Data Owner n'a pas signé. Aucune altération de donnée n'était nécessaire pour ce NO_GO. La dégradation artificielle de la porte B est documentée en S1, puis restaurée.

Règles bloquantes non mesurées dans leur couche cible : RQ-001, RQ-002, RQ-007, RQ-009, RQ-010, RQ-011, RQ-012, RQ-013, RQ-014, RQ-015, RQ-017, RQ-018, RQ-019, RQ-020, RQ-023, RQ-024 et RQ-025. RQ-021/RQ-022 sont les deux seules mesurées et conformes en Bronze.

## 3. Publication vers le CRM (US-32)

Garde de publication : `pipelines/publish_s5.py`. Aucun chargement n'est effectué : RQ-025 et le chargeur transactionnel ne sont pas implémentés; `crm_cible` ne contient pas les tables cibles `client`, `contrat`, `sinistre`.

| Scénario | Message obtenu | Chargement ? | Preuve |
|---|---|---|---|
| Sans certificat | Refus « Aucun certificat pour le lot » prévu par le script; scénario non exécuté ici | Non | `pipelines/publish_s5.py` |
| Certificat NO_GO | « Le certificat n'est pas GO » | Non | Exécuté avec `CERT-L20261014-132851`, code retour 2 |
| Gold modifié après certificat | Comparaison empreinte définie; scénario d'altération non exécuté | Non | `pipelines/publish_s5.py` |
| Certificat GO et Gold intact | Non testé, aucun GO valide/signé | Non | Impossible tant que les règles bloquantes et le chargeur ne sont pas complets |

RQ-025 : aucune réconciliation gold→CRM cible, aucun comptage/somme de contrôle de publication; tables cibles absentes.

Le chargement tout-ou-rien n'est pas vérifié, car le chargeur transactionnel n'est pas encore implémenté. Le script garde-fou refuse explicitement toute publication tant que ce point est incomplet.

## 3 bis. Gouvernance (US-34)

Fiche : `catalogue/gold_client_unique.md`.

| Élément | Valeur / état |
|---|---|
| Propriétaire Data Owner | Rôle attribué à Oussama en S1; maintien en S5 à confirmer par le groupe. |
| Data Steward | À désigner/valider par le groupe; ne pas inventer de nom. |
| Définition de client actif | Contrat en cours et cotisation à jour sur trois mois à la référence du lot, souscripteur ou assuré; sentinelle `0` exclue. Validation Data Owner requise. |
| Règles liées | RQ-002, RQ-007, RQ-009, RQ-019, RQ-020, RQ-023 et RQ-024; couverture complète à confirmer. |

Lineage actuel : `crm.client` et `cif.clients` → Bronze CRM/CIF → `silver.client` → `gold.client_unique`; `gold.xref_identifiants` fournit les identifiants source, Bronze et Silver. Contrats et sinistres Gold non implémentés.

## 4. Décisions de la séance

Aucune décision métier S5 n'est actée par ce travail. Les seuils flous, les règles de survie, le statut par défaut CIF et le GO restent à valider et à consigner par le Data Owner dans `livrables/JOURNAL_DECISIONS.md`.

## 5. Critères de fin

- [ ] Un certificat GO signé est obtenu après couverture et succès de toutes les règles bloquantes; seul le NO_GO est mesuré actuellement.
- [x] Le garde-fou refuse un certificat NO_GO avant toute écriture cible.
- [ ] Le garde-fou vérifie l'absence de certificat et le changement d'empreinte; ces branches sont codées, mais pas encore testées par mutation contrôlée.
- [ ] RQ-025, le chargeur transactionnel et les tables cible sont absents; aucune égalité de comptage/hash CRM n'est prouvée.
- [ ] Les décisions de seuil/sévérité doivent être signées/attribuées au rôle avant toute certification.

## 6. Difficultés et reprise

- Difficultés : couverture incomplète des règles dans les couches attendues; le schéma cible CRM est vide.
- Point de reprise : aucun.
- À améliorer : achever les contrôles et transformations contrat/sinistre, faire valider les décisions par le Data Owner, puis exécuter le test NO_GO/GO et la réconciliation RQ-025 avant toute publication.
