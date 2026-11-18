# Fiche de catalogue : `gold.client_unique`

Statut : fiche de travail, données non certifiées et non publiables.

| Attribut | Valeur actuelle | Validation requise |
|---|---|---|
| Data Owner | Rôle attribué à Oussama en S1 | Confirmation de maintien du rôle par le groupe / enseignant pour S5 |
| Data Steward | À désigner par le groupe | Nom et validation métier |
| Ingénieur qualité | À renseigner pour S4/S5 | Contribution vérifiée dans l'historique Git |
| Rédacteur | Oussama (S1) | Rôle S5 à confirmer |
| Définition de client actif | Contrat en cours à la date de référence et cotisation à jour dans les trois derniers mois; souscripteur ou assuré; sentinelle `assure_id='0'` exclue | Approbation Data Owner requise avant publication |
| Sources | `crm.client`, `cif.clients`, référentiels pays/postal | Rapprochement des identités et règle de survie à approuver |
| Règles liées | RQ-002, RQ-007, RQ-009, RQ-019, RQ-020, RQ-023, RQ-024 | Couverture réelle par couche à vérifier dans `dq.dq_history` |
| Statut qualité | `gold.client_unique` construit pour le lot `L-2026-10-14`; non certifié | Ne pas publier avant un certificat GO signé |

## Lineage

`crm.client` / `cif.clients` → `bronze.crm_client` / `bronze.cif_clients` → `silver.client` → `gold.client_unique`.

`gold.xref_identifiants` conserve `source_systeme`, `source_id`, `bronze_row_id` et `silver_row_id`; les identifiants Bronze sont spécifiques à leur table, donc le système source fait partie du lignage.

### Cas de revue : Société Meunier SARL, Lille

| Source | ID source | Bronze | Silver | Gold actuel |
|---|---|---:|---:|---|
| CRM | `A-17929` | `110723` | `708723` | `CLI-047477` |
| CIF | `K385175` | `54773` | `812773` | `CLI-022264` |

Les raisons sociales, adresses et coordonnées concordent selon le profil mesuré et documenté dans [`../livrables/S4_silver_gold.md`](../livrables/S4_silver_gold.md). Le rapprochement exact de production ne fusionne pas ces deux lignes; elles restent deux clients Gold. Ne pas les présenter comme un golden record unique avant validation métier de l'entité légale et de la règle de survie.

## Limites connues

- La fusion automatique est limitée aux clés exactes non ambiguës; le score fuzzy évalué sur 200 paires n'est pas appliqué à la production.
- Le mapping des clients CIF sans type de personne est provisoire; le statut `INACTIF` attribué par le pipeline n'est pas validé.
- `contrat_certifie`, `sinistre_certifie`, la vue `v_client_actif` et la publication CRM ne sont pas encore implémentés.
- Empreinte SHA-256 du Gold à calculer par `pipelines/certify_s5.py` lors de l'émission du certificat.
