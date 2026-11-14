# Script oral — Soutenance AssurConnect

**Support associé :** `Soutenance_Groupe05_AssurConnect.pptx`
**Durée :** 12 minutes d’exposé, dont 2 minutes de démonstration, puis 8 minutes de questions.
**Rôles S5 confirmés par le groupe :** Oussama — Data Owner; Paul — Ingénieur qualité; Romeo (Dewano dans le dépôt) — Data Steward. Le partage détaillé des contributions et des stories reste à faire.

## Diapositive 1 — Décision de bascule (environ 1 minute)

Bonjour. Notre recommandation, annoncée dès le début, est **NO-GO** pour le lot `L-2026-10-14` : nous ne recommandons pas sa publication vers le CRM cible. Le certificat réel `CERT-L20261014-132851` ne mesure que deux des dix-neuf règles bloquantes dans leur couche attendue. Ces deux règles sont conformes, mais les dix-sept autres ne sont pas couvertes dans leur couche cible. Cette absence de mesure ne peut pas être interprétée comme une conformité. Le NO-GO ne signifie pas que toutes les données d’origine sont mauvaises : il signifie que nous n’avons pas les preuves nécessaires pour autoriser la bascule. Nous allons montrer les chiffres, les limites du périmètre et les conditions qui permettraient de réexaminer cette décision.

## Diapositive 2 — Pourquoi le NO-GO ? (environ 1 minute 30)

La décision repose sur trois faits. Premièrement, dix-sept règles bloquantes ne sont pas mesurées dans la couche où elles doivent s’appliquer. Deuxièmement, le pipeline Silver/Gold couvre les clients, mais pas les contrats et les sinistres : le périmètre métier est donc incomplet. Troisièmement, la réconciliation de publication RQ-025, les tables CRM cibles et le chargeur transactionnel ne sont pas implémentés. Nous ne pouvons donc pas prouver que ce qui serait écrit dans le CRM correspondrait exactement à ce qui a été certifié. Enfin, le certificat existant est NO-GO et son champ signataire est absent. Pour ces raisons, aucune publication ne doit être réalisée. La décision du dossier est déclarée signée par Oussama; sa date et sa preuve doivent être jointes. Cette décision est une mesure de protection de la cible, pas une affirmation que les données sources ont toutes été corrigées ou qu’elles sont toutes erronées.

## Diapositive 3 — Les mesures disponibles (environ 2 minutes)

Sur Bronze, le rapprochement porte sur 385 262 lignes réparties sur sept tables, sans écart pour les contrôles de réconciliation RQ-021 et RQ-022. Cela confirme le chargement et les métadonnées mesurés, mais pas la qualité de toutes les règles métier. Pour RQ-001, la cohérence des dates de contrat est de 99,200 %, avec 800 échecs sur 100 000 contrats. Pour RQ-003, la complétude du téléphone est de 87,998 %, soit 5 989 échecs sur 49 898 souscripteurs. Pour RQ-005, la validité des codes postaux français est de 98,474 %, avec 1 456 échecs sur 95 437 lignes testées. Ces trois résultats sont des mesures Bronze; ils ne sont pas des taux Silver ou Gold. En Silver, 140 000 clients ont été évalués : 98 490 sont marqués `VALIDE` et 41 510 `A_SURVEILLER`. Ces derniers sont conservés, et non supprimés. Les contrôles Silver complets restent à exécuter.

## Diapositive 4 — Couches et périmètre (environ 1 minute 30)

La chaîne comporte quatre étapes. Bronze est alimenté et réconcilié sur les contrôles indiqués. Silver contient le traitement des clients, mais pas celui des contrats et des sinistres. Gold contient 126 033 clients uniques et la table de références des identifiants; les tables Gold des contrats et des sinistres ne sont pas créées. Enfin, la cible CRM n’a reçu aucune ligne. RQ-025 et le chargeur nécessaires à une publication transactionnelle sont absents. Notre implémentation S4 est réalisée en pandas et SQLAlchemy; il ne faut donc pas la présenter comme une transformation PySpark. Le résultat est utile pour démontrer une partie du traitement client, mais il ne constitue pas un jeu Gold complet et prêt à publier.

## Diapositive 5 — Dédoublonnage et décisions métier (environ 1 minute 30)

