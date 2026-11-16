# -*- coding: utf-8 -*-
"""Historiser, certifier et publier les données Gold vers le CRM cible."""
import argparse
import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from build_silver import BATCH_DEFAULT, DB_URL_DEFAULT, ROOT, key, present


REPORTS = ROOT / "reports"
DELIVERABLES = ROOT / "livrables"
CERTIFICATE_PREFIX = "CERT-"
ACTIVE_TARGET = 37643
LAYER_ORDER = ("BRONZE", "SILVER", "GOLD", "CRM")

GOLD_TABLES = {
    "client_unique": (
        "cli_id, nom_reference, adresse, date_naissance, cp, ville, pays_iso, "
        "telephone, email, nb_identifiants_source, statut_client, _batch_id",
        "cli_id",
    ),
    "xref_identifiants": (
        "cli_id, source_systeme, source_id, bronze_row_id, silver_row_id",
        "source_systeme, source_id",
    ),
    "contrat_certifie": (
        "contrat_id, souscripteur_cli_id, assure_cli_id, code_type, date_debut, "
        "date_fin, duree_garantie_mois, prime_annuelle, date_derniere_cotisation, "
        "bronze_row_id, silver_row_id, _batch_id",
        "contrat_id",
    ),
    "sinistre_certifie": (
        "sinistre_id, contrat_id, date_survenance, date_declaration, type_sinistre, "
        "montant_estime, adresse_sinistre, cp_sinistre, ville_sinistre, id_ban, "
        "bronze_row_id, silver_row_id, _batch_id",
        "sinistre_id",
    ),
}

PUBLISH_TABLES = {
    "client": (
        "cli_id, nom_reference, adresse, date_naissance, cp, ville, pays_iso, "
        "telephone, email, nb_identifiants_source, statut_client, _batch_id",
        "cli_id",
        """
        CREATE TABLE IF NOT EXISTS crm_cible.client (
          cli_id CHAR(10) PRIMARY KEY,
          nom_reference VARCHAR(150) NOT NULL,
          adresse VARCHAR(255) NULL,
          date_naissance DATE NULL,
          cp VARCHAR(10) NULL,
          ville VARCHAR(100) NULL,
          pays_iso CHAR(2) NULL,
          telephone VARCHAR(20) NULL,
          email VARCHAR(150) NULL,
          nb_identifiants_source INT NOT NULL,
          statut_client ENUM('PROSPECT','ASSURE','ACTIF','INACTIF') NOT NULL,
          _batch_id VARCHAR(20) NOT NULL
        ) ENGINE=InnoDB
        """,
    ),
    "contrat": (
        "contrat_id, souscripteur_cli_id, assure_cli_id, code_type, date_debut, "
        "date_fin, duree_garantie_mois, prime_annuelle, date_derniere_cotisation, "
        "bronze_row_id, silver_row_id, _batch_id",
        "contrat_id",
        """
        CREATE TABLE IF NOT EXISTS crm_cible.contrat (
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
          KEY idx_cible_contrat_cli (souscripteur_cli_id),
          CONSTRAINT fk_cible_contrat_client
            FOREIGN KEY (souscripteur_cli_id) REFERENCES crm_cible.client (cli_id),
          CONSTRAINT fk_cible_contrat_assure
            FOREIGN KEY (assure_cli_id) REFERENCES crm_cible.client (cli_id)
        ) ENGINE=InnoDB
        """,
    ),
    "sinistre": (
        "sinistre_id, contrat_id, date_survenance, date_declaration, type_sinistre, "
        "montant_estime, adresse_sinistre, cp_sinistre, ville_sinistre, id_ban, "
        "bronze_row_id, silver_row_id, _batch_id",
        "sinistre_id",
        """
        CREATE TABLE IF NOT EXISTS crm_cible.sinistre (
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
          CONSTRAINT fk_cible_sinistre_contrat
            FOREIGN KEY (contrat_id) REFERENCES crm_cible.contrat (contrat_id)
        ) ENGINE=InnoDB
        """,
    ),
}


class PublicationRefused(RuntimeError):
    """The current certification does not authorize CRM publication."""


class _RollbackSelfTest(Exception):
    """Roll back a successful publication simulation."""


def scalar(connection, sql, parameters):
    return int(connection.execute(text(sql), parameters).scalar() or 0)


