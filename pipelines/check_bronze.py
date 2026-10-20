# -*- coding: utf-8 -*-
"""Réconcilie les sources avec Bronze et historise les portes B RQ-021/RQ-022."""
import argparse
import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text

TABLES = [
    ("crm", "client", "crm_client"),
    ("crm", "contrat", "crm_contrat"),
    ("crm", "sinistre", "crm_sinistre"),
    ("crm", "type_contrat", "crm_type_contrat"),
    ("cif", "clients", "cif_clients"),
    ("cif", "compte", "cif_compte"),
    ("cif", "pays", "cif_pays"),
]


def as_text(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def row_hash(values):
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def metadata(connection, schema, table):
    return [row["name"] for row in connection.execute(text(
        "SELECT COLUMN_NAME AS name FROM information_schema.columns "
        "WHERE table_schema=:schema AND table_name=:table ORDER BY ordinal_position"
    ), {"schema": schema, "table": table}).mappings()]


def primary_key(connection, schema, table):
    return [row["name"] for row in connection.execute(text(
        "SELECT COLUMN_NAME AS name FROM information_schema.key_column_usage "
        "WHERE table_schema=:schema AND table_name=:table AND constraint_name='PRIMARY' "
        "ORDER BY ordinal_position"
    ), {"schema": schema, "table": table}).mappings()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="L-2026-10-14")
    parser.add_argument("--url", default=os.environ.get(
        "DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"))
    args = parser.parse_args()
    engine = create_engine(args.url)
    failures = 0
    print("table source bronze ecart_lignes empreintes_diff metadonnees_invalides")

    with engine.begin() as connection:
        for schema, source_table, bronze_table in TABLES:
            columns = metadata(connection, schema, source_table)
            keys = primary_key(connection, schema, source_table)
            if not columns or not keys:
                raise RuntimeError(f"Schéma ou clé primaire manquante : {schema}.{source_table}")
            quoted = ", ".join(f"`{column}`" for column in columns)
            order = ", ".join(f"`{column}`" for column in keys)
            source_rows = connection.execute(text(
                f"SELECT {quoted} FROM `{schema}`.`{source_table}` ORDER BY {order}"
            )).fetchall()
            bronze_rows = connection.execute(text(
                f"SELECT {quoted}, `_row_hash`, `_batch_id`, `_source_system`, `_ingested_at` "
                f"FROM bronze.`{bronze_table}` WHERE `_batch_id`=:batch ORDER BY {order}"
            ), {"batch": args.batch_id}).fetchall()

            mismatches = 0
            for index in range(min(len(source_rows), len(bronze_rows))):
                values = [as_text(value) for value in source_rows[index]]
                actual = bronze_rows[index]
                row_failed = values != [as_text(value) for value in actual[:len(columns)]]
                row_failed = row_failed or row_hash(values) != actual[len(columns)]
                if row_failed:
                    mismatches += 1

            metadata_failures = sum(
                1 for row in bronze_rows
                if row[len(columns) + 1] != args.batch_id
                or row[len(columns) + 2] != schema
                or row[len(columns) + 3] is None
                or row[len(columns)] is None
            )
            source_count, bronze_count = len(source_rows), len(bronze_rows)
            count_delta = abs(source_count - bronze_count)
            reconciled_failures = mismatches + count_delta
            tested = max(source_count, bronze_count, 1)
            for rule_id, failed in (("RQ-021", reconciled_failures),
                                    ("RQ-022", metadata_failures)):
                connection.execute(text(
                    "INSERT INTO dq.dq_history "
                    "(batch_id, couche, rule_id, table_cible, nb_testees, nb_echecs) "
                    "VALUES (:batch, 'BRONZE', :rule, :target, :tested, :failed)"
                ), {"batch": args.batch_id, "rule": rule_id,
                    "target": bronze_table, "tested": tested, "failed": failed})
            failures += reconciled_failures + metadata_failures
            print(f"{bronze_table} {source_count} {bronze_count} {count_delta} "
                  f"{mismatches} {metadata_failures}")

    print(f"Porte B : {'OK' if failures == 0 else 'ECHEC'}; écarts={failures}; "
          f"historique RQ-021/RQ-022 enregistré pour {args.batch_id}.")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()