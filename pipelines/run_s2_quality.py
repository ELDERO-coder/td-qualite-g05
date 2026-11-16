# -*- coding: utf-8 -*-
"""Mesure les règles S2 sur Bronze avec Great Expectations."""
import argparse
import os
from pathlib import Path

import pandas as pd
from great_expectations.dataset import PandasDataset
from sqlalchemy import create_engine, text


BATCH_DEFAULT = "L-2026-10-14"
REPORTS = Path(__file__).resolve().parents[1] / "reports"
DB_URL_DEFAULT = "mysql+pymysql://root:root@mariadb:3306"

CHECKS = (
    {
        "rule_id": "RQ-001",
        "table": "bronze.crm_contrat",
        "sql": """
            SELECT k.bronze_row_id, k.contrat_id AS identifiant,
                   CONCAT('date_debut=', COALESCE(k.date_debut, 'NULL'),
                          '; date_fin=', COALESCE(k.date_fin, 'NULL')) AS valeur,
                   CASE WHEN debut IS NOT NULL AND fin IS NOT NULL AND fin > debut
                        THEN 1 ELSE 0 END AS conforme,
                   'date_fin doit être postérieure à date_debut' AS cause
            FROM (
                SELECT bronze_row_id, contrat_id, date_debut, date_fin,
                       STR_TO_DATE(date_debut, '%Y-%m-%d') AS debut,
                       STR_TO_DATE(date_fin, '%Y-%m-%d') AS fin
                FROM bronze.crm_contrat WHERE _batch_id = :batch_id
            ) k
        """,
    },
    {
        "rule_id": "RQ-002",
        "table": "bronze.crm_contrat",
        "sql": """
            SELECT k.bronze_row_id, k.contrat_id AS identifiant,
                   CONCAT('souscripteur=', k.souscripteur_id,
                          '; naissance=', COALESCE(c.date_naissance, 'NULL'),
                          '; début=', COALESCE(k.date_debut, 'NULL')) AS valeur,
                   CASE WHEN c.date_naissance IS NOT NULL AND k.date_debut IS NOT NULL
                             AND TIMESTAMPDIFF(
                                 YEAR,
                                 STR_TO_DATE(c.date_naissance, '%Y-%m-%d'),
                                 STR_TO_DATE(k.date_debut, '%Y-%m-%d')
                             ) >= 18
                        THEN 1 ELSE 0 END AS conforme,
                   'souscripteur personne physique âgé de moins de 18 ans au début du contrat'
                       AS cause
            FROM bronze.crm_contrat k
            JOIN bronze.crm_client c
              ON c.client_id = k.souscripteur_id AND c._batch_id = :batch_id
            WHERE k._batch_id = :batch_id
              AND c.type_personne = 'souscripteur' AND c.raison_sociale IS NULL
        """,
    },
    {
        "rule_id": "RQ-003",
        "table": "bronze.crm_client",
        "sql": """
            SELECT bronze_row_id, client_id AS identifiant, telephone AS valeur,
                   CASE WHEN telephone IS NOT NULL AND TRIM(telephone) <> ''
                        THEN 1 ELSE 0 END AS conforme,
                   'téléphone du souscripteur nul, vide ou blanc' AS cause
            FROM bronze.crm_client
            WHERE _batch_id = :batch_id AND type_personne = 'souscripteur'
        """,
    },
    {
        "rule_id": "RQ-005",
        "table": "bronze.crm_client",
        "sql": """
            SELECT bronze_row_id, client_id AS identifiant, cp AS valeur,
                   CASE WHEN cp REGEXP '^[0-9]{5}$' THEN 1 ELSE 0 END AS conforme,
                   'code postal français absent ou différent de cinq chiffres' AS cause
            FROM bronze.crm_client
            WHERE _batch_id = :batch_id AND pays = 'FR'
        """,
    },
    {
        "rule_id": "RQ-009",
        "table": "bronze.crm_client",
        "sql": """
            SELECT bronze_row_id, client_id AS identifiant,
                   COALESCE(type_personne, 'NULL') AS valeur,
                   CASE WHEN type_personne IN ('prospect', 'souscripteur', 'assure')
                        THEN 1 ELSE 0 END AS conforme,
                   'type_personne absent ou hors domaine autorisé' AS cause
            FROM bronze.crm_client WHERE _batch_id = :batch_id
        """,
    },
    {
        "rule_id": "RQ-010",
        "table": "bronze.crm_contrat",
        "sql": """
            SELECT bronze_row_id, contrat_id AS identifiant,
                   COALESCE(duree_garantie_mois, 'NULL') AS valeur,
                   CASE WHEN duree_garantie_mois IN ('12', '24', '36', '60')
                        THEN 1 ELSE 0 END AS conforme,
                   'durée de garantie absente ou hors domaine (12, 24, 36, 60 mois)'
                       AS cause
            FROM bronze.crm_contrat WHERE _batch_id = :batch_id
        """,
    },
)