def canonical(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def hash_query(connection, sql, parameters, batch_id):
    digest = hashlib.sha256()
    digest.update(batch_id.encode("utf-8"))
    digest.update(b"\n")
    result = connection.execution_options(stream_results=True).execute(
        text(sql), parameters
    )
    for row in result:
        encoded = json.dumps(
            [canonical(value) for value in row],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def gold_fingerprint(connection, batch_id):
    digest = hashlib.sha256()
    for table, (columns, order_by) in GOLD_TABLES.items():
        digest.update(f"{table}\n".encode("ascii"))
        if table == "xref_identifiants":
            sql = f"""
                SELECT x.cli_id, x.source_systeme, x.source_id,
                       x.bronze_row_id, x.silver_row_id
                FROM gold.xref_identifiants x
                JOIN silver.client s
                  ON s.source_systeme = x.source_systeme
                 AND s.source_id = x.source_id
                WHERE s._batch_id = :batch_id
                ORDER BY x.source_systeme, x.source_id
            """
        else:
            sql = f"""
                SELECT {columns} FROM gold.{table}
                WHERE _batch_id = :batch_id ORDER BY {order_by}
            """
        digest.update(bytes.fromhex(hash_query(
            connection, sql, {"batch_id": batch_id}, batch_id
        )))
    return digest.hexdigest()


def latest_metrics(connection, batch_id):
    return pd.read_sql_query(text("""
        SELECT m.couche, m.rule_id, r.libelle, r.dimension, r.porte, r.severite,
               SUM(m.nb_testees) AS nb_testees,
               SUM(m.nb_echecs) AS nb_echecs,
               CASE WHEN SUM(m.nb_testees) = 0 THEN NULL
                    ELSE ROUND(100.0 * (SUM(m.nb_testees)-SUM(m.nb_echecs))
                                      / SUM(m.nb_testees), 3)
               END AS taux_conformite,
               MAX(m.mesure_le) AS mesure_le
        FROM dq.v_derniere_mesure m
        JOIN dq.regle r ON r.rule_id = m.rule_id
        WHERE m.batch_id = :batch_id AND m.table_cible NOT LIKE 's5.%'
        GROUP BY m.couche, m.rule_id, r.libelle, r.dimension, r.porte, r.severite
        ORDER BY m.rule_id, FIELD(m.couche, 'BRONZE','SILVER','GOLD','CRM')
    """), connection, params={"batch_id": batch_id})


def write_history_report(connection, batch_id):
    REPORTS.mkdir(parents=True, exist_ok=True)
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    by_rule = latest_metrics(connection, batch_id)
    by_rule.to_csv(
        DELIVERABLES / "us29_historique_mesures.csv",
        index=False, encoding="utf-8-sig",
    )

    dimensions = (
        by_rule.groupby(["couche", "dimension"], dropna=False)
        .apply(
            lambda frame: pd.Series({
                "nb_testees": int(frame["nb_testees"].sum()),
                "nb_echecs": int(frame["nb_echecs"].sum()),
                "taux_conformite": (
                    round(
                        100 * (frame["nb_testees"].sum() - frame["nb_echecs"].sum())
                        / frame["nb_testees"].sum(), 3
                    ) if frame["nb_testees"].sum() else None
                ),
            }),
            include_groups=False,
        )
        .reset_index()
    )
    dimensions.to_csv(
        DELIVERABLES / "us29_kpi_dimensions.csv",
        index=False, encoding="utf-8-sig",
    )
    write_dimension_chart(dimensions, REPORTS / "us30_evolution_qualite.svg")
    return by_rule, dimensions


def write_dimension_chart(dimensions, output_path):
    width, height = 920, 520
    left, right, top, bottom = 100, 40, 55, 90
    plot_width, plot_height = width - left - right, height - top - bottom
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b")
    layers = list(LAYER_ORDER)
    layer_x = {
        layer: left + index * plot_width / (len(layers) - 1)
        for index, layer in enumerate(layers)
    }
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="460" y="28" text-anchor="middle" font-size="18" font-family="Arial">'
        'Conformité mesurée par couche et dimension</text>',
    ]
    for tick in range(0, 101, 20):
        y = top + (100 - tick) * plot_height / 100
        svg.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
            'stroke="#dddddd"/>'
        )
        svg.append(
            f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" '
            'font-size="12" font-family="Arial">'
            f'{tick}%</text>'
        )
    for layer in layers:
        x = layer_x[layer]
        svg.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" '
            'stroke="#eeeeee"/>'
        )
        svg.append(
            f'<text x="{x:.1f}" y="{height-bottom+24}" text-anchor="middle" '
            'font-size="13" font-family="Arial">'
            f'{layer.title()}</text>'
        )
    dimensions_names = sorted(str(value) for value in dimensions["dimension"].dropna().unique())
    for index, dimension in enumerate(dimensions_names):
        frame = dimensions[dimensions["dimension"] == dimension]
        points = []
        for layer in layers:
            matches = frame[frame["couche"] == layer]
            if matches.empty or pd.isna(matches.iloc[0]["taux_conformite"]):
                continue
            rate = float(matches.iloc[0]["taux_conformite"])
            x = layer_x[layer]
            y = top + (100 - rate) * plot_height / 100
            points.append((x, y))
            svg.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[index % len(colors)]}"/>'
            )
        if len(points) > 1:
            coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            svg.append(
                f'<polyline points="{coordinates}" fill="none" '
                f'stroke="{colors[index % len(colors)]}" stroke-width="2"/>'
            )
        legend_y = top + index * 22
        svg.append(
            f'<line x1="{width-245}" y1="{legend_y}" x2="{width-225}" y2="{legend_y}" '
            f'stroke="{colors[index % len(colors)]}" stroke-width="3"/>'
            f'<text x="{width-218}" y="{legend_y+4}" font-size="11" '
            f'font-family="Arial">{dimension}</text>'
        )
    svg.append(
        f'<text x="25" y="{top+plot_height/2:.1f}" transform="rotate(-90 25 '
        f'{top+plot_height/2:.1f})" text-anchor="middle" font-size="13" '
        'font-family="Arial">Taux de conformité</text>'
    )
    svg.append(
        f'<text x="{width/2:.1f}" y="{height-20}" text-anchor="middle" '
        'font-size="12" font-family="Arial">Couche de données</text>'
    )
    svg.append("</svg>")
    output_path.write_text("\n".join(svg), encoding="utf-8")


