# -*- coding: utf-8 -*-
"""Vérifie RQ-020 avec Great Expectations et une alerte Soda sur copie."""
import os
import subprocess

import great_expectations as ge
import pandas as pd
from sqlalchemy import create_engine, text


DATA_ROOT = os.environ.get("ASSURCONNECT_DATA", "/home/jovyan/work/data")
REPORT_ROOT = "/home/jovyan/work/reports"
DATABASE_URL = os.environ.get("DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306")
KEYS = [
    ("crm.client", "sources/crm/client.csv", "client_id"),
    ("crm.contrat", "sources/crm/contrat.csv", "contrat_id"),
    ("crm.sinistre", "sources/crm/sinistre.csv", "sinistre_id"),
]
SODA_TEST_TABLE = "us08_client_copy"
SODA_CHECK_NAME = "US-08 duplicate RQ-020 test"


def read_source(relative_path):
    return pd.read_csv(
        os.path.join(DATA_ROOT, relative_path),
        dtype="string",
        keep_default_na=False,
        na_values=[r"\N"],
        encoding="utf-8",
    )


def check_source_keys():
    results = []
    frames = {}
    for table_name, path, key in KEYS:
        frame = read_source(path)
        frames[table_name] = frame
        validator = ge.from_pandas(frame)
        not_null = validator.expect_column_values_to_not_be_null(key)
        unique = validator.expect_column_values_to_be_unique(key)
        nonnull_count = int(frame[key].notna().sum())
        distinct_count = int(frame[key].nunique(dropna=True))
        results.append({
            "table": table_name,
            "key": key,
            "rows": len(frame),
            "nulls": int(frame[key].isna().sum()),
            "distinct_nonnull": distinct_count,
            "uniqueness_pct": round(100 * distinct_count / nonnull_count, 3) if nonnull_count else 0,
            "ge_not_null_pass": bool(not_null["success"]),
            "ge_unique_pass": bool(unique["success"]),
        })
        if not not_null["success"] or not unique["success"]:
            raise AssertionError(f"RQ-020 non conforme sur {table_name}.{key}")

    client_key = KEYS[0][2]
    duplicate_copy = pd.concat(
        [frames["crm.client"], frames["crm.client"].iloc[[0]]],
        ignore_index=True,
    )
    duplicate_validator = ge.from_pandas(duplicate_copy)
    duplicate_result = duplicate_validator.expect_column_values_to_be_unique(client_key)
    if duplicate_result["success"]:
        raise AssertionError("Great Expectations n'a pas détecté le doublon ajouté à la copie")
    results.append({
        "table": "crm.client (copie + doublon)",
        "key": client_key,
        "rows": len(duplicate_copy),
        "nulls": int(duplicate_copy[client_key].isna().sum()),
        "distinct_nonnull": int(duplicate_copy[client_key].nunique(dropna=True)),
        "uniqueness_pct": round(
            100 * duplicate_copy[client_key].nunique(dropna=True)
            / duplicate_copy[client_key].notna().sum(), 3
        ),
        "ge_not_null_pass": True,
        "ge_unique_pass": False,
    })
    return results


def run_soda_copy_test():
    engine = create_engine(DATABASE_URL)
    check_path = "/home/jovyan/work/soda/checks/us08_duplicate_copy_checks.yml"
    config_path = "/home/jovyan/work/soda/configuration.yml"
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS crm.{SODA_TEST_TABLE}"))
            connection.execute(text(
                f"CREATE TABLE crm.{SODA_TEST_TABLE} AS "
                "SELECT * FROM crm.client WHERE client_id IS NOT NULL LIMIT 2"
            ))
            connection.execute(text(
                f"INSERT INTO crm.{SODA_TEST_TABLE} "
                "SELECT * FROM crm.client WHERE client_id IS NOT NULL LIMIT 1"
            ))

        scan = subprocess.run(
            ["soda", "scan", "-d", "crm", "-c", config_path, check_path],
            cwd="/home/jovyan/work",
            capture_output=True,
            text=True,
            check=False,
        )
        output = f"{scan.stdout}\n{scan.stderr}"
        os.makedirs(REPORT_ROOT, exist_ok=True)
        with open(os.path.join(REPORT_ROOT, "us08_soda_duplicate_warning.txt"), "w", encoding="utf-8") as report:
            report.write(output)
        if SODA_CHECK_NAME not in output or "[WARNED]" not in output:
            raise AssertionError(
                "Soda n'a pas émis l'avertissement attendu sur la copie. "
                f"Code retour={scan.returncode}; sortie: {output}"
            )
        return output
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS crm.{SODA_TEST_TABLE}"))
            remaining = connection.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'crm' AND table_name = :table_name"
            ), {"table_name": SODA_TEST_TABLE}).scalar()
            if remaining:
                raise AssertionError("La copie temporaire Soda n'a pas été supprimée")
        engine.dispose()


def main():
    results = check_source_keys()
    os.makedirs(REPORT_ROOT, exist_ok=True)
    metrics_path = os.path.join(REPORT_ROOT, "us08_key_uniqueness.csv")
    pd.DataFrame(results).to_csv(metrics_path, index=False)
    print(pd.DataFrame(results).to_string(index=False))
    print("Great Expectations: le doublon ajouté à la copie fait échouer l'unicité.")
    run_soda_copy_test()
    print("Soda: avertissement RQ-020 confirmé sur la copie doublonnée.")
    print(f"Mesures RQ-020: {metrics_path}")
    print("Copie Soda nettoyée; les tables sources sont intactes.")


if __name__ == "__main__":
    main()
