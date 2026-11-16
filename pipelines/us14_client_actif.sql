-- US-14 : une seule definition ciblee, appliquee identiquement aux trois directions.
-- Lot bronze et date de reference explicites pour rendre la mesure reproductible.
WITH parametres AS (
    SELECT :batch_id AS batch_id,
           DATE(:date_reference) AS date_reference,
           DATE(:debut_fenetre_cotisation) AS debut_fenetre_cotisation
),
clients_actifs AS (
    SELECT DISTINCT k.souscripteur_id AS client_id
    FROM bronze.crm_contrat k
    JOIN bronze.crm_client c
      ON c.client_id = k.souscripteur_id
     AND c._batch_id = k._batch_id
    CROSS JOIN parametres p
    WHERE k._batch_id = p.batch_id
      AND k.souscripteur_id IS NOT NULL
      AND STR_TO_DATE(NULLIF(k.date_debut, ''), '%Y-%m-%d') <= p.date_reference
      AND STR_TO_DATE(NULLIF(k.date_fin, ''), '%Y-%m-%d') >= p.date_reference
      AND STR_TO_DATE(NULLIF(k.date_derniere_cotisation, ''), '%Y-%m-%d')
          >= p.debut_fenetre_cotisation
)
SELECT direction.nom AS direction, COUNT(a.client_id) AS clients_actifs
FROM (
    SELECT 'Commerciale' AS nom
    UNION ALL SELECT 'Sinistres'
    UNION ALL SELECT 'Risques'
) direction
LEFT JOIN clients_actifs a ON TRUE
GROUP BY direction.nom
ORDER BY direction.nom;