def check_result(connection, rule_id, layer, target, sql, parameters):
    row = connection.execute(text(sql), parameters).first()
    if row is None:
        raise RuntimeError(f"Contrôle {rule_id} sans résultat")
    tested, failed = int(row[0] or 0), int(row[1] or 0)
    connection.execute(text("""
        INSERT INTO dq.dq_history
            (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
        VALUES (:batch_id, :layer, :rule_id, :target, :tested, :failed)
    """), {
        "batch_id": parameters["batch_id"],
        "layer": layer,
        "rule_id": rule_id,
        "target": target,
        "tested": tested,
        "failed": failed,
    })
    return {
        "rule_id": rule_id,
        "couche": layer,
        "table_cible": target,
        "nb_testees": tested,
        "nb_echecs": failed,
        "conforme": tested > 0 and failed == 0,
    }


def certify_checks(connection, batch_id):
    p = {"batch_id": batch_id}
    results = []

    history_rules = ("RQ-021", "RQ-022")
    for rule_id in history_rules:
        rows = connection.execute(text("""
            SELECT COUNT(*) AS tables_mesurees, SUM(nb_echecs) AS echecs
            FROM dq.v_derniere_mesure
            WHERE batch_id = :batch_id AND couche = 'BRONZE' AND rule_id = :rule_id
              AND table_cible <> 'bronze'
        """), {"batch_id": batch_id, "rule_id": rule_id}).first()
        tested, failed = int(rows[0] or 0), int(rows[1] or 0)
        expected_tables = 7
        results.append({
            "rule_id": rule_id,
            "couche": "BRONZE",
            "table_cible": "historique des 7 tables Bronze",
            "nb_testees": expected_tables,
            "nb_echecs": failed + int(tested != expected_tables),
            "conforme": tested == expected_tables and failed == 0,
        })

    results.append(check_result(connection, "RQ-001", "SILVER", "silver.contrat", """
        SELECT COUNT(*), SUM(date_debut IS NULL OR date_fin IS NULL OR date_fin <= date_debut)
        FROM silver.contrat WHERE _batch_id = :batch_id
    """, p))
    results.append(check_result(connection, "RQ-007", "SILVER", "silver.client", """
        SELECT COUNT(*), SUM(c.pays_iso IS NULL OR NOT EXISTS (
            SELECT 1 FROM silver.ref_pays r WHERE r.code_pays = c.pays_iso
        ))
        FROM silver.client c WHERE c._batch_id = :batch_id
    """, p))
    results.append(check_result(connection, "RQ-009", "SILVER", "silver.client", """
        SELECT COUNT(*), SUM(c.type_personne IS NULL OR c.type_personne NOT IN
          ('prospect','souscripteur','assure'))
        FROM silver.client c
        WHERE c._batch_id = :batch_id AND c.source_systeme = 'crm'
    """, p))
    results.append(check_result(connection, "RQ-010", "SILVER", "silver.contrat", """
        SELECT COUNT(*), SUM(duree_garantie_mois IS NULL OR duree_garantie_mois NOT IN
          (12,24,36,60))
        FROM silver.contrat WHERE _batch_id = :batch_id
    """, p))
    results.append(check_result(connection, "RQ-014", "SILVER", "silver.sinistre", """
        SELECT COUNT(*), SUM(NOT EXISTS (
          SELECT 1 FROM silver.ref_ban b WHERE b.id_ban = s.id_ban
        ))
        FROM silver.sinistre s WHERE s._batch_id = :batch_id
    """, p))
    results.append(check_result(connection, "RQ-001", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(date_debut IS NULL OR date_fin IS NULL OR date_fin <= date_debut)
        FROM gold.contrat_certifie WHERE _batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-010", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(duree_garantie_mois IS NULL OR duree_garantie_mois NOT IN
          (12,24,36,60))
        FROM gold.contrat_certifie WHERE _batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-014", "GOLD", "gold.sinistre_certifie", """
        SELECT COUNT(*), SUM(NOT EXISTS (
          SELECT 1 FROM silver.ref_ban b WHERE b.id_ban=s.id_ban
        ))
        FROM gold.sinistre_certifie s WHERE s._batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-020", "SILVER", "silver.keys", """
        SELECT
          (SELECT COUNT(*) FROM silver.client WHERE _batch_id = :batch_id)
          + (SELECT COUNT(*) FROM silver.contrat WHERE _batch_id = :batch_id)
          + (SELECT COUNT(*) FROM silver.sinistre WHERE _batch_id = :batch_id),
          (SELECT COUNT(*) FROM (
              SELECT source_systeme, source_id FROM silver.client
              WHERE _batch_id = :batch_id
              GROUP BY source_systeme, source_id HAVING source_id IS NULL OR COUNT(*) > 1
           ) c)
          + (SELECT COUNT(*) FROM (
              SELECT contrat_id FROM silver.contrat
              WHERE _batch_id = :batch_id
              GROUP BY contrat_id HAVING contrat_id IS NULL OR COUNT(*) > 1
           ) k)
          + (SELECT COUNT(*) FROM (
              SELECT sinistre_id FROM silver.sinistre
              WHERE _batch_id = :batch_id
              GROUP BY sinistre_id HAVING sinistre_id IS NULL OR COUNT(*) > 1
           ) s)
    """, p))

    reconciliation_sql = (
        ("crm_client", "silver.client", "client", "crm"),
        ("cif_clients", "silver.client", "client", "cif"),
        ("crm_contrat", "silver.contrat", "contrat", None),
        ("crm_sinistre", "silver.sinistre", "sinistre", None),
    )
    conservation_total = 0
    conservation_failures = 0
    for bronze_table, silver_table, entity, system in reconciliation_sql:
        bronze_params = {"batch_id": batch_id}
        bronze_sql = f"SELECT COUNT(*) FROM bronze.{bronze_table} WHERE _batch_id=:batch_id"
        bronze_count = scalar(connection, bronze_sql, bronze_params)
        silver_sql = f"SELECT COUNT(*) FROM {silver_table} WHERE _batch_id=:batch_id"
        if system:
            silver_sql += " AND source_systeme=:system"
            bronze_params["system"] = system
        silver_count = scalar(connection, silver_sql, bronze_params)
        reject_count = scalar(connection, """
            SELECT COUNT(DISTINCT CONCAT(source_systeme, ':', bronze_row_id))
            FROM dq.rejets
            WHERE batch_id=:batch_id AND porte='S' AND entite=:entity
              AND (:system IS NULL OR source_systeme=:system)
        """, {"batch_id": batch_id, "entity": entity, "system": system})
        conservation_total += bronze_count
        conservation_failures += int(bronze_count != silver_count + reject_count)
    results.append(check_result(
        connection, "RQ-024", "SILVER", "s5.certification.RQ-024",
        "SELECT :tested, :failed",
        {"batch_id": batch_id, "tested": conservation_total,
         "failed": conservation_failures},
    ))

    silver_lineage_checks = (
        ("client", """
            SELECT COUNT(*), SUM(NOT EXISTS (
              SELECT 1 FROM bronze.crm_client b
              WHERE c.source_systeme='crm' AND b.bronze_row_id=c.bronze_row_id
                AND b._batch_id=c._batch_id
            ) AND NOT EXISTS (
              SELECT 1 FROM bronze.cif_clients b
              WHERE c.source_systeme='cif' AND b.bronze_row_id=c.bronze_row_id
                AND b._batch_id=c._batch_id
            ))
            FROM silver.client c WHERE c._batch_id=:batch_id
        """),
        ("contrat", """
            SELECT COUNT(*), SUM(NOT EXISTS (
              SELECT 1 FROM bronze.crm_contrat b
              WHERE b.bronze_row_id=k.bronze_row_id AND b._batch_id=k._batch_id
            )) FROM silver.contrat k WHERE k._batch_id=:batch_id
        """),
        ("sinistre", """
            SELECT COUNT(*), SUM(NOT EXISTS (
              SELECT 1 FROM bronze.crm_sinistre b
              WHERE b.bronze_row_id=s.bronze_row_id AND b._batch_id=s._batch_id
            )) FROM silver.sinistre s WHERE s._batch_id=:batch_id
        """),
    )
    silver_lineage_tested = silver_lineage_failed = 0
    for entity, sql in silver_lineage_checks:
        row = connection.execute(text(sql), p).first()
        silver_lineage_tested += int(row[0] or 0)
        silver_lineage_failed += int(row[1] or 0)

    gold_lineage_checks = (
        ("client", """
            SELECT COUNT(*), SUM(x.cli_id IS NULL)
            FROM gold.client_unique c
            LEFT JOIN (
              SELECT x.cli_id, COUNT(*) AS nb_sources
              FROM gold.xref_identifiants x
              JOIN silver.client s ON s.source_systeme=x.source_systeme
                AND s.source_id=x.source_id AND s.silver_row_id=x.silver_row_id
                AND s._batch_id=:batch_id
              GROUP BY x.cli_id
            ) x ON x.cli_id=c.cli_id
            WHERE c._batch_id=:batch_id
        """),
        ("xref", """
            SELECT COUNT(*), SUM(s.silver_row_id IS NULL OR
              (x.source_systeme='crm' AND b.bronze_row_id IS NULL) OR
              (x.source_systeme='cif' AND c.bronze_row_id IS NULL))
            FROM gold.xref_identifiants x
            LEFT JOIN silver.client s ON s.silver_row_id=x.silver_row_id
              AND s.source_systeme=x.source_systeme AND s.source_id=x.source_id
              AND s._batch_id=:batch_id
            LEFT JOIN bronze.crm_client b ON x.source_systeme='crm'
              AND b.bronze_row_id=x.bronze_row_id AND b._batch_id=:batch_id
            LEFT JOIN bronze.cif_clients c ON x.source_systeme='cif'
              AND c.bronze_row_id=x.bronze_row_id AND c._batch_id=:batch_id
            WHERE s.silver_row_id IS NOT NULL OR x.cli_id IN (
              SELECT cli_id FROM gold.client_unique WHERE _batch_id=:batch_id
            )
        """),
        ("contrat", """
            SELECT COUNT(*), SUM(s.silver_row_id IS NULL OR b.bronze_row_id IS NULL)
            FROM gold.contrat_certifie g
            LEFT JOIN silver.contrat s ON s.silver_row_id=g.silver_row_id
              AND s.bronze_row_id=g.bronze_row_id AND s._batch_id=:batch_id
            LEFT JOIN bronze.crm_contrat b ON b.bronze_row_id=g.bronze_row_id
              AND b._batch_id=:batch_id
            WHERE g._batch_id=:batch_id
        """),
        ("sinistre", """
            SELECT COUNT(*), SUM(s.silver_row_id IS NULL OR b.bronze_row_id IS NULL)
            FROM gold.sinistre_certifie g
            LEFT JOIN silver.sinistre s ON s.silver_row_id=g.silver_row_id
              AND s.bronze_row_id=g.bronze_row_id AND s._batch_id=:batch_id
            LEFT JOIN bronze.crm_sinistre b ON b.bronze_row_id=g.bronze_row_id
              AND b._batch_id=:batch_id
            WHERE g._batch_id=:batch_id
        """),
    )
    gold_lineage_tested = gold_lineage_failed = 0
    for _, sql in gold_lineage_checks:
        row = connection.execute(text(sql), p).first()
        gold_lineage_tested += int(row[0] or 0)
        gold_lineage_failed += int(row[1] or 0)
    results.append(check_result(
        connection, "RQ-023", "GOLD", "s5.certification.RQ-023",
        "SELECT :tested, :failed",
        {"batch_id": batch_id,
         "tested": silver_lineage_tested + gold_lineage_tested,
         "failed": silver_lineage_failed + gold_lineage_failed},
    ))

    results.append(check_result(connection, "RQ-002", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(
          (b.raison_sociale IS NULL OR TRIM(b.raison_sociale)='')
          AND (s.date_naissance IS NULL OR TIMESTAMPDIFF(YEAR,s.date_naissance,k.date_debut)<18)
        )
        FROM gold.contrat_certifie k
        JOIN bronze.crm_contrat bc ON bc.bronze_row_id=k.bronze_row_id
          AND bc._batch_id=:batch_id
        JOIN bronze.crm_client b ON b.client_id=bc.souscripteur_id
          AND b._batch_id=:batch_id AND b.type_personne='souscripteur'
        JOIN silver.client s ON s.source_systeme='crm'
          AND s.source_id=bc.souscripteur_id
          AND s._batch_id=:batch_id
        WHERE k._batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-011", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(NOT EXISTS (
          SELECT 1 FROM crm.type_contrat t WHERE t.code_type=k.code_type
        )) FROM gold.contrat_certifie k WHERE k._batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-012", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(c.cli_id IS NULL)
        FROM gold.contrat_certifie k
        LEFT JOIN gold.client_unique c ON c.cli_id=k.souscripteur_cli_id
          AND c._batch_id=:batch_id
        WHERE k._batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-013", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(a.cli_id IS NULL)
        FROM gold.contrat_certifie k
        LEFT JOIN gold.client_unique a ON a.cli_id=k.assure_cli_id
          AND a._batch_id=:batch_id
        WHERE k._batch_id=:batch_id AND k.assure_cli_id IS NOT NULL
    """, p))
    results.append(check_result(connection, "RQ-015", "GOLD", "gold.contrat_certifie", """
        SELECT COUNT(*), SUM(b.type_personne='prospect')
        FROM gold.contrat_certifie k
        JOIN bronze.crm_contrat bc ON bc.bronze_row_id=k.bronze_row_id
          AND bc._batch_id=:batch_id
        JOIN bronze.crm_client b ON b.client_id=bc.souscripteur_id
          AND b._batch_id=:batch_id
        WHERE k._batch_id=:batch_id
    """, p))
    results.append(check_result(connection, "RQ-017", "GOLD", "gold.sinistre_certifie", """
        SELECT COUNT(*), SUM(
          s.date_survenance < k.date_debut OR s.date_survenance > k.date_fin
        )
        FROM gold.sinistre_certifie s
        JOIN gold.contrat_certifie k ON k.contrat_id=s.contrat_id
          AND k._batch_id=:batch_id
        WHERE s._batch_id=:batch_id
    """, p))
    active_count = scalar(connection, """
        SELECT COUNT(DISTINCT cli_id) FROM gold.v_client_actif
        WHERE _batch_id=:batch_id
    """, p)
    results.append(check_result(
        connection, "RQ-018", "GOLD", "gold.v_client_actif",
        "SELECT 3, IF(:active_count=:expected, 0, 3)",
        {"batch_id": batch_id, "active_count": active_count, "expected": ACTIVE_TARGET},
    ))
    results.append(check_result(connection, "RQ-019", "GOLD", "gold.client_unique", """
        SELECT COUNT(*), (SELECT COUNT(*) FROM (
          SELECT x.source_systeme, x.source_id FROM gold.xref_identifiants x
          JOIN silver.client s ON s.source_systeme=x.source_systeme AND s.source_id=x.source_id
          WHERE s._batch_id=:batch_id
          GROUP BY x.source_systeme, x.source_id HAVING COUNT(DISTINCT x.cli_id)>1
        ) duplicates)
        FROM gold.client_unique WHERE _batch_id=:batch_id
    """, p))

    found_rules = {result["rule_id"] for result in results}
    required_blocking = set(connection.execute(text("""
        SELECT rule_id FROM dq.regle
        WHERE severite='BLOQUANTE' AND porte IN ('B','S','G')
    """)).scalars())
    missing = required_blocking - found_rules
    if missing:
        raise RuntimeError(
            "Règles bloquantes non couvertes par le certificat : "
            + ", ".join(sorted(missing))
        )
    return results


