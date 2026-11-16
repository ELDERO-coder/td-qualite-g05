# Fiche de catalogue — `gold.client_unique`

| Champ | Valeur |
|---|---|
| Description | Référentiel consolidé des identités CRM et CIF ; une ligne par CLI construit par rapprochement déterministe. |
| Data Owner | Direction métier à désigner par le groupe / l'enseignant ; aucune approbation nominative enregistrée. |
| Data Steward | Groupe 05 — rôle exercé par le rédacteur du livrable. |
| Définition métier de « client actif » | Au moins un contrat en cours à la date de référence (01/10/2026) et une cotisation depuis les trois mois précédents (à compter du 01/07/2026), conformément à CD-001. |
| Publication de l'indicateur | Uniquement par `gold.v_client_actif`, à partir des contrats certifiés. La mesure actuelle diverge de CD-001 ; publication CRM suspendue tant que RQ-018 échoue. |
| Règles rattachées | RQ-007, RQ-009 (qualité d'origine Silver) ; RQ-019 (unicité du CLI) ; RQ-023 (lineage) ; RQ-018 pour l'indicateur actif associé. |
| Sensibilité | Données d'identification et coordonnées personnelles ; accès selon les habilitations du CRM. |
| Lot de preuve | `L-2026-10-14`. |
| Implémentation | `pipelines/build_gold.py`. |

## Règle de survie

Retenir par attribut la valeur valide la plus complète ; préférer CRM en cas d'égalité. Cette règle, le score de rapprochement et les seuils restent des propositions du Data Steward, non approuvées par un Data Owner dans les preuves disponibles.

## Lineage

```text
crm.client ──> bronze.crm_client ──> silver.client ──┐
                                                     ├─> gold.xref_identifiants ──> gold.client_unique
cif.clients ─> bronze.cif_clients ─> silver.client ─┘
```

`gold.xref_identifiants` conserve, pour chaque source, les identifiants et `bronze_row_id` / `silver_row_id`. Les mesures de lineage et les traces d'exemple sont exportées dans `reports/us28_trace.csv`.
