-- Diagnostic RQ-018 : expliquer l'ecart de grain entre CD-001 Bronze et Gold.
-- Requete en lecture seule : seules des tables temporaires sont creees.
USE bronze;
SET @batch_id = 'L-2026-10-14';
SET @date_ref = DATE('2026-10-01');
SET @date_debut_cotisation = DATE('2026-07-01');

DROP TEMPORARY TABLE IF EXISTS us09_diag_cd001;
DROP TEMPORARY TABLE IF EXISTS us09_diag_gold_actif;
DROP TEMPORARY TABLE IF EXISTS us09_diag_mapping;
DROP TEMPORARY TABLE IF EXISTS us09_diag_inactifs;
DROP TEMPORARY TABLE IF EXISTS us09_diag_contrats;

CREATE TEMPORARY TABLE us09_diag_cd001 ENGINE=InnoDB AS
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
      >= @date_debut_cotisation;
ALTER TABLE us09_diag_cd001 ADD PRIMARY KEY (client_id);

CREATE TEMPORARY TABLE us09_diag_gold_actif ENGINE=InnoDB AS
SELECT DISTINCT cli_id
FROM gold.v_client_actif
WHERE _batch_id = @batch_id;
ALTER TABLE us09_diag_gold_actif ADD PRIMARY KEY (cli_id);

CREATE TEMPORARY TABLE us09_diag_mapping ENGINE=InnoDB AS
SELECT c.client_id,
       COUNT(DISTINCT x.cli_id) AS gold_ids,
       COUNT(DISTINCT a.cli_id) AS gold_actif_ids
FROM us09_diag_cd001 c
LEFT JOIN gold.xref_identifiants x
  ON x.source_systeme = 'crm'
 AND x.source_id = c.client_id
LEFT JOIN us09_diag_gold_actif a
  ON a.cli_id = x.cli_id
GROUP BY c.client_id;
ALTER TABLE us09_diag_mapping ADD PRIMARY KEY (client_id);

-- Comptes au grain source et au grain Golden Record.
SELECT 'Clients Bronze selon CD-001' AS indicateur, COUNT(*) AS valeur
FROM us09_diag_cd001
UNION ALL
SELECT 'Clients CD-001 sans identifiant Gold', COUNT(*)
FROM us09_diag_mapping WHERE gold_ids = 0
UNION ALL
SELECT 'Clients CD-001 mappes vers un Gold inactif', COUNT(*)
FROM us09_diag_mapping WHERE gold_ids > 0 AND gold_actif_ids = 0
UNION ALL
SELECT 'Identifiants source mappes vers un Gold actif', COUNT(*)
FROM us09_diag_mapping WHERE gold_actif_ids > 0
UNION ALL
SELECT 'Entites Golden Record actives', COUNT(*)
FROM us09_diag_gold_actif
UNION ALL
SELECT 'Reduction nette par rapprochement d identites',
       (SELECT COUNT(*) FROM us09_diag_mapping WHERE gold_actif_ids > 0)
       - (SELECT COUNT(*) FROM us09_diag_gold_actif)
UNION ALL
SELECT 'Entites Gold actives hors CD-001', COUNT(*)
FROM us09_diag_gold_actif a
WHERE NOT EXISTS (
    SELECT 1
    FROM gold.xref_identifiants x
    JOIN us09_diag_cd001 c ON c.client_id = x.source_id
    WHERE x.source_systeme = 'crm'
      AND x.cli_id = a.cli_id
);

-- Causes des clients CD-001 absents du referentiel Golden Record.
SELECT r.rule_id,
       COUNT(DISTINCT k.client_id) AS clients_concernes,
       COUNT(*) AS rejets_client
FROM us09_diag_mapping m
JOIN bronze.crm_client k
  ON k.client_id = m.client_id
 AND k._batch_id = @batch_id
JOIN dq.rejets r
  ON r.batch_id = @batch_id
 AND r.entite = 'client'
 AND r.porte = 'S'
 AND r.bronze_row_id = k.bronze_row_id
WHERE m.gold_ids = 0
GROUP BY r.rule_id
ORDER BY r.rule_id;

-- Contrats CD-001 des clients mappes a un Golden Record non actif.
CREATE TEMPORARY TABLE us09_diag_inactifs ENGINE=InnoDB AS
SELECT client_id
FROM us09_diag_mapping
WHERE gold_ids > 0 AND gold_actif_ids = 0;
ALTER TABLE us09_diag_inactifs ADD PRIMARY KEY (client_id);

CREATE TEMPORARY TABLE us09_diag_contrats ENGINE=InnoDB AS
SELECT c.bronze_row_id, c.contrat_id, c.souscripteur_id
FROM bronze.crm_contrat c
JOIN us09_diag_inactifs i ON i.client_id = c.souscripteur_id
JOIN bronze.crm_client k
  ON k.client_id = c.souscripteur_id
 AND k._batch_id = @batch_id
WHERE c._batch_id = @batch_id
  AND STR_TO_DATE(NULLIF(c.date_debut, ''), '%Y-%m-%d') <= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_fin, ''), '%Y-%m-%d') >= @date_ref
  AND STR_TO_DATE(NULLIF(c.date_derniere_cotisation, ''), '%Y-%m-%d')
      >= @date_debut_cotisation;
ALTER TABLE us09_diag_contrats ADD PRIMARY KEY (bronze_row_id);

SELECT 'Clients avec Gold mais sans Gold actif' AS indicateur, COUNT(*) AS valeur
FROM us09_diag_inactifs
UNION ALL
SELECT 'Contrats CD-001 Bronze de ces clients', COUNT(*)
FROM us09_diag_contrats
UNION ALL
SELECT 'Contrats CD-001 presents dans Silver', COUNT(*)
FROM us09_diag_contrats c
JOIN silver.contrat s
  ON s.bronze_row_id = c.bronze_row_id
 AND s._batch_id = @batch_id
UNION ALL
SELECT 'Contrats CD-001 certifies dans Gold', COUNT(*)
FROM us09_diag_contrats c
JOIN gold.contrat_certifie g
  ON g.contrat_id = c.contrat_id
 AND g._batch_id = @batch_id;

-- Les regles peuvent se cumuler sur un contrat : ne pas additionner ces lignes.
SELECT r.porte, r.rule_id,
       COUNT(DISTINCT c.souscripteur_id) AS clients_concernes,
       COUNT(DISTINCT c.bronze_row_id) AS contrats_concernes
FROM us09_diag_contrats c
JOIN dq.rejets r
  ON r.batch_id = @batch_id
 AND r.entite = 'contrat'
 AND r.bronze_row_id = c.bronze_row_id
GROUP BY r.porte, r.rule_id
ORDER BY r.porte, r.rule_id;