def ensure_publish_tables(connection):
    for _, (_, _, ddl) in PUBLISH_TABLES.items():
        connection.exec_driver_sql(ddl)


def table_digest(connection, schema, table, columns, order_by, batch_id):
    return hash_query(
        connection,
        f"SELECT {columns} FROM {schema}.{table} "
        "WHERE _batch_id=:batch_id ORDER BY " + order_by,
        {"batch_id": batch_id},
        batch_id,
    )


def publish_in_transaction(connection, batch_id):
    certificate = connection.execute(text("""
        SELECT certificat_id, decision, empreinte_gold
        FROM dq.certificat_qualite
        WHERE batch_id=:batch_id
        ORDER BY emis_le DESC, certificat_id DESC LIMIT 1
    """), {"batch_id": batch_id}).first()
    if not certificate:
        raise PublicationRefused("Publication refusée : aucun certificat pour ce lot")
    if certificate.decision != "GO":
        raise PublicationRefused(
            f"Publication refusée : certificat {certificate.certificat_id} = {certificate.decision}"
        )
    actual_fingerprint = gold_fingerprint(connection, batch_id)
    if actual_fingerprint != certificate.empreinte_gold:
        raise PublicationRefused(
            "Publication refusée : Gold a changé depuis l'émission du certificat"
        )

    for table in ("sinistre", "contrat", "client"):
        connection.exec_driver_sql(f"DELETE FROM crm_cible.{table}")

    reconciliation = []
    for target, (columns, order_by, _) in PUBLISH_TABLES.items():
        source = {
            "client": "client_unique",
            "contrat": "contrat_certifie",
            "sinistre": "sinistre_certifie",
        }[target]
        if target == "client":
            source_columns = columns
        else:
            source_columns = columns
        connection.execute(text(
            f"INSERT INTO crm_cible.{target} ({columns}) "
            f"SELECT {source_columns} FROM gold.{source} WHERE _batch_id=:batch_id"
        ), {"batch_id": batch_id})
        source_count = scalar(
            connection, f"SELECT COUNT(*) FROM gold.{source} WHERE _batch_id=:batch_id",
            {"batch_id": batch_id},
        )
        target_count = scalar(
            connection, f"SELECT COUNT(*) FROM crm_cible.{target} WHERE _batch_id=:batch_id",
            {"batch_id": batch_id},
        )
        source_hash = table_digest(connection, "gold", source, columns, order_by, batch_id)
        target_hash = table_digest(connection, "crm_cible", target, columns, order_by, batch_id)
        failures = int(source_count != target_count or source_hash != target_hash)
        connection.execute(text("""
            INSERT INTO dq.dq_history
                (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
            VALUES (:batch_id, 'CRM', 'RQ-025', :target, :tested, :failed)
        """), {
            "batch_id": batch_id,
            "target": f"crm_cible.{target}",
            "tested": source_count,
            "failed": failures,
        })
        reconciliation.append({
            "table": target,
            "lignes_gold": source_count,
            "lignes_crm_cible": target_count,
            "somme_controle_gold": source_hash,
            "somme_controle_crm_cible": target_hash,
            "ecart": failures,
        })
    if any(row["ecart"] for row in reconciliation):
        raise RuntimeError("RQ-025 échoue ; transaction de publication annulée")
    return reconciliation


