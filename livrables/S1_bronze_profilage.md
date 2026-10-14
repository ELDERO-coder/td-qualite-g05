# S1 · Stack Docker, profilage, construction de bronze

Groupe : Groupe 05  ·  Date : 14/10/2026  ·  Rédacteur : Oussama (Data Owner & Rédacteur)  ·  Étiquette : `seance-1`

Rappel : un constat = un chiffre mesuré (règle, couche) + la preuve qui le reproduit + ce que cela change. Voir `README.md`.

## 1. Inventaire des sources (US-01)

| Source | Table | Lignes | Clé primaire | Observation chiffrée |
|---|---|---|---|---|
| crm | client | 100 000 | `client_id` | Plus grande table CRM ; 100 000 enregistrements. |
| crm | contrat | 100 000 | `contrat_id` | Même volume que `crm.client` : 100 000 contrats. |
| crm | sinistre | 100 000 | `sinistre_id` | Même volume que `crm.client` et `crm.contrat` : 100 000 sinistres. |
| crm | type_contrat | 12 | `code_type` | 12 types de contrat référencés. |
| cif | clients | 40 000 | `column0` | 40 000 identités dans le CIF. |
| cif | compte | 45 000 | `column0` | 45 000 comptes, soit 1,125 compte par identité CIF en moyenne. |
| cif | pays | 250 | `code_pays` | 250 lignes dans le référentiel pays. |

Preuve : comptages exécutés sur les tables sources MariaDB ; clés primaires vérifiées dans `initdb/01_sources.sql`.
```sql
SELECT 'crm.client', COUNT(*) FROM crm.client
UNION ALL SELECT 'crm.contrat', COUNT(*) FROM crm.contrat
UNION ALL SELECT 'crm.sinistre', COUNT(*) FROM crm.sinistre
UNION ALL SELECT 'crm.type_contrat', COUNT(*) FROM crm.type_contrat
UNION ALL SELECT 'cif.clients', COUNT(*) FROM cif.clients
UNION ALL SELECT 'cif.compte', COUNT(*) FROM cif.compte
UNION ALL SELECT 'cif.pays', COUNT(*) FROM cif.pays;