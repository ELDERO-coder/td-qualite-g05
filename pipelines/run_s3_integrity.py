# -*- coding: utf-8 -*-
"""Mesure les intégrités inter-tables et statuts S3 sur la couche Bronze."""
import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


BATCH_DEFAULT = "L-2026-10-14"
DB_URL_DEFAULT = "mysql+pymysql://root:root@mariadb:3306"
ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def measure(connection, rule_id, table, sql, batch_id):
    row = connection.execute(
        text(sql), {"batch_id": batch_id}
    ).mappings().one()
    tested = int(row["testees"])
    failures = int(row["echecs"])
    return {
        "rule_id": rule_id,
        "table_cible": table,
        "tested": tested,
        "failures": failures,
        "success_rate": round(100 * (tested - failures) / tested, 3)
        if tested else 100.0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_DEFAULT)
    parser.add_argument("--url", default=os.environ.get("DQ_DB_URL", DB_URL_DEFAULT))
    args = parser.parse_args()
    engine = create_engine(args.url)

    relation_sql = (
        (
            "Contrat.souscripteur_id → client",
            """
            SELECT COUNT(*) AS testees,
                   SUM(k.souscripteur_id IS NULL OR c.client_id IS NULL) AS echecs
            FROM bronze.crm_contrat k
            LEFT JOIN bronze.crm_client c
              ON c.client_id = k.souscripteur_id AND c._batch_id = k._batch_id
            WHERE k._batch_id = :batch_id
            """,
        ),
        (
            "Contrat.code_type → type_contrat",
            """
            SELECT COUNT(*) AS testees,
                   SUM(k.code_type IS NULL OR t.code_type IS NULL) AS echecs
            FROM bronze.crm_contrat k
            LEFT JOIN bronze.crm_type_contrat t
              ON t.code_type = k.code_type AND t._batch_id = k._batch_id
            WHERE k._batch_id = :batch_id
            """,
        ),
        (
            "Contrat.assure_id → client (avant sentinelle)",
            """
            SELECT COUNT(*) AS testees,
                   SUM(k.assure_id IS NULL OR c.client_id IS NULL) AS echecs
            FROM bronze.crm_contrat k
            LEFT JOIN bronze.crm_client c
              ON c.client_id = k.assure_id AND c._batch_id = k._batch_id
            WHERE k._batch_id = :batch_id
            """,
        ),
        (
            "Sinistre.contrat_id → contrat",
            """
            SELECT COUNT(*) AS testees,
                   SUM(s.contrat_id IS NULL OR k.contrat_id IS NULL) AS echecs
            FROM bronze.crm_sinistre s
            LEFT JOIN bronze.crm_contrat k
              ON k.contrat_id = s.contrat_id AND k._batch_id = s._batch_id
            WHERE s._batch_id = :batch_id
            """,
        ),
    )

    measurements = []
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT statut FROM dq.lot_ingestion WHERE batch_id = :batch_id"),
            {"batch_id": args.batch_id},
        ).scalar()
        if status != "TERMINE":
            raise RuntimeError(f"Le lot {args.batch_id} n'existe pas ou n'est pas terminé")

        relation_results = []
        for label, sql in relation_sql:
            result = measure(
                connection, "US-16", label, sql, args.batch_id
            )
            relation_results.append({
                "relation": label,
                "lignes_testees": result["tested"],
                "orphelins": result["failures"],
                "taux_conformite": result["success_rate"],
            })

        sentinel = connection.execute(text("""
            SELECT
                COUNT(*) AS total_contrats,
                SUM(assure_id = '0') AS sentinelles,
                SUM(assure_id IS NULL) AS assure_absent,
                SUM(assure_id <> '0' AND c.client_id IS NULL) AS vrais_orphelins,
                SUM(assure_id <> '0') AS lignes_apres_exclusion
            FROM bronze.crm_contrat k
            LEFT JOIN bronze.crm_client c
              ON c.client_id = k.assure_id AND c._batch_id = k._batch_id
            WHERE k._batch_id = :batch_id
        """), {"batch_id": args.batch_id}).mappings().one()

        status_results = []
        status_sql = (
            (
                "RQ-015",
                "prospect",
                """
                SELECT COUNT(*) AS testees,
                       SUM(EXISTS (
                           SELECT 1 FROM bronze.crm_contrat k
                           WHERE k._batch_id = c._batch_id
                             AND k.souscripteur_id = c.client_id
                       )) AS echecs
                FROM bronze.crm_client c
                WHERE c._batch_id = :batch_id AND c.type_personne = 'prospect'
                """,
                "Prospect ayant au moins un contrat comme souscripteur",
            ),
            (
                "RQ-016",
                "souscripteur",
                """
                SELECT COUNT(*) AS testees,
                       SUM(NOT EXISTS (
                           SELECT 1 FROM bronze.crm_contrat k
                           WHERE k._batch_id = c._batch_id
                             AND k.souscripteur_id = c.client_id
                       )) AS echecs
                FROM bronze.crm_client c
                WHERE c._batch_id = :batch_id AND c.type_personne = 'souscripteur'
                """,
                "Souscripteur sans contrat",
            ),
        )
        for rule_id, entity, sql, description in status_sql:
            result = measure(
                connection, rule_id, f"bronze.crm_client ({entity})", sql, args.batch_id
            )
            status_results.append({
                "rule_id": rule_id,
                "controle": description,
                "lignes_testees": result["tested"],
                "lignes_en_echec": result["failures"],
                "taux_conformite": result["success_rate"],
            })
            measurements.append(result)

        coverage_sql = """
            SELECT COUNT(*) AS testees,
                   SUM(k.contrat_id IS NULL
                       OR STR_TO_DATE(s.date_survenance, '%Y-%m-%d') IS NULL
                       OR STR_TO_DATE(k.date_debut, '%Y-%m-%d') IS NULL
                       OR STR_TO_DATE(k.date_fin, '%Y-%m-%d') IS NULL
                       OR STR_TO_DATE(s.date_survenance, '%Y-%m-%d')
                            < STR_TO_DATE(k.date_debut, '%Y-%m-%d')
                       OR STR_TO_DATE(s.date_survenance, '%Y-%m-%d')
                            > STR_TO_DATE(k.date_fin, '%Y-%m-%d')) AS echecs
            FROM bronze.crm_sinistre s
            LEFT JOIN bronze.crm_contrat k
              ON k.contrat_id = s.contrat_id AND k._batch_id = s._batch_id
            WHERE s._batch_id = :batch_id
        """
        coverage = measure(
            connection, "RQ-017", "bronze.crm_sinistre", coverage_sql, args.batch_id
        )
        measurements.append(coverage)

        active_query = (ROOT / "pipelines" / "us14_client_actif.sql").read_text(
            encoding="utf-8"
        )
        active_results = pd.read_sql_query(text(active_query), connection, params={
            "batch_id": args.batch_id,
            "date_reference": "2026-10-01",
            "debut_fenetre_cotisation": "2026-07-01",
        })
        active_counts = active_results["clients_actifs"].astype(int)
        active_failures = int(active_counts.nunique() != 1)
        measurements.append({
            "rule_id": "RQ-018",
            "table_cible": "bronze.us14_client_actif",
            "tested": int(len(active_results)),
            "failures": active_failures,
            "success_rate": 100.0 if active_failures == 0 else 0.0,
        })

    sentinel_rows = [
        {
            "controle": "Assurés non nuls, sentinelle incluse",
            "lignes_testees": int(sentinel["total_contrats"])
            - int(sentinel["assure_absent"]),
            "orphelins": int(sentinel["sentinelles"] + sentinel["vrais_orphelins"]),
            "convention": "La valeur '0' compte à tort comme un orphelin",
        },
        {
            "controle": "Après exclusion de la sentinelle '0'",
            "lignes_testees": int(sentinel["lignes_apres_exclusion"]),
            "orphelins": int(sentinel["vrais_orphelins"]),
            "convention": "Remplacer '0' par NULL en Silver ; ne pas créer de client fictif",
        },
    ]

    REPORTS.mkdir(exist_ok=True)
    pd.DataFrame(relation_results).to_csv(
        REPORTS / "us16_integrite.csv", index=False
    )
    pd.DataFrame(sentinel_rows).to_csv(
        REPORTS / "us17_sentinelle.csv", index=False
    )
    pd.DataFrame(status_results).to_csv(
        REPORTS / "us18_statuts.csv", index=False
    )
    pd.DataFrame([coverage]).rename(columns={
        "table_cible": "table",
        "tested": "lignes_testees",
        "failures": "lignes_en_echec",
        "success_rate": "taux_conformite",
    }).to_csv(REPORTS / "us19_garantie.csv", index=False)
    active_results.to_csv(REPORTS / "us14_client_actif.csv", index=False)

    with engine.begin() as connection:
        for result in measurements:
            connection.execute(text("""
                INSERT INTO dq.dq_history
                    (batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs)
                VALUES
                    (:batch_id, 'BRONZE', :rule_id, :table_cible,
                     :nb_testees, :nb_echecs)
            """), {
                "batch_id": args.batch_id,
                "rule_id": result["rule_id"],
                "table_cible": result["table_cible"],
                "nb_testees": result["tested"],
                "nb_echecs": result["failures"],
            })

    print("US-16", pd.DataFrame(relation_results).to_string(index=False))
    print("US-17", pd.DataFrame(sentinel_rows).to_string(index=False))
    print("US-18", pd.DataFrame(status_results).to_string(index=False))
    print("US-19", pd.DataFrame([coverage]).to_string(index=False))
    print("US-14", active_results.to_string(index=False))
    engine.dispose()


if __name__ == "__main__":
    main()