def certify(engine, batch_id):
    with engine.begin() as connection:
        checks = certify_checks(connection, batch_id)
        fingerprint = gold_fingerprint(connection, batch_id)
        checked = len(checks)
        passed = sum(result["conforme"] for result in checks)
        decision = "GO" if checked == passed else "NO_GO"
        certificate_id = CERTIFICATE_PREFIX + batch_id
        failed_rules = [
            f"{row['rule_id']} ({row['nb_echecs']}/{row['nb_testees']})"
            for row in checks if not row["conforme"]
        ]
        connection.execute(text("""
            INSERT INTO dq.certificat_qualite
                (certificat_id, batch_id, nb_bloquantes_testees,
                 nb_bloquantes_ok, empreinte_gold, decision, signataire, commentaire)
            VALUES
                (:certificate_id, :batch_id, :tested, :passed, :fingerprint,
                 :decision, NULL, :comment)
            ON DUPLICATE KEY UPDATE
                emis_le=CURRENT_TIMESTAMP,
                nb_bloquantes_testees=VALUES(nb_bloquantes_testees),
                nb_bloquantes_ok=VALUES(nb_bloquantes_ok),
                empreinte_gold=VALUES(empreinte_gold),
                decision=VALUES(decision),
                signataire=NULL,
                commentaire=VALUES(commentaire)
        """), {
            "certificate_id": certificate_id,
            "batch_id": batch_id,
            "tested": checked,
            "passed": passed,
            "fingerprint": fingerprint,
            "decision": decision,
            "comment": (
                "Généré automatiquement ; Data Owner non signataire. Échecs: "
                + (", ".join(failed_rules) if failed_rules else "aucun")
            )[:500],
        })
        pd.DataFrame(checks).to_csv(
            DELIVERABLES / "us31_controles_certificat.csv",
            index=False, encoding="utf-8-sig",
        )
    print(
        f"Certificat {CERTIFICATE_PREFIX + batch_id}: {decision}, "
        f"{passed}/{checked} contrôles conformes, SHA-256 {fingerprint}"
    )
    if failed_rules:
        print("Échecs bloquants : " + "; ".join(failed_rules))
    return decision