def collect_key_checks(connection, batch_id):
    inputs = []
    for table, key in (
        ("crm_client", "client_id"),
        ("crm_contrat", "contrat_id"),
        ("crm_sinistre", "sinistre_id"),
    ):
        query = text(f"""
            SELECT bronze_row_id, `{key}` AS identifiant, `{key}` AS valeur,
                   CASE WHEN `{key}` IS NOT NULL
                             AND COUNT(*) OVER (PARTITION BY `{key}`) = 1
                        THEN 1 ELSE 0 END AS conforme,
                   CASE WHEN `{key}` IS NULL THEN 'clé primaire nulle'
                        ELSE 'clé primaire dupliquée' END AS cause
            FROM bronze.`{table}`
            WHERE _batch_id = :batch_id
        """)
        frame = pd.read_sql_query(query, connection, params={"batch_id": batch_id})
        inputs.append(("RQ-020", f"bronze.{table}", frame))
    return inputs


def prepare_age_comparison(connection, batch_id):
    query = text("""
        SELECT k.contrat_id, k.souscripteur_id,
               c.date_naissance, k.date_debut,
               CASE WHEN STR_TO_DATE(c.date_naissance, '%Y-%m-%d') IS NOT NULL
                         AND STR_TO_DATE(k.date_debut, '%Y-%m-%d') IS NOT NULL
                         AND TIMESTAMPDIFF(
                             YEAR,
                             STR_TO_DATE(c.date_naissance, '%Y-%m-%d'),
                             STR_TO_DATE(k.date_debut, '%Y-%m-%d')
                         ) >= 18
                    THEN 1 ELSE 0 END AS conforme_debut,
               CASE WHEN STR_TO_DATE(c.date_naissance, '%Y-%m-%d') IS NOT NULL
                         AND TIMESTAMPDIFF(
                             YEAR, STR_TO_DATE(c.date_naissance, '%Y-%m-%d'), CURRENT_DATE
                         ) >= 18
                    THEN 1 ELSE 0 END AS conforme_aujourd_hui
        FROM bronze.crm_contrat k
        JOIN bronze.crm_client c
          ON c.client_id = k.souscripteur_id AND c._batch_id = :batch_id
        WHERE k._batch_id = :batch_id
          AND c.type_personne = 'souscripteur' AND c.raison_sociale IS NULL
    """)
    return pd.read_sql_query(query, connection, params={"batch_id": batch_id})


