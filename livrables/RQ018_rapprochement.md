# Rapprochement RQ-018 : CD-001 et Gold

## Conclusion Data Steward

Le compte de **34 695** dans Gold est inférieur de **2 948** au compte CD-001 Bronze (**37 643**), mais cet écart compare deux grains différents : les identifiants source CRM et les identités consolidees du Golden Record. Il ne faut donc pas qualifier les 2 948 de « clients manquants » sans distinguer les causes.

| Étape du rapprochement | Nombre | Lecture |
|---|---:|---|
| Clients source actifs selon CD-001 sur Bronze | 37 643 | Identifiants CRM distincts |
| Sans identifiant dans Gold | 562 | 531 rejets Silver RQ-007 et 31 rejets Silver RQ-009 |
| Identifiant Gold présent, mais sans entité Gold active | 972 | 1 187 contrats Bronze CD-001 ; 127 rejetés en Silver par RQ-010 et 1 060 présents en Silver, mais aucun certifié Gold |
| Identifiants source rattachés à une entité Gold active | 36 109 | Comptage des identifiants CRM source |
| Réduction nette par consolidation d'identités | 1 414 | 36 109 identifiants source regroupés en 34 695 entités Gold actives |
| Entités Gold actives hors du périmètre CD-001 | 0 | Aucune entité Gold active supplémentaire détectée |
| Écart net des deux comptes | **2 948** | 562 + 972 + 1 414 |

Parmi les 1 060 contrats présents en Silver mais non certifiés dans Gold, les rejets relevés sont RQ-002 (206 contrats), RQ-011 (38), RQ-013 (261) et RQ-015 (566). Ces causes peuvent se cumuler sur un même contrat ; leurs nombres ne s'additionnent donc pas pour obtenir le total des contrats.

## Décision et suite

L'analyse explique numériquement l'écart, mais ne justifie pas encore un GO. Les rejets métier restent à traiter ou à arbitrer par leurs Data Owners. Le Data Owner doit aussi confirmer si CD-001 doit être rapproché au grain des identifiants CRM ou au grain des identités consolidées. Le Data Steward ne modifie pas RQ-018 ni les règles de certification sans cette décision.

**Décision actuelle : NO-GO maintenu ; aucune publication CRM.** Relancer la certification seulement après traitement des rejets et validation du grain de rapprochement par le Data Owner.

## Reproduction

- Trois définitions et comparaison Bronze : `pipelines/us09_client_actif.sql`.
- Décomposition Bronze → Silver → Gold : `pipelines/analyser_rq018.sql`.
- Lot : `L-2026-10-14` ; référence CD-001 : 01/10/2026 ; début de fenêtre de cotisation : 01/07/2026.
- La requête de diagnostic ne modifie aucune table persistante ; elle crée uniquement des tables temporaires.

```powershell
Get-Content .\pipelines\analyser_rq018.sql | docker exec -i dq_mariadb mariadb -uroot -proot --table
```