def publish(engine, batch_id):
    ensure_publish_tables_sql(engine)
    try:
        with engine.begin() as connection:
            reconciliation = publish_in_transaction(connection, batch_id)
    except PublicationRefused as error:
        print(str(error))
        raise SystemExit(2) from error
    pd.DataFrame(reconciliation).to_csv(
        DELIVERABLES / "us32_reconciliation.csv",
        index=False, encoding="utf-8-sig",
    )
    print("Publication CRM réussie ; RQ-025 conforme pour les trois tables.")


def ensure_publish_tables_sql(engine):
    with engine.begin() as connection:
        ensure_publish_tables(connection)


def self_test(engine, batch_id):
    ensure_publish_tables_sql(engine)
    checks = []
    reconciliation = []
    degraded_test = []
    try:
        with engine.begin() as connection:
            fingerprint = gold_fingerprint(connection, batch_id)
            original = connection.execute(text("""
                SELECT certificat_id, batch_id, emis_le, nb_bloquantes_testees,
                       nb_bloquantes_ok, empreinte_gold, decision, signataire, commentaire
                FROM dq.certificat_qualite WHERE batch_id=:batch_id
            """), {"batch_id": batch_id}).fetchall()
            connection.execute(text("""
                DELETE FROM dq.certificat_qualite WHERE batch_id=:batch_id
            """), {"batch_id": batch_id})
            try:
                publish_in_transaction(connection, batch_id)
            except PublicationRefused as error:
                checks.append(("sans certificat", str(error), True))
            else:
                checks.append(("sans certificat", "Publication non refusée", False))

            connection.execute(text("""
                INSERT INTO dq.certificat_qualite
                    (certificat_id,batch_id,nb_bloquantes_testees,nb_bloquantes_ok,
                     empreinte_gold,decision,signataire,commentaire)
                VALUES (:id,:batch,1,0,:hash,'NO_GO',NULL,'self-test')
            """), {"id": "TEST-NO-GO", "batch": batch_id, "hash": fingerprint})
            try:
                publish_in_transaction(connection, batch_id)
            except PublicationRefused as error:
                checks.append(("certificat NO_GO", str(error), True))
            else:
                checks.append(("certificat NO_GO", "Publication non refusée", False))

            connection.execute(text(
                "DELETE FROM dq.certificat_qualite WHERE certificat_id='TEST-NO-GO'"
            ))
            connection.execute(text("""
                INSERT INTO dq.certificat_qualite
                    (certificat_id,batch_id,nb_bloquantes_testees,nb_bloquantes_ok,
                     empreinte_gold,decision,signataire,commentaire)
                VALUES ('TEST-STALE',:batch,1,1,:hash,'GO',NULL,'self-test')
            """), {"batch": batch_id, "hash": "0" * 64})
            try:
                publish_in_transaction(connection, batch_id)
            except PublicationRefused as error:
                checks.append(("Gold modifié", str(error), True))
            else:
                checks.append(("Gold modifié", "Empreinte non vérifiée", False))

            connection.execute(text(
                "DELETE FROM dq.certificat_qualite WHERE certificat_id='TEST-STALE'"
            ))
            connection.execute(text("""
                INSERT INTO dq.certificat_qualite
                    (certificat_id,batch_id,nb_bloquantes_testees,nb_bloquantes_ok,
                     empreinte_gold,decision,signataire,commentaire)
                VALUES ('TEST-GO',:batch,1,1,:hash,'GO',NULL,'self-test transactionnel')
            """), {"batch": batch_id, "hash": fingerprint})
            reconciliation = publish_in_transaction(connection, batch_id)
            intact = all(
                row["lignes_gold"] == row["lignes_crm_cible"] and row["ecart"] == 0
                for row in reconciliation
            )
            checks.append((
                "certificat GO et Gold intact",
                "Publication transactionnelle et RQ-025 conformes"
                if intact else "Écart de réconciliation",
                intact,
            ))

            contract = connection.execute(text("""
                SELECT contrat_id FROM gold.contrat_certifie
                WHERE _batch_id=:batch_id ORDER BY contrat_id LIMIT 1
            """), {"batch_id": batch_id}).first()
            if not contract:
                raise RuntimeError("Aucun contrat Gold disponible pour le test négatif")
            connection.execute(text("""
                UPDATE gold.contrat_certifie
                SET date_fin=date_debut
                WHERE contrat_id=:contract_id
            """), {"contract_id": contract.contrat_id})
            degraded_checks = certify_checks(connection, batch_id)
            degraded_failures = [
                f"{row['rule_id']} ({row['nb_echecs']}/{row['nb_testees']})"
                for row in degraded_checks if not row["conforme"]
            ]
            degraded_decision = (
                "GO" if len(degraded_checks) == sum(
                    row["conforme"] for row in degraded_checks
                ) else "NO_GO"
            )
            deliberately_failed = any(
                row["rule_id"] == "RQ-001" and row["nb_echecs"] > 0
                for row in degraded_checks
            )
            degraded_test.append({
                "scenario": "lot de référence dégradé : date_fin = date_debut",
                "decision": degraded_decision,
                "regles_en_echec": ";".join(degraded_failures),
                "rq001_echec_detecte": deliberately_failed,
            })
            checks.append((
                "certification du lot volontairement dégradé",
                f"{degraded_decision}; RQ-001 détectée={deliberately_failed}",
                degraded_decision == "NO_GO" and deliberately_failed,
            ))
            raise _RollbackSelfTest()
    except _RollbackSelfTest:
        pass

    pd.DataFrame(checks, columns=("scenario", "message", "reussi")).to_csv(
        DELIVERABLES / "us32_self_test.csv",
        index=False, encoding="utf-8-sig",
    )
    pd.DataFrame(reconciliation).to_csv(
        DELIVERABLES / "us32_self_test_reconciliation.csv",
        index=False, encoding="utf-8-sig",
    )
    pd.DataFrame(degraded_test).to_csv(
        DELIVERABLES / "us31_no_go_test.csv",
        index=False, encoding="utf-8-sig",
    )
    for scenario, message, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'} {scenario}: {message}")
    if not checks or not all(row[2] for row in checks):
        raise RuntimeError("Un ou plusieurs scénarios de publication ont échoué")
    print("Self-test terminé : toutes les écritures ont été annulées.")