Le pipeline a rapproché 13 967 paires CRM–CIF à l’aide de clés exactes non ambiguës. Les 140 000 références d’entrée conduisent à 126 033 clients Gold. Le rapprochement flou a été évalué séparément sur 200 paires étiquetées, avec un seuil de 0,85 : la précision mesurée est de 99 % et le rappel de 98 %, avec un faux positif dans l’échantillon. Ce résultat n’est pas une garantie sur toute la population. Aucune fusion floue n’est appliquée en production. La règle provisoire de survie donne la priorité à CRM, mais elle n’a pas été approuvée par le Data Owner. La définition du client actif, les statuts CIF, la sentinelle et les seuils doivent également être arbitrés avant une diffusion.

## Diapositive 6 — Certificat réel (environ 1 minute 30)

Voici la ligne réelle du certificat, relue dans MariaDB et jointe au dossier. Elle identifie le lot et l’émission du 21 octobre 2026. La décision enregistrée est `NO_GO`. Les champs indiquent deux règles bloquantes mesurées et deux conformes, sur dix-neuf règles bloquantes au catalogue; notre recalcul de couverture retrouve RQ-021 et RQ-022 comme les deux contrôles couverts dans leur couche attendue. Le champ signataire est `NULL`. L’empreinte SHA-256 permet d’identifier le Gold client qui a été certifié, mais elle ne prouve pas à elle seule que les règles manquantes ont été exécutées ni que la publication CRM a eu lieu. Le CSV joint reproduit l’enregistrement de la base; le notebook de démonstration relit cette même ligne et vérifie la couverture sans écrire dans la base.

## Diapositive 7 — Conditions avant une nouvelle demande de GO (environ 1 minute 30)

Avant de demander un nouveau GO, il faut compléter les transformations et les contrôles des contrats et des sinistres, puis exécuter les règles bloquantes dans leurs couches attendues. Il faut ensuite faire valider par les rôles compétents la définition du client actif, le traitement de la sentinelle, les statuts CIF, les règles de survie et les seuils; ces arbitrages doivent être consignés. Le troisième chantier est la publication : implémenter RQ-025 et le chargeur transactionnel, puis tester le refus d’un NO-GO, le contrôle d’empreinte, l’atomicité et la réconciliation avec le CRM cible. Pour le NO-GO actuel, Oussama confirme avoir signé la décision; la date et la preuve doivent être ajoutées au dossier. Pour une future décision de GO, il faudra réexécuter la certification et obtenir la signature autorisée. Cette présentation n’inclut pas de preuve de signature.

## Diapositive 8 — Démonstration et conclusion (2 minutes de démo, environ 1 minute de conclusion)

Pour la démonstration, nous exécutons le notebook associé en lecture seule. Il affiche l’identifiant du certificat, la décision enregistrée, le nombre de règles bloquantes mesurées dans leur couche attendue et le tableau de couverture règle par règle. Nous n’insérons pas de certificat, ne modifions pas les données et ne fabriquons pas de sortie. Le résultat attendu est le NO-GO réel, deux règles conformes sur dix-neuf et l’absence de signataire.

Pour conclure, la recommandation reste NO-GO pour ce lot. Les prochaines étapes sont la couverture des règles manquantes, la validation des décisions métier et l’implémentation d’une publication réconciliée. Les rôles S5 sont confirmés; les contributions et les stories de chacun restent à partager et à inscrire dans le livrable d’équipe. Nous sommes prêts à répondre à vos questions.

## Réponses factuelles possibles aux questions

- **Pourquoi ne pas décider GO si les deux règles mesurées sont conformes ?** Parce que dix-sept règles bloquantes sur dix-neuf ne sont pas mesurées dans leur couche attendue.
- **Le NO-GO vient-il d’une altération artificielle du lot ?** Non. Le certificat nominal consulté donne déjà NO-GO; le dossier précise que le test artificiel de la porte B a été restauré.
- **Des données ont-elles été publiées vers le CRM ?** Non. Le certificat est NO-GO, les tables cibles et le chargeur sont absents, et aucune écriture n’a été effectuée.
- **Les rapprochements flous sont-ils utilisés en production ?** Non. Le seuil a été évalué sur un échantillon de 200 paires; aucune fusion floue n’est appliquée.
- **Qui a signé la décision du dossier ?** Oussama, Data Owner, selon la confirmation du groupe; la date et la preuve de signature doivent accompagner la copie remise.
- **Qui a signé le certificat en base ?** Personne : le champ `signataire` de la ligne réelle est `NULL`. La signature du dossier ne modifie pas le certificat déjà émis.