def validate(rule_id, table, frame):
    if frame.empty:
        raise RuntimeError(f"{rule_id} sur {table}: aucune ligne éligible au contrôle")
    values = frame["conforme"].fillna(0).astype(bool)
    dataset = PandasDataset(pd.DataFrame({"conforme": values}))
    result = dataset.expect_column_values_to_be_in_set(
        "conforme",
        [True],
        result_format="COMPLETE",
        meta={"rule_id": rule_id, "table_cible": table},
    )
    details = result["result"]
    failures = int(details["unexpected_count"])
    total = int(details["element_count"])
    failed_frame = frame.loc[~values].copy()
    failed_frame.insert(0, "table_cible", table)
    failed_frame.insert(0, "rule_id", rule_id)
    return {
        "rule_id": rule_id,
        "table_cible": table,
        "expectation": "expect_column_values_to_be_in_set(conforme, [True])",
        "tested": total,
        "failures": failures,
        "success_rate": round(100 * (total - failures) / total, 3),
        "ge_success": bool(result["success"]),
    }, failed_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", DB_URL_DEFAULT))
    args = parser.parse_args()
    engine = create_engine(args.url)

    measurements = []
    failures = []
    key_checks = []
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT statut FROM dq.lot_ingestion WHERE batch_id = :batch_id"),
            {"batch_id": args.batch_id},
        ).scalar()
        if status != "TERMINE":
            raise RuntimeError(f"Le lot {args.batch_id} n'existe pas ou n'est pas terminé")

        for check in CHECKS:
            frame = pd.read_sql_query(
                text(check["sql"]), connection, params={"batch_id": args.batch_id}
            )
            measurement, failed = validate(check["rule_id"], check["table"], frame)
            measurements.append(measurement)
            failures.append(failed)

        key_checks = collect_key_checks(connection, args.batch_id)
        for rule_id, table, frame in key_checks:
            measurement, failed = validate(rule_id, table, frame)
            measurements.append(measurement)
            failures.append(failed)
        ages = prepare_age_comparison(connection, args.batch_id)

    failure_rows = pd.concat(failures, ignore_index=True)
    REPORTS.mkdir(exist_ok=True)
    pd.DataFrame(measurements).to_csv(REPORTS / "us10_ge_results.csv", index=False)
    failure_rows.to_csv(REPORTS / "us11_echecs_complets.csv", index=False)
    sample = []
    for _, group in failure_rows.groupby("rule_id", sort=True):
        sample.append(group.head(3))
    sample_frame = pd.concat(sample)
    if len(sample_frame) < 20:
        remaining = failure_rows.drop(index=sample_frame.index)
        for _, group in remaining.groupby("rule_id", sort=True):
            needed = 20 - len(sample_frame)
            if needed <= 0:
                break
            sample_frame = pd.concat([sample_frame, group.head(needed)])
    sample_frame.head(20).reset_index(drop=True).to_csv(
        REPORTS / "us11_echantillon_20.csv", index=False
    )

    age_summary = pd.DataFrame([
        {
            "date_reference": "date_debut_contrat",
            "lignes_testees": len(ages),
            "lignes_en_echec": int((ages["conforme_debut"] == 0).sum()),
        },
        {
            "date_reference": "date_du_jour",
            "lignes_testees": len(ages),
            "lignes_en_echec": int((ages["conforme_aujourd_hui"] == 0).sum()),
        },
        {
            "date_reference": "majeurs_depuis_debut_contrat",
            "lignes_testees": len(ages),
            "lignes_en_echec": int(
                ((ages["conforme_debut"] == 0)
                 & (ages["conforme_aujourd_hui"] == 1)).sum()
            ),
        },
    ])
    age_summary.to_csv(REPORTS / "us13_age_reference.csv", index=False)

    with engine.begin() as connection:
        for measurement in measurements:
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES
                    (:batch_id, 'BRONZE', :rule_id, :table_cible, :nb_testees, :nb_echecs)
            """), {
                "batch_id": args.batch_id,
                "rule_id": measurement["rule_id"],
                "table_cible": measurement["table_cible"],
                "nb_testees": measurement["tested"],
                "nb_echecs": measurement["failures"],
            })

    print(pd.DataFrame(measurements).to_string(index=False))
    print(age_summary.to_string(index=False))
    print(f"Échecs détaillés : {REPORTS / 'us11_echecs_complets.csv'}")
    print(f"Échantillon de 20 : {REPORTS / 'us11_echantillon_20.csv'}")
    engine.dispose()
if __name__ == "__main__":
    main()
