CREATE TABLE IF NOT EXISTS silver.contrat (
  silver_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  bronze_row_id BIGINT NOT NULL,
  contrat_id VARCHAR(20) NULL,
  souscripteur_id VARCHAR(20) NULL,
  assure_id VARCHAR(20) NULL,
  code_type VARCHAR(10) NULL,
  date_debut DATE NULL,
  date_fin DATE NULL,
  duree_garantie_mois INT NULL,
  prime_annuelle DECIMAL(10,2) NULL,
  date_derniere_cotisation DATE NULL,
  statut_qualite ENUM('VALIDE','A_SURVEILLER') NOT NULL DEFAULT 'VALIDE',
  _batch_id VARCHAR(20) NOT NULL,
  _processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bronze_contrat (bronze_row_id),
  KEY idx_contrat (contrat_id),
  KEY idx_souscripteur (souscripteur_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS silver.sinistre (
  silver_row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  bronze_row_id BIGINT NOT NULL,
  sinistre_id VARCHAR(20) NOT NULL,
  contrat_id VARCHAR(20) NULL,
  date_survenance DATE NULL,
  date_declaration DATE NULL,
  type_sinistre VARCHAR(40) NULL,
  montant_estime DECIMAL(12,2) NULL,
  adresse_sinistre VARCHAR(160) NOT NULL,
  cp_sinistre VARCHAR(10) NOT NULL,
  ville_sinistre VARCHAR(80) NOT NULL,
  canal_saisie VARCHAR(30) NULL,
  id_ban CHAR(9) NOT NULL,
  statut_qualite ENUM('VALIDE','A_SURVEILLER') NOT NULL DEFAULT 'VALIDE',
  _batch_id VARCHAR(20) NOT NULL,
  _processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bronze_sinistre (bronze_row_id),
  KEY idx_sinistre (sinistre_id),
  KEY idx_contrat_sinistre (contrat_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gold.contrat_certifie (
  contrat_id VARCHAR(20) PRIMARY KEY,
  souscripteur_cli_id CHAR(10) NOT NULL,
  assure_cli_id CHAR(10) NULL,
  code_type VARCHAR(10) NOT NULL,
  date_debut DATE NOT NULL,
  date_fin DATE NOT NULL,
  duree_garantie_mois INT NOT NULL,
  prime_annuelle DECIMAL(10,2) NULL,
  date_derniere_cotisation DATE NULL,
  bronze_row_id BIGINT NOT NULL,
  silver_row_id BIGINT NOT NULL,
  _batch_id VARCHAR(20) NOT NULL,
  KEY idx_cli_souscripteur (souscripteur_cli_id),
  KEY idx_cli_assure (assure_cli_id),
  CONSTRAINT fk_gold_contrat_client
    FOREIGN KEY (souscripteur_cli_id) REFERENCES gold.client_unique (cli_id),
  CONSTRAINT fk_gold_contrat_assure
    FOREIGN KEY (assure_cli_id) REFERENCES gold.client_unique (cli_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gold.sinistre_certifie (
  sinistre_id VARCHAR(20) PRIMARY KEY,
  contrat_id VARCHAR(20) NOT NULL,
  date_survenance DATE NOT NULL,
  date_declaration DATE NULL,
  type_sinistre VARCHAR(40) NULL,
  montant_estime DECIMAL(12,2) NULL,
  adresse_sinistre VARCHAR(160) NOT NULL,
  cp_sinistre VARCHAR(10) NOT NULL,
  ville_sinistre VARCHAR(80) NOT NULL,
  id_ban CHAR(9) NOT NULL,
  bronze_row_id BIGINT NOT NULL,
  silver_row_id BIGINT NOT NULL,
  _batch_id VARCHAR(20) NOT NULL,
  CONSTRAINT fk_gold_sinistre_contrat
    FOREIGN KEY (contrat_id) REFERENCES gold.contrat_certifie (contrat_id)
) ENGINE=InnoDB;
