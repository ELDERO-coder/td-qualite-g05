-- US-09: compare three business definitions with CD-001 on Bronze.
-- Lot and date reference are explicit so the comparison is reproducible.
USE bronze;
SET @batch_id = 'L-2026-10-14';
SET @date_ref = DATE('2026-10-01');

DROP TEMPORARY TABLE IF EXISTS us09_cd001;
DROP TEMPORARY TABLE IF EXISTS us09_commerciale;
DROP TEMPORARY TABLE IF EXISTS us09_sinistres;
DROP TEMPORARY TABLE IF EXISTS us09_risques;

-- Target CD-001: active contract and a contribution in the preceding 3 months.
CREATE TEMPORARY TABLE us09_cd001 ENGINE=InnoDB
AS
SELECT DISTINCT c.souscripteur_id AS client_id
FROM bronze.crm_contrat c
JOIN bronze.crm_client k
  ON k.client_id = c.souscripteur_id
 AND k._batch_id = @batch_id
WHERE c._batch_id = @batch_id
  AND c.souscripteur_id IS NOT NULL
  AND STR_TO_DATE(NULLIF(c.date_debut, ''), '%Y-%m-%d') <= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_fin, ''), '%Y-%m-%d') >= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_derniere_cotisation, ''), '%Y-%m-%d')
      >= DATE_SUB(@date_ref, INTERVAL 3 MONTH);
ALTER TABLE us09_cd001 ADD PRIMARY KEY (client_id);

-- Commerciale: known client with at least one contract as subscriber.
CREATE TEMPORARY TABLE us09_commerciale ENGINE=InnoDB
AS
SELECT DISTINCT c.souscripteur_id AS client_id
FROM bronze.crm_contrat c
JOIN bronze.crm_client k
  ON k.client_id = c.souscripteur_id
 AND k._batch_id = @batch_id
WHERE c._batch_id = @batch_id
  AND c.souscripteur_id IS NOT NULL;
ALTER TABLE us09_commerciale ADD PRIMARY KEY (client_id);

-- Sinistres: known client with a contract in force and at least one linked claim.
CREATE TEMPORARY TABLE us09_sinistres ENGINE=InnoDB
AS
SELECT DISTINCT c.souscripteur_id AS client_id
FROM bronze.crm_contrat c
JOIN bronze.crm_sinistre s
  ON s.contrat_id = c.contrat_id
 AND s._batch_id = @batch_id
JOIN bronze.crm_client k
  ON k.client_id = c.souscripteur_id
 AND k._batch_id = @batch_id
WHERE c._batch_id = @batch_id
  AND c.souscripteur_id IS NOT NULL
  AND STR_TO_DATE(NULLIF(c.date_debut, ''), '%Y-%m-%d') <= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_fin, ''), '%Y-%m-%d') >= @date_ref;
ALTER TABLE us09_sinistres ADD PRIMARY KEY (client_id);

-- Risques: known client with a contract in force, regardless of payment recency.
CREATE TEMPORARY TABLE us09_risques ENGINE=InnoDB
AS
SELECT DISTINCT c.souscripteur_id AS client_id
FROM bronze.crm_contrat c
JOIN bronze.crm_client k
  ON k.client_id = c.souscripteur_id
 AND k._batch_id = @batch_id
WHERE c._batch_id = @batch_id
  AND c.souscripteur_id IS NOT NULL
  AND STR_TO_DATE(NULLIF(c.date_debut, ''), '%Y-%m-%d') <= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_fin, ''), '%Y-%m-%d') >= @date_ref;
ALTER TABLE us09_risques ADD PRIMARY KEY (client_id);

-- Per-direction totals and exact set differences from CD-001.
SELECT
    'Commerciale' AS direction,
    (SELECT COUNT(*) FROM us09_commerciale) AS clients_direction,
    (SELECT COUNT(*) FROM us09_cd001) AS clients_cd001,
    (SELECT COUNT(*) FROM us09_commerciale d
      JOIN us09_cd001 c USING (client_id)) AS communs,
    (SELECT COUNT(*) FROM us09_commerciale d
      LEFT JOIN us09_cd001 c USING (client_id)
      WHERE c.client_id IS NULL) AS direction_seulement,
    (SELECT COUNT(*) FROM us09_cd001 c
      LEFT JOIN us09_commerciale d USING (client_id)
      WHERE d.client_id IS NULL) AS cd001_seulement
UNION ALL
SELECT
    'Sinistres',
    (SELECT COUNT(*) FROM us09_sinistres),
    (SELECT COUNT(*) FROM us09_cd001),
    (SELECT COUNT(*) FROM us09_sinistres d
      JOIN us09_cd001 c USING (client_id)),
    (SELECT COUNT(*) FROM us09_sinistres d
      LEFT JOIN us09_cd001 c USING (client_id)
      WHERE c.client_id IS NULL),
    (SELECT COUNT(*) FROM us09_cd001 c
      LEFT JOIN us09_sinistres d USING (client_id)
      WHERE d.client_id IS NULL)
UNION ALL
SELECT
    'Risques',
    (SELECT COUNT(*) FROM us09_risques),
    (SELECT COUNT(*) FROM us09_cd001),
    (SELECT COUNT(*) FROM us09_risques d
      JOIN us09_cd001 c USING (client_id)),
    (SELECT COUNT(*) FROM us09_risques d
      LEFT JOIN us09_cd001 c USING (client_id)
      WHERE c.client_id IS NULL),
    (SELECT COUNT(*) FROM us09_cd001 c
      LEFT JOIN us09_risques d USING (client_id)
      WHERE d.client_id IS NULL);
