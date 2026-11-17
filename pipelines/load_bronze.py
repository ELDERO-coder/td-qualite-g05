# -*- coding: utf-8 -*-
"""Copie les tables sources dans Bronze avec métadonnées et empreinte de ligne."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default="L-2026-10-14")
    parser.add_argument("--url", default=os.environ.get(
        "DQ_DB_URL", "mysql+pymysql://root:root@mariadb:3306"))
    parser.add_argument("--chunksize", type=int, default=2000)
    args = parser.parse_args()
    if args.chunksize < 1:
        parser.error("--chunksize doit être supérieur à zéro")

    engine = create_engine(args.url)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO dq.lot_ingestion (batch_id, statut) VALUES (:batch, 'EN_COURS') "
            "ON DUPLICATE KEY UPDATE started_at=CURRENT_TIMESTAMP, finished_at=NULL, statut='EN_COURS'"
        ), {"batch": args.batch_id})

        for source_schema, source_table, bronze_table in TABLES:
            columns = [row["name"] for row in connection.execute(text(
                "SELECT COLUMN_NAME AS name FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name=:table ORDER BY ordinal_position"
            ), {"schema": source_schema, "table": source_table}).mappings()]
            quoted_columns = ", ".join(f"`{column}`" for column in columns)
            connection.execute(text(
                f"DELETE FROM bronze.`{bronze_table}` WHERE _batch_id=:batch"
            ), {"batch": args.batch_id})
            insert_columns = quoted_columns + ", `_batch_id`, `_source_system`, `_row_hash`"
            values_clause = ", ".join(f":{column}" for column in columns)
            insert_sql = text(
                f"INSERT INTO bronze.`{bronze_table}` ({insert_columns}) "
                f"VALUES ({values_clause}, :_batch_id, :_source_system, :_row_hash)"
            )
            total = 0
            offset = 0
            while True:
                rows = connection.execute(text(
                    f"SELECT {quoted_columns} FROM `{source_schema}`.`{source_table}` "
                    "LIMIT :limit OFFSET :offset"
                ), {"limit": args.chunksize, "offset": offset}).fetchall()
                if not rows:
                    break
                prepared = []
                for row in rows:
                    raw_values = [as_text(value) for value in row]
                    item = dict(zip(columns, raw_values))
                    item.update({
                        "_batch_id": args.batch_id,
                        "_source_system": source_schema,
                        "_row_hash": row_hash(raw_values),
                    })
                    prepared.append(item)
                connection.execute(insert_sql, prepared)
                total += len(prepared)
                offset += len(prepared)
            print(f"{source_schema}.{source_table} -> bronze.{bronze_table}: {total}")

        connection.execute(text(
            "UPDATE dq.lot_ingestion SET finished_at=CURRENT_TIMESTAMP, statut='TERMINE' "
            "WHERE batch_id=:batch"
        ), {"batch": args.batch_id})
    print(f"Lot {args.batch_id} terminé.")


if __name__ == "__main__":
    main()