def history(engine, batch_id):
    with engine.begin() as connection:
        measure_silver_advisories(connection, batch_id)
        rules, dimensions = write_history_report(connection, batch_id)
    print(
        f"Historique : {len(rules)} lignes de règles, {len(dimensions)} lignes dimension/couche."
    )
    print("Courbe : reports/us30_evolution_qualite.svg")


def measure_silver_advisories(connection, batch_id):
    clients = pd.read_sql_query(text("""
        SELECT source_systeme, source_id, type_personne, pays_iso, cp,
               ville_normalisee, telephone_normalise, email_normalise
        FROM silver.client WHERE _batch_id=:batch_id
    """), connection, params={"batch_id": batch_id})
    postal = pd.read_sql_query(
        text("SELECT code_postal, commune FROM silver.ref_postal"), connection
    )
    postal_pairs = {
        (str(row.code_postal).strip(), key(row.commune))
        for row in postal.itertuples()
    }
    crm = clients[
        (clients["source_systeme"] == "crm")
        & (clients["type_personne"] == "souscripteur")
    ]
    fr = clients[clients["pays_iso"] == "FR"]
    email_present = clients[
        clients["email_normalise"].apply(present)
    ]
    warning_metrics = {
        "RQ-003": (
            len(crm),
            int((~crm["telephone_normalise"].apply(present)).sum()),
        ),
        "RQ-004": (
            len(fr[fr["telephone_normalise"].apply(present)]),
            int((~fr[fr["telephone_normalise"].apply(present)]["telephone_normalise"]
                 .astype(str).str.fullmatch(r"0[1-9]\d{8}")).sum()),
        ),
        "RQ-005": (
            len(fr),
            int((~fr["cp"].fillna("").astype(str).str.fullmatch(r"\d{5}")).sum()),
        ),
        "RQ-006": (
            len(fr),
            int(sum(
                not row.cp
                or not row.ville_normalisee
                or (str(row.cp).strip(), key(row.ville_normalisee)) not in postal_pairs
                for row in fr.itertuples()
            )),
        ),
        "RQ-008": (
            len(email_present),
            int((~email_present["email_normalise"].astype(str).str.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+"
            )).sum()),
        ),
    }
    for rule_id, (tested, failed) in warning_metrics.items():
        connection.execute(text("""
            INSERT INTO dq.dq_history
                (batch_id,couche,rule_id,table_cible,nb_testees,nb_echecs)
            VALUES (:batch_id,'SILVER',:rule_id,'silver.client',:tested,:failed)
        """), {
            "batch_id": batch_id,
            "rule_id": rule_id,
            "tested": tested,
            "failed": failed,
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("history", "certify", "publish", "self-test")
    )
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", DB_URL_DEFAULT))
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    engine = create_engine(args.url)
    try:
        if args.action == "history":
            history(engine, args.batch_id)
        elif args.action == "certify":
            with engine.begin() as connection:
                measure_silver_advisories(connection, args.batch_id)
                write_history_report(connection, args.batch_id)
            certify(engine, args.batch_id)
            with engine.begin() as connection:
                rules, dimensions = write_history_report(connection, args.batch_id)
            print(
                f"Historique : {len(rules)} lignes de règles, "
                f"{len(dimensions)} lignes dimension/couche."
            )
        elif args.action == "publish":
            publish(engine, args.batch_id)
        else:
            self_test(engine, args.batch_id)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
